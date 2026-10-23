import json
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from screening import assessment_hospitals
from screening.tests import test_guide

# Wording finalised in #220 (B2–B14, B11a, B11b), shortened in the guide chapters tidy-up
# (2026-10-23, the owner's request): the threshold as rows of numbers, the things to bring as chips.
ASSESSMENT = (
    "要申請助聽器的身障補助，先要有聽覺機能的身心障礙證明。證明要到鑑定醫院做身障鑑定。",
    "鑑定門檻",
    "雙耳整體障礙比率",
    "45.0% 以上：第 1 級（輕度）",
    "70.1% 以上：第 2 級",
    "90.1% 以上：第 3 級",
    "另外，一耳聽力 90 dB 以上、另一耳 48 dB 以上，也算第 1 級。",
    # Outside the dropdown: who the page does not apply to stays in sight.
    "未滿 6 歲的孩子門檻不同，本頁不適用，請直接問鑑定醫院。",
    "比率怎麼算",
    "用 500、1000、2000、4000 Hz 的聽力平均計算。",
    "鑑定時會做什麼",
    "耳鼻喉科專科醫師會做這三項，必要時再加做其他檢查：",
    "純音聽力檢查",
    "語音聽力檢查",
    "鼓室圖",
    "怎麼申請鑑定",
    "到公所申請",
    "戶籍所在縣市的任一區（鄉、鎮、市）公所，也可以線上申請。要帶：",
    "身分證影本",
    "一吋半身照片 3 張",
    "印章",
    "帶公所給的鑑定表，到鑑定醫院",
    "檢查費用由政府或健保支付。",
    "拿到證明",
    "鑑定完成後大約 35 天。",
    "找鑑定醫院",
    "選擇您的縣市，列出可以做聽覺機能鑑定的醫院",
)
# Under the menu and any list, as the card's last line.
ROSTER_NOTE = (
    "名冊：衛生福利部「各縣市身心障礙類別、向度之鑑定醫院名冊」（1150717）。"
    "實際的醫院和鑑定項目以各縣市衛生局公布為準，去之前建議先打電話確認。"
)
CHOOSE_COUNTY = "請先選擇縣市。"
# B15 without its full stop, as the menu's blank first option.
BLANK_OPTION = '<option value="" selected>請先選擇縣市</option>'
NONE_IN_COUNTY = "這個縣市目前名冊上沒有可以做聽覺機能鑑定的醫院，請洽縣市衛生局。"
SOURCES = (
    ("身心障礙者鑑定作業辦法", "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0020020"),
    (
        "身心障礙者鑑定作業辦法附表二甲",
        "https://law.moj.gov.tw/LawClass/LawGetFile.ashx?FileId=0000399716&amp;lan=C",
    ),
    (
        "身心障礙者鑑定作業辦法附表一甲",
        "https://law.moj.gov.tw/LawClass/LawGetFile.ashx?FileId=0000399714&amp;lan=C",
    ),
    (
        "身心障礙者權益保障法第 6 條",
        "https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=D0050046&amp;flno=6",
    ),
    (
        "鑑定及需求評估程序",
        "https://dpws.sfaa.gov.tw/idfbook-detail.jsp?serno=202409030003&amp;detailno=2",
    ),
    (
        "取得身心障礙證明，需要多久的作業時間？",
        "https://dpws.sfaa.gov.tw/idfbook-detail.jsp?serno=202409030001&amp;detailno=8",
    ),
    ("身心障礙證明線上申請", "https://dpws.sfaa.gov.tw/online_apply_menu.jsp"),
    (
        "各縣市身心障礙類別、向度之鑑定醫院名冊",
        "https://dep.mohw.gov.tw/DONAHC/cp-1037-5217-104.html",
    ),
)
# The 22 counties as the MOHW roster names them, in its sheet order.
COUNTIES = (
    "臺北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣", "臺中市", "彰化縣",
    "南投縣", "雲林縣", "嘉義市", "嘉義縣", "臺南市", "高雄市", "屏東縣", "基隆市",
    "宜蘭縣", "花蓮縣", "臺東縣", "澎湖縣", "金門縣", "連江縣",
)  # fmt: skip


