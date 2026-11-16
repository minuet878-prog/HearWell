"""Spec #611 N3 (ticket #616): the five forms with several text fields (註冊, 登入, 用 LINE 取名稱,
用 Google 取名稱, 設新密碼) load enter-next.js, which says 下一個 on the phone keyboard and moves
on with Enter. The server sends no enterkeyhint, so without JavaScript Enter sends as before
(acceptance 30); forms with one text field get neither (acceptance 27). What the script does is
tested in frontend/src/enter-next.test.js and e2e.main_flow.EnterNextFieldTest."""

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from screening.tests.helpers import FakeGoogle, FakeLine, consented_user, google_on, line_on
from screening.tests.test_password_reset import _reset_link

SCRIPT = "screening/enter-next.js"
PASSWORD = "Xk9#mPq2vLw"


class EnterNextPage:
    def assert_loads_the_script_only(self, response):
        """Loaded once, and nothing set on the fields as sent (acceptance 30)."""
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(content.count(SCRIPT), 1)
        self.assertNotIn("enterkeyhint", content.lower())

    def assert_left_as_it_was(self, response):
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn(SCRIPT, content)
        self.assertNotIn("enterkeyhint", content.lower())


class PasswordFormsTests(EnterNextPage, TestCase):
    def test_register(self):
        self.assert_loads_the_script_only(self.client.get(reverse("register")))

    def test_register_sent_back(self):
        response = self.client.post(reverse("register"), {"username": "wang"})
        self.assertContains(response, 'id="id_password1_error"')
        self.assert_loads_the_script_only(response)

    def test_login(self):
        self.assert_loads_the_script_only(self.client.get(reverse("login")))

    def test_set_new_password(self):
        user = consented_user(username="wang_ming", email="a@example.com", password=PASSWORD)
        self.client.post(reverse("password_reset"), {"email": user.email})
        response = self.client.get(_reset_link(mail.outbox[-1]), follow=True)
        self.assertContains(response, 'id="id_new_password2"')
        self.assert_loads_the_script_only(response)


@line_on
class LineNameTests(EnterNextPage, TestCase):
    def test_line_name(self):
        line = FakeLine(self.client)
        line.start()
        line.come_back(sub="line-new")
        self.assert_loads_the_script_only(self.client.get(reverse("line_name")))


@google_on
class GoogleNameTests(EnterNextPage, TestCase):
    def test_google_name(self):
        google = FakeGoogle(self.client)
        google.start()
        google.come_back(sub="google-new", email="lin.mei@example.com")
        self.assert_loads_the_script_only(self.client.get(reverse("google_name")))


class OneFieldFormsTests(EnterNextPage, TestCase):
    """Acceptance 27: 忘記密碼, 確認身分, 刪除帳號 and 問答小助手 have one text field each."""

    def test_forgot_password(self):
        self.assert_left_as_it_was(self.client.get(reverse("password_reset")))

    def test_confirm_identity_and_delete_account(self):
        self.client.force_login(consented_user(username="wang", password=PASSWORD))
        for url in (
            f"{reverse('confirm_identity')}?action=delete_account",
            reverse("delete_account"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, 'id="id_password"')
                self.assert_left_as_it_was(response)

    def test_qa_assistant(self):
        response = self.client.get(reverse("qa_home"))
        self.assertContains(response, 'id="id_question"')
        self.assert_left_as_it_was(response)
