"""Ticket #210 (spec #208, ADR 0016): life-impact questionnaires are marked by their definition."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.tests.helpers import consented_user, fake_definition, register


class GradedButNotLifeImpactTests(TestCase):
    """A graded questionnaire that is not a life-impact one, like THI will be."""

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="life_impact_a")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhie_questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhie_s,
                question_text=f"HHIE題{i}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.graded = Questionnaire.objects.create(questionnaire_name="假分級", code="fake-graded")
        cls.graded_question = Question.objects.create(
            questionnaire=cls.graded, question_text="假題", question_number=1
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.enterContext(
            register(
                fake_definition(
                    "fake-graded",
                    thresholds=((2, "假的輕分級", "fake-low"), (4, "假的重分級", "fake-high")),
                    advice={"fake-low": "假的輕建議", "fake-high": "假的重建議"},
                )
            )
        )

    def _submit(self, questionnaire, questions, score, days_ago):
        submission = Submission.objects.create(user=self.user, questionnaire=questionnaire)
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score) for question in questions
        )
        when = timezone.now() - timedelta(days=days_ago)
        Submission.objects.filter(pk=submission.pk).update(created_at=when)
        return submission

    def test_home_keeps_the_life_impact_record_for_last_result_and_retest(self):
        # HHIE-S 200 days ago (retest due), then a newer graded record that is not life impact.
        self._submit(self.hhie_s, self.hhie_questions, 0, days_ago=200)
        self._submit(self.graded, [self.graded_question], 4, days_ago=10)
        response = self.client.get(reverse("index"))
        self.assertContains(response, '<div class="result-banner result-banner-normal">')
        self.assertContains(response, "無/極輕微影響")
        self.assertNotContains(response, "假的重分級")
        self.assertContains(response, "建議再做一次追蹤")
        retake = reverse("screening", args=[self.hhie_s.pk])
        self.assertContains(response, f'href="{retake}">再做一次（大約 3 分鐘）</a>')

    def test_home_has_no_retest_reminder_when_only_that_questionnaire_was_answered(self):
        self._submit(self.graded, [self.graded_question], 4, days_ago=200)
        response = self.client.get(reverse("index"))
        self.assertContains(response, "歡迎回來")
        self.assertNotContains(response, "建議再做一次追蹤")
        self.assertNotContains(response, "下次建議")
        self.assertNotContains(response, "再做一次（大約 3 分鐘）")
