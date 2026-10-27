import dataclasses
from unittest.mock import patch

from django.test import SimpleTestCase

from screening.qa_assistant import content
from screening.qa_assistant.matching import match

# A small test set (spec #396): a way of asking and the question it should open first, or None
# when nothing should be found. The owner rewrites it from the question log, without anyone's
# details, and grows it to 30–50 before tuning the threshold (ADR 0034).
CASES = (
    # The synonym table: 耳機 is how many people say 助聽器 (#399).
    ("耳機補助", "hearing-aid-subsidy"),
    ("耳機補助怎麼申請", "hearing-aid-subsidy"),
    ("助聽器補助要怎麼申請", "hearing-aid-subsidy"),
    ("請問助聽器有補助嗎", "hearing-aid-subsidy"),
    ("助聽氣補助", "hearing-aid-subsidy"),
    ("集音器", "sound-amplifier-vs-hearing-aid"),
    ("集音器是助聽器嗎", "sound-amplifier-vs-hearing-aid"),
    ("集音器可以代替助聽器嗎", "sound-amplifier-vs-hearing-aid"),
    ("突然聽不到", "sudden-hearing-loss"),
    ("耳朵流血怎麼辦", "sudden-hearing-loss"),
    ("一邊耳朵突然聽不見", "sudden-hearing-loss"),
    ("哪個牌子好", "brands-and-shops"),
    ("推薦品牌", "brands-and-shops"),
    ("去哪裡買助聽器", "brands-and-shops"),
    ("我的分數代表什麼", "my-results"),
    ("結果是什麼意思", "my-results"),
    ("要吃什麼藥", "diagnosis-and-medication"),
    ("聽力變差是什麼病", "diagnosis-and-medication"),
    # Nothing close enough: better none than a wrong answer (spec #396 story 44).
    ("今天天氣如何", None),
    ("耳朵癢", None),
    ("我媽媽八十歲了最近常常聽錯話家裡電視也開很大聲", None),
    ("助", None),
)


# A full-width space; Ruff (RUF001) keeps full-width letters and ! out of the source.
SPACE = chr(0x3000)


def full_width(text):
    return "".join(chr(ord(char) + 0xFEE0) for char in text)


def first(text):
    found = match(text)
    return found[0] if found else None


def fake(code, question, other_phrasings=()):
    return dataclasses.replace(
        content.FAQS[0], code=code, question=question, other_phrasings=other_phrasings
    )


class MatchTestSetTests(SimpleTestCase):
    """#399 (spec #396): each way of asking in the test set, its own assertion."""

    def test_each_way_of_asking_opens_the_question_expected(self):
        for text, expected in CASES:
            with self.subTest(text=text):
                self.assertEqual(first(text), expected)


class MatchTests(SimpleTestCase):
    """#399: what match() returns, seen from outside."""

    def test_full_and_half_width_punctuation_and_spaces_do_not_change_the_result(self):
        faqs = (fake("app", "APP 要怎麼安裝"),)
        with patch.object(content, "FAQS", faqs):
            for text in (
                "APP要怎麼安裝",
                "app 要怎麼安裝?",
                f"{full_width('APP')}{SPACE}要怎麼安裝{full_width('!')}",
                "APP，要怎麼「安裝」？",
            ):
                with self.subTest(text=text):
                    self.assertEqual(match(text), ["app"])

    def test_the_same_with_the_real_questions(self):
        expected = match("耳機補助")
        self.assertNotEqual(expected, [])
        for text in (
            "耳機 補助",
            "耳機，補助？",
            f"{SPACE}耳機補助{full_width('!')}",
            "「耳機」補助...",
        ):
            with self.subTest(text=text):
                self.assertEqual(match(text), expected)

    def test_sorted_by_score(self):
        faqs = (
            fake("short", "助聽器補助"),
            fake("long", "助聽器補助要怎麼申請"),
            fake("other", "耳鳴怎麼辦"),
        )
        with patch.object(content, "FAQS", faqs):
            self.assertEqual(match("助聽器補助申請"), ["long", "short"])
            self.assertEqual(match("助聽器補助"), ["short", "long"])

    def test_a_question_matches_by_its_other_phrasings(self):
        faqs = (fake("itch", "配戴後的不舒服", other_phrasings=("戴助聽器耳朵癢",)),)
        with patch.object(content, "FAQS", faqs):
            self.assertEqual(match("戴助聽器耳朵很癢"), ["itch"])
            self.assertEqual(match("耳朵癢"), ["itch"])

    def test_below_the_threshold_nothing_is_returned(self):
        for text in ("今天天氣如何", "", "  ", "？", "耳"):
            with self.subTest(text=text):
                self.assertEqual(match(text), [])

    def test_earphones_mean_hearing_aids(self):
        self.assertEqual(content.SYNONYMS["耳機"], "助聽器")
        self.assertEqual(first("耳機補助"), "hearing-aid-subsidy")

    def test_a_sound_amplifier_is_not_a_hearing_aid(self):
        # The guide's 集音器不是助聽器: a synonym would open the hearing-aid answers for it.
        self.assertEqual([word for word in content.SYNONYMS if "集音器" in word], [])
        self.assertNotIn("hearing-aid-subsidy", match("集音器"))
        self.assertNotIn("hearing-aid-subsidy", match("集音器補助"))
        self.assertEqual(first("集音器"), "sound-amplifier-vs-hearing-aid")

    def test_every_question_is_found_by_its_own_wording(self):
        for faq in content.FAQS:
            for text in (faq.question, *faq.other_phrasings):
                with self.subTest(code=faq.code, text=text):
                    self.assertIn(faq.code, match(text))


class SynonymTableTests(SimpleTestCase):
    """#399: mistakes in the synonym table fail here."""

    def test_no_word_is_part_of_its_own_standard_word(self):
        # 助聽 → 助聽器 would turn every 助聽器 into 助聽器器.
        self.assertEqual(
            [word for word, standard in content.SYNONYMS.items() if word in standard], []
        )
