"""Spec #505 acceptance 14, 22-29 (#511): the 登入方式 group in account settings, where Google
sign-in is added and removed after 確認本人."""

import datetime
import html
import re
from contextlib import nullcontext
from urllib.parse import parse_qsl, urlsplit

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening import oidc
from screening.models import SignInMethod, User
from screening.tests import test_confirm_identity, test_line_in_app_browser
from screening.tests.helpers import GOOGLE_AUTHORIZE, FakeGoogle, consented_user, google_on

PASSWORD = test_confirm_identity.PASSWORD
google_only_user = test_confirm_identity.google_only_user
later = test_confirm_identity.later
LINE = test_line_in_app_browser.LINE_IOS

ADD = "/account/sign-in-methods/google/add"
REMOVE = "/account/sign-in-methods/google/remove"
CONFIRM_ADD = "/account/confirm?action=add_google"
CONFIRM_REMOVE = "/account/confirm?action=remove_google"


def methods_group(response):
    """The 登入方式 section's markup, or None when the page has none."""
    found = re.search(
        r'<section[^>]*id="sign-in-methods".*?</section>', response.content.decode(), re.S
    )
    return found and found.group(0)


def password_user(username="wang_ming", **fields):
    return consented_user(username=username, password=PASSWORD, **fields)


def add_google(user, sub="google-own"):
    return SignInMethod.objects.create(user=user, provider="google", subject=sub)


def off_to_google(test, response):
    """Check a response sends the browser to Google; the query, for FakeGoogle.authorize."""
    location = urlsplit(response["Location"])
    test.assertEqual(f"{location.scheme}://{location.netloc}{location.path}", GOOGLE_AUTHORIZE)
    return dict(parse_qsl(location.query))


def messages_on(client):
    """The words the next page shows at its top (Django's messages)."""
    return [str(message) for message in client.get(reverse("account_settings")).context["messages"]]


@google_on
class GroupTests(TestCase):
    """#505 acceptance 22, 27, 28 (the #507 mockup 5, D5, W12)."""

    def settings_group(self, user, **headers):
        self.client.force_login(user)
        return methods_group(self.client.get(reverse("account_settings"), headers=headers))

    def test_password_and_no_google(self):
        user = password_user()
        self.client.force_login(user)
        response = self.client.get(reverse("account_settings"))
        group = methods_group(response)
        self.assertIsNotNone(group)
        self.assertIn("登入方式", group)
        self.assertRegex(group, r"帳號密碼</span>\s*<span[^>]*>已設定")
        self.assertRegex(group, r"Google</span>\s*<span[^>]*>還沒有新增")
        self.assertIn(f'href="{ADD}" aria-label="新增 Google 登入">新增</a>', group)
        self.assertIn("新增或移除之前，會先請您確認是本人。", group)
        self.assertNotIn(REMOVE, group)
        # Between 我的帳號 and 家人與資料 (D5).
        content = response.content.decode()
        self.assertLess(content.index("我的帳號"), content.index('id="sign-in-methods"'))
        self.assertLess(content.index('id="sign-in-methods"'), content.index("家人與資料"))

    def test_password_and_an_added_google(self):
        user = password_user()
        method = add_google(user)
        added = timezone.make_aware(datetime.datetime(2026, 11, 20, 10, 0))
        SignInMethod.objects.filter(pk=method.pk).update(created_at=added)
        group = self.settings_group(user)
        self.assertRegex(group, r"Google</span>\s*<span[^>]*>2026/11/20 新增")
        self.assertIn(f'action="{REMOVE}"', group)
        self.assertIn(
            'class="danger-link" type="submit" aria-label="移除 Google 登入">移除<', group
        )
        self.assertNotIn(ADD, group)
        self.assertIn("新增或移除之前，會先請您確認是本人。", group)

    # 27
    def test_google_only_has_nothing_to_remove(self):
        group = self.settings_group(google_only_user())
        self.assertRegex(group, r"帳號密碼</span>\s*<span[^>]*>沒有設定")
        self.assertRegex(group, r"Google</span>\s*<span[^>]*>註冊時使用")
        self.assertNotIn(REMOVE, group)
        self.assertNotIn(ADD, group)
        self.assertIn("這是您目前唯一的登入方式，所以不能移除。", group)

    # 28
    def test_admin_accounts_have_no_group(self):
        for username, fields in (("staff", {"is_staff": True}), ("root", {"is_superuser": True})):
            with self.subTest(username):
                self.client.force_login(password_user(username=username, **fields))
                response = self.client.get(reverse("account_settings"))
                self.assertIsNone(methods_group(response))
                self.assertNotContains(response, ADD)

    # 1: nothing to add or remove, so no group.
    def test_without_google_keys_no_group(self):
        user = password_user()
        add_google(user)
        with self.settings(GOOGLE_CLIENT_ID=""):
            self.assertIsNone(self.settings_group(user))

    # The coordinator's call for #511: inside LINE, Google would refuse, so a way out instead.
    def test_inside_line_a_way_out_instead_of_adding(self):
        group = self.settings_group(password_user(), user_agent=LINE)
        self.assertNotIn(ADD, group)
        self.assertIn("用 Safari／Chrome 打開", group)
        self.assertIn('href="/account?openExternalBrowser=1"', group)
        # The guest line is for visitors; a signed-in account's records are kept anyway.
        self.assertNotIn("篩檢結果不會跟著過去", group)

    def test_inside_line_removing_needs_no_google(self):
        user = password_user()
        add_google(user)
        group = self.settings_group(user, user_agent=LINE)
        self.assertIn(REMOVE, group)
        self.assertNotIn("用 Safari／Chrome 打開", group)


