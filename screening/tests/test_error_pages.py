"""#471 (mockup #470 group 8): the site's own 404 and 500 pages in Chinese, not Django's."""

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.views.defaults import server_error

from screening.models import User

NOT_FOUND_TITLE = "找不到這一頁"
NOT_FOUND_TEXT = "網址可能打錯了，或這一頁已經搬家。請回首頁再找一次。"
NOT_FOUND_MAIL = "一直找不到的話，請寫信到"
ERROR_TITLE = "網站出了一點問題"
ERROR_TEXT = (
    "不是您做錯了什麼。我們已經收到錯誤通知，會盡快修好。"
    "您剛剛填的資料可能沒有存起來，請稍後再試一次。"
)
ERROR_MAIL = "一直出現這個畫面的話，請寫信到"
HOME_BUTTON = '<a class="btn btn-primary btn-lg w-full" href="/">回首頁</a>'


@override_settings(DEBUG=False)
class NotFoundPageTests(TestCase):
    def test_a_wrong_address_shows_the_chinese_page(self):
        response = self.client.get("/no-such-page/")

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(response, NOT_FOUND_TITLE, status_code=404)
        self.assertContains(response, NOT_FOUND_TEXT, status_code=404)
        self.assertContains(response, NOT_FOUND_MAIL, status_code=404)
        self.assertContains(response, HOME_BUTTON, html=True, status_code=404)
        self.assertNotContains(response, "Not Found", status_code=404)

    def test_a_page_that_raises_not_found_shows_it_too(self):
        # The monitoring page answers 404 to anyone but a superuser.
        response = self.client.get(reverse("monitoring_test"))

        self.assertContains(response, NOT_FOUND_TITLE, status_code=404)

    def test_the_tab_bar_is_the_signed_in_one_for_a_signed_in_user(self):
        self.client.force_login(User.objects.create_user(username="lost_user"))

        response = self.client.get("/no-such-page/")

        self.assertContains(response, reverse("my_hearing"), status_code=404)
        self.assertNotContains(response, f'href="{reverse("register")}"', status_code=404)


@override_settings(DEBUG=False)
class ServerErrorPageTests(TestCase):
    def test_an_error_in_a_page_shows_the_chinese_page(self):
        admin = User.objects.create_superuser(username="error_admin", password="pw-12345678")
        admin.give_consent()
        self.client.force_login(admin)
        self.client.raise_request_exception = False

        response = self.client.get(reverse("monitoring_test"))

        self.assertEqual(response.status_code, 500)
        self.assertTemplateUsed(response, "500.html")
        content = response.content.decode()
        for text in (ERROR_TITLE, ERROR_TEXT, ERROR_MAIL):
            self.assertIn(text, content)
        self.assertInHTML(HOME_BUTTON, content)
        self.assertNotIn("Server Error", content)


class ServerErrorWithoutDatabaseTests(SimpleTestCase):
    """SimpleTestCase refuses every database query, so the page renders with none."""

    def test_the_page_needs_no_database_and_no_signed_in_user(self):
        request = RequestFactory().get("/")  # no session and no request.user

        response = server_error(request)

        self.assertEqual(response.status_code, 500)
        content = response.content.decode()
        self.assertIn(ERROR_TITLE, content)
        # Without a user the tab bar is the visitor's.
        self.assertIn(f'href="{reverse("register")}"', content)
