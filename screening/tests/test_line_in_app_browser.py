"""#505 acceptance 3 (ticket #512, the #507 mockup W3): inside LINE's in-app browser Google would
be blocked, so the login and register pages offer to open the page in Safari or Chrome instead."""

import html
import re

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from screening.tests.helpers import google_on
from screening.views.common import is_line_in_app_browser

# Real strings (see is_line_in_app_browser): LINE for iOS and LINE for Android.
LINE_IOS = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 Safari Line/15.12.1"
)
LINE_ANDROID = (
    "Mozilla/5.0 (Linux; Android 5.0; ASUS_Z00AD Build/LRX21V; wv) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/51.0.2704.81 Mobile Safari/537.36 Line/6.5.1/IAB"
)
SAFARI = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.6 Mobile/15E148 Safari/604.1"
)
GOOGLE_BUTTON = "使用 Google 帳戶"
PAGES = ("login", "register")
OPEN_OUTSIDE = "用 Safari／Chrome 打開"


def open_outside_href(response):
    """The href of the 「用 Safari／Chrome 打開」 link; fails when there is not exactly one."""
    links = re.findall(
        rf'<a [^>]*href="([^"]*)"[^>]*>(?:(?!</a>).)*{OPEN_OUTSIDE}',
        response.content.decode(),
        re.S,
    )
    assert len(links) == 1, links
    return html.unescape(links[0])


@google_on
class InsideLineTests(TestCase):
    def test_no_google_button_on_the_login_and_register_pages(self):
        for agent in (LINE_IOS, LINE_ANDROID):
            for name in PAGES:
                with self.subTest(agent=agent[-20:], page=name):
                    response = self.client.get(reverse(name), headers={"user-agent": agent})
                    self.assertEqual(response.status_code, 200)
                    self.assertNotContains(response, GOOGLE_BUTTON)

    def test_offers_the_same_page_in_safari_or_chrome_keeping_its_query(self):
        for name in PAGES:
            with self.subTest(page=name):
                url = reverse(name) + "?next=/questionnaire_list"
                response = self.client.get(url, headers={"user-agent": LINE_IOS})
                self.assertEqual(
                    open_outside_href(response),
                    reverse(name) + "?next=%2Fquestionnaire_list&openExternalBrowser=1",
                )

    def test_a_page_without_a_query_gets_only_the_parameter(self):
        response = self.client.get(reverse("login"), headers={"user-agent": LINE_ANDROID})
        self.assertEqual(open_outside_href(response), reverse("login") + "?openExternalBrowser=1")

    def test_says_why_and_that_the_guest_result_stays_in_line(self):
        for name in PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name), headers={"user-agent": LINE_IOS})
                self.assertContains(response, "LINE 裡面不能用 Google 登入")
                self.assertContains(response, "在 LINE 裡做的篩檢結果不會跟著過去。")

    def test_the_password_form_stays(self):
        for name in PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name), headers={"user-agent": LINE_IOS})
                self.assertContains(response, f'action="{reverse(name)}"')


@google_on
class OtherBrowsersTests(TestCase):
    def test_safari_and_a_missing_user_agent_get_the_google_button_and_no_way_out(self):
        for agent in (SAFARI, ""):
            for name in PAGES:
                with self.subTest(agent=agent[-20:], page=name):
                    response = self.client.get(reverse(name), headers={"user-agent": agent})
                    self.assertContains(response, GOOGLE_BUTTON)
                    self.assertNotContains(response, OPEN_OUTSIDE)


@override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
class WithoutGoogleTests(TestCase):
    def test_inside_line_nothing_is_said_about_google(self):
        # No Google on the site (#505 acceptance 1): nothing to send the visitor away for.
        for name in PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name), headers={"user-agent": LINE_IOS})
                self.assertNotContains(response, OPEN_OUTSIDE)
                self.assertNotContains(response, "Google")


class IsLineInAppBrowserTests(SimpleTestCase):
    """The one check the save card (#513) and LINE sign-in (#506) use too."""

    def check(self, agent):
        return is_line_in_app_browser(RequestFactory().get("/", headers={"user-agent": agent}))

    def test_line_for_ios_and_android_and_its_liff_browser(self):
        for agent in (LINE_IOS, LINE_ANDROID, LINE_IOS + " LIFF"):
            with self.subTest(agent=agent[-20:]):
                self.assertTrue(self.check(agent))

    def test_other_browsers_and_no_user_agent(self):
        chrome = (
            "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Mobile Safari/537.36"
        )
        for agent in (SAFARI, chrome, ""):
            with self.subTest(agent=agent[-20:]):
                self.assertFalse(self.check(agent))
        self.assertFalse(is_line_in_app_browser(RequestFactory().get("/")))
