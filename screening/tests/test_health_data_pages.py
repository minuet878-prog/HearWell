"""#182: 健康資料頁面 (GLOSSARY.md) are never cached; pages without health data still may be."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Audiogram, Category, Question, Questionnaire, Submission
from screening.tests.helpers import consented_user


class HealthDataPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="cachetester")
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

    def setUp(self):
        self.client.force_login(self.user)

    def assert_never_cached(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.get("Cache-Control", ""))

    def test_health_data_pages_are_never_cached(self):
        audiogram_args = [self.audiogram.id]
        for url in (
            reverse("questionnaire_list"),
            reverse("screening", args=[self.questionnaire.id]),
            reverse("result", args=[self.submission.id]),
            reverse("my_hearing"),
            reverse("hhi_comparison", args=[self.questionnaire.id]),
            reverse("download_my_data"),
            reverse("health_report"),
            reverse("account_settings"),
            reverse("audiogram_list"),
            reverse("audiogram_detail", args=audiogram_args),
            reverse("audiogram_edit", args=audiogram_args),
            reverse("audiogram_delete", args=audiogram_args),
            reverse("audiogram_compare"),
        ):
            with self.subTest(url=url):
                self.assert_never_cached(url)

    def test_pages_without_health_data_may_be_cached(self):
        self.client.logout()
        for name in ("index", "privacy", "family_guide", "add_to_home", "register"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("no-store", response.get("Cache-Control", ""))
