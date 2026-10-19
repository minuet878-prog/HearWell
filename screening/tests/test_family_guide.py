import re

from django.test import TestCase
from django.urls import reverse

from screening.models import User
from screening.tests.helpers import consented_user

# Each topic with its sources, worded exactly as reviewed in the spec's appendix A.
TOPICS = {
    "怎麼跟聽損的家人說話": (
        (
            "美國聽語學會（ASHA）〈Tips for Communicating With Someone Who Has Hearing Loss〉",
            "https://www.asha.org/about/press-room/articles/tips-for-communicating-with-someone-who-has-hearing-loss/",
        ),
        (
            "美國聽損協會（HLAA）〈Communication Tips〉",
            "https://www.hearingloss.org/managing-hearing-loss/hearing-loss-101/communication-tips/",
        ),
    ),
    "陪伴配戴助聽器": (
        (
            "美國聽語學會（ASHA）〈Hearing Aids for Adults〉",
            "https://www.asha.org/practice-portal/professional-issues/hearing-aids-for-adults/",
        ),
        (
            "美國國家耳聾及其他溝通障礙研究院（NIDCD）〈Hearing Aids〉",
            "https://www.nidcd.nih.gov/sites/default/files/hearing-aids.pdf",
        ),
    ),
    "什麼時候要馬上就醫": (
        (
            "美國耳鼻喉頭頸外科醫學會基金會（AAO-HNSF）"
            "〈Clinical Practice Guideline: Sudden Hearing Loss (Update)〉，2019",
            "https://pubmed.ncbi.nlm.nih.gov/31369359/",
        ),
        (
            "美國國家耳聾及其他溝通障礙研究院（NIDCD）〈Sudden Sensorineural Hearing Loss〉",
            "https://www.nidcd.nih.gov/health/sudden-deafness",
        ),
    ),
}
LINK_TEXT = "給家人看：怎麼跟聽損的家人溝通"
DISCLAIMER = "這些是一般性的建議，不能取代醫師或聽力師的診斷"


class FamilyGuideTests(TestCase):
    """Spec docs/specs/phase-08/phase8_c1_family_guide.md.

    Acceptance 1-7 (8 is the content review)."""

    def setUp(self):
        self.url = reverse("family_guide")

    # 1
    def test_anyone_can_read_it_without_logging_in(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "給家人的溝通與陪伴")

    # 2
    def test_topics_in_order_with_sources_and_disclaimer(self):
        content = self.client.get(self.url).content.decode()
        positions = [content.index(topic) for topic in TOPICS]
        self.assertEqual(positions, sorted(positions))
        ends = [*positions[1:], content.index(DISCLAIMER)]
        for (topic, sources), start, end in zip(TOPICS.items(), positions, ends, strict=True):
            section = content[start:end]
            text = re.sub(r"<[^>]+>", "", section)
            for wording, url in sources:
                with self.subTest(topic=topic, url=url):
                    self.assertIn(f'href="{url}"', section)
                    self.assertIn(wording, text)
        self.assertNotIn("（英文）", content)
        self.assertIn("119", content)

    # 3
    def test_user_without_consent_can_read_it(self):
        self.client.force_login(User.objects.create_user(username="guide_old"))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    # 4
    def test_home_and_history_link_to_it(self):
        link = f'href="{self.url}">{LINK_TEXT}</a>'
        self.assertContains(self.client.get(reverse("index")), link)
        self.client.force_login(consented_user(username="guide_user"))
        self.assertContains(self.client.get(reverse("index")), link)
        self.assertContains(self.client.get(reverse("my_hearing")), link)

    # 5 (the share sheet itself is checked in a real browser by e2e.main_flow)
    def test_share_button_and_visible_address(self):
        content = self.client.get(self.url).content.decode()
        self.assertIn('id="share-button"', content)
        self.assertIn("screening/share-button.js", content)
        # Shown as text, so it can be copied without JavaScript.
        self.assertIn(f"https://testserver{self.url}", content)

    # 7
    def test_no_user_data_on_the_page(self):
        user = consented_user(username="guide_private", email="private@example.com")
        self.client.force_login(user)
        content = self.client.get(self.url).content.decode()
        main = content[content.index("<main") :]
        self.assertNotIn("guide_private", main)
        self.assertNotIn("private@example.com", content)
