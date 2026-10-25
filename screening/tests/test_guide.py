import re
from itertools import pairwise

from django.test import TestCase
from django.urls import reverse

from screening.models import AidAndSubsidy, User
from screening.tests.helpers import consented_user
from screening.views import GUIDE_CHAPTERS

# Wording finalised in #220 (draft comment and its follow-up).
TITLE = "我的選配指引"
LOGIN_NOTE = (
    "登入後，這裡會依您的問卷和聽力圖，整理出要不要找聽力師評估，"
    "以及有沒有達到身障鑑定門檻。下面的章節不用登入也能看。"
)
CONTENTS_TITLE = "選配與補助，一步一步看"
CHAPTERS = (
    "去找聽力師之前",
    "身障鑑定與鑑定醫院",
    "九號表：申請助聽器補助",
    "助聽器的種類與價格",
    # Verification-flow batch F5: in the order they happen, the first weeks before 1-3 months.
    "配戴助聽器之後",
    "二十五號表：使用效益驗證",
)
BACK = "回到我的選配指引"
# Shortened in the guide chapters tidy-up (2026-10-23, the owner's request): things to bring
# as chips, the questions grouped under three labels.
BEFORE_YOU_GO = (
    "第一次去評估選配助聽器，先準備好下面這些，可以少跑一趟。",
    "要帶的東西",
    "醫院的聽力檢查報告（聽力圖）",
    "身分證",
    "身心障礙證明（有的話）",
    "現在用的助聽器（有的話）",
    "也可以在 HearWell 印出聽力報告一起帶去。",
    "要申請身障補助，一定要有身心障礙證明。",
    "可以問聽力師的問題",
    "適不適合我",
    "我適合哪一種助聽器？為什麼？",
    "可以先試戴嗎？試戴多久？要收費嗎？",
    "價格與保固",
    "價格包含哪些服務？之後回來調整要另外收費嗎？",
    "保固多久？包含哪些？",
    "可以給我書面的報價單和保固內容嗎？",
    "補助 這一台是補助的哪一個等級（簡易型、中階型、進階型、雙對側傳聲型）？",
    "可以幫我開九號表嗎？",
    "提醒：要申請身障補助，一定要先拿到核定通知再買，沒核定就先買的不補助。",
)
BEFORE_YOU_GO_SOURCES = (
    (
        "身心障礙者輔具費用補助辦法",
        "https://law.moj.gov.tw/LawClass/LawAll.aspx?PCODE=D0050060",
    ),
    (
        "身心障礙者輔具費用補助基準表",
        "https://law.moj.gov.tw/LawClass/LawGetFile.ashx?FileId=0000326887&amp;lan=C",
    ),
)


def text_of(response):
    """The page's visible text in <main>, tags removed, so wording can be matched as written."""
    content = response.content.decode()
    main = content[content.index("<main") : content.index("</main>")]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", main))


def assert_footer(testcase, response, checked_on, sources):
    """The footer every chapter shares: its check date and each (wording, url) source."""
    content = response.content.decode()
    footer = content[content.index("<footer") : content.index("</footer>")]
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", footer))
    testcase.assertIn(f"本頁資料查核於 {checked_on}。法規、金額如有變動，以官方公告為準。", text)
    # Text-heavy pages tidy-up: the sources sit behind a 「資料來源」 dropdown box.
    testcase.assertIn('<details class="dropdown-box mb-2">', footer)
    testcase.assertIn("<summary>資料來源</summary>", footer)
    for wording, url in sources:
        with testcase.subTest(url=url):
            testcase.assertIn(f'href="{url}"', footer)
            testcase.assertIn(wording, text)


def part(response, title):
    """The HTML of the part (a section named by its h2) titled title, as a screen reader finds
    it: a region whose aria-labelledby is that heading."""
    content = response.content.decode()
    for match in re.finditer(
        r'<section[^>]*aria-labelledby="([^"]+)"[^>]*>(.*?)</section>', content, re.DOTALL
    ):
        heading = re.search(rf'<h2 id="{match[1]}"[^>]*>(.*?)</h2>', match[2], re.DOTALL)
        if heading and heading[1].strip() == title:
            return match[2]
    raise AssertionError(f"No part titled {title}")


def heading_levels(response):
    """The level of every heading in <main>, in order."""
    content = response.content.decode()
    main = content[content.index("<main") : content.index("</main>")]
    return [int(level) for level in re.findall(r"<h([1-6])[\s>]", main)]


def assert_levels_without_skipping(testcase, levels):
    """levels open with the one first-level heading and never skip a level going down."""
    testcase.assertEqual(levels[0], 1)
    testcase.assertEqual(levels.count(1), 1)
    for above, below in pairwise(levels):
        testcase.assertLessEqual(below, above + 1, levels)


