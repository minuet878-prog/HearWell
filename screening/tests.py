from django.test import TestCase

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
