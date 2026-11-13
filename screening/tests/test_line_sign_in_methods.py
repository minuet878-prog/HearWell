"""Spec #506 acceptance 15-18, 22 (ticket #541, the #539 mockup 5, D4, W7, W11): the LINE row
in account settings' 登入方式 group, where LINE sign-in is added and removed after 確認本人, by
the same rules as Google's (#511)."""

import datetime
import re
from contextlib import nullcontext
from unittest import mock
from urllib.parse import parse_qsl, urlsplit

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from screening import oidc
from screening.models import Audiogram, SignInMethod, User
from screening.models.sign_in import SignInMethodQuerySet
from screening.tests import (
    test_confirm_identity,
    test_line_in_app_browser,
    test_sign_in_methods_settings,
)
from screening.tests.helpers import LINE_AUTHORIZE, FakeLine, consented_user, google_on, line_on

PASSWORD = test_confirm_identity.PASSWORD
later = test_confirm_identity.later
methods_group = test_sign_in_methods_settings.methods_group
messages_on = test_sign_in_methods_settings.messages_on
password_user = test_sign_in_methods_settings.password_user
add_google = test_sign_in_methods_settings.add_google
confirm_with_password = test_sign_in_methods_settings.confirm_with_password
form_csrf_token = test_sign_in_methods_settings.form_csrf_token
LINE = test_line_in_app_browser.LINE_IOS

ADD = "/account/sign-in-methods/line/add"
ADD_LINK = f'href="{ADD}" aria-label="新增 LINE 登入">新增</a>'
GOOGLE_ADD = test_sign_in_methods_settings.ADD
REMOVE_BUTTON = '<input type="hidden" name="action" value="remove_line">'
CONFIRM_ADD = "/account/confirm?action=add_line"
CONFIRM_REMOVE = "/account/confirm?action=remove_line"
TAKEN = "這個 LINE 帳號已經用在另一個帳號。"  # W7
ADDED = "已新增 LINE 登入。下次可以直接用 LINE 登入。"  # W11
REMOVED = "已移除 LINE 登入。"  # W11
NOT_ADDED = "沒有完成新增 LINE 登入，請再試一次。"
CONFIRM_FIRST = "新增或移除之前，會先請您確認是本人。"
ONLY_WAY_IN = "這是您目前唯一的登入方式，所以不能移除。"
OPEN_OUTSIDE = "用 Safari／Chrome 打開"


def line_only_user(username="chen_alan", sub="line-own"):
    """An account made with LINE: no usable password, one LINE sign-in method."""
    user = consented_user(username=username)
    SignInMethod.objects.create(user=user, provider="line", subject=sub, used_to_register=True)
    return user


def add_line(user, sub="line-own"):
    return SignInMethod.objects.create(user=user, provider="line", subject=sub)


def off_to_line(test, response):
    """Check a response sends the browser to LINE; the query, for FakeLine.authorize."""
    location = urlsplit(response["Location"])
    test.assertEqual(f"{location.scheme}://{location.netloc}{location.path}", LINE_AUTHORIZE)
    return dict(parse_qsl(location.query))


def row(group, name):
    """One row of the group, by its name (帳號密碼, Google, LINE)."""
    found = re.search(
        rf'<li class="sign-in-method">(?:(?!</li>).)*?settings-row-title">{name}</span>.*?</li>',
        group,
        re.S,
    )
    return found and found.group(0)


def row_names(group):
    return re.findall(r'settings-row-title">([^<]+)</span>', group)


