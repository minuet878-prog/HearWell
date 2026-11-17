from datetime import date, datetime

from django.test import TestCase
from django.utils import timezone

from screening.fitting_route import AUDIOGRAM, fitting_state
from screening.models import AidAndSubsidy, Certificate, GuideChapterView, Questionnaire, Submission
from screening.questionnaires import hhie_s, ioi_ha
from screening.tests import test_fitting_advice, test_guide_summary
from screening.tests.helpers import consented_user

PTA_55 = test_guide_summary.PTA_55
TODAY = date(2026, 10, 23)


class TodayTests(TestCase):
    """#285: the route is judged on the day it is given, so dated rules can be tested."""

    def test_the_state_keeps_the_day_it_was_judged_on(self):
        user = consented_user(username="today_user")
        self.assertEqual(fitting_state(user, TODAY).today, TODAY)


class CurrentStopTests(TestCase):
    """#258 (spec #257 Q18), with #291's nine stops: the 目前這一站 from the records."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="route_user")

    make = test_guide_summary.GuideSummaryTests.make

    def answer(self, wearing=False, day=1, questionnaire=None):
        submission = Submission.objects.create(
            user=self.user,
            questionnaire=questionnaire or self.hhie_s,
            wearing_hearing_aid=wearing,
        )
        moment = timezone.make_aware(datetime(2026, 10, day, 12))
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)

    def stop(self):
        return fitting_state(self.user, TODAY).stop

    def test_without_an_audiogram_the_stop_is_recording_one(self):
        self.answer()
        self.assertEqual(self.stop(), AUDIOGRAM)
        self.assertFalse(fitting_state(self.user, TODAY).insufficient)

    def test_wearing_comes_first_even_when_the_threshold_is_reached(self):
        self.answer(wearing=True)
        self.make(PTA_55, PTA_55)
        self.assertEqual(self.stop(), "after-fitting")

    def test_wearing_without_an_audiogram_is_still_after_fitting(self):
        self.answer(wearing=True)
        self.assertEqual(self.stop(), "after-fitting")

    def test_an_ioi_ha_as_the_latest_questionnaire_counts_as_wearing(self):
        self.answer(wearing=False, day=1)
        self.answer(day=2, questionnaire=Questionnaire.objects.create(code=ioi_ha.CODE))
        self.assertEqual(self.stop(), "after-fitting")

    def test_only_the_latest_questionnaire_says_whether_hearing_aids_are_worn(self):
        self.answer(wearing=True, day=1)
        self.answer(wearing=False, day=2)
        self.make(PTA_55, PTA_55)
        self.assertEqual(self.stop(), "before-you-go")

    def test_an_audiogram_that_cannot_tell_is_recording_one_with_too_little_data(self):
        audiogram = self.make((20, 20, 20, 20), (20, 20, 20, 20))
        audiogram.points.filter(ear="left", frequency=4000).delete()
        self.assertEqual(self.stop(), AUDIOGRAM)
        self.assertTrue(fitting_state(self.user, TODAY).insufficient)

    def test_wearing_with_an_audiogram_that_cannot_tell_still_has_too_little_data(self):
        self.answer(wearing=True)
        audiogram = self.make((20, 20, 20, 20), (20, 20, 20, 20))
        audiogram.points.filter(ear="left", frequency=4000).delete()
        self.assertEqual(self.stop(), "after-fitting")
        self.assertTrue(fitting_state(self.user, TODAY).insufficient)

    def test_an_ear_over_25_with_the_threshold_uncertain_is_before_you_go(self):
        self.make((30, 30, 30, 30), (30, 30, 30, 30), no_response_at=("right", 4000))
        self.assertEqual(fitting_state(self.user, TODAY).threshold["status"], "uncertain")
        self.assertEqual(self.stop(), "before-you-go")

    def test_an_ear_over_40_not_reaching_the_threshold_is_before_you_go(self):
        # Spec #693 (ADR 0067) in place of grill Q3's 25 dB HL.
        self.make((45, 45, 45, 45), (20, 20, 20, 20))
        self.assertEqual(self.stop(), "before-you-go")

    def test_one_ear_over_40_and_the_other_unknown_is_before_you_go(self):
        audiogram = self.make((45, 45, 45, 45), (20, 20, 20, 20))
        audiogram.points.filter(ear="left", frequency=4000).delete()
        self.assertEqual(self.stop(), "before-you-go")

    def test_both_ears_within_25_have_no_stop(self):
        self.make((25, 25, 25, 25), (10, 10, 10, 10))
        self.assertIsNone(self.stop())

    def test_the_latest_audiogram_decides(self):
        self.make(PTA_55, PTA_55, tested_on=date(2026, 9, 1))
        self.make((10, 10, 10, 10), (10, 10, 10, 10), tested_on=date(2026, 10, 1))
        self.assertIsNone(self.stop())


class OldRulesGoneTests(TestCase):
    """#292 (spec #291): #284's rules are gone. A certificate no longer jumps to form 9, and
    form 25's first month no longer holds the 目前這一站 at 配戴之後; the stops move on as the
    user reads and answers them."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="old_rules_user")

    make = test_guide_summary.GuideSummaryTests.make

    def test_a_certificate_no_longer_moves_the_stop_to_form_9(self):
        self.make(PTA_55, PTA_55)
        AidAndSubsidy.objects.create(user=self.user, certificate="yes")
        self.assertEqual(fitting_state(self.user, TODAY).stop, "before-you-go")

    def test_form_25_s_dates_no_longer_move_the_stop(self):
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 5, 1), subsidy="disability", level="mid"
        )
        for today in (date(2026, 5, 20), date(2026, 7, 15), date(2026, 8, 2)):
            with self.subTest(today=today):
                self.assertEqual(fitting_state(self.user, today).stop, "form-25")


