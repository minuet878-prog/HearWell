import base64
import hashlib
import json
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock
from urllib.parse import parse_qsl, urlsplit

from django.db import DatabaseError, connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening import models, oidc
from screening.forms import GoogleNameForm
from screening.models import (
    Answer,
    Audiogram,
    AudiogramPoint,
    Category,
    Consent,
    Question,
    Questionnaire,
    SignInMethod,
    Submission,
    User,
)
from screening.tests import test_consent
from screening.tests.helpers import GOOGLE_CLIENT_ID, FakeGoogle, consented_user, google_on

GOOGLE_BUTTON = "使用 Google 帳戶"
FAILED_WORDS = "登入沒有完成，請再試一次。"
PASSWORD = "Xk9#mPq2vLw"


@override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
class WithoutKeysTests(TestCase):
    """#505 acceptance 1: without the keys there is no Google at all."""

    def test_no_button_on_the_login_and_register_pages(self):
        for name in ("login", "register"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, GOOGLE_BUTTON)

    def test_the_google_urls_are_404(self):
        for name in ("google_start", "google_callback", "google_name"):
            with self.subTest(url=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 404)
        self.assertEqual(self.client.post(reverse("google_name")).status_code, 404)

    def test_a_client_id_without_its_secret_is_still_off(self):
        with override_settings(GOOGLE_CLIENT_ID="only-the-id"):
            self.assertNotContains(self.client.get(reverse("login")), GOOGLE_BUTTON)
            self.assertEqual(self.client.get(reverse("google_start")).status_code, 404)


@google_on
class ButtonTests(TestCase):
    """#505 acceptance 2 (the #507 mockup D1 甲, D2, W1, W2): the button above the form."""

    def test_login_page_has_the_button_above_the_form_then_the_divider(self):
        content = self.client.get(reverse("login")).content.decode()
        button = content.index("使用 Google 帳戶登入")
        divider = content.index("或用帳號密碼")
        form = content.index(f'action="{reverse("login")}"')
        self.assertLess(button, divider)
        self.assertLess(divider, form)

    def test_register_page_has_the_button_above_the_form_then_the_divider(self):
        content = self.client.get(reverse("register")).content.decode()
        button = content.index("使用 Google 帳戶註冊")
        divider = content.index("或填寫資料註冊")
        form = content.index(f'action="{reverse("register")}"')
        self.assertLess(button, divider)
        self.assertLess(divider, form)

    def test_the_button_carries_next_on(self):
        target = reverse("questionnaire_list")
        for name in ("login", "register"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name), {"next": target})
                self.assertContains(
                    response, f'href="{reverse("google_start")}?next=/questionnaire_list"'
                )


@google_on
class StartTests(TestCase):
    """#505 acceptance 4 and 21: the trip to Google."""

    def setUp(self):
        self.google = FakeGoogle(self.client)

    def test_the_authorize_url_asks_for_openid_email_with_state_nonce_and_pkce(self):
        self.google.start()
        query = self.google.authorize
        self.assertEqual(query["response_type"], "code")
        self.assertEqual(query["client_id"], GOOGLE_CLIENT_ID)
        self.assertEqual(query["scope"], "openid email")
        self.assertEqual(query["redirect_uri"], "https://tingpal.test/login/google/callback")
        self.assertEqual(query["code_challenge_method"], "S256")
        for name in ("state", "nonce", "code_challenge"):
            self.assertGreaterEqual(len(query[name]), 32, name)

    def test_each_trip_has_its_own_state_nonce_and_pkce(self):
        self.google.start()
        first = self.google.authorize
        self.google.start()
        for name in ("state", "nonce", "code_challenge"):
            self.assertNotEqual(first[name], self.google.authorize[name], name)

    def test_the_verifier_sent_on_the_way_back_hashes_to_the_challenge(self):
        self.google.start()
        self.google.come_back()
        verifier = self.google.exchanges[0]["code_verifier"]
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        self.assertEqual(challenge, self.google.authorize["code_challenge"])
        self.assertNotEqual(verifier, self.google.authorize["code_challenge"])
        self.assertEqual(
            self.google.exchanges[0]["redirect_uri"], "https://tingpal.test/login/google/callback"
        )
        self.assertEqual(self.google.exchanges[0]["code"], "auth-code")

    # 21
    @override_settings(ALLOWED_HOSTS=["tingpal.test", "evil.example"])
    def test_a_forged_host_header_does_not_change_the_callback_url(self):
        response = self.client.get(reverse("google_start"), headers={"host": "evil.example"})
        query = dict(parse_qsl(urlsplit(response["Location"]).query))
        self.assertEqual(query["redirect_uri"], "https://tingpal.test/login/google/callback")


