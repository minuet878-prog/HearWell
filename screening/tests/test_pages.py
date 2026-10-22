import json
import re
import struct
from datetime import date
from pathlib import Path
from typing import ClassVar

from django.contrib.staticfiles import finders
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import (
    Answer,
    Audiogram,
    Category,
    Question,
    Questionnaire,
    ReportShare,
    Submission,
    User,
)
from screening.questionnaires import hhie_s
from screening.scoring import classify, get_advice
from screening.tests import test_answering, test_history
from screening.tests.helpers import consented_user, fake_definition, register


class CopyTests(TestCase):
    LONG_QUESTION = "這是一題為了測試截斷而刻意寫得很長的題目，超過三十個字之後也必須完整顯示嗎？"
    INTRO = (
        "本問卷的目的在幫助您了解自己的聽力是否對於日常生活造成了影響。"
        "已選配助聽器一段時間後，可以再填一次，有助於了解所配的助聽器是否真的有幫助。"
        "請在閱讀每項問題後圈選常常、有時或從未。"
    )
    ADVICE: ClassVar[dict[str, str]] = {
        "mild_to_moderate": (
            "聽力的問題已經慢慢開始影響到您的社交活動以及情緒，例如"
            "與家人之間常常因為聽不清楚或是電視聲音等而產生爭吵、在多人且吵雜的"
            "社交環境當中會因為聽不清楚而導致社交上的窘迫及退縮，許多聽力衰退"
            "帶來的問題是微妙且和緩的，但經過此次篩檢能夠讓您體認到聽力對自身生"
            "活的影響，建議前往醫院耳鼻喉科進行聽力相關檢查及詢問相關專業意見。"
        ),
        "severe": (
            "聽力問題已經嚴重影響到您的生活了，許多人常常會忽視這一塊，聽不到這件事"
            "情往往已經十分嚴重了才會發現，若您尚未採取任何行動建議立即前往醫院耳鼻"
            "喉科尋求專業建議，並且考慮配戴助聽器。聽力喪失影響的並不只是聽不聽得到，"
            "無形中也會增加社交活動的壓力（例如因為聽不清楚常會在聊天的過程中退縮、"
            "裝作聽得懂等），這些壓力以及情緒的低落會增加長者的認知負擔。"
        ),
    }

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="tester")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.question = Question.objects.create(
            questionnaire=cls.questionnaire,
            question_text=cls.LONG_QUESTION,
            question_number=1,
            category=Category.EMOTIONAL,
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.questionnaire.id])

    def test_question_text_is_not_truncated(self):
        self.assertGreater(len(self.LONG_QUESTION), 30)
        self.assertContains(
            self.client.get(self.url), f"第 1 題／共 1 題</span>{self.LONG_QUESTION}"
        )

    def test_question_text_full_after_validation_error(self):
        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-0-score": "4",
            "form-0-question_id": str(self.question.id),
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"第 1 題／共 1 題</span>{self.LONG_QUESTION}")

    def test_intro_typo_fixed(self):
        response = self.client.get(self.url)
        self.assertContains(response, self.INTRO)
        self.assertNotContains(response, "以選配了助聽器格")

    def test_advice_text(self):
        for level in ("normal", "mild_to_moderate", "severe", "unknown"):
            with self.subTest(level=level):
                advice = get_advice(level)
                for banned in ("ex.", "(", ")", "你"):
                    self.assertNotIn(banned, advice)
                if level in self.ADVICE:
                    self.assertEqual(advice, self.ADVICE[level])

    def test_login_title_in_chinese(self):
        self.client.logout()
        response = self.client.get(reverse("login"))
        self.assertContains(response, '<h1 class="h3 mb-4 font-normal">登入</h1>', html=True)
        self.assertNotContains(response, "Welcome")

    def test_sign_in_status_in_chinese(self):
        response = self.client.get(reverse("index"))
        self.assertContains(response, "目前登入：<strong>tester</strong>")
        self.assertNotContains(response, "Signed in")
        self.client.logout()
        response = self.client.get(reverse("index"))
        # Logged out: the header shows nothing (spec phase4_ui_redesign 4.2), still no English.
        for english in ("Signed in", "Not signed in"):
            self.assertNotContains(response, english)

    def test_history_button_label(self):
        submission = Submission.objects.create(user=self.user, questionnaire=self.questionnaire)
        result_url = reverse("result", args=[submission.id])
        response = self.client.get(reverse("my_hearing"))
        # The whole record is one link (spec phase9_ui_refresh_1_shared.md 4.5), no button.
        self.assertContains(response, f'<a class="link-card" href="{result_url}">')
        self.assertNotContains(response, "查看結果")
        self.assertNotContains(response, "連結")

    def test_empty_history_uses_polite_you(self):
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, "您還沒有做過篩檢紀錄")
        self.assertNotContains(response, "你還沒有")

    def test_questionnaire_list_has_no_orphan_li(self):
        content = self.client.get(reverse("questionnaire_list")).content.decode()
        # <li followed by space or >, so <link> in <head> is not counted.
        self.assertEqual(len(re.findall(r"<li[\s>]", content)), content.count("</li>"))


class AccessibilityTests(TestCase):
    PROMPT = "這次填答時，您有沒有戴助聽器？"

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="tester")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        for number, category in ((1, Category.EMOTIONAL), (2, Category.SOCIAL)):
            Question.objects.create(
                questionnaire=cls.questionnaire,
                question_text=f"第{number}題",
                question_number=number,
                category=category,
            )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.questionnaire.id])

    def test_each_question_in_fieldset_with_legend(self):
        content = self.client.get(self.url).content.decode()
        self.assertEqual(content.count("<fieldset"), 3)
        legends = (
            self.PROMPT,
            '<span class="question-progress">第 1 題／共 2 題</span>第1題',
            '<span class="question-progress">第 2 題／共 2 題</span>第2題',
        )
        for legend in legends:
            with self.subTest(legend=legend):
                self.assertRegex(content, rf"<legend[^>]*>\s*{re.escape(legend)}\s*</legend>")

    def test_hearing_aid_error_linked_to_group(self):
        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-0-score": "4",
            "form-0-question_id": str(Question.objects.get(question_number=1).id),
        }
        content = self.client.post(self.url, data).content.decode()
        self.assertRegex(content, r'<fieldset[^>]*aria-describedby="id_wearing_hearing_aid_error"')
        self.assertRegex(
            content, r'id="id_wearing_hearing_aid_error">\s*<p[^>]*>請選擇這次有沒有戴助聽器'
        )

    def test_choices_are_large_horizontal_buttons(self):
        response = self.client.get(self.url)
        self.assertContains(response, '<div id="id_wearing_hearing_aid" class="choice-group">')
        self.assertContains(response, '<div id="id_form-0-score" class="choice-group">')
        # The input sits inside its label, so the whole button is clickable.
        self.assertRegex(response.content.decode(), r'<label for="id_form-0-score_0">\s*<input')