class FittedOnRouteTests(TestCase):
    """#287 (spec #291 Q5): a fitting date the user filled in counts as wearing hearing aids,
    as the latest questionnaire answered wearing them does."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="fitted_on_user")

    make = test_guide_summary.GuideSummaryTests.make
    answer = CurrentStopTests.answer

    def state(self):
        return fitting_state(self.user, TODAY)

    def test_a_fitting_date_without_a_questionnaire_looks_on_from_after_fitting(self):
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 5, 1))
        self.assertEqual(self.state().stop, "after-fitting")  # spec #291 Q16
        self.assertTrue(self.state().wearing)

    def test_a_fitting_date_with_the_latest_answered_without_them_looks_on_too(self):
        self.make(PTA_55, PTA_55)
        self.answer(wearing=False)
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 5, 1))
        self.assertEqual(self.state().stop, "after-fitting")  # spec #291 Q16

    def test_without_a_fitting_date_the_rest_of_the_row_does_not_count_as_wearing(self):
        self.make(PTA_55, PTA_55)
        AidAndSubsidy.objects.create(user=self.user, ear="both", subsidy="disability", level="mid")
        self.assertFalse(self.state().wearing)
        self.assertEqual(self.state().stop, "before-you-go")


class Form25DatesTests(TestCase):
    """#288 (spec #291 Implementation Decisions): someone who has to do form 25 does it from a
    month to three months after the fitting date, both days included. Kept for #296."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="form_25_user")

    answer = CurrentStopTests.answer

    def fit(self, fitted_on=date(2026, 5, 1), subsidy="disability", level="mid"):
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=fitted_on, subsidy=subsidy, level=level
        )

    def form_25(self):
        return fitting_state(self.user, TODAY).form_25

    def test_from_a_month_to_three_months_after_fitting(self):
        self.fit()
        self.assertEqual(self.form_25(), (date(2026, 6, 1), date(2026, 8, 1)))

    def test_a_month_after_the_31st_is_the_last_day_of_a_shorter_month(self):
        self.fit(fitted_on=date(2026, 1, 31))
        self.assertEqual(self.form_25(), (date(2026, 2, 28), date(2026, 4, 30)))

    def test_an_unknown_level_and_the_higher_levels_have_to_do_it(self):
        for level in ("unknown", "advanced", "cros"):
            with self.subTest(level=level):
                AidAndSubsidy.objects.filter(user=self.user).delete()
                self.fit(level=level)
                self.assertEqual(self.form_25(), (date(2026, 6, 1), date(2026, 8, 1)))

    def test_the_subsidy_unanswered_has_none(self):
        # Spec #291 Q16: the site does not guess form 25 is needed.
        self.fit(subsidy="", level="")
        self.assertIsNone(self.form_25())

    def test_basic_or_paying_otherwise_have_none(self):
        for subsidy, level in (("disability", "basic"), ("other", "")):
            with self.subTest(subsidy=subsidy, level=level):
                AidAndSubsidy.objects.filter(user=self.user).delete()
                self.fit(subsidy=subsidy, level=level)
                self.assertIsNone(self.form_25())

    def test_wearing_by_the_questionnaire_without_a_date_has_none(self):
        self.answer(wearing=True)
        AidAndSubsidy.objects.create(user=self.user, subsidy="disability", level="mid")
        self.assertIsNone(self.form_25())


