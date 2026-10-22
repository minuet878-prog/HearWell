"""SADL answering, scoring and pre-launch visibility (#167)."""

import re
import uuid
from dataclasses import replace
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.models import Questionnaire, Submission
from screening.questionnaires import sadl
from screening.tests.helpers import consented_user, register


class SadlTestCase(TestCase):
    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.questionnaire = Questionnaire.objects.get(code="sadl")
        self.user = consented_user(username="sadl_user", password="Test-pass-12345")
        self.client.force_login(self.user)


class SadlVisibilityTests(SadlTestCase):
    def test_unlisted_sadl_is_hidden_in_production(self):
        catalog = self.client.get(reverse("questionnaire_list"), {"choose": "self"})
        # The full list (choose for myself), with the other questionnaires but not SADL.
        self.assertContains(catalog, "日常聆聽能力（SSQ12-TW）")
        self.assertNotContains(catalog, "SADL")
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk]))
        self.assertEqual(page.status_code, 404)
        codes = [q["code"] for q in self.client.get("/api/questionnaires/").json()]
        self.assertNotIn("sadl", codes)

    @override_settings(DEBUG=True)
    def test_unlisted_sadl_is_offered_on_a_local_debug_site(self):
        catalog = self.client.get(reverse("questionnaire_list"), {"choose": "self"})
        self.assertContains(catalog, "助聽器滿意度（SADL）")
        self.assertContains(catalog, "給正在戴或最近戴過助聽器的人。")
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk]))
        self.assertEqual(page.status_code, 200)

    def test_seeding_creates_fifteen_questions(self):
        self.assertEqual(self.questionnaire.questions.count(), 15)

    def test_listed_sadl_is_offered_in_production(self):
        with register(replace(sadl.DEFINITION, listed=True)):
            catalog = self.client.get(reverse("questionnaire_list"), {"choose": "self"})
        self.assertContains(catalog, "助聽器滿意度（SADL）")


@override_settings(DEBUG=True)
class SadlAnsweringTests(SadlTestCase):
    def test_answer_page_does_not_ask_about_wearing_and_explains_who_answers_item_14(self):
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk]))
        self.assertNotContains(page, "有沒有戴助聽器")
        self.assertNotContains(page, 'id="answer-app"')
        self.assertContains(page, "請依您現在戴著或最近戴過的助聽器回答")
        self.assertContains(page, "拿部分補助、自己也付了錢，請照樣作答")

    def test_every_item_has_seven_labels_and_only_items_11_and_14_take_not_applicable(self):
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk])).content.decode()
        labels = ["一點都沒有", "一點點", "有一些", "中等程度", "相當程度", "非常多", "極度"]
        seven = [(str(value), label) for value, label in enumerate(labels, start=1)]
        not_applicable = {
            11: ("na", "不適用：不戴助聽器講電話也聽得清楚"),
            14: ("na", "不適用：助聽器的錢不是我出的（例如全額補助、家人出錢）"),
        }
        for number in range(1, 16):
            with self.subTest(item=number):
                group = re.search(rf'id="question-{number}".*?</fieldset>', page, re.S).group()
                # Each option is the radio's value and the text right after it, so a letter
                # A–G in front of a label would not match.
                options = re.findall(
                    r'value="([^"]+)" class="choice-group" id="[^"]+">\n (.*?)</label>', group
                )
                expected = seven + ([not_applicable[number]] if number in not_applicable else [])
                self.assertEqual(options, expected)


