import re
from datetime import date, datetime
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import AidAndSubsidy, Questionnaire, Submission
from screening.questionnaires import hhie_s
from screening.tests import test_guide, test_guide_summary, test_route_steps
from screening.tests.helpers import consented_user

PTA_55 = test_guide_summary.PTA_55
# The route's nine stops in order (spec #291): recording an audiogram, then the chapters,
# with the two waits that have no chapter of their own.
STOPS = (
    ("audiogram", "記錄聽力圖"),
    ("before-you-go", "去找聽力師之前"),
    ("assessment", "身障鑑定與鑑定醫院"),
    ("form-9", "九號表：申請助聽器補助"),
    ("notice", "等待核定公文"),
    ("types-and-prices", "助聽器的種類與價格"),
    ("after-fitting", "配戴助聽器之後"),
    ("form-25", "二十五號表：使用效益驗證"),
    ("payout", "等待補助發放"),
)
# 等待核定公文 and 等待補助發放 link to form 9's 申請流程 (spec #291 Q15).
WAITS = ("notice", "payout")
DONE, HERE, BELOW, TOO_LITTLE = "已完成", "您在這裡", "估算未達門檻", "資料不足"
TAGS = (DONE, HERE, BELOW, TOO_LITTLE)


class GuideRouteTests(TestCase):
    """#258: 我的選配指引's 選配路線, each stop marked from the user's records."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="route_reader")
        self.client.force_login(self.user)

    make = test_guide_summary.GuideSummaryTests.make

    def answer(self, wearing=False):
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.hhie_s, wearing_hearing_aid=wearing
        )
        moment = timezone.make_aware(datetime(2026, 10, 2, 12))
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)

    def page(self):
        return self.client.get(reverse("guide")).content.decode()

    def stops(self):
        """Each stop's (slug, markup) in page order."""
        stop = r'<li class="route-stop[^"]*" data-stop="([^"]+)"[^>]*>(.*?)</li>'
        return re.findall(stop, self.page(), re.S)

    def stop(self, slug):
        return dict(self.stops())[slug]

    def tags(self):
        """The marks each stop carries, by slug."""
        return {slug: [t for t in TAGS if f">{t}<" in markup] for slug, markup in self.stops()}

    def assert_only_here_at(self, tags, slug):
        self.assertEqual([s for s, t in tags.items() if HERE in t], [slug])

    def assert_link(self, markup, href, text):
        self.assertRegex(markup, rf'<a [^>]*href="{re.escape(href)}"[^>]*>{re.escape(text)}</a>')

    def test_nine_stops_in_order_each_linked(self):
        self.client.logout()
        stops = self.stops()
        self.assertEqual([slug for slug, _ in stops], [slug for slug, _ in STOPS])
        for (slug, markup), (_, title) in zip(stops, STOPS, strict=True):
            if slug == "audiogram":
                href = reverse("audiogram_new")
            elif slug in WAITS:
                href = reverse("guide_chapter", args=["form-9"]) + "#steps-title"
            else:
                href = reverse("guide_chapter", args=[slug])
            with self.subTest(stop=slug):
                self.assert_link(markup, href, title)

    # 4, 5
    def test_chapters_read_signed_in_are_done_and_here_is_the_first_left(self):
        self.make(PTA_55, PTA_55)
        for slug in ("types-and-prices", "before-you-go"):
            self.client.get(reverse("guide_chapter", args=[slug]))
        tags = self.tags()
        self.assertEqual(tags["before-you-go"], [DONE])
        self.assertEqual(tags["types-and-prices"], [DONE])
        self.assert_only_here_at(tags, "assessment")
        assessment = reverse("guide_chapter", args=["assessment"])
        self.assert_link(self.stop("assessment"), assessment, "找鑑定醫院")

    # 3
    def test_within_25_reading_any_chapter_puts_here_on_the_route(self):
        self.make(*test_route_steps.WITHIN_25)
        self.client.get(reverse("guide_chapter", args=["form-9"]))
        self.assert_only_here_at(self.tags(), "before-you-go")

    # 26
    def test_there_is_no_aid_and_subsidy_card(self):
        self.make(PTA_55, PTA_55)
        self.assertNotIn("我的助聽器與補助", self.page())

    def test_signed_out_no_stop_is_marked(self):
        self.client.logout()
        self.assertEqual(self.tags(), {slug: [] for slug, _ in STOPS})
        self.assertNotIn('aria-current="step"', self.page())

    def test_without_an_audiogram_recording_one_is_here(self):
        self.answer()
        tags = self.tags()
        self.assertEqual(tags["audiogram"], [HERE])
        self.assertEqual(sum(t.count(HERE) for t in tags.values()), 1)
        self.assert_link(self.stop("audiogram"), reverse("audiogram_new"), "記錄醫院的聽力圖")
        self.assertRegex(self.page(), r'<li [^>]*data-stop="audiogram" aria-current="step"[^>]*>')

    def test_with_an_audiogram_recording_it_is_done_with_its_date(self):
        self.make((30, 30, 30, 30), (20, 20, 20, 20))
        tags = self.tags()
        self.assertEqual(tags["audiogram"], [DONE])
        self.assertIn("2026/10/01 的聽力圖", self.stop("audiogram"))
        self.assertEqual(sum(t.count(DONE) for t in tags.values()), 1)

    def test_an_ear_over_25_is_here_at_before_you_go(self):
        self.make((30, 30, 30, 30), (20, 20, 20, 20))
        tags = self.tags()
        self.assertEqual(tags["before-you-go"], [HERE])
        self.assertEqual(sum(t.count(HERE) for t in tags.values()), 1)
        before = reverse("guide_chapter", args=["before-you-go"])
        self.assert_link(self.stop("before-you-go"), before, "去之前要準備什麼")

    def test_not_reached_marks_the_assessment_and_links_to_other_subsidies(self):
        self.make((30, 30, 30, 30), (20, 20, 20, 20))
        self.assertEqual(self.tags()["assessment"], [BELOW])
        without = reverse("guide_chapter", args=["form-9"]) + "#without-certificate"
        self.assert_link(self.stop("assessment"), without, "看沒有身障證明時")

    def test_uncertain_leaves_the_assessment_unmarked(self):
        self.make((30, 30, 30, 30), (30, 30, 30, 30), no_response_at=("right", 4000))
        tags = self.tags()
        self.assertEqual(tags["assessment"], [])
        self.assert_only_here_at(tags, "before-you-go")
        self.assertNotIn("看沒有身障證明時", self.stop("assessment"))

    def test_reached_is_here_at_before_you_go_until_it_is_read(self):
        # Spec #291 default 4, in place of #257 Q5.
        self.make(PTA_55, PTA_55)
        tags = self.tags()
        self.assert_only_here_at(tags, "before-you-go")
        self.assertEqual(tags["assessment"], [])

    def test_an_audiogram_that_cannot_tell_is_here_with_too_little_data(self):
        audiogram = self.make((20, 20, 20, 20), (20, 20, 20, 20))
        audiogram.points.filter(ear="left", frequency=4000).delete()
        tags = self.tags()
        self.assertEqual(tags["audiogram"], [HERE, TOO_LITTLE])
        self.assert_only_here_at(tags, "audiogram")
        edit = reverse("audiogram_edit", args=[audiogram.pk])
        self.assert_link(self.stop("audiogram"), edit, "記錄聽力圖")
        self.assert_link(self.stop("audiogram"), edit, "修改這張聽力圖")

    def test_wearing_with_an_audiogram_that_cannot_tell_marks_too_little_data_only(self):
        self.answer(wearing=True)
        audiogram = self.make((20, 20, 20, 20), (20, 20, 20, 20))
        audiogram.points.filter(ear="left", frequency=4000).delete()
        tags = self.tags()
        self.assertEqual(tags["audiogram"], [TOO_LITTLE])
        self.assert_only_here_at(tags, "after-fitting")
        edit = reverse("audiogram_edit", args=[audiogram.pk])
        self.assert_link(self.stop("audiogram"), edit, "修改這張聽力圖")

    def test_wearing_is_here_after_fitting_and_form_9_links_to_reapplying(self):
        self.answer(wearing=True)
        self.make(PTA_55, PTA_55)
        tags = self.tags()
        self.assertEqual(tags["after-fitting"], [HERE])
        self.assertEqual(sum(t.count(HERE) for t in tags.values()), 1)
        record = reverse("guide_chapter", args=["after-fitting"]) + "#record-title"
        self.assert_link(self.stop("after-fitting"), record, "記錄配戴的效果")
        reapply = reverse("guide_chapter", args=["form-9"]) + "#reapply"
        self.assert_link(self.stop("form-9"), reapply, "看再次申請的規定")

    def test_not_wearing_has_no_reapplying_link_on_the_route(self):
        self.answer(wearing=False)
        self.make(PTA_55, PTA_55)
        self.assertNotIn("#reapply", self.stop("form-9"))

    def test_both_ears_within_25_have_no_stop_here(self):
        self.make((25, 25, 25, 25), (10, 10, 10, 10))
        tags = self.tags()
        self.assertEqual(sum(t.count(HERE) for t in tags.values()), 0)
        self.assertEqual(tags["audiogram"], [DONE])


