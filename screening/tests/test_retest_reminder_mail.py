"""#663 (spec #656 acceptance 16-31, 43): the 重測提醒信, sent by the 09:00 schedule's
send_retest_reminders on the day a life-impact record falls due again."""

import json
import re
from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import requests
from anymail.exceptions import AnymailAPIError
from django.conf import settings
from django.core import mail
from django.core.mail.backends.locmem import EmailBackend
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.forms import HELP_ADDRESS
from screening.models import (
    GuestMonth,
    Questionnaire,
    RetestReminder,
    RetestReminderSent,
    Submission,
    User,
)
from screening.questionnaires import hhia_s, hhie_s, ioi_ha
from screening.tests.helpers import consented_user, submission_with_answers

TAIPEI = ZoneInfo("Asia/Taipei")
# 2026/05/17 + 6 months: a record made that day falls due on 2026/11/17.
ANSWERED_ON = date(2026, 5, 17)
DUE_ON = date(2026, 11, 17)
RETEST_LINK = r'<a href="([^"]*)"[^>]*>再做一次</a>'
COMMAND_LOGGER = "screening.management.commands.send_retest_reminders"
# Resend's default: 10 requests a second for the whole team, the password and feedback mails too
# (resend.com/docs/api-reference/rate-limit).
RESEND_PER_SECOND = 10
# The owner's subject, body and foot line, settled on 2026-11-17 (#658).
SUBJECT = "聽伴 重測提醒"
BODY = (
    "距離您上次在聽伴做聽力篩檢已經半年了。建議再做一次，看看這半年聽力對生活的影響有沒有變化，"
    "一共 10 題。"
)
FOOT = "您在聽伴打開了 email 重測提醒，所以收到這封信。不想再收到："


def at(day, hour=9):
    """That day at that hour, Taiwan time, as the present."""
    moment = datetime(day.year, day.month, day.day, hour, tzinfo=TAIPEI)
    return patch("django.utils.timezone.now", return_value=moment)


class FailingBackend(EmailBackend):
    """The mail service refuses fails@example.com, as Resend can; the rest go to the outbox."""

    def send_messages(self, messages):
        if messages[0].to[0] == "fails@example.com":
            raise OSError(f"Resend refused {messages[0].to[0]}")
        return super().send_messages(messages)


def resend_429(name):
    """Resend's 429 as anymail raises it: the JSON body names which limit it is (resend.com/docs/
    api-reference/errors)."""
    response = requests.Response()
    response.status_code = 429
    response.headers["Content-Type"] = "application/json"
    response._content = json.dumps({"statusCode": 429, "name": name, "message": name}).encode()
    return AnymailAPIError("Resend API response 429", status_code=429, response=response)


class QuotaBackend(EmailBackend):
    """Resend with `left` emails of the quota: then its 429 named `used_up`."""

    left = 0
    used_up = "daily_quota_exceeded"

    def send_messages(self, messages):
        if QuotaBackend.left == 0:
            raise resend_429(QuotaBackend.used_up)
        QuotaBackend.left -= 1
        return super().send_messages(messages)


class RateLimitedBackend(EmailBackend):
    """Resend says too many a second for slow@example.com; the rest go to the outbox."""

    def send_messages(self, messages):
        if messages[0].to[0] == "slow@example.com":
            raise resend_429("rate_limit_exceeded")
        return super().send_messages(messages)