@google_on
class FirstTimeTests(TestCase):
    """#505 acceptance 5-9: the first time back from Google."""

    def setUp(self):
        self.google = FakeGoogle(self.client)

    def _to_name_page(self, **start):
        self.google.start(**start)
        return self.google.come_back(sub="google-new", email="lin.mei@example.com")

    def _name(self, username="林阿美", roc_birth_year=""):
        return self.client.post(
            reverse("google_name"), {"username": username, "roc_birth_year": roc_birth_year}
        )

    # 5
    def test_back_from_google_goes_to_the_name_page_without_an_account(self):
        response = self._to_name_page()
        self.assertRedirects(response, reverse("google_name"))
        self.assertEqual(User.objects.count(), 0)
        page = self.client.get(reverse("google_name"))
        # The owner's call on the #505 review: the label says it becomes the account's email.
        self.assertContains(
            page, '<dt class="settings-row-note">帳號的電子郵件（來自 Google）</dt>', html=True
        )
        self.assertContains(page, "lin.mei@example.com")
        self.assertContains(page, '<label for="id_username">使用者名稱</label>', html=True)
        self.assertContains(
            page, '<label for="id_roc_birth_year">出生年（選填）</label>', html=True
        )
        self.assertContains(
            page, "先用帳號密碼登入，再到帳號設定新增 Google 登入，紀錄才會在同一個帳號。"
        )
        self.assertContains(page, f'href="{reverse("login")}"')
        self.assertNotContains(page, 'type="password"')
        self.assertEqual(User.objects.count(), 0)
        self.assertIn("no-store", page["Cache-Control"])

    # 6
    def test_a_taken_name_gets_the_same_error_as_registering(self):
        User.objects.create_user(username="林阿美", password="x")
        registering = self.client.post(reverse("register"), {"username": "林阿美"})
        self._to_name_page()
        response = self._name("林阿美")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors["username"],
            registering.context["form"].errors["username"],
        )
        self.assertEqual(User.objects.count(), 1)

    def test_the_google_made_an_account_meanwhile_is_a_failed_sign_in_not_an_error(self):
        # Codex review Spec 5: the name page sent twice, the first making the account between the
        # second's check and its insert. The second makes nothing and says try again.
        self._to_name_page()
        real_is_valid = GoogleNameForm.is_valid

        def first_send_made_it(form):
            valid = real_is_valid(form)
            first = User.objects.create_user(username="第一次送出")
            SignInMethod.objects.create(user=first, provider="google", subject="google-new")
            return valid

        with mock.patch.object(GoogleNameForm, "is_valid", first_send_made_it):
            response = self._name("第二次送出")
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("login")), FAILED_WORDS)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(list(User.objects.values_list("username", flat=True)), ["第一次送出"])
        # Google again now signs into the account the first send made.
        self.google.start()
        self.google.come_back(sub="google-new")
        self.assertEqual(
            int(self.client.session["_auth_user_id"]), User.objects.get(username="第一次送出").pk
        )

    def test_a_name_differing_only_in_case_is_taken_too(self):
        User.objects.create_user(username="Ming", password="x")
        self._to_name_page()
        self.assertEqual(self._name("ming").status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_a_birth_year_out_of_range_gets_the_register_pages_error(self):
        self._to_name_page()
        response = self._name(roc_birth_year="200")
        self.assertContains(response, "請輸入民國 1 到")
        self.assertEqual(User.objects.count(), 0)

    # 6
    def test_naming_makes_the_account_signs_in_and_goes_to_consent(self):
        self._to_name_page()
        response = self._name("林阿美", roc_birth_year="45")
        self.assertRedirects(response, reverse("consent"))
        user = User.objects.get()
        self.assertEqual(user.username, "林阿美")
        self.assertEqual(user.birth_year, 1956)
        self.assertEqual(user.email, "lin.mei@example.com")
        self.assertFalse(user.has_usable_password())
        method = SignInMethod.objects.get()
        self.assertEqual(
            (method.user, method.provider, method.subject, method.used_to_register),
            (user, "google", "google-new", True),
        )
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_the_name_page_is_used_once(self):
        self._to_name_page()
        self._name("林阿美")
        response = self._name("別人")  # still signed in as 林阿美, whose session it was
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), 1)

    # 7
    def test_after_10_minutes_the_name_page_makes_nothing(self):
        self._to_name_page()
        later = timezone.now() + timedelta(minutes=10, seconds=1)
        with mock.patch("django.utils.timezone.now", return_value=later):
            response = self._name("林阿美")
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), 0)
        self.assertContains(
            self.client.get(reverse("login")), "等太久了，請再按一次「使用 Google 帳戶登入」。"
        )

    def test_within_10_minutes_the_name_page_still_works(self):
        self._to_name_page()
        later = timezone.now() + timedelta(minutes=9, seconds=50)
        with mock.patch("django.utils.timezone.now", return_value=later):
            self._name("林阿美")
        self.assertEqual(User.objects.count(), 1)

    def test_the_name_page_without_google_sends_to_login(self):
        self.assertRedirects(self.client.get(reverse("google_name")), reverse("login"))

    # 8
    def test_agreeing_goes_on_into_the_wizard_as_registering_does(self):
        target = reverse("questionnaire_list")
        self._to_name_page(next=target)
        response = self._name("林阿美")
        self.assertRedirects(response, test_consent._consent_url(target))
        response = self.client.post(reverse("consent"), {"agree": "", "next": target})
        self.assertRedirects(response, f"{target}?from=consent", fetch_redirect_response=False)
        self.assertTrue(User.objects.get().has_consented())

    def test_from_the_plain_login_page_agreeing_goes_where_registering_does(self):
        # Codex review Spec 4: the register page without a next (its link in the header) goes
        # home after agreeing; Google from the plain login page goes the same way.
        password = test_consent.PASSWORD
        self.client.post(
            reverse("register"),
            {
                "username": "密碼註冊",
                "email": "pw@example.com",
                "password1": password,
                "password2": password,
            },
        )
        registering = self.client.post(reverse("consent"), {"agree": ""})
        self.assertRedirects(registering, reverse("index"), fetch_redirect_response=False)
        self.client.logout()

        self._to_name_page()
        self.assertRedirects(self._name("林阿美"), reverse("consent"))
        response = self.client.post(reverse("consent"), {"agree": ""})
        self.assertRedirects(response, registering.url, fetch_redirect_response=False)
        self.assertTrue(User.objects.get(username="林阿美").has_consented())

    def test_declining_signs_out_and_keeps_the_account_with_no_records(self):
        self._to_name_page()
        self._name("林阿美")
        response = self.client.post(reverse("consent"), {"decline": ""})
        self.assertRedirects(response, reverse("index"))
        self.assertNotIn("_auth_user_id", self.client.session)
        user = User.objects.get()
        self.assertFalse(user.consents.exists())
        self.assertFalse(user.submissions.exists())

    # 9
    def test_an_unverified_email_makes_no_account(self):
        self.google.start()
        for verified in (False, "false", None):
            with self.subTest(email_verified=verified):
                self.google.start()
                response = self.google.come_back(sub="google-new", email_verified=verified)
                self.assertRedirects(response, reverse("register"), fetch_redirect_response=False)
                self.assertNotIn("screening.oidc_identity", self.client.session)
                self.assertContains(
                    self.client.get(reverse("register")),
                    "這個 Google 帳戶的 email 還沒有驗證，沒辦法用來註冊。請改用帳號密碼註冊。",
                )
        self.assertEqual(self.client.get(reverse("google_name")).status_code, 302)
        self.assertEqual(User.objects.count(), 0)