class HeaderBrandTests(TestCase):
    """The white header with the wave-W logo and the two-colour wordmark."""

    def _brand(self, content):
        return re.search(r'<p class="site-brand">(.*?)</p>', content, re.DOTALL).group(1)

    def test_brand_reads_hearwell_and_the_logo_is_decoration(self):
        for logged_in in (False, True):
            if logged_in:
                self.client.force_login(consented_user(username="brandtester"))
            with self.subTest(logged_in=logged_in):
                brand = self._brand(self.client.get(reverse("index")).content.decode())
                self.assertRegex(brand, r'<span class="site-logo" aria-hidden="true"></span>')
                self.assertEqual(re.sub(r"<[^>]+>|\s", "", brand), "HearWell")
                self.assertIn('<span class="site-wordmark-tint">Well</span>', brand)

    def test_header_buttons_are_blue_outlines_on_the_white_header(self):
        self.client.force_login(consented_user(username="logouttester"))
        content = self.client.get(reverse("questionnaire_list")).content.decode()
        self.assertRegex(
            content, r'<button class="btn btn-outline-primary" type="submit">登出</button>'
        )
        self.assertRegex(content, r'id="pwa-back" class="btn btn-outline-primary site-back"')
        self.assertNotIn("btn-outline-light", content)


class RedesignLayoutTests(TestCase):
    NAV = re.compile(r'<nav aria-label="主要導覽".*?</nav>', re.DOTALL)
    LOGGED_IN_ITEMS = ("首頁", "開始篩檢", "我的紀錄", "聽力圖")
    LOGGED_OUT_ITEMS = ("首頁", "登入", "註冊")

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="alice_account", password="secret-pass-123")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.submission = Submission.objects.create(user=cls.user, questionnaire=cls.questionnaire)

    def _nav(self, response):
        self.assertEqual(response.status_code, 200)
        navs = self.NAV.findall(response.content.decode())
        self.assertEqual(len(navs), 1)
        return navs[0]

    def _nav_labels(self, nav):
        return re.findall(r"<span[^>]*>([^<]+)</span>\s*</a>", nav)

    def _logged_in_pages(self):
        return {
            reverse("index"): "首頁",
            reverse("questionnaire_list"): "開始篩檢",
            reverse("screening", args=[self.questionnaire.id]): "開始篩檢",
            reverse("result", args=[self.submission.id]): "我的紀錄",
            reverse("my_hearing"): "我的紀錄",
            reverse("audiogram_list"): "聽力圖",
            reverse("audiogram_new"): "聽力圖",
        }

    def test_logged_in_nav_and_header(self):
        self.client.force_login(self.user)
        for url in self._logged_in_pages():
            with self.subTest(url=url):
                response = self.client.get(url)
                nav = self._nav(response)
                self.assertEqual(self._nav_labels(nav), list(self.LOGGED_IN_ITEMS))
                content = response.content.decode()
                self.assertRegex(content, r"目前登入：\s*<strong>alice_account</strong>")
                self.assertRegex(
                    content,
                    rf'<form[^>]*action="{reverse("logout")}"[^>]*method="post"',
                )

    def test_logged_out_nav(self):
        for url in (reverse("index"), reverse("login"), reverse("register")):
            with self.subTest(url=url):
                response = self.client.get(url)
                nav = self._nav(response)
                self.assertEqual(self._nav_labels(nav), list(self.LOGGED_OUT_ITEMS))
                content = response.content.decode()
                self.assertNotIn("目前登入", content)
                self.assertNotIn(f'action="{reverse("logout")}"', content)

    def test_current_page_marked(self):
        self.client.force_login(self.user)
        for url, label in self._logged_in_pages().items():
            with self.subTest(url=url):
                nav = self._nav(self.client.get(url))
                self.assertEqual(nav.count('aria-current="page"'), 1)
                self.assertRegex(nav, rf'(?s)aria-current="page"[^>]*>.*?<span[^>]*>{label}</span>')
        self.client.logout()
        for name, label in (("login", "登入"), ("register", "註冊")):
            with self.subTest(url=name):
                nav = self._nav(self.client.get(reverse(name)))
                self.assertEqual(nav.count('aria-current="page"'), 1)
                self.assertRegex(nav, rf'(?s)aria-current="page"[^>]*>.*?<span[^>]*>{label}</span>')

    def test_index_shows_start_screening_when_logged_in(self):
        self.client.force_login(self.user)
        nav = self._nav(self.client.get(reverse("index")))
        self.assertIn(f'href="{reverse("questionnaire_list")}"', nav)

    def test_page_titles(self):
        suffix = "\uff5cHearWell"  # U+FF5C FULLWIDTH VERTICAL LINE, as written in the spec
        expected = {
            reverse("questionnaire_list"): "選擇問卷" + suffix,
            reverse("screening", args=[self.questionnaire.id]): "HHIE-S 作答" + suffix,
            reverse("result", args=[self.submission.id]): "篩檢結果" + suffix,
            reverse("my_hearing"): "我的紀錄" + suffix,
        }
        self.client.force_login(self.user)
        titles = {url: self._title(url) for url in expected}
        self.client.logout()
        expected.update(
            {
                reverse("index"): "HearWell 聽力自我照護",
                reverse("login"): "登入" + suffix,
                reverse("register"): "註冊" + suffix,
            }
        )
        for name in ("index", "login", "register"):
            titles[reverse(name)] = self._title(reverse(name))
        self.assertEqual(titles, expected)
        self.assertEqual(len(set(titles.values())), len(titles))

    def _title(self, url):
        match = re.search(r"<title>\s*(.*?)\s*</title>", self.client.get(url).content.decode())
        return match.group(1)

    def test_login_uses_plain_labels(self):
        content = self.client.get(reverse("login")).content.decode()
        self.assertNotIn("form-floating", content)
        self.assertRegex(content, r'<label[^>]*for="id_username"[^>]*>使用者名稱</label>')
        self.assertRegex(content, r'<label[^>]*for="id_password"[^>]*>密碼</label>')
        self.assertRegex(content, r'<input[^>]*id="id_username"')
        self.assertRegex(content, r'<input[^>]*id="id_password"')
        response = self.client.post(
            reverse("login"), {"username": "alice_account", "password": "wrong"}
        )
        self.assertContains(response, "使用者名稱或密碼錯誤")

    def _answer_data(self, skip=(), wearing="True"):
        data = {"form-TOTAL_FORMS": 10, "form-INITIAL_FORMS": 0}
        if wearing is not None:
            data["wearing_hearing_aid"] = wearing
        for i, question in enumerate(self.questions):
            data[f"form-{i}-question_id"] = str(question.id)
            if question.question_number not in skip:
                data[f"form-{i}-score"] = "4"
        return data

    def test_unanswered_questions_are_pointed_out(self):
        self.client.force_login(self.user)
        url = reverse("screening", args=[self.questionnaire.id])
        content = self.client.post(url, self._answer_data(skip=(3, 7))).content.decode()
        self.assertIn("還有 2 題沒有回答，請看標示紅字的題目。", content)
        self.assertEqual(content.count("這一題還沒有回答"), 2)
        for index in (2, 6):  # question 3 and 7
            with self.subTest(question=index + 1):
                self.assertRegex(
                    content, rf'<fieldset[^>]*aria-describedby="id_form-{index}-score_error"'
                )
                self.assertRegex(
                    content, rf'id="id_form-{index}-score_error">\s*<p[^>]*>這一題還沒有回答'
                )
        self.assertEqual(content.count('aria-describedby="id_form-'), 2)
        # Answers already chosen stay selected.
        self.assertRegex(content, r'<input[^>]*name="form-0-score"[^>]*value="4"[^>]*checked')
        self.assertNotIn("表單資料有誤", content)

    def test_invalid_choice_is_not_counted_as_unanswered(self):
        self.client.force_login(self.user)
        url = reverse("screening", args=[self.questionnaire.id])
        data = self._answer_data()
        data["form-0-score"] = "9"
        content = self.client.post(url, data).content.decode()
        self.assertNotIn("沒有回答", content)
        self.assertIn("表單資料有誤", content)

    def test_unanswered_count_matches_marked_questions(self):
        # Tampered form counts: extra forms are not on the page, so they must not be counted.
        self.client.force_login(self.user)
        url = reverse("screening", args=[self.questionnaire.id])
        data = self._answer_data()
        data["form-TOTAL_FORMS"] = data["form-INITIAL_FORMS"] = 12
        content = self.client.post(url, data).content.decode()
        self.assertNotIn("沒有回答", content)

    def test_logout_form_has_csrf_token(self):
        # The test client skips CSRF checks, so a missing token would only fail in production.
        self.client.force_login(self.user)
        content = self.client.get(reverse("index")).content.decode()
        form = re.search(rf'<form[^>]*action="{reverse("logout")}".*?</form>', content, re.DOTALL)
        self.assertIn('name="csrfmiddlewaretoken"', form.group(0))

    def test_only_hearing_aid_missing_behaves_as_before(self):
        self.client.force_login(self.user)
        url = reverse("screening", args=[self.questionnaire.id])
        content = self.client.post(url, self._answer_data(wearing=None)).content.decode()
        # Spec phase6_a11y_remeasure.md acceptance 9: the summary now lists this question too.
        self.assertIn("還有 1 題沒有回答", content)
        self.assertIn('href="#question-hearing-aid">是否戴助聽器</a>', content)
        self.assertRegex(content, r'<fieldset[^>]*aria-describedby="id_wearing_hearing_aid_error"')

    def test_only_expected_scripts(self):
        # No additional scripts: only the bundles each page needs.
        def scripts(url):
            content = self.client.get(url).content.decode()
            inline = re.findall(r"<script(?![^>]*src=)", content)
            return re.findall(r'<script[^>]*src="/static/([^"]+)"', content) + ["<inline>"] * len(
                inline
            )

        logout_js, answer_js = (
            test_answering.ReactAnswerPageTests.LOGOUT_JS,
            test_answering.ReactAnswerPageTests.ANSWER_JS,
        )
        # Every page: back button and pull to refresh in the home-screen app
        # (spec phase10_pwa_back_refresh.md), and the header wave's inline check (#138).
        pwa_js = PwaNavTests.SCRIPT.removeprefix("/static/")
        wave = "<inline>"
        empty_user = consented_user(username="no_records")
        for url in (reverse("index"), reverse("login")):
            with self.subTest(url=url):
                self.assertEqual(scripts(url), [pwa_js, wave])
        # The 顯示 button on the password fields (#151).
        with self.subTest(url="register"):
            self.assertEqual(
                scripts(reverse("register")), [pwa_js, "screening/password-toggle.js", wave]
            )
        self.client.force_login(empty_user)
        with self.subTest(url="my_hearing without records"):
            self.assertEqual(scripts(reverse("my_hearing")), [pwa_js, logout_js, wave])
        self.client.force_login(self.user)
        expected = {
            reverse("index"): [pwa_js, logout_js, wave],
            reverse("questionnaire_list"): [pwa_js, logout_js, wave],
            # The inline one hides the form before it is drawn (spec phase5_answer_flash.md).
            # submit-button.js: "送出中…" on the web form (spec phase6_web_double_submit.md).
            reverse("screening", args=[self.questionnaire.id]): [
                pwa_js,
                logout_js,
                answer_js,
                "screening/submit-button.js",
                wave,
                "<inline>",
            ],
            reverse("result", args=[self.submission.id]): [pwa_js, logout_js, wave],
            reverse("my_hearing"): [
                pwa_js,
                logout_js,
                test_history.TrendChartPageTests.CHART_JS,
                wave,
            ],
        }
        for url, bundles in expected.items():
            with self.subTest(url=url):
                self.assertEqual(scripts(url), bundles)


