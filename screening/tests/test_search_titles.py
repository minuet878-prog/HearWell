"""Each 公開頁面's title and description in search results (spec #583, ticket #589), in the words
the owner confirmed row by row in the titles table (#587)."""

import html
import re
from dataclasses import fields
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from screening.qa_assistant import content

TABLE = Path(settings.BASE_DIR) / "docs/planning/found-by-family/search-basics-titles.md"
UNCHANGED = "（不改）"


def table_rows():
    """The table's rows as lists of cells, the row's key (A1, D6…) first."""
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        if re.match(r"\| [A-E]\d+ \|", line):
            yield [cell.strip() for cell in line.strip("|").split("|")]


def confirmed_pages():
    """{path: (title, description)} for each page row with an address; an unchanged title is the
    current one. Rows the owner confirmed only: 可 in the last cell."""
    pages = {}
    for _key, address, current, title, description, status in (
        row for row in table_rows() if len(row) == 6
    ):
        if address.startswith("`") and status == "可" and description != "—":
            pages[address.strip("`")] = (current if title == UNCHANGED else title, description)
    return pages


def head_of(response):
    """(title, meta description or None) of a page."""
    content = response.content.decode()
    title = re.search(r"<title>\s*(.*?)\s*</title>", content, re.S).group(1)
    description = re.search(r'<meta name="description" content="([^"]*)">', content)
    return html.unescape(title), description and html.unescape(description.group(1))


class ConfirmedWordingTests(TestCase):
    def test_each_page_in_the_table_shows_the_confirmed_title_and_description(self):
        # Spec #583 acceptance 14.
        pages = confirmed_pages()
        # A1–A5 (A5: spec #633), B1–B10 (B8–B10: spec #655), C1–C7, D1, D3–D5.
        self.assertEqual(len(pages), 26)
        for path, (title, description) in pages.items():
            with self.subTest(path=path):
                self.assertEqual(head_of(self.client.get(path)), (title, description))

    def test_each_answer_shows_its_question_and_the_confirmed_description(self):
        # Spec #583 acceptance 16: the title is the question and 聽伴, the description its sentence.
        descriptions = {
            question: description
            for key, question, description, status in (row for row in table_rows() if len(row) == 4)
            if key.startswith("D") and status == "可"
        }
        self.assertEqual(len(descriptions), len(content.FAQS))
        for faq in content.FAQS:
            with self.subTest(code=faq.code):
                shown = head_of(self.client.get(reverse("qa_answer", args=[faq.code])))
                title = f"{faq.question}｜聽伴"  # noqa: RUF001
                self.assertEqual(shown, (title, descriptions[faq.question]))

    def test_a_question_without_a_description_cannot_be_written(self):
        # A new question must say its description: leaving it out stops the site from starting.
        written = {
            field.name: getattr(content.FAQS[0], field.name) for field in fields(content.Faq)
        }
        del written["description"]
        with self.assertRaises(TypeError):
            content.Faq(**written)

    def test_the_home_page_says_screening_not_testing(self):
        # Spec #583 acceptance 18 (grill Q10): the home page asks questions, it is no hearing test.
        title, description = head_of(self.client.get(reverse("index")))
        for word in ("檢測", "測驗", "測試"):
            with self.subTest(word=word):
                self.assertNotIn(word, title + description)


class PageHeadingTests(TestCase):
    """Spec #583 acceptance 15: only the title in the head changes; each page's heading stays."""

    def test_the_big_headings_are_the_ones_before(self):
        headings = {
            # Spec #655 (#673): the visitor's home is two doors; #749 (the canvas's ProGuest)
            # put its heading in the bird's bubble.
            "/": "聽力變化常常容易被忽略",
            "/learn": "了解",
            "/learn/simulator": "聽損模擬",
            "/privacy": "隱私權說明",
            "/family": "家人專區",
            "/family/talk": "怎麼跟聽損的家人說話",
            "/family/reluctant": "長輩不肯去怎麼說",
            "/family/hearing-aids": "助聽器",
            "/family/visits": "陪診與代辦",
            "/family/visits/subsidy": "補助檢核",
            "/family/visits/deadlines": "期限試算",
            # Spec #655 (#675): the three family pages' own headings (#671).
            "/family/signs": "怎麼知道爸媽的聽力變差了",
            "/family/loud-tv": "爸媽看電視開很大聲，怎麼辦？",
            "/family/huh": "跟他講話，他一直說「蛤」？",
            "/guide": "助聽器選配與補助",
            "/guide/before-you-go": "去找聽力師之前",
            "/guide/assessment": "身障鑑定與鑑定醫院",
            "/guide/form-9": "九號表：申請助聽器補助",
            "/guide/types-and-prices": "助聽器的種類與價格",
            "/guide/after-fitting": "配戴助聽器之後",
            "/guide/form-25": "二十五號表：使用效益驗證",
            "/qa": "問答小助手",
            "/qa/topic/questionnaires": "問卷是什麼",
            "/qa/topic/hearing-aids": "助聽器選配與補助",
            "/qa/topic/hearing-health": "聽力保健常識",
        }
        headings |= {f"/qa/{faq.code}": faq.question for faq in content.FAQS}
        for path, heading in headings.items():
            with self.subTest(path=path):
                page = self.client.get(path).content.decode()
                h1 = re.search(r"<h1[^>]*>\s*(.*?)\s*</h1>", page, re.S).group(1)
                self.assertEqual(re.sub(r"<[^>]+>", "", h1).strip(), heading)


class CanonicalTests(TestCase):
    def test_a_public_page_names_its_address_without_parameters(self):
        # Spec #583 acceptance 17: /guide?edit=… is the same page as /guide.
        for url in ("/guide", "/guide?edit=form-9"):
            with self.subTest(url=url):
                self.assertContains(
                    self.client.get(url),
                    '<link rel="canonical" href="https://testserver/guide">',
                    html=True,
                )

    def test_a_page_kept_out_of_search_has_no_description_or_canonical(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, 'name="description"')
        self.assertNotContains(response, 'rel="canonical"')
