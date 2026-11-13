"""Signing up and in with LINE (ticket #540, spec #506, ADR 0056, 0057, the #539 mockup B)."""

import base64
import hashlib
import json
from datetime import date, timedelta
from unittest import mock
from urllib.parse import parse_qsl, urlsplit

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from screening import models, oidc
from screening.models import Consent, GuestMonth, SignInMethod, User
from screening.models.guest_counts import count_guest_saved
from screening.tests import test_consent, test_line_in_app_browser
from screening.tests.helpers import (
    LINE_CHANNEL_ID,
    FakeGoogle,
    FakeLine,
    consented_user,
    google_on,
    line_on,
)

LINE_LOGIN = "使用 LINE 帳號登入"
LINE_REGISTER = "使用 LINE 帳號註冊"
GOOGLE_BUTTON = "使用 Google 帳戶"
FAILED_WORDS = "登入沒有完成，請再試一次。"
CANCELLED_WORDS = "沒有完成 LINE 登入，可以再試一次，或用其他方式登入。"  # W2
UNAVAILABLE_WORDS = "LINE 暫時沒有回應，請稍後再試，或用其他方式登入。"  # W3
EMAIL_HELP = "LINE 帳號不見時，可以用這個信箱設密碼登入。不填也可以。"  # W5
PASSWORD = "Xk9#mPq2vLw"


@override_settings(LINE_CLIENT_ID="", LINE_CLIENT_SECRET="")
class WithoutKeysTests(TestCase):
    """#506 acceptance 1: without the keys there is no LINE at all; the rest works as before."""

    def test_no_line_button_on_the_login_and_register_pages(self):
        for name in ("login", "register"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "LINE")

    def test_the_line_urls_are_404(self):
        for name in ("line_start", "line_callback", "line_name"):
            with self.subTest(url=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 404)
        self.assertEqual(self.client.post(reverse("line_name")).status_code, 404)

    def test_a_channel_id_without_its_secret_is_still_off(self):
        with override_settings(LINE_CLIENT_ID="only-the-id"):
            self.assertNotContains(self.client.get(reverse("login")), LINE_LOGIN)
            self.assertEqual(self.client.get(reverse("line_start")).status_code, 404)

    @google_on
    def test_google_and_the_password_form_stay(self):
        for name in ("login", "register"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, GOOGLE_BUTTON)
                self.assertContains(response, f'action="{reverse(name)}"')


