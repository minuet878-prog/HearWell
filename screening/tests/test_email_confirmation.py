"""確認信 (security check 2026-11-19, the owner's picks; docs/design/
email-confirmation-mockup.html). An email typed on the site gets the 重設密碼信 and the 重測提醒
only once its owner pressed 確認信箱 in the 確認信. Google's email and the emails kept before count
as confirmed; a link lasts 3 days."""

import importlib
import re
from datetime import timedelta
from unittest import mock
from urllib.parse import urlsplit

from django.apps import apps
from django.core import mail, signing
from django.core.cache import caches
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from screening.forms import HELP_ADDRESS
from screening.management.commands import send_retest_reminders
from screening.models import RetestReminder, User
from screening.tests.helpers import (
    FakeGoogle,
    FakeLine,
    consented_user,
    google_on,
    line_on,
    submission_with_answers,
)

PASSWORD = "Xk9#mPq2vLw"
SENT = "已寄確認信到 {}。請在 3 天內打開信，按「確認信箱」。沒收到的話，可以到帳號設定重寄。"
UNCONFIRMED = f"這個信箱還沒確認，沒辦法寄重設密碼信。請寫信到 {HELP_ADDRESS}，我們幫您處理。"


def confirmation_link(message):
    return re.search(r"https?://\S+/email/confirm/\S+", message.body).group()


def path_of(link):
    return urlsplit(link).path


def unconfirmed_user(**kwargs):
    user = consented_user(**kwargs)
    User.objects.filter(pk=user.pk).update(confirmed_email="")
    return User.objects.get(pk=user.pk)


@override_settings(SITE_URL="https://tingpal.tw")
class SendingTests(TestCase):
    def setUp(self):
        caches["password_reset"].clear()

    def test_registering_sends_the_confirmation_and_says_so(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "wang_ming",
                "email": "wang@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
            follow=True,
        )
        self.assertContains(response, SENT.format("wang@example.com"))
        (message,) = mail.outbox
        self.assertEqual(message.to, ["wang@example.com"])
        self.assertEqual(message.subject, "聽伴 確認您的信箱")
        self.assertEqual(message.reply_to, [HELP_ADDRESS])
        link = confirmation_link(message)
        self.assertTrue(link.startswith("https://tingpal.tw/email/confirm/"))
        (html, _), *_ = message.alternatives
        for words in ("wang_ming", link, "3 天內有效", "確認信箱"):
            with self.subTest(words=words):
                self.assertIn(words, message.body + html)
        self.assertFalse(User.objects.get(username="wang_ming").email_confirmed)

    def test_adding_an_email_sends_the_confirmation(self):
        user = consented_user(username="no_email", password=PASSWORD)
        self.client.force_login(user)
        self.client.post(f"{reverse('confirm_identity')}?action=add_email", {"password": PASSWORD})
        response = self.client.post(
            reverse("add_email"), {"email": "added@example.com"}, follow=True
        )
        self.assertContains(response, SENT.format("added@example.com"))
        self.assertEqual(mail.outbox[-1].to, ["added@example.com"])
        self.assertFalse(User.objects.get(pk=user.pk).email_confirmed)

    def test_the_link_does_not_show_the_email(self):
        # It ends up in the server's access log and the browser's history.
        user = consented_user(username="no_email", password=PASSWORD)
        User.objects.filter(pk=user.pk).update(email="secret.address@example.com")
        self.client.force_login(user)
        self.client.post(reverse("email_confirm_resend"))
        token = urlsplit(confirmation_link(mail.outbox[-1])).path.rsplit("/", 1)[1]
        self.assertNotIn("secret", signing.b64_decode(token.split(":")[0].encode()).decode())

    def test_a_failed_send_says_to_resend_later(self):
        with mock.patch(
            "screening.email_confirmation.EmailMultiAlternatives.send", side_effect=OSError
        ):
            response = self.client.post(
                reverse("register"),
                {
                    "username": "wang_ming",
                    "email": "wang@example.com",
                    "password1": PASSWORD,
                    "password2": PASSWORD,
                },
                follow=True,
            )
        self.assertContains(response, "確認信寄不出去，請稍後到帳號設定重寄。")
        self.assertTrue(User.objects.filter(username="wang_ming").exists())


