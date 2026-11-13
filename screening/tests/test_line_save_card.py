"""Saving a guest's result with LINE (ticket #543, spec #506 acceptance 23-25): the save card's
「使用 LINE 帳號繼續」 above Google's, also inside LINE where Google is not; a new account saving
straight away, an account there already asked first, and the monthly 保存 count's LINE column."""

import json
from urllib.parse import quote

from django.test import override_settings
from django.urls import reverse

from screening.models import SignInMethod, Submission, User
from screening.tests import test_google_save_card, test_guest_save
from screening.tests.helpers import FakeLine, consented_user, google_on, line_on
from screening.tests.test_line_in_app_browser import LINE_ANDROID, LINE_IOS, SAFARI

LINE_CONTINUE = "使用 LINE 帳號繼續"
GOOGLE_CONTINUE = test_google_save_card.GOOGLE_CONTINUE
SAVE_FROM_CARD = test_guest_save.SAVE_FROM_CARD
saved_counts = test_google_save_card.saved_counts


class LineSaveTestCase(test_google_save_card.GoogleSaveTestCase):
    def setUp(self):
        super().setUp()
        self.line = FakeLine(self.client)

    def from_the_card(self, sub="line-saver"):
        """The save card's LINE button, then back from LINE."""
        self.line.start("line_save_card")
        return self.line.come_back(sub=sub)


