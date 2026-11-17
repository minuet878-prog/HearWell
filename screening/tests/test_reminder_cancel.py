"""#662 (spec #656 acceptance 32-39): the email 重測提醒 cancelled from an email's link without
signing in (the #657 mockup's cancel page B), RFC 8058's one-click included."""

from datetime import date

from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse

from screening.models import RetestReminder
from screening.tests import test_layout
from screening.tests.helpers import consented_user

# The owner's words on the three pages, settled on 2026-11-17 (#658).
CANCEL_WORDS = (
    "按下「取消提醒」後，這個帳號就不會再收到重測提醒信。您的帳號和篩檢紀錄都不會受影響。"
)
CANCELLED_WORDS = "之後不會再寄重測提醒信給這個帳號。想再收到，可以登入後到帳號設定打開。"
INVALID_WORDS = "這可能是比較舊的提醒信，或連結沒有複製完整。要關掉重測提醒，請登入後到帳號設定。"


class ReminderCancelTests(TestCase):
    def setUp(self):
        self.user = consented_user(username="wang_baba", email="family@example.com")
        self.reminder = RetestReminder.objects.create(
            user=self.user, enabled=True, enabled_on=date(2026, 11, 16)
        )
        # A mail program's one-click sends no CSRF token, and neither does a page left open.
        self.client = Client(enforce_csrf_checks=True)

    def _url(self, token=None):
        return reverse("reminder_cancel", args=[token or self.reminder.cancel_token])

    def _reminder(self):
        return RetestReminder.objects.get(pk=self.reminder.pk)

    # 32
    def test_opening_the_link_shows_the_account_and_a_button_without_cancelling(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        text = test_layout._text(response.content.decode())
        self.assertIn("取消 email 重測提醒", text)
        self.assertIn("帳號 wang_baba", text)
        # Under the account, above the button.
        self.assertLess(text.index("帳號 wang_baba"), text.index(CANCEL_WORDS))
        self.assertLess(text.index(CANCEL_WORDS), text.index("取消提醒 不取消"))
        self.assertContains(
            response, '<button class="btn btn-primary btn-lg w-full" type="submit">'
        )
        self.assertIn("取消提醒", text)
        self.assertContains(response, f'href="{reverse("index")}"')
        self.assertIn("不取消，回首頁", text)
        self.assertTrue(self._reminder().enabled)

    # 33
    def test_the_button_turns_it_off_and_says_so(self):
        response = self.client.post(self._url(), follow=True)
        self.assertRedirects(response, reverse("reminder_cancelled"))
        text = test_layout._text(response.content.decode())
        self.assertIn("已取消", text)
        self.assertLess(text.index("✓ 已取消"), text.index(CANCELLED_WORDS))
        reminder = self._reminder()
        self.assertFalse(reminder.enabled)
        self.assertIsNone(reminder.enabled_on)

    # 34: RFC 8058's one-click, a POST with this body and no CSRF token or cookie; answered
    # there and then, not sent on to another address (cross review, Codex 7).
    def test_a_mail_programs_one_click_turns_it_off(self):
        response = self.client.post(
            self._url(),
            "List-Unsubscribe=One-Click",
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Location", response)
        self.assertFalse(self._reminder().enabled)

    # 35
    def test_a_wrong_code_and_a_deleted_account_say_the_same(self):
        gone = consented_user(username="gone_mama", email="family@example.com")
        gone_token = RetestReminder.objects.create(user=gone, enabled=True).cancel_token
        gone.delete_with_data()
        wrong = "x" * 43  # as long as a real code
        pages = {}
        for name, token in (("wrong", wrong), ("deleted", gone_token)):
            for method in ("get", "post"):
                with self.subTest(code=name, method=method):
                    response = getattr(self.client, method)(self._url(token))
                    self.assertContains(response, "這個連結已經不能用了", status_code=404)
                    self.assertContains(response, INVALID_WORDS, status_code=404)
                    self.assertNotContains(response, "gone_mama", status_code=404)
                    # The footer's 意見回饋 link names the address it came from.
                    pages[name, method] = test_layout._main(response.content.decode())
        self.assertEqual(len(set(pages.values())), 1)
        self.assertTrue(self._reminder().enabled)

    # 36
    def test_cancelling_again_still_says_cancelled(self):
        self.client.post(self._url())
        self.assertEqual(self.client.get(self._url()).status_code, 200)
        response = self.client.post(self._url(), follow=True)
        self.assertRedirects(response, reverse("reminder_cancelled"))
        self.assertIn("已取消", test_layout._text(response.content.decode()))
        self.assertFalse(self._reminder().enabled)

    # 37
    def test_an_old_emails_link_stops_working_once_turned_off_and_on(self):
        old = self._url()
        owner = Client()
        owner.force_login(self.user)
        owner.post(reverse("retest_reminder"), {"enabled": "0"})
        owner.post(reverse("retest_reminder"), {"enabled": "1"})
        self.assertContains(self.client.get(old), "這個連結已經不能用了", status_code=404)
        self.assertEqual(self.client.post(old).status_code, 404)
        self.assertTrue(self._reminder().enabled)
        new = self._url(self._reminder().cancel_token)
        self.assertEqual(self.client.get(new).status_code, 200)

    # 37: pressed at the very moment the owner turns it on again (cross review, Codex 8).
    def test_an_old_link_pressed_while_turned_on_again_leaves_the_new_one_on(self):
        old = self.reminder.cancel_token
        self.reminder.turn_off()
        on_again = []

        def turn_on_again(execute, sql, params, many, context):
            # Just after the cancel's first look at the old code, the owner turns it on again.
            result = execute(sql, params, many, context)
            if not on_again and old in (params or ()):
                on_again.append(True)
                self._reminder().turn_on(date(2026, 11, 17))
            return result

        with connection.execute_wrapper(turn_on_again):
            self.client.post(self._url(old))
        self.assertEqual(on_again, [True])
        reminder = self._reminder()
        self.assertTrue(reminder.enabled)
        self.assertNotEqual(reminder.cancel_token, old)

    # 38
    def test_cancelling_one_account_leaves_the_other_on_the_same_address(self):
        mama = consented_user(username="wang_mama", email="family@example.com")
        other = RetestReminder.objects.create(user=mama, enabled=True, enabled_on=date(2026, 11, 1))
        self.client.post(self._url())
        self.assertFalse(self._reminder().enabled)
        other.refresh_from_db()
        self.assertTrue(other.enabled)
        self.assertEqual(other.enabled_on, date(2026, 11, 1))

    # 39
    def test_signed_in_before_agreeing_to_the_notice_can_still_cancel(self):
        self.user.consents.all().delete()
        self.assertFalse(self.user.has_consented())
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self._url()), "取消提醒")
        response = self.client.post(self._url(), follow=True)
        self.assertRedirects(response, reverse("reminder_cancelled"))
        self.assertFalse(self._reminder().enabled)

    # 39
    # The footer's 意見回饋 link carries the page's address as its way back; the cancel page's
    # address is its code, so like a shared report's it has none (#633 cross review P2).
    def test_the_footer_feedback_link_never_carries_the_code(self):
        token = self.reminder.cancel_token
        for url in (self._url(), self._url("x" * 43)):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(
                    response,
                    f'href="{reverse("feedback")}?page=reminder_cancel"',
                    status_code=response.status_code,
                )
                self.assertNotIn(token, response.content.decode().split("<footer")[1])
                self.assertNotIn("x" * 43, response.content.decode().split("<footer")[1])

    def test_pages_not_cached_indexed_or_referred(self):
        responses = {
            "cancel": self.client.get(self._url()),
            "invalid": self.client.get(self._url("x" * 43)),
            "cancelled": self.client.get(reverse("reminder_cancelled")),
        }
        for name, response in responses.items():
            with self.subTest(page=name):
                self.assertIn("no-store", response["Cache-Control"])
                self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
                self.assertEqual(response["Referrer-Policy"], "no-referrer")
                self.assertContains(
                    response,
                    '<meta name="robots" content="noindex, nofollow">',
                    status_code=response.status_code,
                )

    # 39
    def test_pages_are_not_in_the_sitemap(self):
        sitemap = self.client.get(reverse("sitemap")).content.decode()
        self.assertIn("<urlset", sitemap)
        self.assertNotIn("/reminder", sitemap)