@line_on
@google_on
class ButtonTests(TestCase):
    """#506 acceptance 2, 3 (the #539 mockup D1 B, D2, D3): LINE, then Google, then the form;
    inside LINE no Google, and the way out to Safari or Chrome under the form."""

    def assertInOrder(self, name, *texts, agent=test_line_in_app_browser.SAFARI):
        """Each text on the page comes after the one before it."""
        content = self.client.get(reverse(name), headers={"user-agent": agent}).content.decode()
        position = 0
        for text in texts:
            found = content.find(text, position)
            self.assertNotEqual(found, -1, f"{text} not after the text before it")
            position = found + len(text)

    def test_login_page_has_line_then_google_then_the_divider_then_the_form(self):
        self.assertInOrder(
            "login",
            LINE_LOGIN,
            "使用 Google 帳戶登入",
            "或用帳號密碼",
            f'action="{reverse("login")}"',
        )

    def test_register_page_has_line_then_google_then_the_divider_then_the_form(self):
        self.assertInOrder(
            "register",
            LINE_REGISTER,
            "使用 Google 帳戶註冊",
            "或填寫資料註冊",
            f'action="{reverse("register")}"',
        )

    def test_nothing_about_line_or_safari_comes_after_the_form_outside_line(self):
        content = self.client.get(reverse("login")).content.decode()
        self.assertEqual(content.count(LINE_LOGIN), 1)
        self.assertNotIn(test_line_in_app_browser.OPEN_OUTSIDE, content)

    def test_the_line_button_looks_like_googles_with_lines_icon(self):
        # D1 B: the same white, grey-bordered button, LINE's green icon on the left.
        response = self.client.get(reverse("login"))
        self.assertContains(
            response,
            f'<a class="btn btn-lg btn-provider" href="{reverse("line_start")}">',
        )
        self.assertContains(response, 'class="btn-line-logo"')

    def test_the_button_carries_next_on(self):
        for name in ("login", "register"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name), {"next": "/questionnaire_list"})
                self.assertContains(
                    response, f'href="{reverse("line_start")}?next=/questionnaire_list"'
                )

    def test_inside_line_there_is_line_and_no_google(self):
        for agent in (test_line_in_app_browser.LINE_IOS, test_line_in_app_browser.LINE_ANDROID):
            for name, words in (("login", LINE_LOGIN), ("register", LINE_REGISTER)):
                with self.subTest(agent=agent[-20:], page=name):
                    response = self.client.get(reverse(name), headers={"user-agent": agent})
                    self.assertContains(response, words)
                    self.assertNotContains(response, GOOGLE_BUTTON)
                    self.assertContains(response, f'action="{reverse(name)}"')

    def test_inside_line_the_way_out_is_under_the_password_form(self):
        for name, words in (("login", LINE_LOGIN), ("register", LINE_REGISTER)):
            with self.subTest(page=name):
                self.assertInOrder(
                    name,
                    words,
                    f'action="{reverse(name)}"',
                    "</form>",
                    test_line_in_app_browser.OPEN_OUTSIDE,
                    agent=test_line_in_app_browser.LINE_IOS,
                )

    def test_only_line_without_google(self):
        with override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET=""):
            response = self.client.get(reverse("login"))
        self.assertContains(response, LINE_LOGIN)
        self.assertContains(response, "或用帳號密碼")
        self.assertNotContains(response, GOOGLE_BUTTON)