@google_on
@line_on
class GroupTests(TestCase):
    """#506 acceptance 1, 15, 18, 22 (the #539 mockup 5, D4)."""

    def settings_group(self, user, **headers):
        self.client.force_login(user)
        return methods_group(self.client.get(reverse("account_settings"), headers=headers))

    # 15
    def test_three_rows_and_line_can_be_added(self):
        group = self.settings_group(password_user())
        self.assertEqual(row_names(group), ["帳號密碼", "Google", "LINE"])  # D4
        line = row(group, "LINE")
        self.assertRegex(line, r"LINE</span>\s*<span[^>]*>還沒有新增")
        self.assertIn('class="btn-line-logo"', line)
        self.assertIn(ADD_LINK, line)
        self.assertNotIn(REMOVE_BUTTON, group)
        self.assertIn(CONFIRM_FIRST, group)

    def test_an_added_line_can_be_removed(self):
        user = password_user()
        method = add_line(user)
        added = timezone.make_aware(datetime.datetime(2026, 11, 20, 10, 0))
        SignInMethod.objects.filter(pk=method.pk).update(created_at=added)
        line = row(self.settings_group(user), "LINE")
        self.assertRegex(line, r"LINE</span>\s*<span[^>]*>2026/11/20 新增")
        self.assertIn(REMOVE_BUTTON, line)
        self.assertIn('class="danger-link" type="submit" aria-label="移除 LINE 登入">移除<', line)
        self.assertNotIn(ADD, line)

    # 18
    def test_line_only_has_nothing_to_remove(self):
        group = self.settings_group(line_only_user())
        self.assertRegex(row(group, "帳號密碼"), r"沒有設定")
        line = row(group, "LINE")
        self.assertRegex(line, r"LINE</span>\s*<span[^>]*>註冊時使用")
        self.assertNotIn(REMOVE_BUTTON, group)
        self.assertNotIn(ADD, group)
        self.assertIn(ONLY_WAY_IN, group)
        self.assertNotIn(CONFIRM_FIRST, group)
        # Google can still be added (the mockup's 只有 LINE).
        self.assertIn(GOOGLE_ADD, row(group, "Google"))

    def test_line_and_google_without_a_password_either_can_be_removed(self):
        user = line_only_user()
        add_google(user)
        group = self.settings_group(user)
        self.assertIn(REMOVE_BUTTON, row(group, "LINE"))
        self.assertIn('value="remove_google"', row(group, "Google"))
        self.assertNotIn(ONLY_WAY_IN, group)

    # 22
    def test_admin_accounts_have_no_group(self):
        for username, fields in (("staff", {"is_staff": True}), ("root", {"is_superuser": True})):
            with self.subTest(username):
                self.client.force_login(password_user(username=username, **fields))
                response = self.client.get(reverse("account_settings"))
                self.assertIsNone(methods_group(response))
                self.assertNotContains(response, ADD)

    def test_admin_accounts_have_no_group_with_line_alone(self):
        with self.settings(GOOGLE_CLIENT_ID=""):
            self.client.force_login(password_user(username="staff", is_staff=True))
            self.assertIsNone(methods_group(self.client.get(reverse("account_settings"))))

    # 1
    def test_without_line_keys_no_line_row(self):
        user = password_user()
        add_line(user)
        with self.settings(LINE_CLIENT_ID=""):
            group = self.settings_group(user)
        self.assertEqual(row_names(group), ["帳號密碼", "Google"])
        self.assertNotIn("LINE", group)

    def test_line_keys_alone_show_the_line_row(self):
        with self.settings(GOOGLE_CLIENT_ID=""):
            group = self.settings_group(password_user())
        self.assertEqual(row_names(group), ["帳號密碼", "LINE"])
        self.assertIn(ADD_LINK, group)

    def test_without_either_keys_no_group(self):
        user = password_user()
        add_line(user)
        with self.settings(GOOGLE_CLIENT_ID="", LINE_CLIENT_ID=""):
            self.assertIsNone(self.settings_group(user))


@google_on
@line_on
class InsideLineGroupTests(TestCase):
    """Inside LINE's browser the LINE row works as anywhere; only Google's row gives way to the
    open-in-Safari-or-Chrome box (#511)."""

    def settings_group(self, user):
        self.client.force_login(user)
        return methods_group(
            self.client.get(reverse("account_settings"), headers={"user-agent": LINE})
        )

    def test_line_can_be_added_inside_line(self):
        group = self.settings_group(password_user())
        self.assertIn(ADD_LINK, row(group, "LINE"))
        self.assertNotIn(GOOGLE_ADD, group)
        self.assertIn(OPEN_OUTSIDE, group)
        self.assertIn(CONFIRM_FIRST, group)

    def test_line_only_inside_line(self):
        # The mockup's 只有 LINE・在 LINE 裡打開: the only-way-in line, then the box.
        group = self.settings_group(line_only_user())
        self.assertNotIn(GOOGLE_ADD, group)
        self.assertNotIn(REMOVE_BUTTON, group)
        self.assertIn(ONLY_WAY_IN, group)
        self.assertLess(group.index(ONLY_WAY_IN), group.index(OPEN_OUTSIDE))

    def test_line_can_be_removed_inside_line(self):
        user = password_user()
        add_line(user)
        add_google(user)
        group = self.settings_group(user)
        self.assertIn(REMOVE_BUTTON, row(group, "LINE"))
        self.assertNotIn(OPEN_OUTSIDE, group)

    def test_adding_goes_to_line_inside_line(self):
        self.client.force_login(password_user())
        confirm_with_password(self, CONFIRM_ADD)
        response = self.client.get(ADD, headers={"user-agent": LINE})
        self.assertEqual(off_to_line(self, response)["scope"], "openid")


