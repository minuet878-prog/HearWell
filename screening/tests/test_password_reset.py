import re
import time
from datetime import UTC, datetime, timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.core.cache import caches
from django.core.mail.backends.base import BaseEmailBackend
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from screening import forms
from screening.forms import PASSWORD_RULES
from screening.models import User
from screening.tests.helpers import consented_user
from screening.views.accounts import RESET_EMAIL

PASSWORD = "Xk9#mPq2vLw"
NOT_REGISTERED = "這個信箱沒有註冊，請檢查有沒有打錯"
HELP_ADDRESS = "hearwellweb@gmail.com"


def _reset_link(message):
    """The reset address in the plain-text version of a 重設密碼信."""
    return re.search(r"https?://\S+/reset/\S+", message.body).group()


class ForgotPasswordPageTests(TestCase):
    """#527 (spec #355): the forgot-password page sends a 重設密碼信 to each ordinary account
    on the email, any letter case, with or without a password; staff, superusers and inactive
    accounts count as not registered (ADR 0038)."""

    def _ask(self, email):
        return self.client.post(reverse("password_reset"), {"email": email})

    def _as_typed(self, response, email):
        """The page with the typed email and the per-request CSRF token taken out."""
        content = response.content.decode().replace(email, "EMAIL")
        return re.sub(r'name="csrfmiddlewaretoken" value="[^"]*"', "", content)

    def _assert_same_as_not_registered(self, email):
        unknown = "nobody@example.com"
        self.assertEqual(
            self._as_typed(self._ask(email), email),
            self._as_typed(self._ask(unknown), unknown),
        )

    def test_the_page_asks_for_the_email_and_offers_the_help_address(self):
        response = self.client.get(reverse("password_reset"))
        content = response.content.decode()
        self.assertRegex(content, r"<title>\s*忘記密碼｜聽伴\s*</title>")  # noqa: RUF001
        self.assertContains(response, '<label for="id_email">電子郵件</label>', html=True)
        self.assertContains(response, 'autocomplete="email"')
        self.assertContains(response, f'<a class="inline-link" href="mailto:{HELP_ADDRESS}">')

    def test_a_registered_email_in_any_case_gets_one_email(self):
        consented_user(username="wang_ming", email="a@example.com", password=PASSWORD)
        response = self._ask("A@Example.com")
        self.assertRedirects(response, reverse("password_reset_sent"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["a@example.com"])

    def test_two_accounts_on_one_email_get_one_each(self):
        consented_user(username="wang_ming", email="home@example.com", password=PASSWORD)
        consented_user(username="lin_mei", email="home@example.com", password=PASSWORD)
        self._ask("home@example.com")
        self.assertEqual(len(mail.outbox), 2)
        by_name = {
            name: message
            for message in mail.outbox
            for name in ("wang_ming", "lin_mei")
            if name in message.body
        }
        self.assertEqual(set(by_name), {"wang_ming", "lin_mei"})
        self.assertNotIn("lin_mei", by_name["wang_ming"].body)
        self.assertNotEqual(_reset_link(by_name["wang_ming"]), _reset_link(by_name["lin_mei"]))

    def test_an_account_without_a_password_gets_one_too(self):
        # Signing in with Google or LINE leaves no usable password (spec #505, #506).
        user = User.objects.create_user(username="google_only", email="g@example.com")
        self.assertFalse(user.has_usable_password())
        self._ask("g@example.com")
        self.assertEqual(len(mail.outbox), 1)

    def test_an_unknown_email_stays_on_the_page_and_keeps_what_was_typed(self):
        response = self._ask("x@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, NOT_REGISTERED)
        self.assertContains(response, 'value="x@example.com"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertEqual(mail.outbox, [])

    def test_an_email_of_staff_or_a_superuser_only_reads_as_not_registered(self):
        User.objects.create_user(username="staff", email="s@example.com", is_staff=True)
        # A superuser who is not staff too, so each flag is checked on its own.
        User.objects.create_user(username="root", email="r@example.com", is_superuser=True)
        for email in ("s@example.com", "r@example.com"):
            with self.subTest(email=email):
                self.assertContains(self._ask(email), NOT_REGISTERED)
                self._assert_same_as_not_registered(email)
        self.assertEqual(mail.outbox, [])

    def test_an_email_shared_with_an_admin_reaches_the_ordinary_account_only(self):
        User.objects.create_user(username="staff", email="both@example.com", is_staff=True)
        consented_user(username="wang_ming", email="both@example.com", password=PASSWORD)
        self._ask("both@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("wang_ming", mail.outbox[0].body)
        self.assertNotIn("staff", mail.outbox[0].body)

    def test_an_inactive_account_reads_as_not_registered(self):
        User.objects.create_user(username="gone", email="i@example.com", is_active=False)
        self.assertContains(self._ask("i@example.com"), NOT_REGISTERED)
        self._assert_same_as_not_registered("i@example.com")
        self.assertEqual(mail.outbox, [])


class SentPageTests(TestCase):
    """#527 (spec #355, mockup #524 D2): the page after sending shows the email to check, keeps
    it out of the address, and offers a way back to type it again."""

    def setUp(self):
        consented_user(username="wang_ming", email="a@example.com", password=PASSWORD)
        self.response = self.client.post(
            reverse("password_reset"), {"email": "a@example.com"}, follow=True
        )

    def test_it_shows_the_email_without_putting_it_in_the_address(self):
        url, _ = self.response.redirect_chain[-1]
        self.assertEqual(url, reverse("password_reset_sent"))
        self.assertNotIn("example", url)
        self.assertContains(self.response, "a@example.com")

    def test_it_says_where_to_look_and_where_to_ask(self):
        content = self.response.content.decode()
        self.assertRegex(content, r"<title>\s*信寄出了｜聽伴\s*</title>")  # noqa: RUF001
        self.assertContains(self.response, "幾分鐘內會收到，沒收到請看垃圾信件匣。")
        self.assertContains(self.response, f'href="mailto:{HELP_ADDRESS}"')

    def test_a_wrong_email_can_be_typed_again(self):
        self.assertContains(
            self.response,
            f'<a class="inline-link" href="{reverse("password_reset")}">信箱打錯了？重新輸入</a>',
            html=True,
        )

    def test_without_a_request_it_goes_to_the_forgot_password_page(self):
        self.client.session.flush()
        response = self.client.get(reverse("password_reset_sent"))
        self.assertRedirects(response, reverse("password_reset"))


class ResetEmailTests(TestCase):
    """#527 (spec #355, mockup #524 D4): 聽伴's sender and subject, replies to the owner's
    mailbox, and both versions carry the name, the whole address and the two promises."""

    def setUp(self):
        consented_user(username="wang_ming", email="a@example.com", password=PASSWORD)

    def _send(self, **extra):
        self.client.post(reverse("password_reset"), {"email": "a@example.com"}, **extra)
        return mail.outbox[-1]

    def test_sender_subject_and_where_replies_go(self):
        message = self._send()
        self.assertEqual(message.subject, "聽伴 重設密碼")
        self.assertEqual(message.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertTrue(message.from_email.startswith("聽伴 <"))
        self.assertEqual(message.reply_to, [HELP_ADDRESS])

    def test_both_versions_carry_the_name_the_address_and_the_promises(self):
        message = self._send()
        link = _reset_link(message)
        (html, kind), *_ = message.alternatives
        self.assertEqual(kind, "text/html")
        for version, text in (("plain", message.body), ("html", html)):
            for words in ("wang_ming", link, "1 天內有效", "不是您申請的請忽略"):
                with self.subTest(version=version, words=words):
                    self.assertIn(words, text)

    def test_the_link_is_on_the_address_the_page_was_opened_on(self):
        message = self._send(HTTP_HOST="localhost", secure=True)
        self.assertTrue(_reset_link(message).startswith("https://localhost/reset/"))


class SetNewPasswordTests(TestCase):
    """#527 (spec #355, mockup #524 D3): the link opens a page naming the account, with the
    register page's rules and 顯示 buttons; a good password signs in through the consent page."""

    def _open_link(self, user):
        self.client.post(reverse("password_reset"), {"email": user.email})
        link = _reset_link(mail.outbox[-1])
        # Django moves the token into the session and the address to .../set-password.
        return self.client.get(link, follow=True)

    def _set(self, response, password):
        url, _ = response.redirect_chain[-1]
        return self.client.post(
            url, {"new_password1": password, "new_password2": password}, follow=True
        )

    def test_the_page_names_the_account_and_has_the_rules_and_show_buttons(self):
        user = consented_user(username="wang_ming", email="a@example.com", password=PASSWORD)
        response = self._open_link(user)
        content = response.content.decode()
        self.assertRegex(content, r"<title>\s*設新密碼｜聽伴\s*</title>")  # noqa: RUF001
        self.assertContains(response, "帳號：<strong>wang_ming</strong>", html=True)
        for rule in PASSWORD_RULES:
            with self.subTest(rule=rule):
                self.assertContains(response, f"<li>{rule}</li>", html=True)
        self.assertContains(response, '<label for="id_new_password1">新密碼</label>', html=True)
        self.assertContains(response, '<label for="id_new_password2">新密碼確認</label>', html=True)
        buttons = re.findall(r"<button[^>]*>顯示</button>", content)
        self.assertEqual(len(buttons), 2)
        self.assertIn("screening/password-toggle.js", content)

    def test_a_password_against_the_rules_is_refused(self):
        user = consented_user(username="wang_ming", email="a@example.com", password=PASSWORD)
        response = self._set(self._open_link(user), "38475610")
        self.assertContains(response, "這個密碼只包含數字。")
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD))

    def test_a_good_password_signs_in_and_goes_home_with_a_message(self):
        user = consented_user(username="wang_ming", email="a@example.com", password=PASSWORD)
        response = self._set(self._open_link(user), "Qz7!nw4Tlake")
        self.assertEqual(response.redirect_chain[-1][0], reverse("index"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertContains(response, "密碼改好了")
        self.client.logout()
        self.assertTrue(self.client.login(username="wang_ming", password="Qz7!nw4Tlake"))
        self.assertFalse(self.client.login(username="wang_ming", password=PASSWORD))

    def test_who_has_not_agreed_signs_in_on_the_consent_page(self):
        user = User.objects.create_user(username="new_one", email="n@example.com")
        response = self._set(self._open_link(user), "Qz7!nw4Tlake")
        self.assertEqual(response.redirect_chain[-1][0], reverse("consent"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertContains(response, "密碼改好了")

    def test_an_account_without_a_password_can_then_sign_in_with_one(self):
        user = User.objects.create_user(username="google_only", email="g@example.com")
        self._set(self._open_link(user), "Qz7!nw4Tlake")
        self.client.logout()
        self.assertTrue(self.client.login(username="google_only", password="Qz7!nw4Tlake"))

    def test_another_device_is_signed_out(self):
        user = consented_user(username="wang_ming", email="a@example.com", password=PASSWORD)
        other = Client()
        other.force_login(user)
        self.assertEqual(other.get(reverse("my_hearing")).status_code, 200)
        self._set(self._open_link(user), "Qz7!nw4Tlake")
        self.assertRedirects(
            other.get(reverse("my_hearing")),
            f"{reverse('login')}?next={reverse('my_hearing')}",
        )


class ExpiredLinkTests(TestCase):
    """#527 (spec #355): a link works for a day and once; signing in after asking ends it too.
    The same address then says so, with no password fields and a way to ask again."""

    def setUp(self):
        self.user = consented_user(username="wang_ming", email="a@example.com", password=PASSWORD)
        self.client.post(reverse("password_reset"), {"email": "a@example.com"})
        self.link = _reset_link(mail.outbox[-1])

    def _open(self, hours_later=0):
        later = datetime.now() + timedelta(hours=hours_later)
        with mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=later):
            return self.client.get(self.link, follow=True)

    def _assert_expired(self, response):
        content = response.content.decode()
        self.assertRegex(content, r"<title>\s*連結不能用了｜聽伴\s*</title>")  # noqa: RUF001
        self.assertContains(response, "這個連結已經過期或用過了")
        self.assertContains(
            response,
            f'<a class="w-full btn btn-lg btn-primary" href="{reverse("password_reset")}">'
            "重新申請</a>",
            html=True,
        )
        self.assertNotContains(response, 'type="password"')

    def test_after_a_day_it_has_expired(self):
        self._assert_expired(self._open(hours_later=25))

    def test_after_23_hours_it_still_works(self):
        self.assertContains(self._open(hours_later=23), 'name="new_password1"')

    def test_it_works_once(self):
        url, _ = self._open().redirect_chain[-1]
        self.client.post(url, {"new_password1": "Qz7!nw4Tlake", "new_password2": "Qz7!nw4Tlake"})
        self.client.logout()
        self._assert_expired(self.client.get(self.link, follow=True))

    def test_signing_in_after_asking_ends_it(self):
        self.assertTrue(Client().login(username="wang_ming", password=PASSWORD))
        self._assert_expired(self._open())

    def test_a_link_lasts_one_day(self):
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 24 * 60 * 60)


class LinkOfAnAccountThatChangedTests(TestCase):
    """#527 self-review (spec #355 story 34): an account made staff or superuser, or made
    inactive, after the email was sent cannot use its link either."""

    def test_the_link_reads_as_expired(self):
        for number, change in enumerate(
            ({"is_staff": True}, {"is_superuser": True}, {"is_active": False})
        ):
            with self.subTest(change=change):
                email = f"later{number}@example.com"
                user = consented_user(username=f"later_{number}", email=email, password=PASSWORD)
                self.client.post(reverse("password_reset"), {"email": email})
                link = _reset_link(mail.outbox[-1])
                User.objects.filter(pk=user.pk).update(**change)
                response = self.client.get(link, follow=True)
                self.assertContains(response, "這個連結已經過期或用過了")
                self.assertNotContains(response, 'type="password"')


class ResetPagesSiteWideTests(TestCase):
    """#527 (spec #355): the four pages pass the checks the login and register pages do: the
    title, one h1 in main, the skip link, the footer, and the 登入 tab marked (mockup #524)."""

    def _pages(self):
        consented_user(username="wang_ming", email="a@example.com", password=PASSWORD)
        forgot = self.client.get(reverse("password_reset"))
        sent = self.client.post(reverse("password_reset"), {"email": "a@example.com"}, follow=True)
        link = _reset_link(mail.outbox[-1])
        confirm = self.client.get(link, follow=True)
        expired = self.client.get(reverse("password_reset_confirm", args=["MQ", "wrong-token"]))
        return {
            "忘記密碼": forgot,
            "信寄出了": sent,
            "設新密碼": confirm,
            "連結不能用了": expired,
        }

    def test_each_page_passes_the_site_wide_checks(self):
        for title, response in self._pages().items():
            with self.subTest(title=title):
                content = response.content.decode()
                self.assertRegex(content, rf"<title>\s*{title}｜聽伴\s*</title>")  # noqa: RUF001
                main = content[content.index("<main") : content.index("</main>")]
                self.assertEqual(len(re.findall(r"<h1\b", content)), 1)
                self.assertEqual(len(re.findall(r"<h1\b", main)), 1)
                self.assertIn('href="#main-content"', content)
                self.assertIn('<footer class="site-footer">', content)
                self.assertRegex(content, rf'<a href="{reverse("login")}" aria-current="page">')


TOO_MANY = "試太多次了，請一小時後再試"


class AttemptLimitTests(TestCase):
    """#528 (spec #355): 10 sendings an hour from one address, whether registered or not, and 3
    emails an hour to one email. The address is X-Forwarded-For's last, which Nginx adds; the
    ones before it come from the visitor and can be forged. Counts live in the database cache."""

    def setUp(self):
        caches["password_reset"].clear()
        consented_user(username="wang_ming", email="a@example.com", password=PASSWORD)

    def _ask(self, email, forwarded=None, remote="127.0.0.1"):
        extra = {"REMOTE_ADDR": remote}
        if forwarded:
            extra["HTTP_X_FORWARDED_FOR"] = forwarded
        return self.client.post(reverse("password_reset"), {"email": email}, **extra)

    def test_the_eleventh_from_one_address_is_refused_without_looking_up_the_email(self):
        for _ in range(10):
            self._ask("x@example.com")
        response = self._ask("a@example.com")
        self.assertContains(response, f'<div class="error-box" role="alert">{TOO_MANY}</div>')
        self.assertNotContains(response, NOT_REGISTERED)
        self.assertEqual(mail.outbox, [])
        # Not looked up: an unknown email gets the same page, without 沒有註冊.
        response = self._ask("y@example.com")
        self.assertContains(response, TOO_MANY)
        self.assertNotContains(response, NOT_REGISTERED)

    def test_an_hour_later_it_works_again(self):
        for _ in range(10):
            self._ask("x@example.com")
        later = timezone.now() + timedelta(hours=1, seconds=1)
        # The database cache took its own name for now() when it loaded, so that is the one to move.
        with mock.patch("django.core.cache.backends.db.tz_now", return_value=later):
            response = self._ask("a@example.com")
        self.assertRedirects(response, reverse("password_reset_sent"))
        self.assertEqual(len(mail.outbox), 1)

    def test_the_hour_counts_from_the_first_attempt_not_the_latest(self):
        # Nine now and the tenth 50 minutes later: an hour after the first, the count is gone.
        start = time.time()

        def at(minutes):
            moved = start + minutes * 60
            return (
                mock.patch("time.time", return_value=moved),
                mock.patch(
                    "django.core.cache.backends.db.tz_now",
                    return_value=datetime.fromtimestamp(moved, tz=UTC),
                ),
            )

        for minutes, times in ((0, 9), (50, 1)):
            clock, cache_clock = at(minutes)
            with clock, cache_clock:
                for _ in range(times):
                    self._ask("x@example.com")
        clock, cache_clock = at(61)
        with clock, cache_clock:
            response = self._ask("a@example.com")
        self.assertRedirects(response, reverse("password_reset_sent"))

    def test_the_address_is_the_last_one_forwarded(self):
        for _ in range(10):
            self._ask("x@example.com", forwarded="1.1.1.1, 9.9.9.9")
        response = self._ask("a@example.com", forwarded="2.2.2.2, 9.9.9.9")
        self.assertContains(response, TOO_MANY)
        self.assertEqual(mail.outbox, [])

    def test_two_addresses_behind_the_same_proxy_count_apart(self):
        for _ in range(10):
            self._ask("x@example.com", forwarded="8.8.8.8")
        self.assertContains(self._ask("a@example.com", forwarded="8.8.8.8"), TOO_MANY)
        response = self._ask("a@example.com", forwarded="7.7.7.7")
        self.assertRedirects(response, reverse("password_reset_sent"))
        self.assertEqual(len(mail.outbox), 1)

    def test_the_fourth_email_to_one_email_in_an_hour_is_refused_from_any_address(self):
        for number in range(3):
            self._ask("a@example.com", forwarded=f"10.0.0.{number}")
        self.assertEqual(len(mail.outbox), 3)
        response = self._ask("A@example.com", forwarded="10.0.0.9")
        self.assertContains(response, f'<div class="error-box" role="alert">{TOO_MANY}</div>')
        self.assertEqual(len(mail.outbox), 3)

    def test_an_unknown_email_does_not_count_against_the_email(self):
        for _ in range(3):
            self._ask("x@example.com", forwarded="10.0.0.1")
        User.objects.create_user(username="late", email="x@example.com")
        response = self._ask("x@example.com", forwarded="10.0.0.2")
        self.assertRedirects(response, reverse("password_reset_sent"))

    def test_the_cache_keeps_no_address_or_email_as_typed(self):
        self._ask("a@example.com", forwarded="9.9.9.9")
        with connection.cursor() as cursor:
            cursor.execute("SELECT cache_key FROM password_reset_limits")
            keys = " ".join(row[0] for row in cursor.fetchall())
        self.assertTrue(keys)
        self.assertNotIn("9.9.9.9", keys)
        self.assertNotIn("a@example.com", keys)


class RefusingBackend(BaseEmailBackend):
    """A mail service that answers with an error naming the recipient, as Resend's can."""

    def send_messages(self, messages):
        raise OSError(f"Resend refused {messages[0].to[0]}")


class RefusingTheSecondEmailBackend(BaseEmailBackend):
    """Sends the first email and refuses the second. Django makes a backend for each email, so
    the count is kept on the class (SendFailureTests.setUp starts it at 0)."""

    calls = 0

    def send_messages(self, messages):
        RefusingTheSecondEmailBackend.calls += 1
        if RefusingTheSecondEmailBackend.calls == 2:
            raise OSError(f"Resend refused {messages[0].to[0]}")
        return len(messages)


SEND_FAILED = "信寄不出去，請稍後再試，或寫信到"


class SendFailureTests(TestCase):
    """#529 (spec #355): when the mail service fails, the page says so instead of pretending,
    keeps what was typed, and the owner sees the error in Sentry without the email in it."""

    def setUp(self):
        caches["password_reset"].clear()
        RefusingTheSecondEmailBackend.calls = 0
        consented_user(username="wang_ming", email="a@example.com", password=PASSWORD)

    def _ask(self):
        return self.client.post(reverse("password_reset"), {"email": "a@example.com"})

    @override_settings(EMAIL_BACKEND=f"{__name__}.RefusingBackend")
    def test_the_page_says_it_could_not_send_and_keeps_the_email(self):
        with self.assertLogs("screening.views.accounts", "ERROR"):
            response = self._ask()
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'<div class="error-box wrap-anywhere" role="alert"><span>{SEND_FAILED} '
            f'<a class="inline-link" href="mailto:{HELP_ADDRESS}">{HELP_ADDRESS}</a></span></div>',
            html=True,
        )
        self.assertContains(response, 'value="a@example.com"')
        self.assertNotIn(RESET_EMAIL, self.client.session)

    @override_settings(EMAIL_BACKEND=f"{__name__}.RefusingTheSecondEmailBackend")
    def test_one_of_two_failing_is_a_failure_too(self):
        consented_user(username="lin_mei", email="a@example.com", password=PASSWORD)
        with self.assertLogs("screening.views.accounts", "ERROR"):
            response = self._ask()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, SEND_FAILED)

    @override_settings(EMAIL_BACKEND=f"{__name__}.RefusingBackend")
    def test_the_log_has_the_error_but_not_the_email(self):
        with self.assertLogs("screening.views.accounts", "ERROR") as logs:
            self._ask()
        (record,) = logs.records
        self.assertIsNotNone(record.exc_info)
        self.assertNotIn("a@example.com", record.getMessage())
        self.assertEqual(record.args, ())

    def test_a_mistake_before_sending_stays_an_error(self):
        # Only the mail service failing reads as 信寄不出去; a broken email template is a bug.
        with mock.patch.object(forms.loader, "render_to_string", side_effect=ValueError("bug")):
            with self.assertRaises(ValueError):
                self._ask()