@line_on
class StartTests(TestCase):
    """#506 acceptance 4: the trip to LINE, and what our server sends LINE on the way back."""

    def setUp(self):
        self.line = FakeLine(self.client)

    def test_the_authorize_url_asks_for_openid_only_with_state_nonce_and_pkce(self):
        self.line.start()
        query = self.line.authorize
        self.assertEqual(query["response_type"], "code")
        self.assertEqual(query["client_id"], LINE_CHANNEL_ID)
        self.assertEqual(query["scope"], "openid")
        self.assertEqual(query["redirect_uri"], "https://tingpal.test/login/line/callback")
        self.assertEqual(query["code_challenge_method"], "S256")
        for name in ("state", "nonce", "code_challenge"):
            self.assertGreaterEqual(len(query[name]), 32, name)
        self.assertNotIn("prompt", query)

    def test_each_trip_has_its_own_state_nonce_and_pkce(self):
        self.line.start()
        first = self.line.authorize
        self.line.start()
        for name in ("state", "nonce", "code_challenge"):
            self.assertNotEqual(first[name], self.line.authorize[name], name)

    def test_the_code_goes_to_lines_token_endpoint_with_the_verifier(self):
        self.line.start()
        self.line.come_back()
        endpoint, fields = self.line.calls[0]
        self.assertEqual(endpoint, "token")
        digest = hashlib.sha256(fields["code_verifier"].encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        self.assertEqual(challenge, self.line.authorize["code_challenge"])
        self.assertEqual(
            fields,
            {
                "grant_type": "authorization_code",
                "code": "line-auth-code",
                "code_verifier": fields["code_verifier"],
                "redirect_uri": "https://tingpal.test/login/line/callback",
                "client_id": LINE_CHANNEL_ID,
                "client_secret": "line-test-secret",
            },
        )

    def test_the_id_token_is_verified_at_line_with_our_channel_and_this_trips_nonce(self):
        self.line.start()
        self.line.come_back()
        endpoint, fields = self.line.calls[1]
        self.assertEqual(endpoint, "verify")
        self.assertEqual(
            fields,
            {
                "id_token": "line-id-token",
                "client_id": LINE_CHANNEL_ID,
                "nonce": self.line.authorize["nonce"],
            },
        )

    @override_settings(ALLOWED_HOSTS=["tingpal.test", "evil.example"])
    def test_a_forged_host_header_does_not_change_the_callback_url(self):
        response = self.client.get(reverse("line_start"), headers={"host": "evil.example"})
        query = dict(parse_qsl(urlsplit(response["Location"]).query))
        self.assertEqual(query["redirect_uri"], "https://tingpal.test/login/line/callback")


@line_on
class FirstTimeTests(TestCase):
    """#506 acceptance 5-8: the first time back from LINE, the name page with an optional email."""

    def setUp(self):
        self.line = FakeLine(self.client)

    def _to_name_page(self, **start):
        self.line.start(**start)
        return self.line.come_back(sub="line-new")

    def _name(self, username="陳阿蘭", roc_birth_year="", email=""):
        return self.client.post(
            reverse("line_name"),
            {"username": username, "roc_birth_year": roc_birth_year, "email": email},
        )

    # 5
    def test_back_from_line_goes_to_the_name_page_without_an_account(self):
        response = self._to_name_page()
        self.assertRedirects(response, reverse("line_name"))
        self.assertEqual(User.objects.count(), 0)
        page = self.client.get(reverse("line_name"))
        self.assertContains(page, '<label for="id_username">使用者名稱</label>', html=True)
        self.assertContains(
            page, '<label for="id_roc_birth_year">出生年（選填）</label>', html=True
        )
        # W4, W5 (the #539 mockup, rewording the spec's help line).
        self.assertContains(page, '<label for="id_email">電子郵件（選填）</label>', html=True)
        self.assertContains(page, EMAIL_HELP)
        self.assertContains(page, 'type="email"')
        # W6.
        self.assertContains(page, "已經有帳號了嗎？")
        self.assertContains(
            page, "先用原本的方式登入，再到帳號設定新增 LINE 登入，紀錄才會在同一個帳號。"
        )
        self.assertContains(
            page, f'<a class="inline-link" href="{reverse("login")}">用其他方式登入</a>', html=True
        )
        self.assertNotContains(page, "來自")
        self.assertNotContains(page, 'type="password"')
        self.assertIn("no-store", page["Cache-Control"])
        self.assertEqual(User.objects.count(), 0)

    # 6
    def test_without_an_email_makes_the_account_signs_in_and_goes_to_consent(self):
        self._to_name_page()
        response = self._name("陳阿蘭", roc_birth_year="40")
        self.assertRedirects(response, reverse("consent"))
        user = User.objects.get()
        self.assertEqual((user.username, user.birth_year, user.email), ("陳阿蘭", 1951, ""))
        self.assertFalse(user.has_usable_password())
        method = SignInMethod.objects.get()
        self.assertEqual(
            (method.user, method.provider, method.subject, method.used_to_register),
            (user, "line", "line-new", True),
        )
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        # As registering with a password does: the consent page greets a new account.
        self.assertTrue(self.client.session["screening.new_account"])

    # 7
    def test_a_malformed_email_gets_the_register_pages_error(self):
        registering = self.client.post(reverse("register"), {"email": "not-an-email"})
        self._to_name_page()
        response = self._name(email="not-an-email")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors["email"],
            registering.context["form"].errors["email"],
        )
        self.assertEqual(User.objects.count(), 0)

    def test_an_email_becomes_the_accounts(self):
        self._to_name_page()
        self._name(email="chen.lan@example.com")
        self.assertEqual(User.objects.get().email, "chen.lan@example.com")

    # 8
    def test_an_email_already_on_an_account_still_makes_the_account(self):
        consented_user(username="林阿美", email="chen.lan@example.com", password=PASSWORD)
        response = self._to_name_page()
        self.assertRedirects(response, reverse("line_name"))
        self.assertRedirects(self._name(email="Chen.Lan@example.com"), reverse("consent"))
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(SignInMethod.objects.get().user.username, "陳阿蘭")

    def test_a_taken_name_gets_the_same_error_as_registering(self):
        User.objects.create_user(username="陳阿蘭", password="x")
        registering = self.client.post(reverse("register"), {"username": "陳阿蘭"})
        self._to_name_page()
        response = self._name("陳阿蘭")
        self.assertEqual(
            response.context["form"].errors["username"],
            registering.context["form"].errors["username"],
        )
        self.assertEqual(User.objects.count(), 1)

    def test_a_birth_year_out_of_range_gets_the_register_pages_error(self):
        self._to_name_page()
        self.assertContains(self._name(roc_birth_year="200"), "請輸入民國 1 到")
        self.assertEqual(User.objects.count(), 0)

    def test_after_10_minutes_the_name_page_makes_nothing(self):
        self._to_name_page()
        later = timezone.now() + timedelta(minutes=10, seconds=1)
        with mock.patch("django.utils.timezone.now", return_value=later):
            response = self._name()
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), 0)
        self.assertContains(
            self.client.get(reverse("login")), "等太久了，請再按一次「使用 LINE 帳號登入」。"
        )

    def test_the_name_page_is_used_once(self):
        self._to_name_page()
        self._name("陳阿蘭")
        self.assertRedirects(self._name("別人"), reverse("login"), fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), 1)

    @google_on
    def test_a_google_identity_waiting_is_not_lines(self):
        google = FakeGoogle(self.client)
        google.start()
        google.come_back(sub="google-new")  # waiting on the Google name page
        self.assertRedirects(
            self.client.get(reverse("line_name")), reverse("login"), fetch_redirect_response=False
        )
        self.assertEqual(self._name().status_code, 302)
        self.assertEqual(User.objects.count(), 0)

    def test_agreeing_goes_on_to_next_as_registering_does(self):
        target = reverse("questionnaire_list")
        self._to_name_page(next=target)
        self.assertRedirects(self._name(), test_consent._consent_url(target))