def confirm_with_password(test, confirm_url):
    response = test.client.post(confirm_url, {"password": PASSWORD})
    test.assertEqual(response.status_code, 302)
    return response


@google_on
class AddTests(TestCase):
    """#505 acceptance 23-25, 29: 新增 Google 登入."""

    def setUp(self):
        self.user = password_user(email="wang.ming@example.com")
        self.client.force_login(self.user)
        self.google = FakeGoogle(self.client)

    def start_adding(self):
        """Confirm with the password and follow on to Google."""
        response = confirm_with_password(self, CONFIRM_ADD)
        self.assertRedirects(response, ADD, fetch_redirect_response=False)
        self.google.authorize = off_to_google(self, self.client.get(ADD))

    # 23
    def test_adding_asks_who_it_is_first(self):
        response = self.client.get(ADD)
        self.assertRedirects(response, CONFIRM_ADD)
        self.assertNotIn(oidc.FLOW, self.client.session)
        page = self.client.get(CONFIRM_ADD)
        self.assertContains(
            page, "接下來要<strong>新增 Google 登入</strong>。請輸入 wang_ming 的密碼。"
        )

    # 23
    def test_a_wrong_password_does_not_go_to_google(self):
        response = self.client.post(CONFIRM_ADD, {"password": "wrong"})
        self.assertContains(response, "密碼不正確")
        self.assertRedirects(self.client.get(ADD), CONFIRM_ADD)
        self.assertNotIn(oidc.FLOW, self.client.session)

    # 23
    def test_the_right_password_goes_on_to_google_for_adding(self):
        self.start_adding()
        self.assertEqual(self.client.session[oidc.FLOW]["purpose"], "add_method")

    def test_google_is_asked_to_show_its_account_chooser(self):
        # So the user picks which Google to add, not whichever the phone is signed into; no
        # login_hint, which would skip the chooser.
        self.start_adding()
        self.assertEqual(self.google.authorize["prompt"], "select_account")
        self.assertNotIn("login_hint", self.google.authorize)

    # 24
    def test_a_new_google_is_added_and_signs_into_the_same_account(self):
        self.start_adding()
        response = self.google.come_back(sub="google-new", email="other@gmail.com")
        self.assertRedirects(response, reverse("account_settings"), fetch_redirect_response=False)
        self.assertEqual(
            messages_on(self.client), ["已新增 Google 登入。下次可以直接用 Google 登入。"]
        )
        method = SignInMethod.objects.get()
        self.assertEqual(
            (method.user, method.provider, method.subject, method.used_to_register),
            (self.user, "google", "google-new", False),
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "wang.ming@example.com")
        self.assertTrue(self.user.check_password(PASSWORD))
        # Afterwards Google signs into this same account.
        self.client.logout()
        self.google.start()
        self.google.come_back(sub="google-new", email="other@gmail.com")
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
        self.assertEqual(User.objects.count(), 1)

    # 25
    def test_a_google_on_another_account_is_not_added(self):
        other = google_only_user(username="lin_mei", sub="google-taken")
        self.start_adding()
        response = self.google.come_back(sub="google-taken", email="lin.mei@gmail.com")
        self.assertRedirects(response, reverse("account_settings"), fetch_redirect_response=False)
        self.assertEqual(
            messages_on(self.client), ["這個 Google 帳號已經用在另一個聽伴帳號，所以沒有新增。"]
        )
        self.assertFalse(self.user.sign_in_methods.exists())
        self.assertEqual(
            list(SignInMethod.objects.values_list("user", "subject", "used_to_register")),
            [(other.pk, "google-taken", True)],
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "wang.ming@example.com")
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    # 29
    def test_after_5_minutes_confirm_again(self):
        confirm_with_password(self, CONFIRM_ADD)
        with later(5 * 60 + 1):
            response = self.client.get(ADD)
            self.assertRedirects(response, CONFIRM_ADD, fetch_redirect_response=False)
            self.assertContains(self.client.get(CONFIRM_ADD), "確認已經過期，請再確認一次。")
        self.assertNotIn(oidc.FLOW, self.client.session)

    def test_one_confirmation_one_trip(self):
        self.start_adding()
        self.assertRedirects(self.client.get(ADD), CONFIRM_ADD)

    def test_a_trip_that_fails_comes_back_to_account_settings(self):
        for name, come_back in (
            ("cancelled", {"cancelled": True}),
            ("google down", {"exchange": oidc.Unavailable("down")}),
            ("forged", {"nonce": "someone-else"}),
        ):
            with self.subTest(name):
                self.start_adding()
                with (
                    self.assertLogs("screening.views.sign_in", "WARNING")
                    if name != "cancelled"
                    else nullcontext()
                ):
                    response = self.google.come_back(**come_back)
                self.assertRedirects(
                    response, reverse("account_settings"), fetch_redirect_response=False
                )
                self.assertEqual(
                    messages_on(self.client), ["沒有完成新增 Google 登入，請再試一次。"]
                )
                self.assertFalse(SignInMethod.objects.exists())
                self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_an_account_with_google_already_has_nothing_to_add(self):
        add_google(self.user)
        confirm_with_password(self, CONFIRM_ADD)
        self.assertRedirects(self.client.get(ADD), reverse("account_settings"))
        self.assertNotIn(oidc.FLOW, self.client.session)

    def test_only_a_link_to_follow(self):
        confirm_with_password(self, CONFIRM_ADD)
        self.assertEqual(self.client.post(ADD).status_code, 405)
        self.assertNotIn(oidc.FLOW, self.client.session)

    def test_without_google_keys_is_404(self):
        with self.settings(GOOGLE_CLIENT_ID=""):
            self.assertEqual(self.client.get(ADD).status_code, 404)

    def test_logged_out_goes_to_log_in(self):
        self.client.logout()
        response = self.client.get(ADD)
        self.assertRedirects(response, f"{reverse('login')}?next={ADD}")