class PageFlowTests(TestCase):
    """Spec docs/specs/phase-04/phase4_ui_flow.md, acceptance 1-14a."""

    # Spec #148 (ticket #150): a login button replaced the small hint for people not signed in.
    HINT = "我已經有帳號，登入"
    # As changed by phase9_ui_refresh_3_structure.md 4.4, phase9_ui_refresh_4a_home.md 4.1
    # and spec #148 (ticket #150, the account step).
    HOME_ORDER = (
        'class="home-illustration"',
        "了解聽力對您生活的影響",
        "聽力變化很慢，自己常常沒發現。花 3 分鐘看看聽力對生活的影響。",
        "開始篩檢",
        "建立帳號，大約 1 分鐘。",
        "回答問題，大約 3 分鐘。",
        "馬上看到結果分級和建議。",
        "隔一段時間再做一次，在「我的紀錄」看分數的變化。",
        "結果長這樣",
        "示意圖",
        "內容由台灣執業聽力師設計與審定。",
    )

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="flowtester")
        cls.other = consented_user(username="someoneelse")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhie_s,
                question_text=f"題目內容{i:02d}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.short = Questionnaire.objects.create(questionnaire_name="短問卷", code="short")
        Question.objects.bulk_create(
            Question(
                questionnaire=cls.short,
                question_text=f"短題{i}",
                question_number=i,
                category=Category.SOCIAL,
            )
            for i in range(1, 4)
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _main(self, response):
        # Only the page body; the header and nav repeat some words (e.g. 開始篩檢, the username).
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _assert_in_order(self, content, parts):
        positions = [content.index(part) for part in parts]
        self.assertEqual(positions, sorted(positions), parts)

    def _submit(self, scores, questionnaire=None, user=None):
        submission = Submission.objects.create(
            user=user or self.user, questionnaire=questionnaire or self.hhie_s
        )
        # Reversed so a missing order_by on the result page shows up.
        for question, score in reversed(list(zip(self.questions, scores, strict=False))):
            Answer.objects.create(submission=submission, question=question, score=score)
        return submission

    # Home (1-3)
    def test_home_order_for_anonymous(self):
        self.client.logout()
        main = self._main(self.client.get(reverse("index")))
        self._assert_in_order(main, self.HOME_ORDER)
        self._assert_in_order(main, ("開始篩檢", self.HINT, "建立帳號，大約 1 分鐘。"))
        self.assertNotIn("7–10 年", main)
        # Spec #148 (ticket #150): straight to registering, then back to choosing a questionnaire.
        start = f"{reverse('register')}?next={reverse('questionnaire_list')}"
        self.assertRegex(main, rf'<a[^>]*href="{re.escape(start)}"[^>]*>\s*開始篩檢')

    def test_home_order_for_logged_in_without_hint(self):
        main = self._main(self.client.get(reverse("index")))
        self._assert_in_order(main, self.HOME_ORDER)
        self.assertNotIn(self.HINT, main)

    def test_home_has_no_missing_features(self):
        # HHIE-S is allowed since phase9_ui_refresh_4a_home.md (result preview, trust block).
        for logged_in in (True, False):
            if not logged_in:
                self.client.logout()
            content = self.client.get(reverse("index")).content.decode()
            for text in ("HHIA-S", "記錄日常聆聽困難", "以白話理解"):
                with self.subTest(logged_in=logged_in, text=text):
                    self.assertNotIn(text, content)

    # Questionnaire list (4-5)
    def test_questionnaire_list_shows_info(self):
        main = self._main(self.client.get(reverse("questionnaire_list") + "?choose=self"))
        self._assert_in_order(
            main,
            (
                "自行選擇問卷",
                "聽力對生活的影響（HHIE-S）",
                "適合 65 歲以上的長輩。",
                # Tags since phase9_ui_refresh_4b_questionnaire_cards.md 4.1.
                '<span class="card-tag">10 題</span>',
                '<span class="card-tag">約 3 分鐘</span>',
            ),
        )
        self.assertRegex(
            main,
            rf'<a[^>]*href="{reverse("screening", args=[self.hhie_s.id])}"[^>]*>'
            r"(\s*<[^>]+>)*\s*聽力對生活的影響（HHIE-S）",
        )

    def test_question_count_is_not_hard_coded(self):
        with register(fake_definition("short")):
            main = self._main(self.client.get(reverse("questionnaire_list") + "?choose=self"))
            page = self._main(self.client.get(reverse("screening", args=[self.short.id])))
        start = main.index("短問卷")
        card = main[start : main.index("</a>", start)]
        self.assertIn('<span class="card-tag">3 題</span>', card)
        self.assertIn("共 3 題，", page)
        self.assertRegex(page, r"<legend[^>]*>(\s*<[^>]+>)*\s*第 3 題／共 3 題")

    # Answer page (6-7)
    def _assert_progress(self, page):
        self.assertIn("共 10 題，大約 3 分鐘。", page)
        for n in (1, 10):
            with self.subTest(question=n):
                self.assertRegex(page, rf"<legend[^>]*>(\s*<[^>]+>)*\s*第 {n} 題／共 10 題")

    def test_answer_page_shows_progress(self):
        response = self.client.get(reverse("screening", args=[self.hhie_s.id]))
        self._assert_progress(self._main(response))

    def test_answer_page_does_not_count_questions_again(self):
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("screening", args=[self.hhie_s.id]))
        self.assertFalse([q for q in ctx.captured_queries if "COUNT(" in q["sql"]])

    def test_progress_kept_after_unanswered_post(self):
        data = {"form-TOTAL_FORMS": 10, "form-INITIAL_FORMS": 10, "wearing_hearing_aid": "True"}
        for i, question in enumerate(self.questions):
            data[f"form-{i}-question_id"] = str(question.id)
            if i != 2:
                data[f"form-{i}-score"] = "4"
        response = self.client.post(reverse("screening", args=[self.hhie_s.id]), data)
        page = self._main(response)
        self._assert_progress(page)
        self.assertIn("還有 1 題沒有回答，請看標示紅字的題目。", page)
        self.assertRegex(page, r'value="4"[^>]*checked')
        self.assertFalse(Submission.objects.exists())

    # Result page (8-13a)
    def _result(self, submission):
        return self._main(self.client.get(reverse("result", args=[submission.id])))

    def test_result_page_order(self):
        # Ticket #157 (ADR 0010): numbered next steps, then the full advice, then the
        # collapsed score detail, with the secondary buttons last.
        submission = self._submit([4, 4, 2, 2, 0, 0, 0, 0, 0, 0])  # 12
        day = timezone.localtime(submission.created_at).strftime("%Y/%m/%d")
        main = self._result(submission)
        steps = hhie_s.NEXT_STEPS["mild_to_moderate"]
        self._assert_in_order(
            main,
            (
                f"{day} 作答",
                "輕度到中度影響",
                "總分 12 分（滿分 40）",
                "接下來建議您",
                steps[0]["text"],
                steps[1]["text"],
                steps[2]["text"],
                "完整建議",
                get_advice("mild_to_moderate"),
                "<details",
                "分數細節與作答明細",
                "情緒分數：12",
                "社交分數：0",
                "助聽器：未記錄",
                "看我的紀錄與趨勢",
                "回首頁",
            ),
        )

    def test_result_next_step_links(self):
        main = self._result(self._submit([0] * 10))
        self.assertRegex(main, rf'<a[^>]*href="{reverse("my_hearing")}"[^>]*>\s*看我的紀錄與趨勢')
        self.assertRegex(main, rf'<a[^>]*href="{reverse("index")}"[^>]*>\s*回首頁')

    def test_result_has_no_username_or_halfwidth_colon(self):
        main = self._result(self._submit([2] * 10))
        self.assertNotIn("flowtester", main)
        self.assertNotRegex(main, r"(總分|情緒分數|社交分數|助聽器|建議|結果)\s*:")

    def test_result_answers_collapsed_in_question_order(self):
        main = self._result(self._submit([4, 2, 0, 4, 2, 0, 4, 2, 0, 4]))
        details = re.search(r"<details(\s[^>]*)?>(.*?)</details>", main, re.DOTALL)
        self.assertIsNotNone(details)
        self.assertNotIn("open", details.group(1) or "")
        body = details.group(2)
        self.assertRegex(body, r"<summary[^>]*>\s*分數細節與作答明細\s*</summary>")
        self._assert_in_order(body, [f"題目內容{i:02d}" for i in range(1, 11)])
        for i, answer in ((1, "常常"), (2, "有時"), (3, "從未"), (10, "常常")):
            with self.subTest(question=i):
                self.assertIn(f"題目內容{i:02d}——{answer}", body)

    def test_result_banner_marks_its_level(self):
        # The colours themselves are measured in a browser: e2e StyleInBrowserTest.
        unknown = Questionnaire.objects.create(questionnaire_name="Unknown", code="unconfigured")
        self.enterContext(register(fake_definition("unconfigured")))
        cases = (
            ("normal", [0] * 10, self.hhie_s),
            ("mild_to_moderate", [2] * 6 + [0] * 4, self.hhie_s),
            ("severe", [4] * 10, self.hhie_s),
            ("unknown", [2] * 10, unknown),
        )
        for level, scores, questionnaire in cases:
            with self.subTest(level=level):
                submission = self._submit(scores, questionnaire=questionnaire)
                if level == "unknown":
                    with self.assertLogs("screening.scoring", "ERROR"):
                        main = self._result(submission)
                else:
                    main = self._result(submission)
                self.assertRegex(main, rf'class="[^"]*\bresult-banner-{level}\b')

    def test_result_zero_score(self):
        main = self._result(self._submit([0] * 10))
        self.assertIn("總分 0 分（滿分 40）", main)
        self.assertIn("無/極輕微影響", main)

    def test_result_without_thresholds_has_no_max(self):
        unknown = Questionnaire.objects.create(questionnaire_name="Unknown", code="unconfigured")
        self.enterContext(register(fake_definition("unconfigured")))
        submission = self._submit([2] * 10, questionnaire=unknown)
        with self.assertLogs("screening.scoring", "ERROR"):
            main = self._result(submission)
        self.assertIn("總分 20 分", main)
        self.assertNotIn("滿分", main)

    # IDOR (14) is covered by SubmissionResultAccessTests; one more for the redesigned page.
    def test_result_of_other_user_is_404(self):
        submission = self._submit([0] * 10, user=self.other)
        response = self.client.get(reverse("result", args=[submission.id]))
        self.assertEqual(response.status_code, 404)

    # History page (14a)
    def test_history_uses_fullwidth_colon(self):
        self._submit([2] * 10)
        content = self.client.get(reverse("my_hearing")).content.decode()
        self.assertIn("總分：20", content)
        self.assertNotIn("總分:", content)


