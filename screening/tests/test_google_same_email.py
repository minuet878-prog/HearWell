import html
import re

from django.test import TestCase, override_settings
from django.urls import reverse

from screening.models import SignInMethod, User
from screening.tests.helpers import FakeGoogle, google_on

PASSWORD = "Xk9#mPq2vLw"


@google_on
class SameEmailTests(TestCase):
    """#505 acceptance 12-14 (ADR 0057): a Google email already on an account never signs into it
    nor merges with it."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="王小明", password=PASSWORD, email="a@example.com"
        )
        self.google = FakeGoogle(self.client)

    def _back_from_google(self, email="a@example.com"):
        self.google.start()
        return self.google.come_back(sub="google-new", email=email)

    # 12
    def test_the_same_email_goes_to_its_own_page_and_signs_nobody_in(self):
        response = self._back_from_google()
        self.assertRedirects(response, reverse("google_same_email"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(SignInMethod.objects.exists())
        self.assertEqual(User.objects.count(), 1)

    def test_the_email_matches_whatever_its_case(self):
        response = self._back_from_google(email="A@Example.COM")
        self.assertRedirects(response, reverse("google_same_email"))
        self.assertFalse(SignInMethod.objects.exists())

    # 12, the #507 mockup W11
    def test_the_page_says_so_with_the_password_way_first(self):
        self._back_from_google()
        page = self.client.get(reverse("google_same_email"))
        content = page.content.decode()
        self.assertContains(page, "<h1", count=1)
        self.assertContains(page, "這個 email 已經有帳號</h1>")
        self.assertContains(page, "a@example.com 已經用在一個聽伴帳號。")
        self.assertContains(
            page,
            "如果那是您的帳號，請先用帳號密碼登入，再到帳號設定新增 Google 登入。"
            "這樣您的紀錄都會在同一個帳號裡。",
        )
        self.assertContains(page, "<strong>那不是我的帳號</strong>", html=True)
        self.assertContains(
            page, "可能是有人打錯了 email。您可以用這個 Google 另外建立自己的帳號。"
        )
        password = content.index('class="w-full btn btn-lg btn-primary"')
        self.assertIn("用帳號密碼登入", content[password : content.index("</a>", password)])
        not_mine = content.index(f'<a class="inline-link" href="{reverse("google_name")}">')
        self.assertIn("不是我的，建立新帳號", content[not_mine : content.index("</a>", not_mine)])
        self.assertLess(password, not_mine)
        # The account it is on stays unnamed: anyone could look an email up.
        self.assertNotContains(page, "王小明")
        self.assertIn("no-store", page["Cache-Control"])
        self.assertNotIn("_auth_user_id", self.client.session)

    # 13
    def test_not_mine_makes_a_new_account_with_the_same_email(self):
        self._back_from_google()
        self.client.get(reverse("google_same_email"))
        response = self.client.post(
            reverse("google_name"), {"username": "林阿美", "roc_birth_year": ""}
        )
        self.assertRedirects(response, reverse("consent"))
        new = User.objects.get(username="林阿美")
        self.assertEqual(new.email, "a@example.com")
        self.assertEqual(int(self.client.session["_auth_user_id"]), new.pk)
        self.assertEqual(
            list(SignInMethod.objects.values_list("user", "subject")), [(new.pk, "google-new")]
        )
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, "a@example.com")
        self.assertTrue(self.owner.check_password(PASSWORD))
        self.assertFalse(self.owner.sign_in_methods.exists())

    # 14: #511 makes account settings' 登入方式 section, which this then points at.
    def test_signing_in_with_the_password_goes_back_to_account_settings(self):
        self._back_from_google()
        page = self.client.get(reverse("google_same_email")).content.decode()
        href = html.unescape(re.search(r'<a class="w-full btn[^"]*" href="([^"]+)">', page)[1])
        self.assertTrue(href.startswith(reverse("login") + "?"))
        self.assertEqual(self.client.get(href).status_code, 200)
        response = self.client.post(href, {"username": "王小明", "password": PASSWORD})
        self.assertRedirects(response, reverse("account_settings"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.owner.pk)
        self.assertFalse(self.owner.sign_in_methods.exists())

    def test_without_a_trip_to_google_the_page_sends_back_to_login(self):
        response = self.client.get(reverse("google_same_email"))
        self.assertRedirects(response, reverse("login"))

    # 10: who Google says it is decides, not the email.
    def test_a_known_google_account_signs_into_its_own_account_whatever_its_email(self):
        mine = User.objects.create_user(username="林阿美", email="lin.mei@example.com")
        SignInMethod.objects.create(user=mine, provider="google", subject="google-mine")
        self.google.start()
        self.google.come_back(sub="google-mine", email="a@example.com")
        self.assertEqual(int(self.client.session["_auth_user_id"]), mine.pk)
        self.assertFalse(self.owner.sign_in_methods.exists())


@override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
class WithoutKeysTests(TestCase):
    # 1
    def test_the_same_email_page_is_404(self):
        self.assertEqual(self.client.get(reverse("google_same_email")).status_code, 404)