@google_on
class AdminTests(TestCase):
    """#505 acceptance 28: an admin account is refused whatever it sends."""

    def setUp(self):
        self.admin = password_user(username="admin", is_staff=True)
        self.client.force_login(self.admin)
        # Even confirmed: confirming is not what keeps an admin out.
        confirm_with_password(self, test_confirm_identity.CONFIRM_DELETE)

    def test_adding_is_refused(self):
        self.assertEqual(self.client.get(ADD).status_code, 403)
        self.assertNotIn(oidc.FLOW, self.client.session)

    def test_a_superuser_is_refused_too(self):
        User.objects.filter(pk=self.admin.pk).update(is_staff=False, is_superuser=True)
        self.assertEqual(self.client.get(ADD).status_code, 403)
        self.assertNotIn(oidc.FLOW, self.client.session)

    def test_removing_is_refused(self):
        # An admin should never have one; if one is there, removing is still not theirs to do.
        add_google(self.admin)
        self.assertEqual(self.client.post(REMOVE).status_code, 403)
        self.assertTrue(self.admin.sign_in_methods.exists())

    def test_made_admin_during_the_trip_nothing_is_added(self):
        User.objects.filter(pk=self.admin.pk).update(is_staff=False)
        google = FakeGoogle(self.client)
        confirm_with_password(self, CONFIRM_ADD)
        google.authorize = off_to_google(self, self.client.get(ADD))
        User.objects.filter(pk=self.admin.pk).update(is_staff=True)
        response = google.come_back(sub="google-admin", email="admin@example.com")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(SignInMethod.objects.exists())


