"""#748 (spec #741 acceptance 35-39, story 51; ADR 0079): the site header and the tab bar."""

import re

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from screening.tests.helpers import consented_user, read_site_css


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

    def test_header_has_no_signed_in_line_or_wave(self):
        content = self.client.get(reverse("index")).content.decode()
        self.assertNotIn("目前登入", content)
        self.assertNotIn("site-wave", content)

    # Spec #741, at acceptance (2026-11-21, compare-avatar-menu.html A): tapping the avatar opens
    # a small menu, the name, 帳號設定 and 登出. It is in the page hidden; site-header.js shows
    # the menu button in place of the link, so without JavaScript the avatar stays the link.
    def test_avatar_menu_is_in_the_page_hidden(self):
        top = header(self.client.get(reverse("index")).content.decode())
        self.assertRegex(
            top,
            r'<button class="site-avatar" type="button" aria-label="帳號選單：jason"'
            r' aria-expanded="false" aria-controls="site-account-menu" hidden'
            r" data-site-account-toggle>J</button>",
        )
        menu = re.search(
            r'<div class="site-account-menu" id="site-account-menu" hidden>.*?</div>', top, re.S
        )
        self.assertIsNotNone(menu)
        self.assertRegex(menu.group(0), r'<p class="site-account-name">jason</p>')
        self.assertRegex(
            menu.group(0),
            rf'<a class="site-account-item" href="{reverse("account_settings")}">'
            r"<svg[^>]*>.*?</svg>帳號設定</a>",
        )

    def test_menu_logout_posts_to_logout_with_the_csrf_token(self):
        top = header(self.client.get(reverse("index")).content.decode())
        form = re.search(
            rf'<form id="header-logout-form" action="{reverse("logout")}" method="post">.*?</form>',
            top,
            re.S,
        )
        self.assertIsNotNone(form)
        self.assertIn('name="csrfmiddlewaretoken"', form.group(0))
        self.assertRegex(
            form.group(0),
            r'<button class="site-account-item site-account-logout" type="submit">'
            r"<svg[^>]*>.*?</svg>登出</button>",
        )

    def test_header_keeps_the_name_without_the_bird(self):
        # The owner (2026-11-21, at acceptance): the bird is the dialogue's alone, as the
        # canvas's Pro header, so two birds no longer stack at the top left.
        top = header(self.client.get(reverse("index")).content.decode())
        brand = re.search(r'<p class="site-brand">(.*?)</p>', top, re.S).group(1)
        self.assertNotIn("site-logo", brand)
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
        self.assertNotIn("site-account-menu", top)
        self.assertNotIn("登出", top)


class BackButtonTests(TestCase):
    # Story 51: without JavaScript the back button is a link to the home page; site-header.js
    # turns it into the browser's back. ADR 0079: every page, the home page too.
    BACK = (
        '<a class="site-back" href="/" aria-label="回首頁" data-site-back>'
        '<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/>'
        "</svg></a>"
    )

    # The owner, 2026-11-21: it shows from the start, before 聽伴, on every page but the home page.
    def test_every_page_but_home_has_the_back_link_before_the_name(self):
        user = consented_user(username="backtester")
        pages = [(False, reverse("login")), (False, reverse("learn"))]
        pages += [(True, reverse(name)) for name in ("questionnaire_list", "learn", "my_hearing")]
        for logged_in, url in pages:
            with self.subTest(url=url):
                if logged_in:
                    self.client.force_login(user)
                top = header(self.client.get(url).content.decode())
                self.assertIn(self.BACK, top)
                self.assertLess(top.index("site-back"), top.index("site-brand"))

    def test_home_has_no_back_link(self):
        for logged_in in (False, True):
            if logged_in:
                self.client.force_login(consented_user(username="hometester"))
            with self.subTest(logged_in=logged_in):
                top = header(self.client.get(reverse("index")).content.decode())
                self.assertNotIn("site-back", top)
                self.assertIn('<p class="site-brand">', top)

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

    def test_first_paint_waits_for_the_whole_tab_bar(self):
        # 37, ADR 0028: a slow phone painted before the tab bar was parsed, so the pill did not
        # slide. The wait is for <main>, which comes after the whole tab bar.
        for url in (reverse("index"), reverse("learn")):
            with self.subTest(url=url):
                content = self.client.get(url).content.decode()
                head = content[: content.index("</head>")]
                self.assertIn('<link rel="expect" href="#main-content" blocking="render">', head)
                self.assertLess(
                    content.index('<nav aria-label="主要導覽"'),
                    content.index('<main id="main-content"'),
                )


def hover_rules_outside_hover_media(css):
    """Selectors with :hover that no @media (hover: ...) wraps."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found, stack, prelude = [], [], ""
    for char in css:
        if char == "{":
            selector = prelude.strip()
            wrapped = any(s.startswith("@media") and "hover" in s for s in stack)
            if ":hover" in selector and not wrapped:
                found.append(selector)
            stack.append(selector)
            prelude = ""
        elif char == "}":
            if stack:
                stack.pop()
            prelude = ""
        elif char == ";":
            prelude = ""
        else:
            prelude += char
    return found


class HeaderButtonHoverTests(SimpleTestCase):
    # CODING_STANDARDS 22 (ADR 0006): a hover effect shows only where there is a mouse, so a
    # finger tapping 返回, the avatar or 離開 does not leave it stuck in the hover colour.
    def test_back_avatar_and_leave_hover_only_under_a_hover_media_query(self):
        unwrapped = hover_rules_outside_hover_media(read_site_css())
        for button in (".site-back", ".site-avatar", ".site-leave"):
            with self.subTest(button=button):
                self.assertEqual([s for s in unwrapped if button in s], [])
