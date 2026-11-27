"""Spec #741 (實作中本人補充, 2026-11-21, compare-impact.html's A): a graded result page's
這個分數怎麼算, open between the score block and the 建議下一步: a score ruler that does not move,
for HHIE-S and HHIA-S where the impact is (情緒, 社交), then the reviewed first step."""

import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening import questionnaires
from screening.models import Question
from screening.questionnaires import hhia_s, hhie_s, thi
from screening.tests.helpers import consented_user, submission_with_answers
from screening.tests.test_result_pages_redesign import read

SECTION = re.compile(r'<section class="score-explain"[^>]*>.*?</section>', re.S)
BAND = re.compile(
    r'<span class="score-ruler-band score-ruler-band-([a-z_]+)[^"]*" style="width: ([\d.]+)%">'
)
DOT = re.compile(r'<span class="score-ruler-dot" style="left: ([\d.]+)%">')


class ScoreExplainTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())

    def setUp(self):
        self.user = consented_user(username="score_explain")
        self.client.force_login(self.user)

    def main(self, code, scores):
        record = submission_with_answers(self.user, code, scores, wearing_hearing_aid=False)
        content = self.client.get(reverse("result", args=[record.pk])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def section(self, main):
        return SECTION.search(main).group(0)

    def test_it_is_open_between_the_score_block_and_the_suggestion(self):
        main = self.main(hhie_s.CODE, [4, 4, 2, 2, 0, 0, 0, 0, 0, 0])  # 12
        order = [
            '<div class="result-banner',
            '<section class="score-explain"',
            '<section class="hero-card"',
        ]
        positions = [main.find(piece) for piece in order]
        self.assertNotIn(-1, positions)
        self.assertEqual(positions, sorted(positions))
        # Not folded any more: no row of that name.
        self.assertNotIn("<span>這個分數怎麼算</span>", main)
        section = self.section(main)
        self.assertNotIn('<details class="result-details"', section)
        # Its heading and how the total is counted went in the owner's 2026-11-27 walkthrough.
        self.assertNotIn("這個分數怎麼算", section)
        self.assertNotIn("每一題的分數加起來就是總分，分數越高，影響越大。", section)

    def test_the_ruler_has_each_level_and_a_dot_that_does_not_move(self):
        cases = (
            (
                hhie_s.CODE,
                [4, 4, 2, 2, 0, 0, 0, 0, 0, 0],
                [("normal", 20), ("mild_to_moderate", 40), ("severe", 40)],
                30,
                ["極輕微", "輕到中度", "顯著"],
                "分數尺從 0 到 40 分，您 12 分，在「輕度到中度影響」這一段。",
            ),
            (
                thi.CODE,
                [4] * 10 + [0] * 15,
                [
                    ("normal", 16),
                    ("mild_to_moderate", 20),
                    ("mild_to_moderate", 20),
                    ("severe", 20),
                    ("severe", 24),
                ],
                40,
                ["輕微", "輕度", "中度", "重度", "極重度"],
                "分數尺從 0 到 100 分，您 40 分，在「中度障礙」這一段。",
            ),
        )
        for code, scores, bands, dot, names, said in cases:
            with self.subTest(code=code):
                section = self.section(self.main(code, scores))
                self.assertEqual(
                    [(colour, round(float(width))) for colour, width in BAND.findall(section)],
                    bands,
                )
                self.assertEqual(round(float(DOT.search(section).group(1))), dot)
                # On screen: 「您 N 分」 over the dot, each level's short name under its band.
                ruler = section[section.index('<div class="score-ruler" aria-hidden="true">') :]
                words = re.sub(r"<[^>]+>", " ", ruler).split()
                self.assertEqual(words[:3], ["您", str(sum(scores)), "分"])
                self.assertEqual(words[3 : 3 + len(names)], names)
                # Not a slider: nothing to drag or type into.
                self.assertNotIn("<input", section)
                self.assertNotIn('role="slider"', section)
                # A screen reader hears the ruler once, in words, and not its drawing.
                heard = read(section)
                self.assertIn(said, heard)
                self.assertNotIn(f"您 {sum(scores)} 分 ", heard)

    def parts(self, section):
        """Each part's (name, open, words read on its row, its answers' words)."""
        found = re.findall(
            r'<details class="score-impact"([^>]*)>\s*<summary>(.*?)</summary>(.*?)</details>',
            section,
            re.S,
        )
        return [
            (
                read(summary).split()[0],
                " open" in attrs,
                read(summary),
                [read(item) for item in re.findall(r"<li>(.*?)</li>", body, re.S)],
            )
            for attrs, summary, body in found
        ]

    def test_where_the_impact_is_lists_each_part_with_the_answers(self):
        # Items 1, 2, 4, 7, 9 are 情緒 and 3, 5, 6, 8, 10 社交 (the fixture's, HHIE-S's own).
        main = self.main(hhie_s.CODE, [4, 4, 2, 2, 0, 0, 0, 0, 0, 0])  # 情緒 10, 社交 2
        section = self.section(main)
        questions = dict(
            Question.objects.filter(questionnaire__code=hhie_s.CODE).values_list(
                "question_number", "question_text"
            )
        )
        # Under the page's h1 now that the section has no heading of its own (2026-11-27).
        self.assertIn('<h2 class="score-impact-title">聽力問題影響在哪裡</h2>', section)
        self.assertEqual(
            self.parts(section),
            [
                (
                    "情緒",
                    True,
                    "情緒 10 分（滿分 20）",
                    [
                        f"{questions[1]} 常常",
                        f"{questions[2]} 常常",
                        f"{questions[4]} 有時",
                        f"{questions[7]} 從未",
                        f"{questions[9]} 從未",
                    ],
                ),
                (
                    "社交",
                    False,
                    "社交 2 分（滿分 20）",
                    [
                        f"{questions[3]} 有時",
                        f"{questions[5]} 從未",
                        f"{questions[6]} 從未",
                        f"{questions[8]} 從未",
                        f"{questions[10]} 從未",
                    ],
                ),
            ],
        )
        # Each bar its part's share of that part's full score, drawn for the eye only.
        self.assertEqual(
            re.findall(r'<span class="score-impact-fill" style="width: ([\d.]+)%">', section),
            ["50.00", "10.00"],
        )
        # Only one open at a time where the browser can (details name).
        self.assertEqual(section.count('name="score-impact"'), 2)
        # The subscales' caveat, then #461's reviewed first step, shown under the two rows.
        order = [
            "聽力問題影響在哪裡",
            "社交 2 分（滿分 20）",
            "情緒與社交分項僅供參考，目前沒有正式的解讀標準，請以總分分級為主。",
            hhie_s.NEXT_STEPS["mild_to_moderate"][0]["text"],
        ]
        positions = [read(section).find(piece) for piece in order]
        self.assertNotIn(-1, positions)
        self.assertEqual(positions, sorted(positions))

    def test_the_higher_part_is_open_and_a_tie_opens_emotional(self):
        for scores, opened in (
            ([0, 0, 4, 0, 4, 4, 0, 0, 0, 0], "社交"),  # 情緒 0, 社交 12
            ([4, 0, 4, 0, 0, 0, 0, 0, 0, 0], "情緒"),  # 4 and 4
            ([0] * 10, "情緒"),
        ):
            with self.subTest(scores=scores):
                parts = self.parts(self.section(self.main(hhie_s.CODE, scores)))
                self.assertEqual([name for name, is_open, *_ in parts if is_open], [opened])

    def test_only_questionnaires_with_parts_say_where_the_impact_is(self):
        for code, scores, level, has_parts in (
            (hhia_s.CODE, [2] * 10, "mild_to_moderate", True),
            (thi.CODE, [2] * 25, "moderate", False),
        ):
            with self.subTest(code=code):
                section = self.section(self.main(code, scores))
                self.assertEqual("聽力問題影響在哪裡" in section, has_parts)
                self.assertEqual(len(self.parts(section)), 2 if has_parts else 0)
                # Without parts the first step is right under the ruler.
                first = questionnaires.get(code).next_steps[level][0]["text"]
                self.assertLess(section.index("分數尺從"), section.index(first))