@google_on
class RemoveTests(TestCase):
    """#505 acceptance 26, 27, 29: 移除 Google 登入."""

    def setUp(self):
        self.user = password_user(email="wang.ming@example.com")
        add_google(self.user, sub="google-own")
        self.client.force_login(self.user)

    # 26
    def test_removing_after_the_password_and_google_no_longer_knows_it(self):
        response = self.client.post(REMOVE)
        self.assertRedirects(response, CONFIRM_REMOVE)
        self.assertContains(
            self.client.get(CONFIRM_REMOVE), "接下來要<strong>移除 Google 登入</strong>。"
        )
        self.assertTrue(self.user.sign_in_methods.exists())
        # The right password removes it straight away: the browser takes the POST on (307).
        response = self.client.post(CONFIRM_REMOVE, {"password": PASSWORD}, follow=True)
        self.assertEqual(
            response.redirect_chain, [(REMOVE, 307), (reverse("account_settings"), 302)]
        )
        self.assertEqual(
            [str(message) for message in response.context["messages"]], ["已移除 Google 登入。"]
        )
        self.assertFalse(SignInMethod.objects.exists())
        # Signing in with that Google is now a code never seen: off to make a new account.
        self.client.logout()
        google = FakeGoogle(self.client)
        google.start()
        response = google.come_back(sub="google-own", email="someone@gmail.com")
        self.assertRedirects(response, reverse("google_name"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_link_cannot_remove_even_when_confirmed(self):
        # A page elsewhere can make the browser GET any URL (an <img>), with this session.
        self.client.post(CONFIRM_REMOVE, {"password": PASSWORD})
        self.assertEqual(self.client.get(REMOVE).status_code, 405)
        self.assertTrue(self.user.sign_in_methods.exists())

    def test_back_on_the_confirm_page_it_is_shown_not_sent_to_a_get(self):
        self.client.post(CONFIRM_REMOVE, {"password": PASSWORD})  # the 307 not followed
        response = self.client.get(CONFIRM_REMOVE)
        self.assertContains(response, "接下來要<strong>移除 Google 登入</strong>。")
        self.assertTrue(self.user.sign_in_methods.exists())

    def test_a_post_from_another_site_is_refused(self):
        self.client.post(CONFIRM_REMOVE, {"password": PASSWORD})
        # The same session, posting without this site's CSRF token.
        other_site = self.client_class(enforce_csrf_checks=True)
        other_site.cookies = self.client.cookies
        self.assertEqual(other_site.post(REMOVE).status_code, 403)
        self.assertTrue(self.user.sign_in_methods.exists())

    def test_a_confirmation_for_another_action_does_not_remove(self):
        # 確認本人 for 新增 is left unused: this account already has Google, so 新增 goes back.
        confirm_with_password(self, CONFIRM_ADD)
        self.assertRedirects(self.client.get(ADD), reverse("account_settings"))
        self.assertRedirects(self.client.post(REMOVE), CONFIRM_REMOVE)
        self.assertTrue(self.user.sign_in_methods.exists())

    def test_the_settings_page_removes_with_a_form(self):
        group = methods_group(self.client.get(reverse("account_settings")))
        self.assertRegex(
            group,
            rf'<form method="post" action="{REMOVE}">\s*<input type="hidden" '
            r'name="csrfmiddlewaretoken"[^>]*>\s*<button class="danger-link" type="submit" '
            r'aria-label="移除 Google 登入">移除</button>',
        )

    # 27
    def test_the_only_way_in_cannot_be_removed_even_when_sent_directly(self):
        user = google_only_user(username="lin_mei", sub="google-only")
        self.client.force_login(user)
        test_confirm_identity.confirm_with_google(self, sub="google-only", action="remove_google")
        self.assertEqual(self.client.post(REMOVE).status_code, 403)
        self.assertEqual(self.client.get(REMOVE).status_code, 405)
        self.assertTrue(user.sign_in_methods.exists())

    # 29
    def test_after_5_minutes_confirm_again(self):
        self.client.post(CONFIRM_REMOVE, {"password": PASSWORD})
        with later(5 * 60 + 1):
            response = self.client.post(REMOVE)
            self.assertRedirects(response, CONFIRM_REMOVE, fetch_redirect_response=False)
        self.assertTrue(self.user.sign_in_methods.exists())

    def test_without_confirming_nothing_is_removed(self):
        self.assertRedirects(self.client.post(REMOVE), CONFIRM_REMOVE)
        self.assertTrue(self.user.sign_in_methods.exists())

    def test_only_this_accounts_google(self):
        # Another account's Google is never this account's to remove.
        other = google_only_user(username="lin_mei", sub="google-other")
        SignInMethod.objects.filter(user=self.user).delete()
        self.client.post(CONFIRM_REMOVE, {"password": PASSWORD})
        self.assertEqual(self.client.post(REMOVE).status_code, 404)
        self.assertTrue(other.sign_in_methods.exists())

    def test_without_google_keys_is_404(self):
        self.client.post(CONFIRM_REMOVE, {"password": PASSWORD})
        with self.settings(GOOGLE_CLIENT_ID=""):
            self.assertEqual(self.client.post(REMOVE).status_code, 404)
        self.assertTrue(self.user.sign_in_methods.exists())


@google_on
class SameEmailTests(TestCase):
    """#505 acceptance 14: from the same-email page, the password leads to this group."""

    def test_signing_in_with_the_password_lands_on_the_group(self):
        user = password_user(email="a@example.com")
        google = FakeGoogle(self.client)
        google.start()
        google.come_back(sub="google-new", email="a@example.com")
        page = self.client.get(reverse("google_same_email")).content.decode()
        href = html.unescape(re.search(r'<a class="w-full btn[^"]*" href="([^"]+)">', page)[1])
        response = self.client.post(href, {"username": "wang_ming", "password": PASSWORD})
        self.assertEqual(response["Location"], "/account#sign-in-methods")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        group = methods_group(self.client.get(response["Location"]))
        self.assertIn(f'href="{ADD}"', group)


@google_on
class InsideLineTests(TestCase):
    """The coordinator's call for #511: inside LINE's browser Google would refuse to sign in, so
    the confirm and delete pages offer Safari or Chrome instead of 使用 Google 帳戶確認."""

    def setUp(self):
        self.client.force_login(google_only_user())

    def test_the_confirm_page(self):
        response = self.client.get(
            test_confirm_identity.CONFIRM_DELETE, headers={"user-agent": LINE}
        )
        self.assertNotContains(response, "使用 Google 帳戶確認")
        self.assertContains(response, "用 Safari／Chrome 打開")
        self.assertContains(
            response, 'href="/account/confirm?action=delete_account&amp;openExternalBrowser=1"'
        )
        self.assertNotContains(response, "篩檢結果不會跟著過去")

    def test_the_delete_page(self):
        response = self.client.get(reverse("delete_account"), headers={"user-agent": LINE})
        self.assertNotContains(response, "使用 Google 帳戶確認")
        self.assertContains(response, 'href="/account/delete?openExternalBrowser=1"')
        self.assertNotContains(response, ">刪除帳號</button>")

    def test_outside_line_the_google_button(self):
        for page in (test_confirm_identity.CONFIRM_DELETE, reverse("delete_account")):
            with self.subTest(page):
                response = self.client.get(
                    page, headers={"user-agent": test_line_in_app_browser.SAFARI}
                )
                self.assertContains(response, "使用 Google 帳戶確認")
                self.assertNotContains(response, "openExternalBrowser")
