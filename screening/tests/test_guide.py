import re

from django.test import TestCase
from django.urls import reverse

from screening.models import User
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
    "二十五號表：使用效益驗證",
    "配戴助聽器之後",
)
BACK = "回到我的選配指引"
BEFORE_YOU_GO = (
    "第一次去評估選配助聽器時，先準備好下面的東西和問題，可以少跑一趟，也比較知道要問什麼。",
    "要帶的東西",
    "醫院給的聽力檢查報告（聽力圖）。也可以在 HearWell 印出聽力報告帶去。",
    "身分證。",
    "身心障礙證明（有的話）。要申請身障補助，一定要有證明。",
    "現在在用的助聽器（有的話）。",
    "可以問聽力師的問題",
    "我適合哪一種助聽器？為什麼？",
    "可以先試戴嗎？可以試戴多久？試戴要收費嗎？",
    "價格包含哪些服務？之後回來調整要另外收費嗎？",
    "保固多久？保固包含哪些？",
    "這一台屬於補助的哪一個等級（簡易型、中階型、進階型、雙對側傳聲型）？",
    "我要申請補助，可以幫我開九號表嗎？",
    "可以給我書面的報價單和保固內容嗎？",
    "提醒：要申請身障補助的話，一定要先拿到核定通知再買，沒核定就先買的不補助。",
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
    testcase.assertIn('<details class="phone-choice mb-2">', footer)
    testcase.assertIn("<summary>資料來源</summary>", footer)
    for wording, url in sources:
        with testcase.subTest(url=url):
            testcase.assertIn(f'href="{url}"', footer)
            testcase.assertIn(wording, text)


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
        assert_footer(self, response, "2026-10-22", BEFORE_YOU_GO_SOURCES)
        self.assertContains(response, f'href="{reverse("guide")}">{BACK}</a>')

    def test_user_without_consent_can_read_it(self):
        self.client.force_login(User.objects.create_user(username="guide_old"))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_unknown_chapter_is_not_found(self):
        url = reverse("guide_chapter", args=["no-such-chapter"])
        self.assertEqual(self.client.get(url).status_code, 404)
