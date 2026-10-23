from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.fitting_route import AUDIOGRAM, fitting_state
from screening.models import AidAndSubsidy, GuideChapterView, Questionnaire
from screening.questionnaires import hhie_s, ioi_ha
from screening.tests import test_fitting_route, test_guide_summary
from screening.tests.helpers import consented_user

TODAY = date(2026, 10, 23)
PTA_55 = test_guide_summary.PTA_55
OVER_25 = ((30, 30, 30, 30), (20, 20, 20, 20))
WITHIN_25 = ((25, 25, 25, 25), (10, 10, 10, 10))


class ChapterViewTests(TestCase):
    """#292 (spec #291 acceptance 4): opening a chapter signed in records it as 看過, once."""

    def setUp(self):
        self.user = consented_user(username="chapter_reader")
        self.client.force_login(self.user)

    def open(self, slug):
        return self.client.get(reverse("guide_chapter", args=[slug]))

    def viewed(self, user=None):
        return list(
            GuideChapterView.objects.filter(user=user or self.user).values_list(
                "chapter", flat=True
            )
        )

    def test_opening_a_chapter_signed_in_records_it(self):
        self.assertEqual(self.open("before-you-go").status_code, 200)
        self.assertEqual(self.viewed(), ["before-you-go"])

    def test_opening_it_again_keeps_the_first_time(self):
        self.open("types-and-prices")
        first = GuideChapterView.objects.get(user=self.user).first_viewed_at
        self.open("types-and-prices")
        self.assertEqual(self.viewed(), ["types-and-prices"])
        self.assertEqual(GuideChapterView.objects.get(user=self.user).first_viewed_at, first)

    def test_signed_out_records_nothing(self):
        self.client.logout()
        self.assertEqual(self.open("before-you-go").status_code, 200)
        self.assertFalse(GuideChapterView.objects.exists())

    def test_only_the_reader_s_own_views_are_recorded(self):
        other = consented_user(username="other_reader")
        self.open("form-9")
        self.assertEqual(self.viewed(other), [])

    def test_an_unknown_chapter_records_nothing(self):
        self.assertEqual(self.open("no-such-chapter").status_code, 404)
        self.assertFalse(GuideChapterView.objects.exists())

    def queries_opening(self, slug):
        with CaptureQueriesContext(connection) as queries:
            self.open(slug)
        return len(queries)

    def test_the_queries_stay_the_same_however_many_chapters_were_read(self):
        # CODING_STANDARDS 15: recording a view does not grow with the views already there.
        self.open("form-9")
        self.open("types-and-prices")
        with_two = self.queries_opening("before-you-go")
        GuideChapterView.objects.filter(chapter="before-you-go").delete()
        for slug in ("assessment", "after-fitting", "form-25"):
            self.open(slug)
        self.assertEqual(self.queries_opening("before-you-go"), with_two)


class AidPageGoneTests(TestCase):
    """#292 (spec #291 acceptance 26): #284's 我的助聽器與補助 page is gone."""

    def test_its_old_address_is_not_found(self):
        self.client.force_login(consented_user(username="old_page_reader"))
        self.assertEqual(self.client.get("/my_aid").status_code, 404)
        self.assertEqual(self.client.post("/my_aid", {"has_certificate": "True"}).status_code, 404)
        self.assertFalse(AidAndSubsidy.objects.exists())