class PwaTests(TestCase):
    """Spec docs/specs/phase-04/phase4.md batch 2, acceptance 18-23."""

    PWA_DIR = Path(__file__).resolve().parent.parent / "static" / "screening" / "pwa"
    STATIC = "/static/screening/pwa/"
    GUIDE_ORDER = (
        "把 HearWell 加到手機主畫面",
        "加到主畫面後，HearWell 會像其他 app 一樣出現在手機桌面上，"
        "點一下就能打開，不用每次輸入網址。",
        "iPhone（Safari）",
        "用 Safari 打開 HearWell 網站。",
        "點畫面下方的「分享」按鈕（一個方框，上面有向上的箭頭）。如果沒看到，先點「⋯」再點「分享」。",
        "往下滑，點「加入主畫面」。",
        "點右上角的「加入」。",
        "第一次從主畫面打開時，需要再登入一次。",
        "Android 手機（Chrome）",
        "用 Chrome 打開 HearWell 網站。",
        "點右上角的「⋮」（三個點）。",
        "點「加到主畫面」或「安裝應用程式」。",
        "再點一次「安裝」或「新增」。",
        "從主畫面打開時，請用畫面下方的「首頁、開始篩檢、我的紀錄」切換頁面。",
    )

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="pwatester")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        question = Question.objects.create(
            questionnaire=cls.questionnaire,
            question_text="第一題",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        cls.submission = Submission.objects.create(user=cls.user, questionnaire=cls.questionnaire)
        Answer.objects.create(submission=cls.submission, question=question, score=2)

    def _head(self, response):
        content = response.content.decode()
        return content[content.index("<head>") : content.index("</head>")]

    def _png_size(self, path):
        data = path.read_bytes()[:24]
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", path)
        return struct.unpack(">II", data[16:24])

    def _manifest(self):
        return json.loads((self.PWA_DIR / "manifest.json").read_text(encoding="utf-8"))

    # 18
    def test_every_page_links_app_info(self):
        self.client.force_login(self.user)
        urls = [
            reverse("index"),
            reverse("questionnaire_list"),
            reverse("screening", args=[self.questionnaire.id]),
            reverse("result", args=[self.submission.id]),
            reverse("my_hearing"),
            reverse("add_to_home"),
        ]
        heads = {url: self._head(self.client.get(url)) for url in urls}
        self.client.logout()
        for name in ("login", "register"):
            heads[reverse(name)] = self._head(self.client.get(reverse(name)))
        for url, head in heads.items():
            with self.subTest(url=url):
                self.assertRegex(head, rf'<link rel="manifest" href="{self.STATIC}manifest\.json')
                # The header turned white, so the phone's status bar matches it (#138's rule).
                self.assertIn('<meta name="theme-color" content="#ffffff">', head)
                # Browser tab icon: SVG where supported, a 32px PNG for the rest.
                self.assertRegex(
                    head, rf'<link rel="icon" href="{self.STATIC}favicon-32\.png" sizes="32x32">'
                )
                self.assertRegex(
                    head,
                    rf'<link rel="icon" href="{self.STATIC}favicon\.svg" type="image/svg\+xml">',
                )
                self.assertRegex(
                    head, rf'<link rel="apple-touch-icon" href="{self.STATIC}apple-touch-icon\.png'
                )
                self.assertIn('<meta name="apple-mobile-web-app-title" content="HearWell">', head)

    # 19
    def test_manifest_fields(self):
        manifest = self._manifest()
        expected = {
            "name": "HearWell 聽力自我照護",
            "short_name": "HearWell",
            "id": "/",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "theme_color": "#ffffff",
            "background_color": "#faf7f2",
            "lang": "zh-Hant",
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(manifest.get(key), value)

    def test_manifest_icons_exist_with_right_size(self):
        icons = {
            (icon["sizes"], icon.get("purpose", "any")): icon for icon in self._manifest()["icons"]
        }
        self.assertEqual(
            set(icons), {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")}
        )
        for (sizes, purpose), icon in icons.items():
            with self.subTest(sizes=sizes, purpose=purpose):
                self.assertEqual(icon["type"], "image/png")
                path = self.PWA_DIR / icon["src"]
                self.assertTrue(path.is_file(), path)
                width, height = self._png_size(path)
                self.assertEqual(f"{width}x{height}", sizes)

    # 20
    def test_apple_touch_icon_is_180(self):
        self.assertEqual(self._png_size(self.PWA_DIR / "apple-touch-icon.png"), (180, 180))

    def test_favicon_png_is_32(self):
        self.assertEqual(self._png_size(self.PWA_DIR / "favicon-32.png"), (32, 32))

    def test_favicon_app_icon_and_header_draw_the_same_wave_w(self):
        # ADR 0012: the logo lives in three files; changing one alone fails here.
        wave = "M8 20c2 14 5 22 10 22 6 0 8-12 14-12s8 12 14 12c5 0 8-8 10-22"
        css = Path(__file__).resolve().parents[2] / "frontend" / "src" / "site.css"
        for path in (self.PWA_DIR / "favicon.svg", self.PWA_DIR / "icon.svg", css):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn(wave, text)
                if path.suffix == ".svg":
                    self.assertIn('<stop offset="0" stop-color="#1f4e8c"/>', text)
                    self.assertIn('<stop offset="1" stop-color="#1d6f99"/>', text)

    # 21
    def test_pwa_folder_has_only_app_info_and_icons(self):
        # Allow-list: a service worker added here under any name fails this test.
        names = {path.name for path in self.PWA_DIR.iterdir()}
        expected = {
            "manifest.json",
            "icon.svg",
            "favicon.svg",
            "favicon-32.png",
            "icon-192.png",
            "icon-512.png",
            "apple-touch-icon.png",
        }
        self.assertEqual(names, expected)
        self.assertNotIn("serviceworker", self._manifest())

    def test_no_service_worker_registration(self):
        root = Path(__file__).resolve().parent.parent.parent
        app = root / "screening"
        sources = [
            *(app / "templates").rglob("*.html"),
            # This file names "serviceWorker" itself; migrations are generated.
            *(
                p
                for p in app.rglob("*.py")
                if "migrations" not in p.parts and p != Path(__file__).resolve()
            ),
            *(root / "config").rglob("*.py"),
            *(root / "frontend" / "src").rglob("*.js*"),
            # The trend chart bundle is a build output (React), not our code.
            *(p for p in (app / "static").rglob("*") if p.is_file() and "trend" not in p.parts),
        ]
        for path in sources:
            if path.suffix in (".html", ".py", ".js", ".jsx", ".json", ".css", ".svg"):
                with self.subTest(path=str(path.relative_to(root))):
                    self.assertNotIn("serviceWorker", path.read_text(encoding="utf-8"))

    # 22
    def test_guide_page_for_anonymous_and_logged_in(self):
        for logged_in in (False, True):
            if logged_in:
                self.client.force_login(self.user)
            with self.subTest(logged_in=logged_in):
                response = self.client.get(reverse("add_to_home"))
                self.assertEqual(response.status_code, 200)
                content = response.content.decode()
                # U+FF5C FULLWIDTH VERTICAL LINE, as in the other page titles
                self.assertIn("<title>加到主畫面\uff5cHearWell</title>", content)
                self.assertNotIn('aria-current="page"', content)
                main = content[content.index("<main") : content.index("</main>")]
                positions = [main.index(part) for part in self.GUIDE_ORDER]
                self.assertEqual(positions, sorted(positions))
                steps = [ol.count("<li>") for ol in re.findall(r"<ol>(.*?)</ol>", main, re.DOTALL)]
                self.assertEqual(steps, [4, 4])

    # 23, as changed by phase9_ui_refresh_1_shared.md acceptance 5: the link moved to the footer
    def test_home_links_to_guide_in_footer(self):
        content = self.client.get(reverse("index")).content.decode()
        footer = content.split('<footer class="site-footer"', 1)[1]
        link = re.search(
            rf'<a[^>]*href="{reverse("add_to_home")}"[^>]*>\s*把 HearWell 加到手機主畫面', footer
        )
        self.assertIsNotNone(link)


class PwaNavTests(TestCase):
    """Spec docs/specs/phase-10/phase10_pwa_back_refresh.md.

    Acceptance 3, 10 and 11 (rest: Vitest, e2e)."""

    BACK = re.compile(r'<button([^>]*id="pwa-back"[^>]*)>(.*?)</button>', re.DOTALL)
    SCRIPT = "/static/screening/frontend/pwa-nav.js"

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="pwanavtester")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        question = Question.objects.create(
            questionnaire=cls.questionnaire,
            question_text="第一題",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        cls.submission = Submission.objects.create(user=cls.user, questionnaire=cls.questionnaire)
        Answer.objects.create(submission=cls.submission, question=question, score=2)
        cls.audiogram = Audiogram.objects.create(user=cls.user, tested_on=date(2026, 1, 1))
        Audiogram.objects.create(user=cls.user, tested_on=date(2026, 6, 1))

    def _pages(self):
        """Every kind of page once: (logged in, url)."""
        return [
            (False, reverse("login")),
            (False, reverse("register")),
            (False, reverse("add_to_home")),
            (True, reverse("questionnaire_list")),
            (True, reverse("screening", args=[self.questionnaire.id])),
            (True, reverse("result", args=[self.submission.id])),
            (True, reverse("my_hearing")),
            (True, reverse("audiogram_list")),
        ]

    def _get(self, logged_in, url):
        if logged_in:
            self.client.force_login(self.user)
        else:
            self.client.logout()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _assert_site_stylesheets(self, content):
        stylesheets = re.findall(
            r'<link\b(?=[^>]*\brel="stylesheet")[^>]*\bhref="([^"]+)"', content
        )
        self.assertEqual(
            stylesheets,
            [
                "/static/screening/frontend/site.css",
                "https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;600;700&display=swap",
            ],
        )

    def test_pages_load_built_css_with_only_site_and_font_stylesheets(self):
        share = ReportShare.objects.create(user=self.user, token="css-test-share")
        pages = [
            (False, reverse("index")),
            (True, reverse("index")),
            *self._pages(),
            (True, reverse("hhi_comparison", args=[self.questionnaire.id])),
            (False, reverse("shared_cover", args=[share.token])),
            (False, reverse("shared_report", args=[share.token])),
            *(
                (True, reverse(name))
                for name in (
                    "family_guide",
                    "privacy",
                    "account_settings",
                    "delete_account",
                    "health_report",
                    "audiogram_new",
                    "audiogram_compare",
                )
            ),
            *(
                (True, reverse(name, args=[self.audiogram.id]))
                for name in (
                    "audiogram_detail",
                    "audiogram_edit",
                    "audiogram_delete",
                )
            ),
        ]
        for logged_in, url in pages:
            with self.subTest(logged_in=logged_in, url=url):
                content = self._get(logged_in, url)
                self.assertIn(
                    '<link href="/static/screening/frontend/site.css" rel="stylesheet">', content
                )
                self._assert_site_stylesheets(content)
                self.assertNotIn("screening/styles.css", content)

    # #126: the old custom stylesheet's rules now live in the built site.css.
    def test_old_stylesheet_is_deleted(self):
        self.assertIsNone(finders.find("screening/styles.css"))

    def test_invalid_share_loads_built_css_with_only_site_and_font_stylesheets(self):
        response = self.client.get(reverse("shared_cover", args=["css-missing-share"]))
        self.assertContains(response, "/static/screening/frontend/site.css", status_code=404)
        self._assert_site_stylesheets(response.content.decode())

    def test_consent_page_loads_built_css_with_only_site_and_font_stylesheets(self):
        self.client.force_login(User.objects.create_user(username="css_undecided"))
        response = self.client.get(reverse("consent"))
        self.assertContains(response, "/static/screening/frontend/site.css")
        self._assert_site_stylesheets(response.content.decode())

    # 3
    def test_home_has_no_back_button(self):
        for logged_in in (False, True):
            with self.subTest(logged_in=logged_in):
                self.assertNotIn('id="pwa-back"', self._get(logged_in, reverse("index")))

    # 10, 11: hidden until the script finds the home-screen app; the visible text is its name.
    def test_other_pages_have_a_hidden_back_button(self):
        for logged_in, url in self._pages():
            with self.subTest(url=url):
                content = self._get(logged_in, url)
                header = content[content.index("<header") : content.index("</header>")]
                attrs, inner = self.BACK.search(header).groups()
                self.assertIn('type="button"', attrs)
                self.assertRegex(attrs, r"\shidden(\s|$)")
                self.assertNotIn("aria-label", attrs)
                spoken = re.sub(r'<span aria-hidden="true">.*?</span>', "", inner)
                self.assertEqual(spoken.strip(), "上一頁")

    # 9, 9b: pwa-nav.js turns pull to refresh off when <main> has any of these.
    INPUTS = re.compile(r"<(form|input|select|textarea)[\s>]")

    def _main(self, logged_in, url):
        content = self._get(logged_in, url)
        return content[content.index("<main") : content.index("</main>")]

    # 9
    def test_pages_with_forms_have_inputs_in_main(self):
        pages = [
            (True, reverse("screening", args=[self.questionnaire.id])),
            (False, reverse("login")),
            (False, reverse("register")),
            (True, reverse("health_report")),  # the share form
            (True, reverse("audiogram_compare")),
            (True, reverse("audiogram_delete", args=[self.audiogram.id])),
            (True, reverse("delete_account")),
        ]
        for logged_in, url in pages:
            with self.subTest(url=url):
                self.assertRegex(self._main(logged_in, url), self.INPUTS)

    # 9: only a user who has not agreed yet sees the consent page.
    def test_consent_page_has_inputs_in_main(self):
        self.client.force_login(User.objects.create_user(username="pwa_undecided"))
        content = self.client.get(reverse("consent")).content.decode()
        main = content[content.index("<main") : content.index("</main>")]
        self.assertRegex(main, self.INPUTS)

    # 9: React draws the audiogram input's selects and checkboxes inside <main>.
    def test_audiogram_input_draws_inside_main(self):
        self.assertIn('id="audiogram-app"', self._main(True, reverse("audiogram_new")))

    # 9b: the log-out form sits in the header, outside <main>.
    def test_my_hearing_has_no_inputs_in_main(self):
        content = self._get(True, reverse("my_hearing"))
        self.assertIn('id="logout-form"', content)
        main = content[content.index("<main") : content.index("</main>")]
        self.assertNotRegex(main, self.INPUTS)

    # 10
    def test_every_page_loads_the_script_and_a_hidden_pull_hint(self):
        for logged_in, url in [(False, reverse("index")), *self._pages()]:
            with self.subTest(url=url):
                content = self._get(logged_in, url)
                self.assertIn(f'<script type="module" src="{self.SCRIPT}"></script>', content)
                self.assertRegex(content, r'<div id="pwa-pull"[^>]*\shidden[\s>]')
                self.assertRegex(content, r'<div id="pwa-pull"[^>]*aria-hidden="true"')


class HomeTests(TestCase):
    """Spec docs/specs/phase-09/phase9_ui_refresh_4a_home.md, acceptance 1-7."""

    # Spec #148 (ticket #150) adds the account step in front.
    STEPS = (
        "建立帳號，大約 1 分鐘。",
        "回答問題，大約 3 分鐘。",
        "馬上看到結果分級和建議。",
        "隔一段時間再做一次，在「我的紀錄」看分數的變化。",
    )

    def _main(self):
        content = self.client.get(reverse("index")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _between(self, content, start, end):
        begin = content.index(start)
        return content[begin : content.index(end, begin)]

    # 1
    def test_illustration_first_and_hidden(self):
        for logged_in in (False, True):
            if logged_in:
                self.client.force_login(consented_user(username="hometester"))
            with self.subTest(logged_in=logged_in):
                main = self._main()
                self.assertRegex(main, r'<svg[^>]*class="home-illustration"[^>]*aria-hidden="true"')
                self.assertLess(main.index("home-illustration"), main.index("<h1"))

    # 3
    def test_step_cards(self):
        steps = self._between(self._main(), "step-cards", "</ol>")
        cards = re.findall(r"<li[^>]*>(.*?)</li>", steps, re.S)
        self.assertEqual(len(cards), 4)
        for number, (card, text) in enumerate(zip(cards, self.STEPS, strict=True), start=1):
            with self.subTest(step=number):
                self.assertRegex(card, rf'class="step-number"[^>]*>{number}<')
                self.assertRegex(card, r'class="step-icon"[^>]*aria-hidden="true"')
                self.assertIn(text, card)

    # 4
    def test_result_preview_uses_real_scoring(self):
        preview = self._between(self._main(), "result-preview", "</figure>")
        classified = classify(18, "hhie-s")
        self.assertIn("示意圖", preview)
        self.assertIn("實際結果依您的回答而定。", preview)
        self.assertIn(f"result-banner-{classified['level']}", preview)
        self.assertIn(classified["text"], preview)
        self.assertIn("HHIE-S 總分 18 分（滿分 40）", preview)
        self.assertIn(get_advice(classified["level"])[:40] + "……", preview)

    # 5: superseded by ADR 0010 / ticket #159 (screening.tests.test_home.ReturningUserHomeTests).
    # A returning user's home page now shows their own last result on purpose.

    # 6, changed in the brand refresh (design picker round 3): the "由聽力師開發" block repeated
    # the top's 國際標準量表 label, so it became one line in a badge card.
    def test_trust_block(self):
        main = self._main()
        line = self._between(main, 'class="home-credential"', "</p>")
        self.assertIn('<span class="home-credential-icon"><svg', line)
        self.assertIn('aria-hidden="true"', line)
        self.assertIn("內容由台灣執業聽力師設計與審定。", line)
        self.assertEqual(main.count("內容由台灣執業聽力師設計與審定。"), 1)
        gone_texts = (
            "由聽力師開發",
            "HHIE-S、IOI-HA",
            "出處都列在說明頁",
            "本網站由執業聽力師開發",
            # Dropped in round 3: it repeated the top's 聽力變化很慢 line.
            "很多人在察覺聽力問題好幾年後",
        )
        for gone in gone_texts:
            with self.subTest(gone=gone):
                self.assertNotIn(gone, main)

    # 7
    def test_band_backgrounds(self):
        main = self._main()
        bands = re.findall(r'<section class="home-band[^"]*">(.*?)</section>', main, re.S)
        # The trust band became the one-line badge card (brand refresh), so one band is left.
        self.assertEqual(len(bands), 1)
        self.assertIn("home-illustration", bands[0])
        for band in bands:
            self.assertNotIn("step-cards", band)
            self.assertNotIn("result-preview", band)
