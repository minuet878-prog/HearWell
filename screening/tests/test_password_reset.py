import re
from datetime import datetime, timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from screening.forms import PASSWORD_RULES
from screening.models import User
from screening.tests.helpers import consented_user

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
                response = self._ask(email)
                self.assertContains(response, NOT_REGISTERED)
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
        response = self._ask("i@example.com")
        self.assertContains(response, NOT_REGISTERED)
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
