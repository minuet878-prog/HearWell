"""Failed sign-ins are counted, so a password cannot be guessed without end: 5 for one username
in 15 minutes, 20 from one address in an hour (the owner's pick, 2026-11-19). The site's login,
the admin's, and the password asked before deleting the account or confirming it is you. Counts
live in the database cache, hashed, like the forgot-password page's (#528)."""

from datetime import timedelta
from unittest import mock

from django.core.cache import caches
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import User
from screening.tests.helpers import consented_user

PASSWORD = "Xk9#mPq2vLw"
TOO_MANY = "試太多次了，請稍後再試"


class SignInLimitTests(TestCase):
    def setUp(self):
        caches["password_reset"].clear()
        self.user = consented_user(username="wang_ming", password=PASSWORD)

    def _login(self, username="wang_ming", password=PASSWORD, remote="127.0.0.1"):
        return self.client.post(
            reverse("login"), {"username": username, "password": password}, REMOTE_ADDR=remote
        )

    def _signed_in(self):
        return "_auth_user_id" in self.client.session

    def test_five_wrong_passwords_then_even_the_right_one_waits(self):
        for _ in range(5):
            response = self._login(password="wrong")
            self.assertContains(response, "使用者名稱或密碼錯誤")
        response = self._login()
        self.assertContains(
            response, f'<div id="login_error" class="error-box" role="alert">{TOO_MANY}</div>'
        )
        self.assertNotContains(response, "使用者名稱或密碼錯誤")
        self.assertFalse(self._signed_in())

    def test_one_username_waiting_leaves_others_alone(self):
        consented_user(username="li_hua", password=PASSWORD)
        for _ in range(5):
            self._login(password="wrong")
        self._login(username="li_hua")
        self.assertTrue(self._signed_in())

    def test_the_username_counts_from_any_address(self):
        for number in range(5):
            self._login(password="wrong", remote=f"203.0.113.{number}")
        self.assertContains(self._login(remote="198.51.100.1"), TOO_MANY)

    def test_twenty_from_one_address_then_every_username_waits(self):
        for number in range(20):
            self._login(username=f"guess{number}", password="wrong")
        self.assertContains(self._login(), TOO_MANY)
        self.assertFalse(self._signed_in())
        # Another address is not held up.
        self._login(remote="198.51.100.1")
        self.assertTrue(self._signed_in())

    def test_signing_in_is_not_counted(self):
        for _ in range(6):
            self._login()
            self.client.logout()
        self._login()
        self.assertTrue(self._signed_in())

    def test_fifteen_minutes_later_the_username_works_again(self):
        for _ in range(5):
            self._login(password="wrong")
        later = timezone.now() + timedelta(minutes=15, seconds=1)
        # The database cache took its own name for now() when it loaded, so that is the one to move.
        with mock.patch("django.core.cache.backends.db.tz_now", return_value=later):
            self._login()
        self.assertTrue(self._signed_in())

    def test_the_admin_login_counts_too(self):
        User.objects.create_superuser(username="site_admin", password=PASSWORD)
        url = reverse("admin:login")
        for _ in range(5):
            self.client.post(url, {"username": "site_admin", "password": "wrong"})
        response = self.client.post(url, {"username": "site_admin", "password": PASSWORD})
        self.assertContains(response, TOO_MANY)
        self.assertFalse(self._signed_in())

    def test_an_hour_later_the_address_works_again(self):
        for number in range(20):
            self._login(username=f"guess{number}", password="wrong")
        later = timezone.now() + timedelta(hours=1, seconds=1)
        with mock.patch("django.core.cache.backends.db.tz_now", return_value=later):
            self._login()
        self.assertTrue(self._signed_in())

    def test_counts_keep_neither_the_username_nor_the_address(self):
        # ADR 0071: hashed, like the forgot-password page's.
        self._login(password="wrong", remote="203.0.113.7")
        with connection.cursor() as cursor:
            cursor.execute("SELECT cache_key, value FROM password_reset_limits")
            rows = cursor.fetchall()
        self.assertEqual(len(rows), 2)
        for row in rows:
            for kept in ("wang_ming", "203.0.113.7"):
                self.assertNotIn(kept, " ".join(row))


class SignInLengthTests(TestCase):
    def test_a_sign_in_still_lasts_14_days(self):
        # The owner kept it (2026-11-19): elders signed in on their own phone stay signed in.
        consented_user(username="wang_ming", password=PASSWORD)
        self.client.post(reverse("login"), {"username": "wang_ming", "password": PASSWORD})
        self.assertEqual(self.client.session.get_expiry_age(), 14 * 24 * 60 * 60)


class PasswordConfirmLimitTests(TestCase):
    """Deleting the account and confirming it is you ask for the password again: the same count
    as the username's sign-ins, so neither page is a way round the other."""

    def setUp(self):
        caches["password_reset"].clear()
        self.user = consented_user(username="wang_ming", password=PASSWORD)
        self.client.force_login(self.user)

    def test_five_wrong_then_the_account_is_not_deleted(self):
        url = reverse("delete_account")
        for _ in range(5):
            self.assertContains(self.client.post(url, {"password": "wrong"}), "密碼不正確")
        response = self.client.post(url, {"password": PASSWORD})
        self.assertContains(response, TOO_MANY)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_confirming_it_is_you_counts_too(self):
        url = f"{reverse('confirm_identity')}?action=add_email"
        for _ in range(5):
            self.assertContains(self.client.post(url, {"password": "wrong"}), "密碼不正確")
        response = self.client.post(url, {"password": PASSWORD})
        self.assertContains(response, TOO_MANY)
        self.assertRedirects(self.client.get(reverse("add_email")), url)

    def test_wrong_passwords_here_hold_up_the_login_too(self):
        for _ in range(5):
            self.client.post(reverse("delete_account"), {"password": "wrong"})
        self.client.logout()
        response = self.client.post(
            reverse("login"), {"username": "wang_ming", "password": PASSWORD}
        )
        self.assertContains(response, TOO_MANY)

    def test_twenty_from_the_address_hold_up_both_pages(self):
        for number in range(20):
            self.client.post(reverse("login"), {"username": f"guess{number}", "password": "wrong"})
        self.client.force_login(self.user)
        for url in (reverse("delete_account"), f"{reverse('confirm_identity')}?action=add_email"):
            with self.subTest(url):
                self.assertContains(self.client.post(url, {"password": PASSWORD}), TOO_MANY)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_wrong_passwords_here_count_for_the_address(self):
        for number in range(15):
            self.client.post(reverse("login"), {"username": f"guess{number}", "password": "wrong"})
        self.client.force_login(self.user)
        for _ in range(5):
            self.client.post(reverse("confirm_identity") + "?action=add_email", {"password": "x"})
        self.client.logout()
        consented_user(username="li_hua", password=PASSWORD)
        response = self.client.post(reverse("login"), {"username": "li_hua", "password": PASSWORD})
        self.assertContains(response, TOO_MANY)