@google_on
class GoogleTests(TestCase):
    def test_googles_email_counts_as_confirmed_and_nothing_is_sent(self):
        google = FakeGoogle(self.client)
        google.start()
        google.come_back(sub="google-new", email="lin.mei@example.com")
        self.client.post(reverse("google_name"), {"username": "林阿美", "roc_birth_year": ""})
        self.assertTrue(User.objects.get(username="林阿美").email_confirmed)
        self.assertEqual(mail.outbox, [])


@line_on
class LineTests(TestCase):
    def _name(self, email):
        line = FakeLine(self.client)
        line.start()
        line.come_back()
        return self.client.post(
            reverse("line_name"), {"username": "陳大同", "roc_birth_year": "", "email": email}
        )

    def test_a_typed_email_is_sent_its_confirmation(self):
        self._name("chen@example.com")
        self.assertFalse(User.objects.get(username="陳大同").email_confirmed)
        self.assertEqual(mail.outbox[-1].to, ["chen@example.com"])

    def test_without_an_email_nothing_is_sent(self):
        self._name("")
        self.assertTrue(User.objects.filter(username="陳大同").exists())
        self.assertEqual(mail.outbox, [])


class ConfirmPageTests(TestCase):
    def setUp(self):
        self.user = unconfirmed_user(username="wang_ming", email="wang@example.com")
        self.client.force_login(self.user)
        self.client.post(reverse("email_confirm_resend"))
        self.path = path_of(confirmation_link(mail.outbox[-1]))
        self.client.logout()

    def test_opening_the_link_asks_and_confirms_nothing(self):
        # A mail program's link scanner opens links too; signed out, as from the email.
        response = self.client.get(self.path)
        self.assertContains(response, '<h1 class="h3 mt-4">確認信箱</h1>', html=True)
        self.assertContains(response, "<strong>wang@example.com</strong>")
        self.assertContains(response, ">確認信箱</button>")
        self.assertFalse(User.objects.get(pk=self.user.pk).email_confirmed)
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertIn("no-store", response["Cache-Control"])

    def test_pressing_the_button_confirms_it(self):
        response = self.client.post(self.path)
        self.assertContains(response, "信箱確認好了")
        self.assertContains(response, "忘記密碼時，我們會把重設密碼信寄到 wang@example.com。")
        self.assertTrue(User.objects.get(pk=self.user.pk).email_confirmed)

    def test_signed_in_before_agreeing_it_still_opens(self):
        # Someone else's phone, signed in but not agreed yet: the consent gate lets it through.
        self.client.force_login(User.objects.create_user(username="newcomer"))
        self.assertContains(self.client.post(self.path), "信箱確認好了")
        self.assertTrue(User.objects.get(pk=self.user.pk).email_confirmed)

    def test_a_link_past_3_days_cannot_be_used(self):
        later = timezone.now() + timedelta(days=3, seconds=1)
        with mock.patch("django.core.signing.time.time", return_value=later.timestamp()):
            response = self.client.post(self.path)
        self.assertContains(response, "這個連結不能用了", status_code=404)
        self.assertContains(response, f'href="{reverse("account_settings")}"', status_code=404)
        self.assertFalse(User.objects.get(pk=self.user.pk).email_confirmed)

    def test_a_link_changed_or_for_an_email_changed_since_cannot_be_used(self):
        self.assertEqual(self.client.get(self.path[:-2] + "xx").status_code, 404)
        User.objects.filter(pk=self.user.pk).update(email="other@example.com")
        self.assertEqual(self.client.post(self.path).status_code, 404)
        self.assertFalse(User.objects.get(pk=self.user.pk).email_confirmed)