@override_settings(DEBUG=True)
class SadlScoringTests(SadlTestCase):
    def answer(self, values):
        """Sends the server form; each value is 1–7, "na", or None for an unanswered item."""
        questions = list(self.questionnaire.questions.all())
        data = {
            "idempotency_key": str(uuid.uuid4()),
            "form-TOTAL_FORMS": len(questions),
            "form-INITIAL_FORMS": 0,
        }
        for index, (question, value) in enumerate(zip(questions, values, strict=True)):
            data[f"form-{index}-question_id"] = question.pk
            if value is not None:
                data[f"form-{index}-score"] = value
        return self.client.post(reverse("screening", args=[self.questionnaire.pk]), data)

    def test_an_unanswered_item_is_not_saved_and_is_listed(self):
        response = self.answer([4, 4, None] + [4] * 12)
        self.assertContains(response, 'href="#question-3">第 3 題</a>')
        self.assertNotContains(response, 'href="#question-2">')
        self.assertFalse(Submission.objects.exists())

    def test_not_applicable_is_refused_outside_items_11_and_14(self):
        response = self.answer(["na"] + [4] * 14)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Submission.objects.exists())

    def test_a_record_is_saved_as_worn(self):
        response = self.answer([4] * 15)
        submission = Submission.objects.get()
        self.assertRedirects(response, reverse("result", args=[submission.pk]))
        self.assertIs(submission.wearing_hearing_aid, True)

    def test_overall_and_subscale_scores_with_reversed_items_and_not_applicable(self):
        # Worked by hand from the official scoring rules: items 2, 4, 7 and 13 are reversed.
        cases = (
            ([4] * 15, "4.0", ("4.0", "4.0", "4.0", "4.0"), False),
            ([1] * 15, "2.6", ("1.0", "1.0", "5.0", "5.0"), False),
            ([1] * 10 + ["na", 1, 1, "na", 1], "2.8", ("1.0", "1.0", "7.0", "5.0"), True),
        )
        names = ("正面效果", "服務與費用", "負面特徵", "個人形象")
        for values, overall, subscales, skipped in cases:
            with self.subTest(overall=overall):
                self.answer(values)
                submission = Submission.objects.latest("pk")
                data = self.client.get(f"/api/submissions/{submission.pk}/").json()
                self.assertEqual(data["satisfaction"]["overall"], overall)
                self.assertEqual(
                    [(s["name"], s["score"]) for s in data["satisfaction"]["subscales"]],
                    list(zip(names, subscales, strict=True)),
                )
                self.assertIsNone(data["scores"])
                self.assertIsNone(data["level"])
                self.assertNotIn("average_score", data)
                page = self.client.get(reverse("result", args=[submission.pk]))
                self.assertContains(page, f"整體滿意度：{overall}")
                for name, score in zip(names, subscales, strict=True):
                    self.assertContains(page, f"{name}：{score}")
                if skipped:
                    self.assertContains(page, "第 11、14 題選了「不適用」，沒有算進分數")
                else:
                    self.assertNotContains(page, "沒有算進分數")

    def test_result_page_explains_the_scale_without_norms_or_grades(self):
        self.answer([4] * 15)
        page = self.client.get(reverse("result", args=[Submission.objects.get().pk]))
        self.assertContains(page, "1 到 7 分，分數越高越滿意，4 分是中間")
        self.assertNotContains(page, "常模")
        self.assertNotContains(page, "level-badge")

    def test_answer_and_result_pages_credit_the_scale_and_its_translators(self):
        credit = "© University of Memphis, 1999；中文版：Fang 等，2013（國泰綜合醫院）"
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk])).content.decode()
        self.assertGreater(page.find(credit), page.index("</form>"))
        self.answer([4] * 15)
        result = self.client.get(reverse("result", args=[Submission.objects.get().pk]))
        result = result.content.decode()
        self.assertGreater(result.find(credit), result.index("選擇問卷</a>"))

    def test_result_page_reads_the_answers_once(self):
        self.answer([4] * 15)
        submission = Submission.objects.get()
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("result", args=[submission.pk]))
        reads = [q for q in ctx.captured_queries if '"screening_question"' in q["sql"]]
        self.assertEqual(len(reads), 1)

    def test_each_subscale_shows_the_owner_approved_explanation(self):
        # Text approved by the owner in #168.
        approved = {
            "正面效果": "戴助聽器帶來多少好處，例如比較聽得懂別人說話、比較少請人重說、"
            "比較有自信、聲音聽起來自然。",
            "服務與費用": "您對幫您調整助聽器的人員、助聽器的價格，"
            "以及助聽器耐不耐用，滿意的程度。",
            "負面特徵": "助聽器帶來的困擾，例如聲音跟預期不同、轉大聲時出現迴音（嘯叫聲），"
            "以及講電話時幫不幫得上忙。分數越高，代表困擾越少。",
            "個人形象": "戴助聽器時，您在不在意外觀和別人的眼光。分數越高，代表越不在意、"
            "對自己的樣子越滿意。",
        }
        self.answer([4] * 15)
        page = self.client.get(reverse("result", args=[Submission.objects.get().pk]))
        for name, text in approved.items():
            with self.subTest(name=name):
                self.assertContains(page, f"<strong>{name}：4.0</strong><br>{text}")

    def test_the_submission_list_reads_answers_the_same_number_of_times_for_two_or_five(self):
        def list_queries():
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get("/api/submissions/")
            self.assertEqual(response.status_code, 200)
            return len(ctx.captured_queries)

        for _ in range(2):
            self.answer([4] * 15)
        two = list_queries()
        for _ in range(3):
            self.answer([4] * 15)
        self.assertEqual(list_queries(), two)


