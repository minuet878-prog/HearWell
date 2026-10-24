import re
from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening.models import AidAndSubsidy, GuideChapterView
from screening.tests import test_guide_summary
from screening.tests.helpers import consented_user

PTA_55 = test_guide_summary.PTA_55
STOP = r'<li class="route-stop[^"]*" data-stop="([^"]+)"[^>]*>(.*?)</li>'
TICK = '<svg class="route-tick"'


class RouteCheckmarkTests(TestCase):
    """#336 (spec #326 E5, acceptance 21): answering the 您在這裡 stop on the route so that it
    becomes 已完成 ticks it on the route the answer goes back to, once; a refresh, changing a
    done stop's answer, answering at a chapter's foot or a stop turning 不適用 tick nothing."""

    def setUp(self):
        # 您在這裡 is 身障鑑定與鑑定醫院: an audiogram reaching the threshold, 去找聽力師之前 read.
        self.user = consented_user(username="route_tick_user")
        self.client.force_login(self.user)
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")

    make = test_guide_summary.GuideSummaryTests.make

    def answer(self, stop="assessment", next_url=None, **data):
        data = {"stop": stop, "next": next_url or f"/guide#stop-{stop}", **data}
        return self.client.post(reverse("route_answer"), data)

    def page(self):
        return self.client.get(reverse("guide")).content.decode()

    def ticked(self, markup=None):
        """The stops showing the tick, in route order."""
        return [
            slug for slug, stop in re.findall(STOP, markup or self.page(), re.S) if TICK in stop
        ]

    def test_the_stop_just_done_is_ticked_not_the_new_you_are_here(self):
        self.answer(certificate="yes")
        page = self.page()
        self.assertEqual(self.ticked(page), ["assessment"])
        stops = dict(re.findall(STOP, page, re.S))
        self.assertNotIn(TICK, stops["form-9"])
        self.assertIn('data-stop="form-9" aria-current="step"', page)
        # The circle is green with the tick, and its number is still there for screen readers.
        self.assertRegex(page, r'<li class="route-stop is-done-now" data-stop="assessment"')
        self.assertRegex(
            stops["assessment"],
            r'<span class="route-number"><svg class="route-tick" aria-hidden="true" '
            r'focusable="false"[^>]*>.*?</svg><span class="visually-hidden">3</span></span>',
        )

    def test_a_refresh_shows_no_tick(self):
        self.answer(certificate="yes")
        self.assertEqual(self.ticked(), ["assessment"])
        self.assertEqual(self.ticked(), [])

    def test_changing_a_done_stop_s_answer_shows_no_tick(self):
        self.answer(certificate="yes")
        self.page()
        for certificate in ("yes", "no_subsidy"):
            with self.subTest(certificate=certificate):
                self.answer(certificate=certificate, next_url="/guide#stop-assessment")
                self.assertEqual(self.ticked(), [])

    def test_answering_at_the_chapter_s_foot_shows_no_tick(self):
        chapter = self.answer(certificate="yes", next_url="/guide/assessment#stop-question")
        self.assertRedirects(
            chapter, "/guide/assessment#stop-question", fetch_redirect_response=False
        )
        self.assertNotIn(TICK, self.client.get("/guide/assessment").content.decode())
        self.assertEqual(self.ticked(), [])

    def test_stops_turned_not_applicable_show_no_tick(self):
        # 不申請身障補助 makes 身障鑑定 done and the subsidy's four stops 不適用: only the first.
        self.answer(certificate="no_subsidy")
        self.assertEqual(self.ticked(), ["assessment"])

    def test_you_are_here_turning_not_applicable_shows_no_tick(self):
        # Wearing with 身障補助 at 中階型, 您在這裡 is 二十五號表; changing 配戴之後 to 自費或其他
        # makes it 不適用.
        AidAndSubsidy.objects.create(
            user=self.user,
            fitted_on=date(2026, 9, 1),
            ear="both",
            subsidy="disability",
            level="mid",
        )
        self.assertIn('data-stop="form-25" aria-current="step"', self.page())
        self.answer(stop="after-fitting", fitted_on="2026-09-01", ear="both", subsidy="other")
        page = self.page()
        self.assertRegex(page, r'<li class="route-stop is-na" data-stop="form-25"')
        self.assertEqual(self.ticked(page), [])

    def test_an_answer_that_leaves_the_stop_not_done_shows_no_tick(self):
        self.answer(certificate="applying")
        self.assertEqual(self.ticked(), [])

    def test_the_notice_is_ticked_only_by_its_last_answer(self):
        AidAndSubsidy.objects.filter(user=self.user).delete()
        AidAndSubsidy.objects.create(user=self.user, certificate="yes", form_9_done=True)
        for name, value, ticked in (
            ("notice_received", "True", []),
            ("approved_ears", "both", []),
            ("level", "mid", ["notice"]),
        ):
            with self.subTest(name=name):
                self.answer(stop="notice", **{name: value})
                self.assertEqual(self.ticked(), ticked)

    def test_a_stop_done_that_was_not_you_are_here_shows_no_tick(self):
        # Wearing, 您在這裡 is 配戴之後; 身障鑑定 answered on its own is done but was not here.
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 9, 1), ear="both")
        self.assertIn('data-stop="after-fitting" aria-current="step"', self.page())
        self.answer(certificate="yes")
        self.assertEqual(self.ticked(), [])

    def test_the_tick_does_not_outlive_logging_out(self):
        self.answer(certificate="yes")
        self.client.post(reverse("logout"))
        self.client.force_login(self.user)
        self.assertEqual(self.ticked(), [])

    def test_the_tick_does_not_pass_to_another_account(self):
        self.answer(certificate="yes")
        other = consented_user(username="route_tick_other_user")
        self.client.force_login(other)  # on the same browser, without logging out
        self.assertNotIn(TICK, self.page())