class AssessmentChapterTests(TestCase):
    """#222: the disability assessment chapter and its hospital list by county."""

    def setUp(self):
        self.url = reverse("guide_chapter", args=["assessment"])

    def test_logged_out_visitor_reads_the_chapter_and_the_county_menu(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>身障鑑定與鑑定醫院\uff5cHearWell</title>")
        self.assertContains(response, '<h1 class="h3 mt-4">身障鑑定與鑑定醫院</h1>')
        text = test_guide.text_of(response)
        positions = [text.index(s) for s in (*ASSESSMENT, CHOOSE_COUNTY, ROSTER_NOTE)]
        self.assertEqual(positions, sorted(positions))
        content = response.content.decode()
        # Searching lands on the results, not at the top of the page.
        self.assertIn(f'<form method="get" action="{self.url}#hospital-results">', content)
        self.assertLess(content.index("</form>"), content.index('<div id="hospital-results"'))
        self.assertLess(content.index('<div id="hospital-results"'), content.index(CHOOSE_COUNTY))
        self.assertIn('<label for="county"', content)
        self.assertIn('<select id="county" name="county"', content)
        options = [
            content.index(f'<option value="{county}">{county}</option>') for county in COUNTIES
        ]
        self.assertEqual(options, sorted(options))
        # Nothing chosen: the blank first option is preselected, no county is.
        self.assertLess(content.index(BLANK_OPTION), options[0])
        self.assertEqual(content.count(" selected>"), 1)

    def test_footer_has_the_check_date_and_official_sources(self):
        response = self.client.get(self.url)
        test_guide.assert_footer(self, response, "2026-10-22", SOURCES)

    def test_the_threshold_is_three_rows_of_ratios_the_first_outlined(self):
        content = self.client.get(self.url).content.decode()
        start = content.index('<h2 id="threshold-title"')
        section = content[start : content.index("</section>", start)]
        rows = re.findall(
            r'<li( class="is-key")?><span class="fact-rows-value">(.*?)</span><span>(.*?)</span>',
            section,
        )
        self.assertEqual(
            rows,
            [
                (' class="is-key"', "45.0%", "以上：第 1 級（輕度）"),
                ("", "70.1%", "以上：第 2 級"),
                ("", "90.1%", "以上：第 3 級"),
            ],
        )

    def test_applying_is_a_three_step_list_ending_with_the_wait(self):
        content = self.client.get(self.url).content.decode()
        start = content.index('<h2 id="apply-title"')
        section = content[start : content.index("</section>", start)]
        steps = section[section.index('<ol class="step-list" role="list">') :]
        numbers = re.findall(r'<span class="step-list-number">(\d+)</span>', steps)
        self.assertEqual(numbers, ["1", "2", "3"])
        # Each step from its number to the next: step 1 holds a list of its own.
        items = re.split(r'<span class="step-list-number">\d+</span>', steps)[1:]
        self.assertIn("到公所申請", items[0])
        self.assertIn("戶籍所在縣市的任一區", items[0])
        chips = re.findall(r"</svg>\s*([^<]+?)\s*</li>", items[0])
        self.assertEqual(chips, ["身分證影本", "一吋半身照片 3 張", "印章"])
        self.assertIn("帶公所給的鑑定表，到鑑定醫院", items[1])
        self.assertIn("由政府或健保支付。", items[1])
        tags = [re.findall(r'<span class="step-when"[^>]*>(.*?)</span>', item) for item in items]
        self.assertEqual(tags, [[], [], ["約 35 天"]])

    def test_chosen_county_lists_only_its_hearing_assessment_hospitals(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.url, {"county": "澎湖縣"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        text = test_guide.text_of(response)
        # Roster 1150717, Penghu sheet: these three have "v" under b230; 惠民醫院 does not.
        for name in (
            "衛生福利部澎湖醫院",
            "三軍總醫院澎湖分院附設民眾診療服務處",
            "臺中市立老人復健綜合醫院（委託財團法人中國醫藥大學興建經營）",
        ):
            with self.subTest(name=name):
                self.assertRegex(content, rf"<li[^>]*>{re.escape(name)}</li>")
        listing = content[content.index('id="hospital-list"') :]
        self.assertEqual(listing[: listing.index("</ul>")].count("</li>"), 3)
        self.assertNotIn("惠民醫院", text)
        self.assertNotIn("臺北榮民總醫院", text)
        # How many before the list, the roster's version after it.
        self.assertLess(text.index("澎湖縣：3 家醫院"), text.index("衛生福利部澎湖醫院"))
        self.assertLess(text.index("衛生福利部澎湖醫院"), text.index(ROSTER_NOTE))
        self.assertIn('<option value="澎湖縣" selected>澎湖縣</option>', content)
        self.assertIn('<option value="">請先選擇縣市</option>', content)
        self.assertEqual(content.count(" selected>"), 1)
        self.assertNotIn(CHOOSE_COUNTY, text)

    def test_unknown_or_empty_county_shows_the_menu_without_an_error(self):
        for county in ("火星市", ""):
            with self.subTest(county=county):
                response = self.client.get(self.url, {"county": county})
                self.assertEqual(response.status_code, 200)
                content = response.content.decode()
                self.assertIn(CHOOSE_COUNTY, test_guide.text_of(response))
                self.assertIn('<option value="臺北市">臺北市</option>', content)
                self.assertIn(BLANK_OPTION, content)
                self.assertEqual(content.count(" selected>"), 1)
                self.assertNotIn('id="hospital-list"', content)

    def test_county_without_hospitals_says_to_ask_the_health_bureau(self):
        # Every county of roster 1150717 has one, so a stand-in snapshot shows the empty case.
        snapshot = {
            "version": "1150717",
            "counties": ["臺北市", "連江縣"],
            "hospitals": [{"county": "臺北市", "name": "測試醫院"}],
        }
        with mock.patch.object(assessment_hospitals, "roster", return_value=snapshot):
            text = test_guide.text_of(self.client.get(self.url, {"county": "臺北市"}))
            self.assertIn("測試醫院", text)
            self.assertNotIn(NONE_IN_COUNTY, text)
            text = test_guide.text_of(self.client.get(self.url, {"county": "連江縣"}))
            self.assertIn(NONE_IN_COUNTY, text)
            self.assertNotIn("測試醫院", text)

    def test_the_roster_is_read_once_on_first_use(self):
        assessment_hospitals.roster.cache_clear()
        self.addCleanup(assessment_hospitals.roster.cache_clear)
        with mock.patch.object(
            Path, "read_text", autospec=True, side_effect=Path.read_text
        ) as read:
            self.client.get(self.url)
            self.client.get(self.url, {"county": "澎湖縣"})
        self.assertEqual(read.call_count, 1)


class AssessmentHospitalSnapshotTests(TestCase):
    """#222: the roster snapshot the chapter reads."""

    def setUp(self):
        path = settings.BASE_DIR / "screening" / "data" / "assessment_hospitals.json"
        self.snapshot = json.loads(path.read_text(encoding="utf-8"))

    def test_every_row_has_a_county_among_the_22_and_a_hospital_name(self):
        self.assertEqual(self.snapshot["version"], "1150717")
        self.assertEqual(tuple(self.snapshot["counties"]), COUNTIES)
        self.assertTrue(self.snapshot["hospitals"])
        for row in self.snapshot["hospitals"]:
            with self.subTest(row=row):
                # Names only: the roster has no address or phone columns.
                self.assertEqual(set(row), {"county", "name"})
                self.assertIn(row["county"], COUNTIES)
                self.assertTrue(row["name"].strip())
