"""Spec #505 acceptance 29-32 (#510): confirming it is the account's owner (確認本人) before
deleting an account, with the password or, without one, the Google already on the account."""

from contextlib import nullcontext
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qsl, quote, urlsplit

from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from screening import oidc
from screening.models import SignInMethod, User
from screening.tests.helpers import GOOGLE_AUTHORIZE, FakeGoogle, consented_user, google_on
from screening.views import confirm_identity

OWN_SUB = "google-own"
NOT_YOURS = "這不是您帳號上的 Google。請改用註冊時用的那個 Google 帳戶。"  # W16


def google_only_user(username="google_only", sub=OWN_SUB):
    """An account made with Google: no usable password, one Google sign-in method."""
    user = consented_user(username=username)
    SignInMethod.objects.create(user=user, provider="google", subject=sub, used_to_register=True)
    return user


def start_confirming(client, google, action="delete_account"):
    """Press 「使用 Google 帳戶確認」: off to Google, whose authorize query google keeps."""
    response = client.post(f"{reverse('confirm_identity')}?action={action}", {"provider": "google"})
    location = urlsplit(response["Location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == GOOGLE_AUTHORIZE
    google.authorize = dict(parse_qsl(location.query))
    return response


@google_on
class DeleteWithoutPasswordTests(TestCase):
    """#505 acceptance 30: without a password the delete page confirms with Google instead."""

    def setUp(self):
        self.user = google_only_user()
        self.client.force_login(self.user)

    def test_delete_page_offers_google_instead_of_a_password(self):
        response = self.client.get(reverse("delete_account"))
        self.assertNotContains(response, 'name="password"')
        self.assertContains(response, "您的帳號沒有密碼，請用 Google 確認是本人。")  # W17
        self.assertContains(response, "<li>登入方式（Google）</li>", html=True)
        self.assertContains(
            response, f'action="{reverse("confirm_identity")}?action=delete_account"'
        )
        self.assertContains(response, "使用 Google 帳戶確認")  # D3
        # The red button comes only after confirming (the #507 mockup).
        self.assertNotContains(response, ">刪除帳號</button>")

    def test_google_is_asked_to_show_its_account_chooser(self):
        google = FakeGoogle(self.client)
        start_confirming(self.client, google)
        # Google has no max_age or prompt=login (login-research.md section 8): the chooser, and
        # no login_hint, which would skip it.
        self.assertEqual(google.authorize["prompt"], "select_account")
        self.assertNotIn("login_hint", google.authorize)

    def test_signing_in_does_not_show_the_chooser(self):
        self.client.logout()
        google = FakeGoogle(self.client)
        google.start()
        self.assertNotIn("prompt", google.authorize)

    def test_own_google_confirms_and_back_on_the_delete_page_delete_deletes(self):
        google = FakeGoogle(self.client)
        start_confirming(self.client, google)
        response = google.come_back(sub=OWN_SUB, email="own@example.com")
        self.assertRedirects(
            response,
            f"{reverse('confirm_identity')}?action=delete_account",
            target_status_code=302,
        )
        page = self.client.get(response["Location"], follow=True)
        self.assertRedirects(page, reverse("delete_account"))
        self.assertContains(page, "已確認是您本人。")
        self.assertContains(page, ">刪除帳號</button>")
        self.assertNotContains(page, "使用 Google 帳戶確認")
        # Nothing is deleted until the button is pressed.
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

        response = self.client.post(reverse("delete_account"))
        self.assertRedirects(response, reverse("index"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(SignInMethod.objects.filter(subject=OWN_SUB).exists())

    def test_delete_without_confirming_deletes_nothing(self):
        response = self.client.post(reverse("delete_account"))
        self.assertRedirects(response, reverse("delete_account"))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())


@google_on
class DeleteBeforeAgreeingTests(TestCase):
    """#505 acceptance 30 for an account that has not agreed to the current privacy notice:
    deleting one's data is a right before agreeing (ConsentRequiredMiddleware), so 確認本人 for
    deleting is open too; its other actions are not."""

    def check_deletes(self, user):
        self.client.force_login(user)
        google = FakeGoogle(self.client)
        start_confirming(self.client, google)
        response = google.come_back(sub=OWN_SUB, email="own@example.com")
        page = self.client.get(response["Location"], follow=True)
        self.assertRedirects(page, reverse("delete_account"))
        self.assertContains(page, "已確認是您本人。")
        self.assertRedirects(self.client.post(reverse("delete_account")), reverse("index"))
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def test_never_agreed(self):
        user = google_only_user()
        user.consents.all().delete()
        self.check_deletes(user)

    def test_agreed_to_an_older_version_only(self):
        user = google_only_user()
        user.consents.update(version=5)
        self.check_deletes(user)

    def test_adding_or_removing_still_asks_to_agree_first(self):
        user = google_only_user()
        user.consents.all().delete()
        self.client.force_login(user)
        for action in ("add_google", "remove_google"):
            with self.subTest(action):
                url = f"{reverse('confirm_identity')}?action={action}"
                response = self.client.get(url)
                self.assertRedirects(
                    response,
                    f"{reverse('consent')}?next={quote(url, safe='')}",
                    fetch_redirect_response=False,
                )


@google_on
class WrongGoogleTests(TestCase):
    """#505 acceptance 31: a Google that is not the account's confirms nothing."""

    def setUp(self):
        self.user = google_only_user()
        self.client.force_login(self.user)

    def come_back_as(self, sub):
        google = FakeGoogle(self.client)
        start_confirming(self.client, google)
        return google.come_back(sub=sub, email="other@example.com")

    def assert_nothing_confirmed(self, response):
        confirm_page = f"{reverse('confirm_identity')}?action=delete_account"
        self.assertRedirects(response, confirm_page, fetch_redirect_response=False)
        page = self.client.get(confirm_page)
        self.assertContains(page, NOT_YOURS)
        self.assertContains(page, "使用 Google 帳戶確認")
        # The delete page still asks for 確認本人, and pressing delete deletes nothing.
        self.assertNotContains(self.client.get(reverse("delete_account")), "已確認是您本人")
        self.client.post(reverse("delete_account"))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(
            list(SignInMethod.objects.values_list("user__username", "subject")),
            [*self.methods_before],
        )

    def test_a_google_never_seen(self):
        self.methods_before = [("google_only", OWN_SUB)]
        self.assert_nothing_confirmed(self.come_back_as("google-stranger"))

    def test_a_wrong_google_confirms_nothing_for_adding(self):
        google = FakeGoogle(self.client)
        start_confirming(self.client, google, action="add_google")
        response = google.come_back(sub="google-stranger", email="other@example.com")
        confirm_add = f"{reverse('confirm_identity')}?action=add_google"
        self.assertRedirects(response, confirm_add, fetch_redirect_response=False)
        self.assertContains(self.client.get(confirm_add), NOT_YOURS)
        self.assertNotIn(confirm_identity.CONFIRMED, self.client.session)
        self.assertNotIn(oidc.FLOW, self.client.session)
        self.assertEqual(list(SignInMethod.objects.values_list("subject", flat=True)), [OWN_SUB])

    def test_no_google_confirmation_can_remove(self):
        # Removing is done with the password on the confirm page itself; this account's Google
        # is its only way in, so the page refuses before any trip to Google could start.
        confirm_remove = f"{reverse('confirm_identity')}?action=remove_google"
        self.assertEqual(self.client.post(confirm_remove, {"provider": "google"}).status_code, 403)
        self.assertNotIn(oidc.FLOW, self.client.session)
        self.assertEqual(list(SignInMethod.objects.values_list("subject", flat=True)), [OWN_SUB])

    def test_a_google_on_another_account(self):
        google_only_user(username="someone_else", sub="google-theirs")
        self.methods_before = [("google_only", OWN_SUB), ("someone_else", "google-theirs")]
        self.assert_nothing_confirmed(self.come_back_as("google-theirs"))
        self.assertTrue(User.objects.filter(username="someone_else").exists())


def confirm_with_google(test, sub=OWN_SUB, action="delete_account"):
    google = FakeGoogle(test.client)
    start_confirming(test.client, google, action)
    google.come_back(sub=sub, email="own@example.com")


def later(seconds):
    """Patch the clock to this many seconds from now."""
    return patch(
        "django.utils.timezone.now", return_value=timezone.now() + timedelta(seconds=seconds)
    )


@google_on
class ConfirmationLastsTests(TestCase):
    """#505 acceptance 29 and #510: a confirmation holds for 5 minutes and for one action."""

    def setUp(self):
        self.user = google_only_user()
        self.client.force_login(self.user)
        confirm_with_google(self)

    def test_deleting_within_5_minutes_deletes(self):
        with later(5 * 60 - 1):
            self.client.post(reverse("delete_account"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_after_5_minutes_confirm_again(self):
        with later(5 * 60 + 1):
            response = self.client.post(reverse("delete_account"))
            self.assertRedirects(response, reverse("delete_account"), fetch_redirect_response=False)
            page = self.client.get(reverse("delete_account"))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertContains(page, "確認已經過期，請再確認一次。")  # W18
        self.assertContains(page, "使用 Google 帳戶確認")
        self.assertNotContains(page, ">刪除帳號</button>")

    def test_after_5_minutes_the_delete_page_asks_again(self):
        with later(5 * 60 + 1):
            page = self.client.get(reverse("delete_account"))
        self.assertNotContains(page, "已確認是您本人")
        self.assertContains(page, "使用 Google 帳戶確認")

    def request(self):
        request = RequestFactory().get("/")
        request.session = self.client.session
        return request

    def test_a_confirmation_is_good_for_one_action(self):
        request = self.request()
        self.assertTrue(confirm_identity.is_confirmed(request, "delete_account"))
        # Looking does not use it.
        self.assertTrue(confirm_identity.is_confirmed(request, "delete_account"))
        self.assertTrue(confirm_identity.use_confirmation(request, "delete_account"))
        self.assertFalse(confirm_identity.use_confirmation(request, "delete_account"))
        self.assertFalse(confirm_identity.is_confirmed(request, "delete_account"))

    def test_a_confirmation_is_only_for_the_action_it_was_asked_for(self):
        # Confirmed to delete the account: adding or removing a sign-in method is not confirmed.
        request = self.request()
        for other in ("add_google", "remove_google"):
            with self.subTest(other):
                self.assertFalse(confirm_identity.is_confirmed(request, other))
                self.assertFalse(confirm_identity.use_confirmation(request, other))
        # Trying it on another action uses it up all the same.
        self.assertFalse(confirm_identity.is_confirmed(request, "delete_account"))

    def test_a_used_confirmation_is_not_reported_as_expired(self):
        request = self.request()
        confirm_identity.use_confirmation(request, "delete_account")
        confirm_identity.use_confirmation(request, "delete_account")
        self.assertIsNone(confirm_identity.confirm_error(request))


PASSWORD = "Xk9#mPq2vLw"
CONFIRM_DELETE = "/account/confirm?action=delete_account"


@google_on
class ConfirmWithPasswordTests(TestCase):
    """The confirm page with a usable password (#505 acceptance 23, 32; #511 uses it)."""

    def setUp(self):
        self.user = consented_user(username="wang_ming", password=PASSWORD)
        SignInMethod.objects.create(user=self.user, provider="google", subject=OWN_SUB)
        self.client.force_login(self.user)

    def confirmed(self):
        request = RequestFactory().get("/")
        request.session = self.client.session
        return confirm_identity.is_confirmed(request, "delete_account")

    def test_asks_for_the_password_and_says_what_comes_next(self):
        response = self.client.get(CONFIRM_DELETE)
        self.assertContains(response, "先確認是您本人")
        self.assertContains(
            response, "接下來要<strong>刪除帳號</strong>。請輸入 wang_ming 的密碼。"
        )
        self.assertContains(response, 'name="password"')
        self.assertNotContains(response, "使用 Google 帳戶確認")

    def test_wrong_password_confirms_nothing(self):
        response = self.client.post(CONFIRM_DELETE, {"password": "wrong"})
        self.assertContains(response, "密碼不正確")
        self.assertFalse(self.confirmed())

    def test_right_password_confirms_and_goes_on(self):
        response = self.client.post(CONFIRM_DELETE, {"password": PASSWORD})
        self.assertRedirects(response, reverse("delete_account"))
        self.assertTrue(self.confirmed())

    def test_google_is_not_a_way_round_the_password(self):
        response = self.client.post(CONFIRM_DELETE, {"provider": "google"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "請輸入密碼")
        self.assertNotIn(oidc.FLOW, self.client.session)
        self.assertFalse(self.confirmed())

    def test_delete_page_keeps_the_password_field_and_lists_the_google(self):
        # #505 acceptance 32: as before; the Google sign-in method goes with the account (W17).
        response = self.client.get(reverse("delete_account"))
        self.assertContains(response, 'name="password"')
        self.assertContains(response, "<li>登入方式（Google）</li>", html=True)
        self.assertNotContains(response, "您的帳號沒有密碼")


@google_on
class ConfirmPageTests(TestCase):
    def setUp(self):
        self.user = google_only_user()
        self.client.force_login(self.user)

    def test_without_a_password_says_to_sign_in_with_google_again(self):
        response = self.client.get(CONFIRM_DELETE)
        self.assertContains(
            response, "接下來要<strong>刪除帳號</strong>。請用您帳號上的 Google 再登入一次。"
        )
        self.assertNotContains(response, 'name="password"')
        self.assertContains(response, "使用 Google 帳戶確認")
        self.assertEqual(
            response["Cache-Control"], "max-age=0, no-cache, no-store, must-revalidate, private"
        )

    def test_an_unknown_action_is_404(self):
        self.assertEqual(self.client.get("/account/confirm?action=anything").status_code, 404)
        self.assertEqual(self.client.get("/account/confirm").status_code, 404)

    def test_logged_out_goes_to_log_in(self):
        self.client.logout()
        response = self.client.get(CONFIRM_DELETE)
        self.assertRedirects(response, f"{reverse('login')}?next={quote(CONFIRM_DELETE)}")

    def test_a_trip_that_fails_comes_back_here_not_to_the_login_page(self):
        for name, come_back in (
            ("cancelled", {"cancelled": True}),
            ("google down", {"exchange": oidc.Unavailable("down")}),
            ("forged", {"nonce": "someone-else"}),
        ):
            with self.subTest(name):
                google = FakeGoogle(self.client)
                start_confirming(self.client, google)
                with (
                    self.assertLogs("screening.views.sign_in", "WARNING")
                    if name != "cancelled"
                    else nullcontext()
                ):
                    response = google.come_back(**come_back)
                self.assertRedirects(response, CONFIRM_DELETE, fetch_redirect_response=False)
                self.assertContains(
                    self.client.get(CONFIRM_DELETE), "沒有完成 Google 確認，請再試一次。"
                )
                self.assertNotContains(self.client.get(reverse("delete_account")), "已確認是您本人")

    def test_signed_out_during_the_trip_back_to_log_in_with_nothing_confirmed(self):
        # The callback is a public URL: the account was turned off while at Google, so the
        # session no longer signs anyone in when the trip comes back.
        google = FakeGoogle(self.client)
        start_confirming(self.client, google)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        response = google.come_back(sub=OWN_SUB, email="own@example.com")
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={quote(CONFIRM_DELETE)}",
            fetch_redirect_response=False,
        )
        self.assertNotIn(confirm_identity.CONFIRMED, self.client.session)

    def test_without_google_keys_there_is_no_google_button(self):
        with self.settings(GOOGLE_CLIENT_ID=""):
            response = self.client.get(reverse("delete_account"))
            self.assertNotContains(response, "使用 Google 帳戶確認")
            response = self.client.post(CONFIRM_DELETE, {"provider": "google"})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(oidc.FLOW, self.client.session)