@line_on
class RevokeTests(TestCase):
    """#506 acceptance 9: the access token LINE gives is revoked straight away; a revoke that
    fails goes to error monitoring and signs in all the same."""

    def setUp(self):
        self.line = FakeLine(self.client)
        self.user = consented_user(username="陳阿蘭")
        SignInMethod.objects.create(user=self.user, provider="line", subject="line-1")
        self.line.start()

    def test_the_access_token_is_revoked_after_the_id_token_is_verified(self):
        self.line.come_back(sub="line-1")
        self.assertEqual(self.line.endpoints(), ["token", "verify", "revoke"])
        self.assertEqual(
            self.line.calls[2][1],
            {
                "access_token": "line-access-token",
                "client_id": LINE_CHANNEL_ID,
                "client_secret": "line-test-secret",
            },
        )
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_a_first_time_trip_revokes_too(self):
        self.assertRedirects(self.line.come_back(sub="line-new"), reverse("line_name"))
        self.assertEqual(self.line.endpoints(), ["token", "verify", "revoke"])

    def test_a_revoke_that_fails_signs_in_and_goes_to_monitoring(self):
        for name, revoke in (
            ("no answer", oidc.Unavailable("https://api.line.me/oauth2/v2.1/revoke: URLError")),
            ("refused", {"error": "invalid_request", "error_description": "invalid token"}),
        ):
            with self.subTest(name):
                self.client.logout()
                self.line.start()
                with self.assertLogs("screening.oidc", "ERROR") as logs:
                    response = self.line.come_back(sub="line-1", revoke=revoke)
                self.assertRedirects(response, reverse("consent"), target_status_code=302)
                self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
                output = "\n".join(logs.output)
                self.assertIn("LINE access token not revoked", output)
                self.assertNotIn("line-access-token", output)

    def test_an_id_token_line_refuses_still_has_its_access_token_revoked(self):
        with self.assertLogs("screening.views.sign_in", "ERROR"):
            self.line.come_back(sub="line-1", nonce="other")
        self.assertEqual(self.line.endpoints(), ["token", "verify", "revoke"])
        self.assertNotIn("_auth_user_id", self.client.session)


