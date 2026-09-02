from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission, User
from screening.scoring import classify


class ClassifyTests(TestCase):
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
        self.user_a = User.objects.create_user(username="user_a", password="testpass123")
        self.user_b = User.objects.create_user(username="user_b", password="testpass123")
        self.questionnaire = Questionnaire.objects.create(questionnaire_name="測試問卷")
        self.submission = Submission.objects.create(
            user=self.user_a, questionnaire=self.questionnaire
        )

    def test_user_cannot_view_others_submission(self):
        self.client.login(username="user_b", password="testpass123")
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
        self.user_a = User.objects.create_user(username="user_a", password="testpass123")
        self.questionnaire = Questionnaire.objects.create(questionnaire_name="測試問卷")
        self.question = Question.objects.create(
            questionnaire=self.questionnaire,
            question_text="數值正確？",
            question_number=1,
            category=Category.EMOTIONAL,
        )

    def test_screening_view_accept_correct_value(self):
        self.client.login(username="user_a", password="testpass123")
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
        self.user_a = User.objects.create_user(username="user_a", password="testpass123")
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