class AccountSettingsTests(TestCase):
    def setUp(self):
        caches["password_reset"].clear()
        self.user = unconfirmed_user(username="wang_ming", email="wang@example.com")
        self.client.force_login(self.user)

    def test_an_unconfirmed_email_says_so_with_a_resend_button(self):
        response = self.client.get(reverse("account_settings"))
        self.assertContains(response, '<span class="email-unconfirmed">還沒確認</span>', html=True)
        self.assertContains(response, "請打開確認信，按「確認信箱」。")
        self.assertContains(response, "您的 email 還沒確認，確認以後才能收提醒。")
        self.assertEqual(response.content.decode().count(">重寄確認信</button>"), 2)
        self.assertNotContains(response, "打開提醒")

    def test_a_confirmed_email_has_no_tag_or_button(self):
        User.objects.filter(pk=self.user.pk).update(confirmed_email="wang@example.com")
        response = self.client.get(reverse("account_settings"))
        self.assertNotContains(response, "還沒確認")
        self.assertNotContains(response, "重寄確認信")
        self.assertContains(response, "打開提醒")

    def test_three_resends_an_hour(self):
        for _ in range(3):
            response = self.client.post(reverse("email_confirm_resend"), follow=True)
            self.assertContains(response, SENT.format("wang@example.com"))
        response = self.client.post(reverse("email_confirm_resend"), follow=True)
        self.assertContains(response, "試太多次了，請一小時後再試")
        self.assertEqual(len(mail.outbox), 3)

    def test_a_confirmed_email_is_not_sent_again(self):
        User.objects.filter(pk=self.user.pk).update(confirmed_email="wang@example.com")
        self.client.post(reverse("email_confirm_resend"))
        self.assertEqual(mail.outbox, [])


class GateTests(TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S, for a result page

    def setUp(self):
        caches["password_reset"].clear()

    def test_no_reset_email_to_an_unconfirmed_email(self):
        unconfirmed_user(username="wang_ming", email="wang@example.com")
        response = self.client.post(reverse("password_reset"), {"email": "wang@example.com"})
        self.assertContains(response, f'<div class="error-box" role="alert">{UNCONFIRMED}</div>')
        self.assertEqual(mail.outbox, [])

    def test_only_the_confirmed_account_on_a_shared_email_gets_one(self):
        consented_user(username="confirmed_one", email="shared@example.com")
        unconfirmed_user(username="typed_by_someone", email="shared@example.com")
        self.client.post(reverse("password_reset"), {"email": "shared@example.com"})
        (message,) = mail.outbox
        self.assertIn("confirmed_one", message.body)
        self.assertNotIn("typed_by_someone", message.body)

    def test_the_result_page_asks_to_confirm_before_offering_the_reminder(self):
        user = unconfirmed_user(username="wang_ming", email="wang@example.com")
        self.client.force_login(user)
        response = self.client.get(
            reverse("result", args=[submission_with_answers(user, "hhie-s", [0] * 10).pk])
        )
        self.assertContains(response, "想在到期時收到 email 提醒，要先確認您的 email。")
        self.assertNotContains(response, "到期時寄 email 提醒我")

    def test_the_reminder_cannot_be_turned_on_for_an_unconfirmed_email(self):
        user = unconfirmed_user(username="wang_ming", email="wang@example.com")
        self.client.force_login(user)
        self.client.post(reverse("retest_reminder"), {"enabled": "1"})
        self.assertFalse(RetestReminder.objects.filter(user=user, enabled=True).exists())

    def test_no_reminder_is_sent_to_an_unconfirmed_email(self):
        user = unconfirmed_user(username="wang_ming", email="wang@example.com")
        reminder = RetestReminder.objects.create(user=user)
        reminder.turn_on(timezone.localdate() - timedelta(days=400))
        self.assertNotIn(reminder, send_retest_reminders._sendable())
        User.objects.filter(pk=user.pk).update(confirmed_email="wang@example.com")
        self.assertIn(reminder, send_retest_reminders._sendable())


class ExistingEmailsTests(TestCase):
    def test_emails_kept_before_count_as_confirmed(self):
        kept = User.objects.create_user(username="kept", email="kept@example.com")
        none = User.objects.create_user(username="none")
        User.objects.update(confirmed_email="")
        migration = importlib.import_module("screening.migrations.0044_user_confirmed_email")
        migration.confirm_existing_emails(apps, None)
        self.assertTrue(User.objects.get(pk=kept.pk).email_confirmed)
        self.assertEqual(User.objects.get(pk=none.pk).confirmed_email, "")
