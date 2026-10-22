"""SADL answering, scoring and pre-launch visibility (#167)."""

import uuid
from dataclasses import replace
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
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
        catalog = self.client.get(reverse("questionnaire_list"))
        self.assertNotContains(catalog, "SADL")
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk]))
        self.assertEqual(page.status_code, 404)
        codes = [q["code"] for q in self.client.get("/api/questionnaires/").json()]
        self.assertNotIn("sadl", codes)

    @override_settings(DEBUG=True)
    def test_unlisted_sadl_is_offered_on_a_local_debug_site(self):
        catalog = self.client.get(reverse("questionnaire_list"))
        self.assertContains(catalog, "助聽器滿意度（SADL）")
        self.assertContains(catalog, "給正在戴或最近戴過助聽器的人。")
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk]))
        self.assertEqual(page.status_code, 200)

    def test_seeding_creates_fifteen_questions(self):
        self.assertEqual(self.questionnaire.questions.count(), 15)

    def test_listed_sadl_is_offered_in_production(self):
        with register(replace(sadl.DEFINITION, listed=True)):
            catalog = self.client.get(reverse("questionnaire_list"))
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
        for label in ("一點都沒有", "一點點", "有一些", "中等程度", "相當程度", "非常多", "極度"):
            self.assertEqual(page.count(f" {label}</label>"), 15, label)
        self.assertEqual(page.count('value="na"'), 2)
        self.assertIn("不適用：不戴助聽器講電話也聽得清楚", page)
        self.assertIn("不適用：助聽器的錢不是我出的（例如全額補助、家人出錢）", page)
        self.assertNotIn(">A<", page)


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
        self.assertContains(response, "第 3 題")
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
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk]))
        self.assertContains(page, credit)
        self.answer([4] * 15)
        result = self.client.get(reverse("result", args=[Submission.objects.get().pk]))
        self.assertContains(result, credit)
