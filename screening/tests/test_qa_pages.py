import dataclasses
import re
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.models import User
from screening.qa_assistant import content
from screening.tests import test_guide
from screening.tests.helpers import consented_user

REFERRALS = ("my-results", "diagnosis-and-medication", "brands-and-shops", "sudden-hearing-loss")
SITE_CSS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "site.css"
# The family page's 馬上就醫 box, which the assistant's home page pins its urgent answer in.
URGENT_BOX_PAGES = ("qa_home", "family_guide")


def urgent_box(response):
    """(its classes, what is inside) of the section saying to see a doctor soon."""
    content = response.content.decode()
    for classes, inside in re.findall(
        r'<section class="([^"]*)"[^>]*>(.*?)</section>', content, re.S
    ):
        if "請盡快" in inside:
            return classes, inside
    raise AssertionError("no section says to see a doctor soon")


# The owner's pick (2026-10-27, B): every question in a list is a white card with an arrow and no
# icon (ADR 0022); each topic is a white tile, its icon above its name.
QUESTION_CARD = re.compile(
    r'<a class="link-card" href="/qa/([^"/#]+)">\s*<span class="link-card-body">'
    r'<span class="link-card-title">([^<]+)</span></span>\s*'
    r'<span class="link-card-arrow" aria-hidden="true">›</span>\s*</a>'  # noqa: RUF001
)
TOPIC_TILE = re.compile(
    r'<a class="link-card qa-topic" href="/qa/topic/([^"]+)">\s*'
    r'<span class="action-card-icon" aria-hidden="true" data-icon="([^"]+)">(.*?)</span>\s*'
    r"<span class=\"link-card-title\">([^<]+)</span>\s*</a>",
    re.S,
)
TOPIC_TILES = [
    ("using-the-site", "home", "網站怎麼用"),
    ("questionnaires", "clipboard", "問卷是什麼"),
    ("hearing-aids", "guide", "助聽器選配與補助"),
    ("hearing-health", "ear", "聽力保健常識"),
]


def question_cards(html):
    """(code, question) of every question card in html."""
    return QUESTION_CARD.findall(html)


def topic_tiles(html):
    """(slug, icon, name) of every topic tile in html; each icon must draw something."""
    tiles = TOPIC_TILE.findall(html)
    for slug, _, drawing, _ in tiles:
        if "<path" not in drawing:
            raise AssertionError(f"{slug}'s icon draws nothing")
    return [(slug, icon, name) for slug, icon, _, name in tiles]


def answer_part(response):
    """The answer itself: from the page's h1 to the footer of sources."""
    content = response.content.decode()
    return content[content.index("<h1") : content.index("<footer")]


