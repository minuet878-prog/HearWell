"""#697 (spec #693, ADR 0067): 建議評估選配 judged from one audiogram and the latest life-impact
record, 40 dB HL taken as 輕度 as the degree table has it and the questionnaire by its level."""

from datetime import date, datetime
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from screening.audiogram import FittingAdvice, fitting_advice
from screening.fitting_route import fitting_state
from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.questionnaires import hhia_s, hhie_s, ioi_ha, thi
from screening.tests import test_guide_summary, test_guide_threshold
from screening.tests.helpers import consented_user

TODAY = date(2026, 11, 17)
# Ten items' scores graded 無／極輕微影響 (8), 輕度到中度影響 (10) and 顯著影響 (26).
NORMAL_SCORES = (4, 4, 0, 0, 0, 0, 0, 0, 0, 0)
MILD_SCORES = (4, 4, 2, 0, 0, 0, 0, 0, 0, 0)
SEVERE_SCORES = (4, 4, 4, 4, 4, 2, 2, 2, 0, 0)


def points(right, left):
    """One audiogram's air points, each ear's four PTA frequencies at a value; None leaves an ear
    without 4000 Hz, so its PTA cannot be worked out."""
    made = []
    for side, value in (("right", right), ("left", left)):
        ear = test_guide_threshold.ear(side, (60 if value is None else value,) * 4)
        made += ear[:3] if value is None else ear
    return [mock.Mock(**point) for point in made]


def record(user, scores, code=hhie_s.CODE, on=None):
    """The user's record answered with these scores, on a day at noon when one is given."""
    questionnaire = Questionnaire.objects.get(code=code)
    submission = Submission.objects.create(user=user, questionnaire=questionnaire)
    if on is not None:
        moment = timezone.make_aware(datetime(on.year, on.month, on.day, 12))
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
    Answer.objects.bulk_create(
        Answer(submission=submission, question=question, score=score)
        for question, score in zip(
            questionnaire.questions.order_by("question_number"), scores, strict=True
        )
    )
    return submission


class LifeImpactTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        for code in (hhie_s.CODE, hhia_s.CODE, thi.CODE, ioi_ha.CODE):
            questionnaire = Questionnaire.objects.create(questionnaire_name=code, code=code)
            Question.objects.bulk_create(
                Question(
                    questionnaire=questionnaire,
                    question_text=f"假題{i}",
                    question_number=i,
                    category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
                )
                for i in range(1, 11)
            )


