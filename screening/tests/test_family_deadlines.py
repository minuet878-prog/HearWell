"""#432 (spec #426): 期限試算, as the server sends it. Filling it in a real browser is in
e2e.main_flow.FamilyDeadlinesTest."""

import inspect
import re
from datetime import date
from itertools import pairwise
from unittest.mock import patch

from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from screening.family_deadlines import PASSED_NOTE, Deadline, deadlines
from screening.fitting_route import fitting_state
from screening.models import AidAndSubsidy, AidLevel, Submission, Subsidy, User
from screening.tests import test_family_zone, test_pages
from screening.tests.helpers import consented_user
from screening.views import family

TODAY = date(2026, 6, 15)
FORM_9_WORDS = "九號表有效到 {}（3 個月內有效）。請在這天以前到公所申請。"
NOTICE_WORDS = "購買並請款的期限：{}（收到核定通知後 6 個月內）。"
FORM_25_WORDS = (
    "二十五號表可以做的日期：{} 到 {}。買中階型、進階型或雙對側傳聲型要做，簡易型不需要二十五號表。"
)


class DeadlinesTests(SimpleTestCase):
    """Expected days are worked out by hand from the rules in batch-2-wording.md section 3."""

    def calculate(self, form_9_on=None, notice_on=None, fitted_on=None, today=TODAY):
        return deadlines(form_9_on, notice_on, fitted_on, today=today)

    def test_form_9_is_valid_for_three_months(self):
        self.assertEqual(
            self.calculate(form_9_on=date(2026, 6, 1)),
            (Deadline(FORM_9_WORDS.format("2026/09/01"), ""),),
        )

    def test_notice_gives_six_months_to_buy(self):
        self.assertEqual(
            self.calculate(notice_on=date(2026, 6, 1)),
            (Deadline(NOTICE_WORDS.format("2026/12/01"), ""),),
        )

    def test_fitting_gives_form_25_from_one_month_to_three_months(self):
        self.assertEqual(
            self.calculate(fitted_on=date(2026, 6, 1)),
            (Deadline(FORM_25_WORDS.format("2026/07/01", "2026/09/01"), ""),),
        )

    def test_all_three_in_the_order_they_are_asked(self):
        words = [
            result.words
            for result in self.calculate(
                form_9_on=date(2026, 6, 1), notice_on=date(2026, 6, 2), fitted_on=date(2026, 6, 3)
            )
        ]
        self.assertEqual(
            words,
            [
                FORM_9_WORDS.format("2026/09/01"),
                NOTICE_WORDS.format("2026/12/02"),
                FORM_25_WORDS.format("2026/07/03", "2026/09/03"),
            ],
        )

    def test_nothing_given_nothing_shown(self):
        self.assertEqual(self.calculate(), ())

    def test_a_day_the_later_month_lacks_becomes_its_last_day(self):
        # Form 9, three months on: 11/30 to 2/28, or 2/29 in a leap year.
        for start, expected in (
            (date(2026, 11, 30), "2027/02/28"),
            (date(2027, 11, 30), "2028/02/29"),
        ):
            with self.subTest(start=start):
                result = self.calculate(form_9_on=start, today=start)
                self.assertEqual(result[0].words, FORM_9_WORDS.format(expected))
        # The notice, six months on: 8/31 to 2/28.
        result = self.calculate(notice_on=date(2026, 8, 31), today=date(2026, 8, 31))
        self.assertEqual(result[0].words, NOTICE_WORDS.format("2027/02/28"))
        # Fitting, one month on: 1/31 to 2/28, or 2/29 in a leap year; three months on, 4/30.
        for start, first, last in (
            (date(2026, 1, 31), "2026/02/28", "2026/04/30"),
            (date(2028, 1, 31), "2028/02/29", "2028/04/30"),
        ):
            with self.subTest(start=start):
                result = self.calculate(fitted_on=start, today=start)
                self.assertEqual(result[0].words, FORM_25_WORDS.format(first, last))

    def test_a_deadline_before_today_has_passed(self):
        for day in (
            {"form_9_on": date(2026, 3, 14)},  # until 6/14
            {"notice_on": date(2025, 12, 14)},  # until 6/14
            {"fitted_on": date(2026, 3, 14)},  # form 25 until 6/14
        ):
            with self.subTest(day=day):
                self.assertEqual(self.calculate(**day)[0].passed_note, PASSED_NOTE)

    def test_a_deadline_on_today_has_not_passed(self):
        for day in (
            {"form_9_on": date(2026, 3, 15)},  # until 6/15
            {"notice_on": date(2025, 12, 15)},  # until 6/15
            {"fitted_on": date(2026, 3, 15)},  # form 25 until 6/15
        ):
            with self.subTest(day=day):
                self.assertEqual(self.calculate(**day)[0].passed_note, "")

    # Its first day gone by, form 25 can still be done until its last.
    def test_form_25_is_judged_by_its_last_day(self):
        result = self.calculate(fitted_on=date(2026, 4, 1))  # 5/1 to 7/1
        self.assertEqual(result[0].passed_note, "")

    def test_only_the_passed_one_says_so(self):
        results = self.calculate(form_9_on=date(2026, 1, 1), notice_on=date(2026, 6, 1))
        self.assertEqual([result.passed_note for result in results], [PASSED_NOTE, ""])

    def test_the_passed_words_are_the_drafts(self):
        self.assertEqual(PASSED_NOTE, "這個日期已過，請向公所或聽力師確認。")


