"""Spec #148 batch 1, ticket #150: the visitor's home page. A signed-in user's home, the 照顧旅程
or the 空狀態首頁, is test_home_journey's (#459). #471 (mockup #458 ⑪ for a visitor): the visitor
sees the 空狀態首頁 too. #499 (spec #492): its 開始篩檢 opens a guest's wizard, no account first,
and a guest result kept in this browser is drawn on top by guest-home.js."""

import json
import re

from django.test import TestCase
from django.urls import reverse

from screening.questionnaires import hhia_s, hhie_s
from screening.tests.helpers import consented_user, without_nonce


class VisitorHomeTestCase(TestCase):
    def setUp(self):
        self.list_url = reverse("questionnaire_list")
        self.login_url = reverse("login")

    def _main(self):
        content = self.client.get(reverse("index")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _link(self, main, text):
        """The href of the link in the page body whose whole text is `text`."""
        links = re.findall(r'<a[^>]*href="([^"]*)"[^>]*>\s*([^<]*?)\s*</a>', main)
        hrefs = [href for href, label in links if label == text]
        self.assertEqual(len(hrefs), 1, f"{text}: {links}")
        return hrefs[0]


class GuestHomeStartTests(VisitorHomeTestCase):
    """#492 acceptance 1: without a guest result, the way to screening opens the wizard's age
    step instead of the register page. Since spec #655 (#673) that way is a door and the three
    steps are gone (grill Q4); since spec #741 (#752) it is the blue hero card's 開始, and
    我已經有帳號，登入 is gone (grill P15)."""

    def test_start_opens_the_wizards_age_step(self):
        start = re.search(r'href="([^"]+)" data-door="door_self"', self._main()).group(1)
        self.assertEqual(start, self.list_url)
        page = self.client.get(start)
        self.assertTemplateNotUsed(page, "screening/register.html")
        self.assertContains(page, "您目前的實際年齡？")

    def test_no_three_steps_and_no_login_link(self):
        main = self._main()
        self.assertNotIn("empty-preview", main)
        self.assertNotIn("我已經有帳號，登入", main)


class GuestHomeKeptResultTests(VisitorHomeTestCase):
    """#492 acceptance 21, the server's part: an empty place on top and each guest questionnaire's
    topic and result page, for guest-home.js to draw the kept results from (guest-home.test.js).
    The page is the same for every visitor, so it may still be cached."""

    def test_an_empty_place_on_top_and_the_guest_questionnaires(self):
        main = self._main()
        place = re.search(r'<div id="guest-home"([^>]*)></div>', main)
        self.assertIn("hidden", place.group(1))
        # Spec #741 acceptance 43 (#752, grill P14): above the blue hero card, under the bird.
        self.assertLess(main.index('<div class="bird-dialogue">'), place.start())
        self.assertLess(place.start(), main.index('<section class="hero-card"'))
        page = self.client.get(reverse("index")).content.decode()
        data = re.search(
            r'<script id="guest-home-data" type="application/json">(.*?)</script>', page
        )
        self.assertEqual(
            json.loads(data.group(1)),
            {
                code: {"topic": "聽力對生活的影響", "url": f"/guest/result/{code}"}
                for code in (hhie_s.CODE, hhia_s.CODE)
            },
        )
        self.assertIn("screening/frontend/guest-home.js", page)

    def test_the_same_page_for_every_visitor_and_still_cached(self):
        first = self.client.get(reverse("index"))
        self.client.cookies.clear()
        second = self.client.get(reverse("index"))
        self.assertEqual(without_nonce(first.content), without_nonce(second.content))
        self.assertNotIn("no-store", first.get("Cache-Control", ""))

    def test_signed_in_has_none(self):
        self.client.force_login(consented_user(username="signedin"))
        page = self.client.get(reverse("index")).content.decode()
        for part in ('id="guest-home"', "guest-home-data", "guest-home.js"):
            with self.subTest(part=part):
                self.assertNotIn(part, page)


class NewUserHomeTests(VisitorHomeTestCase):
    PASSWORD = "Xk9#mPq2vLw"
    OLD_HINT = "第一次使用請先註冊，已有帳號請直接登入。"

    def test_the_old_hint_is_gone(self):
        self.assertNotIn(self.OLD_HINT, self._main())

    def test_the_visitor_sees_the_two_doors_and_what_stays_below(self):
        # Spec #655 (#673, grill Q4): the doors take the place of the 空狀態首頁's heading, its
        # three steps, 開始篩檢 and 我是家人 (test_home_doors has the doors themselves).
        main = self._main()
        # #749 (the canvas's ProGuest): the bird's bubble is the page's heading.
        self.assertIn('<h1 class="bird-title">聽力變化常常容易被忽略</h1>', main)
        for gone in ("從一份問卷開始", "empty-preview"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, main)
        links = re.search(r'<ul class="home-links" role="list">(.*?)</ul>', main, re.S).group(1)
        # Spec #741 (#752): 了解助聽器選配與補助 became the door 想了解助聽器; P13 keeps this.
        self.assertEqual(
            re.findall(r'<li([^>]*)><a href="([^"]+)">([^<]+)</a></li>', links),
            [(" data-hide-in-app", reverse("add_to_home"), "加到手機主畫面")],
        )
        self.assertIn('<p class="empty-credit">內容由台灣執業聽力師設計與審定。</p>', main)
        self.assertEqual(main.count("btn-primary"), 0)
        for old in ("home-hero", "home-illustration", "result-preview", "結果長這樣"):
            with self.subTest(old=old):
                self.assertNotIn(old, main)

    # The logo and the one-time ring are drawn by CSS on btn-start and checked in e2e.
    def test_start_button_uses_the_btn_start_class(self):
        # Spec #655 (#673): only a signed-in user's 空狀態首頁 has 開始篩檢; a visitor has doors.
        self.assertNotIn("btn-start", self._main())
        self.client.force_login(consented_user(username="startbutton"))
        # #749 (ADR 0076): white, in the blue hero card.
        self.assertRegex(
            self._main(), r'<a class="btn btn-hero btn-lg btn-start"[^>]*>開始篩檢</a>'
        )

    # The 2026-11-14 walkthrough: someone with an account logs in to see their 照顧旅程, so the
    # link no longer sends them on to the questionnaire list. Since spec #741 (#752, grill P15)
    # that link is the page's 登入 outside the page body, with no next of its own.
    def test_login_link_logs_in_then_opens_the_home_page(self):
        consented_user(username="returning", password=self.PASSWORD)
        login = reverse("login")
        # The header's 登入 (#748): the tab bar's and the page's own went (spec #741 P9, P15).
        self.assertContains(
            self.client.get(reverse("index")), f'site-login" href="{login}">登入</a>'
        )
        response = self.client.post(
            login, {"username": "returning", "password": self.PASSWORD}, follow=True
        )
        self.assertEqual(response.redirect_chain[-1][0], reverse("index"))

    def test_other_protected_pages_still_go_to_login_and_back(self):
        consented_user(username="tester", password=self.PASSWORD)
        # The list is a guest's wizard since spec #492 (test_guest).
        for url in (reverse("my_hearing"), reverse("audiogram_list")):
            with self.subTest(url=url):
                self.client.logout()
                login_url = f"{reverse('login')}?next={url}"
                self.assertRedirects(self.client.get(url), login_url)
                response = self.client.post(
                    reverse("login"),
                    {"username": "tester", "password": self.PASSWORD, "next": url},
                )
                self.assertRedirects(response, url)

    def test_anonymous_home_has_no_never_cache_header(self):
        response = self.client.get(reverse("index"))
        self.assertNotIn("no-store", response.get("Cache-Control", ""))
