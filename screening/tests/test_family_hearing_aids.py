"""#433 (spec #426): 助聽器, as the server sends it. Picking a problem in a real browser is in
e2e.main_flow.FamilyHearingAidsTest."""

import inspect
import re
from itertools import pairwise

from django.test import Client, TestCase
from django.urls import reverse

from screening.models import User
from screening.tests import test_family_zone, test_pages
from screening.views import family

CHECK_FIRST = "可以先檢查"
SEE_AUDIOLOGIST = "該回去找聽力師"
URGENT_LINK = "/family#urgent-title"
# Words of batch-3-wording.md section 1, written out so a slip in the definition shows.
PROBLEMS = {
    "沒聲音或變小聲": {
        CHECK_FIRST: [
            "有沒有戴好、有沒有開機；有音量鍵的話，音量是不是太小。",
            "電池有沒有裝對方向、貼紙撕了沒。不確定就換一顆新的；充電式的看有沒有充飽。",
            "耳模或耳塞有沒有被耳垢或水氣堵住，導管有沒有折到或堵住。",
        ],
        SEE_AUDIOLOGIST: [
            "檢查完還是沒聲音，或聲音變形。",
            "覺得他的聽力變了，助聽器需要調整。",
        ],
    },
    "一直嘯叫": {
        CHECK_FIRST: [
            "有沒有戴好，耳朵和助聽器之間有沒有縫。",
            "帽子、圍巾或耳機有沒有蓋到助聽器。",
            "耳模或耳塞有沒有太鬆或破損，導管有沒有裂開。",
            "有音量鍵的話，可以先暫時調小。",
        ],
        SEE_AUDIOLOGIST: [
            "檢查完還是一直叫，或耳模已經鬆了。",
            "耳朵裡可能有很多耳垢：不要自己挖，請耳鼻喉科或聽力師看看。",
        ],
    },
    "太吵或聲音太大": {
        CHECK_FIRST: [
            "是不是剛開始戴。前幾週可能覺得環境很吵、自己的聲音怪怪的，要時間適應。",
            "有音量鍵的話，音量是不是太大。",
        ],
        SEE_AUDIOLOGIST: [
            "太吵、太小聲或不舒服，都可以請聽力師調整，不用勉強忍耐。",
            "助聽器沒辦法把想聽和不想聽的聲音完全分開。記下哪些場合最困擾，回診時告訴聽力師。",
        ],
    },
    "有嗡嗡聲": {
        CHECK_FIRST: [
            "關機再開機，回到平常的設定。可能是不小心切到感應線圈（T）的設定。",
        ],
        SEE_AUDIOLOGIST: [
            "開關機之後還有雜音，或聲音變形。",
        ],
    },
    "戴起來會磨、會緊": {
        CHECK_FIRST: [
            "有沒有戴對位置、左右耳有沒有戴反。",
        ],
        SEE_AUDIOLOGIST: [
            "戴對了還是不舒服。耳模或耳塞通常可以調整，不用硬撐。",
            "如果是耳朵痛或流膿，請選第一項。",
        ],
    },
}
EAR_TROUBLE = "耳朵痛、流膿或突然聽不到"
SEE_A_DOCTOR = "不用先檢查助聽器，請盡快到耳鼻喉科就醫。"
# Common makers' names, so none slips in from a source or a how-to.
BRANDS = (
    "Phonak",
    "Oticon",
    "Signia",
    "Widex",
    "ReSound",
    "Starkey",
    "Unitron",
    "Bernafon",
    "Sonic",
    "Rexton",
    "Hansaton",
)


