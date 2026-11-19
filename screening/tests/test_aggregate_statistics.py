from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening import models
from screening.models import Consent, User
from screening.tests import test_consent, test_layout


class StatisticsPrivacyTests(TestCase):
    """Spec #733 (ADR 0069): the privacy notice adds 整體統計 as a use, in consent version 9."""

    def setUp(self):
        page = self.client.get(reverse("privacy")).content.decode()
        self.main = page[page.index("<main") : page.index("</main>")]

    def part(self, title_id, next_id):
        # The row's words, from its title to the next row's start.
        html = self.main[self.main.index(f'id="{title_id}"') : self.main.index(f'id="{next_id}"')]
        return test_layout._text(html[html.index(">") + 1 : html.rindex("<details")])

    def test_why_it_is_collected_includes_the_statistics(self):
        why = self.part("why-title", "collected-title")
        self.assertIn(
            "把大家的篩檢結果和聽力紀錄合起來統計，改善網站，也對外說明聽伴的成效；"
            "對外只公布認不出是誰的整體數字。",
            why,
        )
        # Acceptance 7: the promise stays, now with the statistics listed above it.
        self.assertTrue(why.endswith("我們不會把您的資料拿去賣、做廣告，或做上面以外的用途。"))

    def test_a_part_of_its_own_after_the_feedback_part(self):
        self.assertIn('<h2 id="statistics-title" class="fold-row-title">整體統計</h2>', self.main)
        self.assertLess(
            self.main.index('id="feedback-title"'), self.main.index('id="statistics-title"')
        )
        self.assertLess(
            self.main.index('id="statistics-title"'), self.main.index('id="storage-title"')
        )

    def test_the_part_says_what_is_counted_and_what_is_published(self):
        # Acceptance 2: word for word, nothing more.
        sentences = (
            "我們會把大家的問卷作答與結果、聽力圖、助聽器與補助資料和出生年合起來統計，"
            "例如每個月有幾個人做篩檢、各分級各佔多少，用來改善網站，"
            "也會在簡報、網站或申請補助時說明聽伴的成效。",
            "不會用到您的 email、使用者名稱和登入方式。",
            "對外只公布整體數字，不公布任何人的作答、分數或帳號。",
            "一個數字背後少於 10 人時不公布，或併到大一點的組，避免被認出是誰。",
            "只統計同意這一版說明的人。",
            "刪除帳號後，您的資料不會再算進新的統計；已經公布的數字無法收回。",
            "以後如果要拿資料做學術研究，會另外說明、請您自己勾選同意；不勾也一樣能使用聽伴。",
        )
        self.assertEqual(
            self.part("statistics-title", "storage-title"), " ".join(("整體統計", *sentences))
        )


class StatisticsHighlightTests(TestCase):
    """Spec #733 acceptance 3: the highlights' first sentence adds the statistics, on every page
    that shows them."""

    NEW = "只用來算分數、給建議、保存您的紀錄，以及做認不出是誰的整體統計；不拿去賣或做廣告。"
    OLD = "只用來算分數、給建議、保存您的紀錄，不拿去賣或做廣告。"

    def test_the_privacy_consent_and_about_pages_say_it(self):
        self.client.force_login(User.objects.create_user(username="not_agreed"))
        for name in ("privacy", "consent", "about"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                # The first item under the highlights' first group, 用來做什麼.
                highlights = response.content.decode().split("用來做什麼</h3>", 1)[1]
                first = highlights[highlights.index("<li>") + 4 : highlights.index("</li>")]
                self.assertEqual(first, self.NEW)
                self.assertNotContains(response, self.OLD)


class ConsentVersionNineTests(TestCase):
    """Spec #733 acceptance 4–6: a new use, so version 9; who agreed to 8 agrees again."""

    def test_version_9_with_its_date(self):
        self.assertEqual(models.CONSENT_VERSION, 9)
        # Set the day version 9 goes live, not before the reminder's date (version 8's last move).
        self.assertGreaterEqual(models.PRIVACY_UPDATED_ON, date(2026, 11, 19))
        updated_on = f"{models.PRIVACY_UPDATED_ON:%Y/%m/%d}"
        self.assertContains(self.client.get(reverse("privacy")), f"第 9 版，{updated_on} 更新")

    def test_who_agreed_to_version_8_agrees_again_and_goes_on(self):
        user = User.objects.create_user(username="agreed_to_8")
        Consent.objects.create(user=user, version=8)
        self.client.force_login(user)
        url = reverse("my_hearing")
        consent_url = test_consent._consent_url(url)
        self.assertRedirects(self.client.get(url), consent_url)
        self.assertContains(self.client.get(consent_url), StatisticsHighlightTests.NEW)
        self.assertRedirects(
            self.client.post(consent_url, {"agree": "1"}), url, fetch_redirect_response=False
        )
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_agreeing_now_keeps_version_9(self):
        user = User.objects.create_user(username="new_here")
        self.client.force_login(user)
        self.client.post(reverse("consent"), {"agree": "1"})
        self.assertEqual(list(user.consents.values_list("version", flat=True)), [9])
