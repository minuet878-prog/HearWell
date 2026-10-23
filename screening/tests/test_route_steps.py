from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.fitting_route import AUDIOGRAM, fitting_state
from screening.models import AidAndSubsidy, Consent, GuideChapterView, Questionnaire, User
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

    def test_signed_in_without_the_current_consent_records_nothing(self):
        only_first = User.objects.create_user(username="first_version_reader")
        Consent.objects.create(user=only_first, version=1)
        never = User.objects.create_user(username="never_consented_reader")
        for user in (only_first, never):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(self.open("before-you-go").status_code, 200)
                self.assertEqual(self.viewed(user), [])

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
        AidAndSubsidy.objects.create(user=self.user, certificate="applying")
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

    def test_changing_an_answer_does_not_undo_a_viewed_stop(self):
        self.make(*OVER_25)
        self.view("before-you-go")
        AidAndSubsidy.objects.create(user=self.user, certificate="yes")
        AidAndSubsidy.objects.filter(user=self.user).update(certificate="applying")
        self.assertIn("before-you-go", self.state().done)


class CertificateStopTests(TestCase):
    """#293 (spec #291 acceptance 7): 身障鑑定與鑑定醫院 is done by the certificate answer; not
    applying makes the subsidy's stops 不適用, and 您在這裡 passes them by."""

    def setUp(self):
        self.user = consented_user(username="certificate_user")
        self.make(*OVER_25)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")

    make = test_guide_summary.GuideSummaryTests.make

    def state(self, certificate=None):
        if certificate is not None:
            AidAndSubsidy.objects.update_or_create(
                user=self.user, defaults={"certificate": certificate}
            )
        return fitting_state(self.user, TODAY)

    def test_having_one_is_done_and_moves_on_to_form_9(self):
        state = self.state("yes")
        self.assertIn("assessment", state.done)
        self.assertEqual(state.stop, "form-9")
        self.assertEqual(state.not_applicable, frozenset())

    def test_applying_stays_at_the_assessment(self):
        state = self.state("applying")
        self.assertNotIn("assessment", state.done)
        self.assertEqual(state.stop, "assessment")
        self.assertEqual(state.not_applicable, frozenset())

    def test_unanswered_stays_at_the_assessment(self):
        state = self.state("")
        self.assertNotIn("assessment", state.done)
        self.assertEqual(state.stop, "assessment")

    def test_not_applying_is_done_and_the_subsidy_s_stops_do_not_apply(self):
        state = self.state("no_subsidy")
        self.assertIn("assessment", state.done)
        self.assertEqual(state.not_applicable, {"form-9", "notice", "form-25", "payout"})
        self.assertEqual(state.stop, "types-and-prices")

    def test_not_applying_with_types_and_prices_read_moves_on_to_after_fitting(self):
        GuideChapterView.objects.create(user=self.user, chapter="types-and-prices")
        self.assertEqual(self.state("no_subsidy").stop, "after-fitting")

    def test_wearing_and_not_applying_passes_form_25_and_the_payout_by(self):
        AidAndSubsidy.objects.create(
            user=self.user, certificate="no_subsidy", fitted_on=date(2026, 5, 1), subsidy="other"
        )
        state = self.state()
        self.assertLessEqual({"form-25", "payout"}, state.not_applicable)
        self.assertIsNone(state.stop)

    def test_changing_back_to_applying_undoes_it(self):
        self.state("no_subsidy")
        state = self.state("applying")
        self.assertNotIn("assessment", state.done)
        self.assertEqual(state.not_applicable, frozenset())
        self.assertEqual(state.stop, "assessment")


class PurchaseReminderTests(TestCase):
    """#294 (spec #291 acceptance 10, Q12): 種類與價格 always says the six months to buy in;
    the notice's date is not asked."""

    REMINDER = '<p class="route-note">收到核定通知後 6 個月內要買。</p>'

    def stop(self):
        content = self.client.get(reverse("guide")).content.decode()
        start = content.index('data-stop="types-and-prices"')
        return content[start : content.index("</li>", start)]

    def test_signed_in_or_out_the_stop_says_it(self):
        self.assertIn(self.REMINDER, self.stop())
        self.client.force_login(consented_user(username="reminder_user"))
        self.assertIn(self.REMINDER, self.stop())


