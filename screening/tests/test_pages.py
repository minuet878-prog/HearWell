import json
import re
import struct
from pathlib import Path
from typing import ClassVar

from django.contrib.staticfiles import finders
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Category, Question, Questionnaire, Submission, User
from screening.scoring import get_advice
from screening.tests import test_answering, test_history


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
        cls.user = User.objects.create_user(username="tester")
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
        self.assertContains(response, '<h1 class="h3 mb-3 fw-normal">登入</h1>', html=True)
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
        self.assertContains(
            response,
            f'<a class="btn btn-primary align-self-md-center" href="{result_url}">查看結果</a>',
            html=True,
        )
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
        cls.user = User.objects.create_user(username="tester")
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

    def _css(self):
        with open(finders.find("screening/styles.css"), encoding="utf-8") as f:
            return re.sub(r"/\*.*?\*/", "", f.read(), flags=re.DOTALL)

    def _rule(self, selector):
        # Exactly one rule for the selector, so a later rule cannot silently override it.
        bodies = [
            body
            for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", self._css())
            if selectors.strip() == selector
        ]
        self.assertEqual(len(bodies), 1, selector)
        return bodies[0].lower()

    def test_stylesheet_loads_after_bootstrap(self):
        content = self.client.get(reverse("index")).content.decode()
        self.assertLess(content.index("bootstrap.min.css"), content.index("screening/styles"))

    def test_body_and_muted_text_color(self):
        root = self._rule(":root")
        self.assertIn("--bs-body-color: #495057", root)
        self.assertIn("--bs-body-color-rgb: 73, 80, 87", root)
        self.assertIn("--bs-secondary-color: #495057", root)

    def test_level_and_error_text_colors(self):
        expected = {
            ".text-success": "#1e7b55",
            ".text-warning": "#8a5a00",
            ".text-danger": "#c23b1c",
            ".text-secondary": "#495057",
        }
        for selector, color in expected.items():
            with self.subTest(selector=selector):
                self.assertIn(f"color: {color} !important", self._rule(selector))

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
        self.assertIn("min-height: 3rem", self._rule("div.choice-group label"))
        # The input sits inside its label, so the whole button is clickable.
        self.assertRegex(response.content.decode(), r'<label for="id_form-0-score_0">\s*<input')
        self.assertIn("display: flex", self._rule("div.choice-group"))


class RedesignLayoutTests(TestCase):
    NAV = re.compile(r'<nav aria-label="主要導覽".*?</nav>', re.DOTALL)
    LOGGED_IN_ITEMS = ("首頁", "開始篩檢", "我的紀錄", "聽力圖")
    LOGGED_OUT_ITEMS = ("首頁", "登入", "註冊")

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alice_account", password="secret-pass-123")
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
        self.assertNotIn("沒有回答", content)
        self.assertRegex(content, r'<fieldset[^>]*aria-describedby="id_wearing_hearing_aid_error"')

    def test_only_expected_scripts(self):
        # No Bootstrap JS or anything else: only the bundles each page needs.
        def scripts(url):
            content = self.client.get(url).content.decode()
            return re.findall(r'<script[^>]*src="/static/([^"]+)"', content) + (
                ["<inline>"] if re.search(r"<script(?![^>]*src=)", content) else []
            )

        logout_js, answer_js = (
            test_answering.ReactAnswerPageTests.LOGOUT_JS,
            test_answering.ReactAnswerPageTests.ANSWER_JS,
        )
        empty_user = User.objects.create_user(username="no_records")
        for url in (reverse("index"), reverse("login"), reverse("register")):
            with self.subTest(url=url):
                self.assertEqual(scripts(url), [])
        self.client.force_login(empty_user)
        with self.subTest(url="my_hearing without records"):
            self.assertEqual(scripts(reverse("my_hearing")), [logout_js])
        self.client.force_login(self.user)
        expected = {
            reverse("index"): [logout_js],
            reverse("questionnaire_list"): [logout_js],
            # The inline one hides the form before it is drawn (spec phase5_answer_flash.md).
            # submit-button.js: "送出中…" on the web form (spec phase6_web_double_submit.md).
            reverse("screening", args=[self.questionnaire.id]): [
                logout_js,
                answer_js,
                "screening/submit-button.js",
                "<inline>",
            ],
            reverse("result", args=[self.submission.id]): [logout_js],
            reverse("my_hearing"): [logout_js, test_history.TrendChartPageTests.CHART_JS],
        }
        for url, bundles in expected.items():
            with self.subTest(url=url):
                self.assertEqual(scripts(url), bundles)


