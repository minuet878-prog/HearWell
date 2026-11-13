"""Spec #506 acceptance 19-21 (ticket #542, the #539 mockup 6, W9, W10): 確認本人 without a
password with any sign-in method on the account, LINE among them, by the same rules as Google's
(#510): bound to its action, for 5 minutes, used once; and a LINE-only account deleting itself."""

import threading
from contextlib import nullcontext
from unittest import mock
from urllib.parse import parse_qsl, quote, urlsplit

from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from screening import oidc
from screening.models import CONSENT_VERSION, SignInMethod, User
from screening.tests import (
    test_confirm_identity,
    test_consent,
    test_line_in_app_browser,
    test_line_sign_in_methods,
    test_sign_in_methods_settings,
)
from screening.tests.helpers import (
    GOOGLE_AUTHORIZE,
    GOOGLE_TOKEN,
    LINE_AUTHORIZE,
    LINE_ENDPOINTS,
    FakeGoogle,
    FakeLine,
    consented_user,
    google_on,
    id_token,
    line_on,
)
from screening.views import confirm_identity

later = test_confirm_identity.later
line_only_user = test_line_sign_in_methods.line_only_user
add_google = test_sign_in_methods_settings.add_google
messages_on = test_sign_in_methods_settings.messages_on
PASSWORD = test_confirm_identity.PASSWORD
LINE_BROWSER = test_line_in_app_browser.LINE_IOS

OWN_LINE = "line-own"
OWN_GOOGLE = "google-own"
LINE_BUTTON = "使用 LINE 帳號確認"  # W1
GOOGLE_BUTTON = "使用 Google 帳戶確認"
ANY_ONE = "請用您帳號上的其中一種方式再登入一次。"  # W9
NOT_YOUR_LINE = "這不是您帳號上的 LINE。請用註冊時那支手機上的 LINE 再試一次。"  # W10
NOT_YOUR_GOOGLE = "這不是您帳號上的 Google。請改用註冊時用的那個 Google 帳戶。"  # W16
NOT_CONFIRMED = "沒有完成 LINE 確認，請再試一次。"  # a draft for the owner
CONFIRMED = "已確認是您本人。"
DELETE_BUTTON = ">刪除帳號</button>"
OPEN_OUTSIDE = "用 Safari／Chrome 打開"


def confirm_url(action):
    return f"{reverse('confirm_identity')}?action={action}"


CONFIRM_DELETE = confirm_url("delete_account")
CONFIRM_REMOVE_LINE = confirm_url("remove_line")
CONFIRM_REMOVE_GOOGLE = confirm_url("remove_google")
SETTINGS_GROUP = f"{reverse('account_settings')}#sign-in-methods"


def line_and_google_user(username="lin_mei", line=OWN_LINE, google=OWN_GOOGLE):
    """An account without a password with both LINE and Google (made with LINE)."""
    user = line_only_user(username=username, sub=line)
    add_google(user, sub=google)
    return user


def press(client, provider, action):
    """Press 「使用 ○○ 確認」 on the confirm page for this action; where it sends the browser."""
    return client.post(confirm_url(action), {"provider": provider})


def off_to(test, response, authorize):
    location = urlsplit(response["Location"])
    test.assertEqual(f"{location.scheme}://{location.netloc}{location.path}", authorize)
    return dict(parse_qsl(location.query))


def confirm_with_line(test, sub=OWN_LINE, action="delete_account", **come_back):
    """Confirm on the confirm page with LINE, which gives back this code; LINE's answer."""
    line = FakeLine(test.client)
    line.authorize = off_to(test, press(test.client, "line", action), LINE_AUTHORIZE)
    return line.come_back(sub=sub, **come_back)


def confirm_with_google(test, sub=OWN_GOOGLE, action="delete_account"):
    google = FakeGoogle(test.client)
    google.authorize = off_to(test, press(test.client, "google", action), GOOGLE_AUTHORIZE)
    return google.come_back(sub=sub, email="own@example.com")


def methods(user):
    return sorted(user.sign_in_methods.values_list("provider", "subject"))


def button_order(test, response):
    """The confirm buttons' words in the order the page shows them."""
    content = response.content.decode()
    found = [(content.find(words), words) for words in (LINE_BUTTON, GOOGLE_BUTTON)]
    return [words for at, words in sorted(found) if at != -1]