class Form9AndNoticeStopTests(TestCase):
    """#294 (spec #291 acceptance 8, 9): 九號表 is done by 完成了; 等待核定公文 by 收到了 with
    單耳 or 雙耳 and the level both answered. 還沒 stays."""

    def setUp(self):
        self.user = consented_user(username="form_9_user")
        self.make(*OVER_25)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")

    make = test_guide_summary.GuideSummaryTests.make

    def state(self, **answers):
        AidAndSubsidy.objects.update_or_create(
            user=self.user, defaults={"certificate": "yes", **answers}
        )
        return fitting_state(self.user, TODAY)

    def test_with_a_certificate_and_form_9_unanswered_here_is_form_9(self):
        self.assertEqual(self.state().stop, "form-9")

    def test_form_9_not_yet_stays_at_form_9(self):
        state = self.state(form_9_done=False)
        self.assertNotIn("form-9", state.done)
        self.assertEqual(state.stop, "form-9")

    def test_form_9_done_is_done_and_moves_on_to_the_notice(self):
        state = self.state(form_9_done=True)
        self.assertIn("form-9", state.done)
        self.assertEqual(state.stop, "notice")

    def test_notice_not_yet_or_received_alone_stays_at_the_notice(self):
        for answers in (
            {"notice_received": False},
            {"notice_received": True},
            {"notice_received": True, "approved_ears": "both"},
            {"notice_received": True, "level": "mid"},
        ):
            with self.subTest(**answers):
                AidAndSubsidy.objects.filter(user=self.user).delete()
                state = self.state(form_9_done=True, **answers)
                self.assertNotIn("notice", state.done)
                self.assertEqual(state.stop, "notice")

    def test_received_with_the_ears_and_the_level_is_done(self):
        state = self.state(
            form_9_done=True, notice_received=True, approved_ears="one", level="basic"
        )
        self.assertIn("notice", state.done)
        self.assertEqual(state.stop, "types-and-prices")

    def test_the_notice_done_out_of_order_is_done_and_here_stays_at_form_9(self):
        state = self.state(notice_received=True, approved_ears="both", level="mid")
        self.assertIn("notice", state.done)
        self.assertEqual(state.stop, "form-9")

    def test_an_answer_at_form_9_starts_the_route_within_25(self):
        self.user.audiograms.all().delete()
        GuideChapterView.objects.all().delete()
        self.make(*WITHIN_25)
        AidAndSubsidy.objects.create(user=self.user, form_9_done=False)
        self.assertEqual(fitting_state(self.user, TODAY).stop, "before-you-go")


class FittingStopTests(TestCase):
    """#295 (spec #291 acceptance 12, 13, Q9): 配戴之後 is done once a fitting date is filled
    in; from then on 您在這裡 looks only at 二十五號表 and 等待補助發放."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="fitting_stop_user")
        self.make(*OVER_25)

    make = test_guide_summary.GuideSummaryTests.make
    answer = test_fitting_route.CurrentStopTests.answer

    def state(self):
        return fitting_state(self.user, TODAY)

    def test_a_fitting_date_is_done_and_here_is_form_25_not_the_stops_before(self):
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 5, 1), subsidy="disability", level="mid"
        )
        state = self.state()
        self.assertEqual(state.done, {AUDIOGRAM, "after-fitting"})
        self.assertEqual(state.stop, "form-25")

    def test_wearing_by_the_questionnaire_without_a_date_stays_at_after_fitting(self):
        self.answer(wearing=True)
        AidAndSubsidy.objects.create(user=self.user, ear="both", subsidy="disability")
        state = self.state()
        self.assertNotIn("after-fitting", state.done)
        self.assertEqual(state.stop, "after-fitting")


class Form25AndPayoutStopTests(TestCase):
    """#296 (spec #291 acceptance 15, 16): who has to do form 25. 簡易型 passes it by to the
    payout; paying otherwise passes both by and leaves no stop once fitted."""

    def setUp(self):
        self.user = consented_user(username="form_25_stop_user")

    def state(self, **answers):
        AidAndSubsidy.objects.update_or_create(
            user=self.user, defaults={"fitted_on": date(2026, 5, 1), **answers}
        )
        return fitting_state(self.user, TODAY)

    def test_the_subsidy_at_these_levels_or_none_is_here_at_form_25(self):
        for level in ("mid", "advanced", "cros", "unknown", ""):
            with self.subTest(level=level):
                state = self.state(subsidy="disability", level=level)
                self.assertEqual(state.not_applicable, frozenset())
                self.assertEqual(state.stop, "form-25")

    def test_the_notice_at_a_level_is_here_at_form_25(self):
        state = self.state(notice_received=True, approved_ears="both", level="advanced")
        self.assertEqual(state.stop, "form-25")

    def test_the_subsidy_unanswered_without_the_notice_leaves_after_fitting_not_done(self):
        # Spec #291 Q16: an older record with the date alone is still at 配戴之後, and the
        # site does not guess form 25 is needed.
        state = self.state()
        self.assertNotIn("after-fitting", state.done)
        self.assertEqual(state.stop, "after-fitting")
        self.assertIsNone(state.form_25)

    def test_the_notice_needs_no_subsidy_answer_for_after_fitting(self):
        state = self.state(notice_received=True, approved_ears="both", level="mid")
        self.assertIn("after-fitting", state.done)

    def test_basic_passes_form_25_by_to_the_payout(self):
        state = self.state(subsidy="disability", level="basic")
        self.assertEqual(state.not_applicable, {"form-25"})
        self.assertEqual(state.stop, "payout")

    def test_paying_otherwise_passes_both_by_and_leaves_no_stop(self):
        state = self.state(subsidy="other")
        self.assertEqual(state.not_applicable, {"form-25", "payout"})
        self.assertIsNone(state.stop)

    def test_form_25_done_is_done_and_here_is_the_payout_never_done(self):
        state = self.state(subsidy="disability", level="mid", form_25_done=True)
        self.assertEqual(state.done, {"after-fitting", "form-25"})
        self.assertEqual(state.stop, "payout")

    def test_form_25_not_yet_stays_at_form_25(self):
        state = self.state(subsidy="disability", level="mid", form_25_done=False)
        self.assertNotIn("form-25", state.done)
        self.assertEqual(state.stop, "form-25")
