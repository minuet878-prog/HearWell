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
# Each tip as reviewed in the spec's appendix A: the bold point, then what follows its colon.
TIPS = {
    "talk-title": (
        ("先叫名字，等他看你再說", "可以輕拍肩膀，不要從背後或隔壁房間說話。"),
        (
            "面對面、讓他看得到你的臉",
            "表情和嘴型能幫助理解。站在光線照得到你臉的地方，不要背光。",
        ),
        (
            "說清楚、稍微放慢，不用大喊",
            "大喊會讓聲音變形，反而更難聽懂，也容易聽起來像在生氣。",
        ),
        ("說話時不要遮住嘴巴", "不要邊吃東西、邊走開或戴著口罩說重要的事。"),
        (
            "聽不懂時，換個說法",
            "同一句話重複很多次不一定有用，換成比較簡單或不同的詞試試看。",
        ),
        ("減少背景噪音", "說話前先把電視、收音機關小聲，在餐廳選安靜的角落。"),
        (
            "重要的事寫下來",
            "看診時間、地點、吃藥方式，說完再寫在紙上或傳文字訊息，請他確認。",
        ),
        ("多人聊天時，一次一個人說話", "換話題時先提醒「我們在講……」。"),
        (
            "耐心，也讓他參與",
            "不要替他回答，也不要說「算了，沒事」，被排除在對話外會讓人更不想說話。",
        ),
    ),
    "aid-title": (
        (
            "剛開始不習慣是正常的",
            "前幾週可能覺得自己的聲音怪怪的、環境的聲音很吵，大腦需要時間重新適應聲音。",
        ),
        (
            "鼓勵每天戴",
            "照聽力師建議，從安靜的地方、短時間開始，再慢慢拉長；戴得越規律，越容易適應。",
        ),
        (
            "陪他回診調整",
            "覺得太吵、太小聲或不舒服，都可以回去請聽力師調整，不用勉強忍耐。"
            "可以一起記下哪些場合聽不清楚，回診時告訴聽力師。",
        ),
        (
            "助聽器不是「戴上就跟以前一樣」",
            "在吵雜的餐廳、多人聊天時還是可能聽不清楚，上面的說話方法依然有用。",
        ),
        (
            "幫忙注意日常保養",
            "電池或充電、清潔、收納，長輩手指不靈活時特別需要幫忙。",
        ),
        (
            "多肯定他的努力",
            "願意配戴本身就不容易，注意到他聽得比較好時，可以告訴他。",
        ),
    ),
}
# The shared report's help cards link to these (#194).
ANCHORS = ("talk-title", "aid-title", "urgent-title")
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

    # 2; #240 moved the sources to the page's end, one group per topic under its title.
    def test_topics_in_order_with_sources_grouped_at_the_end(self):
        content = self.client.get(self.url).content.decode()
        headings = [content.index(f'id="{anchor}"') for anchor in ANCHORS]
        self.assertEqual(headings, sorted(headings))
        start = content.index('id="sources-title"')
        sources = content[start : content.index("</section>", start)]
        positions = [sources.index(f"<h3>{topic}</h3>") for topic in TOPICS]
        self.assertEqual(positions, sorted(positions))
        ends = [*positions[1:], len(sources)]
        for (topic, topic_sources), start, end in zip(TOPICS.items(), positions, ends, strict=True):
            group = sources[start:end]
            text = re.sub(r"<[^>]+>", "", group)
            for wording, url in topic_sources:
                with self.subTest(topic=topic, url=url):
                    self.assertIn(f'href="{url}"', group)
                    self.assertIn(wording, text)
        self.assertNotIn("（英文）", content)
        self.assertIn("119", content)

    # #240: the order of comparison row 15, option A.
    def test_blocks_in_the_redesigned_order(self):
        content = self.client.get(self.url).content.decode()
        main = content[content.index("<main") : content.index("</main>")]
        markers = (
            "<h1",
            "家人有聽力困難時",
            'aria-label="本頁內容"',
            'id="talk-title"',
            'id="aid-title"',
            'id="urgent-title"',
            DISCLAIMER,
            'id="share-title"',
            'id="sources-title"',
        )
        positions = [main.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))

    # #240: the bold point on one line, the rest on the next, without the colon between them.
    def test_each_tip_puts_its_point_above_the_rest(self):
        content = self.client.get(self.url).content.decode()
        for anchor, tips in TIPS.items():
            start = content.index(f'id="{anchor}"')
            section = content[start : content.index("</section>", start)]
            found = re.findall(
                r'<li><strong class="tip-point[^"]*">([^<]+)</strong>([^<]+)</li>', section
            )
            with self.subTest(anchor=anchor):
                self.assertEqual(tuple(found), tips)

    # 3
    def test_user_without_consent_can_read_it(self):
        self.client.force_login(User.objects.create_user(username="guide_old"))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    # 4
    def test_home_and_history_link_to_it(self):
        # The footer link starts with a decorative icon (footer redesign).
        link = rf'href="{self.url}">(<svg [^>]*aria-hidden="true".*?</svg>)?{LINK_TEXT}</a>'
        self.assertRegex(self.client.get(reverse("index")).content.decode(), link)
        self.client.force_login(consented_user(username="guide_user"))
        self.assertRegex(self.client.get(reverse("index")).content.decode(), link)
        self.assertRegex(self.client.get(reverse("my_hearing")).content.decode(), link)

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