@google_on
@line_on
class ButtonsTests(TestCase):
    """#506 acceptance 21: without a password, a button for each sign-in method on the account,
    LINE above Google (the #539 mockup 6); any one of them starts a trip."""

    def setUp(self):
        self.user = line_and_google_user()
        self.client.force_login(self.user)

    def test_the_confirm_page_has_a_button_for_each_line_first(self):
        response = self.client.get(CONFIRM_REMOVE_LINE)
        self.assertContains(response, f"接下來要<strong>移除 LINE 登入</strong>。{ANY_ONE}")
        self.assertEqual(button_order(self, response), [LINE_BUTTON, GOOGLE_BUTTON])
        self.assertContains(response, '<button type="submit" name="provider" value="line"')
        self.assertContains(response, '<button type="submit" name="provider" value="google"')
        self.assertNotContains(response, 'name="password"')
        self.assertNotContains(response, OPEN_OUTSIDE)

    def test_the_delete_page_has_a_button_for_each_line_first(self):
        response = self.client.get(reverse("delete_account"))
        self.assertContains(response, "您的帳號沒有密碼，請用 LINE 或 Google 確認是本人。")
        self.assertEqual(button_order(self, response), [LINE_BUTTON, GOOGLE_BUTTON])
        self.assertContains(response, f'action="{CONFIRM_DELETE}"')
        self.assertNotContains(response, DELETE_BUTTON)

    def test_either_button_starts_a_trip_for_this_action(self):
        line = off_to(self, press(self.client, "line", "delete_account"), LINE_AUTHORIZE)
        self.assertEqual(self.client.session[oidc.FLOW]["purpose"], "confirm_identity")
        self.assertEqual(self.client.session[oidc.FLOW]["next"], CONFIRM_DELETE)
        google = off_to(self, press(self.client, "google", "delete_account"), GOOGLE_AUTHORIZE)
        self.assertEqual(self.client.session[oidc.FLOW]["provider"], "google")
        self.assertEqual(google["prompt"], "select_account")
        self.assertIn("nonce", line)

    def test_line_is_not_asked_to_log_in_again(self):
        # The owner's call (2026-11-14, login-research.md section 10): as strong as Google's, and
        # elders need not remember their LINE password.
        query = off_to(self, press(self.client, "line", "delete_account"), LINE_AUTHORIZE)
        for name in ("prompt", "max_age", "disable_auto_login"):
            with self.subTest(name):
                self.assertNotIn(name, query)

    def test_inside_line_only_the_line_button(self):
        response = self.client.get(CONFIRM_REMOVE_LINE, headers={"user-agent": LINE_BROWSER})
        self.assertEqual(button_order(self, response), [LINE_BUTTON])
        self.assertContains(response, "請用您帳號上的 LINE 再登入一次。")
        # LINE works inside LINE: no need to leave.
        self.assertNotContains(response, OPEN_OUTSIDE)
        response = self.client.get(reverse("delete_account"), headers={"user-agent": LINE_BROWSER})
        self.assertEqual(button_order(self, response), [LINE_BUTTON])
        self.assertContains(response, "您的帳號沒有密碼，請用 LINE 確認是本人。")

    def test_a_provider_not_on_the_account_starts_nothing(self):
        user = line_only_user(username="chen_alan", sub="line-alan")
        self.client.force_login(user)
        response = press(self.client, "google", "delete_account")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(oidc.FLOW, self.client.session)

    def test_without_line_keys_no_line_button(self):
        with self.settings(LINE_CLIENT_ID=""):
            response = self.client.get(CONFIRM_DELETE)
            self.assertEqual(button_order(self, response), [GOOGLE_BUTTON])
            self.assertContains(response, "請用您帳號上的 Google 再登入一次。")
            self.assertEqual(press(self.client, "line", "delete_account").status_code, 200)
            self.assertNotIn(oidc.FLOW, self.client.session)

    def test_with_a_password_line_is_not_a_way_round_it(self):
        user = consented_user(username="wang_ming", password=PASSWORD)
        SignInMethod.objects.create(user=user, provider="line", subject="line-wang")
        self.client.force_login(user)
        response = self.client.get(CONFIRM_DELETE)
        self.assertContains(response, 'name="password"')
        self.assertNotContains(response, LINE_BUTTON)
        response = press(self.client, "line", "delete_account")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(oidc.FLOW, self.client.session)


