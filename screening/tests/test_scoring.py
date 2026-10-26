from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.scoring import classify
from screening.tests.helpers import consented_user, fake_definition, register


class ClassifyTests(SimpleTestCase):
    def test_hhie_s_boundaries(self):
        expected = {
            0: "normal",
            8: "normal",
            10: "mild_to_moderate",
            24: "mild_to_moderate",
            26: "severe",
            40: "severe",
        }
        for score, level in expected.items():
            with self.subTest(score=score):
                self.assertEqual(classify(score, "hhie-s")["level"], level)

    def test_score_out_of_range_is_unknown(self):
        for score in (-2, 42):
            with self.subTest(score=score), self.assertLogs("screening.scoring", "ERROR"):
                self.assertEqual(classify(score, "hhie-s")["level"], "unknown")

    def test_questionnaire_without_thresholds_is_unknown(self):
        with self.assertLogs("screening.scoring", "ERROR"):
            result = classify(10, "unconfigured")
        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["text"], "無法判讀")

    # #356: the two life-impact questionnaires sit side by side on 我的紀錄, so they name their
    # levels the same way; only the words change, never the cut-offs.
    def test_hhie_s_and_hhia_s_name_their_levels_the_same(self):
        expected = {0: "無／極輕微影響", 10: "輕度到中度影響", 26: "顯著影響"}
        for code in ("hhie-s", "hhia-s"):
            for score, text in expected.items():
                with self.subTest(code=code, score=score):
                    self.assertEqual(classify(score, code)["text"], text)


class ClassifyViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="user")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.unknown = Questionnaire.objects.create(
            questionnaire_name="未設定門檻問卷", code="unconfigured"
        )

    def setUp(self):
        self.enterContext(register(fake_definition("unconfigured")))

    def _make_submission(self, questionnaire, score):
        question = Question.objects.create(
            questionnaire=questionnaire,
            question_text="第一題",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        submission = Submission.objects.create(user=self.user, questionnaire=questionnaire)
        Answer.objects.create(submission=submission, question=question, score=score)
        return submission

    def test_result_page_shows_unknown_for_questionnaire_without_thresholds(self):
        submission = self._make_submission(self.unknown, score=4)
        self.client.force_login(self.user)
        with self.assertLogs("screening.scoring", "ERROR"):
            response = self.client.get(reverse("result", args=[submission.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "無法判讀")
        self.assertContains(response, "result-banner-unknown")
        self.assertContains(response, "這次的作答結果無法判讀分級")

    def test_history_page_survives_unknown_submission(self):
        self._make_submission(self.hhie_s, score=4)
        self._make_submission(self.unknown, score=4)
        self.client.force_login(self.user)
        # One tab per questionnaire (phase4_history_by_questionnaire.md): each tab must survive.
        with self.assertLogs("screening.scoring", "ERROR") as logs:
            response = self.client.get(reverse("my_hearing") + "?questionnaire=unconfigured")
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "無法判讀")
        response = self.client.get(reverse("my_hearing") + "?questionnaire=hhie-s")
        self.assertContains(response, "無／極輕微影響")

    def test_result_and_history_show_same_classification(self):
        submission = self._make_submission(self.hhie_s, score=4)
        self.client.force_login(self.user)
        result = self.client.get(reverse("result", args=[submission.id]))
        history = self.client.get(reverse("my_hearing"))
        self.assertContains(result, "無／極輕微影響")
        self.assertContains(history, "無／極輕微影響")


class ScoringAggregateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="user")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="測試問卷", code="test")
        questions_emo = [
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"情緒題{i}",
                question_number=i,
                category=Category.EMOTIONAL,
            )
            for i in range(1, 6)
        ]
        questions_soc = [
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"社交題{i}",
                question_number=i,
                category=Category.SOCIAL,
            )
            for i in range(6, 11)
        ]
        cls.questions_e = Question.objects.bulk_create(questions_emo)
        cls.questions_s = Question.objects.bulk_create(questions_soc)

    def _make_submission(self, emotional_score, social_score):
        submission = Submission.objects.create(user=self.user, questionnaire=self.questionnaire)
        answers_e = [
            Answer(submission=submission, question=question, score=emotional_score)
            for question in self.questions_e
        ]
        answers_s = [
            Answer(submission=submission, question=question, score=social_score)
            for question in self.questions_s
        ]
        answers = [*answers_e, *answers_s]
        Answer.objects.bulk_create(answers)
        return submission

    def test_emotional_full_marks(self):
        submission = self._make_submission(emotional_score=4, social_score=0)
        self.assertEqual(submission.total_answer_score, 20)
        self.assertEqual(submission.emotional_score, 20)
        self.assertEqual(submission.social_score, 0)

    def test_social_full_marks(self):
        submission = self._make_submission(emotional_score=0, social_score=4)
        self.assertEqual(submission.total_answer_score, 20)
        self.assertEqual(submission.emotional_score, 0)
        self.assertEqual(submission.social_score, 20)

    def test_mix_marks(self):
        submission = self._make_submission(emotional_score=4, social_score=2)
        self.assertEqual(submission.total_answer_score, 30)
        self.assertEqual(submission.emotional_score, 20)
        self.assertEqual(submission.social_score, 10)

    def test_calculate_score_return_zero(self):
        submission = Submission.objects.create(user=self.user, questionnaire=self.questionnaire)
        self.assertEqual(submission.total_answer_score, 0)
        self.assertEqual(submission.emotional_score, 0)
        self.assertEqual(submission.social_score, 0)

    def test_has_subscores_the_same_annotated_or_aggregated(self):
        # #386: one rule, from the scoring aggregate, on both scoring paths.
        all_zero = self._make_submission(emotional_score=0, social_score=0)
        no_subscore_items = Submission.objects.create(
            user=self.user, questionnaire=self.questionnaire
        )
        other = Question.objects.create(
            questionnaire=self.questionnaire, question_text="其他題", question_number=11
        )
        Answer.objects.create(submission=no_subscore_items, question=other, score=4)
        for submission, expected in ((all_zero, True), (no_subscore_items, False)):
            for path, fetched in (
                ("aggregate", Submission.objects.get(pk=submission.pk)),
                ("annotate", Submission.objects.with_scores().get(pk=submission.pk)),
            ):
                with self.subTest(path, expected=expected):
                    self.assertEqual(fetched.has_subscores, expected)


class HistoryScorePathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="user")
        cls.other = consented_user(username="other")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )

    def _make_submission(self, user, scores):
        submission = Submission.objects.create(user=user, questionnaire=self.questionnaire)
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(self.questions, scores, strict=False)
        )
        return submission

    def _count_history_queries(self, expected_rows):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse("my_hearing"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["submissions"]), expected_rows)
        return len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_submissions(self):
        self.client.force_login(self.user)
        self._make_submission(self.user, [4] * 10)
        one = self._count_history_queries(expected_rows=1)
        for _ in range(4):
            self._make_submission(self.user, [2] * 10)
        five = self._count_history_queries(expected_rows=5)
        self.assertEqual(one, five)

    def test_history_and_result_show_same_scores(self):
        # emotional 5 x 4 = 20, social 3 x 2 = 6 -> total 26 (severe)
        submission = self._make_submission(self.user, [4, 4, 4, 4, 4, 2, 2, 2, 0, 0])
        self.client.force_login(self.user)
        history = self.client.get(reverse("my_hearing"))
        result = self.client.get(reverse("result", args=[submission.id]))
        self.assertContains(history, "總分：26")
        self.assertContains(history, "顯著影響")
        self.assertContains(result, "總分 26 分")
        self.assertContains(result, "情緒分數：20")
        self.assertContains(result, "社交分數：6")
        self.assertContains(result, "顯著影響")

    def test_submission_without_answers_scores_zero(self):
        self._make_submission(self.user, [])
        self.client.force_login(self.user)
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, "總分：0")
        self.assertContains(response, "無／極輕微影響")

    def test_history_only_shows_own_submissions(self):
        own = self._make_submission(self.user, [0] * 10)
        others = self._make_submission(self.other, [4] * 10)
        self.client.force_login(self.user)
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, reverse("result", args=[own.id]))
        self.assertNotContains(response, reverse("result", args=[others.id]))


class SubscaleNoteTests(TestCase):
    NOTE = "情緒與社交分項僅供參考，目前沒有正式的解讀標準，請以總分分級為主。"

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="user")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.unknown = Questionnaire.objects.create(
            questionnaire_name="未設定門檻問卷", code="unconfigured"
        )

    def _make_submission(self, questionnaire):
        question = Question.objects.create(
            questionnaire=questionnaire,
            question_text="第一題",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        submission = Submission.objects.create(user=self.user, questionnaire=questionnaire)
        Answer.objects.create(submission=submission, question=question, score=4)
        return submission

    def setUp(self):
        self.client.force_login(self.user)
        self.enterContext(register(fake_definition("unconfigured")))

    def test_result_page_shows_note_below_subscales(self):
        submission = self._make_submission(self.hhie_s)
        response = self.client.get(reverse("result", args=[submission.id]))
        content = response.content.decode()
        self.assertIn(self.NOTE, content)
        self.assertLess(content.index("建議"), content.index("社交分數"))
        self.assertLess(content.index("社交分數"), content.index(self.NOTE))

    def test_note_shown_when_unclassifiable(self):
        submission = self._make_submission(self.unknown)
        with self.assertLogs("screening.scoring", "ERROR"):
            response = self.client.get(reverse("result", args=[submission.id]))
        self.assertContains(response, "無法判讀")
        self.assertContains(response, self.NOTE)

    def test_history_page_has_no_note(self):
        self._make_submission(self.hhie_s)
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, "總分")
        self.assertNotContains(response, self.NOTE)

    def test_note_uses_readable_rem_size(self):
        submission = self._make_submission(self.hhie_s)
        response = self.client.get(reverse("result", args=[submission.id]))
        self.assertContains(response, f'<p class="text-black">{self.NOTE}</p>', html=True)
