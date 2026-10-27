import dataclasses
import re
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from screening.models import User
from screening.qa_assistant import content
from screening.tests import test_guide, test_qa_pages
from screening.tests.helpers import consented_user

TOPIC_SLUGS = ("using-the-site", "questionnaires", "hearing-aids", "hearing-health")

# The way back above a topic or an answer (prototype #373): the arrow is hidden from screen readers.
BACK = '<span aria-hidden="true">‹</span> '  # noqa: RUF001


def unknown_related(faqs):
    known = {faq.code for faq in faqs}
    return [(faq.code, code) for faq in faqs for code in faq.related if code not in known]


def reused_retired_codes(faqs, retired):
    return sorted({faq.code for faq in faqs} & retired)


def main_of(response):
    page = response.content.decode()
    return page[page.index("<main") : page.index("</main>")]


def faq_with(code, related):
    return dataclasses.replace(content.BY_CODE[code], related=related)


def by_code_with(*changed):
    return {**content.BY_CODE, **{faq.code: faq for faq in changed}}


class QaTopicPageTests(TestCase):
    """#398 (spec #396): a topic's page lists its questions, each leading to its answer."""

    def test_lists_the_topics_questions_each_linking_to_its_answer(self):
        response = self.client.get(reverse("qa_topic", args=["hearing-aids"]))
        self.assertEqual(response.status_code, 200)
        main = main_of(response)
        self.assertRegex(main, r"<h1[^>]*>助聽器選配與補助</h1>")
        cards = test_qa_pages.question_cards(main)
        self.assertEqual(cards[0], ("brands-and-shops", "哪個牌子的助聽器比較好？去哪家店買？"))
        self.assertEqual(
            [code for code, _ in cards],
            # #399 adds the subsidy and the 集音器 questions to this topic.
            ["brands-and-shops", "hearing-aid-subsidy", "sound-amplifier-vs-hearing-aid"],
        )
        # Nothing else on the page leads to an answer.
        self.assertEqual(re.findall(r'href="/qa/([^"/]+)"', main), [code for code, _ in cards])

    def test_the_urgent_answer_is_on_no_topic_page(self):
        # Prototype #373: it is pinned on the home page, not in a list; its data says
        # hearing-health, whose page still lists its other questions.
        urgent = reverse("qa_answer", args=["sudden-hearing-loss"])
        for slug in TOPIC_SLUGS:
            with self.subTest(topic=slug):
                main = main_of(self.client.get(reverse("qa_topic", args=[slug])))
                self.assertNotIn(urgent, main)
        health = main_of(self.client.get(reverse("qa_topic", args=["hearing-health"])))
        self.assertIn(reverse("qa_answer", args=["diagnosis-and-medication"]), health)

    def test_a_topic_never_defined_is_not_found(self):
        response = self.client.get(reverse("qa_topic", args=["no-such-topic"]))
        self.assertEqual(response.status_code, 404)

    def test_home_links_each_topic_to_its_page_in_order(self):
        page = self.client.get(reverse("qa_home")).content.decode()
        topics = page[page.index(">依主題找</h2>") : page.index("</main>")]
        self.assertEqual(
            [(slug, name) for slug, _, name in test_qa_pages.topic_tiles(topics)],
            [
                ("using-the-site", "網站怎麼用"),
                ("questionnaires", "問卷是什麼"),
                ("hearing-aids", "助聽器選配與補助"),
                ("hearing-health", "聽力保健常識"),
            ],
        )

    def test_leads_back_to_the_assistant_home(self):
        main = main_of(self.client.get(reverse("qa_topic", args=["questionnaires"])))
        back = f'<a href="{reverse("qa_home")}">{BACK}回問答小助手</a>'
        self.assertIn(back, main[: main.index("<h1")])

    def test_headings_do_not_skip_a_level(self):
        for slug in TOPIC_SLUGS:
            with self.subTest(topic=slug):
                response = self.client.get(reverse("qa_topic", args=[slug]))
                levels = test_guide.heading_levels(response)
                test_guide.assert_levels_without_skipping(self, levels)


class QaTopicForEveryoneTests(TestCase):
    """#398 (ADR 0032, the owner's call 2026-10-27): a topic page is the same for everyone."""

    def test_signed_in_sees_what_a_visitor_sees(self):
        for slug in TOPIC_SLUGS:
            with self.subTest(topic=slug):
                self.client.logout()
                url = reverse("qa_topic", args=[slug])
                visitor = test_guide.text_of(self.client.get(url))
                self.client.force_login(consented_user(username=f"qa_topic_{slug}"))
                self.assertEqual(test_guide.text_of(self.client.get(url)), visitor)

    def test_signed_in_before_agreeing_to_the_privacy_notice(self):
        self.client.force_login(User.objects.create_user(username="qa_topic_not_consented"))
        for slug in TOPIC_SLUGS:
            with self.subTest(topic=slug):
                response = self.client.get(reverse("qa_topic", args=[slug]))
                self.assertEqual(response.status_code, 200)