class ReapplyDateTests(TestCase):
    """#288 (spec #284 acceptance 17): someone who bought with 身障補助 can apply again four
    years after the fitting date."""

    def setUp(self):
        self.user = consented_user(username="reapply_user")

    def reapply_on(self):
        return fitting_state(self.user, TODAY).reapply_on

    def test_four_years_after_the_fitting_date(self):
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 5, 1), subsidy="disability", level="basic"
        )
        self.assertEqual(self.reapply_on(), date(2030, 5, 1))

    def test_the_notice_received_counts_as_the_subsidy(self):
        # #296: 用身障補助 as spec #291 defines it, the notice received or 配戴之後's answer.
        AidAndSubsidy.objects.create(
            user=self.user,
            notice_received=True,
            approved_ears="both",
            level="mid",
            fitted_on=date(2026, 5, 1),
        )
        self.assertEqual(self.reapply_on(), date(2030, 5, 1))

    def test_the_end_of_february_in_a_year_that_is_not_leap(self):
        # 2100 is not a leap year: four years after 29 February is the 28th (spec #284 testing).
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2096, 2, 29), subsidy="disability", level="basic"
        )
        self.assertEqual(self.reapply_on(), date(2100, 2, 28))

    def test_none_without_the_subsidy_or_a_fitting_date(self):
        for fitted_on, subsidy in (
            (date(2026, 5, 1), "other"),
            (date(2026, 5, 1), ""),
            (None, "disability"),
        ):
            with self.subTest(fitted_on=fitted_on, subsidy=subsidy):
                AidAndSubsidy.objects.filter(user=self.user).delete()
                AidAndSubsidy.objects.create(user=self.user, fitted_on=fitted_on, subsidy=subsidy)
                self.assertIsNone(self.reapply_on())

    def test_none_before_filling_anything_in(self):
        self.assertIsNone(self.reapply_on())


class ViewingDoesNotStartRouteTests(TestCase):
    """#695 (spec #693 Q9): within the normal range the route waits until the user answers a
    question on it; a chapter viewed is 已完成 but does not start it."""

    def setUp(self):
        self.user = consented_user(username="viewing_user")
        self.make((20, 20, 20, 20), (20, 20, 20, 20))

    make = test_guide_summary.GuideSummaryTests.make

    def test_viewing_chapters_keeps_the_route_waiting(self):
        for chapter in ("before-you-go", "types-and-prices"):
            GuideChapterView.objects.create(user=self.user, chapter=chapter)
        state = fitting_state(self.user, TODAY)
        self.assertTrue(state.waiting)
        self.assertIsNone(state.stop)
        self.assertEqual(state.done, {AUDIOGRAM, "before-you-go", "types-and-prices"})

    def test_answering_a_question_on_the_route_starts_it(self):
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        AidAndSubsidy.objects.create(user=self.user, certificate=Certificate.APPLYING)
        state = fitting_state(self.user, TODAY)
        self.assertFalse(state.waiting)
        self.assertEqual(state.stop, "assessment")


