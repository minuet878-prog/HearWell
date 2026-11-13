"""Saving a guest's result with Google (ticket #513, spec #505 acceptance 35-37, Q13, Q18): the
save card's 「使用 Google 帳戶繼續」, a new account saving straight away, an account there already
asked first, and the monthly 保存 count split by how the saving account was registered."""

import json
import uuid
from datetime import date
from unittest import mock
from urllib.parse import parse_qsl, quote, urlsplit

from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from screening.models import GuestMonth, SignInMethod, Submission, User
from screening.models.sign_in import SignInMethodQuerySet
from screening.tests import test_guest_save
from screening.tests.helpers import GOOGLE_AUTHORIZE, FakeGoogle, consented_user, google_on
from screening.tests.test_line_in_app_browser import LINE_ANDROID, LINE_IOS, SAFARI

GOOGLE_CONTINUE = "使用 Google 帳戶繼續"
SAVE_FROM_CARD = test_guest_save.SAVE_FROM_CARD
SCORES = [4, 4, 2, 0, 0, 0, 4, 0, 0, 2]  # 16, 輕度到中度影響


class GoogleSaveTestCase(test_guest_save.GuestSaveTestCase):
    def setUp(self):
        # The guest scoring's rate limit counts in the cache; each test starts with none counted.
        cache.clear()
        self.addCleanup(cache.clear)
        self.google = FakeGoogle(self.client)

    def from_the_card(self, sub="google-saver", email="saver@example.com"):
        """The save card's Google button, then back from Google."""
        response = self.client.get(reverse("google_save_card"))
        location = urlsplit(response["Location"])
        self.assertEqual(f"{location.scheme}://{location.netloc}{location.path}", GOOGLE_AUTHORIZE)
        self.google.authorize = dict(parse_qsl(location.query))
        return self.google.come_back(sub=sub, email=email)

    def guest_total(self):
        response = self.client.post(
            test_guest_save.GUEST_SCORE,
            json.dumps(self.body(self.hhie_s, SCORES, just_finished=True)),
            content_type="application/json",
        )
        return response.json()["scores"]["total"]

    def save_guest_result(self):
        # What guest-save.js sends for the guest result kept in the browser.
        return self.save(self.body(self.hhie_s, SCORES, from_guest=True), uuid.uuid4())