class GuideContentsTests(TestCase):
    """#221: the contents page of the hearing-aid guide."""

    def setUp(self):
        self.url = reverse("guide")

    def test_logged_out_visitor_sees_the_contents_and_the_login_note(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(f'<h1 class="h3 mt-4">{TITLE}</h1>', content)
        self.assertIn(LOGIN_NOTE, content)
        self.assertIn(CONTENTS_TITLE, content)
        positions = [content.index(title) for title in CHAPTERS]
        self.assertEqual(positions, sorted(positions))

    def test_logged_in_user_sees_the_contents_without_the_login_note(self):
        self.client.force_login(consented_user(username="guide_reader"))
        content = self.client.get(self.url).content.decode()
        self.assertIn(CONTENTS_TITLE, content)
        self.assertNotIn(LOGIN_NOTE, content)

    def test_every_chapter_is_linked(self):
        content = self.client.get(self.url).content.decode()
        for chapter in GUIDE_CHAPTERS:
            href = f'href="{reverse("guide_chapter", args=[chapter.slug])}"'
            with self.subTest(chapter=chapter.slug):
                self.assertIn(href, content)


class GuideChapterTests(TestCase):
    """#221: a chapter page, with the footer every chapter shares."""

    def setUp(self):
        self.url = reverse("guide_chapter", args=["before-you-go"])

    def test_before_you_go_is_open_without_logging_in(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>去找聽力師之前\uff5cHearWell</title>")
        self.assertContains(response, '<h1 class="h3 mt-4">去找聽力師之前</h1>')
        text = text_of(response)
        positions = [text.index(sentence) for sentence in BEFORE_YOU_GO]
        self.assertEqual(positions, sorted(positions))

    def test_footer_has_the_check_date_and_official_sources(self):
        response = self.client.get(self.url)
        assert_footer(self, response, "2026/10/22", BEFORE_YOU_GO_SOURCES)
        self.assertContains(response, f'href="{reverse("guide")}">{BACK}</a>')

    def test_user_without_consent_can_read_it(self):
        self.client.force_login(User.objects.create_user(username="guide_old"))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    # #319 (#318 acceptance 11): each chapter's title is the one first-level heading and its parts
    # second-level ones, the stop's question at the foot included; no level is skipped.
    def test_every_chapter_titles_its_parts_one_level_below_without_skipping(self):
        for signed_in in (False, True):
            if signed_in:
                self.client.force_login(consented_user(username="guide_levels"))
            for chapter in GUIDE_CHAPTERS:
                with self.subTest(chapter=chapter.slug, signed_in=signed_in):
                    url = reverse("guide_chapter", args=[chapter.slug])
                    levels = heading_levels(self.client.get(url))
                    assert_levels_without_skipping(self, levels)
                    self.assertIn(2, levels)

    def test_unknown_chapter_is_not_found(self):
        url = reverse("guide_chapter", args=["no-such-chapter"])
        self.assertEqual(self.client.get(url).status_code, 404)


class ChapterTidyT367Tests(TestCase):
    """#367 (spec #354): the chapters' way back to the guide and their own small fixes."""

    BACK_BUTTON = f'<a class="btn btn-outline-primary btn-lg w-full" href="/guide">{BACK}</a>'

    def chapter(self, slug, **query):
        return self.client.get(reverse("guide_chapter", args=[slug]), query).content.decode()

    def test_a_chapter_without_an_answer_ends_with_the_way_back_before_its_sources(self):
        signed_in = consented_user(username="chapter_back_user")
        for user in (None, signed_in):
            if user:
                self.client.force_login(user)
            for chapter in GUIDE_CHAPTERS:
                with self.subTest(chapter=chapter.slug, signed_in=bool(user)):
                    content = self.chapter(chapter.slug)
                    self.assertEqual(content.count(self.BACK_BUTTON), 1)
                    at = content.index(self.BACK_BUTTON)
                    self.assertGreater(at, content.index("</article>"))
                    self.assertLess(at, content.index("<footer"))
                    if 'id="stop-question"' in content:
                        self.assertGreater(at, content.index('id="stop-question"'))

    def test_an_answered_chapter_leads_back_by_its_card_only(self):
        user = consented_user(username="chapter_back_answered")
        AidAndSubsidy.objects.create(user=user, certificate="yes")
        self.client.force_login(user)
        content = self.chapter("assessment")
        self.assertIn("已記下：有身障證明", content)
        self.assertNotIn(self.BACK_BUTTON, content)

    def test_before_you_go_links_the_report_from_its_printing_sentence(self):
        bring = part(
            self.client.get(reverse("guide_chapter", args=["before-you-go"])), "要帶的東西"
        )
        self.assertIn(
            "<p>也可以在 HearWell 印出聽力報告一起帶去。"
            f'<a href="{reverse("health_report")}">看／印聽力報告</a></p>',
            bring,
        )

    def test_form_9_opens_with_a_jump_to_each_of_its_six_parts(self):
        content = self.chapter("form-9")
        nav = re.search(r'<nav aria-labelledby="page-jump-title">(.*?)</nav>', content, re.S)
        self.assertIsNotNone(nav)
        self.assertIn('<p id="page-jump-title" class="tint-subhead mb-2">本頁段落</p>', nav[1])
        links = re.findall(r'<a [^>]*href="#([^"]+)">([^<]+)</a>', nav[1])
        self.assertEqual(
            links,
            [
                ("who-title", "誰可以申請"),
                ("steps-title", "申請流程"),
                ("issuer-title", "九號表找誰開"),
                ("amount-title", "補助多少"),
                ("reapply", "再次申請（換新機）"),
                ("without-certificate", "沒有身障證明時"),
            ],
        )
        for target, _ in links:
            with self.subTest(target=target):
                self.assertIn(f'id="{target}"', content)
        # Under the lead, before the first part.
        lead = content.index("「九號表」是買助聽器前要做的輔具評估報告書")
        self.assertLess(lead, nav.start())
        self.assertLess(nav.end(), content.index('<section class="section-box'))

    def test_form_25_tags_its_when_as_form_9_does(self):
        who_how = part(
            self.client.get(reverse("guide_chapter", args=["form-25"])), "誰要做、怎麼做"
        )
        self.assertIn(
            '<dd>配戴滿 1 個月後、3 個月內。<span class="step-when" aria-hidden="true">'
            "配戴 1–3 個月內</span></dd>",
            who_how,
        )