class FittingAdviceRouteTests(test_fitting_advice.LifeImpactTestCase):
    """#697 (spec #693): the route waits while 建議評估選配 suggests no assessment yet, until an
    answer on it; someone wearing hearing aids is not judged by it."""

    MILD_EAR = (30, 30, 30, 30)
    NORMAL_EAR = (20, 20, 20, 20)

    def setUp(self):
        self.user = consented_user(username="advice_route_user")

    make = test_guide_summary.GuideSummaryTests.make

    def record(self, scores, **fields):
        submission = test_fitting_advice.record(self.user, scores)
        Submission.objects.filter(pk=submission.pk).update(**fields)

    def state(self):
        return fitting_state(self.user, TODAY)

    def test_mild_with_life_impact_goes_on_to_the_next_stop(self):
        # Spec #693 acceptance 6: the route has its 您在這裡.
        self.make(self.MILD_EAR, self.NORMAL_EAR)
        self.record(test_fitting_advice.MILD_SCORES)
        state = self.state()
        self.assertFalse(state.waiting)
        self.assertEqual(state.stop, "before-you-go")

    def test_tracked_or_waiting_on_a_questionnaire_the_route_has_no_stop(self):
        # Spec #693 acceptance 7 and 8: the audiogram stop done, no 您在這裡.
        self.make(self.MILD_EAR, self.NORMAL_EAR)
        for scores in (None, test_fitting_advice.NORMAL_SCORES):
            if scores is not None:
                self.record(scores)
            state = self.state()
            with self.subTest(scores=scores):
                self.assertTrue(state.waiting)
                self.assertIsNone(state.stop)
                self.assertEqual(state.done, {AUDIOGRAM})

    def test_an_answer_on_the_route_starts_it_when_tracked(self):
        self.make(self.MILD_EAR, self.NORMAL_EAR)
        self.record(test_fitting_advice.NORMAL_SCORES)
        AidAndSubsidy.objects.create(user=self.user, certificate=Certificate.APPLYING)
        state = self.state()
        self.assertFalse(state.waiting)
        self.assertEqual(state.stop, "before-you-go")

    def test_an_ear_that_could_change_the_result_keeps_the_audiogram_stop(self):
        audiogram = self.make(self.MILD_EAR, self.NORMAL_EAR)
        audiogram.points.filter(ear="left", frequency=4000).delete()
        state = self.state()
        self.assertTrue(state.insufficient)
        self.assertFalse(state.waiting)
        self.assertEqual(state.stop, AUDIOGRAM)

    def test_wearing_looks_on_from_after_fitting_whatever_the_advice(self):
        # Spec #693 acceptance 12.
        for ears in ((self.MILD_EAR, self.NORMAL_EAR), (self.NORMAL_EAR, self.NORMAL_EAR)):
            self.user = consented_user(username=f"advice_wearing_{ears[0][0]}")
            self.make(*ears)
            self.record(test_fitting_advice.NORMAL_SCORES, wearing_hearing_aid=True)
            state = self.state()
            with self.subTest(ears=ears):
                self.assertFalse(state.waiting)
                self.assertEqual(state.stop, "after-fitting")


class CrossReview693WearingAudiogramTests(test_fitting_advice.LifeImpactTestCase):
    """The cross review on #693, acceptance 12: someone wearing hearing aids has the audiogram
    stop done as before spec #693, an ear over 25 dB HL or both ears' PTA known, whatever an
    ear without a PTA and the life-impact record could make of 建議評估選配."""

    def setUp(self):
        self.user = consented_user(username="wearing_audiogram_user")
        audiogram = self.make((30, 30, 30, 30), (20, 20, 20, 20))
        audiogram.points.filter(ear="left", frequency=4000).delete()

    make = test_guide_summary.GuideSummaryTests.make

    def assert_audiogram_done(self):
        state = fitting_state(self.user, TODAY)
        self.assertTrue(state.wearing)
        self.assertIn(AUDIOGRAM, state.done)
        self.assertFalse(state.insufficient)
        self.assertEqual(state.stop, "after-fitting")

    def test_a_fitting_date_and_no_life_impact_record(self):
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 5, 1))
        self.assert_audiogram_done()

    def test_the_latest_life_impact_record_answered_wearing_them_and_not_affected(self):
        # The same cause: 追蹤 not wearing them, so unknown with the ear without a PTA.
        submission = test_fitting_advice.record(self.user, test_fitting_advice.NORMAL_SCORES)
        Submission.objects.filter(pk=submission.pk).update(wearing_hearing_aid=True)
        self.assert_audiogram_done()

    def test_both_ears_within_25_and_one_unknown_still_has_too_little_data(self):
        # As before: no ear over 25 dB HL, so the unknown one could still be.
        self.user = consented_user(username="wearing_normal_user")
        audiogram = self.make((20, 20, 20, 20), (20, 20, 20, 20))
        audiogram.points.filter(ear="left", frequency=4000).delete()
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 5, 1))
        state = fitting_state(self.user, TODAY)
        self.assertTrue(state.insufficient)
        self.assertNotIn(AUDIOGRAM, state.done)