class FittedOnRouteTests(TestCase):
    """#287 (spec #291 Q5): a fitting date counts as wearing hearing aids on the route too."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="fitted_on_reader")
        self.client.force_login(self.user)

    make = test_guide_summary.GuideSummaryTests.make
    answer = GuideRouteTests.answer
    page = GuideRouteTests.page
    stops = GuideRouteTests.stops
    tags = GuideRouteTests.tags
    assert_only_here_at = GuideRouteTests.assert_only_here_at

    def test_a_fitting_date_with_the_latest_answered_without_them_looks_on_from_it(self):
        self.make(PTA_55, PTA_55)
        self.answer(wearing=False)
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 5, 1))
        self.assert_only_here_at(self.tags(), "form-25")


class Form25DeadlineTests(TestCase):
    """#288: the form 25 stop dated from the fitting date (#296 turns it to spec #291's)."""

    def setUp(self):
        self.user = consented_user(username="form_25_reader")
        self.client.force_login(self.user)
        self.today = date(2026, 5, 20)
        real_localdate = timezone.localdate

        def localdate(value=None, timezone=None):
            return self.today if value is None else real_localdate(value, timezone)

        self.enterContext(patch("django.utils.timezone.localdate", localdate))

    page = GuideRouteTests.page
    stops = GuideRouteTests.stops
    stop = GuideRouteTests.stop

    def fit(self, fitted_on=date(2026, 5, 1), subsidy="disability", level="mid"):
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=fitted_on, subsidy=subsidy, level=level
        )

    def test_before_a_month_says_from_when_it_can_be_done(self):
        self.fit()
        self.assertIn("2026/06/01 起可以做", self.stop("form-25"))

    def test_from_a_month_to_three_says_by_when(self):
        self.fit()
        self.today = date(2026, 7, 15)
        form_25 = self.stop("form-25")
        self.assertIn("2026/08/01 前要做完", form_25)
        self.assertNotIn("起可以做", form_25)

    def test_the_wording_turns_on_the_boundary_days(self):
        self.fit()
        for today, wording in (
            (date(2026, 5, 31), "2026/06/01 起可以做"),
            (date(2026, 6, 1), "2026/08/01 前要做完"),
            (date(2026, 8, 1), "2026/08/01 前要做完"),
            (date(2026, 8, 2), "期限是 2026/08/01"),
        ):
            with self.subTest(today=today):
                self.today = today
                self.assertIn(f'<p class="route-note">{wording}</p>', self.stop("form-25"))

    def test_after_three_months_it_says_the_deadline_never_overdue_and_stays_here(self):
        # #296 (spec #291 acceptance 14): still at form 25, and its question can be answered.
        self.fit()
        self.today = date(2026, 8, 2)
        form_25 = self.stop("form-25")
        self.assertIn('<p class="route-note">期限是 2026/08/01</p>', form_25)
        self.assertNotIn("過期", form_25)
        self.assertNotIn("前要做完", form_25)
        self.assertIn('<span class="route-mark">您在這裡</span>', form_25)

    def test_basic_or_paying_has_no_form_25_date(self):
        self.today = date(2026, 7, 15)
        for subsidy, level in (("disability", "basic"), ("other", "")):
            with self.subTest(subsidy=subsidy, level=level):
                AidAndSubsidy.objects.filter(user=self.user).delete()
                self.fit(subsidy=subsidy, level=level)
                self.assertNotIn("2026/", self.stop("form-25"))

    def test_the_subsidy_unanswered_is_dated_as_if_it_had_to_be_done(self):
        # #296 (coordinator's decision): rather a reminder than none.
        self.fit(subsidy="", level="")
        self.assertIn("2026/06/01 起可以做", self.stop("form-25"))

    GAP = '<p class="route-gap">至少 1 個月</p>'

    def test_the_line_from_after_fitting_to_form_25_says_at_least_a_month(self):
        # #296 (spec #291 acceptance 14): on the line between the two stops, so at the end
        # of 配戴之後, after its box.
        self.fit()
        after_fitting = self.stop("after-fitting")
        self.assertIn(self.GAP, after_fitting)
        self.assertGreater(after_fitting.index(self.GAP), after_fitting.index("</div>"))
        self.assertEqual(self.page().count("route-gap"), 1)

    def test_signed_out_the_line_says_it_too(self):
        self.client.logout()
        self.assertIn(self.GAP, self.stop("after-fitting"))

    def test_without_form_25_the_line_says_nothing(self):
        for subsidy, level in (("disability", "basic"), ("other", "")):
            with self.subTest(subsidy=subsidy, level=level):
                AidAndSubsidy.objects.filter(user=self.user).delete()
                self.fit(subsidy=subsidy, level=level)
                self.assertNotIn("route-gap", self.page())

    def test_a_month_after_the_31st_is_the_last_day_of_february(self):
        self.fit(fitted_on=date(2026, 1, 31))
        self.today = date(2026, 2, 10)
        self.assertIn("2026/02/28 起可以做", self.stop("form-25"))


