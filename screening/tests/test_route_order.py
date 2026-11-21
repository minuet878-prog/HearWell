"""#743 (spec #741, ADR 0074): the 選配路線 in its new order, the home page passing by 助聽器的種類
與價格, 配戴之後 done with a first IOI-HA, the certificate's answers reworded, and 看過指引頁
kept with the chapter views."""

import json
from datetime import date, datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.care_journey import care_journey
from screening.fitting_route import GUIDE_PAGE, fitting_state
from screening.models import (
    AidAndSubsidy,
    AidLevel,
    ApprovedEars,
    Certificate,
    GuideChapterView,
    Questionnaire,
    Submission,
    Subsidy,
)
from screening.questionnaires import hhie_s, ioi_ha
from screening.tests import test_guide_summary
from screening.tests.helpers import consented_user, route_stops
from screening.tests.test_route_answers import answer_buttons

PTA_55 = test_guide_summary.PTA_55
TODAY = date(2026, 11, 21)
HERE, DONE = "您在這裡", "已完成"
# Spec #741 acceptance 31, word for word.
NINE = (
    "audiogram",
    "assessment",
    "form-9",
    "notice",
    "before-you-go",
    "types-and-prices",
    "after-fitting",
    "form-25",
    "payout",
)
# Folded (ADR 0063): the same order without the four 補助站.
FIVE = ("audiogram", "assessment", "before-you-go", "types-and-prices", "after-fitting")


class RouteOrderTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code=ioi_ha.CODE)

    def setUp(self):
        self.user = consented_user(username="route_order_user", birth_year=1950)
        self.client.force_login(self.user)

    make = test_guide_summary.GuideSummaryTests.make

    def submit(self, questionnaire, on, wearing=False):
        submission = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        moment = timezone.make_aware(datetime(on.year, on.month, on.day, 12))
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)

    def aid(self, **answers):
        AidAndSubsidy.objects.update_or_create(user=self.user, defaults=answers)

    def notice_done(self, **more):
        self.aid(
            certificate=Certificate.YES,
            form_9_done=True,
            notice_received=True,
            approved_ears=ApprovedEars.BOTH,
            level=AidLevel.MID,
            **more,
        )

    def stops(self):
        return route_stops(self.client.get(reverse("guide")).content.decode())

    def marks(self):
        """The marks each stop on my guide carries, by slug."""
        return {
            slug: [m for m in (DONE, HERE) if f">{m}<" in markup] for slug, markup in self.stops()
        }

    def guide_here(self):
        return [slug for slug, marks in self.marks().items() if HERE in marks]


class RouteOrderPageTests(RouteOrderTestCase):
    # Acceptance 31
    def test_my_guide_lists_the_nine_stops_in_the_new_order(self):
        self.aid(certificate=Certificate.YES)
        self.assertEqual(tuple(slug for slug, _ in self.stops()), NINE)

    def test_folded_my_guide_keeps_the_order_without_the_subsidy_stops(self):
        for signed_in in (True, False):
            with self.subTest(signed_in=signed_in):
                if not signed_in:
                    self.client.logout()
                self.assertEqual(tuple(slug for slug, _ in self.stops()), FIVE)

    def test_after_the_audiogram_the_route_asks_for_the_certificate_first(self):
        self.submit(self.hhie_s, TODAY)
        self.make(PTA_55, PTA_55)
        self.assertEqual(fitting_state(self.user, TODAY).stop, "assessment")


class HomeSkipsTypesAndPricesTests(RouteOrderTestCase):
    def setUp(self):
        super().setUp()
        self.submit(self.hhie_s, TODAY)
        self.make(PTA_55, PTA_55)
        # My guide opened, so the 照顧旅程's step 4 is done and its card is the route's (#744).
        GuideChapterView.objects.create(user=self.user, chapter=GUIDE_PAGE)

    # Acceptance 17
    def test_the_notice_done_both_are_at_before_you_go(self):
        self.notice_done()
        self.assertEqual(care_journey(self.user, TODAY).card.title, "去找聽力師之前")
        self.assertEqual(self.guide_here(), ["before-you-go"])

    # Acceptance 18
    def test_notice_not_yet_and_types_and_prices_read_is_done_on_my_guide(self):
        self.aid(certificate=Certificate.YES, form_9_done=True, notice_received=False)
        self.client.get(reverse("guide_chapter", args=["types-and-prices"]))
        self.assertEqual(self.marks()["types-and-prices"], [DONE])

    # Acceptance 19
    def test_my_guide_at_types_and_prices_the_home_page_says_after_fitting(self):
        self.notice_done()
        self.client.get(reverse("guide_chapter", args=["before-you-go"]))
        self.assertEqual(self.guide_here(), ["types-and-prices"])
        card = care_journey(self.user, TODAY).card
        self.assertEqual(card.title, "配戴助聽器之後")


class AfterFittingNeedsIoiHaTests(RouteOrderTestCase):
    """配戴之後 (spec #741 acceptance 22's groundwork): the fitting date and an IOI-HA from it."""

    def setUp(self):
        super().setUp()
        self.aid(fitted_on=date(2026, 11, 1), subsidy=Subsidy.OTHER)

    def state(self):
        return fitting_state(self.user, TODAY)

    def test_the_date_alone_leaves_after_fitting_here(self):
        self.assertNotIn("after-fitting", self.state().done)
        self.assertEqual(self.state().stop, "after-fitting")

    def test_an_ioi_ha_before_the_fitting_date_does_not_count(self):
        self.submit(self.ioi_ha, date(2026, 10, 31))
        self.assertNotIn("after-fitting", self.state().done)

    def test_an_ioi_ha_from_the_fitting_date_on_makes_it_done(self):
        self.submit(self.ioi_ha, date(2026, 11, 1))
        self.assertIn("after-fitting", self.state().done)

    def test_an_ioi_ha_without_a_fitting_date_is_not_done(self):
        self.aid(fitted_on=None)
        self.submit(self.ioi_ha, date(2026, 11, 1))
        self.assertNotIn("after-fitting", self.state().done)


class CertificateWordingTests(RouteOrderTestCase):
    # Acceptance 32
    def test_the_chapter_offers_yes_applying_and_no_and_keeps_the_values(self):
        page = self.client.get(reverse("guide_chapter", args=["assessment"])).content.decode()
        self.assertEqual(
            answer_buttons(page, "certificate"),
            [("yes", "有", False), ("applying", "正在申請", False), ("no_subsidy", "沒有", False)],
        )
        self.client.post(
            reverse("route_answer"),
            {"stop": "assessment", "certificate": "applying", "next": "/guide/assessment"},
        )
        self.assertEqual(AidAndSubsidy.for_user(self.user).certificate, "applying")


class GuidePageViewedTests(RouteOrderTestCase):
    """看過指引頁 (spec #741 實作決定): kept with the chapter views, and so in the download."""

    def viewed(self):
        response = self.client.get(reverse("download_my_data"))
        return json.loads(response.content)["aid_and_subsidy"]["viewed_chapters"]

    def test_opening_my_guide_signed_in_is_kept_once_by_the_page_s_name(self):
        self.client.get(reverse("guide"))
        self.client.get(reverse("guide"))
        self.assertEqual([v["chapter"] for v in self.viewed()], ["助聽器選配與補助"])

    def test_before_agreeing_to_the_privacy_notice_nothing_is_kept(self):
        self.user.consents.all().delete()
        self.client.get(reverse("guide"))
        self.user.give_consent()
        self.assertEqual(self.viewed(), [])