class PageFlowTests(TestCase):
    """Spec docs/specs/phase4_ui_flow.md, acceptance 1-14a."""

    HINT = "第一次使用請先註冊，已有帳號請直接登入。"
    HOME_ORDER = (
        "了解聽力對您生活的影響",
        "回答幾個日常生活情境的問題，大約 3 分鐘。",
        "開始篩檢",
        "回答問題，大約 3 分鐘。",
        "馬上看到結果分級和建議。",
        "隔一段時間再做一次，在「我的紀錄」看分數的變化。",
        "可達 10 年",
        "從察覺聽力問題到尋求協助，往往拖延多年。及早了解，才能及早處理。",
        "本網站由執業聽力師開發，使用經過驗證的標準化量表。"
        "結果僅供參考，不能取代聽力檢查與醫師診斷。",
    )

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="flowtester")
        cls.other = User.objects.create_user(username="someoneelse")
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
        self._assert_in_order(main, ("開始篩檢", self.HINT, "回答問題，大約 3 分鐘。"))
        self.assertNotIn("7–10 年", main)
        self.assertRegex(main, rf'<a[^>]*href="{reverse("questionnaire_list")}"[^>]*>\s*開始篩檢')

    def test_home_order_for_logged_in_without_hint(self):
        main = self._main(self.client.get(reverse("index")))
        self._assert_in_order(main, self.HOME_ORDER)
        self.assertNotIn(self.HINT, main)

    def test_home_has_no_scale_names_or_missing_features(self):
        for logged_in in (True, False):
            if not logged_in:
                self.client.logout()
            content = self.client.get(reverse("index")).content.decode()
            for text in ("HHIE-S", "HHIA-S", "記錄日常聆聽困難", "以白話理解"):
                with self.subTest(logged_in=logged_in, text=text):
                    self.assertNotIn(text, content)

    # Questionnaire list (4-5)
    def test_questionnaire_list_shows_info(self):
        main = self._main(self.client.get(reverse("questionnaire_list")))
        self._assert_in_order(
            main,
            (
                "請選擇問卷",
                "HHIE-S 聽力障礙自我評估",
                "適合 65 歲以上的長輩。",
                "共 10 題，大約 3 分鐘。",
            ),
        )
        self.assertRegex(
            main, rf'<a[^>]*href="{reverse("screening", args=[self.hhie_s.id])}"[^>]*>\s*HHIE-S'
        )

    def test_question_count_is_not_hard_coded(self):
        main = self._main(self.client.get(reverse("questionnaire_list")))
        start = main.index("短問卷")
        card = main[start : main.index("</p>", start)]
        self.assertIn("共 3 題。", card)
        self.assertNotIn("適合", card)
        self.assertNotIn("分鐘", card)
        page = self._main(self.client.get(reverse("screening", args=[self.short.id])))
        self.assertIn("共 3 題。", page)
        self.assertNotIn("分鐘", page)
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
        submission = self._submit([4, 4, 2, 2, 0, 0, 0, 0, 0, 0])  # 12
        day = timezone.localtime(submission.created_at).strftime("%Y/%m/%d")
        main = self._result(submission)
        self._assert_in_order(
            main,
            (
                f"{day} 作答",
                "輕度到中度影響",
                "總分 12 分（滿分 40）",
                "建議",
                get_advice("mild_to_moderate"),
                "看我的紀錄與趨勢",
                "回首頁",
                "分數細節",
                "情緒分數：12",
                "社交分數：0",
                "助聽器：未記錄",
                "<details",
                "查看我的 10 題作答",
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
        self.assertRegex(body, r"<summary[^>]*>\s*查看我的 10 題作答\s*</summary>")
        self._assert_in_order(body, [f"題目內容{i:02d}" for i in range(1, 11)])
        for i, answer in ((1, "常常"), (2, "有時"), (3, "從未"), (10, "常常")):
            with self.subTest(question=i):
                self.assertIn(f"題目內容{i:02d}——{answer}", body)

    def test_result_banner_colors(self):
        css = Path(finders.find("screening/styles.css")).read_text()
        hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")
        cases = (
            ("normal", [0] * 10, self.hhie_s, "#e3f4ec", "#1e7b55"),
            ("mild_to_moderate", [2] * 6 + [0] * 4, self.hhie_s, "#fff4d6", "#8a5a00"),
            ("severe", [4] * 10, self.hhie_s, "#feece7", "#c23b1c"),
            ("unknown", [2] * 10, hhia_s, None, "#495057"),
        )
        for level, scores, questionnaire, background, color in cases:
            with self.subTest(level=level):
                submission = self._submit(scores, questionnaire=questionnaire)
                if level == "unknown":
                    with self.assertLogs("screening.scoring", "ERROR"):
                        main = self._result(submission)
                else:
                    main = self._result(submission)
                self.assertRegex(main, rf'class="[^"]*\bresult-banner-{level}\b')
                rule = re.search(rf"\.result-banner-{level}\s*\{{([^}}]*)\}}", css)
                self.assertIsNotNone(rule)
                self.assertRegex(rule.group(1), rf"(?<!-)color:\s*{color}")
                if background:
                    self.assertRegex(rule.group(1), rf"background-color:\s*{background}")

    def test_result_zero_score(self):
        main = self._result(self._submit([0] * 10))
        self.assertIn("總分 0 分（滿分 40）", main)
        self.assertIn("無/極輕微影響", main)

    def test_result_without_thresholds_has_no_max(self):
        hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")
        submission = self._submit([2] * 10, questionnaire=hhia_s)
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
    """Spec docs/specs/phase4.md batch 2, acceptance 18-23."""

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
        cls.user = User.objects.create_user(username="pwatester")
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
                self.assertIn('<meta name="theme-color" content="#1f4e8c">', head)
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
            "theme_color": "#1f4e8c",
            "background_color": "#ffffff",
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

    # 21
    def test_pwa_folder_has_only_app_info_and_icons(self):
        # Allow-list: a service worker added here under any name fails this test.
        names = {path.name for path in self.PWA_DIR.iterdir()}
        expected = {
            "manifest.json",
            "icon.svg",
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

    # 23
    def test_home_links_to_guide_before_disclaimer(self):
        content = self.client.get(reverse("index")).content.decode()
        link = re.search(
            rf'<a[^>]*href="{reverse("add_to_home")}"[^>]*>\s*把 HearWell 加到手機主畫面', content
        )
        self.assertIsNotNone(link)
        self.assertLess(link.start(), content.index("本網站由執業聽力師開發"))
