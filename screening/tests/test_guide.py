import re
from itertools import pairwise

from django.test import TestCase
from django.urls import reverse

from screening.models import AidAndSubsidy, User
from screening.tests.helpers import consented_user
from screening.views.guide import GUIDE_CHAPTERS

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
# as chips, the questions grouped under three labels. #467 (H2): the parts titled as questions,
# the first question in sight before its group.
BEFORE_YOU_GO = (
    "第一次去評估選配助聽器，先準備好下面這些，可以少跑一趟。",
    "要帶什麼去？",
    "醫院的聽力檢查報告（聽力圖）",
    "身分證",
    "身心障礙證明（有的話）",
    "現在用的助聽器（有的話）",
    "也可以在聽伴印出聽力報告一起帶去。",
    "要申請身障補助，一定要有身心障礙證明。",
    "可以問聽力師什麼？",
    "我適合哪一種助聽器？為什麼？",
    "適不適合我",
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


def article_text(response):
    """text_of without the key cards at a chapter's start (#467, H1): they repeat sentences of
    the parts below, so the parts' wording is read in order after them."""
    content = response.content.decode()
    content = re.sub(r'<ul class="key-cards".*?</ul>', "", content, flags=re.S)
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
        self.assertContains(response, "<title>去找聽力師之前\uff5c聽伴</title>")
        self.assertContains(response, '<h1 class="h3 mt-4">去找聽力師之前</h1>')
        text = article_text(response)
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
            self.client.get(reverse("guide_chapter", args=["before-you-go"])), "要帶什麼去？"
        )
        self.assertIn(
            "<p>也可以在聽伴印出聽力報告一起帶去。"
            f'<a href="{reverse("health_report")}">看／印聽力報告</a></p>',
            bring,
        )

    def test_form_25_tags_its_when_as_form_9_does(self):
        who_how = part(
            self.client.get(reverse("guide_chapter", args=["form-25"])), "誰要做？什麼時候做？"
        )
        self.assertIn(
            '<dd>配戴滿 1 個月後、3 個月內。<span class="step-when" aria-hidden="true">'
            "配戴 1–3 個月內</span></dd>",
            who_how,
        )
