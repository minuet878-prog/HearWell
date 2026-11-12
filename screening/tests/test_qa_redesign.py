"""#469 (spec #453, the #468 mockup A): the Q&A assistant redesigned. The urgent answer is one red
box that is a link (ADR 0041); topics are framed tiles (G); every list of questions is list rows
with an icon (E); typing to ask and 沒回答到您的問題？ sit on the white page. Order, answers,
sources and check dates are unchanged."""

import re

from django.test import TestCase
from django.urls import reverse

from screening.qa_assistant import content

# A question row: its icon, then the question, then the arrow.
QUESTION_ROW = re.compile(
    r'<a class="link-card action-card" href="/qa/([^"/#]+)">\s*'
    r'<span class="action-card-icon" aria-hidden="true" data-icon="question">.*?</span>\s*'
    r'<span class="link-card-body"><span class="link-card-title">([^<]+)</span></span>\s*'
    r'<span class="link-card-arrow" aria-hidden="true">›</span>\s*</a>',  # noqa: RUF001
    re.S,
)


def _main(response):
    page = response.content.decode()
    return page[page.index("<main") : page.index("</main>")]


class QaHomeRedesignTests(TestCase):
    def setUp(self):
        response = self.client.get(reverse("qa_home"))
        self.assertEqual(response.status_code, 200)
        self.main = _main(response)

    def test_the_urgent_box_is_red_and_one_link(self):
        box = re.search(r'<a class="([^"]*)" href="([^"]+)">(.*?)</a>', self.main, re.S)
        classes, href, inside = box.groups()
        self.assertLessEqual({"card", "family-urgent", "family-urgent-link"}, set(classes.split()))
        self.assertEqual(href, reverse("qa_answer", args=[content.URGENT_CODE]))
        self.assertRegex(
            inside, r'<h2 id="qa-urgent-title"[^>]*>.*突然聽不到、耳朵流血？請盡快就醫</h2>'
        )
        self.assertIn(content.BY_CODE[content.URGENT_CODE].question, inside)
        self.assertIn('class="link-card-arrow"', inside)
        # It comes before everything else on the page but its title.
        self.assertLess(box.start(), self.main.index(">依主題找</h2>"))

    def test_popular_questions_are_rows_with_an_icon(self):
        popular = self.main[self.main.index(">大家常問</h2>") : self.main.index("qa-ask-title")]
        self.assertEqual(
            QUESTION_ROW.findall(popular),
            [(code, content.BY_CODE[code].question) for code in content.POPULAR],
        )

    def test_typing_comes_last_on_the_white_page_with_the_one_solid_button(self):
        self.assertNotIn('class="qa-ask', self.main)
        ask = self.main[self.main.index('id="qa-ask-title"') :]
        self.assertIn(
            '<button type="submit" class="btn btn-primary btn-lg w-full">找答案</button>', ask
        )
        self.assertEqual(self.main.count("btn-primary"), 1)


class QaListsRedesignTests(TestCase):
    def test_topic_and_results_list_questions_as_rows_with_an_icon(self):
        topic = _main(self.client.get(reverse("qa_topic", args=["hearing-aids"])))
        self.assertTrue(QUESTION_ROW.findall(topic))
        self.assertEqual(len(QUESTION_ROW.findall(topic)), len(re.findall(r'href="/qa/', topic)))
        search = self.client.post(
            reverse("qa_search"), {"question": "助聽器補助怎麼申請"}, follow=True
        )
        results = _main(search)
        self.assertTrue(QUESTION_ROW.findall(results))


class QaAnswerRedesignTests(TestCase):
    def setUp(self):
        self.main = _main(self.client.get(reverse("qa_answer", args=["brands-and-shops"])))

    def test_sources_fold_like_a_row_with_the_date_outside(self):
        fold = re.search(r'<details class="result-details">(.*?)</details>', self.main, re.S)
        self.assertIsNotNone(fold)
        summary, body = fold.group(1).split("</summary>", 1)
        self.assertIn('data-icon="info"', summary)
        self.assertIn("資料來源", summary)
        self.assertIn(f'href="{reverse("guide_chapter", args=["types-and-prices"])}"', body)
        self.assertIn(
            '<p class="guide-checked">本頁資料查核於 2026/10/27。</p>', self.main[fold.end() :]
        )

    def test_related_questions_are_rows_and_not_answered_is_white_with_an_outline_button(self):
        related = self.main[self.main.index(">相關問題</h2>") : self.main.index("qa-more-title")]
        self.assertEqual(
            [code for code, _ in QUESTION_ROW.findall(related)],
            list(content.BY_CODE["brands-and-shops"].related),
        )
        self.assertNotIn('class="qa-ask', self.main)
        self.assertRegex(
            self.main,
            r'<section class="mt-6" aria-labelledby="qa-more-title">\s*'
            r'<h2 id="qa-more-title" class="h4">沒回答到您的問題？</h2>\s*'
            rf'<a class="btn btn-outline-primary btn-lg w-full" href="{reverse("qa_home")}">'
            r"回問答小助手首頁</a>\s*</section>",
        )
        self.assertNotIn("btn-primary ", self.main)
