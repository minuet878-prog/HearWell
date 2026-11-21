"""#748 (spec #741 acceptance 35-39, story 51; ADR 0079): the site header and the tab bar."""

import re

from django.test import TestCase
from django.urls import reverse

from screening.tests.helpers import consented_user


def header(content):
    return content[content.index("<header") : content.index("</header>")]


class SignedInHeaderTests(TestCase):
    # 35
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="jason")

    def setUp(self):
        self.client.force_login(self.user)

    def test_avatar_shows_the_first_letter_and_reads_as_account_settings(self):
        for url in (reverse("index"), reverse("questionnaire_list"), reverse("learn")):
            with self.subTest(url=url):
                top = header(self.client.get(url).content.decode())
                self.assertRegex(
                    top,
                    rf'<a class="site-avatar" href="{reverse("account_settings")}"'
                    r' aria-label="帳號設定：jason">J</a>',
                )

    def test_header_has_no_signed_in_line_logout_or_wave(self):
        content = self.client.get(reverse("index")).content.decode()
        top = header(content)
        self.assertNotIn("目前登入", content)
        self.assertNotIn("登出", top)
        self.assertNotIn("site-wave", content)

    def test_header_keeps_the_bird_and_the_name(self):
        top = header(self.client.get(reverse("index")).content.decode())
        brand = re.search(r'<p class="site-brand">(.*?)</p>', top, re.S).group(1)
        self.assertIn('<span class="site-logo" aria-hidden="true"></span>', brand)
        self.assertEqual(re.sub(r"<[^>]+>|\s", "", brand), "聽伴")

    def test_logout_is_the_last_thing_on_account_settings(self):
        content = self.client.get(reverse("account_settings")).content.decode()
        main = content[content.index("<main") : content.index("</main>")]
        form = re.search(
            rf'<form id="logout-form" action="{reverse("logout")}" method="post">.*?</form>',
            main,
            re.S,
        )
        self.assertIsNotNone(form)
        self.assertIn(">登出</button>", form.group(0))
        self.assertEqual(main[form.end() :].strip(), "")


class SignedOutHeaderTests(TestCase):
    # 36
    def test_home_has_a_login_outline_button(self):
        top = header(self.client.get(reverse("index")).content.decode())
        self.assertRegex(
            top,
            rf'<a class="btn btn-outline-primary site-login" href="{reverse("login")}">登入</a>',
        )
        self.assertNotIn("site-avatar", top)


class BackButtonTests(TestCase):
    # Story 51: without JavaScript the back button is a link to the home page; site-header.js
    # turns it into the browser's back. ADR 0079: every page, the home page too.
    BACK = (
        '<a class="site-back" href="/" aria-label="回首頁" data-site-back>'
        '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/>'
        "</svg></a>"
    )

    def test_every_page_has_the_back_link_in_the_header(self):
        user = consented_user(username="backtester")
        pages = [(False, reverse("index")), (False, reverse("login"))]
        pages += [(True, reverse(name)) for name in ("index", "questionnaire_list", "learn")]
        for logged_in, url in pages:
            with self.subTest(url=url):
                if logged_in:
                    self.client.force_login(user)
                top = header(self.client.get(url).content.decode())
                self.assertIn(self.BACK, top)

    # The home-screen app's own 上一頁 is merged into this one.
    def test_the_old_home_screen_app_button_is_gone(self):
        self.assertNotIn("pwa-back", self.client.get(reverse("login")).content.decode())


class TabBarTests(TestCase):
    # 37: four tabs, signed in or not; the second is 問卷 (spec #741 P1).
    NAV = re.compile(r'<nav aria-label="主要導覽".*?</nav>', re.S)

    def labels(self, url):
        nav = self.NAV.search(self.client.get(url).content.decode()).group(0)
        return re.findall(r"<span>([^<]+)</span>\s*</a>", nav)

    def test_four_tabs_signed_in_or_not(self):
        for logged_in in (False, True):
            if logged_in:
                self.client.force_login(consented_user(username="tabtester"))
            with self.subTest(logged_in=logged_in):
                self.assertEqual(self.labels(reverse("index")), ["首頁", "問卷", "紀錄", "了解"])

    def test_signed_out_records_tab_leads_to_login_and_is_current_there(self):
        nav = self.NAV.search(self.client.get(reverse("login")).content.decode()).group(0)
        self.assertRegex(nav, rf'<a href="{reverse("my_hearing")}" aria-current="page">')
