"""Spec #148 batch 2, ticket #158: the result page's score position bar."""

import re

from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.tests.helpers import consented_user, fake_definition, register


class ScoreBarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="score_bar_user")
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

    def test_segments_are_proportioned_to_the_thresholds(self):
        # HHIE-S thresholds 8 / 24 / 40 of 40: segment widths 20%, 40%, 40%.
        page = self._get(self._hhie_s(12))
        self.assertIn(
            'class="score-bar-segment score-bar-segment-normal" style="width: 20.00%"', page
        )
        self.assertIn(
            'class="score-bar-segment score-bar-segment-mild_to_moderate" style="width: 40.00%"',
            page,
        )
        self.assertIn(
            'class="score-bar-segment score-bar-segment-severe" style="width: 40.00%"', page
        )
        self.assertIn('class="score-bar-marker" style="--position: 30.00%"', page)

    # Text-heavy pages tidy-up (replacing round 4's label per segment, too crowded for THI's five):
    # only this score's level, under the marker, then 0 and the top score.
    def test_names_only_this_score_s_level_under_the_marker_and_the_two_ends(self):
        page = self._get(self._hhie_s(12))
        current = '<div class="score-bar-current" style="--position: 30.00%">'
        self.assertIn(f"{current}<span>輕度到中度影響</span></div>", page)
        self.assertIn('<div class="score-bar-ends"><span>0</span><span>40</span></div>', page)
        for other in ("無/極輕微影響", "顯著影響"):
            with self.subTest(level=other):
                self.assertNotIn(f"<span>{other}</span>", page[page.index('class="score-bar"') :])

    def test_hhia_s_uses_its_own_thresholds(self):
        # HHIA-S's own definition, not HHIE-S's (same numbers, but read independently).
        page = self._get(self._submit(self.hhia_s, self.hhia_questions, [4, 4, 2, 2] + [0] * 6))
        self.assertIn(
            'class="score-bar-segment score-bar-segment-normal" style="width: 20.00%"', page
        )
        self.assertIn('class="score-bar-marker" style="--position: 30.00%"', page)

    def test_marker_stays_inside_the_bar_at_both_ends(self):
        self.assertIn('style="--position: 0.00%"', self._get(self._hhie_s(0)))
        self.assertIn('style="--position: 100.00%"', self._get(self._hhie_s(40)))

    def test_uses_the_questionnaire_s_own_thresholds_not_a_fixed_table(self):
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
            submission = self._submit(questionnaire, [question], [5])
            page = self._get(submission)
        self.assertIn('class="score-bar-segment score-bar-segment-low" style="width: 50.00%"', page)
        self.assertIn(
            'class="score-bar-segment score-bar-segment-high" style="width: 50.00%"', page
        )
        self.assertIn('style="--position: 25.00%"', page)
        # This score's level and the definition's own top score.
        self.assertIn('style="--position: 25.00%"><span>低</span></div>', page)
        self.assertIn('<div class="score-bar-ends"><span>0</span><span>20</span></div>', page)

    def test_second_of_two_levels_sharing_a_colour_is_the_deeper_shade(self):
        # THI's five levels in three colours: the bar shows five segments, not three.
        questionnaire = Questionnaire.objects.create(questionnaire_name="假問卷", code="fake-shade")
        question = Question.objects.create(
            questionnaire=questionnaire, question_text="第一題", question_number=1
        )
        definition = fake_definition(
            "fake-shade",
            thresholds=((10, "輕", "mild"), (20, "中", "moderate"), (30, "重", "severe")),
            level_colors={"mild": "normal", "moderate": "normal", "severe": "severe"},
            advice={"mild": "輕建議", "moderate": "中建議", "severe": "重建議"},
        )
        with register(definition):
            submission = self._submit(questionnaire, [question], [5])
            page = self._get(submission)
        segments = re.findall(r'class="score-bar-segment ([^"]+)"', page)
        self.assertEqual(
            segments,
            [
                "score-bar-segment-normal",
                "score-bar-segment-normal score-bar-segment-deep",
                "score-bar-segment-severe",
            ],
        )

    def test_no_bar_without_thresholds(self):
        submission = self._submit(self.unknown, [self.unknown_question], [4])
        with self.assertLogs("screening.scoring", "ERROR"):
            page = self._get(submission)
        self.assertNotIn("score-bar", page)

    def test_no_bar_when_the_score_is_outside_the_thresholds(self):
        # HHIE-S has thresholds, but 10 points an item (100) is out of range: 「無法判讀」.
        submission = self._submit(self.hhie_s, self.hhie_questions, [10] * 10)
        with self.assertLogs("screening.scoring", "ERROR"):
            page = self._get(submission)
        self.assertIn("無法判讀", page)
        self.assertNotIn("score-bar", page)

    def test_bar_is_hidden_from_assistive_technology(self):
        page = self._get(self._hhie_s(12))
        self.assertIn('<div class="score-bar" aria-hidden="true">', page)
        # The level and score text, read normally, stay outside the hidden bar.
        self.assertIn(
            '<h2 class="result-level mb-0" aria-describedby="result-score">輕度到中度影響</h2>',
            page,
        )