@override_settings(SITE_URL="https://tingpal.test")
class ReminderMailTestCase(TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S

    def person(self, username, email=None, answered_on=ANSWERED_ON, on_since=ANSWERED_ON, **kw):
        """An account with its email 重測提醒 on since on_since and an HHIE-S record made at noon,
        Taiwan time, on answered_on (None: no record)."""
        email = f"{username}@example.com" if email is None else email
        user = consented_user(username=username, email=email, **kw)
        if answered_on is not None:
            self.answer(user, answered_on)
        RetestReminder.objects.create(user=user, enabled=True, enabled_on=on_since)
        return user

    def answer(self, user, on, code=hhie_s.CODE, score=0, hour=12):
        submission = submission_with_answers(user, code, [score] * 10)
        moment = datetime(on.year, on.month, on.day, hour, tzinfo=TAIPEI)
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def run_on(self, day, hour=9):
        """The schedule's run on that day: to whom it sent, in order. Its pauses are kept in
        self.pauses as (emails sent so far, seconds), not waited."""
        mail.outbox.clear()
        self.pauses = []
        with (
            at(day, hour),
            patch(
                f"{COMMAND_LOGGER}.sleep",
                side_effect=lambda seconds: self.pauses.append((len(mail.outbox), seconds)),
            ),
        ):
            call_command("send_retest_reminders", stdout=StringIO())
        return [message.to[0] for message in mail.outbox]

    def records(self):
        return list(
            RetestReminderSent.objects.order_by("user__username", "due_on").values_list(
                "user__username", "due_on", "attempts", "last_failed_on"
            )
        )


class WhenItIsSentTests(ReminderMailTestCase):
    # 16
    def test_sent_on_the_day_it_falls_due(self):
        self.person("due_today", email="mama@example.com")
        self.assertEqual(self.run_on(DUE_ON), ["mama@example.com"])
        (record,) = RetestReminderSent.objects.all()
        self.assertEqual(record.due_on, DUE_ON)
        self.assertEqual(record.attempts, 1)
        self.assertIsNotNone(record.sent_at)

    def test_the_due_day_is_the_taiwan_date_of_the_record(self):
        # 2026/05/31 23:30 in Taiwan is still the 31st's afternoon in UTC; + 6 months is 11/30.
        user = self.person("late_night", answered_on=None, on_since=date(2026, 5, 1))
        self.answer(user, date(2026, 5, 31), hour=23)
        self.assertEqual(self.run_on(date(2026, 11, 29)), [])
        self.assertEqual(self.run_on(date(2026, 11, 30)), ["late_night@example.com"])

    # 17
    def test_not_the_day_before(self):
        self.person("due_tomorrow")
        self.assertEqual(self.run_on(DUE_ON - timedelta(days=1)), [])
        self.assertFalse(RetestReminderSent.objects.exists())

    # 18
    def test_a_second_run_the_same_day_sends_nothing(self):
        self.person("run_twice")
        self.assertEqual(self.run_on(DUE_ON), ["run_twice@example.com"])
        self.assertEqual(self.run_on(DUE_ON, hour=15), [])
        self.assertEqual(RetestReminderSent.objects.count(), 1)

    # 19
    def test_never_again_for_the_same_due_day(self):
        self.person("not_redone")
        self.run_on(DUE_ON)
        for days in (1, 2, 30):
            with self.subTest(days=days):
                self.assertEqual(self.run_on(DUE_ON + timedelta(days=days)), [])

    # 20
    def test_done_again_after_the_reminder_falls_due_again(self):
        user = self.person("redone")
        self.run_on(DUE_ON)
        self.answer(user, date(2026, 11, 20))
        self.assertEqual(self.run_on(date(2027, 5, 19)), [])
        self.assertEqual(self.run_on(date(2027, 5, 20)), ["redone@example.com"])
        self.assertEqual(
            list(RetestReminderSent.objects.order_by("due_on").values_list("due_on", flat=True)),
            [DUE_ON, date(2027, 5, 20)],
        )

    # 21
    def test_done_again_early_moves_the_due_day_on(self):
        user = self.person("early")
        self.answer(user, date(2026, 11, 10))
        self.assertEqual(self.run_on(DUE_ON), [])
        self.assertEqual(self.run_on(date(2027, 5, 10)), ["early@example.com"])

    # 22
    def test_only_to_those_with_it_on_an_email_and_a_life_impact_record(self):
        self.person("gets_it")
        off = self.person("turned_off")
        RetestReminder.objects.filter(user=off).update(enabled=False, enabled_on=None)
        self.person("no_email", email="")
        self.person("deactivated", is_active=False)
        self.person("staff", is_staff=True)
        User.objects.create_superuser(username="owner", email="owner@example.com", password="pw")
        owner = User.objects.get(username="owner")
        self.answer(owner, ANSWERED_ON)
        RetestReminder.objects.create(user=owner, enabled=True, enabled_on=ANSWERED_ON)
        self.person("no_record", answered_on=None)
        self.assertEqual(self.run_on(DUE_ON), ["gets_it@example.com"])
        # Nothing for the others either: one without an email is not counted as sent.
        self.assertEqual([record[0] for record in self.records()], ["gets_it"])

    def test_not_for_another_questionnaire_s_record(self):
        # IOI-HA is not a life-impact questionnaire: it never falls due (ADR 0016).
        user = self.person("ioi_only", answered_on=None)
        submission = submission_with_answers(user, ioi_ha.CODE, [1] * 7)
        moment = datetime(2026, 5, 17, 12, tzinfo=TAIPEI)
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        self.assertEqual(self.run_on(DUE_ON), [])

    # 23
    def test_not_when_it_was_already_due_when_turned_on(self):
        self.person("on_too_late", on_since=DUE_ON + timedelta(days=1))
        self.assertEqual(self.run_on(DUE_ON + timedelta(days=1)), [])
        self.assertEqual(self.run_on(DUE_ON + timedelta(days=2)), [])

    def test_turned_on_the_day_it_falls_due_is_sent(self):
        self.person("on_that_day", on_since=DUE_ON)
        self.assertEqual(self.run_on(DUE_ON), ["on_that_day@example.com"])

    # 24
    def test_days_missed_are_sent_on_the_next_run(self):
        self.person("due_17th")
        self.person("due_18th", answered_on=date(2026, 5, 18))
        self.person("due_21st", answered_on=date(2026, 5, 21))
        self.assertEqual(
            self.run_on(date(2026, 11, 20)), ["due_17th@example.com", "due_18th@example.com"]
        )

    # 25
    def test_at_most_sixty_a_day(self):
        self.assertEqual(settings.RETEST_REMINDER_DAILY_LIMIT, 60)

    @override_settings(RETEST_REMINDER_DAILY_LIMIT=2)
    def test_over_the_limit_the_oldest_first_and_the_rest_the_next_day(self):
        self.person("due_17th")
        self.person("due_15th", answered_on=date(2026, 5, 15))
        self.person("due_16th", answered_on=date(2026, 5, 16))
        self.assertEqual(self.run_on(DUE_ON), ["due_15th@example.com", "due_16th@example.com"])
        self.assertEqual(self.run_on(DUE_ON + timedelta(days=1)), ["due_17th@example.com"])

    # 26
    def test_a_pause_between_each_one_within_resend_s_rate(self):
        self.person("due_15th", answered_on=date(2026, 5, 15))
        self.person("due_16th", answered_on=date(2026, 5, 16))
        self.person("due_17th")
        self.assertEqual(len(self.run_on(DUE_ON)), 3)
        self.assertEqual([sent for sent, _ in self.pauses], [1, 2])
        for _, seconds in self.pauses:
            # At most half of Resend's rate: the other mails share it.
            self.assertGreaterEqual(seconds, 2 / RESEND_PER_SECOND)

    def test_one_email_for_each_account_of_the_same_address(self):
        self.person("wang_mama", email="daughter@example.com")
        self.person("wang_baba", email="daughter@example.com")
        self.assertEqual(self.run_on(DUE_ON), ["daughter@example.com", "daughter@example.com"])
        bodies = sorted(message.body for message in mail.outbox)
        self.assertIn("wang_baba 您好", bodies[0])
        self.assertNotIn("wang_mama", bodies[0])
        self.assertIn("wang_mama 您好", bodies[1])
        self.assertNotIn("wang_baba", bodies[1])


class TheMailTests(ReminderMailTestCase):
    def setUp(self):
        self.user = self.person("wang_baba", email="baba@example.com")
        self.run_on(DUE_ON)
        (self.message,) = mail.outbox
        self.html = self.message.alternatives[0].content
        self.cancel_url = "https://tingpal.test" + reverse(
            "reminder_cancel", args=[RetestReminder.objects.get(user=self.user).cancel_token]
        )

    def retest_url(self):
        (url,) = set(re.findall(RETEST_LINK, self.html))
        return url

    # 27
    def test_text_and_html_with_the_username_and_both_links(self):
        self.assertEqual(self.message.alternatives[0].mimetype, "text/html")
        retest_url = self.retest_url()
        self.assertTrue(retest_url.startswith("https://tingpal.test/"))
        for body in (self.message.body, self.html):
            with self.subTest(body=body[:20]):
                self.assertIn("wang_baba 您好：", body)
                self.assertIn(retest_url, body)
                self.assertIn(self.cancel_url, body)
        self.assertIn(f'<a href="{self.cancel_url}"', self.html)

    # 27: the owner's words, the body between 您好 and 再做一次, 取消提醒 the foot's link.
    def test_the_owner_s_subject_body_and_foot_line(self):
        self.assertEqual(self.message.subject, SUBJECT)
        text = self.message.body
        self.assertLess(text.index("wang_baba 您好："), text.index(BODY))
        self.assertLess(text.index(BODY), text.index("再做一次"))
        self.assertIn(f"{FOOT}取消提醒\n{self.cancel_url}", text)
        self.assertLess(self.html.index("wang_baba 您好："), self.html.index(BODY))
        self.assertLess(self.html.index(BODY), re.search(RETEST_LINK, self.html).start())
        self.assertRegex(
            self.html, re.escape(f'{FOOT}<a href="{self.cancel_url}"') + "[^>]*>取消提醒</a>"
        )

    def test_from_the_site_replies_to_the_contact_address(self):
        self.assertEqual(self.message.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertTrue(settings.DEFAULT_FROM_EMAIL.startswith("聽伴 <"))
        self.assertEqual(self.message.to, ["baba@example.com"])
        self.assertEqual(self.message.reply_to, [HELP_ADDRESS])

    def test_one_click_cancel_headers(self):
        # RFC 8058: what Gmail and Outlook need to show 取消訂閱 and POST it themselves.
        self.assertEqual(self.message.extra_headers["List-Unsubscribe"], f"<{self.cancel_url}>")
        self.assertEqual(
            self.message.extra_headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click"
        )

    def test_the_cancel_header_turns_the_reminder_off(self):
        path = urlsplit(self.cancel_url).path
        self.client.post(path, {"List-Unsubscribe": "One-Click"})
        self.assertFalse(RetestReminder.objects.get(user=self.user).enabled)


class NoHealthDataTests(ReminderMailTestCase):
    # 27: no score or level, even the worst.
    def test_no_score_or_level(self):
        user = self.person("worst", answered_on=None)
        self.answer(user, ANSWERED_ON, score=4)  # 40, 顯著影響
        self.run_on(DUE_ON)
        (message,) = mail.outbox
        for body in (message.body, message.alternatives[0].content, message.subject):
            with self.subTest(body=body[:20]):
                # Not the bare 影響: the owner's body asks whether 聽力對生活的影響 has changed.
                levels = ("無／極輕微影響", "輕度到中度影響", "顯著影響")
                for health in (*levels, "40 分", "40分", "分數", "分級"):
                    self.assertNotIn(health, body)


class RetestLinkTests(ReminderMailTestCase):
    """28: signed out, the link signs in first, then opens the home page's 再做一次."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())  # HHIA-S

    def test_signs_in_then_opens_the_home_page_s_one(self):
        user = self.person("link_user", password="Fake-pass-1357")
        # HHIA-S after HHIE-S: the newer one is the one to do again (ADR 0030).
        self.answer(user, ANSWERED_ON, code=hhia_s.CODE, hour=13)
        hhia = Questionnaire.objects.get(code=hhia_s.CODE)
        self.run_on(DUE_ON)
        (message,) = mail.outbox
        html = message.alternatives[0].content
        (url,) = set(re.findall(RETEST_LINK, html))
        self.assertNotIn("utm_", url)
        retest = urlsplit(url)

        signed_out = self.client.get(f"{retest.path}?{retest.query}")
        login = urlsplit(signed_out["Location"])
        self.assertEqual(login.path, reverse("login"))
        (after_login,) = parse_qs(login.query)["next"]
        login_page = self.client.post(
            signed_out["Location"], {"username": "link_user", "password": "Fake-pass-1357"}
        )
        self.assertEqual(login_page["Location"], after_login)
        opened = self.client.get(after_login)
        self.assertEqual(opened["Location"], reverse("screening", args=[hhia.pk]))

        with at(DUE_ON):
            home = self.client.get(reverse("index")).content.decode()
        (home_retest,) = re.findall(r'class="journey-tile-link" href="([^"]*)">再做一次<', home)
        self.assertEqual(home_retest, opened["Location"])


class FailedSendTests(ReminderMailTestCase):
    """29: one that cannot go tells Sentry, without the address; the others go; tried again the
    next day, three days at most."""

    @override_settings(EMAIL_BACKEND=f"{__name__}.FailingBackend")
    def test_the_others_still_go_and_it_is_tried_three_days(self):
        self.person("fails", email="fails@example.com")
        self.person("goes", email="goes@example.com", answered_on=date(2026, 5, 17))
        with self.assertLogs(COMMAND_LOGGER, "ERROR") as logs:
            self.assertEqual(self.run_on(DUE_ON), ["goes@example.com"])
        (log,) = logs.records
        self.assertIsNotNone(log.exc_info)
        self.assertEqual(log.getMessage(), "A retest reminder could not be sent")
        self.assertEqual(log.args, ())
        self.assertNotIn("fails", log.getMessage())
        self.assertEqual(self.records(), [("fails", DUE_ON, 1, DUE_ON), ("goes", DUE_ON, 1, None)])

        with self.assertNoLogs(COMMAND_LOGGER, "ERROR"):
            self.run_on(DUE_ON, hour=15)  # the same day: not again
        self.assertEqual(self.records()[0], ("fails", DUE_ON, 1, DUE_ON))
        for days in (1, 2):
            day = DUE_ON + timedelta(days=days)
            with self.assertLogs(COMMAND_LOGGER, "ERROR"):
                self.run_on(day)
            self.assertEqual(self.records()[0], ("fails", DUE_ON, days + 1, day))

        with self.assertNoLogs(COMMAND_LOGGER, "ERROR"):
            self.run_on(DUE_ON + timedelta(days=3))  # given up: not tried a fourth day
        self.assertEqual(self.records()[0], ("fails", DUE_ON, 3, DUE_ON + timedelta(days=2)))

    @override_settings(EMAIL_BACKEND=f"{__name__}.RateLimitedBackend")
    def test_too_many_a_second_fails_that_one_and_the_others_go(self):
        # Resend's other 429: not the quota, so the day goes on and it is tried again tomorrow.
        self.person("slow", email="slow@example.com", answered_on=date(2026, 5, 15))
        self.person("goes", email="goes@example.com")
        with self.assertLogs(COMMAND_LOGGER, "ERROR"):
            self.assertEqual(self.run_on(DUE_ON), ["goes@example.com"])
        self.assertEqual(
            self.records(), [("goes", DUE_ON, 1, None), ("slow", date(2026, 11, 15), 1, DUE_ON)]
        )


@override_settings(EMAIL_BACKEND=f"{__name__}.QuotaBackend")
class QuotaUsedUpTests(ReminderMailTestCase):
    """30: Resend's quota for the day or the month used up stops the day's sending, none counted
    as failed."""

    def test_the_day_s_quota_the_rest_wait_for_the_next_day(self):
        self.the_rest_wait_for_the_next_day("daily_quota_exceeded")

    def test_the_month_s_quota_the_rest_wait_for_the_next_day(self):
        self.the_rest_wait_for_the_next_day("monthly_quota_exceeded")

    def the_rest_wait_for_the_next_day(self, used_up):
        QuotaBackend.used_up = used_up
        self.person("due_15th", answered_on=date(2026, 5, 15))
        self.person("due_16th", answered_on=date(2026, 5, 16))
        self.person("due_17th")
        QuotaBackend.left = 1
        with self.assertNoLogs(COMMAND_LOGGER, "ERROR"):
            self.assertEqual(self.run_on(DUE_ON), ["due_15th@example.com"])
        self.assertEqual(self.records(), [("due_15th", date(2026, 11, 15), 1, None)])
        QuotaBackend.left = 10
        self.assertEqual(
            self.run_on(DUE_ON + timedelta(days=1)),
            ["due_16th@example.com", "due_17th@example.com"],
        )
        self.assertEqual(GuestMonth.objects.get().reminders_sent, 3)


class MonthCountTests(ReminderMailTestCase):
    # 31
    @override_settings(EMAIL_BACKEND=f"{__name__}.FailingBackend")
    def test_each_one_sent_counts_in_its_taiwan_month_and_a_failed_one_does_not(self):
        # 07:00 on 2026/12/01 in Taiwan is still November in UTC.
        self.person("december", answered_on=date(2026, 6, 1))
        self.person("fails", email="fails@example.com", answered_on=date(2026, 6, 1))
        with self.assertLogs(COMMAND_LOGGER, "ERROR"):
            self.run_on(date(2026, 12, 1), hour=7)
        self.assertEqual(
            list(GuestMonth.objects.values_list("month", "reminders_sent", "completed")),
            [(date(2026, 12, 1), 1, 0)],
        )


class DeletedAccountTests(ReminderMailTestCase):
    # 43
    def test_deleting_the_account_deletes_what_was_sent_and_keeps_the_month_count(self):
        user = self.person("leaving")
        kept = self.person("staying")
        self.run_on(DUE_ON)
        user.delete_with_data()
        self.assertEqual(list(RetestReminderSent.objects.values_list("user", flat=True)), [kept.pk])
        self.assertEqual(GuestMonth.objects.get().reminders_sent, 2)


class SentAdminTests(ReminderMailTestCase):
    # 45: which due days were sent, to look at only.
    def test_the_admin_only_looks(self):
        self.person("looked_at")
        self.run_on(DUE_ON)
        record = RetestReminderSent.objects.get()
        self.client.force_login(User.objects.create_superuser(username="owner", password="pw"))
        changelist = reverse("admin:screening_retestremindersent_changelist")
        page = self.client.get(changelist).content.decode()
        headers = re.findall(r'<th scope="col" class="[^"]*column-(\w+)', page)
        self.assertEqual(headers, ["user", "due_on", "sent_at", "attempts", "last_failed_on"])
        self.assertIn("looked_at", page)
        self.assertNotIn("looked_at@example.com", page)
        change = reverse("admin:screening_retestremindersent_change", args=[record.pk])
        self.assertEqual(self.client.get(change).status_code, 200)
        add = reverse("admin:screening_retestremindersent_add")
        self.assertEqual(self.client.get(add).status_code, 403)
        self.assertEqual(self.client.post(change, {"attempts": 0}).status_code, 403)
        delete = reverse("admin:screening_retestremindersent_delete", args=[record.pk])
        self.assertEqual(self.client.post(delete, {"post": "yes"}).status_code, 403)
        self.assertEqual(RetestReminderSent.objects.get().attempts, 1)

    def test_two_or_many_take_the_same_queries(self):
        # CODING_STANDARDS 15: a row more each day something is sent.
        for number in range(2):
            self.person(f"two_{number}")
        self.run_on(DUE_ON)
        self.client.force_login(User.objects.create_superuser(username="owner", password="pw"))
        changelist = reverse("admin:screening_retestremindersent_changelist")
        self.client.get(changelist)  # the first request also looks up what the admin caches
        with CaptureQueriesContext(connection) as two:
            self.assertEqual(self.client.get(changelist).status_code, 200)
        for number in range(5):
            self.person(f"many_{number}")
        self.run_on(DUE_ON)
        self.assertEqual(RetestReminderSent.objects.count(), 7)
        with self.assertNumQueries(len(two)):
            self.assertEqual(self.client.get(changelist).status_code, 200)


class SameDueDayAsTheHomePageTests(ReminderMailTestCase):
    """Spec #656 測試決定: the home page's 下次篩檢 is the day the schedule sends on."""

    def test_the_home_page_s_next_screening_is_the_schedule_s_due_day(self):
        user = self.person("same_day", answered_on=None, on_since=date(2026, 5, 1))
        self.answer(user, date(2026, 5, 31), hour=23)  # 11/30: the month ends sooner
        self.client.force_login(user)
        day_before = date(2026, 11, 29)
        with at(day_before):
            home = self.client.get(reverse("index")).content.decode()
        (shown,) = re.findall(r'<span class="journey-tile-small">(\d{4}/\d\d/\d\d)</span>', home)
        self.assertEqual(self.run_on(day_before), [])
        self.run_on(date(2026, 11, 30))
        self.assertEqual(RetestReminderSent.objects.get().due_on.strftime("%Y/%m/%d"), shown)
