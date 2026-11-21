"""#660 (spec #656 acceptance 7-11, the #657 mockup's 二): an account without an email adds one
itself, once, after 確認本人; one with an email cannot change it here and writes to us as before."""

from urllib.parse import urlsplit

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from screening.models import RetestReminder, User
from screening.tests import (
    test_confirm_identity,
    test_email_confirmation,
    test_layout,
    test_line_confirm_identity,
    test_line_sign_in_methods,
)
from screening.tests.helpers import consented_user, google_on, line_on

later = test_confirm_identity.later

PASSWORD = "Xk9#mPq2vLw"
ADD_EMAIL = reverse("add_email")
CONFIRM_ADD_EMAIL = f"{reverse('confirm_identity')}?action=add_email"


class AddEmailEntryTests(TestCase):
    """Acceptance 7: the way in, and 確認本人 before the email field."""

    def setUp(self):
        self.user = consented_user(username="wang_baba", password=PASSWORD)
        self.client.force_login(self.user)

    def test_the_email_row_and_the_reminder_both_lead_to_adding_one(self):
        page = self.client.get(reverse("account_settings")).content.decode()
        account = page[page.index("我的帳號") : page.index('<section id="retest-reminder"')]
        start = page.index('<section id="retest-reminder"')
        reminder = page[start : page.index("</section>", start)]
        self.assertIn(f'href="{ADD_EMAIL}"', account)
        self.assertIn("補上", test_layout._text(account))
        self.assertIn(f'href="{ADD_EMAIL}"', reminder)

    def test_not_confirmed_yet_goes_to_confirm_it_is_them_first(self):
        response = self.client.get(ADD_EMAIL)
        self.assertRedirects(response, CONFIRM_ADD_EMAIL)
        page = self.client.get(CONFIRM_ADD_EMAIL)
        self.assertContains(page, "接下來要<strong>補上 email</strong>。請輸入 wang_baba 的密碼。")
        self.assertNotContains(page, 'name="email"')

    def test_the_right_password_shows_the_email_field(self):
        response = self.client.post(CONFIRM_ADD_EMAIL, {"password": PASSWORD}, follow=True)
        self.assertRedirects(response, ADD_EMAIL)
        self.assertContains(response, '<h1 class="bird-title">補上 email</h1>', html=True)
        self.assertContains(response, 'name="email"')

    def test_a_wrong_password_shows_no_email_field(self):
        self.client.post(CONFIRM_ADD_EMAIL, {"password": "wrong"})
        self.assertRedirects(self.client.get(ADD_EMAIL), CONFIRM_ADD_EMAIL)


@google_on
@line_on
class AddEmailWithoutPasswordTests(TestCase):
    """Acceptance 7: without a password, 確認本人 with a provider on the account."""

    def test_google_confirms_then_the_email_field(self):
        user = test_confirm_identity.google_only_user()
        user.email = ""
        user.save()
        self.client.force_login(user)
        test_confirm_identity.confirm_with_google(self, action="add_email")
        response = self.client.get(CONFIRM_ADD_EMAIL, follow=True)
        self.assertRedirects(response, ADD_EMAIL)
        self.assertContains(response, 'name="email"')

    def test_line_confirms_then_the_email_field(self):
        self.client.force_login(test_line_sign_in_methods.line_only_user())
        test_line_confirm_identity.confirm_with_line(self, action="add_email")
        response = self.client.get(CONFIRM_ADD_EMAIL, follow=True)
        self.assertRedirects(response, ADD_EMAIL)
        self.assertContains(response, 'name="email"')

    def test_a_line_never_seen_shows_no_email_field(self):
        self.client.force_login(test_line_sign_in_methods.line_only_user())
        test_line_confirm_identity.confirm_with_line(self, sub="line-other", action="add_email")
        self.assertRedirects(self.client.get(ADD_EMAIL), CONFIRM_ADD_EMAIL)