class FittingAdviceJudgmentTests(LifeImpactTestCase):
    """Spec #693's table: the ear's PTA by the latest life-impact record, at 25/26 and 40/41."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = consented_user(username="advice_user")
        cls.normal = record(cls.user, NORMAL_SCORES)
        cls.mild = record(cls.user, MILD_SCORES)
        cls.severe = record(cls.user, SEVERE_SCORES)

    def test_either_ear_over_40_recommends_whatever_the_questionnaire(self):
        for life_impact in (None, self.normal, self.mild, self.severe):
            with self.subTest(life_impact=life_impact):
                self.assertEqual(
                    fitting_advice(points(41, 10), life_impact), FittingAdvice.RECOMMEND
                )
                self.assertEqual(
                    fitting_advice(points(10, 60), life_impact), FittingAdvice.RECOMMEND
                )

    def test_the_worse_ear_at_26_to_40_goes_by_the_questionnaire(self):
        # 40 is 輕度 on the degree table, 26 the first over the normal limit.
        for worse in (26, 40):
            for life_impact, advice in (
                (None, FittingAdvice.QUESTIONNAIRE_FIRST),
                (self.normal, FittingAdvice.TRACK),
                (self.mild, FittingAdvice.RECOMMEND),
                (self.severe, FittingAdvice.RECOMMEND),
            ):
                with self.subTest(worse=worse, life_impact=life_impact):
                    self.assertEqual(fitting_advice(points(worse, 10), life_impact), advice)
                    self.assertEqual(fitting_advice(points(25, worse), life_impact), advice)

    def test_both_ears_within_25_are_normal_whatever_the_questionnaire(self):
        for life_impact in (None, self.normal, self.severe):
            with self.subTest(life_impact=life_impact):
                self.assertEqual(fitting_advice(points(25, 25), life_impact), FittingAdvice.NORMAL)

    def test_hhia_s_counts_as_hhie_s_does(self):
        normal = record(self.user, NORMAL_SCORES, code=hhia_s.CODE)
        mild = record(self.user, MILD_SCORES, code=hhia_s.CODE)
        self.assertEqual(fitting_advice(points(30, 10), normal), FittingAdvice.TRACK)
        self.assertEqual(fitting_advice(points(30, 10), mild), FittingAdvice.RECOMMEND)

    def test_an_ear_without_a_pta_matters_only_when_it_could_change_the_result(self):
        # Spec #693 acceptance 13: 45 and a missing ear recommends; 30 and one cannot tell.
        self.assertEqual(fitting_advice(points(45, None), None), FittingAdvice.RECOMMEND)
        self.assertEqual(fitting_advice(points(None, 45), None), FittingAdvice.RECOMMEND)
        for life_impact in (None, self.normal):
            with self.subTest(life_impact=life_impact):
                self.assertEqual(
                    fitting_advice(points(30, None), life_impact), FittingAdvice.UNKNOWN
                )
        # 輕度 with life impact recommends, whatever the missing ear is.
        self.assertEqual(fitting_advice(points(30, None), self.mild), FittingAdvice.RECOMMEND)
        self.assertEqual(fitting_advice(points(20, None), None), FittingAdvice.UNKNOWN)
        self.assertEqual(fitting_advice(points(None, None), self.severe), FittingAdvice.UNKNOWN)


class FittingAdviceLatestRecordTests(LifeImpactTestCase):
    """The user's own latest audiogram and latest HHIE-S or HHIA-S, whenever it was answered."""

    def setUp(self):
        self.user = consented_user(username="latest_user")

    make = test_guide_summary.GuideSummaryTests.make

    def advice(self, user=None):
        return fitting_state(user or self.user, TODAY).advice

    def test_without_an_audiogram_there_is_no_advice(self):
        record(self.user, SEVERE_SCORES)
        self.assertIsNone(self.advice())

    def test_the_newer_record_decides_either_way(self):
        # Spec #693 acceptance 9.
        self.make((30,) * 4, (10,) * 4)
        record(self.user, NORMAL_SCORES, on=date(2026, 5, 1))
        record(self.user, MILD_SCORES, on=date(2026, 9, 1))
        self.assertEqual(self.advice(), FittingAdvice.RECOMMEND)
        record(self.user, NORMAL_SCORES, on=date(2026, 10, 1))
        self.assertEqual(self.advice(), FittingAdvice.TRACK)

    def test_a_record_years_old_still_counts(self):
        self.make((30,) * 4, (10,) * 4)
        record(self.user, MILD_SCORES, on=date(2020, 1, 1))
        self.assertEqual(self.advice(), FittingAdvice.RECOMMEND)

    def test_hhia_s_newer_than_hhie_s_decides(self):
        self.make((30,) * 4, (10,) * 4)
        record(self.user, MILD_SCORES, on=date(2026, 5, 1))
        record(self.user, NORMAL_SCORES, code=hhia_s.CODE, on=date(2026, 9, 1))
        self.assertEqual(self.advice(), FittingAdvice.TRACK)

    def test_thi_and_ioi_ha_are_no_life_impact_records(self):
        self.make((30,) * 4, (10,) * 4)
        record(self.user, SEVERE_SCORES, code=thi.CODE, on=date(2026, 9, 1))
        self.assertEqual(self.advice(), FittingAdvice.QUESTIONNAIRE_FIRST)
        record(self.user, NORMAL_SCORES, on=date(2026, 5, 1))
        record(self.user, SEVERE_SCORES, code=ioi_ha.CODE, on=date(2026, 10, 1))
        self.assertEqual(self.advice(), FittingAdvice.TRACK)

    def test_only_the_user_s_own_records_count(self):
        # Spec #693 acceptance 15: judged on the owner's audiogram and questionnaire alone.
        other = consented_user(username="other_user")
        self.make((30,) * 4, (10,) * 4)
        self.make((60,) * 4, (60,) * 4, user=other)
        record(other, MILD_SCORES)
        self.assertEqual(self.advice(), FittingAdvice.QUESTIONNAIRE_FIRST)
        record(self.user, NORMAL_SCORES)
        self.assertEqual(self.advice(), FittingAdvice.TRACK)
        self.assertEqual(self.advice(other), FittingAdvice.RECOMMEND)