@google_on
@line_on
class SaveCardButtonTests(LineSaveTestCase):
    """The #539 mockup 7 (W1, D2): 「使用 LINE 帳號繼續」 under 註冊保存, above Google's; inside
    LINE, LINE's and no Google."""

    def card(self, agent=SAFARI):
        response = self.client.post(
            test_guest_save.GUEST_SCORE,
            json.dumps(self.body(self.hhie_s, [0] * 10, just_finished=False)),
            content_type="application/json",
            headers={"user-agent": agent},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["html"]

    def test_above_google_it_starts_a_save_card_trip(self):
        html = self.card()
        self.assertIn(f'href="{reverse("line_save_card")}"', html)
        self.assertIn(f"<span>{LINE_CONTINUE}</span>", html)
        line = html.index(LINE_CONTINUE)
        self.assertLess(html.index("註冊保存</a>"), line)
        self.assertLess(line, html.index(GOOGLE_CONTINUE))
        self.assertLess(html.index(GOOGLE_CONTINUE), html.index("登入保存</a>"))

    def test_inside_line_lines_and_no_google(self):
        for agent in (LINE_IOS, LINE_ANDROID):
            with self.subTest(agent=agent[-20:]):
                html = self.card(agent)
                self.assertIn(f'href="{reverse("line_save_card")}"', html)
                self.assertIn(LINE_CONTINUE, html)
                self.assertNotIn("Google", html)
                self.assertNotIn("openExternalBrowser", html)

    @override_settings(LINE_CLIENT_ID="", LINE_CLIENT_SECRET="")
    def test_not_without_the_line_keys(self):
        # #506 acceptance 1: Google's stays.
        html = self.card()
        self.assertNotIn("LINE", html)
        self.assertIn(GOOGLE_CONTINUE, html)
        self.assertEqual(self.client.get(reverse("line_save_card")).status_code, 404)


@line_on
class NewAccountTests(LineSaveTestCase):
    """#506 acceptance 23: inside LINE, the first time with LINE, a name and the consent, then saved
    without being asked, with the guest result page's score. (That the browser's copy is cleared
    is the e2e GuestSaveWithLineTest's.)"""

    def setUp(self):
        super().setUp()
        self.client.defaults["HTTP_USER_AGENT"] = LINE_IOS

    def test_name_then_consent_then_saved_without_asking(self):
        total = self.guest_total()
        self.assertRedirects(self.from_the_card(), reverse("line_name"))
        response = self.client.post(reverse("line_name"), {"username": "存檔阿公"})
        consent = f"{reverse('consent')}?next={quote(SAVE_FROM_CARD, safe='')}"
        self.assertRedirects(response, consent, fetch_redirect_response=False)
        response = self.client.post(consent, {"agree": "", "next": SAVE_FROM_CARD})
        self.assertRedirects(response, SAVE_FROM_CARD, fetch_redirect_response=False)
        page = self.client.get(SAVE_FROM_CARD)
        self.assertContains(page, '<h1 class="h3 mt-4">保存這次結果</h1>')
        self.assertNotContains(page, "data-asking")
        self.assertEqual(self.save_guest_result().status_code, 201)
        user = User.objects.get(username="存檔阿公")
        self.assertTrue(
            SignInMethod.objects.filter(
                user=user, provider="line", subject="line-saver", used_to_register=True
            ).exists()
        )
        self.assertEqual(Submission.objects.get(user=user).result.total, total)


@line_on
class AccountThereAlreadyTests(LineSaveTestCase):
    """#506 acceptance 24: a LINE already on an account signs in to it, and the save page first
    asks whether to keep the result there, naming the account; nothing saved until 要. (Its 「不要」
    clears the browser's copy: the e2e GuestSaveWithLineTest.)"""

    def setUp(self):
        super().setUp()
        self.account = consented_user(username="女兒的帳號")
        SignInMethod.objects.create(
            user=self.account, provider="line", subject="line-daughter", used_to_register=True
        )

    def test_signed_in_then_asked_naming_the_account(self):
        response = self.from_the_card(sub="line-daughter")
        self.assertRedirects(response, reverse("guest_save"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.account.pk)
        page = self.client.get(reverse("guest_save"))
        self.assertContains(page, test_guest_save.ASK_TITLE)
        self.assertContains(page, "data-asking")
        self.assertContains(page, f"data-guest-ask-yes>{test_guest_save.YES}</button>")
        self.assertContains(page, f"data-guest-ask-no>{test_guest_save.NO}</button>")
        self.assertContains(page, "目前登入：<strong>女兒的帳號</strong>")
        self.assertFalse(Submission.objects.exists())
        self.assertEqual(User.objects.count(), 1)

    def test_an_admin_account_is_turned_away_as_from_the_login_page(self):
        self.account.is_staff = True
        self.account.save()
        response = self.from_the_card(sub="line-daughter")
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


@line_on
class NotFinishedTests(LineSaveTestCase):
    """Cancelled at LINE: as from the login page's button, nobody signed in, nothing saved."""

    def test_cancelled_back_to_the_login_page_with_its_words(self):
        self.line.start("line_save_card")
        response = self.line.come_back(cancelled=True)
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertContains(
            self.client.get(reverse("login")),
            "沒有完成 LINE 登入，可以再試一次，或用其他方式登入。",
        )
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(User.objects.exists())


@line_on
class SavedCountTests(LineSaveTestCase):
    """#506 acceptance 25: a guest result saved by an account registered with LINE adds one to the
    保存 count's LINE column."""

    def test_registered_with_line_from_the_card_adds_to_line(self):
        self.from_the_card()
        self.client.post(reverse("line_name"), {"username": "存檔阿公"})
        self.client.post(reverse("consent"), {"agree": ""})
        self.assertEqual(self.save_guest_result().status_code, 201)
        self.assertEqual(saved_counts(), [(0, 0, 1)])

    def test_an_account_there_already_saving_after_the_question(self):
        user = consented_user(username="line_first")
        SignInMethod.objects.create(
            user=user, provider="line", subject="line-first", used_to_register=True
        )
        self.from_the_card(sub="line-first")
        self.save_guest_result()  # 要，存進這個帳號
        self.assertEqual(saved_counts(), [(0, 0, 1)])

    def test_line_added_later_still_counts_as_a_password_account(self):
        user = consented_user(username="password_first")
        SignInMethod.objects.create(
            user=user, provider="line", subject="line-later", used_to_register=False
        )
        self.client.force_login(user)
        self.save_guest_result()
        self.assertEqual(saved_counts(), [(1, 0, 0)])
