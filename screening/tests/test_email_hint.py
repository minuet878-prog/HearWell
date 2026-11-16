"""Spec #611 J2 (ticket #614): the three email fields a person types (註冊, 用 LINE 取名稱 and
忘記密碼) each come with an empty place for the typo question under the field and the script
that asks it; 用 Google 取名稱 has neither (the email is Google's). When to ask and what is
asked is email-hint.js's, tested in frontend/src/email-hint.test.js and
e2e.main_flow.EmailTypoHintTest."""

import re

from django.test import TestCase
from django.urls import reverse

from screening.models import User
from screening.tests.helpers import FakeGoogle, FakeLine, google_on, line_on

SCRIPT = "screening/email-hint.js"
# Sent empty: nothing shows and it takes no room until the script asks; without JavaScript it
# stays so. A status area, so screen readers say the question when it comes.
HINT = '<div id="id_email_hint" class="email-hint" role="status"></div>'
PASSWORD = "Xk9#mPq2vLw"
TYPO = "wang@gmial.com"


class EmailHintPlace:
    def assert_hint_under_the_email_field(self, response):
        content = response.content.decode()
        self.assertIn(SCRIPT, content)
        self.assertEqual(content.count(HINT), 1)
        field = re.search(r'<input[^>]*id="id_email"[^>]*>', content)
        hint = content.index(HINT)
        # Under the field, over its help words and the server's errors.
        self.assertLess(field.end(), hint)
        for below in ('id="id_email_helptext"', 'id="id_email_error"'):
            if below in content:
                self.assertLess(hint, content.index(below), below)
        return field.group()


class RegisterTests(EmailHintPlace, TestCase):
    def _post(self, **overrides):
        data = {
            "username": "wang",
            "email": TYPO,
            "password1": PASSWORD,
            "password2": PASSWORD,
            "roc_birth_year": "",
            **overrides,
        }
        return self.client.post(reverse("register"), data)

    # 1
    def test_the_register_page_has_the_place_and_script(self):
        self.assert_hint_under_the_email_field(self.client.get(reverse("register")))

    # 7: sent back for another field's mistake, the typo is still in the field for the script.
    def test_a_page_sent_back_keeps_the_typo_for_the_question(self):
        response = self._post(password2="Different#123")
        self.assertFalse(User.objects.exists())
        field = self.assert_hint_under_the_email_field(response)
        self.assertIn(f'value="{TYPO}"', field)

    # 5: only asked, never stopped; the server takes what was typed.
    def test_the_server_takes_the_typo_as_typed(self):
        self._post()
        self.assertEqual(User.objects.get().email, TYPO)


@line_on
class LineNameTests(EmailHintPlace, TestCase):
    def setUp(self):
        line = FakeLine(self.client)
        line.start()
        line.come_back(sub="line-new")

    # 1, 8: the optional email gets it too.
    def test_the_line_name_page_has_the_place_and_script(self):
        self.assert_hint_under_the_email_field(self.client.get(reverse("line_name")))

    # 7
    def test_a_page_sent_back_keeps_the_typo_for_the_question(self):
        response = self.client.post(reverse("line_name"), {"username": "", "email": TYPO})
        self.assertFalse(User.objects.exists())
        field = self.assert_hint_under_the_email_field(response)
        self.assertIn(f'value="{TYPO}"', field)


class ForgotPasswordTests(EmailHintPlace, TestCase):
    # 1
    def test_the_forgot_password_page_has_the_place_and_script(self):
        self.assert_hint_under_the_email_field(self.client.get(reverse("password_reset")))

    # 7: the typo is no one's, so the page comes back with it and 沒註冊 under the field.
    def test_a_page_sent_back_keeps_the_typo_for_the_question(self):
        response = self.client.post(reverse("password_reset"), {"email": TYPO})
        field = self.assert_hint_under_the_email_field(response)
        self.assertIn(f'value="{TYPO}"', field)


@google_on
class GoogleNameTests(TestCase):
    # The email there is Google's and cannot be changed.
    def test_the_google_name_page_has_no_question(self):
        google = FakeGoogle(self.client)
        google.start()
        google.come_back(sub="google-new", email="lin.mei@gmial.com")
        content = self.client.get(reverse("google_name")).content.decode()
        self.assertIn("lin.mei@gmial.com", content)
        self.assertNotIn(SCRIPT, content)
        self.assertNotIn("email-hint", content)