@override_settings(DEBUG=True)
class SadlHistoryTests(SadlTestCase):
    """我的紀錄的 SADL 分頁 (#171)."""

    def answer(self, values):
        questions = list(self.questionnaire.questions.all())
        data = {
            "idempotency_key": str(uuid.uuid4()),
            "form-TOTAL_FORMS": len(questions),
            "form-INITIAL_FORMS": 0,
        }
        for index, (question, value) in enumerate(zip(questions, values, strict=True)):
            data[f"form-{index}-question_id"] = question.pk
            if value is not None:
                data[f"form-{index}-score"] = value
        return self.client.post(reverse("screening", args=[self.questionnaire.pk]), data)

    def test_the_sadl_tab_lists_each_record_by_overall_score_linking_to_its_result(self):
        # A second questionnaire so the tab nav (and its label) actually renders.
        Submission.objects.create(
            user=self.user, questionnaire=Questionnaire.objects.get(code="ssq12-tw")
        )
        self.answer([4] * 15)
        first = Submission.objects.latest("pk")
        self.answer([1] * 15)
        second = Submission.objects.latest("pk")
        history = self.client.get(reverse("my_hearing"), {"questionnaire": "sadl"})
        self.assertContains(history, "助聽器滿意度（SADL）")
        self.assertContains(history, "整體滿意度：4.0")
        self.assertContains(history, "整體滿意度：2.6")
        self.assertContains(history, reverse("result", args=[first.pk]))
        self.assertContains(history, reverse("result", args=[second.pk]))

    def test_the_sadl_tab_has_no_wearing_comparison_or_trend_chart(self):
        self.answer([4] * 15)
        self.answer([1] * 15)
        history = self.client.get(reverse("my_hearing"), {"questionnaire": "sadl"})
        self.assertNotContains(history, "配戴狀態比較")
        self.assertNotContains(history, "比較戴與不戴助聽器")
        self.assertNotIn("trend-chart", history.content.decode())
        self.assertNotContains(history, "screening/frontend/trend-chart.js")

    def test_another_users_sadl_record_does_not_appear(self):
        self.answer([4] * 15)
        other = consented_user(username="sadl_other", password="Test-pass-12345")
        self.client.force_login(other)
        self.answer([1] * 15)
        self.client.force_login(self.user)
        history = self.client.get(reverse("my_hearing"), {"questionnaire": "sadl"})
        self.assertContains(history, "整體滿意度：4.0")
        self.assertNotContains(history, "整體滿意度：2.6")

    def test_the_tab_reads_answers_the_same_number_of_times_for_two_or_five_records(self):
        def list_queries():
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get(reverse("my_hearing"), {"questionnaire": "sadl"})
            self.assertEqual(response.status_code, 200)
            return len(ctx.captured_queries)

        for _ in range(2):
            self.answer([4] * 15)
        two = list_queries()
        for _ in range(3):
            self.answer([4] * 15)
        self.assertEqual(list_queries(), two)