class QaAnswerWayOnTests(TestCase):
    """#398 (spec #396, prototype #373 Y): an answer leads back to its topic and on to more."""

    def test_leads_back_to_its_topic(self):
        main = main_of(self.client.get(reverse("qa_answer", args=["brands-and-shops"])))
        topic = reverse("qa_topic", args=["hearing-aids"])
        back = f'<a href="{topic}">{BACK}回「助聽器選配與補助」</a>'
        self.assertIn(back, main[: main.index("<h1")])

    def test_the_urgent_answer_leads_back_to_the_assistant_home(self):
        # It is on no topic page, so 回「聽力保健常識」 would lead where it is not.
        main = main_of(self.client.get(reverse("qa_answer", args=["sudden-hearing-loss"])))
        before_question = main[: main.index("<h1")]
        self.assertIn(f'<a href="{reverse("qa_home")}">{BACK}回問答小助手</a>', before_question)
        self.assertNotIn("/qa/topic/", before_question)

    def test_shows_the_related_questions_the_definition_names(self):
        brands = faq_with("brands-and-shops", related=("my-results", "sudden-hearing-loss"))
        with patch("screening.qa_assistant.content.BY_CODE", by_code_with(brands)):
            main = main_of(self.client.get(reverse("qa_answer", args=["brands-and-shops"])))
        section = main[main.index(">相關問題</h2>") : main.index(">沒回答到您的問題？</h2>")]
        self.assertEqual(
            test_qa_pages.question_cards(section),
            [
                ("my-results", "我的分數代表什麼？"),
                ("sudden-hearing-loss", "突然聽不到、耳朵流血，該怎麼辦？"),
            ],
        )

    def test_without_related_questions_there_is_no_heading_for_them(self):
        brands = faq_with("brands-and-shops", related=())
        with patch("screening.qa_assistant.content.BY_CODE", by_code_with(brands)):
            main = main_of(self.client.get(reverse("qa_answer", args=["brands-and-shops"])))
        self.assertNotIn("相關問題", main)

    def test_every_answer_in_the_definition_shows_its_related_questions(self):
        for faq in content.FAQS:
            with self.subTest(code=faq.code):
                main = main_of(self.client.get(reverse("qa_answer", args=[faq.code])))
                for code in faq.related:
                    self.assertIn(f'href="{reverse("qa_answer", args=[code])}"', main)

    def test_not_answered_leads_to_the_assistant_home(self):
        main = main_of(self.client.get(reverse("qa_answer", args=["my-results"])))
        heading = main.index(">沒回答到您的問題？</h2>")
        self.assertRegex(
            main[heading:], rf'<a class="[^"]*" href="{reverse("qa_home")}">回問答小助手首頁</a>'
        )
        self.assertLess(main.index("以上是一般說明"), heading)

    def test_a_retired_code_goes_to_the_assistant_home(self):
        # ADR 0033: family shared the old address; it leads somewhere, never to a wrong answer.
        with patch("screening.qa_assistant.content.RETIRED_CODES", frozenset({"old-question"})):
            response = self.client.get(reverse("qa_answer", args=["old-question"]))
        self.assertRedirects(response, reverse("qa_home"))

    def test_a_code_never_used_is_still_not_found(self):
        with patch("screening.qa_assistant.content.RETIRED_CODES", frozenset({"old-question"})):
            response = self.client.get(reverse("qa_answer", args=["never-a-question"]))
        self.assertEqual(response.status_code, 404)

    def test_headings_do_not_skip_a_level(self):
        for faq in content.FAQS:
            with self.subTest(code=faq.code):
                response = self.client.get(reverse("qa_answer", args=[faq.code]))
                levels = test_guide.heading_levels(response)
                test_guide.assert_levels_without_skipping(self, levels)


class FaqRelatedAndRetiredDefinitionTests(SimpleTestCase):
    """#398 (spec #396, ADR 0033): mistakes in related or retired codes fail here."""

    def test_related_questions_point_at_questions_that_exist(self):
        self.assertEqual(unknown_related(content.FAQS), [])

    def test_no_question_uses_a_retired_code(self):
        self.assertEqual(reused_retired_codes(content.FAQS, content.RETIRED_CODES), [])


class FaqRelatedAndRetiredChecksCatchMistakesTests(SimpleTestCase):
    """The checks above fail on a broken definition, so passing means something."""

    def test_a_related_question_that_does_not_exist(self):
        broken = faq_with("my-results", related=("brands-and-shops", "gone"))
        others = [faq for faq in content.FAQS if faq.code != "my-results"]
        self.assertEqual(unknown_related((broken, *others)), [("my-results", "gone")])

    def test_a_live_code_also_retired(self):
        retired = frozenset({"my-results", "old-question"})
        self.assertEqual(reused_retired_codes(content.FAQS, retired), ["my-results"])


TILE_TITLE = re.compile(
    r'<a class="link-card qa-topic" href="/qa/topic/([^"]+)">.*?'
    r'<span class="link-card-title">(.*?)</span>\s*</a>',
    re.S,
)
PHRASE = re.compile(r'<span class="qa-topic-phrase">([^<]+)</span>')


class QaTopicTileWrapTests(TestCase):
    """A tile's name breaks only between its phrases (聽力保健／常識, never 聽力保／健常識)."""

    def tile_phrases(self):
        tiles = TILE_TITLE.findall(main_of(self.client.get(reverse("qa_home"))))
        return {slug: PHRASE.findall(title) for slug, title in tiles}

    def test_the_long_names_break_between_their_phrases(self):
        phrases = self.tile_phrases()
        self.assertEqual(phrases["hearing-aids"], ["助聽器選配", "與補助"])
        self.assertEqual(phrases["hearing-health"], ["聽力保健", "常識"])

    def test_every_tile_spells_its_topic_name(self):
        self.assertEqual(
            {slug: "".join(parts) for slug, parts in self.tile_phrases().items()},
            dict(content.TOPICS),
        )
