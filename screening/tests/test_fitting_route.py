from datetime import date, datetime

from django.test import TestCase
from django.utils import timezone

from screening.fitting_route import AUDIOGRAM, fitting_state
from screening.models import AidAndSubsidy, Questionnaire, Submission
from screening.questionnaires import hhie_s, ioi_ha
from screening.tests import test_guide_summary
from screening.tests.helpers import consented_user

PTA_55 = test_guide_summary.PTA_55
TODAY = date(2026, 10, 23)


class TodayTests(TestCase):
    """#285: the route is judged on the day it is given, so dated rules can be tested."""

    def test_the_state_keeps_the_day_it_was_judged_on(self):
        user = consented_user(username="today_user")
        self.assertEqual(fitting_state(user, TODAY).today, TODAY)


class CurrentStopTests(TestCase):
    """#258 (spec #257 Q18): the 目前這一站, the first rule from the top that holds."""

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
        self.assertEqual(self.stop(), "assessment")

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

    def test_reaching_the_threshold_is_the_assessment(self):
        self.make(PTA_55, PTA_55)
        self.assertEqual(self.stop(), "assessment")

    def test_an_ear_over_25_with_the_threshold_uncertain_is_before_you_go(self):
        self.make((30, 30, 30, 30), (30, 30, 30, 30), no_response_at=("right", 4000))
        self.assertEqual(fitting_state(self.user, TODAY).threshold["status"], "uncertain")
        self.assertEqual(self.stop(), "before-you-go")

    def test_an_ear_over_25_not_reaching_the_threshold_is_before_you_go(self):
        self.make((30, 30, 30, 30), (20, 20, 20, 20))
        self.assertEqual(self.stop(), "before-you-go")

    def test_one_ear_over_25_and_the_other_unknown_is_before_you_go(self):
        audiogram = self.make((30, 30, 30, 30), (20, 20, 20, 20))
        audiogram.points.filter(ear="left", frequency=4000).delete()
        self.assertEqual(self.stop(), "before-you-go")

    def test_both_ears_within_25_have_no_stop(self):
        self.make((25, 25, 25, 25), (10, 10, 10, 10))
        self.assertIsNone(self.stop())

    def test_the_latest_audiogram_decides(self):
        self.make(PTA_55, PTA_55, tested_on=date(2026, 9, 1))
        self.make((10, 10, 10, 10), (10, 10, 10, 10), tested_on=date(2026, 10, 1))
        self.assertIsNone(self.stop())


class CertificateRouteTests(TestCase):
    """#286 (spec #284 Q6): a 身障證明 the user says they have moves the 目前這一站 on to form 9."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="certificate_user")

    make = test_guide_summary.GuideSummaryTests.make
    answer = CurrentStopTests.answer

    def certify(self, has_certificate):
        AidAndSubsidy.objects.create(user=self.user, has_certificate=has_certificate)

    def stop(self):
        return fitting_state(self.user, TODAY).stop

    def test_a_certificate_without_an_audiogram_is_form_9(self):
        self.certify(True)
        self.assertEqual(self.stop(), "form-9")

    def test_a_certificate_comes_before_reaching_the_threshold(self):
        self.certify(True)
        self.make(PTA_55, PTA_55)
        self.assertEqual(self.stop(), "form-9")

    def test_a_certificate_comes_before_an_audiogram_that_cannot_tell(self):
        audiogram = self.make((20, 20, 20, 20), (20, 20, 20, 20))
        audiogram.points.filter(ear="left", frequency=4000).delete()
        self.certify(True)
        self.assertEqual(self.stop(), "form-9")

    def test_wearing_comes_before_a_certificate(self):
        self.certify(True)
        self.answer(wearing=True)
        self.assertEqual(self.stop(), "after-fitting")

    def test_not_yet_is_the_same_as_unanswered(self):
        for has_certificate in (False, None):
            with self.subTest(has_certificate=has_certificate):
                AidAndSubsidy.objects.filter(user=self.user).delete()
                self.make(PTA_55, PTA_55)
                self.certify(has_certificate)
                self.assertEqual(self.stop(), "assessment")


class FittedOnRouteTests(TestCase):
    """#287 (spec #284 acceptance 11, story 21): a fitting date the user filled in counts as
    wearing hearing aids, as the latest questionnaire answered wearing them does."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="fitted_on_user")

    make = test_guide_summary.GuideSummaryTests.make
    answer = CurrentStopTests.answer

    def state(self):
        return fitting_state(self.user, TODAY)

    def test_a_fitting_date_without_a_questionnaire_is_after_fitting(self):
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 5, 1))
        self.assertEqual(self.state().stop, "after-fitting")
        self.assertTrue(self.state().wearing)

    def test_a_fitting_date_with_the_latest_answered_without_them_is_after_fitting(self):
        self.make(PTA_55, PTA_55)
        self.answer(wearing=False)
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 5, 1))
        self.assertEqual(self.state().stop, "after-fitting")

    def test_without_a_fitting_date_the_rest_of_the_row_does_not_count_as_wearing(self):
        self.make(PTA_55, PTA_55)
        AidAndSubsidy.objects.create(
            user=self.user, ear="both", subsidy="disability", level="mid"
        )
        self.assertFalse(self.state().wearing)
        self.assertEqual(self.state().stop, "assessment")
