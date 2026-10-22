"""Ticket #210 (spec #208, ADR 0016): life-impact questionnaires are marked by their definition."""

import re
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


class LevelColorTests(TestCase):
    """A level's colour (ADR 0007's three) is set apart from its code: two codes, one colour."""

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="life_impact_b")
        cls.graded = Questionnaire.objects.create(questionnaire_name="假分級", code="fake-colors")
        cls.question = Question.objects.create(
            questionnaire=cls.graded, question_text="假題", question_number=1
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.enterContext(
            register(
                fake_definition(
                    "fake-colors",
                    thresholds=(
                        (2, "假的無分級", "fake-none"),
                        (4, "假的輕分級", "fake-mild"),
                        (6, "假的中分級", "fake-moderate"),
                    ),
                    level_colors={
                        "fake-none": "normal",
                        "fake-mild": "mild_to_moderate",
                        "fake-moderate": "mild_to_moderate",
                    },
                    advice={"fake-mild": "假的輕建議", "fake-moderate": "假的中建議"},
                    trend_chart=True,
                )
            )
        )

    def _submit(self, score):
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.graded, wearing_hearing_aid=False
        )
        Answer.objects.create(submission=submission, question=self.question, score=score)
        return submission

    def test_result_page_shows_two_levels_in_one_colour_with_their_own_text(self):
        for score, text in ((4, "假的輕分級"), (6, "假的中分級")):
            with self.subTest(text=text):
                page = self.client.get(reverse("result", args=[self._submit(score).pk]))
                self.assertContains(
                    page, '<div class="result-banner result-banner-mild_to_moderate">'
                )
                self.assertContains(page, f'aria-describedby="result-score">{text}</h2>')

    def test_score_bar_segments_take_the_level_colours(self):
        page = self.client.get(reverse("result", args=[self._submit(4).pk])).content.decode()
        self.assertEqual(
            re.findall(
                r'class="score-bar-segment score-bar-segment-([\w-]+(?: score-bar-segment-deep)?)"',
                page,
            ),
            # The second of two levels in one colour is the deeper shade (Definition.shade).
            ["normal", "mild_to_moderate", "mild_to_moderate score-bar-segment-deep"],
        )

    def test_history_badges_and_trend_bands_take_the_level_colours(self):
        self._submit(4)
        self._submit(6)
        page = self.client.get(reverse("my_hearing")).content.decode()
        for text in ("假的輕分級", "假的中分級"):
            with self.subTest(text=text):
                self.assertIn(
                    f'<span class="level-badge level-badge-mild_to_moderate">{text}</span>', page
                )
        self.assertEqual(
            re.findall(r'<li class="trend-band-([\w-]+(?: trend-band-deep)?)">', page),
            ["mild_to_moderate trend-band-deep", "mild_to_moderate", "normal"],
        )

    def test_api_gives_each_level_its_colour_for_the_trend_chart(self):
        detail = self.client.get(reverse("api:questionnaire", args=[self.graded.pk])).json()
        self.assertEqual(
            [(level["code"], level["color"]) for level in detail["levels"]],
            [
                ("fake-none", "normal"),
                ("fake-mild", "mild_to_moderate"),
                ("fake-moderate", "mild_to_moderate"),
            ],
        )