class FamilyHearingAidsTests(test_family_zone.SignsInWithARecord, TestCase):
    def setUp(self):
        self.url = reverse("family_hearing_aids")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.content = response.content.decode()
        self.main = test_family_zone._main(self.content)

    def test_address_is_family_hearing_aids(self):
        self.assertEqual(self.url, "/family/hearing-aids")

    def test_page_has_one_heading_its_title_and_the_learn_tab(self):
        self.assertEqual(re.findall(r"<h1[^>]*>([^<]*)</h1>", self.content), ["助聽器"])
        self.assertRegex(self.content, r"<title>\s*助聽器｜聽伴\s*</title>")  # noqa: RUF001
        nav = test_pages.RedesignLayoutTests.NAV.search(self.content).group()
        self.assertEqual(
            re.findall(r'aria-current="page"[^>]*>.*?<span>([^<]+)</span>', nav, re.S),
            ["了解"],
        )

    def _options(self):
        """{label: the HTML under it} for each option's explanation, as the server sends them."""
        start = self.main.index("data-pick-explanations")
        explanations = self.main[start : self.main.index("data-pick-live", start)]
        chunks = explanations.split('<strong class="tint-subhead block">')[1:]
        return {chunk.split("</strong>")[0]: chunk.split("</strong>", 1)[1] for chunk in chunks}

    def _groups(self, chunk):
        """{group title: its lines} for the groups in an option's HTML."""
        groups = re.findall(r"<h3[^>]*>([^<]+)</h3>\s*<ul[^>]*>(.*?)</ul>", chunk, re.S)
        return {title: re.findall(r"<li>([^<]+)</li>", lines) for title, lines in groups}

    # The one to see a doctor comes first, so no one spends time checking the aid before it.
    def test_the_question_and_its_options_with_the_urgent_one_first(self):
        self.assertIn("現在是什麼狀況？", self.main)
        self.assertEqual(
            re.findall(
                r'<input type="radio" name="hearing-aid-problem"><span>([^<]+)</span>', self.main
            ),
            [EAR_TROUBLE, *PROBLEMS],
        )

    def test_each_problem_has_things_to_check_and_when_to_see_the_audiologist(self):
        options = self._options()
        for label, groups in PROBLEMS.items():
            with self.subTest(label=label):
                self.assertEqual(self._groups(options[label]), groups)

    # Acceptance 31: no checking first; the doctor, in bold, and where /family says when.
    def test_ear_trouble_sends_them_to_a_doctor_with_nothing_to_check(self):
        chunk = self._options()[EAR_TROUBLE]
        self.assertIn(f"<strong>{SEE_A_DOCTOR}</strong>", chunk)
        self.assertRegex(
            chunk,
            rf'<a [^>]*href="{URGENT_LINK}"[^>]*>.*?什麼時候要馬上就醫.*?</a>',
        )
        self.assertEqual(self._groups(chunk), {})
        self.assertNotIn(CHECK_FIRST, chunk)
        self.assertNotIn(SEE_AUDIOLOGIST, chunk)

    # Even with the aid working, sudden loss is a doctor's: the same place, from this option too.
    def test_no_sound_also_points_to_when_to_see_a_doctor(self):
        chunk = self._options()["沒聲音或變小聲"]
        self.assertRegex(
            chunk,
            rf'<a [^>]*href="{URGENT_LINK}"[^>]*>.*?'
            r"另外：助聽器都正常，他還是突然聽不到，請看「什麼時候要馬上就醫」。.*?</a>",
        )

    def test_the_urgent_link_lands_on_its_section(self):
        path, _, anchor = URGENT_LINK.partition("#")
        self.assertContains(self.client.get(path), f'<h2 id="{anchor}"')

    def test_reminds_that_makers_differ(self):
        self.assertIn(
            "各廠牌的按鍵、電池和清潔工具不一樣，操作請看說明書或問聽力師。",
            re.sub(r"<[^>]+>", "", self.main),
        )

    # Whole page, ignoring case: only general words, on no maker's terms.
    def test_no_brand_names_anywhere_on_the_page(self):
        for brand in BRANDS:
            with self.subTest(brand=brand):
                self.assertNotIn(brand.lower(), self.content.lower())

    # Acceptance 35: types and prices are the guide's. Linked, not repeated here.
    def test_types_and_prices_link_to_the_guide_with_no_amount_or_law(self):
        chapter = reverse("guide_chapter", args=["types-and-prices"])
        self.assertRegex(
            self.main,
            rf'看選配指引的<a [^>]*href="{chapter}"[^>]*>「外型與價格」</a>。',
        )
        self.assertEqual(self.client.get(chapter).status_code, 200)
        self.assertNotRegex(re.sub(r"<[^>]+>", "", self.main), r"[\d,一二三四五六七八九十百千萬]元")
        self.assertNotIn("法規", self.main)
        self.assertNotIn("補助", self.main)

    # The jump list has this ticket's one section: #434 and #435 add theirs.
    def test_jump_link_lands_on_the_section(self):
        self.assertRegex(
            self.main,
            r'(?s)<a [^>]*href="#problems-title"[^>]*>.*?助聽器怪怪的.*?</a>',
        )
        self.assertRegex(self.main, r'<h2 id="problems-title"[^>]*>助聽器怪怪的</h2>')
        self.assertLess(self.main.index('href="#problems-title"'), self.main.index("<h2"))

    def test_foot_has_sources_and_checked_date(self):
        foot = self.main[self.main.index('id="sources-title"') :]
        self.assertIn("內容查核於 2026/11/06。", foot)
        self.assertEqual(
            re.findall(r'<li><a href="([^"]+)">([^<]+)</a></li>', foot),
            [
                (
                    "https://rnid.org.uk/information-and-support/hearing-aids/"
                    "solving-common-problems/",
                    "RNID：Solving common hearing aid problems（2026/06/02 更新）",
                ),
                (
                    "https://rnid.org.uk/information-and-support/hearing-aids/cleaning-maintaining/",
                    "RNID：Cleaning and maintaining your hearing aids（2026/06/01 更新）",
                ),
                (
                    "https://www.nidcd.nih.gov/health/hearing-aids",
                    "NIDCD：Hearing Aids（2022/10/11 更新）",
                ),
                (
                    "https://www.fda.gov/medical-devices/hearing-aids/"
                    "hearing-aid-benefits-and-limitations",
                    "FDA：Hearing Aid Benefits and Limitations（2022/11/18 更新）",
                ),
                (
                    "https://www.cuh.nhs.uk/patient-information/nhs-hearing-aids-problem-solving/",
                    "Cambridge University Hospitals：NHS hearing aids problem solving"
                    "（2025/04/15 核定）",
                ),
                (
                    "https://www.hampshirehospitals.nhs.uk/our-services/"
                    "az-departments-and-specialties/audiology-1/adult-services/"
                    "hearing-aid-troubleshooting-guide",
                    "Hampshire Hospitals：Hearing Aid Troubleshooting Guide（沒有標日期）",
                ),
                ("/guide/after-fitting", "聽伴選配指引「配戴之後」的審定內容"),
                ("/family", "家人專區的審定內容"),
            ],
        )

    # The reviewed pages the sources name, and every other link of ours on the page, open.
    def test_every_link_of_ours_opens(self):
        for href in set(re.findall(r'<a [^>]*href="(/[^"#]*)', self.main)):
            with self.subTest(href=href):
                self.assertEqual(self.client.get(href).status_code, 200)

    def test_way_back_to_the_zone(self):
        self.assertRegex(self.main, r'<a [^>]*href="/family"[^>]*>回到家人專區</a>')

    def test_headings_never_skip_a_level(self):
        levels = [int(level) for level in re.findall(r"<h([1-6])[\s>]", self.main)]
        self.assertEqual(levels[0], 1)
        for previous, level in pairwise(levels):
            self.assertLessEqual(level, previous + 1)

    def test_signed_in_user_gets_the_same_page_without_their_data(self):
        self.sign_in_with_a_record("aids_private")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # A visitor's page, fetched now: signing in loaded the questionnaires its survey link needs.
        visitor = Client().get(self.url).content.decode()
        self.assertEqual(test_family_zone._main(content), test_family_zone._main(visitor))
        self.assert_shows_no_record(content, "aids_private")

    def test_user_without_consent_can_read_it(self):
        self.client.force_login(User.objects.create_user(username="aids_old"))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    # Reads no one's data, so it can stay public: nothing in the view touches request.user.
    def test_view_never_reads_the_user(self):
        source = inspect.getsource(family.family_hearing_aids)
        self.assertNotIn("request.user", source)
        self.assertNotIn("login_required", source)
