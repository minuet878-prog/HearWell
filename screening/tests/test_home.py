"""Spec #148 batch 1, ticket #150: the visitor's home page. A signed-in user's home, the 照顧旅程
or the 空狀態首頁, is test_home_journey's (#459)."""

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
        "半年後再做，看分數變化。",
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
        steps = re.search(r'<ol class="step-cards.*?</ol>', main, re.DOTALL).group(0)
        return re.findall(r"<span>([^<]+)</span>", steps)

    def test_anonymous_sees_start_and_login_buttons_and_four_steps(self):
        main = self._main()
        self.assertEqual(self._link(main, "開始篩檢"), self.start_url)
        self.assertEqual(self._link(main, "我已經有帳號，登入"), self.login_url)
        self.assertEqual(self._steps(main), list(self.STEPS))
        self.assertNotIn(self.OLD_HINT, main)

    def test_hero_labels_sit_above_the_title(self):
        main = self._main()
        hero = main[main.index('<section class="home-hero') : main.index("<h1")]
        chips = re.findall(r'<span class="home-chip">.*?</svg>\s*([^<]+?)\s*</span>', hero, re.S)
        self.assertEqual(chips, ["約 3 分鐘", "國際標準量表"])
        self.assertEqual(hero.count('aria-hidden="true"'), hero.count("<svg"))

    def test_login_is_a_text_link_under_the_start_button(self):
        main = self._main()
        login = re.search(r"<a([^>]*)>\s*我已經有帳號，登入\s*</a>", main)
        self.assertNotIn("btn", login.group(1))
        self.assertLess(main.index(">開始篩檢<"), login.start())

    def test_title_is_larger_and_the_picture_is_the_smiling_elder(self):
        main = self._main()
        self.assertRegex(main, r'<h1 class="[^"]*\btext-center\b[^"]*">了解聽力對您生活的影響</h1>')
        start = main.index('class="home-illustration"')
        picture = main[start : main.index("</svg>", start)]
        for part in ("ill-face", "ill-hair", "ill-cheek", "ill-accent"):
            self.assertIn(part, picture)

    def test_result_preview_shows_the_result_page_score_bar(self):
        # Design picker round 2: the example card carries the same bar as the result page,
        # with HHIE-S's own thresholds and the made-up 18 points.
        main = self._main()
        preview = main[main.index('<figure class="result-preview">') : main.index("</figure>")]
        self.assertIn('<div class="score-bar" aria-hidden="true">', preview)
        for level, width in (("normal", 20), ("mild_to_moderate", 40), ("severe", 40)):
            with self.subTest(level=level):
                self.assertIn(
                    f'class="score-bar-segment score-bar-segment-{level}" '
                    f'style="width: {width}.00%"',
                    preview,
                )
        self.assertIn('class="score-bar-marker" style="--position: 45.00%"', preview)
        self.assertLess(preview.index("result-banner"), preview.index("score-bar"))

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
        for url in (self.list_url, reverse("my_hearing"), reverse("audiogram_list")):
            with self.subTest(url=url):
                self.client.logout()
                login_url = f"{reverse('login')}?next={url}"
                self.assertRedirects(self.client.get(url), login_url)
                response = self.client.post(
                    reverse("login"),
                    {"username": "tester", "password": self.PASSWORD, "next": url},
                )
                self.assertRedirects(response, url)

    def test_result_preview_uses_the_result_page_level_style(self):
        # 18 points on HHIE-S is mild to moderate; the result page draws its banner the same way.
        self.assertInHTML(
            '<div class="result-banner result-banner-mild_to_moderate">'
            '<div class="result-level">輕度到中度影響</div>'
            "<div>HHIE-S 總分 18 分（滿分 40）</div></div>",
            self._main(),
        )

    def test_anonymous_home_has_no_never_cache_header(self):
        response = self.client.get(reverse("index"))
        self.assertNotIn("no-store", response.get("Cache-Control", ""))
