import re

from django.test import TestCase
from django.urls import reverse

from screening.tests import test_guide
from screening.tests.helpers import consented_user

# Wording finalised in #220 (C2–C31; C31 names the New Taipei centre), shortened in the guide
# chapters tidy-up (2026-10-23, the owner's request): step titles, the amounts as rows of numbers.
# #467 (H1 + H2): the parts titled as questions, read after the key cards.
FORM_9 = (
    "「九號表」是買助聽器前要做的輔具評估報告書（格式編號 9）。"
    "有身心障礙證明的人，帶著它向戶籍所在地的公所申請助聽器補助。",
    "我可以申請嗎？",
    "有聽覺機能身心障礙證明（第二類 b230、s260，或舊制 02）的人。輕度也可以，不限年齡。",
    "中度以上視覺障礙，而且好的那一耳聽力損失大於 40 dB 的人。",
    "最近一年在國內住超過 183 天。",
    "要怎麼辦？",
    # Readability batch 2 (the owner's A): the six steps in sight, their words behind
    # 看每一步的說明, the warning once, in step 4.
    "做評估，拿到九號表",
    "找聽力師或縣市輔具中心。九號表 3 個月內有效。",
    "到公所申請",
    "帶申請表、身分證正本和九號表，到戶籍所在地的公所，也可以線上申請。",
    "等核定通知",
    "主管機關收到評估報告後，10 天內會核定。",
    "購買並請款",
    "收到核定通知後 6 個月內。",
    "先拿到核定通知再買，沒核定就先買的不補助。",
    "使用效益驗證",
    "買中階型、進階型或雙對側傳聲型的人，配戴滿 1 個月到 3 個月內要做，"
    "拿到二十五號表。 看二十五號表",
    "核銷",
    "帶購買憑證、保固書影本（和二十五號表）。受理後 1 個月內撥款。",
    "九號表去哪裡開？",
    "聽力師或縣市輔具中心的評估人員都可以開，例如醫院耳鼻喉科的聽力師。",
    "各縣市輔具中心",
    "看各縣市輔具中心電話",
    "可以補助多少錢？",
    "補助上限，依助聽器等級",
    "2,000 元 簡易型，每只最多",
    "10,000 元 中階型，每只最多",
    "20,000 元 進階型，每只最多",
    "30,000 元 雙對側傳聲型，每組最多",
    "再乘上比例，而且不超過實際購買金額",
    "100% 低收入戶",
    "75% 中低收入戶",
    "50% 一般戶",
    "滿 65 歲以後才第一次鑑定為輕度的人，申請進階型另有總額上限："
    "低收入戶 20,000 元、中低收入戶 15,000 元、一般戶 10,000 元。",
    "雙耳一起申請或分開申請，都算同一項。",
    "用了幾年可以換新的？",
    "滿 4 年 可以再申請（最低使用年限）",
    "每 2 年 12 歲以下可以申請一次",
    "再次申請簡易型，不需要重新評估。",
    "沒有身障證明怎麼辦？",
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
    ("先拿到核定通知再買，沒核定就先買的不補助。", (RULES, TABLE)),
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
# Rows as read on the page, the tags gone (#578: the owner's wording in the #577 mockup).
CENTRES_SAMPLE = (
    "基隆市輔具資源中心 (02)2469-6966 轉 211",
    "新北市輔具資源中心(蘆洲) (02)8286-7045",
    "嘉義市輔具資源中心 西區服務處 (05)285-8212",
    "臺南市輔具資源中心 永華中心 (06)209-8938",
    "連江縣輔具資源中心 (0836)25022 轉 302 或 (0836)23050",
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
        text = test_guide.article_text(response)
        positions = [text.index(s) for s in FORM_9]
        self.assertEqual(positions, sorted(positions))

    def test_reapply_and_without_certificate_anchors_land_on_their_headings(self):
        content = self.client.get(self.url).content.decode()
        # Each part's title is a section title (T1, ADR 0043), without a top margin.
        for anchor, title in (
            ("reapply", "用了幾年可以換新的？"),
            ("without-certificate", "沒有身障證明怎麼辦？"),
        ):
            with self.subTest(anchor=anchor):
                heading = f'<h2 id="{anchor}" class="h4">{title}</h2>'
                self.assertIn(heading, content)

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
        test_guide.assert_footer(self, response, "2026/10/23", sources)
        # The footer's date is the page's only check date (the centre list has none of its own).
        self.assertEqual(test_guide.text_of(response).count("查核於"), 1)

    def test_issuer_section_lists_every_county_centre_with_its_source(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        start = content.index(
            '<ul class="centre-list" role="list" aria-labelledby="centres-title">'
        )
        centres = content[start : content.index("</section>", start)]
        positions = [
            centres.index(f'<li><span class="centre-county">{county}</span>') for county in COUNTIES
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(centres.count("<li>") - len(COUNTIES), CENTRE_COUNT)
        rows = [without_tags(row) for row in CENTRE_ROW.findall(centres)]
        for entry in CENTRES_SAMPLE:
            with self.subTest(entry=entry):
                self.assertIn(entry, rows)
        text = test_guide.text_of(response)
        self.assertIn('<h3 id="centres-title" class="h5 mt-4">各縣市輔具中心</h3>', content)
        # Guide chapters tidy-up: the list is folded away under the heading.
        box = content.index('<details class="dropdown-box mb-0">')
        self.assertLess(content.index('id="centres-title"'), box)
        self.assertIn("<summary>看各縣市輔具中心電話</summary>", content[box:start])
        self.assertTrue(centres.rstrip().endswith("</ul>\n    </details>"))
        self.assertLess(text.index(CENTRES_SOURCE), text.index("基隆市輔具資源中心"))
        self.assertIn(f'<p>資料來源：<a href="{PORTAL[1]}">{PORTAL[0]}</a></p>', content)

    def test_amounts_are_rows_of_large_numbers(self):
        content = self.client.get(self.url).content.decode()
        start = content.index('<h2 id="amount-title"')
        section = content[start : content.index("</section>", start)]
        values = re.findall(r'<span class="fact-rows-value">(.*?)</span>', section)
        self.assertEqual(
            values, ["2,000 元", "10,000 元", "20,000 元", "30,000 元", "100%", "75%", "50%"]
        )

    def test_steps_warn_against_buying_before_approval_and_link_to_form_25(self):
        content = self.client.get(self.url).content.decode()
        start = content.index('<h2 id="steps-title"')
        steps = content[start : content.index("</section>", start)]
        self.assertIn("先拿到核定通知再買，沒核定就先買的不補助。", steps)
        form_25 = reverse("guide_chapter", args=["form-25"])
        self.assertIn(f'<a href="{form_25}">看二十五號表</a>', steps)

    # Readability batch 2 (the owner's A, mockup-readability-batch2.html): one list of the six
    # steps in sight, each step's words shown while 看每一步的說明 over it is open (site.css; the
    # toggle above the list, so a screen reader reads on into the words; the sources in sight
    # under the list); the warning once, inside step 4. It was the warning in sight and the list
    # behind 看更多 (#467 H2).
    def test_process_is_the_six_steps_in_sight_their_words_behind_a_fold(self):
        content = self.client.get(self.url).content.decode()
        start = content.index('<h2 id="steps-title"')
        steps = content[start : content.index("</section>", start)]
        self.assertNotIn("tip-box", steps)
        self.assertEqual(steps.count('<ol class="step-list"'), 1)
        first = steps.index('<ol class="step-list" role="list">')
        last = steps.index("</ol>")
        toggle = re.search(r"<details([^>]*)><summary>看每一步的說明</summary></details>", steps)
        self.assertIsNotNone(toggle)
        self.assertIn("data-step-details", toggle.group(1))
        self.assertLess(toggle.end(), first)
        self.assertIn("來源：", steps[last:])
        items = re.findall(r"<li>(.*?)</li>", steps[first:last], re.S)
        self.assertEqual(len(items), 6)
        # The circles carry the numbers for screen readers too: the list's own markers are off.
        numbers = re.findall(r'<span class="step-list-number">(\d+)</span>', steps)
        self.assertEqual(numbers, ["1", "2", "3", "4", "5", "6"])
        for number, item in enumerate(items, 1):
            with self.subTest(step=number):
                self.assertEqual(item.count('<span class="step-detail">'), 1)
        self.assertEqual(steps.count("先拿到核定通知再買"), 1)
        self.assertIn("先拿到核定通知再買，沒核定就先買的不補助。", items[3])

    def test_each_step_has_its_time_limit_tag(self):
        content = self.client.get(self.url).content.decode()
        start = content.index('<h2 id="steps-title"')
        steps = content[start : content.index("</section>", start)]
        items = re.findall(r"<li>(.*?)</li>", steps, re.S)
        # Not hidden from screen readers: with the words folded, the tag is the time limit.
        self.assertEqual(re.findall(r'<span class="step-when"([^>]*)>', steps), [""] * 5)
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


# The centre list's numbers before #578, each centre's in page order, as area code and number
# without punctuation. They are reviewed data: #578 changes how they look, never a digit
# (spec #576 acceptance 3).
NUMBERS_BEFORE = (
    ("基隆市輔具資源中心", ("0224696966",)),
    ("臺北市西區輔具中心", ("0225237902",)),
    ("臺北市南區輔具中心", ("0227207364",)),
    ("臺北市合宜輔具中心", ("0277137760",)),
    ("新北市輔具資源中心(蘆洲)", ("0282867045",)),
    ("新北市輔具資源中心(新店)", ("0229121911",)),
    (
        "桃園市北區輔具資源中心",
        (
            "033683040",
            "033732028",
        ),
    ),
    ("桃園市南區輔具資源中心", ("034890298",)),
    ("新竹市輔具資源中心", ("035623707",)),
    ("新竹縣北區輔具資源中心", ("035527316",)),
    ("新竹縣南區輔具資源中心", ("035111015",)),
    (
        "北區輔具資源中心",
        (
            "037268462",
            "037268463",
        ),
    ),
    ("南區輔具資源中心", ("037752642",)),
    ("臺中市北區輔具資源中心", ("0425314200",)),
    ("臺中市南區輔具資源中心", ("0424713589",)),
    ("臺中市海線輔具資源中心", ("0426627152",)),
    ("彰化縣二林輔具資源中心 總站", ("048962178",)),
    ("彰化縣二林輔具資源中心 彰化據點", ("047229767",)),
    ("彰化縣田尾輔具資源中心", ("048836311",)),
    (
        "南投縣第一輔具資源中心",
        (
            "0492420338",
            "0492420390",
        ),
    ),
    ("南投縣第二輔具資源中心", ("0492228086",)),
    ("雲林縣輔助器具資源中心", ("055339620",)),
    ("雲林縣輔助器具資源中心虎尾站", ("056339620",)),
    ("嘉義市輔具資源中心 東區服務處", ("052256686",)),
    ("嘉義市輔具資源中心 西區服務處", ("052858212",)),
    ("嘉義縣輔具資源中心 山線服務中心", ("052793350",)),
    ("嘉義縣輔具資源中心 海線服務據點", ("053791851",)),
    ("嘉義縣民雄輔具資源中心", ("052268005",)),
    ("臺南市輔具資源中心 官田中心", ("065790636",)),
    ("臺南市輔具資源中心 佳里中心", ("067266700",)),
    ("臺南市輔具資源中心 永華中心", ("062098938",)),
    ("高雄市北區輔具資源中心 總站", ("076226730",)),
    ("高雄市北區輔具資源中心 鳳山據點", ("077100366",)),
    ("高雄市北區輔具資源中心 旗山據點", ("076625695",)),
    (
        "高雄市南區輔具資源中心 總站",
        (
            "078416336",
            "078151500",
        ),
    ),
    ("高雄市南區輔具資源中心 楠梓據點", ("073661130",)),
    ("屏東縣屏北區輔具資源中心", ("087365455",)),
    ("屏東縣屏中區輔具資源中心 總站", ("087899599",)),
    ("屏東縣屏中區輔具資源中心 屏南工作站", ("088883741",)),
    ("臺東縣輔具資源中心", ("089232263",)),
    (
        "花蓮縣輔具資源中心",
        (
            "038225365",
            "038241657",
            "038241658",
        ),
    ),
    (
        "花蓮縣南區輔具資源中心",
        (
            "038886586",
            "038887992",
        ),
    ),
    ("宜蘭縣溪北輔具資源中心", ("039320920",)),
    ("宜蘭縣溪南輔具資源中心", ("039544106",)),
    ("澎湖縣輔具資源中心", ("069262740",)),
    (
        "金門縣輔具資源中心",
        (
            "082333629",
            "082333269",
        ),
    ),
    (
        "連江縣輔具資源中心",
        (
            "083625022",
            "083623050",
        ),
    ),
)

DIAL_LINK = re.compile(r'<a href="(tel:[^"]*)"[^>]*>(.*?)</a>', re.S)
# A centre's row: an item of the list with no list inside it.
CENTRE_ROW = re.compile(r"<li>((?:(?!<li>|<ul).)*?)</li>", re.S)


def centre_list(response):
    content = response.content.decode()
    start = content.index('aria-labelledby="centres-title"')
    return content[start : content.index("</details>", start)]


def without_tags(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


class CentrePhoneLinksTests(TestCase):
    """#578 (spec #576): every phone number of the assistive device centres dials."""

    def setUp(self):
        self.url = reverse("guide_chapter", args=["form-9"])

    def test_every_number_is_a_dial_link_with_the_digits_it_had(self):
        signed_in = consented_user(username="centre_phone_user")
        for user in (None, signed_in):
            if user:
                self.client.force_login(user)
            with self.subTest(signed_in=bool(user)):
                block = centre_list(self.client.get(self.url))
                rows = []
                for row in CENTRE_ROW.findall(block):
                    name = re.match(r"\s*([^<]+)", row).group(1).strip()
                    links = DIAL_LINK.findall(row)
                    for href, shown in links:
                        number = without_tags(shown)
                        # The link is the number alone, as (area code)number.
                        self.assertRegex(number, r"^\(0\d{1,3}\)\d[\d-]*\d$")
                        # It dials that number from anywhere: +886, the leading 0 dropped.
                        self.assertEqual(href, "tel:+886" + re.sub(r"\D", "", number)[1:])
                    rows.append((name, tuple(re.sub(r"\D", "", without_tags(s)) for _, s in links)))
                self.assertEqual(tuple(rows), NUMBERS_BEFORE)
                # No number is left as plain words: outside the links, nothing as long as one.
                self.assertNotRegex(without_tags(DIAL_LINK.sub("", block)), r"\d[\d-]{5,}")

    # Spec #576 acceptance 4 to 6, each kind of row the owner read in the #577 mockup: an
    # extension is 轉 after its number, a range whole; several numbers are several links; a
    # note stays beside what it is about. (That a link holds its number alone is tested above.)
    ROWS = (
        "基隆市輔具資源中心 (02)2469-6966 轉 211",
        "桃園市北區輔具資源中心 (03)368-3040 (03)373-2028",
        "桃園市南區輔具資源中心 (03)4890298 轉 2000～2020",  # noqa: RUF001
        "新竹市輔具資源中心 (03)562-3707 轉 131～142",  # noqa: RUF001
        "新竹縣北區輔具資源中心 (03)552-7316 總機 9、轉 10～16",  # noqa: RUF001
        "臺中市海線輔具資源中心 (04)2662-7152 轉 35～39",  # noqa: RUF001
        "高雄市北區輔具資源中心 總站 (07)6226730 轉 145（輔具租借、諮詢）；轉 112、113（輔具申請）",
        "高雄市南區輔具資源中心 總站 (07)841-6336 (07)815-1500 轉 111",
        "花蓮縣輔具資源中心 (03)8225365 (03)8241657 (03)8241658",
        "宜蘭縣溪南輔具資源中心 (03)9544106 轉 8114",
        "金門縣輔具資源中心 服務電話 (082)333629 意見專線 (082)333269",
        "連江縣輔具資源中心 (0836)25022 轉 302 或 (0836)23050",
    )

    def test_extensions_and_notes_are_plain_words_beside_their_number(self):
        block = centre_list(self.client.get(self.url))
        rows = [without_tags(row) for row in CENTRE_ROW.findall(block)]
        for row in self.ROWS:
            with self.subTest(row=row):
                self.assertIn(row, rows)

    # Spec #576 acceptance 9: dozens of numbers on one page, so a link's name says whose it
    # is; the phone icon before it is drawn only.
    def test_a_link_is_named_by_its_centre_and_number_and_its_icon_is_not_read(self):
        block = centre_list(self.client.get(self.url))
        self.assertIn(
            '<a href="tel:+88678151500" aria-label="撥打高雄市南區輔具資源中心 總站 (07)815-1500">',
            block,
        )
        links = re.findall(r'<a href="tel:[^"]*" aria-label="([^"]*)">(.*?)</a>', block, re.S)
        self.assertEqual(len(links), 56)
        for name, shown in links:
            with self.subTest(name=name):
                # The words in sight are part of the name, for voice control.
                self.assertTrue(name.startswith("撥打"))
                self.assertTrue(name.endswith(without_tags(shown)))
                self.assertEqual(shown.count("<svg"), 1)
                self.assertIn(
                    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">', shown
                )
