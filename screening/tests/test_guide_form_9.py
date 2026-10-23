import re

from django.test import TestCase
from django.urls import reverse

from screening.tests import test_guide

# Wording finalised in #220 (C2–C31; C31 names the New Taipei centre), shortened in the plan B
# tidy-up (2026-10-23, the owner's request): step titles, the amounts as rows of numbers.
FORM_9 = (
    "「九號表」是買助聽器前要做的輔具評估報告書（格式編號 9）。"
    "有身心障礙證明的人，帶著它向戶籍所在地的公所申請助聽器補助。",
    "誰可以申請",
    "有聽覺機能身心障礙證明（第二類 b230、s260，或舊制 02）的人。輕度也可以，不限年齡。",
    "中度以上視覺障礙，而且好的那一耳聽力損失大於 40 dB 的人。",
    "最近一年在國內住超過 183 天。",
    "申請流程",
    "做評估，拿到九號表",
    "找聽力師或縣市輔具中心。九號表 3 個月內有效。",
    "到公所申請",
    "帶申請表、身分證正本和九號表，到戶籍所在地的公所，也可以線上申請。",
    "等核定通知",
    "收到評估報告後，10 天內核定。",
    # Between steps 3 and 4 since the step list (#259).
    "重要：一定要先拿到核定通知再買，沒核定就先買的不補助。",
    "購買並請款",
    "收到核定通知後 6 個月內。",
    "使用效益驗證",
    "買中階型、進階型或雙對側傳聲型的人，配戴滿 1 個月到 3 個月內要做，"
    "拿到二十五號表。 看二十五號表",
    "核銷",
    "帶購買憑證、保固書影本（和二十五號表）。受理後 1 個月內撥款。",
    "九號表找誰開",
    "聽力師或縣市輔具中心的評估人員都可以開，例如醫院耳鼻喉科的聽力師。",
    "各縣市輔具中心電話",
    "補助多少",
    "每只的上限，依助聽器等級",
    "2,000 元 簡易型",
    "10,000 元 中階型",
    "20,000 元 進階型",
    "30,000 元 雙對側傳聲型（一組）",
    "再乘上比例，而且不超過實際購買金額",
    "100% 低收入戶",
    "75% 中低收入戶",
    "50% 一般戶",
    "滿 65 歲以後才第一次鑑定為輕度的人，申請進階型另有總額上限："
    "低收入戶 20,000 元、中低收入戶 15,000 元、一般戶 10,000 元。",
    "雙耳一起申請或分開申請，都算同一項。",
    "再次申請（換新機）",
    "滿 4 年 可以再申請（最低使用年限）",
    "每 2 年 12 歲以下可以申請一次",
    "再次申請簡易型，不需要重新評估。",
    "沒有身障證明時",
    "不能申請上面的補助，但還有下面這些資源。",
    "低收入戶老人配戴助聽器補助",
    "5,500 元 每只最多，同一耳 4 年一次",
    "65 歲以上（原住民 55 歲以上）的低收入戶，經健保合約醫療院所診斷，"
    "聽力損失在 45 到 110 分貝之間。",
    "申請時附 6 個月內的診斷證明書和聽力圖正本，向設籍或居住的縣市政府申請。",
    "縣市補助",
    "各縣市可能另有補助，請洽您縣市的社會局。",
    "免費評估和試戴",
    "有些縣市的輔具中心提供，沒有身障證明也可以，例如新北市輔具資源中心。",
)

RULES = ("身心障礙者輔具費用補助辦法", "https://law.moj.gov.tw/LawClass/LawAll.aspx?PCODE=D0050060")
TABLE = (
    "身心障礙者輔具費用補助基準表",
    "https://law.moj.gov.tw/LawClass/LawGetFile.ashx?FileId=0000326887&amp;lan=C",
)
LOW_INCOME_ELDERLY = (
    "衛生福利部社會及家庭署低收入戶老人配戴助聽器獎助項目及基準（114–117 年）",
    "https://social.chiayi.gov.tw/News_Content.aspx?n=1101&amp;s=909655",
)
NEW_TAIPEI = ("新北市輔具資源中心公告", "https://atrc.aihsin.ntpc.gov.tw/NewsInfo/62")
PORTAL = ("輔具資源入口網", "https://newrepat.sfaa.gov.tw/home/repat-center")
# Each block of amounts, time limits or conditions: its last sentence, and the sources
# that must be linked before its section ends (research.md §2, §3).
SOURCED_BLOCKS = (
    ("最近一年在國內住超過 183 天。", (RULES, TABLE)),
    ("重要：一定要先拿到核定通知再買，沒核定就先買的不補助。", (RULES, TABLE)),
    ("雙耳一起申請或分開申請，都算同一項。", (RULES, TABLE)),
    ("再次申請簡易型，不需要重新評估。", (TABLE,)),
    ("向設籍或居住的縣市政府申請。", (LOW_INCOME_ELDERLY,)),
    ("例如新北市輔具資源中心。", (NEW_TAIPEI,)),
)

# C17: copied from the portal's contact sheet (updated 2026-03-20), every centre and
# service office, grouped by county in the sheet's order.
COUNTIES = (
    "基隆市", "臺北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣", "臺中市",
    "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "臺南市", "高雄市", "屏東縣",
    "臺東縣", "花蓮縣", "宜蘭縣", "澎湖縣", "金門縣", "連江縣",
)  # fmt: skip
CENTRE_COUNT = 47
CENTRES_SAMPLE = (
    "基隆市輔具資源中心：(02)2469-6966#211",
    "新北市輔具資源中心(蘆洲)：(02)8286-7045",
    "嘉義市輔具資源中心 西區服務處：(05)285-8212",
    "臺南市輔具資源中心 永華中心：(06)209-8938",
    "連江縣輔具資源中心：(0836)25022#302 或 (0836)23050",
)
CENTRES_SOURCE = "資料來源： 輔具資源入口網"


