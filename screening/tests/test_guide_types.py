import re

from django.test import TestCase
from django.urls import reverse

from screening.tests import test_guide

# Wording finalised in #220: D2–D17 from the draft, D18 and D18a from the follow-up.
SENTENCES = (
    "助聽器有好幾種外型。適合哪一種，要看聽損程度、耳朵形狀和手的靈活度，請和聽力師討論。",
    "耳掛型：掛在耳朵後面，機體比較大、好操作，可以接耳塞或客製耳模，輕度到極重度都可以用。",
    "受話器外置型（耳道接收型）：機體小、掛在耳後，喇叭放進耳道，戴起來比較不悶，適合到重度。",
    "耳內型：依耳朵形狀訂製，戴在外耳殼，適合到重度。"
    "更小的有耳道型（適合到中重度）和深耳道型（最不明顯，適合輕度到中度）。",
    "上面的聽損程度，不是身心障礙證明的等級。",
    "集音器不是助聽器",
    "助聽器是醫療器材，要有衛生福利部的醫療器材許可證，而且要由有醫療器材販賣許可的業者販售。",
    "集音器、輔聽器一般不是醫療器材，依法不能宣稱改善聽損。買之前，先確認是不是有許可證的助聽器。",
    "補助等級與上限",
    "簡易型（類比或數位）：每只最多補助 2,000 元。",
    "中階型（數位、6 個以上壓縮頻道、多個程式、自動降噪、自動消除回饋音）：每只最多 10,000 元。",
    "進階型（中階型的功能，再加上指向性麥克風、可以接無線傳輸）：每只最多 20,000 元。",
    "雙對側傳聲型（好的那一耳戴進階型助聽器、另一耳戴無線收音麥克風，兩件一組）："
    "每組最多 30,000 元。",
    "實際售價依等級與店家差異很大，購買前請店家提供報價單與保固內容。",
    "去哪裡買",
    "請在有醫療器材販賣業許可的聽力所或醫院購買。"
    "保固書上要有醫療器材許可證字號，申請補助核銷時也會用到。",
    "想確認助聽器是不是合法上市，可以到食藥署「西藥、醫療器材及化粧品許可證暨相關資料查詢」網站"
    "（lmspiq.fda.gov.tw），輸入許可證字號、中文品名或廠商名稱查詢。",
    "查詢時要輸入驗證碼，可以按語音播放聽。",
)
FDA_SEARCH = "https://lmspiq.fda.gov.tw/web/MDPIQ/MDPIQ1000"
# research.md §2 (subsidy table), §5 (Medical Devices Act), §6 (the SFAA leaflet).
SOURCES = (
    (
        "助聽器 構造／種類／功能",
        "https://hearingcare.psa.org.tw/documents/助聽器%20構造_種類_功能.pdf",
    ),
    (
        "身心障礙者輔具費用補助基準表",
        "https://law.moj.gov.tw/LawClass/LawGetFile.ashx?FileId=0000326887&amp;lan=C",
    ),
    ("醫療器材管理法", "https://law.moj.gov.tw/LawClass/LawAll.aspx?PCODE=L0030106"),
)


def flat_text(response):
    """The visible text with all whitespace removed, so a link inside a sentence still matches."""
    return "".join(test_guide.text_of(response).split())


class TypesAndPricesChapterTests(TestCase):
    """#224: the hearing aid types and prices chapter."""

    def setUp(self):
        self.url = reverse("guide_chapter", args=["types-and-prices"])

    def test_logged_out_visitor_reads_the_finalised_sentences_in_order(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>助聽器的種類與價格")
        self.assertContains(response, '<h1 class="h3 mt-4">助聽器的種類與價格</h1>')
        text = flat_text(response)
        positions = [text.index("".join(sentence.split())) for sentence in SENTENCES]
        self.assertEqual(positions, sorted(positions))

    def test_the_licence_search_names_and_links_the_fda_site(self):
        content = self.client.get(self.url).content.decode()
        self.assertIn(
            f'食藥署「<a href="{FDA_SEARCH}">西藥、醫療器材及化粧品許可證暨相關資料查詢</a>」網站',
            content,
        )
        self.assertNotIn("info.fda.gov.tw", content)

    def test_footer_has_the_check_date_and_official_sources(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        text = test_guide.text_of(response)
        self.assertIn(test_guide.CHECKED, text)
        for wording, url in SOURCES:
            with self.subTest(url=url):
                self.assertIn(f'href="{url}"', content)
                self.assertIn(wording, text)

    def test_the_only_amounts_are_the_four_subsidy_limits_and_no_brand_is_named(self):
        text = test_guide.text_of(self.client.get(self.url))
        self.assertEqual(
            re.findall(r"[\d,]+ *元", text), ["2,000 元", "10,000 元", "20,000 元", "30,000 元"]
        )
        # Brands and models are written in Latin letters; the only ones here are the FDA domain.
        self.assertEqual(set(re.findall(r"[A-Za-z]+", text)), {"lmspiq", "fda", "gov", "tw"})
        for brand in ("峰力", "奧迪康", "西嘉", "瑞聲達", "唯聽", "斯達克", "優利康", "伯納峰"):
            with self.subTest(brand=brand):
                self.assertNotIn(brand, text)

    def test_the_only_outside_links_are_the_fda_search_and_the_official_sources(self):
        # No shop or brand site: every link leaving HearWell is one of these.
        content = self.client.get(self.url).content.decode()
        outside = set(re.findall(r'href="(https?://[^"]+)"', content))
        self.assertEqual(outside, {FDA_SEARCH} | {url for _, url in SOURCES})
