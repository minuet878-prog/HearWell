"""Spec #148 batch 1, ticket #150: the visitor's home page. A signed-in user's home, the 照顧旅程
or the 空狀態首頁, is test_home_journey's (#459). #471 (mockup #458 ⑪ for a visitor): the visitor
sees the 空狀態首頁 too, its first step 建立帳號."""

import re

from django.test import TestCase
from django.urls import reverse

from screening.tests.helpers import consented_user


class NewUserHomeTests(TestCase):
    PASSWORD = "Xk9#mPq2vLw"
    STEPS = (
        "建立帳號，大約 1 分鐘。",
        "回答問題，大約 3 分鐘。",
        "馬上看到結果分級和建議。",
    )
    OLD_HINT = "第一次使用請先註冊，已有帳號請直接登入。"

    def setUp(self):
        self.list_url = reverse("questionnaire_list")
        self.start_url = f"{reverse('register')}?next={self.list_url}"
        self.login_url = f"{reverse('login')}?next={self.list_url}"

    def _main(self):
        content = self.client.get(reverse("index")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _link(self, main, text):
        """The href of the link in the page body whose whole text is `text`."""
        links = re.findall(r'<a[^>]*href="([^"]*)"[^>]*>\s*([^<]*?)\s*</a>', main)
        hrefs = [href for href, label in links if label == text]
        self.assertEqual(len(hrefs), 1, f"{text}: {links}")
        return hrefs[0]

    def _steps(self, main):
        steps = re.search(r'<div class="empty-preview">.*?</ol>', main, re.DOTALL).group(0)
        return re.findall(r'<span class="step-list-body">([^<]+)</span>', steps)

    def test_anonymous_sees_start_and_login_buttons_and_three_steps(self):
        main = self._main()
        self.assertEqual(self._link(main, "開始篩檢"), self.start_url)
        self.assertEqual(self._link(main, "我已經有帳號，登入"), self.login_url)
        self.assertEqual(self._steps(main), list(self.STEPS))
        self.assertNotIn(self.OLD_HINT, main)

    def test_the_visitor_sees_the_empty_state_home(self):
        main = self._main()
        self.assertIn('<h1 class="h3">從一份問卷開始</h1>', main)
        self.assertIn(
            "<p>聽力變化很慢，自己常常沒發現。花 3 分鐘，看看聽力對您生活的影響。</p>", main
        )
        self.assertIn(
            '<p class="empty-preview-title">做完第一份問卷，這裡會排出您的照顧旅程</p>', main
        )
        links = re.search(r'<ul class="home-links" role="list">(.*?)</ul>', main, re.S).group(1)
        self.assertEqual(
            re.findall(r'<li([^>]*)><a href="([^"]+)">([^<]+)</a></li>', links),
            [
                ("", reverse("guide"), "了解助聽器選配與補助"),
                ("", reverse("family_guide"), "我是家人"),
                (" data-hide-in-app", reverse("add_to_home"), "加到手機主畫面"),
            ],
        )
        self.assertIn('<p class="empty-credit">內容由台灣執業聽力師設計與審定。</p>', main)
        self.assertEqual(main.count("btn-primary"), 1)
        for old in ("home-hero", "home-illustration", "result-preview", "結果長這樣"):
            with self.subTest(old=old):
                self.assertNotIn(old, main)

    def test_login_is_a_text_link_under_the_start_button(self):
        main = self._main()
        login = re.search(r"<a([^>]*)>\s*我已經有帳號，登入\s*</a>", main)
        self.assertNotIn("btn", login.group(1))
        self.assertLess(main.index(">開始篩檢<"), login.start())

    # The logo and the one-time ring are drawn by CSS on btn-start and checked in e2e.
    def test_start_button_uses_the_btn_start_class(self):
        for logged_in in (False, True):
            if logged_in:
                self.client.force_login(consented_user(username="startbutton"))
            with self.subTest(logged_in=logged_in):
                self.assertRegex(
                    self._main(),
                    r'<a class="btn btn-primary btn-lg btn-start w-full"[^>]*>開始篩檢</a>',
                )

    def test_login_button_logs_in_then_chooses_a_questionnaire(self):
        consented_user(username="returning", password=self.PASSWORD)
        page = self.client.get(self._link(self._main(), "我已經有帳號，登入"))
        self.assertContains(
            page, f'<input type="hidden" name="next" value="{self.list_url}">', html=True
        )
        response = self.client.post(
            reverse("login"),
            {"username": "returning", "password": self.PASSWORD, "next": self.list_url},
        )
        self.assertRedirects(response, self.list_url)

    def test_start_registers_then_consents_then_chooses_a_questionnaire(self):
        page = self.client.get(self._link(self._main(), "開始篩檢"))
        self.assertTemplateUsed(page, "screening/register.html")
        self.assertContains(
            page, f'<input type="hidden" name="next" value="{self.list_url}">', html=True
        )
        response = self.client.post(
            reverse("register"),
            {
                "username": "newcomer",
                "email": "newcomer@example.com",
                "password1": self.PASSWORD,
                "password2": self.PASSWORD,
                "next": self.list_url,
            },
        )
        consent_url = f"{reverse('consent')}?next={self.list_url}"
        self.assertRedirects(response, consent_url)
        response = self.client.post(consent_url, {"agree": "1", "next": self.list_url})
        # The wizard's first screen greets the new account (#152).
        self.assertRedirects(response, f"{self.list_url}?from=consent")

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
