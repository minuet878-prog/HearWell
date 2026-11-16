"""Spec #611 J4 (ticket #615): on 註冊, 用 LINE 取名稱 and 用 Google 取名稱, 出生年 carries this
民國 year, has an empty place for 今年滿 76 歲 right under its 民國 ... 年 row and a status area for
the tick's words, and the page loads the script that shows them (register-checks.js, tested in
frontend/src/register-checks.test.js and e2e.main_flow.BirthAgeTest). The age shown is this year
less the birth year, as the account's age (acceptance 20)."""

import re
from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening.models import User
from screening.tests.helpers import FakeGoogle, FakeLine, google_on, line_on

SCRIPT = "screening/register-checks.js"
# Sent empty, so it takes no room until the tick shows; without JavaScript it stays so. Kept
# from screen readers: they hear 「格式正確，今年滿 76 歲」 from the status area instead.
AGE = '<p class="birth-age" id="id_roc_birth_year_age" aria-hidden="true"></p>'
STATUS = '<p class="visually-hidden" role="status"></p>'
PASSWORD = "Xk9#mPq2vLw"


def this_roc_year():
    return date.today().year - 1911


class BirthAgePlace:
    def assert_age_place(self, response):
        """The page's 出生年 field as sent: this year on it, the age's place under its row."""
        content = response.content.decode()
        self.assertIn(SCRIPT, content)
        field = re.search(r'<input[^>]*name="roc_birth_year"[^>]*>', content)
        self.assertIn(f'data-this-year="{this_roc_year()}"', field.group())
        self.assertIn(f'data-max="{this_roc_year() - 18}"', field.group())
        self.assertEqual(content.count(AGE), 1)
        # Right under the 民國 ... 年 row, over the tick's words, its help and the server's errors.
        row_end = content.index('<span class="input-group-text">年</span>', field.end())
        between = content[row_end : content.index(AGE)]
        self.assertRegex(between, r"^<span class=\"input-group-text\">年</span>\s*</div>\s*$")
        status = content.index(STATUS, content.index(AGE))
        for below in ('id="id_roc_birth_year_helptext"', 'id="id_roc_birth_year_error"'):
            if below in content:
                self.assertLess(status, content.index(below), below)
        return field.group()

    def assert_age_matches(self, roc):
        """Acceptance 20: the account's age is the page's this year less the birth year."""
        self.assertEqual(User.objects.get().age, this_roc_year() - roc)


class RegisterTests(BirthAgePlace, TestCase):
    def _post(self, **overrides):
        data = {
            "username": "wang",
            "email": "wang@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "roc_birth_year": "39",
            **overrides,
        }
        return self.client.post(reverse("register"), data)

    # 13
    def test_the_register_page_has_this_year_and_the_age_place(self):
        self.assert_age_place(self.client.get(reverse("register")))

    # 18: sent back for another field's mistake, the right year is still in the field.
    def test_a_page_sent_back_keeps_the_year_for_the_age(self):
        response = self._post(password2="Different#123")
        self.assertFalse(User.objects.exists())
        self.assertIn('value="39"', self.assert_age_place(response))

    # 20
    def test_the_accounts_age_is_the_one_shown(self):
        self._post()
        self.assert_age_matches(39)


@line_on
class LineNameTests(BirthAgePlace, TestCase):
    def setUp(self):
        line = FakeLine(self.client)
        line.start()
        line.come_back(sub="line-new")

    # 14
    def test_the_line_name_page_has_this_year_and_the_age_place(self):
        self.assert_age_place(self.client.get(reverse("line_name")))

    # 18
    def test_a_page_sent_back_keeps_the_year_for_the_age(self):
        response = self.client.post(reverse("line_name"), {"username": "", "roc_birth_year": "39"})
        self.assertFalse(User.objects.exists())
        self.assertIn('value="39"', self.assert_age_place(response))

    # 20
    def test_the_accounts_age_is_the_one_shown(self):
        self.client.post(reverse("line_name"), {"username": "陳阿蘭", "roc_birth_year": "39"})
        self.assert_age_matches(39)


@google_on
class GoogleNameTests(BirthAgePlace, TestCase):
    def setUp(self):
        google = FakeGoogle(self.client)
        google.start()
        google.come_back(sub="google-new", email="lin.mei@example.com")

    # 14
    def test_the_google_name_page_has_this_year_and_the_age_place(self):
        self.assert_age_place(self.client.get(reverse("google_name")))

    # 18
    def test_a_page_sent_back_keeps_the_year_for_the_age(self):
        response = self.client.post(
            reverse("google_name"), {"username": "", "roc_birth_year": "39"}
        )
        self.assertFalse(User.objects.exists())
        self.assertIn('value="39"', self.assert_age_place(response))

    # 20
    def test_the_accounts_age_is_the_one_shown(self):
        self.client.post(reverse("google_name"), {"username": "林阿美", "roc_birth_year": "39"})
        self.assert_age_matches(39)