class ReapplyDateTests(TestCase):
    """#288 (spec #284 acceptance 17): the form 9 stop says when 身障補助 can be applied for
    again, without moving the 目前這一站."""

    def setUp(self):
        self.user = consented_user(username="reapply_reader")
        self.client.force_login(self.user)

    stops = GuideRouteTests.stops
    page = GuideRouteTests.page
    stop = GuideRouteTests.stop
    tags = GuideRouteTests.tags
    assert_only_here_at = GuideRouteTests.assert_only_here_at

    def test_the_subsidy_and_a_fitting_date_say_when_to_apply_again(self):
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 5, 1), subsidy="disability", level="mid"
        )
        self.assertIn("2030/05/01 起可以再申請補助", self.stop("form-9"))
        self.assert_only_here_at(self.tags(), "form-25")

    def test_four_years_after_29_february_shows_the_28th_in_2100(self):
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2096, 2, 29), subsidy="disability", level="basic"
        )
        self.assertIn("2100/02/28 起可以再申請補助", self.stop("form-9"))

    def test_paying_has_no_date_to_apply_again(self):
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 5, 1), subsidy="other")
        self.assertNotIn("起可以再申請補助", self.page())


class AidOnlyRecordsTests(TestCase):
    """Only 助聽器與補助資料, no questionnaire or audiogram: still records, so the page does
    not ask for them above a route that has a 目前這一站 (#284 review)."""

    def setUp(self):
        self.user = consented_user(username="aid_only_reader")
        self.client.force_login(self.user)

    def text(self):
        return test_guide.text_of(self.client.get(reverse("guide")))

    def test_any_answer_is_a_record(self):
        for fields in (
            {"certificate": "yes"},
            {"certificate": "applying"},
            {"certificate": "no_subsidy"},
            {"fitted_on": date(2026, 5, 1)},
            {"ear": "both"},
            {"subsidy": "other"},
        ):
            with self.subTest(**fields):
                AidAndSubsidy.objects.filter(user=self.user).delete()
                AidAndSubsidy.objects.create(user=self.user, **fields)
                text = self.text()
                self.assertNotIn(test_guide_summary.NO_RECORDS, text)
                self.assertNotIn(test_guide_summary.START, text)
                self.assertNotIn(test_guide_summary.NO_AUDIOGRAM, text)

    def test_a_row_left_unanswered_is_not_a_record(self):
        AidAndSubsidy.objects.create(user=self.user)
        self.assertIn(test_guide_summary.NO_RECORDS, self.text())
