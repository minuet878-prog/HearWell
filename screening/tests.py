from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission, User
from screening.scoring import classify


class ClassifyTests(SimpleTestCase):
    def test_score_out_of_range_positive(self):
        with self.assertRaises(ValueError):
            classify(42)

    def test_score_out_of_range_negative(self):
        with self.assertRaises(ValueError):
            classify(-5)

    def test_zero_score_is_minimal(self):
        result = classify(0)
        self.assertEqual(result["text"], "無/極輕微影響")

    def test_margin_of_moderate_impact(self):
        result = classify(9)
        self.assertEqual(result["text"], "輕度到中度影響")

    def test_margin_of_severe_impact(self):
        result = classify(25)
        self.assertEqual(result["text"], "顯著影響")

    def test_forty_score_is_maximum(self):
        result = classify(40)
        self.assertEqual(result["text"], "顯著影響")


class SubmissionResultAccessTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="user_a")
        self.user_b = User.objects.create_user(username="user_b")
        self.questionnaire = Questionnaire.objects.create(questionnaire_name="測試問卷")
        self.submission = Submission.objects.create(
            user=self.user_a, questionnaire=self.questionnaire
        )

    def test_user_cannot_view_others_submission(self):
        self.client.force_login(self.user_b)
        url = reverse("result", kwargs={"submission_id": self.submission.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class LoginRequiredTests(TestCase):
    def test_not_login_visit_can_redirect(self):
        protected_url = reverse("my_hearing")
        response = self.client.get(protected_url)
        login_url = reverse("login")
        expected_reversed_url = f"{login_url}?next={protected_url}"
        self.assertRedirects(response, expected_reversed_url)


class ScreeningViewAcceptValueTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="user_a")
        self.questionnaire = Questionnaire.objects.create(questionnaire_name="測試問卷")
        self.question = Question.objects.create(
            questionnaire=self.questionnaire,
            question_text="數值正確？",
            question_number=1,
            category=Category.EMOTIONAL,
        )

    def test_screening_view_accept_correct_value(self):
        self.client.force_login(self.user_a)
        url = reverse("screening", kwargs={"questionnaire_id": self.questionnaire.id})
        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-0-score": "4",
            "form-0-question_id": str(self.question.id),
        }
        response = self.client.post(url, data)
        submission = Submission.objects.get(user=self.user_a, questionnaire=self.questionnaire)
        expected_reversed_url = reverse("result", kwargs={"submission_id": submission.id})
        self.assertTrue(Answer.objects.filter(question=self.question, score=4).exists())
        self.assertRedirects(response, expected_reversed_url)


class ModelsUniqueConstraintTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="user_a")
        self.questionnaire = Questionnaire.objects.create(questionnaire_name="測試問卷")
        self.question = Question.objects.create(
            questionnaire=self.questionnaire,
            question_text="constraint正確?",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        self.submission = Submission.objects.create(
            user=self.user_a, questionnaire=self.questionnaire
        )
        self.answer = Answer.objects.create(
            submission=self.submission, question=self.question, score=0
        )

    def test_question_model_unique_constraint(self):
        with self.assertRaises(IntegrityError):
            Question.objects.create(
                questionnaire=self.questionnaire,
                question_text="constraint正確?",
                question_number=1,
                category=Category.EMOTIONAL,
            )

    def test_answer_model_unique_constraint(self):
        with self.assertRaises(IntegrityError):
            Answer.objects.create(submission=self.submission, question=self.question, score=0)


class ScoringAggregateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="user")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="測試問卷")
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