class QaHomeTests(TestCase):
    """#397 (spec #396): the Q&A assistant's home page."""

    def test_urgent_answer_then_the_four_topics_then_popular(self):
        # The owner's call (2026-10-27): 依主題找 comes before 大家常問.
        response = self.client.get(reverse("qa_home"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        main = content[content.index("<main") :]
        self.assertRegex(main, r"<h1[^>]*>問答小助手</h1>")
        order = [
            f'href="{reverse("qa_answer", args=["sudden-hearing-loss"])}"',
            ">依主題找</h2>",
            "網站怎麼用",
            "問卷是什麼",
            "助聽器選配與補助",
            "聽力保健常識",
            ">大家常問</h2>",
        ]
        places = [main.find(text) for text in order]
        self.assertNotIn(-1, places, dict(zip(order, places, strict=True)))
        self.assertEqual(places, sorted(places))

    def test_the_urgent_answer_sits_in_the_family_page_urgent_box(self):
        # The owner's call (2026-10-27): the family page's 馬上就醫 look, blue, not red (ADR 0007).
        boxes = {name: urgent_box(self.client.get(reverse(name))) for name in URGENT_BOX_PAGES}
        for name, (classes, _) in boxes.items():
            with self.subTest(page=name):
                self.assertLessEqual({"card", "family-urgent"}, set(classes.split()))
        _, inside = boxes["qa_home"]
        self.assertIn("請盡快就醫", inside)
        self.assertIn(f'href="{reverse("qa_answer", args=["sudden-hearing-loss"])}"', inside)

    def test_the_urgent_box_look_is_not_the_family_page_own(self):
        # The family page's rules nest under .family-guide; the box's own look must not, or the
        # assistant's box above would be a plain card.
        css = re.sub(r"/\*.*?\*/", "", SITE_CSS.read_text(encoding="utf-8"), flags=re.S)
        selectors = [
            selector.strip()
            for selector, rule in re.findall(r"([^{}]*)\{([^{}]*)\}", css)
            if ".family-urgent" in selector and "border:" in rule
        ]
        self.assertEqual(selectors, [".card.family-urgent"])
        self.assertNotIn("qa-urgent", css)

    def test_popular_follows_the_definition_order(self):
        for popular in (
            ("my-results", "brands-and-shops", "diagnosis-and-medication"),
            ("diagnosis-and-medication", "my-results"),
        ):
            with (
                self.subTest(popular=popular),
                patch("screening.qa_assistant.content.POPULAR", popular),
            ):
                content = self.client.get(reverse("qa_home")).content.decode()
                section = content[content.index(">大家常問</h2>") : content.index("qa-ask-title")]
                links = re.findall(r'href="/qa/([^"]+)"', section)
                self.assertEqual(tuple(links), popular)

    def test_headings_do_not_skip_a_level(self):
        response = self.client.get(reverse("qa_home"))
        test_guide.assert_levels_without_skipping(self, test_guide.heading_levels(response))


class QaLookTests(TestCase):
    """The owner's pick (2026-10-27, B, ADR 0022): what can be tapped is a white card, the rest
    flat; the typing and 沒回答到 parts on a pale blue block."""

    TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "screening" / "qa"

    def main(self, url, data=None):
        if data is None:
            response = self.client.get(url)
        else:
            response = self.client.post(url, data, follow=True)
        page = response.content.decode()
        return page[page.index("<main") : page.index("</main>")]

    def test_home_topics_are_tiles_with_their_icons(self):
        main = self.main(reverse("qa_home"))
        topics = main[main.index(">依主題找</h2>") : main.index(">大家常問</h2>")]
        self.assertEqual(topic_tiles(topics), TOPIC_TILES)

    def test_nothing_found_lists_the_same_tiles(self):
        main = self.main(reverse("qa_search"), {"question": "今天天氣如何"})
        self.assertIn(">依主題找</h2>", main)
        self.assertEqual(topic_tiles(main), TOPIC_TILES)

    def test_popular_questions_are_white_cards_without_icons(self):
        main = self.main(reverse("qa_home"))
        popular = main[main.index(">大家常問</h2>") : main.index("qa-ask-title")]
        self.assertEqual(
            question_cards(popular),
            [(code, content.BY_CODE[code].question) for code in content.POPULAR],
        )

    def test_matched_questions_are_white_cards_without_icons(self):
        main = self.main(reverse("qa_search"), {"question": "助聽器補助怎麼申請"})
        cards = question_cards(main)
        self.assertTrue(cards)
        self.assertEqual([code for code, _ in cards], re.findall(r'href="/qa/([^"/#]+)"', main))

    def test_the_ask_form_sits_on_a_pale_blue_block_its_button_full_width(self):
        main = self.main(reverse("qa_home"))
        block = re.search(
            r'<section class="qa-ask mt-6" aria-labelledby="qa-ask-title">\s*'
            r'<h2 id="qa-ask-title" class="h4">找不到？打字問</h2>(.*?)</section>',
            main,
            re.S,
        )
        self.assertIsNotNone(block)
        self.assertIn(f'<form method="post" action="{reverse("qa_search")}"', block[1])
        self.assertIn(
            '<button type="submit" class="btn btn-primary btn-lg w-full">找答案</button>', block[1]
        )

    def test_the_answer_is_on_the_page_its_reminder_in_a_tip_box(self):
        main = self.main(reverse("qa_answer", args=["brands-and-shops"]))
        self.assertIn('<article class="wrap-anywhere">', main)
        self.assertIn(
            '<p class="tip-box mt-4">以上是一般說明，您的情況請以醫師、聽力師為準。</p>',
            main[main.index("<article") : main.index("</article>")],
        )

    def test_not_answered_is_a_pale_blue_block_with_a_full_width_outline_button(self):
        main = self.main(reverse("qa_answer", args=["brands-and-shops"]))
        self.assertRegex(
            main,
            r'<section class="qa-ask mt-6" aria-labelledby="qa-more-title">\s*'
            r'<h2 id="qa-more-title" class="h4">沒回答到您的問題？</h2>\s*'
            rf'<a class="btn btn-outline-primary btn-lg w-full" href="{reverse("qa_home")}">'
            r"回問答小助手首頁</a>\s*</section>",
        )

    def test_the_thin_line_list_look_is_gone(self):
        self.assertNotIn("qa-questions", SITE_CSS.read_text(encoding="utf-8"))
        for template in self.TEMPLATES.glob("*.html"):
            with self.subTest(template=template.name):
                self.assertNotIn("qa-questions", template.read_text(encoding="utf-8"))


class QaAnswerTests(TestCase):
    """#397 (spec #396): one question a page."""

    def test_question_answer_reminder_sources_and_check_date(self):
        response = self.client.get(reverse("qa_answer", args=["brands-and-shops"]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertRegex(content, r"<h1[^>]*>哪個牌子的助聽器比較好？去哪家店買？</h1>")
        text = test_guide.text_of(response)
        self.assertIn("小助手不推薦品牌、型號或店家。", text)
        self.assertIn("以上是一般說明，您的情況請以醫師、聽力師為準。", text)
        footer = content[content.index("<footer") : content.index("</footer>")]
        self.assertIn('<details class="dropdown-box mb-2">', footer)
        self.assertIn("<summary>資料來源</summary>", footer)
        self.assertIn(f'href="{reverse("guide_chapter", args=["types-and-prices"])}"', footer)
        self.assertIn(f'href="{reverse("guide_chapter", args=["assessment"])}"', footer)
        self.assertIn('<p class="guide-checked">本頁資料查核於 2026/10/27。</p>', footer)

    def test_a_code_never_used_is_not_found(self):
        response = self.client.get(reverse("qa_answer", args=["no-such-question"]))
        self.assertEqual(response.status_code, 404)

    def test_a_changed_answer_keeps_its_address(self):
        # ADR 0033: the owner rewrites an answer; the address family were sent still opens it.
        address = reverse("qa_answer", args=["brands-and-shops"])
        rewritten = dataclasses.replace(
            content.BY_CODE["brands-and-shops"],
            answer="<p>改寫過的答案。</p>",
            checked_on=date(2027, 3, 1),
        )
        with patch.dict("screening.qa_assistant.content.BY_CODE", {rewritten.code: rewritten}):
            response = self.client.get(address)
        self.assertEqual(response.status_code, 200)
        self.assertIn("<p>改寫過的答案。</p>", answer_part(response))
        self.assertContains(response, '<p class="guide-checked">本頁資料查核於 2027/03/01。</p>')

    def test_headings_do_not_skip_a_level(self):
        for code in REFERRALS:
            with self.subTest(code=code):
                response = self.client.get(reverse("qa_answer", args=[code]))
                levels = test_guide.heading_levels(response)
                test_guide.assert_levels_without_skipping(self, levels)


class QaSameForEveryoneTests(TestCase):
    """#397 (ADR 0032): signed in or not, the same answer; nobody's records are read."""

    PAGES = (("qa_home", ()), *(("qa_answer", (code,)) for code in REFERRALS))

    def test_signed_in_sees_what_a_visitor_sees(self):
        for name, args in self.PAGES:
            with self.subTest(page=name, args=args):
                self.client.logout()
                visitor = test_guide.text_of(self.client.get(reverse(name, args=args)))
                self.client.force_login(consented_user(username=f"qa_{name}_{args}"))
                signed_in = test_guide.text_of(self.client.get(reverse(name, args=args)))
                self.assertEqual(signed_in, visitor)

    def test_no_questionnaire_or_audiogram_is_read(self):
        self.client.force_login(consented_user(username="qa_reader"))
        requests = [
            *((f"GET {name} {args}", reverse(name, args=args), None) for name, args in self.PAGES),
            *(
                (f"GET qa_topic {slug}", reverse("qa_topic", args=[slug]), None)
                for slug, _ in content.TOPICS
            ),
            ("POST qa_search", reverse("qa_search"), {"question": "助聽器補助怎麼申請"}),
            ("GET qa_results", reverse("qa_results"), None),
        ]
        for label, url, data in requests:
            with self.subTest(request=label):
                with CaptureQueriesContext(connection) as queries:
                    if data is None:
                        response = self.client.get(url)
                    else:
                        response = self.client.post(url, data)
                self.assertIn(response.status_code, (200, 302))
                tables = " ".join(query["sql"] for query in queries.captured_queries)
                self.assertNotIn("screening_submission", tables)
                self.assertNotIn("screening_answer", tables)
                self.assertNotIn("screening_audiogram", tables)

    def test_signed_in_before_agreeing_to_the_privacy_notice(self):
        # The owner's call (2026-10-27): open like the family page; family share the links.
        self.client.force_login(User.objects.create_user(username="qa_not_consented"))
        for name, args in self.PAGES:
            with self.subTest(page=name, args=args):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)


class QaReferralTests(TestCase):
    """#397 (ADR 0032): the four referral answers say where to go instead."""

    def answer(self, code):
        return answer_part(self.client.get(reverse("qa_answer", args=[code])))

    def test_my_results_leads_to_my_records(self):
        answer = self.answer("my-results")
        self.assertIn("不解讀個人的結果", answer)
        self.assertIn(f'<a href="{reverse("my_hearing")}">到「我的紀錄」看結果</a>', answer)
        self.assertIn("帶給聽力師看", answer)

    def test_diagnosis_and_medication_sends_to_an_ear_nose_and_throat_doctor(self):
        answer = self.answer("diagnosis-and-medication")
        self.assertIn("不回答個人的診斷和用藥", answer)
        self.assertIn("耳鼻喉科醫師", answer)
        # The site has no ENT page to send to: the answer itself links nowhere.
        self.assertNotIn("<a", answer)

    def test_brands_and_shops_lead_to_types_and_prices_and_the_hospital_search(self):
        answer = self.answer("brands-and-shops")
        self.assertIn("不推薦品牌、型號或店家", answer)
        types = reverse("guide_chapter", args=["types-and-prices"])
        self.assertIn(f'<a href="{types}">「助聽器的種類與價格」</a>', answer)
        hospitals = f"{reverse('guide_chapter', args=['assessment'])}#hospitals-title"
        self.assertIn(f'<a href="{hospitals}">「找鑑定醫院」</a>', answer)

    def test_sudden_hearing_loss_says_to_see_a_doctor_soon(self):
        answer = self.answer("sudden-hearing-loss")
        self.assertIn("請盡快到耳鼻喉科就醫", answer)
        urgent = f"{reverse('family_guide')}#urgent-title"
        self.assertIn(f'<a href="{urgent}">「什麼時候要馬上就醫」</a>', answer)