@google_on
class AgainTests(TestCase):
    """#505 acceptance 10, 11: signing in again."""

    def setUp(self):
        self.google = FakeGoogle(self.client)
        self.user = consented_user(username="林阿美", email="lin.mei@example.com")
        self.user.set_unusable_password()
        self.user.save()
        SignInMethod.objects.create(
            user=self.user, provider="google", subject="google-1", used_to_register=True
        )

    # 10
    def test_the_same_code_signs_in_the_same_account(self):
        self.google.start()
        response = self.google.come_back(sub="google-1", email="new.address@example.com")
        self.assertRedirects(response, reverse("consent"), target_status_code=302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(SignInMethod.objects.count(), 1)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "lin.mei@example.com")

    def test_signing_in_again_goes_back_to_next(self):
        target = reverse("my_hearing")
        self.google.start(next=target)
        self.assertRedirects(self.google.come_back(sub="google-1"), target)

    def test_next_to_another_site_is_dropped(self):
        self.google.start(next="https://evil.example/")
        response = self.google.come_back(sub="google-1")
        self.assertRedirects(response, reverse("consent"), target_status_code=302)

    def test_an_unverified_email_still_signs_in_a_known_code(self):
        self.google.start()
        self.google.come_back(sub="google-1", email_verified=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    # 11
    def test_an_admin_account_is_not_signed_in(self):
        for flags in ({"is_staff": True}, {"is_superuser": True}):
            with self.subTest(**flags):
                User.objects.filter(pk=self.user.pk).update(
                    **{"is_staff": False, "is_superuser": False} | flags
                )
                self.google.start()
                response = self.google.come_back(sub="google-1")
                self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
                self.assertNotIn("_auth_user_id", self.client.session)
                self.assertContains(self.client.get(reverse("login")), "這個帳號請用帳號密碼登入。")

    def test_a_deactivated_account_is_not_signed_in(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.google.start()
        self.assertRedirects(self.google.come_back(sub="google-1"), reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    # 39
    def test_who_agreed_to_the_last_version_is_asked_again(self):
        Consent.objects.filter(user=self.user).update(version=models.CONSENT_VERSION - 1)
        target = reverse("my_hearing")
        self.google.start(next=target)
        self.google.come_back(sub="google-1")
        self.assertRedirects(self.client.get(target), test_consent._consent_url(target))


@google_on
class CallbackSecurityTests(TestCase):
    """#505 acceptance 15-20: a forged, replayed, late or cancelled callback signs no one in.
    The code google-1 belongs to an account, so a check that let it through would sign it in."""

    def setUp(self):
        self.google = FakeGoogle(self.client)
        self.user = consented_user(username="林阿美")
        SignInMethod.objects.create(user=self.user, provider="google", subject="google-1")
        self.google.start()

    def assertRejected(self, response, message=FAILED_WORDS, exchanged=False):
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(self.client.get(reverse("login")), message)
        self.assertEqual(bool(self.google.exchanges), exchanged)

    def test_the_real_callback_signs_in(self):
        # The other tests' baseline: unchanged, this callback does sign the account in.
        self.assertRedirects(
            self.google.come_back(sub="google-1"), reverse("consent"), target_status_code=302
        )
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    # 15
    def test_a_different_state_is_rejected_before_calling_google(self):
        state = self.google.authorize["state"]
        forged = state[:-1] + ("A" if state[-1] != "A" else "B")
        self.assertRejected(self.google.come_back(query={"code": "auth-code", "state": forged}))

    def test_a_state_that_is_not_ascii_is_rejected_not_a_server_error(self):
        self.assertRejected(self.google.come_back(query={"code": "auth-code", "state": "中"}))

    def test_no_state_is_rejected_before_calling_google(self):
        self.assertRejected(self.google.come_back(query={"code": "auth-code"}))

    def test_no_trip_in_the_session_is_rejected(self):
        query = {"code": "auth-code", "state": self.google.authorize["state"]}
        session = self.client.session
        del session["screening.oidc_flow"]
        session.save()
        self.assertRejected(self.google.come_back(query=query))

    def test_a_state_is_used_up_even_by_a_failed_try(self):
        good = {"code": "auth-code", "state": self.google.authorize["state"]}
        self.google.come_back(query={"code": "auth-code", "state": "wrong"})
        self.assertRejected(self.google.come_back(query=good))

    def test_no_code_is_rejected(self):
        self.assertRejected(self.google.come_back(query={"state": self.google.authorize["state"]}))

    # 16
    def test_more_than_10_minutes_after_leaving_is_rejected_before_calling_google(self):
        later = timezone.now() + timedelta(minutes=10, seconds=1)
        with mock.patch("django.utils.timezone.now", return_value=later):
            response = self.google.come_back(sub="google-1")
        self.assertRejected(response)

    def test_just_under_10_minutes_is_still_in_time(self):
        later = timezone.now() + timedelta(minutes=9, seconds=50)
        with mock.patch("django.utils.timezone.now", return_value=later):
            self.google.come_back(sub="google-1")
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    # 17
    def test_an_id_token_for_another_trip_is_rejected(self):
        self.assertRejected(self.google.come_back(sub="google-1", nonce="other"), exchanged=True)

    def test_a_nonce_that_is_not_ascii_is_rejected_not_a_server_error(self):
        self.assertRejected(self.google.come_back(sub="google-1", nonce="中"), exchanged=True)

    def test_an_id_token_without_a_nonce_is_rejected(self):
        self.assertRejected(self.google.come_back(sub="google-1", nonce=None), exchanged=True)

    def test_an_id_token_for_another_client_is_rejected(self):
        self.assertRejected(
            self.google.come_back(sub="google-1", aud="another.apps.googleusercontent.com"),
            exchanged=True,
        )

    def test_an_id_token_from_another_issuer_is_rejected(self):
        self.assertRejected(
            self.google.come_back(sub="google-1", iss="https://evil.example"), exchanged=True
        )

    def test_both_of_googles_issuer_forms_are_accepted(self):
        self.google.come_back(sub="google-1", iss="accounts.google.com")
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_an_expired_id_token_is_rejected(self):
        past = int(timezone.now().timestamp()) - 1
        self.assertRejected(self.google.come_back(sub="google-1", exp=past), exchanged=True)

    def test_an_id_token_without_a_sub_is_rejected(self):
        self.assertRejected(self.google.come_back(sub=None), exchanged=True)

    def test_an_unreadable_id_token_is_rejected(self):
        with mock.patch(
            "screening.oidc.post_to_provider", return_value={"id_token": "not-a-token"}
        ):
            response = self.client.get(
                reverse("google_callback"),
                {"code": "auth-code", "state": self.google.authorize["state"]},
            )
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    # 18
    def test_the_same_callback_twice_is_rejected(self):
        query = {"code": "auth-code", "state": self.google.authorize["state"]}
        self.google.come_back(sub="google-new", query=query)  # to the name page, not signed in
        self.assertRedirects(
            self.google.come_back(sub="google-1", query=query),
            reverse("login"),
            fetch_redirect_response=False,
        )
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(len(self.google.exchanges), 1)

    # 19
    def test_cancelling_on_google_comes_back_to_login_with_words(self):
        response = self.google.come_back(
            query={"error": "access_denied", "state": self.google.authorize["state"]}
        )
        self.assertRejected(response, "沒有完成 Google 登入。可以再試一次，或用帳號密碼登入。")
        self.assertNotIn("screening.oidc_flow", self.client.session)

    def test_a_cancel_is_believed_only_for_this_trip_in_time(self):
        # The state and the trip's age are checked before `error` is read: a cancel that is not
        # this trip's (forged, used up, too late) is a failed sign-in like any other callback.
        for name, state, seconds_later in (
            ("no state", None, 0),
            ("another state", "forged", 0),
            ("not ascii", "中", 0),
            ("too late", "this trip's", 10 * 60 + 1),
        ):
            with self.subTest(name):
                self.google.start()
                query = {"error": "access_denied"}
                if state is not None:
                    query["state"] = (
                        self.google.authorize["state"] if state == "this trip's" else state
                    )
                later = timezone.now() + timedelta(seconds=seconds_later)
                with (
                    mock.patch("django.utils.timezone.now", return_value=later),
                    self.assertLogs("screening.views.sign_in", "ERROR"),
                ):
                    response = self.google.come_back(query=query)
                self.assertRejected(response)

    def test_a_cancel_already_used_is_not_believed_again(self):
        query = {"error": "access_denied", "state": self.google.authorize["state"]}
        self.google.come_back(query=query)
        with self.assertLogs("screening.views.sign_in", "ERROR"):
            self.assertRejected(self.google.come_back(query=query))

    # 20
    def test_google_not_answering_comes_back_to_login_and_goes_to_monitoring(self):
        with self.assertLogs("screening.views.sign_in", "ERROR") as logs:
            response = self.google.come_back(
                sub="google-1", exchange=oidc.Unavailable("google token endpoint: URLError")
            )
        self.assertRejected(
            response, "Google 暫時沒有回應，請稍後再試，或用帳號密碼登入。", exchanged=True
        )
        self.assertIn("Google token exchange failed", logs.output[0])

    def test_an_error_answer_from_google_is_google_not_answering(self):
        # Google's token endpoint answering 200 with no ID token: an error in its JSON, or none.
        for name, answer in (
            ("error", {"error": "invalid_grant", "error_description": "Bad Request"}),
            ("no id_token", {"access_token": "never-kept"}),
        ):
            with self.subTest(name):
                self.google.start()
                with self.assertLogs("screening.views.sign_in", "ERROR") as logs:
                    response = self.google.come_back(sub="google-1", exchange=answer)
                self.assertRejected(
                    response, "Google 暫時沒有回應，請稍後再試，或用帳號密碼登入。", exchanged=True
                )
                self.assertIn("Google token exchange failed", logs.output[0])
                self.google.exchanges.clear()

    def test_a_rejected_callback_goes_to_monitoring_without_its_secrets(self):
        # Error monitoring takes ERROR and above (Sentry's logging integration); a forged
        # callback is a technical detail for it, as Google not answering is (spec #505).
        for name, come_back in (
            ("state", {"query": {"code": "secret-code", "state": "forged-state"}}),
            ("nonce", {"sub": "google-1", "nonce": "other", "email": "amei@example.com"}),
        ):
            with self.subTest(name):
                self.google.start()
                state = self.google.authorize["state"]
                with self.assertLogs("screening.views.sign_in", "ERROR") as logs:
                    response = self.google.come_back(**come_back)
                self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
                output = "\n".join(logs.output)
                self.assertIn("Google callback rejected", output)
                for secret in ("secret-code", "forged-state", state, "amei@example.com"):
                    self.assertNotIn(secret, output)


class SignInMethodDataTests(TestCase):
    """#505 acceptance 33, 34 and the admin: the sign-in methods go with the account, come out
    in 下載我的資料 without any token, and the admin may only look at them."""

    def setUp(self):
        self.user = consented_user(username="林阿美", password=PASSWORD)
        self.method = SignInMethod.objects.create(
            user=self.user, provider="google", subject="google-1", used_to_register=True
        )
        self.other = consented_user(username="別人")
        SignInMethod.objects.create(user=self.other, provider="google", subject="google-2")
        self.client.force_login(self.user)

    def add_health_data(self):
        """A record and an audiogram of the account's, as test_account_deletion fills them."""
        questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        question = Question.objects.create(
            questionnaire=questionnaire,
            question_text="假題目一",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        submission = Submission.objects.create(user=self.user, questionnaire=questionnaire)
        Answer.objects.create(submission=submission, question=question, score=4)
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 3, 4))
        AudiogramPoint.objects.create(
            audiogram=audiogram, ear="right", conduction="air", frequency=1000, db=35
        )

    def health_data(self):
        return (
            Submission.objects.filter(user_id=self.user.pk).count(),
            Answer.objects.filter(submission__user_id=self.user.pk).count(),
            Audiogram.objects.filter(user_id=self.user.pk).count(),
            AudiogramPoint.objects.filter(audiogram__user_id=self.user.pk).count(),
        )

    # 33
    def test_deleting_the_account_deletes_its_sign_in_methods_with_its_records(self):
        self.add_health_data()
        response = self.client.post(reverse("delete_account"), {"password": PASSWORD})
        self.assertRedirects(response, reverse("index"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(SignInMethod.objects.filter(user_id=self.user.pk).exists())
        self.assertEqual(self.health_data(), (0, 0, 0, 0))
        self.assertEqual(SignInMethod.objects.get().user, self.other)

    def test_a_failure_midway_deletes_nothing(self):
        self.add_health_data()
        with (
            mock.patch.object(User, "delete", side_effect=DatabaseError),
            self.assertRaises(DatabaseError),
        ):
            self.client.post(reverse("delete_account"), {"password": PASSWORD})
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(SignInMethod.objects.filter(pk=self.method.pk).exists())
        self.assertTrue(self.user.consents.exists())
        self.assertEqual(self.health_data(), (1, 1, 1, 1))

    # 32
    def test_a_wrong_password_on_the_delete_page_keeps_the_account(self):
        self.add_health_data()
        response = self.client.post(reverse("delete_account"), {"password": "wrong"})
        self.assertContains(response, "密碼不正確")
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(SignInMethod.objects.filter(pk=self.method.pk).exists())
        self.assertEqual(self.health_data(), (1, 1, 1, 1))

    def test_after_deleting_the_same_google_is_a_new_code(self):
        self.client.post(reverse("delete_account"), {"password": PASSWORD})
        with google_on:
            google = FakeGoogle(self.client)
            google.start()
            response = google.come_back(sub="google-1")
        self.assertRedirects(response, reverse("google_name"), fetch_redirect_response=False)

    # 34
    def test_the_download_lists_the_sign_in_methods_without_tokens(self):
        response = self.client.get(reverse("download_my_data"))
        data = json.loads(response.content)
        created_at = timezone.localtime(self.method.created_at).isoformat()
        self.assertEqual(
            data["sign_in_methods"],
            [
                {
                    "provider": "Google",
                    "subject": "google-1",
                    "created_at": created_at,
                    "used_to_register": True,
                }
            ],
        )
        self.assertNotIn("google-2", response.content.decode())
        self.assertNotIn("token", response.content.decode())

    def test_the_download_has_an_empty_list_without_any(self):
        self.client.force_login(consented_user(username="只用密碼"))
        data = json.loads(self.client.get(reverse("download_my_data")).content)
        self.assertEqual(data["sign_in_methods"], [])

    def test_the_admin_may_look_but_not_add_change_or_delete(self):
        admin = User.objects.create_superuser(username="admin", password=PASSWORD)
        self.client.force_login(admin)
        changelist = reverse("admin:screening_signinmethod_changelist")
        self.assertEqual(self.client.get(changelist).status_code, 200)
        change = reverse("admin:screening_signinmethod_change", args=[self.method.pk])
        self.assertEqual(self.client.get(change).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("admin:screening_signinmethod_add")).status_code, 403
        )
        self.client.post(change, {"subject": "changed"})
        delete = reverse("admin:screening_signinmethod_delete", args=[self.method.pk])
        self.assertEqual(self.client.post(delete, {"post": "yes"}).status_code, 403)
        self.method.refresh_from_db()
        self.assertEqual(self.method.subject, "google-1")


class SignInMethodAdminTests(TestCase):
    """The admin's list of sign-in methods (CODING_STANDARDS.md 15): as many queries for many
    rows as for two."""

    def queries_for_the_list(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("admin:screening_signinmethod_changelist"))
        self.assertEqual(response.status_code, 200)
        return len(queries)

    def test_the_list_does_not_query_per_row(self):
        self.client.force_login(User.objects.create_superuser(username="admin", password=PASSWORD))
        for n in range(2):
            user = User.objects.create_user(username=f"user_{n}")
            SignInMethod.objects.create(user=user, provider="google", subject=f"google-{n}")
        two = self.queries_for_the_list()
        for n in range(2, 7):
            user = User.objects.create_user(username=f"user_{n}")
            SignInMethod.objects.create(user=user, provider="google", subject=f"google-{n}")
        self.assertEqual(self.queries_for_the_list(), two)


class PrivacyTests(TestCase):
    """#505 acceptance 38, 39: the privacy notice says what Google gives, in a new version."""

    def test_the_privacy_notice_says_what_google_gives_and_what_it_does_not(self):
        response = self.client.get(reverse("privacy"))
        self.assertContains(response, "用 Google 登入時")
        self.assertContains(
            response,
            "只拿 Google 給您的代號和 email（Google 標示已驗證的），"
            "不拿您在 Google 的名稱、大頭貼和聯絡人。",
        )
        self.assertContains(response, "不保留 Google 給的任何權杖")
        self.assertContains(response, "登入完成後，不會再跟 Google 拿任何資料。")

    def test_version_7_dated_the_day_it_changed(self):
        # #526 (spec #355) took version 6 for the 重設密碼信 first.
        self.assertEqual(models.CONSENT_VERSION, 7)
        self.assertEqual(models.PRIVACY_UPDATED_ON, date(2026, 11, 14))
        self.assertContains(self.client.get(reverse("privacy")), "第 7 版，2026/11/14 更新")

    # 39
    def test_who_agreed_to_version_6_agrees_again(self):
        user = User.objects.create_user(username="agreed_to_6")
        Consent.objects.create(user=user, version=6)
        self.client.force_login(user)
        url = reverse("my_hearing")
        self.assertRedirects(self.client.get(url), test_consent._consent_url(url))
        self.assertContains(self.client.get(test_consent._consent_url(url)), "Google")


class PostToProviderTests(SimpleTestCase):
    """#505 acceptance 20 and #506 acceptance 12, 14 at the real post_to_provider, against a
    small server on this machine: what a provider answers is given back, no answer is
    Unavailable, never a server error."""

    def serve(self, status, body):
        """A provider on this machine answering every POST with this status and body; the form
        it was sent goes into self.received."""
        self.received = []
        test = self

        class Provider(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                test.received.append(dict(parse_qsl(self.rfile.read(length).decode())))
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Provider)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/token"

    def test_posts_the_form_and_gives_the_json(self):
        url = self.serve(200, b'{"id_token": "x"}')
        self.assertEqual(
            oidc.post_to_provider(url, {"code": "c", "nonce": "中"}), {"id_token": "x"}
        )
        self.assertEqual(self.received, [{"code": "c", "nonce": "中"}])

    def test_an_empty_answer_is_an_empty_dict(self):
        # LINE's revoke endpoint answers 200 with nothing in it.
        self.assertEqual(oidc.post_to_provider(self.serve(200, b""), {}), {})

    def test_a_refusal_gives_its_json(self):
        # LINE's verify endpoint refusing an ID token: 400 with an error in its JSON.
        body = b'{"error": "invalid_request", "error_description": "IdToken expired."}'
        answer = oidc.post_to_provider(self.serve(400, body), {})
        self.assertEqual(answer["error"], "invalid_request")

    def test_no_usable_answer_is_unavailable(self):
        for name, status, body in (
            ("server error", 500, b'{"error": "server_error"}'),
            ("not json", 200, b"<html>"),
            ("a refusal not in json", 400, b"Bad Request"),
            ("not an object", 200, b"[]"),
        ):
            with self.subTest(name), self.assertRaises(oidc.Unavailable):
                oidc.post_to_provider(self.serve(status, body), {})

    def test_a_provider_that_does_not_answer_is_unavailable(self):
        # Nothing listens on port 9 of this machine.
        with self.assertRaises(oidc.Unavailable):
            oidc.post_to_provider("http://127.0.0.1:9/token", {"code": "c"})