@google_on
@line_on
class RemoveWithoutPasswordTests(TestCase):
    """#506 acceptance 19: with LINE and Google and no password, either one confirms removing
    the other or itself; the one left stays. Removing is done as the right one comes back, as the
    right password does it on the confirm page."""

    def setUp(self):
        self.user = line_and_google_user()
        self.client.force_login(self.user)

    def test_removing_line_confirmed_with_either(self):
        for name, confirm in (("LINE", confirm_with_line), ("Google", confirm_with_google)):
            with self.subTest(name):
                add = SignInMethod.objects.get_or_create
                add(user=self.user, provider="line", subject=OWN_LINE)
                response = confirm(self, action="remove_line")
                self.assertRedirects(response, SETTINGS_GROUP, fetch_redirect_response=False)
                self.assertEqual(messages_on(self.client), ["已移除 LINE 登入。"])  # W11
                self.assertEqual(methods(self.user), [("google", OWN_GOOGLE)])
                self.assertNotIn(confirm_identity.CONFIRMED, self.client.session)

    def test_removing_google_confirmed_with_either(self):
        for name, confirm in (("LINE", confirm_with_line), ("Google", confirm_with_google)):
            with self.subTest(name):
                add = SignInMethod.objects.get_or_create
                add(user=self.user, provider="google", subject=OWN_GOOGLE)
                response = confirm(self, action="remove_google")
                self.assertRedirects(response, SETTINGS_GROUP, fetch_redirect_response=False)
                self.assertEqual(messages_on(self.client), ["已移除 Google 登入。"])
                self.assertEqual(methods(self.user), [("line", OWN_LINE)])

    def test_the_removed_line_signs_in_nowhere(self):
        confirm_with_line(self, action="remove_line")
        self.client.logout()
        line = FakeLine(self.client)
        line.start()
        self.assertRedirects(line.come_back(sub=OWN_LINE), reverse("line_name"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_line_never_seen_removes_nothing(self):
        response = confirm_with_line(self, sub="line-stranger", action="remove_line")
        self.assertRedirects(response, CONFIRM_REMOVE_LINE, fetch_redirect_response=False)
        self.assertContains(self.client.get(CONFIRM_REMOVE_LINE), NOT_YOUR_LINE)
        self.assertEqual(methods(self.user), [("google", OWN_GOOGLE), ("line", OWN_LINE)])
        self.assertNotIn(confirm_identity.CONFIRMED, self.client.session)

    def test_someone_elses_line_or_google_removes_nothing(self):
        other = line_and_google_user("someone_else", line="line-theirs", google="google-theirs")
        for name, confirm, sub, words in (
            ("LINE", confirm_with_line, "line-theirs", NOT_YOUR_LINE),
            ("Google", confirm_with_google, "google-theirs", NOT_YOUR_GOOGLE),
        ):
            with self.subTest(name):
                response = confirm(self, sub=sub, action="remove_google")
                self.assertRedirects(response, CONFIRM_REMOVE_GOOGLE, fetch_redirect_response=False)
                self.assertContains(self.client.get(CONFIRM_REMOVE_GOOGLE), words)
                self.assertEqual(methods(self.user), [("google", OWN_GOOGLE), ("line", OWN_LINE)])
                self.assertEqual(
                    methods(other), [("google", "google-theirs"), ("line", "line-theirs")]
                )

    def test_the_only_way_in_by_the_time_line_comes_back_is_not_removed(self):
        # Google removed in another tab while at LINE: LINE is now the only way in.
        line = FakeLine(self.client)
        line.authorize = off_to(self, press(self.client, "line", "remove_line"), LINE_AUTHORIZE)
        self.user.sign_in_methods.filter(provider="google").delete()
        self.assertEqual(line.come_back(sub=OWN_LINE).status_code, 403)
        self.assertEqual(methods(self.user), [("line", OWN_LINE)])

    def test_two_browsers_one_after_the_other_leave_one_way_in(self):
        # Both trips started while the account had LINE and Google; the second comes back after
        # the first removed its one.
        other = Client()
        other.force_login(self.user)
        line = FakeLine(self.client)
        line.authorize = off_to(self, press(self.client, "line", "remove_google"), LINE_AUTHORIZE)
        other_line = FakeLine(other)
        other_line.authorize = off_to(self, press(other, "line", "remove_line"), LINE_AUTHORIZE)
        line.come_back(sub=OWN_LINE)
        self.assertEqual(other_line.come_back(sub=OWN_LINE).status_code, 403)
        self.assertEqual(methods(self.user), [("line", OWN_LINE)])

    def test_a_line_confirmation_for_deleting_removes_nothing(self):
        confirm_with_line(self)
        self.client.get(CONFIRM_REMOVE_LINE)
        self.assertEqual(methods(self.user), [("google", OWN_GOOGLE), ("line", OWN_LINE)])

    def test_a_trip_that_fails_comes_back_with_lines_words(self):
        for name, come_back in (
            ("cancelled", {"cancelled": True}),
            ("LINE down", {"token": oidc.Unavailable("down")}),
            ("refused", {"verify": {"error": "invalid_request", "error_description": "x"}}),
            ("forged", {"nonce": "someone-else"}),
        ):
            with self.subTest(name):
                logs = (
                    nullcontext()
                    if name == "cancelled"
                    else self.assertLogs("screening.views.sign_in", "WARNING")
                )
                with logs:
                    response = confirm_with_line(self, action="remove_line", **come_back)
                self.assertRedirects(response, CONFIRM_REMOVE_LINE, fetch_redirect_response=False)
                page = self.client.get(CONFIRM_REMOVE_LINE)
                self.assertContains(page, NOT_CONFIRMED)
                self.assertContains(page, LINE_BUTTON)
                self.assertEqual(methods(self.user), [("google", OWN_GOOGLE), ("line", OWN_LINE)])


@line_on
class ProviderTurnedOffTests(TestCase):
    """A sign-in method whose provider's keys are gone signs in nowhere, so it is no way in: the
    last one that still works is not removed (cross-review of #506, Standards 1)."""

    def setUp(self):
        # Google's keys off (only LINE's on): its row is still on the account.
        self.user = line_and_google_user()
        self.client.force_login(self.user)

    def test_line_is_the_only_way_in_left(self):
        self.assertEqual(self.client.get(CONFIRM_REMOVE_LINE).status_code, 403)
        settings = self.client.get(reverse("account_settings"))
        self.assertNotContains(settings, test_line_sign_in_methods.REMOVE_BUTTON)
        self.assertContains(settings, test_line_sign_in_methods.ONLY_WAY_IN)

    def test_line_coming_back_to_remove_itself_removes_nothing(self):
        # Google's keys taken off while at LINE.
        with google_on:
            line = FakeLine(self.client)
            line.authorize = off_to(self, press(self.client, "line", "remove_line"), LINE_AUTHORIZE)
        self.assertEqual(line.come_back(sub=OWN_LINE).status_code, 403)
        self.assertEqual(methods(self.user), [("google", OWN_GOOGLE), ("line", OWN_LINE)])

    def test_with_a_password_it_can_still_be_removed(self):
        self.user.set_password(PASSWORD)
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.post(CONFIRM_REMOVE_LINE, {"password": PASSWORD})
        self.assertRedirects(response, SETTINGS_GROUP, fetch_redirect_response=False)
        self.assertEqual(methods(self.user), [("google", OWN_GOOGLE)])


@google_on
@line_on
class RemovingAtTheSameMomentTests(TransactionTestCase):
    """Two browsers removing LINE and Google from an account without a password at the same
    moment: whichever comes second waits for the first and is refused, so the account keeps a
    way in (cross-review of #506, Standards 1). Real threads with their own database
    connections; only LINE's answers (post_to_provider) and a pause after each check are put
    in."""

    def test_one_of_two_removals_at_once_is_refused(self):
        user = line_and_google_user()
        # Each trip confirms with the method it removes, so whichever runs second is still
        # confirmed by a method on the account and reaches the removal's check (cross-review
        # recheck on #506, item 1): it must be refused there, not earlier.
        trips = {}
        for provider, authorize_url in (("line", LINE_AUTHORIZE), ("google", GOOGLE_AUTHORIZE)):
            client = Client()
            client.force_login(user)
            response = press(client, provider, f"remove_{provider}")
            trips[provider] = (client, off_to(self, response, authorize_url))
        line_trip, google_trip = trips["line"][1], trips["google"][1]
        line = FakeLine(None)
        line.authorize = line_trip
        google = FakeGoogle(None)
        google.authorize = google_trip

        def answers(url, fields):
            if url == GOOGLE_TOKEN:
                return {"id_token": id_token(**google.claims(OWN_GOOGLE, "lin.mei@example.com"))}
            endpoint = LINE_ENDPOINTS[url]
            if endpoint == "token":
                return {"access_token": "line-access-token", "id_token": "line-id-token"}
            if endpoint == "verify":
                return line.claims(OWN_LINE)
            return {}

        # The first to check waits (at most a second) for the other to check too: without a
        # lock both find the other's sign-in method still there and both remove theirs.
        checked = []
        second_checked = threading.Event()
        real_check = SignInMethod.can_be_removed

        def check_then_pause(method):
            answer = real_check(method)
            checked.append(method.provider)
            if len(checked) == 1:
                second_checked.wait(timeout=1)
            else:
                second_checked.set()
            return answer

        errors = []
        statuses = {}

        def come_back(provider):
            client, authorize = trips[provider]
            try:
                query = {"code": f"{provider}-auth-code", "state": authorize["state"]}
                statuses[provider] = client.get(reverse(f"{provider}_callback"), query).status_code
            except Exception as error:
                errors.append(error)
            finally:
                connection.close()

        threads = [threading.Thread(target=come_back, args=(p,)) for p in trips]
        with (
            mock.patch("screening.oidc.post_to_provider", side_effect=answers),
            mock.patch.object(SignInMethod, "can_be_removed", check_then_pause),
        ):
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(errors, [])
        # Both came back confirmed and reached the check; one removed, the other refused.
        self.assertEqual(set(checked), {"line", "google"})
        self.assertEqual(sorted(statuses.values()), [302, 403])
        self.assertEqual(len(methods(user)), 1)


@line_on
class DeleteLineOnlyTests(TestCase):
    """#506 acceptance 20: an account with LINE alone confirms with LINE, then deletes; a LINE
    that is not the account's deletes nothing."""

    def setUp(self):
        self.user = line_only_user(sub=OWN_LINE)
        self.client.force_login(self.user)

    def test_the_delete_page_offers_line_instead_of_a_password(self):
        response = self.client.get(reverse("delete_account"))
        self.assertNotContains(response, 'name="password"')
        self.assertContains(response, "<li>登入方式（LINE）</li>", html=True)
        self.assertContains(response, "您的帳號沒有密碼，請用 LINE 確認是本人。")
        self.assertContains(response, f'action="{CONFIRM_DELETE}"')
        self.assertEqual(button_order(self, response), [LINE_BUTTON])
        self.assertNotContains(response, DELETE_BUTTON)
        self.assertContains(
            self.client.get(CONFIRM_DELETE),
            "接下來要<strong>刪除帳號</strong>。請用您帳號上的 LINE 再登入一次。",
        )

    def test_inside_line_the_line_button_is_there_too(self):
        for page in (reverse("delete_account"), CONFIRM_DELETE):
            with self.subTest(page):
                response = self.client.get(page, headers={"user-agent": LINE_BROWSER})
                self.assertContains(response, LINE_BUTTON)
                self.assertNotContains(response, OPEN_OUTSIDE)

    def test_own_line_confirms_and_back_on_the_delete_page_delete_deletes(self):
        response = confirm_with_line(self)
        self.assertRedirects(response, CONFIRM_DELETE, target_status_code=302)
        page = self.client.get(response["Location"], follow=True)
        self.assertRedirects(page, reverse("delete_account"))
        self.assertContains(page, CONFIRMED)
        self.assertContains(page, DELETE_BUTTON)
        self.assertNotContains(page, LINE_BUTTON)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

        response = self.client.post(reverse("delete_account"))
        self.assertRedirects(response, reverse("index"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(SignInMethod.objects.filter(subject=OWN_LINE).exists())

    def test_a_line_never_seen_deletes_nothing(self):
        response = confirm_with_line(self, sub="line-stranger")
        self.assertRedirects(response, CONFIRM_DELETE, fetch_redirect_response=False)
        page = self.client.get(CONFIRM_DELETE)
        self.assertContains(page, NOT_YOUR_LINE)
        self.assertContains(page, LINE_BUTTON)
        self.assertNotContains(self.client.get(reverse("delete_account")), CONFIRMED)
        self.client.post(reverse("delete_account"))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_someone_elses_line_deletes_nothing(self):
        other = line_only_user(username="someone_else", sub="line-theirs")
        confirm_with_line(self, sub="line-theirs")
        self.assertContains(self.client.get(CONFIRM_DELETE), NOT_YOUR_LINE)
        self.client.post(reverse("delete_account"))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(User.objects.filter(pk=other.pk).exists())
        self.assertEqual(methods(other), [("line", "line-theirs")])

    def test_a_trip_that_fails_deletes_nothing(self):
        with self.assertLogs("screening.views.sign_in", "WARNING"):
            confirm_with_line(self, token=oidc.Unavailable("down"))
        self.assertContains(self.client.get(CONFIRM_DELETE), NOT_CONFIRMED)
        self.client.post(reverse("delete_account"))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_after_5_minutes_confirm_again(self):
        confirm_with_line(self)
        with later(5 * 60 + 1):
            response = self.client.post(reverse("delete_account"))
            self.assertRedirects(response, reverse("delete_account"), fetch_redirect_response=False)
            page = self.client.get(reverse("delete_account"))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertContains(page, "確認已經過期，請再確認一次。")  # W18
        self.assertContains(page, LINE_BUTTON)

    def test_within_5_minutes_deletes(self):
        confirm_with_line(self)
        with later(5 * 60 - 1):
            self.client.post(reverse("delete_account"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())


@google_on
@line_on
class BoundToItsActionTests(TestCase):
    """A LINE confirmation counts once, for the action it was asked for: one for adding Google
    deletes nothing, one for deleting adds nothing, and someone else's adds nothing."""

    def setUp(self):
        self.user = line_only_user(sub=OWN_LINE)
        self.client.force_login(self.user)

    def test_confirmed_for_adding_google_deletes_nothing(self):
        response = confirm_with_line(self, action="add_google")
        # On to Google to add it, the confirmation used up there.
        self.assertRedirects(response, confirm_url("add_google"), target_status_code=302)
        self.assertRedirects(
            self.client.get(confirm_url("add_google")),
            reverse("google_add"),
            fetch_redirect_response=False,
        )
        off_to(self, self.client.get(reverse("google_add")), GOOGLE_AUTHORIZE)
        self.client.post(reverse("delete_account"))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_confirmed_for_deleting_adds_nothing_and_is_used_up(self):
        confirm_with_line(self)
        response = self.client.get(reverse("google_add"))
        self.assertRedirects(response, confirm_url("add_google"), fetch_redirect_response=False)
        self.client.post(reverse("delete_account"))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_someone_elses_line_adds_nothing(self):
        line_only_user(username="someone_else", sub="line-theirs")
        response = confirm_with_line(self, sub="line-theirs", action="add_google")
        self.assertRedirects(response, confirm_url("add_google"), fetch_redirect_response=False)
        self.assertContains(self.client.get(confirm_url("add_google")), NOT_YOUR_LINE)
        self.assertNotIn(confirm_identity.CONFIRMED, self.client.session)
        response = self.client.get(reverse("google_add"))
        self.assertRedirects(response, confirm_url("add_google"), fetch_redirect_response=False)
        self.assertEqual(methods(self.user), [("line", OWN_LINE)])

    def test_used_once(self):
        confirm_with_line(self)
        self.client.post(reverse("delete_account"))
        self.assertNotIn(confirm_identity.CONFIRMED, self.client.session)


@google_on
@line_on
class BeforeAgreeingTests(TestCase):
    """Deleting one's data is a right before agreeing to the newest privacy notice
    (ConsentRequiredMiddleware): a LINE-only account can confirm with LINE and delete; adding
    and removing still ask to agree first."""

    def check_deletes(self, user):
        self.client.force_login(user)
        response = confirm_with_line(self)
        page = self.client.get(response["Location"], follow=True)
        self.assertRedirects(page, reverse("delete_account"))
        self.assertContains(page, CONFIRMED)
        self.assertRedirects(self.client.post(reverse("delete_account")), reverse("index"))
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def test_never_agreed(self):
        user = line_only_user(sub=OWN_LINE)
        user.consents.all().delete()
        self.check_deletes(user)

    def test_agreed_to_an_older_version_only(self):
        user = line_only_user(sub=OWN_LINE)
        user.consents.update(version=7)
        self.check_deletes(user)

    def test_adding_or_removing_still_asks_to_agree_first(self):
        user = line_and_google_user()
        user.consents.all().delete()
        self.client.force_login(user)
        for action in ("add_line", "remove_line", "remove_google"):
            with self.subTest(action):
                url = confirm_url(action)
                for response in (self.client.get(url), press(self.client, "line", action)):
                    self.assertRedirects(
                        response,
                        f"{reverse('consent')}?next={quote(url, safe='')}",
                        fetch_redirect_response=False,
                    )
                self.assertNotIn(oidc.FLOW, self.client.session)
        self.assertEqual(methods(user), [("google", OWN_GOOGLE), ("line", OWN_LINE)])


def a_newer_notice_goes_live(user):
    """The privacy notice changes while the user is away at the provider: they agreed to the
    one before only."""
    user.consents.update(version=CONSENT_VERSION - 1)


@google_on
@line_on
class NewerNoticeDuringTheTripTests(TestCase):
    """The callback is open before agreeing (signing in is). Coming back to add or remove a
    sign-in method after a newer privacy notice went live goes to agree first and writes
    nothing; only confirming to delete the account goes on (cross-review of #506, Standards
    2)."""

    def test_adding_google_or_line_adds_nothing(self):
        for provider, fake, authorize in (
            ("google", FakeGoogle, GOOGLE_AUTHORIZE),
            ("line", FakeLine, LINE_AUTHORIZE),
        ):
            with self.subTest(provider):
                user = consented_user(username=f"adding_{provider}", password=PASSWORD)
                self.client.force_login(user)
                self.client.post(confirm_url(f"add_{provider}"), {"password": PASSWORD})
                trip = fake(self.client)
                trip.authorize = off_to(
                    self, self.client.get(reverse(f"{provider}_add")), authorize
                )
                a_newer_notice_goes_live(user)
                response = trip.come_back(sub=f"{provider}-new")
                self.assertRedirects(
                    response,
                    test_consent._consent_url(reverse("account_settings")),
                    fetch_redirect_response=False,
                )
                self.assertFalse(SignInMethod.objects.exists())

    def test_removing_with_line_or_google_removes_nothing(self):
        user = line_and_google_user()
        self.client.force_login(user)
        for provider, fake, authorize, sub in (
            ("line", FakeLine, LINE_AUTHORIZE, OWN_LINE),
            ("google", FakeGoogle, GOOGLE_AUTHORIZE, OWN_GOOGLE),
        ):
            with self.subTest(provider):
                user.give_consent()
                trip = fake(self.client)
                pressed = press(self.client, provider, "remove_google")
                trip.authorize = off_to(self, pressed, authorize)
                a_newer_notice_goes_live(user)
                response = trip.come_back(sub=sub)
                self.assertRedirects(
                    response,
                    test_consent._consent_url(CONFIRM_REMOVE_GOOGLE),
                    fetch_redirect_response=False,
                )
                self.assertEqual(methods(user), [("google", OWN_GOOGLE), ("line", OWN_LINE)])

    def test_confirming_to_delete_goes_on(self):
        user = line_only_user(sub=OWN_LINE)
        self.client.force_login(user)
        line = FakeLine(self.client)
        line.authorize = off_to(self, press(self.client, "line", "delete_account"), LINE_AUTHORIZE)
        a_newer_notice_goes_live(user)
        response = line.come_back(sub=OWN_LINE)
        self.assertRedirects(response, CONFIRM_DELETE, target_status_code=302)
        confirmed = self.client.session[confirm_identity.CONFIRMED]
        self.assertEqual(confirmed["action"], "delete_account")