@google_on
class SaveCardButtonTests(GoogleSaveTestCase):
    """The #507 mockup 7 (W1): 「使用 Google 帳戶繼續」 under 註冊保存, above 登入保存."""

    def card(self, agent=SAFARI):
        response = self.client.post(
            test_guest_save.GUEST_SCORE,
            json.dumps(self.body(self.hhie_s, [0] * 10, just_finished=False)),
            content_type="application/json",
            headers={"user-agent": agent},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["html"]

    def test_between_register_and_log_in_it_starts_a_save_card_trip(self):
        html = self.card()
        self.assertIn(f'href="{reverse("google_save_card")}"', html)
        self.assertIn(f"<span>{GOOGLE_CONTINUE}</span>", html)
        google = html.index(GOOGLE_CONTINUE)
        self.assertLess(html.index("註冊保存</a>"), google)
        self.assertLess(google, html.index("登入保存</a>"))

    def test_not_inside_line_where_google_is_blocked(self):
        # Nor the 用 Safari／Chrome 打開 box: the guest result would not go along (the #507
        # mockup 7 shows none; W3 says so).
        for agent in (LINE_IOS, LINE_ANDROID):
            with self.subTest(agent=agent[-20:]):
                html = self.card(agent)
                self.assertNotIn("Google", html)
                self.assertNotIn("openExternalBrowser", html)
                self.assertIn("註冊保存</a>", html)
                self.assertIn("登入保存</a>", html)

    @override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
    def test_not_without_the_google_keys(self):
        self.assertNotIn("Google", self.card())
        self.assertEqual(self.client.get(reverse("google_save_card")).status_code, 404)


@google_on
class NewAccountTests(GoogleSaveTestCase):
    """#505 acceptance 35 (Q18): the first time with Google, a name and the consent, then saved
    without being asked, with the guest result page's score."""

    def test_name_then_consent_then_saved_without_asking(self):
        total = self.guest_total()
        self.assertRedirects(self.from_the_card(), reverse("google_name"))
        response = self.client.post(reverse("google_name"), {"username": "存檔阿嬤"})
        consent = f"{reverse('consent')}?next={quote(SAVE_FROM_CARD, safe='')}"
        self.assertRedirects(response, consent, fetch_redirect_response=False)
        response = self.client.post(consent, {"agree": "", "next": SAVE_FROM_CARD})
        self.assertRedirects(response, SAVE_FROM_CARD, fetch_redirect_response=False)
        page = self.client.get(SAVE_FROM_CARD)
        self.assertContains(page, '<h1 class="h3 mt-4">保存這次結果</h1>')
        self.assertNotContains(page, "data-asking")
        self.assertEqual(self.save_guest_result().status_code, 201)
        user = User.objects.get(username="存檔阿嬤")
        self.assertTrue(SignInMethod.objects.filter(user=user, used_to_register=True).exists())
        self.assertEqual(Submission.objects.get(user=user).result.total, total)


@google_on
class AccountThereAlreadyTests(GoogleSaveTestCase):
    """#505 acceptance 36 (Q18): a Google already on an account signs in to it, and the save page
    first asks whether to keep the result there, naming the account; nothing saved until 要."""

    def setUp(self):
        super().setUp()
        self.account = consented_user(username="阿明的帳號")
        SignInMethod.objects.create(
            user=self.account, provider="google", subject="google-ming", used_to_register=True
        )

    def test_signed_in_then_asked_naming_the_account(self):
        response = self.from_the_card(sub="google-ming", email="ming@example.com")
        self.assertRedirects(response, reverse("guest_save"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.account.pk)
        page = self.client.get(reverse("guest_save"))
        self.assertContains(page, test_guest_save.ASK_TITLE)
        self.assertContains(page, "data-asking")
        self.assertContains(page, f"data-guest-ask-yes>{test_guest_save.YES}</button>")
        self.assertContains(page, f"data-guest-ask-no>{test_guest_save.NO}</button>")
        # The #493 mockup's question screen names the account in the header, above the question.
        self.assertContains(page, "目前登入：<strong>阿明的帳號</strong>")
        self.assertFalse(Submission.objects.exists())

    def test_not_agreed_to_the_latest_notice_the_consent_comes_before_the_question(self):
        self.account.consents.all().delete()
        self.from_the_card(sub="google-ming", email="ming@example.com")
        save = reverse("guest_save")
        consent = f"{reverse('consent')}?next={quote(save, safe='')}"
        self.assertRedirects(self.client.get(save), consent, fetch_redirect_response=False)
        self.client.post(consent, {"agree": "", "next": save})
        self.assertContains(self.client.get(save), test_guest_save.ASK_TITLE)
        self.assertFalse(Submission.objects.exists())

    def test_one_look_decides_both_the_account_and_whether_to_ask(self):
        # Codex review Spec 1: another session adds this Google to 阿明的帳號 while the callback
        # runs. Whatever the callback saw when it looked, it never signs into that account with
        # the save-straight-away way a brand-new account gets.
        real = SignInMethodQuerySet.for_identity
        looks = []

        def bound_meanwhile(queryset, identity):
            looks.append(identity)
            if len(looks) == 2:
                SignInMethod.objects.filter(user=self.account).update(subject="google-race")
            return real(queryset, identity)

        with mock.patch.object(SignInMethodQuerySet, "for_identity", bound_meanwhile):
            response = self.from_the_card(sub="google-race", email="ming@example.com")
        self.assertRedirects(response, reverse("google_name"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_an_admin_account_is_turned_away_as_from_the_login_page(self):
        self.account.is_staff = True
        self.account.save()
        response = self.from_the_card(sub="google-ming", email="ming@example.com")
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


@google_on
class SameEmailTests(GoogleSaveTestCase):
    """A new Google whose email is already an account's goes to the same-email page (ADR 0057);
    「不是我的，建立新帳號」 makes a new account, which saves straight away like any new one."""

    def test_not_mine_new_account_saves_without_asking(self):
        consented_user(username="someone", email="shared@example.com")
        response = self.from_the_card(sub="google-new", email="shared@example.com")
        self.assertRedirects(response, reverse("google_same_email"))
        self.client.post(reverse("google_name"), {"username": "另一個人"})
        consent = f"{reverse('consent')}?next={quote(SAVE_FROM_CARD, safe='')}"
        response = self.client.post(consent, {"agree": "", "next": SAVE_FROM_CARD})
        self.assertRedirects(response, SAVE_FROM_CARD, fetch_redirect_response=False)


@google_on
class NotFinishedTests(GoogleSaveTestCase):
    """Cancelled at Google: as from the login page's button, nobody signed in, nothing saved."""

    def test_cancelled_back_to_the_login_page_with_its_words(self):
        response = self.client.get(reverse("google_save_card"))
        self.google.authorize = dict(parse_qsl(urlsplit(response["Location"]).query))
        response = self.google.come_back(cancelled=True)
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("login")), "沒有完成 Google 登入。")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(User.objects.exists())


def saved_counts():
    """This month's 保存 (帳號密碼, Google, LINE)."""
    return list(GuestMonth.objects.values_list("saved_password", "saved_google", "saved_line"))


@google_on
class SavedCountTests(GoogleSaveTestCase):
    """#505 acceptance 37 (Q13): a newly saved guest result adds one to the 保存 column of how the
    saving account was registered; registered with a password, the password column as before."""

    def test_registered_with_google_from_the_card_adds_to_google(self):
        self.from_the_card()
        self.client.post(reverse("google_name"), {"username": "存檔阿嬤"})
        self.client.post(reverse("consent"), {"agree": ""})
        self.assertEqual(self.save_guest_result().status_code, 201)
        self.assertEqual(saved_counts(), [(0, 1, 0)])

    def test_registered_with_a_password_adds_to_password(self):
        self.register_from_card()
        self.client.post(reverse("consent"), {"agree": ""})
        self.assertEqual(self.save_guest_result().status_code, 201)
        self.assertEqual(saved_counts(), [(1, 0, 0)])

    def test_google_added_later_still_counts_as_a_password_account(self):
        # Its Google sign-in was added in account settings, not used to register (#511).
        user = consented_user(username="password_first")
        SignInMethod.objects.create(
            user=user, provider="google", subject="google-later", used_to_register=False
        )
        self.client.force_login(user)
        self.save_guest_result()
        self.assertEqual(saved_counts(), [(1, 0, 0)])

    def test_an_account_there_already_saving_after_the_question(self):
        user = consented_user(username="google_first")
        SignInMethod.objects.create(
            user=user, provider="google", subject="google-first", used_to_register=True
        )
        self.from_the_card(sub="google-first", email="first@example.com")
        self.save_guest_result()  # 要，存進這個帳號
        self.assertEqual(saved_counts(), [(0, 1, 0)])


class SavedColumnsMigrationTests(TransactionTestCase):
    """Migration 0034: the months counted before keep their 保存, in the password column (every
    account then had registered with a password); the Google and LINE columns start at 0."""

    before = (("screening", "0033_signinmethod"),)
    after = (("screening", "0034_guestmonth_saved_by_registration"),)

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(list(targets))
        return executor.loader.project_state(list(targets)).apps.get_model(
            "screening", "GuestMonth"
        )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_each_months_saves_become_the_password_columns(self):
        old = self.migrate(self.before)
        old.objects.create(month=date(2026, 10, 1), completed=31, saved=9)
        old.objects.create(month=date(2026, 11, 1), completed=12, saved=4)
        new = self.migrate(self.after)
        self.assertEqual(
            list(
                new.objects.order_by("month").values_list(
                    "month", "completed", "saved_password", "saved_google", "saved_line"
                )
            ),
            [(date(2026, 10, 1), 31, 9, 0, 0), (date(2026, 11, 1), 12, 4, 0, 0)],
        )
