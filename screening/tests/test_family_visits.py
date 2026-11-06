"""#430 (spec #426): 陪診與代辦's checklist, as the server sends it. Ticking, reloading and printing
it in a real browser are in e2e.main_flow.FamilyVisitsTest."""

import inspect
import re
from itertools import pairwise

from django.test import TestCase
from django.urls import reverse

from screening.models import Submission, User
from screening.tests import test_family_zone, test_pages
from screening.views import family


class FamilyVisitsTests(test_family_zone.SignsInWithARecord, TestCase):
    def setUp(self):
        self.url = reverse("family_visits")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.content = response.content.decode()
        self.main = test_family_zone._main(self.content)

    def test_address_is_family_visits(self):
        self.assertEqual(self.url, "/family/visits")

    def test_page_has_one_heading_its_title_and_the_learn_tab(self):
        self.assertEqual(re.findall(r"<h1[^>]*>([^<]*)</h1>", self.content), ["陪診與代辦"])
        self.assertRegex(self.content, r"<title>\s*陪診與代辦｜聽伴\s*</title>")  # noqa: RUF001
        nav = test_pages.RedesignLayoutTests.NAV.search(self.content).group()
        self.assertEqual(
            re.findall(r'aria-current="page"[^>]*>.*?<span>([^<]+)</span>', nav, re.S),
            ["了解"],
        )

    def _checkbox_words(self, group):
        return re.findall(
            r'<label class="visit-check"><input type="checkbox" autocomplete="off">'
            r"<span>([^<]+)</span></label>",
            group,
        )

    def _groups(self):
        """{legend: the words of the checkboxes directly under it} for each fieldset on the page."""
        groups = {}
        for chunk in self.main.split("<legend")[1:]:
            legend = re.search(r">([^<]+)</legend>", chunk).group(1)
            groups[legend] = self._checkbox_words(chunk.split("<fieldset")[0])
        return groups

    # Words of batch-2-wording.md section 1, written out so a slip in the definition shows.
    def test_every_item_is_a_checkbox_in_its_named_group(self):
        self.assertEqual(
            self._groups(),
            {
                "要帶的東西": [
                    "醫院的聽力檢查報告（聽力圖）",
                    "身分證",
                    "身心障礙證明（有的話）",
                    "現在用的助聽器（有的話）",
                    "聽伴印的聽力報告（有的話）",
                ],
                "想問聽力師的問題": [],
                "適不適合": [
                    "哪一種助聽器適合他？為什麼？",
                    "可以先試戴嗎？試戴多久？要收費嗎？",
                ],
                "價格與保固": [
                    "價格包含哪些服務？之後回來調整要另外收費嗎？",
                    "保固多久？包含哪些？",
                    "可以給我們書面的報價單和保固內容嗎？",
                ],
                "補助": [
                    "這一台是補助的哪一個等級（簡易型、中階型、進階型、雙對側傳聲型）？",
                    "可以幫他開九號表嗎？",
                ],
            },
        )
        self.assertEqual(self.main.count("<fieldset"), 5)
        self.assertEqual(self.main.count('type="checkbox"'), 12)

    # No ticking is ever sent: nothing to submit, and no script on the page of its own.
    # Ticks cannot be sent anywhere; the one script beyond the layout's only opens printing.
    def test_no_form_and_only_the_print_script_of_its_own(self):
        self.assertNotIn("<form", self.main)
        self.assertNotIn(" name=", self.main)
        self.assertNotIn("<script", self.main)
        layout = self.client.get(reverse("privacy")).content.decode()
        scripts = re.compile(r"<script[^>]*\ssrc=\"([^\"]+)\"")
        extra = set(scripts.findall(self.content)) - set(scripts.findall(layout))
        self.assertEqual(len(extra), 1)
        self.assertIn("screening/print-button.js", extra.pop())

    def test_intro_reminder_and_section_heading(self):
        text = re.sub(r"<[^>]+>", "", self.main)
        self.assertRegex(self.main, r"<h2[^>]*>陪診清單</h2>")
        self.assertIn("勾選不會留下，可以列印帶去。", text)
        self.assertIn(
            "要申請身障補助，一定要先拿到核定通知再買，沒核定就先買的不補助。",
            text,
        )

    # 文字同指引: the things to bring (but the one split out of a sentence), the reminder and the
    # sources are the chapter's own, which stays as it was.
    def test_words_and_sources_match_the_guide_chapter(self):
        response = self.client.get(reverse("guide_chapter", args=["before-you-go"]))
        chapter = response.content.decode()
        for words in (
            "醫院的聽力檢查報告（聽力圖）",
            "身分證",
            "身心障礙證明（有的話）",
            "現在用的助聽器（有的話）",
            "要申請身障補助，一定要先拿到核定通知再買，沒核定就先買的不補助。",
            "查核於 2026/10/22",
        ):
            with self.subTest(words=words):
                self.assertIn(words, chapter)
                self.assertIn(words, self.main)
        self.assertNotRegex(chapter, r"聽伴印的聽力報告|適合他|幫他開")
        for url in (
            "https://law.moj.gov.tw/LawClass/LawAll.aspx?PCODE=D0050060",
            "https://law.moj.gov.tw/LawClass/LawGetFile.ashx?FileId=0000326887&amp;lan=C",
        ):
            with self.subTest(url=url):
                self.assertIn(f'<a href="{url}">', chapter)
                self.assertIn(f'<a href="{url}">', self.main)

    # The reminder's link as the chapter words it; the way back to the zone at the foot.
    def test_links_are_the_reminder_and_the_way_back_and_none_needs_an_account(self):
        self.assertRegex(self.main, r'<a [^>]*href="/guide/form-9"[^>]*>看九號表的流程</a>')
        self.assertRegex(self.main, r'<a [^>]*href="/family"[^>]*>回到家人專區</a>')
        self.assertNotIn(reverse("health_report"), self.main)
        for href in re.findall(r'<a [^>]*href="(/[^"#]*)', self.main):
            with self.subTest(href=href):
                self.assertEqual(self.client.get(href).status_code, 200)

    def test_headings_never_skip_a_level(self):
        levels = [int(level) for level in re.findall(r"<h([1-6])[\s>]", self.main)]
        self.assertEqual(levels[0], 1)
        for previous, level in pairwise(levels):
            self.assertLessEqual(level, previous + 1)

    def test_foot_has_sources_and_checked_date(self):
        foot = self.main[self.main.index('id="sources-title"') :]
        self.assertIn("內容查核於 2026/10/22。", foot)
        self.assertIn("身心障礙者輔具費用補助辦法", foot)
        self.assertIn("身心障礙者輔具費用補助基準表", foot)

    def test_signed_in_user_gets_the_same_page_without_their_data(self):
        self.sign_in_with_a_record("visits_private")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(test_family_zone._main(content), self.main)
        self.assert_shows_no_record(content, "visits_private")

    def test_user_without_consent_can_read_it(self):
        self.client.force_login(User.objects.create_user(username="visits_old"))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    # Reads no one's data, so it can stay public: nothing in the view touches request.user.
    def test_view_never_reads_the_user(self):
        source = inspect.getsource(family.family_visits)
        self.assertNotIn("request.user", source)
        self.assertNotIn("login_required", source)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    # On a shared phone, 上一頁 should not bring back someone else's ticks (owner, 2026-11-06).
    def test_the_response_is_never_stored(self):
        self.assertIn("no-store", self.client.get(self.url).get("Cache-Control", ""))

    def test_print_button_uses_the_report_script_and_stays_off_the_paper(self):
        self.assertRegex(
            self.main,
            r'<p class="[^"]*no-print[^"]*">\s*'
            r'<button id="print-button" type="button"[^>]*>列印或存成 PDF</button>',
        )
        self.assertIn("screening/print-button.js", self.content)

    def test_viewing_it_writes_nothing_and_sets_no_cookie(self):
        before = (Submission.objects.count(), User.objects.count())
        response = self.client.get(self.url)
        self.assertEqual((Submission.objects.count(), User.objects.count()), before)
        self.assertEqual(len(response.cookies), 0)


class FamilyVisitsEntryTests(TestCase):
    """The zone's home page leads to the checklist, with the owner's words."""

    def test_zone_home_links_to_the_visits_page(self):
        content = self.client.get(reverse("family_guide")).content.decode()
        start = content.index('aria-label="專區內容"')
        entries = content[start : content.index("</nav>", start)]
        self.assertIn(
            (
                "/family/visits",
                "clipboard",
                "陪診與代辦",
                "要帶什麼、想問什麼、補助還缺什麼、期限到哪天",
            ),
            test_family_zone.ENTRY.findall(entries),
        )
