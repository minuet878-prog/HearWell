"""#750 (spec #741, canvas ProResult): the result page's semicircle gauge, in place of ticket #158's
score position bar: one arc for each level by the questionnaire's own thresholds, a knob where the
score is, the scale's two ends; hidden from screen readers, which read the score and level."""

import re

from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.tests.helpers import consented_user, fake_definition, register

ARC = re.compile(r'<path class="gauge-arc ([^"]+)" d="([^"]+)"')
KNOB = re.compile(r'<circle class="gauge-knob" cx="([\d.]+)" cy="([\d.]+)"')


def result_box(page):
    """The result box: the gauge, the score, the level and the line against last time."""
    return page[page.index('<div class="result-banner') : page.index('<section class="hero-card"')]


class GaugeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="gauge_user")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhie_questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhie_s,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")
        cls.hhia_questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhia_s,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.unknown = Questionnaire.objects.create(
            questionnaire_name="未設定門檻問卷", code="unconfigured"
        )
        cls.unknown_question = Question.objects.create(
            questionnaire=cls.unknown, question_text="第一題", question_number=1
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.enterContext(register(fake_definition("unconfigured")))

    def _submit(self, questionnaire, questions, scores):
        submission = Submission.objects.create(user=self.user, questionnaire=questionnaire)
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(questions, scores, strict=True)
        )
        return submission

    def _hhie_s(self, total):
        scores = [4] * (total // 4) + [2] * (total % 4 // 2)
        scores += [0] * (10 - len(scores))
        return self._submit(self.hhie_s, self.hhie_questions, scores)

    def _get(self, submission):
        return self.client.get(reverse("result", args=[submission.id])).content.decode()

    def test_the_knob_is_where_the_score_is_on_the_arc(self):
        # The canvas's own drawing: 12 of 40 sits at (86.1, 49.7); 0 and 40 at the arc's feet,
        # half the full score at its top.
        for total, knob in (
            (12, ("86.1", "49.7")),
            (0, ("35.0", "150.0")),
            (20, ("159.0", "26.0")),
            (40, ("283.0", "150.0")),
        ):
            with self.subTest(total=total):
                self.assertEqual(KNOB.findall(self._get(self._hhie_s(total))), [knob])

    def test_each_level_s_arc_runs_between_its_thresholds(self):
        # Two levels of 10 and 20 meet at the top: each arc stops a little short of it.
        questionnaire = Questionnaire.objects.create(questionnaire_name="假問卷", code="fake-level")
        question = Question.objects.create(
            questionnaire=questionnaire, question_text="第一題", question_number=1
        )
        definition = fake_definition(
            "fake-level",
            thresholds=((10, "低", "low"), (20, "高", "high")),
            advice={"low": "低建議", "high": "高建議"},
        )
        with register(definition):
            page = self._get(self._submit(questionnaire, [question], [5]))
        self.assertEqual(
            ARC.findall(page),
            [
                (
                    "gauge-arc-low gauge-arc-current play-once-gauge",
                    "M35.0 150.0A124 124 0 0 1 154.3 26.1",
                ),
                ("gauge-arc-high", "M163.7 26.1A124 124 0 0 1 283.0 150.0"),
            ],
        )
        # The definition's own top score at the scale's end.
        self.assertIn('<span class="gauge-end">0</span><span class="gauge-end">20</span>', page)

    def test_hhia_s_uses_its_own_thresholds(self):
        # HHIA-S's own definition, not HHIE-S's (same numbers, but read independently).
        page = self._get(self._submit(self.hhia_s, self.hhia_questions, [4, 4, 2, 2] + [0] * 6))
        self.assertEqual(KNOB.findall(result_box(page)), [("86.1", "49.7")])
        self.assertIn('<span class="gauge-end">40</span>', page)

    def test_second_of_two_levels_sharing_a_colour_is_the_deeper_shade(self):
        # THI's five levels in three colours: five arcs, not three.
        questionnaire = Questionnaire.objects.create(questionnaire_name="假問卷", code="fake-shade")
        question = Question.objects.create(
            questionnaire=questionnaire, question_text="第一題", question_number=1
        )
        definition = fake_definition(
            "fake-shade",
            thresholds=((1, "輕", "mild"), (2, "中", "moderate"), (4, "重", "severe")),
            level_colors={"mild": "normal", "moderate": "normal", "severe": "severe"},
            advice={"mild": "輕建議", "moderate": "中建議", "severe": "重建議"},
        )
        with register(definition):
            page = self._get(self._submit(questionnaire, [question], [4]))
        self.assertEqual(
            [classes for classes, _ in ARC.findall(page)],
            [
                "gauge-arc-normal",
                "gauge-arc-normal gauge-arc-deep",
                "gauge-arc-severe gauge-arc-current play-once-gauge",
            ],
        )

    def test_no_gauge_without_thresholds(self):
        submission = self._submit(self.unknown, [self.unknown_question], [4])
        with self.assertLogs("screening.scoring", "ERROR"):
            page = self._get(submission)
        self.assertNotIn('class="gauge"', page)

    def test_no_gauge_when_the_score_is_outside_the_thresholds(self):
        # HHIE-S has thresholds, but 10 points an item (100) is out of range: 「無法判讀」.
        submission = self._submit(self.hhie_s, self.hhie_questions, [10] * 10)
        with self.assertLogs("screening.scoring", "ERROR"):
            page = self._get(submission)
        self.assertIn(
            '<h2 class="result-block-level" aria-describedby="result-score">無法判讀</h2>', page
        )
        self.assertNotIn('class="gauge"', page)

    def test_gauge_is_hidden_from_assistive_technology(self):
        page = self._get(self._hhie_s(12))
        self.assertIn('<svg class="gauge-arcs" viewBox="0 0 318 164" aria-hidden="true"', page)
        self.assertIn('<span class="gauge-ends" aria-hidden="true">', page)
        # The level and score text, read normally, stay outside the hidden drawing.
        self.assertIn(
            '<h2 class="result-block-level visually-hidden" aria-describedby="result-score">'
            "輕度到中度影響</h2>",
            page,
        )
