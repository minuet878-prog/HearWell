"""#659 (spec #656 acceptance 1-6, 43-45, 40): the email 重測提醒 turned on and off in the
account settings (the #657 mockup's C)."""

import json
import re
from datetime import UTC, date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.models import RetestReminder, Submission, User
from screening.questionnaires import hhie_s
from screening.tests import test_layout
from screening.tests.helpers import consented_user, submission_with_answers

TAIPEI = ZoneInfo("Asia/Taipei")
# 01:00 on 2026/11/17 in Taiwan, still the 16th in UTC: the day it was turned on is Taiwan's.
NOW = datetime(2026, 11, 16, 17, tzinfo=UTC)
# The owner's words beside the switch, settled on 2026-11-17 (#658).
PURPOSE = (
    "打開後，上次做完滿半年的那天早上，我們會寄一封提醒信到您的 email。信裡不會寫分數或結果。"
    "您的 email 只用來寄這個提醒和重設密碼信，隨時可以關掉。"
)


class ReminderSwitchTests(TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S

    def setUp(self):
        self.enterContext(patch("django.utils.timezone.now", return_value=NOW))
        self.user = consented_user(username="reminder_a", email="a@example.com")
        self.client.force_login(self.user)
        self.url = reverse("retest_reminder")

    def _page(self):
        response = self.client.get(reverse("account_settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        start = content.index('<section id="retest-reminder"')
        return content[start : content.index("</section>", start)]

    def _section(self):
        """The text of the account settings' email 重測提醒 section."""
        return test_layout._text(self._page())

    def _hhie_s(self, on):
        """An HHIE-S record made at noon, Taiwan time, on that day."""
        submission = submission_with_answers(self.user, hhie_s.CODE, [0] * 10)
        moment = datetime(on.year, on.month, on.day, 12, tzinfo=TAIPEI)
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def _turn(self, enabled, **fields):
        return self.client.post(self.url, {"enabled": enabled, **fields})

    def _reminder(self):
        return RetestReminder.objects.get(user=self.user)

    # 1
    def test_off_by_default_says_where_it_would_go(self):
        text = self._section()
        self.assertIn("email 重測提醒", text)
        self.assertIn(PURPOSE, text)
        self.assertIn("目前 沒有打開", text)
        self.assertIn("打開提醒", text)
        self.assertIn("會寄到 a@example.com", text)
        self.assertNotIn("已開啟", text)
        self.assertFalse(RetestReminder.objects.filter(user=self.user, enabled=True).exists())

    # 2
    def test_turning_it_on_keeps_taiwan_s_day_and_says_where_it_goes(self):
        response = self._turn("1")
        self.assertRedirects(response, reverse("account_settings"), fetch_redirect_response=False)
        reminder = self._reminder()
        self.assertTrue(reminder.enabled)
        self.assertEqual(reminder.enabled_on, date(2026, 11, 17))
        text = self._section()
        self.assertIn("已開啟，到期會寄到 a@example.com", text)
        self.assertIn("目前 已開啟（2026/11/17 起）", text)
        self.assertIn("關掉提醒", text)
        self.assertNotIn("打開提醒", text.replace("關掉提醒", ""))

    def test_the_day_it_falls_due_is_the_home_page_s(self):
        self._hhie_s(date(2026, 6, 1))
        self._turn("1")
        text = self._section()
        self.assertIn("下次篩檢 2026/12/01，那天早上 9 點寄信。", text)
        self.assertNotIn("您現在就可以再做一次", text)
        home = test_layout._text(self.client.get(reverse("index")).content.decode())
        self.assertIn("2026/12/01", home)

    # 3
    def test_turning_it_off(self):
        self._turn("1")
        response = self._turn("0")
        self.assertRedirects(response, reverse("account_settings"), fetch_redirect_response=False)
        reminder = self._reminder()
        self.assertFalse(reminder.enabled)
        self.assertIsNone(reminder.enabled_on)
        text = self._section()
        self.assertIn("目前 沒有打開", text)
        self.assertNotIn("已開啟", text)

    def test_on_again_has_a_new_cancel_code(self):
        self._turn("1")
        first = self._reminder().cancel_token
        self._turn("1")  # pressed twice: still the same reminder
        self.assertEqual(self._reminder().cancel_token, first)
        self._turn("0")
        self._turn("1")
        again = self._reminder()
        self.assertTrue(again.enabled)
        self.assertNotEqual(again.cancel_token, first)
        self.assertGreaterEqual(len(again.cancel_token), 43)  # token_urlsafe(32)

    # 4
    def test_already_due_says_do_it_now_and_links_to_it(self):
        record = self._hhie_s(date(2026, 3, 10))
        self._turn("1")
        page = self._page()
        text = test_layout._text(page)
        self.assertIn("您現在就可以再做一次", text)
        self.assertIn("上一次是 2026/03/10", text)
        self.assertIn(f'href="{reverse("screening", args=[record.questionnaire.pk])}"', page)
        self.assertNotIn("下次篩檢", text)
        # Due before the day it was turned on: the schedule does not send this one (23).
        self.assertIn("這一次不另外寄信", text)

    # 4, 23: due the day it is turned on, so the schedule sends it (cross review, Codex 5).
    def test_due_the_day_it_is_turned_on_does_not_say_no_mail(self):
        record = self._hhie_s(date(2026, 5, 17))  # + 6 months: 2026/11/17, today
        self._turn("1")
        page = self._page()
        text = test_layout._text(page)
        self.assertIn("您現在就可以再做一次", text)
        self.assertIn("上一次是 2026/05/17", text)
        self.assertIn(f'href="{reverse("screening", args=[record.questionnaire.pk])}"', page)
        self.assertNotIn("不另外寄信", text)

    def test_off_says_nothing_of_doing_it_now(self):
        self._hhie_s(date(2026, 3, 10))
        self.assertNotIn("您現在就可以再做一次", self._section())

    # 5
    def test_without_an_email_it_cannot_be_turned_on(self):
        self.user.email = ""
        self.user.save()
        page = self._page()
        text = test_layout._text(page)
        self.assertIn("目前 沒有打開", text)
        self.assertIn("您的帳號還沒有 email，要先補上才能收提醒。", text)
        self.assertIn("補上 email", text)
        self.assertNotIn("打開提醒", text)
        self.assertNotIn(f'action="{self.url}"', page)
        self._turn("1")
        self.assertFalse(RetestReminder.objects.filter(user=self.user, enabled=True).exists())

    # 6
    def test_the_page_s_own_form_turns_it_on_and_off_without_javascript(self):
        for button in ("打開提醒", "關掉提醒"):
            with self.subTest(button=button):
                page = self._page()
                form = next(f for f in re.findall(r"<form .*?</form>", page, re.S) if button in f)
                self.assertIn('method="post"', form)
                self.assertIn(f'action="{self.url}"', form)
                self.assertIn('type="submit"', form)
                fields = dict(re.findall(r'name="(\w+)" value="([^"]*)"', form))
                fields.pop("csrfmiddlewaretoken")
                self.client.post(self.url, fields)
                self.assertEqual(self._reminder().enabled, button == "打開提醒")

    # #661 sends the result page's form here too: back to its next, a same-site one only.
    def test_back_to_a_same_site_next(self):
        response = self._turn("1", next="/my_hearing")
        self.assertRedirects(response, "/my_hearing", fetch_redirect_response=False)
        response = self._turn("0", next="https://example.com/")
        self.assertRedirects(response, reverse("account_settings"), fetch_redirect_response=False)

    def test_signed_out_changes_nothing(self):
        self.client.logout()
        response = self._turn("1")
        self.assertTrue(response.url.startswith(reverse("login")))
        self.assertFalse(RetestReminder.objects.exists())

    def test_only_post_with_on_or_off(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self._turn("yes").status_code, 400)
        self.assertFalse(RetestReminder.objects.exists())

    def test_only_one_s_own_reminder(self):
        other = consented_user(username="reminder_b", email="b@example.com")
        RetestReminder.objects.create(user=other, enabled=True, enabled_on=date(2026, 11, 1))
        self._turn("1")
        self._turn("0")
        other_reminder = RetestReminder.objects.get(user=other)
        self.assertTrue(other_reminder.enabled)
        self.assertEqual(other_reminder.enabled_on, date(2026, 11, 1))


class ReminderDataTests(TestCase):
    """Spec #656 acceptance 43-45: deleting the account, 下載我的資料, the admin."""

    def setUp(self):
        self.user = consented_user(username="reminder_data", email="d@example.com")
        self.reminder = RetestReminder.objects.create(
            user=self.user, enabled=True, enabled_on=date(2026, 11, 3)
        )

    # 43
    def test_deleting_the_account_deletes_the_reminder(self):
        other = consented_user(username="reminder_kept", email="k@example.com")
        RetestReminder.objects.create(user=other, enabled=True, enabled_on=date(2026, 11, 3))
        self.user.delete_with_data()
        self.assertEqual(list(RetestReminder.objects.values_list("user", flat=True)), [other.pk])

    # 44
    def test_my_data_says_whether_it_is_on_and_since_when_without_the_code(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("download_my_data"))
        self.assertEqual(
            json.loads(response.content)["retest_reminder"],
            {"enabled": True, "enabled_on": "2026-11-03"},
        )
        self.assertNotIn(self.reminder.cancel_token, response.content.decode())

    def test_my_data_without_one_says_off(self):
        RetestReminder.objects.all().delete()
        self.client.force_login(self.user)
        data = json.loads(self.client.get(reverse("download_my_data")).content)
        self.assertEqual(data["retest_reminder"], {"enabled": False, "enabled_on": None})

    # 45
    def test_the_admin_only_looks_and_never_shows_the_code(self):
        admin = User.objects.create_superuser(username="reminder_admin", password="pw")
        self.client.force_login(admin)
        changelist = reverse("admin:screening_retestreminder_changelist")
        page = self.client.get(changelist).content.decode()
        headers = re.findall(r'<th scope="col" class="[^"]*column-(\w+)', page)
        self.assertEqual(headers, ["user", "enabled", "enabled_on"])
        change = reverse("admin:screening_retestreminder_change", args=[self.reminder.pk])
        detail = self.client.get(change)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "reminder_data")
        for content in (page, detail.content.decode()):
            self.assertNotIn(self.reminder.cancel_token, content)
        add = reverse("admin:screening_retestreminder_add")
        self.assertNotIn(add, page)
        self.assertEqual(self.client.get(add).status_code, 403)
        self.assertEqual(self.client.post(change, {"enabled": ""}).status_code, 403)
        delete = reverse("admin:screening_retestreminder_delete", args=[self.reminder.pk])
        self.assertEqual(self.client.post(delete, {"post": "yes"}).status_code, 403)
        self.assertTrue(RetestReminder.objects.get(pk=self.reminder.pk).enabled)

    def test_the_admin_list_takes_the_same_queries_for_many(self):
        # CODING_STANDARDS 15 (cross review): a row more for each account that turns it on.
        self.client.force_login(User.objects.create_superuser(username="owner", password="pw"))
        changelist = reverse("admin:screening_retestreminder_changelist")
        self.client.get(changelist)  # the first request also looks up what the admin caches
        with CaptureQueriesContext(connection) as one:
            self.assertEqual(self.client.get(changelist).status_code, 200)
        for number in range(5):
            user = consented_user(username=f"many_{number}", email=f"m{number}@example.com")
            RetestReminder.objects.create(user=user, enabled=True, enabled_on=date(2026, 11, 3))
        with self.assertNumQueries(len(one)):
            self.assertContains(self.client.get(changelist), "many_4")