class HereTests(TestCase):
    """#292 (spec #291 acceptance 1-5, 12, 19, story 33): 您在這裡 is the first stop not done;
    someone wearing hearing aids looks from 配戴之後 on."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="nine_stops_user")

    make = test_guide_summary.GuideSummaryTests.make
    answer = test_fitting_route.CurrentStopTests.answer

    def view(self, *chapters):
        for chapter in chapters:
            GuideChapterView.objects.create(user=self.user, chapter=chapter)

    def state(self):
        return fitting_state(self.user, TODAY)

    # 1
    def test_without_an_audiogram_it_is_recording_one(self):
        self.answer()
        self.assertEqual(self.state().stop, AUDIOGRAM)
        self.assertEqual(self.state().done, frozenset())

    def test_an_audiogram_missing_a_frequency_is_recording_one_and_not_done(self):
        audiogram = self.make(*WITHIN_25)
        audiogram.points.filter(ear="left", frequency=4000).delete()
        self.view("before-you-go")
        self.assertEqual(self.state().stop, AUDIOGRAM)
        self.assertNotIn(AUDIOGRAM, self.state().done)

    # 2
    def test_a_complete_audiogram_over_25_is_done_and_here_moves_to_before_you_go(self):
        self.make(*OVER_25)
        self.assertEqual(self.state().done, {AUDIOGRAM})
        self.assertEqual(self.state().stop, "before-you-go")

    def test_reaching_the_threshold_still_starts_at_before_you_go(self):
        # Default 4: in place of #257 Q5's 達到就到身障鑑定.
        self.make(PTA_55, PTA_55)
        self.assertEqual(self.state().stop, "before-you-go")

    def test_viewing_before_you_go_makes_it_done_and_moves_on_to_the_assessment(self):
        self.make(PTA_55, PTA_55)
        self.view("before-you-go")
        self.assertEqual(self.state().done, {AUDIOGRAM, "before-you-go"})
        self.assertEqual(self.state().stop, "assessment")

    # 3
    def test_both_ears_within_25_with_nothing_started_have_no_stop(self):
        self.make(*WITHIN_25)
        self.assertEqual(self.state().done, {AUDIOGRAM})
        self.assertIsNone(self.state().stop)

    def test_both_ears_within_25_after_viewing_any_chapter_follow_the_rule(self):
        self.make(*WITHIN_25)
        self.view("types-and-prices")
        self.assertEqual(self.state().stop, "before-you-go")
        self.view("before-you-go")
        self.assertEqual(self.state().stop, "assessment")

    def test_both_ears_within_25_after_any_answer_follow_the_rule(self):
        self.make(*WITHIN_25)
        AidAndSubsidy.objects.create(user=self.user, has_certificate=True)
        self.assertEqual(self.state().stop, "before-you-go")

    def test_viewing_a_chapter_without_a_stop_of_its_own_also_starts_the_route(self):
        self.make(*WITHIN_25)
        self.view("form-25")
        self.assertEqual(self.state().stop, "before-you-go")
        self.assertEqual(self.state().done, {AUDIOGRAM})

    # 5
    def test_viewing_types_and_prices_out_of_order_is_done_and_here_stays_at_the_first(self):
        self.make(*OVER_25)
        self.view("before-you-go", "types-and-prices")
        self.assertEqual(self.state().done, {AUDIOGRAM, "before-you-go", "types-and-prices"})
        self.assertEqual(self.state().stop, "assessment")

    def test_only_before_you_go_and_types_and_prices_are_done_by_viewing(self):
        self.make(*OVER_25)
        self.view("before-you-go", "assessment", "form-9", "after-fitting", "form-25")
        self.assertEqual(self.state().done, {AUDIOGRAM, "before-you-go"})
        self.assertEqual(self.state().stop, "assessment")

    # 12
    def test_wearing_by_the_latest_questionnaire_is_here_after_fitting(self):
        self.make(PTA_55, PTA_55)
        self.answer(wearing=True)
        self.assertEqual(self.state().stop, "after-fitting")
        self.assertEqual(self.state().done, {AUDIOGRAM})

    def test_an_ioi_ha_as_the_latest_counts_as_wearing(self):
        self.answer(wearing=False, day=1)
        self.answer(day=2, questionnaire=Questionnaire.objects.create(code=ioi_ha.CODE))
        self.assertEqual(self.state().stop, "after-fitting")

    def test_wearing_without_an_audiogram_is_still_after_fitting(self):
        self.answer(wearing=True)
        self.assertEqual(self.state().stop, "after-fitting")

    def test_wearing_with_both_ears_within_25_is_still_after_fitting(self):
        self.make(*WITHIN_25)
        self.answer(wearing=True)
        self.assertEqual(self.state().stop, "after-fitting")

    def test_wearing_keeps_the_stops_already_done(self):
        self.answer(wearing=True)
        self.view("types-and-prices")
        self.assertEqual(self.state().done, {"types-and-prices"})
        self.assertEqual(self.state().stop, "after-fitting")

    # 19
    def test_a_later_record_does_not_undo_a_viewed_stop(self):
        self.make(*OVER_25)
        self.view("before-you-go", "types-and-prices")
        self.make(PTA_55, PTA_55, tested_on=date(2026, 10, 20))
        self.answer(wearing=True, day=21)
        self.assertLessEqual({"before-you-go", "types-and-prices"}, self.state().done)