@line_on
class AddTests(TestCase):
    """#506 acceptance 16, 17: 新增 LINE 登入."""

    def setUp(self):
        self.user = password_user(email="wang.ming@example.com")
        self.client.force_login(self.user)
        self.line = FakeLine(self.client)

    def start_adding(self, client=None, line=None):
        """Confirm with the password and follow on to LINE (in this test's browser unless
        another is given)."""
        client = client or self.client
        response = client.post(CONFIRM_ADD, {"password": PASSWORD})
        self.assertRedirects(response, ADD, fetch_redirect_response=False)
        (line or self.line).authorize = off_to_line(self, client.get(ADD))

    def test_adding_asks_who_it_is_first(self):
        response = self.client.get(ADD)
        self.assertRedirects(response, CONFIRM_ADD)
        self.assertNotIn(oidc.FLOW, self.client.session)
        self.assertContains(
            self.client.get(CONFIRM_ADD),
            "接下來要<strong>新增 LINE 登入</strong>。請輸入 wang_ming 的密碼。",
        )

    def test_a_wrong_password_does_not_go_to_line(self):
        response = self.client.post(CONFIRM_ADD, {"password": "wrong"})
        self.assertContains(response, "密碼不正確")
        self.assertRedirects(self.client.get(ADD), CONFIRM_ADD)
        self.assertNotIn(oidc.FLOW, self.client.session)

    def test_the_right_password_goes_on_to_line_for_adding(self):
        self.start_adding()
        flow = self.client.session[oidc.FLOW]
        self.assertEqual((flow["provider"], flow["purpose"]), ("line", "add_method"))
        # The owner's call (#542): LINE is not asked for a fresh login.
        self.assertNotIn("prompt", self.line.authorize)
        self.assertNotIn("disable_auto_login", self.line.authorize)

    # 16
    def test_a_new_line_is_added_and_signs_into_the_same_account(self):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=datetime.date(2026, 3, 4))
        self.start_adding()
        response = self.line.come_back(sub="line-new")
        self.assertRedirects(response, reverse("account_settings"), fetch_redirect_response=False)
        self.assertEqual(messages_on(self.client), [ADDED])
        method = SignInMethod.objects.get()
        self.assertEqual(
            (method.user, method.provider, method.subject, method.used_to_register),
            (self.user, "line", "line-new", False),
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "wang.ming@example.com")
        self.assertTrue(self.user.check_password(PASSWORD))
        # The access token is given back to LINE here too.
        self.assertEqual(self.line.endpoints(), ["token", "verify", "revoke"])
        # Afterwards LINE signs into this same account, with the same records.
        self.client.logout()
        self.line.start()
        self.line.come_back(sub="line-new")
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
        self.assertEqual(User.objects.count(), 1)
        page = self.client.get(reverse("audiogram_detail", args=[audiogram.pk]))
        self.assertContains(page, "2026/03/04")

    # 17
    def test_a_line_on_another_account_is_not_added(self):
        other = line_only_user(username="lin_mei", sub="line-taken")
        self.start_adding()
        response = self.line.come_back(sub="line-taken")
        self.assertRedirects(response, reverse("account_settings"), fetch_redirect_response=False)
        self.assertEqual(messages_on(self.client), [TAKEN])
        self.assertFalse(self.user.sign_in_methods.exists())
        self.assertEqual(
            list(SignInMethod.objects.values_list("user", "subject", "used_to_register")),
            [(other.pk, "line-taken", True)],
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "wang.ming@example.com")
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    # 17: two accounts add the same LINE at once; whoever comes back first has it.
    def test_two_accounts_adding_the_same_line_at_once(self):
        other = password_user(username="lin_mei")
        other_client = Client()
        other_client.force_login(other)
        other_line = FakeLine(other_client)
        self.start_adding()
        self.start_adding(client=other_client, line=other_line)
        self.line.come_back(sub="line-shared")
        response = other_line.come_back(sub="line-shared")
        self.assertRedirects(response, reverse("account_settings"), fetch_redirect_response=False)
        self.assertEqual(messages_on(other_client), [TAKEN])
        self.assertEqual(
            list(SignInMethod.objects.values_list("user", "subject")),
            [(self.user.pk, "line-shared")],
        )
        self.assertFalse(other.sign_in_methods.exists())

    def test_the_same_account_adding_two_lines_at_once_keeps_the_first(self):
        # Two browsers of this account each add a different LINE (cross-review of #506,
        # Standards 4): one LINE per account, so the second is not added, not a server error.
        other_client = Client()
        other_client.force_login(self.user)
        other_line = FakeLine(other_client)
        self.start_adding()
        self.start_adding(client=other_client, line=other_line)
        self.line.come_back(sub="line-first")
        response = other_line.come_back(sub="line-second")
        self.assertRedirects(response, reverse("account_settings"), fetch_redirect_response=False)
        self.assertEqual(messages_on(other_client), [NOT_ADDED])
        self.assertEqual(
            list(self.user.sign_in_methods.values_list("provider", "subject")),
            [("line", "line-first")],
        )

    # 17: the other account takes it between the check and the insert.
    def test_a_line_added_to_another_account_meanwhile_is_not_added(self):
        real = SignInMethodQuerySet.for_identity

        class TakenRightAfterTheCheck:
            def __init__(self, rows, subject):
                self.rows = rows
                self.subject = subject

            def exists(self):
                found = self.rows.exists()
                if not User.objects.filter(username="lin_mei").exists():
                    line_only_user(username="lin_mei", sub=self.subject)
                return found

        def for_identity(queryset, identity):
            return TakenRightAfterTheCheck(real(queryset, identity), identity.subject)

        self.start_adding()
        with mock.patch.object(SignInMethodQuerySet, "for_identity", for_identity):
            response = self.line.come_back(sub="line-race")
        self.assertRedirects(response, reverse("account_settings"), fetch_redirect_response=False)
        self.assertEqual(messages_on(self.client), [TAKEN])
        self.assertFalse(self.user.sign_in_methods.exists())
        self.assertEqual(
            list(SignInMethod.objects.values_list("user__username", "subject")),
            [("lin_mei", "line-race")],
        )

    def test_a_trip_that_fails_comes_back_to_account_settings(self):
        for name, come_back, logged in (
            ("cancelled", {"cancelled": True}, False),
            ("LINE down", {"token": oidc.Unavailable("down")}, True),
            ("forged", {"nonce": "someone-else"}, True),
        ):
            with self.subTest(name):
                self.start_adding()
                with (
                    self.assertLogs("screening.views.sign_in", "ERROR") if logged else nullcontext()
                ):
                    response = self.line.come_back(**come_back)
                self.assertRedirects(
                    response, reverse("account_settings"), fetch_redirect_response=False
                )
                self.assertEqual(messages_on(self.client), [NOT_ADDED])
                self.assertFalse(SignInMethod.objects.exists())
                self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_after_5_minutes_confirm_again(self):
        confirm_with_password(self, CONFIRM_ADD)
        with later(5 * 60 + 1):
            response = self.client.get(ADD)
            self.assertRedirects(response, CONFIRM_ADD, fetch_redirect_response=False)
        self.assertNotIn(oidc.FLOW, self.client.session)

    @google_on
    def test_a_confirmation_for_google_does_not_add_line(self):
        confirm_with_password(self, test_sign_in_methods_settings.CONFIRM_ADD)
        self.assertRedirects(self.client.get(ADD), CONFIRM_ADD)
        self.assertNotIn(oidc.FLOW, self.client.session)

    def test_an_account_with_line_already_has_nothing_to_add(self):
        add_line(self.user)
        confirm_with_password(self, CONFIRM_ADD)
        self.assertRedirects(self.client.get(ADD), reverse("account_settings"))
        self.assertNotIn(oidc.FLOW, self.client.session)

    def test_only_a_link_to_follow(self):
        confirm_with_password(self, CONFIRM_ADD)
        self.assertEqual(self.client.post(ADD).status_code, 405)
        self.assertNotIn(oidc.FLOW, self.client.session)

    # 1
    def test_without_line_keys_is_404(self):
        with self.settings(LINE_CLIENT_ID=""):
            self.assertEqual(self.client.get(ADD).status_code, 404)
            self.assertEqual(self.client.get(CONFIRM_REMOVE).status_code, 404)

    def test_logged_out_goes_to_log_in(self):
        self.client.logout()
        self.assertRedirects(self.client.get(ADD), f"{reverse('login')}?next={ADD}")