class ConfirmedTests(TestCase):
    """Acceptance 8-10, once confirmed with the password."""

    def setUp(self):
        self.user = consented_user(username="wang_baba", password=PASSWORD)
        self.client.force_login(self.user)
        self.client.post(CONFIRM_ADD_EMAIL, {"password": PASSWORD})

    def email(self):
        return User.objects.get(pk=self.user.pk).email

    # 8, with its 確認信 answered first (security check 2026-11-19, the owner's pick)
    def test_a_good_email_is_saved_and_the_reminder_waits_for_its_confirmation(self):
        response = self.client.post(ADD_EMAIL, {"email": "wang.daughter@example.com"})
        self.assertRedirects(response, reverse("account_settings"))
        self.assertEqual(self.email(), "wang.daughter@example.com")
        page = self.client.get(reverse("account_settings"))
        self.assertContains(page, "wang.daughter@example.com")
        self.assertNotContains(page, "打開提醒")
        self.assertNotContains(page, f'href="{ADD_EMAIL}"')
        self.client.post(reverse("retest_reminder"), {"enabled": "1"})
        self.assertFalse(RetestReminder.objects.filter(user=self.user, enabled=True).exists())
        self.client.post(urlsplit(test_email_confirmation.confirmation_link(mail.outbox[-1])).path)
        self.assertContains(self.client.get(reverse("account_settings")), "打開提醒")
        self.client.post(reverse("retest_reminder"), {"enabled": "1"})
        self.assertTrue(RetestReminder.objects.get(user=self.user).enabled)

    # 9
    def test_a_malformed_email_is_not_saved_and_stays_in_the_box(self):
        registering = self.client.post(reverse("register"), {"email": "wang.daughter@gmail"})
        response = self.client.post(ADD_EMAIL, {"email": "wang.daughter@gmail"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors["email"],
            registering.context["form"].errors["email"],
        )
        self.assertContains(response, 'value="wang.daughter@gmail"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertEqual(self.email(), "")

    def test_after_a_mistyped_one_the_next_try_is_saved(self):
        self.client.post(ADD_EMAIL, {"email": "wang.daughter@gmail"})
        self.client.post(ADD_EMAIL, {"email": "wang.daughter@gmail.com"})
        self.assertEqual(self.email(), "wang.daughter@gmail.com")

    # 10
    def test_after_5_minutes_nothing_is_saved_and_it_asks_again(self):
        with later(5 * 60 + 1):
            response = self.client.post(ADD_EMAIL, {"email": "wang.daughter@gmail.com"})
            self.assertRedirects(response, CONFIRM_ADD_EMAIL, fetch_redirect_response=False)
            page = self.client.get(CONFIRM_ADD_EMAIL)
        self.assertEqual(self.email(), "")
        self.assertContains(page, "確認已經過期，請再確認一次。")  # W18

    def test_within_5_minutes_it_is_saved(self):
        with later(5 * 60 - 1):
            self.client.post(ADD_EMAIL, {"email": "wang.daughter@gmail.com"})
        self.assertEqual(self.email(), "wang.daughter@gmail.com")

    def test_a_confirmation_adds_one_email_only(self):
        self.client.post(ADD_EMAIL, {"email": "wang.daughter@gmail.com"})
        # Blank again (say we cleared it on request): the used confirmation adds no other.
        User.objects.filter(pk=self.user.pk).update(email="")
        response = self.client.post(ADD_EMAIL, {"email": "someone.else@gmail.com"})
        self.assertRedirects(response, CONFIRM_ADD_EMAIL)
        self.assertEqual(self.email(), "")

    def test_a_confirmation_for_another_action_adds_nothing(self):
        self.client.post(
            f"{reverse('confirm_identity')}?action=delete_account", {"password": PASSWORD}
        )
        response = self.client.post(ADD_EMAIL, {"email": "wang.daughter@gmail.com"})
        self.assertRedirects(response, CONFIRM_ADD_EMAIL)
        self.assertEqual(self.email(), "")


class AlreadyHasEmailTests(TestCase):
    """Acceptance 11: with an email, the address changes nothing; writing to us, as before."""

    NOTE = "要修改請寫信到 hearwellweb@gmail.com"

    def setUp(self):
        self.user = consented_user(username="wang_ma", password=PASSWORD, email="ma@example.com")
        self.client.force_login(self.user)

    def test_opening_the_address_goes_back_to_account_settings(self):
        self.assertRedirects(self.client.get(ADD_EMAIL), reverse("account_settings"))

    def test_even_confirmed_the_email_stays_as_it_was(self):
        self.client.post(CONFIRM_ADD_EMAIL, {"password": PASSWORD})
        response = self.client.post(ADD_EMAIL, {"email": "someone.else@example.com"})
        self.assertRedirects(response, reverse("account_settings"))
        self.assertEqual(User.objects.get(pk=self.user.pk).email, "ma@example.com")

    def test_account_settings_has_no_way_to_add_one_and_still_says_to_write(self):
        self.user.birth_year = None
        self.user.save()
        page = self.client.get(reverse("account_settings"))
        self.assertNotContains(page, f'href="{ADD_EMAIL}"')
        self.assertIn(self.NOTE, test_layout._text(page.content.decode()))

    def test_with_both_filled_in_it_does_not_say_to_write(self):
        # 照舊 is #361 as it was (the owner's call on the cross review, Codex 6): said only
        # while a detail is blank, not to change one filled in.
        self.user.birth_year = 1950
        self.user.save()
        page = self.client.get(reverse("account_settings"))
        self.assertNotContains(page, f'href="{ADD_EMAIL}"')
        self.assertNotIn("要修改請寫信", test_layout._text(page.content.decode()))
