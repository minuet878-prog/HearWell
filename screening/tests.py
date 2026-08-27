from django.test import TestCase
from django.urls import reverse

from screening.models import Questionnaire, Submission, User
from screening.scoring import classify


# Create your tests here.
class ClassifyTests(TestCase):
    def test_score_out_of_range_positive(self):
        result = classify(42)
        self.assertEqual(result["text"], "不合規的分數")

    def test_score_out_of_range_negative(self):
        result = classify(-5)
        self.assertEqual(result["text"], "不合規的分數")

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
