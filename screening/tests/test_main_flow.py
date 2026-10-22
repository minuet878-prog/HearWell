"""Spec #148 batch 2, ticket #159: the shared new/old-user state."""

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from screening.main_flow import get_user_state
from screening.models import Answer, Audiogram, Category, Question, Questionnaire, Submission
from screening.tests.helpers import consented_user


class UserStateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="tester")
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
        cls.hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")
        cls.hhia_questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhia_s,
                question_text=f"HHIA題{i}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        cls.ioi_questions = Question.objects.bulk_create(
            Question(questionnaire=cls.ioi_ha, question_text=f"IOI題{i}", question_number=i)
            for i in range(1, 8)
        )

    def _at(self, submission, days_ago):
        when = timezone.now() - timedelta(days=days_ago)
        Submission.objects.filter(pk=submission.pk).update(created_at=when)
        return submission

    def _hhi(self, questionnaire, questions, days_ago, user=None):
        submission = Submission.objects.create(user=user or self.user, questionnaire=questionnaire)
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=0) for question in questions
        )
        return self._at(submission, days_ago)

    def _ioi_ha(self, days_ago, user=None):
        submission = Submission.objects.create(
            user=user or self.user, questionnaire=self.ioi_ha, norm_group="ungrouped"
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=3)
            for question in self.ioi_questions
        )
        return self._at(submission, days_ago)

    def test_no_submissions_is_a_new_user(self):
        state = get_user_state(self.user, today=date(2026, 10, 22))
        self.assertTrue(state.is_new)
        self.assertIsNone(state.last_result)

    def test_an_audiogram_alone_is_still_a_new_user(self):
        Audiogram.objects.create(user=self.user, tested_on=date(2026, 9, 1))
        state = get_user_state(self.user, today=date(2026, 10, 22))
        self.assertTrue(state.is_new)

    def test_last_result_prefers_the_latest_life_impact_submission(self):
        self._ioi_ha(days_ago=10)
        hhie = self._hhi(self.hhie_s, self.hhie_questions, days_ago=5)
        state = get_user_state(self.user, today=date(2026, 10, 22))
        self.assertFalse(state.is_new)
        self.assertEqual(state.last_result.submission, hhie)
        self.assertTrue(state.last_result.is_life_impact)

    def test_last_result_falls_back_to_another_questionnaire_without_a_retest_reminder(self):
        ioi = self._ioi_ha(days_ago=200)
        state = get_user_state(self.user, today=date(2026, 10, 22))
        self.assertEqual(state.last_result.submission, ioi)
        self.assertFalse(state.last_result.is_life_impact)
        self.assertFalse(state.retest_due)
        self.assertIsNone(state.next_suggested_date)

    def test_retest_due_at_exactly_six_months(self):
        self._hhi(self.hhie_s, self.hhie_questions, days_ago=0)
        Submission.objects.update(created_at=timezone.make_aware(timezone.datetime(2026, 4, 22)))
        state = get_user_state(self.user, today=date(2026, 10, 22))
        self.assertTrue(state.retest_due)

    def test_not_yet_due_one_month_in(self):
        self._hhi(self.hhie_s, self.hhie_questions, days_ago=0)
        Submission.objects.update(created_at=timezone.make_aware(timezone.datetime(2026, 9, 22)))
        state = get_user_state(self.user, today=date(2026, 10, 22))
        self.assertFalse(state.retest_due)
        self.assertEqual(state.next_suggested_date, date(2027, 3, 22))

    def test_retake_opens_the_same_questionnaire(self):
        # Even once the user has turned 65 (who the wizard would now route to HHIE-S), "再做
        # 一次" reopens the questionnaire the record itself belongs to.
        older = consented_user(username="turned_65", birth_year=date.today().year - 65)
        self._hhi(self.hhia_s, self.hhia_questions, days_ago=1, user=older)
        state = get_user_state(older, today=date(2026, 10, 22))
        self.assertEqual(state.retest_questionnaire, self.hhia_s)

    def test_only_the_given_user_is_considered(self):
        other = consented_user(username="other")
        self._hhi(self.hhie_s, self.hhie_questions, days_ago=1, user=other)
        state = get_user_state(self.user, today=date(2026, 10, 22))
        self.assertTrue(state.is_new)