@line_on
class AgainTests(TestCase):
    """#506 acceptance 10 and 22 (signing in): signing in again with LINE."""

    def setUp(self):
        self.line = FakeLine(self.client)
        self.user = consented_user(username="陳阿蘭")
        self.user.set_unusable_password()
        self.user.save()
        SignInMethod.objects.create(
            user=self.user, provider="line", subject="line-1", used_to_register=True
        )

    # 10
    def test_the_same_code_signs_in_the_same_account(self):
        self.line.start()
        response = self.line.come_back(sub="line-1")
        self.assertRedirects(response, reverse("consent"), target_status_code=302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(SignInMethod.objects.count(), 1)

    def test_signing_in_again_goes_back_to_next(self):
        target = reverse("my_hearing")
        self.line.start(next=target)
        self.assertRedirects(self.line.come_back(sub="line-1"), target)

    @google_on
    def test_the_same_code_from_google_is_another_identity(self):
        google = FakeGoogle(self.client)
        google.start()
        self.assertRedirects(google.come_back(sub="line-1"), reverse("google_name"))
        self.assertNotIn("_auth_user_id", self.client.session)

    # 22
    def test_an_admin_account_is_not_signed_in(self):
        for flags in ({"is_staff": True}, {"is_superuser": True}):
            with self.subTest(**flags):
                User.objects.filter(pk=self.user.pk).update(
                    **{"is_staff": False, "is_superuser": False} | flags
                )
                self.line.start()
                response = self.line.come_back(sub="line-1")
                self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
                self.assertNotIn("_auth_user_id", self.client.session)
                self.assertContains(self.client.get(reverse("login")), "這個帳號請用帳號密碼登入。")

    def test_a_deactivated_account_is_not_signed_in(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.line.start()
        self.assertRedirects(self.line.come_back(sub="line-1"), reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)


@line_on
class CallbackSecurityTests(TestCase):
    """#506 acceptance 11-14: a forged, replayed, late or cancelled callback, or an ID token LINE
    or our own checks refuse, signs no one in. The code line-1 belongs to an account, so a check
    that let it through would sign it in."""

    def setUp(self):
        self.line = FakeLine(self.client)
        self.user = consented_user(username="陳阿蘭")
        SignInMethod.objects.create(user=self.user, provider="line", subject="line-1")
        self.line.start()

    def assertRejected(self, response, message=FAILED_WORDS):
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(self.client.get(reverse("login")), message)

    def test_the_real_callback_signs_in(self):
        # The other tests' baseline: unchanged, this callback does sign the account in.
        self.line.come_back(sub="line-1")
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    # 11
    def test_a_callback_not_this_trips_is_rejected_without_calling_line(self):
        state = self.line.authorize["state"]
        for name, query in (
            (
                "different state",
                {"code": "c", "state": state[:-1] + ("A" if state[-1] != "A" else "B")},
            ),
            ("no state", {"code": "c"}),
            ("not ascii", {"code": "c", "state": "中"}),
        ):
            with self.subTest(name):
                self.line.start()
                with self.assertLogs("screening.views.sign_in", "ERROR"):
                    self.assertRejected(self.line.come_back(query=query))
        self.assertEqual(self.line.calls, [])

    def test_a_used_state_is_rejected_without_calling_line(self):
        query = {"code": "c", "state": self.line.authorize["state"]}
        self.line.come_back(sub="line-new", query=query)  # to the name page, not signed in
        self.line.calls.clear()
        with self.assertLogs("screening.views.sign_in", "ERROR"):
            self.assertRejected(self.line.come_back(sub="line-1", query=query))
        self.assertEqual(self.line.calls, [])

    def test_more_than_10_minutes_after_leaving_is_rejected_without_calling_line(self):
        later = timezone.now() + timedelta(minutes=10, seconds=1)
        with (
            mock.patch("django.utils.timezone.now", return_value=later),
            self.assertLogs("screening.views.sign_in", "ERROR"),
        ):
            response = self.line.come_back(sub="line-1")
        self.assertRejected(response)
        self.assertEqual(self.line.calls, [])

    # 12
    def test_an_id_token_line_refuses_is_rejected(self):
        for description in ("Invalid IdToken Nonce.", "IdToken expired.", "Invalid IdToken."):
            with self.subTest(description):
                self.line.start()
                refusal = {"error": "invalid_request", "error_description": description}
                with self.assertLogs("screening.views.sign_in", "ERROR") as logs:
                    self.assertRejected(self.line.come_back(sub="line-1", verify=refusal))
                self.assertIn("LINE callback rejected", logs.output[0])

    def test_what_line_verified_is_checked_again(self):
        past = int(timezone.now().timestamp()) - 1
        for name, claims in (
            ("another nonce", {"nonce": "other"}),
            ("no nonce", {"nonce": None}),
            ("another channel", {"aud": "1659999999"}),
            ("another issuer", {"iss": "https://evil.example"}),
            ("google as issuer", {"iss": "https://accounts.google.com"}),
            ("expired", {"exp": past}),
            ("no sub", {"sub": None}),
        ):
            with self.subTest(name):
                self.line.start()
                with self.assertLogs("screening.views.sign_in", "ERROR"):
                    self.assertRejected(self.line.come_back(**({"sub": "line-1"} | claims)))

    def test_a_rejected_callback_goes_to_monitoring_without_its_secrets(self):
        state = self.line.authorize["state"]
        with self.assertLogs("screening.views.sign_in", "ERROR") as logs:
            self.line.come_back(sub="line-1", nonce="other")
        output = "\n".join(logs.output)
        for secret in (state, "line-auth-code", "line-access-token", "line-id-token", "line-1"):
            self.assertNotIn(secret, output)

    # 13
    def test_cancelling_on_line_comes_back_to_login_with_words(self):
        self.assertRejected(self.line.come_back(cancelled=True), CANCELLED_WORDS)
        self.assertEqual(self.line.calls, [])
        self.assertNotIn("screening.oidc_flow", self.client.session)

    def test_a_cancel_is_believed_only_for_this_trip(self):
        with self.assertLogs("screening.views.sign_in", "ERROR"):
            self.assertRejected(
                self.line.come_back(query={"error": "ACCESS_DENIED", "state": "forged"})
            )

    # 14
    def test_access_denied_in_any_case_is_a_cancel(self):
        query = {"error": "access_denied", "state": self.line.authorize["state"]}
        self.assertRejected(self.line.come_back(query=query), CANCELLED_WORDS)

    def test_any_other_error_on_the_callback_is_line_not_answering(self):
        # Only ACCESS_DENIED is the user pressing cancel; any other error LINE sends back is LINE
        # not answering.
        for error in ("SERVER_ERROR", "INVALID_REQUEST", "INTERACTION_REQUIRED"):
            with self.subTest(error):
                self.line.start()
                query = {"error": error, "state": self.line.authorize["state"]}
                with self.assertLogs("screening.views.sign_in", "ERROR"):
                    response = self.line.come_back(query=query)
                self.assertRejected(response, UNAVAILABLE_WORDS)
        self.assertEqual(self.line.calls, [])

    def test_the_callbacks_error_text_never_reaches_the_logs(self):
        # Anyone holding this trip's state can write anything into `error` (cross-review of
        # #506, Standards 3): the log lines and their tracebacks are fixed words.
        crafted = "SERVER_ERROR chen.lan@example.com"
        query = {
            "error": crafted,
            "error_description": "chen.lan",
            "state": self.line.authorize["state"],
        }
        with self.assertLogs("screening", "DEBUG") as logs:
            self.assertRejected(self.line.come_back(query=query), UNAVAILABLE_WORDS)
        output = "\n".join(logs.output)
        self.assertIn("LINE token exchange failed", output)
        self.assertNotIn("chen.lan", output)

    def test_an_error_on_a_callback_not_this_trips_is_rejected(self):
        with self.assertLogs("screening.views.sign_in", "ERROR") as logs:
            response = self.line.come_back(query={"error": "SERVER_ERROR", "state": "forged"})
        self.assertRejected(response)
        self.assertIn("LINE callback rejected", logs.output[0])

    def test_line_not_answering_comes_back_to_login_and_goes_to_monitoring(self):
        down = oidc.Unavailable("https://api.line.me/oauth2/v2.1/token: URLError")
        for name, come_back in (
            ("token endpoint down", {"token": down}),
            ("token endpoint error", {"token": {"error": "invalid_grant"}}),
            ("verify endpoint down", {"verify": down}),
        ):
            with self.subTest(name):
                self.line.start()
                with self.assertLogs("screening.views.sign_in", "ERROR") as logs:
                    response = self.line.come_back(sub="line-1", **come_back)
                self.assertRejected(response, UNAVAILABLE_WORDS)
                self.assertIn("LINE token exchange failed", logs.output[0])


class SignInMethodDataTests(TestCase):
    """#506 acceptance 26: LINE in 下載我的資料, without any token."""

    def test_the_download_lists_line_without_tokens(self):
        user = consented_user(username="陳阿蘭", password=PASSWORD)
        method = SignInMethod.objects.create(
            user=user, provider="line", subject="U4af4980629", used_to_register=True
        )
        self.client.force_login(user)
        response = self.client.get(reverse("download_my_data"))
        data = json.loads(response.content)
        self.assertEqual(
            data["sign_in_methods"],
            [
                {
                    "provider": "LINE",
                    "subject": "U4af4980629",
                    "created_at": timezone.localtime(method.created_at).isoformat(),
                    "used_to_register": True,
                }
            ],
        )
        self.assertNotIn("token", response.content.decode())


class GuestCountTests(TestCase):
    """#506 acceptance 25, its column (the save card's LINE button is #543): an account made with
    LINE that saves a guest result counts in 保存's LINE column."""

    def test_an_account_made_with_line_counts_in_the_line_column(self):
        user = User.objects.create_user(username="陳阿蘭")
        SignInMethod.objects.create(user=user, provider="line", subject="U1", used_to_register=True)
        count_guest_saved(user)
        self.assertEqual(
            list(GuestMonth.objects.values_list("saved_password", "saved_google", "saved_line")),
            [(0, 0, 1)],
        )


class PrivacyTests(TestCase):
    """#506 acceptance 27: the privacy notice says what LINE gives, in a new version."""

    def test_the_privacy_notice_says_what_line_gives_and_what_it_does_not(self):
        response = self.client.get(reverse("privacy"))
        self.assertContains(response, "用 LINE 登入時")
        self.assertContains(
            response,
            "只拿 LINE 給您的代號，不拿您在 LINE 的名稱、大頭貼、email 和好友名單。",
        )
        self.assertContains(response, "拿到代號後，馬上請 LINE 作廢它給的權杖")
        self.assertContains(response, "登入完成後，不會再跟 LINE 拿任何資料。")

    def test_the_consent_highlights_say_it_too(self):
        self.assertContains(
            self.client.get(reverse("privacy")),
            "用 LINE 登入時，只拿 LINE 給您的代號，不拿名稱、大頭貼、email 和好友名單。",
        )

    def test_version_8_with_its_date(self):
        # Version 7 (Google, spec #505) is already live: LINE is one more. Its date is set the
        # day version 8 goes live, not before version 7's.
        self.assertEqual(models.CONSENT_VERSION, 8)
        self.assertGreaterEqual(models.PRIVACY_UPDATED_ON, date(2026, 11, 14))
        updated_on = models.PRIVACY_UPDATED_ON.strftime("%Y/%m/%d")
        self.assertContains(self.client.get(reverse("privacy")), f"第 8 版，{updated_on} 更新")

    def test_who_agreed_to_version_7_agrees_again(self):
        user = User.objects.create_user(username="agreed_to_7")
        Consent.objects.create(user=user, version=7)
        self.client.force_login(user)
        url = reverse("my_hearing")
        self.assertRedirects(self.client.get(url), test_consent._consent_url(url))
        self.assertContains(self.client.get(test_consent._consent_url(url)), "用 LINE 登入時")