@line_on
class AdminTests(TestCase):
    """#506 acceptance 22: an admin account is refused whatever it sends."""

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
        add_line(self.admin)
        self.assertEqual(self.client.get(CONFIRM_REMOVE).status_code, 403)
        self.assertEqual(self.client.post(CONFIRM_REMOVE, {"password": PASSWORD}).status_code, 403)
        self.assertTrue(self.admin.sign_in_methods.exists())

    def test_made_admin_during_the_trip_nothing_is_added(self):
        User.objects.filter(pk=self.admin.pk).update(is_staff=False)
        line = FakeLine(self.client)
        confirm_with_password(self, CONFIRM_ADD)
        line.authorize = off_to_line(self, self.client.get(ADD))
        User.objects.filter(pk=self.admin.pk).update(is_staff=True)
        response = line.come_back(sub="line-admin")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(SignInMethod.objects.exists())


@line_on
class RemoveTests(TestCase):
    """#506 acceptance 18 and #505's rule: 移除 LINE 登入 asks for the password on the confirm
    page, and the right password, POSTed with this site's CSRF token, removes it there."""

    def setUp(self):
        self.user = password_user(email="wang.ming@example.com")
        add_line(self.user, sub="line-own")
        self.client = self.client_class(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def send_password(self, password=PASSWORD):
        token = form_csrf_token(self.client.get(CONFIRM_REMOVE))
        return self.client.post(
            CONFIRM_REMOVE, {"password": password, "csrfmiddlewaretoken": token}
        )

    def send_password_status(self):
        """The status of a POST with the password and this site's CSRF token, for a page that is
        refused and has no form to take the token from."""
        self.client.get(reverse("account_settings"))
        token = self.client.cookies["csrftoken"].value
        return self.client.post(
            CONFIRM_REMOVE, {"password": PASSWORD, "csrfmiddlewaretoken": token}
        ).status_code

    def test_the_settings_button_leads_to_the_confirm_page(self):
        group = methods_group(self.client.get(reverse("account_settings")))
        form = re.search(
            r'<form method="get" action="([^"]+)">((?:(?!</form>).)*remove_line.*?)</form>',
            group,
            re.S,
        )
        self.assertEqual(form[1], reverse("confirm_identity"))
        self.assertIn(
            '<button class="danger-link" type="submit" aria-label="移除 LINE 登入">移除</button>',
            form[2],
        )
        self.assertContains(
            self.client.get(CONFIRM_REMOVE),
            "接下來要<strong>移除 LINE 登入</strong>。請輸入 wang_ming 的密碼。",
        )
        self.assertTrue(self.user.sign_in_methods.exists())

    def test_the_right_password_removes_it_and_line_no_longer_knows_it(self):
        response = self.send_password()
        settings_group = f"{reverse('account_settings')}#sign-in-methods"
        self.assertRedirects(response, settings_group, fetch_redirect_response=False)
        self.assertEqual(messages_on(self.client), [REMOVED])
        self.assertFalse(SignInMethod.objects.exists())
        # Signing in with that LINE is now a code never seen: off to make a new account.
        self.client.logout()
        line = FakeLine(self.client)
        line.start()
        self.assertRedirects(line.come_back(sub="line-own"), reverse("line_name"))
        self.assertNotIn("_auth_user_id", self.client.session)

    @google_on
    def test_removing_line_leaves_google(self):
        add_google(self.user)
        self.send_password()
        self.assertEqual(list(self.user.sign_in_methods.values_list("provider")), [("google",)])

    def test_a_wrong_password_removes_nothing(self):
        self.assertContains(self.send_password("wrong"), "密碼不正確")
        self.assertTrue(self.user.sign_in_methods.exists())

    def test_a_post_from_another_site_is_refused(self):
        # The same session, posting the right password without this site's CSRF token.
        response = self.client.post(CONFIRM_REMOVE, {"password": PASSWORD})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.user.sign_in_methods.exists())

    def test_opening_the_page_removes_nothing_even_after_confirming(self):
        confirm_with_password(self, CONFIRM_ADD, csrf=True)
        self.assertContains(self.client.get(CONFIRM_REMOVE), "請輸入 wang_ming 的密碼")
        self.assertTrue(self.user.sign_in_methods.exists())

    # 18
    def test_the_only_way_in_cannot_be_removed_even_when_sent_directly(self):
        user = line_only_user(username="lin_mei", sub="line-only")
        self.client.force_login(user)
        self.assertEqual(self.client.get(CONFIRM_REMOVE).status_code, 403)
        self.assertEqual(self.send_password_status(), 403)
        self.assertTrue(user.sign_in_methods.exists())

    def test_only_this_accounts_line(self):
        other = line_only_user(username="lin_mei", sub="line-other")
        SignInMethod.objects.filter(user=self.user).delete()
        self.assertEqual(self.client.get(CONFIRM_REMOVE).status_code, 404)
        self.assertEqual(self.send_password_status(), 404)
        self.assertTrue(other.sign_in_methods.exists())

    def test_without_line_keys_is_404(self):
        with self.settings(LINE_CLIENT_ID=""):
            self.assertEqual(self.client.get(CONFIRM_REMOVE).status_code, 404)
            self.assertEqual(self.send_password_status(), 404)
        self.assertTrue(self.user.sign_in_methods.exists())