class Form9ChapterTests(TestCase):
    """#223: the form 9 subsidy chapter of the hearing-aid guide."""

    def setUp(self):
        self.url = reverse("guide_chapter", args=["form-9"])

    def test_logged_out_visitor_reads_the_whole_chapter_in_order(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1 class="h3 mt-4">九號表：申請助聽器補助</h1>')
        text = test_guide.text_of(response)
        positions = [text.index(sentence) for sentence in FORM_9]
        self.assertEqual(positions, sorted(positions))

    def test_reapply_and_without_certificate_anchors_land_on_their_headings(self):
        content = self.client.get(self.url).content.decode()
        # Each part is a card since the text-heavy pages tidy-up, its title without a top margin.
        self.assertIn('<h2 id="reapply" class="h4">再次申請（換新機）</h2>', content)
        self.assertIn('<h2 id="without-certificate" class="h4">沒有身障證明時</h2>', content)

    def test_amounts_time_limits_and_conditions_have_their_sources_beside_them(self):
        content = self.client.get(self.url).content.decode()
        for sentence, sources in SOURCED_BLOCKS:
            start = content.index(sentence)
            block = content[start : content.index("</section>", start)]
            with self.subTest(sentence=sentence):
                self.assertIn("來源：", block)
                for wording, url in sources:
                    self.assertIn(f'<a href="{url}">{wording}</a>', block)

    def test_footer_has_the_check_date_and_every_official_source(self):
        response = self.client.get(self.url)
        sources = (RULES, TABLE, LOW_INCOME_ELDERLY, NEW_TAIPEI, PORTAL)
        test_guide.assert_footer(self, response, "2026-10-23", sources)
        # The footer's date is the page's only check date (the centre list has none of its own).
        self.assertEqual(test_guide.text_of(response).count("查核於"), 1)

    def test_issuer_section_lists_every_county_centre_with_its_source(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        start = content.index('<ul aria-labelledby="centres-title">')
        centres = content[start : content.index("</section>", start)]
        positions = [centres.index(f"<li>{county}") for county in COUNTIES]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(centres.count("<li>") - len(COUNTIES), CENTRE_COUNT)
        for entry in CENTRES_SAMPLE:
            with self.subTest(entry=entry):
                self.assertIn(f"<li>{entry}</li>", centres)
        text = test_guide.text_of(response)
        # Plan B tidy-up: the list is folded away behind its title.
        box = content.index('<details class="dropdown-box mb-0">')
        self.assertIn('<summary id="centres-title">各縣市輔具中心電話</summary>', content)
        self.assertLess(box, content.index('id="centres-title"'))
        self.assertLess(content.index('id="centres-title"'), start)
        self.assertTrue(centres.rstrip().endswith("</ul>\n    </details>"))
        self.assertLess(text.index(CENTRES_SOURCE), text.index("基隆市輔具資源中心"))
        self.assertIn(f'<p>資料來源：<a href="{PORTAL[1]}">{PORTAL[0]}</a></p>', content)

    def test_steps_warn_against_buying_before_approval_and_link_to_form_25(self):
        content = self.client.get(self.url).content.decode()
        start = content.index('<h2 id="steps-title"')
        steps = content[start : content.index("</section>", start)]
        self.assertIn("重要：一定要先拿到核定通知再買，沒核定就先買的不補助。", steps)
        form_25 = reverse("guide_chapter", args=["form-25"])
        self.assertIn(f'<a href="{form_25}">看二十五號表</a>', steps)

    def test_process_is_a_step_list_split_by_the_warning_after_step_3(self):
        content = self.client.get(self.url).content.decode()
        start = content.index('<h2 id="steps-title"')
        steps = content[start : content.index("</section>", start)]
        first = steps.index('<ol class="step-list" role="list">')
        second = steps.index('<ol class="step-list" role="list" start="4">')
        warning = steps.index("重要：一定要先拿到核定通知再買")
        self.assertLess(steps.index("</ol>", first), warning)
        self.assertLess(warning, second)
        self.assertEqual(steps[first:warning].count("<li>"), 3)
        self.assertEqual(steps[second:].count("<li>"), 3)
        # The circles carry the numbers for screen readers too: the list's own markers are off.
        numbers = re.findall(r'<span class="step-list-number">(\d+)</span>', steps)
        self.assertEqual(numbers, ["1", "2", "3", "4", "5", "6"])

    def test_each_step_has_its_time_limit_tag(self):
        content = self.client.get(self.url).content.decode()
        start = content.index('<h2 id="steps-title"')
        steps = content[start : content.index("</section>", start)]
        items = re.findall(r"<li>(.*?)</li>", steps, re.S)
        tags = [re.findall(r'<span class="step-when"[^>]*>(.*?)</span>', item) for item in items]
        expected = [
            ["3 個月內有效"],
            [],
            ["10 天內核定"],
            ["6 個月內"],
            ["配戴 1–3 個月內"],
            ["1 個月內撥款"],
        ]
        self.assertEqual(tags, expected)


class BeforeYouGoLinkTests(TestCase):
    """#223 (#220 A16): the before-you-go reminder now links to this chapter."""

    def test_reminder_is_followed_by_a_link_to_the_form_9_steps(self):
        response = self.client.get(reverse("guide_chapter", args=["before-you-go"]))
        content = response.content.decode()
        link = f'<a href="{reverse("guide_chapter", args=["form-9"])}">看九號表的流程</a>'
        self.assertIn(link, content)
        reminder = test_guide.BEFORE_YOU_GO[-1]
        self.assertLess(content.index(reminder), content.index(link))