class SameDaysAsTheRouteTests(TestCase):
    """The route and the page work form 25 out of one rule: the same day, the same dates."""

    def test_page_and_route_give_form_25_the_same_days(self):
        user = consented_user(username="deadlines_route")
        AidAndSubsidy.objects.create(
            user=user,
            fitted_on=date(2026, 1, 31),
            subsidy=Subsidy.DISABILITY,
            level=AidLevel.MID,
        )
        route = fitting_state(user, TODAY).form_25
        self.assertEqual(route, (date(2026, 2, 28), date(2026, 4, 30)))
        response = self.client.post(reverse("family_deadlines"), {"fitted_on": "2026-01-31"})
        self.assertContains(response, FORM_25_WORDS.format("2026/02/28", "2026/04/30"))


class FamilyDeadlinesPageTests(test_family_zone.SignsInWithARecord, TestCase):
    def setUp(self):
        self.url = reverse("family_deadlines")
        real_localdate = timezone.localdate

        def localdate(value=None, timezone=None):
            return TODAY if value is None else real_localdate(value, timezone)

        self.enterContext(patch("django.utils.timezone.localdate", localdate))

    def get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response

    def post(self, **dates):
        response = self.client.post(self.url, dates)
        self.assertEqual(response.status_code, 200)
        return response

    def main(self, response):
        return test_family_zone._main(response.content.decode())

    def text(self, response):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", self.main(response)))

    def field(self, response, name):
        return re.search(rf'<input[^>]*name="{name}"[^>]*>', self.main(response)).group()

    def summary(self, response):
        found = re.search(r'<div id="error-summary"[^>]*>.*?</div>', self.main(response), re.S)
        return found.group() if found else None

    def test_address_is_under_the_visits_page(self):
        self.assertEqual(self.url, "/family/visits/deadlines")

    def test_page_has_one_heading_its_title_and_the_learn_tab(self):
        content = self.get().content.decode()
        self.assertEqual(re.findall(r"<h1[^>]*>([^<]*)</h1>", content), ["期限試算"])
        self.assertRegex(content, r"<title>\s*期限試算｜聽伴\s*</title>")  # noqa: RUF001
        nav = test_pages.RedesignLayoutTests.NAV.search(content).group()
        self.assertEqual(
            re.findall(r'aria-current="page"[^>]*>.*?<span>([^<]+)</span>', nav, re.S),
            ["了解"],
        )

    def test_headings_never_skip_a_level_with_results_or_without(self):
        for response in (self.get(), self.post(form_9_on="2026-06-01")):
            levels = [int(level) for level in re.findall(r"<h([1-6])[\s>]", self.main(response))]
            self.assertEqual(levels[0], 1)
            for previous, level in pairwise(levels):
                self.assertLessEqual(level, previous + 1)

    def test_the_form_asks_three_optional_dates_each_with_its_label(self):
        response = self.get()
        self.assertIn("輸入手上有的日期，只填一個也可以。日期不會留下來。", self.text(response))
        main = self.main(response)
        for name, label in (
            ("form_9_on", "九號表開立日期"),
            ("notice_on", "收到核定通知日期"),
            ("fitted_on", "開始配戴日期"),
        ):
            with self.subTest(name=name):
                field = self.field(response, name)
                self.assertIn('type="date"', field)
                self.assertNotIn("required", field)
                self.assertRegex(main, rf'<label[^>]*for="id_{name}"[^>]*>{label}</label>')
        self.assertRegex(main, r"<button[^>]*>試算</button>")

    def test_way_back_to_the_zone(self):
        self.assertRegex(self.main(self.get()), r'<a [^>]*href="/family"[^>]*>回到家人專區</a>')

    def test_foot_has_sources_and_checked_date(self):
        main = self.main(self.get())
        foot = main[main.index('id="sources-title"') :]
        self.assertIn("內容查核於 2026/10/22。", foot)
        self.assertIn("身心障礙者輔具費用補助辦法", foot)
        self.assertIn("身心障礙者輔具費用補助基準表", foot)

    def test_before_trying_there_is_nothing_to_print(self):
        response = self.get()
        self.assertNotIn("print-button", response.content.decode())
        self.assertNotIn("試算結果", self.main(response))

    def test_one_date_shows_only_its_deadline_and_no_error(self):
        for name, shown, others in (
            ("form_9_on", FORM_9_WORDS.format("2026/09/01"), ("購買並請款", "二十五號表可以做")),
            ("notice_on", NOTICE_WORDS.format("2026/12/01"), ("九號表有效到", "二十五號表可以做")),
            (
                "fitted_on",
                FORM_25_WORDS.format("2026/07/01", "2026/09/01"),
                ("九號表有效到", "購買並請款"),
            ),
        ):
            with self.subTest(name=name):
                response = self.post(**{name: "2026-06-01"})
                text = self.text(response)
                self.assertIn(shown, text)
                for other in others:
                    self.assertNotIn(other, text)
                self.assertIsNone(self.summary(response))
                self.assertNotIn("text-danger", self.main(response))

    def test_results_end_with_the_closing_note(self):
        self.assertIn(
            "這裡只幫忙算日期，實際期限以主管機關的通知為準。",
            self.text(self.post(form_9_on="2026-06-01")),
        )

    def test_a_passed_deadline_says_so_beside_it(self):
        text = self.text(self.post(form_9_on="2026-01-01", notice_on="2026-06-01"))
        self.assertEqual(text.count(PASSED_NOTE), 1)
        self.assertLess(text.index("九號表有效到"), text.index(PASSED_NOTE))
        self.assertLess(text.index(PASSED_NOTE), text.index("購買並請款"))

    def test_results_stay_above_the_form_which_keeps_the_dates(self):
        response = self.post(form_9_on="2026-06-01")
        main = self.main(response)
        self.assertLess(main.index("試算結果"), main.index("<form"))
        self.assertIn('value="2026-06-01"', self.field(response, "form_9_on"))

    def test_results_bring_the_print_button_and_its_script(self):
        response = self.post(form_9_on="2026-06-01")
        self.assertRegex(
            self.main(response),
            r'<p class="[^"]*no-print[^"]*">\s*'
            r'<button id="print-button" type="button"[^>]*>列印或存成 PDF</button>',
        )
        self.assertIn("screening/print-button.js", response.content.decode())

    def test_all_blank_is_an_error_for_the_whole_form(self):
        for response in (self.post(), self.post(form_9_on="", notice_on="", fitted_on="")):
            self.assertIn("請至少填一個日期。", self.summary(response))
            self.assertNotIn("試算結果", self.main(response))
            self.assertNotIn("print-button", response.content.decode())

    def test_a_wrong_date_is_an_error_and_every_date_typed_stays(self):
        for wrong in ("not-a-date", "2026-02-30", "2026-13-01"):
            with self.subTest(wrong=wrong):
                response = self.post(form_9_on=wrong, notice_on="2026-06-01")
                summary = self.summary(response)
                self.assertIn("請輸入正確的日期。", summary)
                self.assertRegex(summary, r'<a href="#id_form_9_on">九號表開立日期</a>')
                self.assertIn(f'value="{wrong}"', self.field(response, "form_9_on"))
                self.assertIn('value="2026-06-01"', self.field(response, "notice_on"))
                self.assertNotIn("試算結果", self.main(response))

    def test_a_future_date_is_an_error_and_today_is_not(self):
        response = self.post(fitted_on="2026-06-16", form_9_on="2026-06-01")
        self.assertIn("這個日期不能是未來。", self.summary(response))
        self.assertIn('value="2026-06-16"', self.field(response, "fitted_on"))
        self.assertIn('value="2026-06-01"', self.field(response, "form_9_on"))
        self.assertNotIn("試算結果", self.main(response))
        response = self.post(fitted_on="2026-06-15")
        self.assertIsNone(self.summary(response))
        self.assertIn("二十五號表可以做的日期", self.text(response))

    # Adding months to the last day there is would go past what a date can hold.
    def test_the_last_date_there_is_is_only_a_future_date(self):
        for name in ("form_9_on", "notice_on", "fitted_on"):
            with self.subTest(name=name):
                response = self.post(**{name: "9999-12-31"})
                self.assertIn("這個日期不能是未來。", self.summary(response))

    def test_errors_take_the_focus_and_mark_the_field(self):
        response = self.post(form_9_on="not-a-date")
        tag = re.search(r'<div id="error-summary"[^>]*>', self.main(response)).group()
        self.assertIn('role="alert"', tag)
        self.assertIn('tabindex="-1"', tag)
        self.assertIn("autofocus", tag)
        field = self.field(response, "form_9_on")
        self.assertIn('aria-invalid="true"', field)
        self.assertIn('aria-describedby="id_form_9_on_error"', field)
        self.assertIn('id="id_form_9_on_error"', self.main(response))

    def test_dates_go_by_post_and_never_come_back_in_a_link(self):
        self.assertRegex(
            self.main(self.get()), r'<form method="post" action="/family/visits/deadlines"'
        )
        response = self.post(form_9_on="2026-06-01")
        self.assertEqual(response.request["QUERY_STRING"], "")
        for href in re.findall(r'href="([^"]*)"', response.content.decode()):
            self.assertNotIn("2026-06-01", href)

    def test_trying_it_writes_nothing_and_keeps_nothing_in_a_session(self):
        before = (Submission.objects.count(), User.objects.count(), Session.objects.count())
        response = self.post(form_9_on="2026-06-01")
        self.post(form_9_on="not-a-date")
        self.assertEqual(
            (Submission.objects.count(), User.objects.count(), Session.objects.count()), before
        )
        self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)

    def test_no_response_is_ever_stored(self):
        for response in (
            self.get(),
            self.post(form_9_on="2026-06-01"),
            self.post(form_9_on="not-a-date"),
        ):
            self.assertIn("no-store", response.get("Cache-Control", ""))

    def test_view_never_reads_the_user(self):
        source = inspect.getsource(family.family_deadlines)
        self.assertNotIn("request.user", source)
        self.assertNotIn("login_required", source)

    def test_signed_in_user_gets_the_same_page_without_their_data(self):
        token = re.compile(r'<input type="hidden" name="csrfmiddlewaretoken"[^>]*>')
        visitor = token.sub("", self.main(self.post(form_9_on="2026-06-01")))
        self.sign_in_with_a_record("deadlines_private")
        response = self.post(form_9_on="2026-06-01")
        self.assertEqual(token.sub("", self.main(response)), visitor)
        self.assert_shows_no_record(response.content.decode(), "deadlines_private")

    def test_user_without_consent_can_open_and_send_it(self):
        self.client.force_login(User.objects.create_user(username="deadlines_old"))
        self.get()
        self.assertIn("九號表有效到", self.text(self.post(form_9_on="2026-06-01")))

    def test_a_visitor_sends_it_with_the_token_the_page_gave(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url, {"form_9_on": "2026-06-01"}).status_code, 403)
        client.get(self.url)
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(self.url, {"form_9_on": "2026-06-01", "csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 200)
        self.assertIn("九號表有效到", self.text(response))

    # This page's words have no use for 申請的人, so what can be checked is the words to avoid.
    def test_words_never_say_your_family_member(self):
        for response in (
            self.get(),
            self.post(form_9_on="2026-06-01", notice_on="2026-06-01", fitted_on="2026-06-01"),
            self.post(form_9_on="2020-01-01", notice_on="2020-01-01", fitted_on="2020-01-01"),
            self.post(form_9_on="not-a-date"),
            self.post(),
        ):
            self.assertNotIn("您的家人", self.main(response))


class FamilyDeadlinesEntryTests(TestCase):
    def setUp(self):
        response = self.client.get(reverse("family_visits"))
        self.main = test_family_zone._main(response.content.decode())

    def test_visits_page_has_the_entry_above_the_checklist(self):
        self.assertIn(
            ("/family/visits/deadlines", "clipboard", "期限試算", "輸入日期，算出期限"),
            test_family_zone.ENTRY.findall(self.main),
        )
        self.assertLess(self.main.index("/family/visits/deadlines"), self.main.index("陪診清單"))


class Form25ChapterLinkTests(TestCase):
    OPENING = "「二十五號表」是配戴助聽器後的使用效益驗證報告書（格式編號 25），核銷補助時要附上。"
    LINE = "想算出可以做的日期？可以用期限試算。"

    def setUp(self):
        response = self.client.get(reverse("guide_chapter", args=["form-25"]))
        self.main = test_family_zone._main(response.content.decode())

    def test_a_line_after_the_opening_leads_to_the_calculator(self):
        text = re.sub(r"<[^>]+>", "", self.main)
        self.assertLess(text.index(self.OPENING), text.index(self.LINE))
        self.assertLess(text.index(self.LINE), text.index("誰要做、怎麼做"))
        self.assertRegex(self.main, r'<a href="/family/visits/deadlines">期限試算</a>')

    def test_the_line_does_not_say_your_family_member(self):
        self.assertNotIn("您的家人", self.main)
