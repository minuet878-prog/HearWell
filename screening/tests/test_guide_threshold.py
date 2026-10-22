from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase

from screening.tests import test_audiogram

# Each ear's four PTA frequencies (500, 1k, 2k, 4k) giving the PTA in the name.
PTA_55 = (55, 55, 55, 55)
PTA_53_75 = (50, 55, 55, 55)
PTA_60 = (60, 60, 60, 60)


def ear(side, values):
    return test_audiogram._four(test_audiogram._air, side, values)


def estimate_points(points):
    from screening.audiogram import assessment_estimate

    return assessment_estimate([mock.Mock(**point) for point in points])


def estimate(right, left, extra=()):
    return estimate_points([*ear("right", right), *ear("left", left), *extra])


def no_response_at(points, frequency):
    """The same air points, with the one at frequency marked as no response."""
    return [{**p, "no_response": p["frequency"] == frequency} for p in points]


class AssessmentEstimateTests(SimpleTestCase):
    """#226: the disability assessment (b230) threshold, estimated from one audiogram."""

    def test_both_ears_at_55_reach_the_threshold(self):
        result = estimate(PTA_55, PTA_55)
        self.assertEqual(result["ratio"], Decimal("45.0"))
        self.assertEqual(result["status"], "reached")

    def test_just_under_rounds_to_44_7_and_does_not_reach(self):
        result = estimate(PTA_53_75, PTA_60)
        self.assertEqual(result["right"]["pta"], 53.75)
        self.assertEqual(result["ratio"], Decimal("44.7"))
        self.assertEqual(result["status"], "not_reached")

    def test_halves_round_up_not_to_even(self):
        # 11.25 exactly: Python's round() would give 11.2.
        self.assertEqual(estimate((30, 30, 35, 35), (30, 30, 35, 35))["ratio"], Decimal("11.3"))

    def test_one_ear_90_and_the_other_48_needs_no_rule_of_its_own(self):
        result = estimate((90, 90, 90, 90), (45, 50, 50, 50))
        self.assertEqual(result["ratio"], Decimal("45.9"))
        self.assertEqual(result["status"], "reached")

    def test_an_ear_under_25_counts_as_0_percent(self):
        result = estimate((10, 10, 10, 10), (100, 100, 100, 100))
        self.assertEqual(result["right"]["ratio"], 0)
        self.assertEqual(result["ratio"], Decimal("16.7"))
        self.assertEqual(result["status"], "not_reached")

    def test_an_ear_counts_at_most_100_percent(self):
        result = estimate((90, 90, 95, 95), PTA_55)
        self.assertEqual(result["right"]["ratio"], 100)

    def test_not_reached_with_a_no_response_point_is_uncertain(self):
        # Marked at 80 dB but unheard: the real threshold can only be worse.
        result = estimate_points(
            [*ear("right", (40, 40, 40, 40)), *no_response_at(ear("left", (80, 80, 80, 80)), 4000)]
        )
        self.assertEqual(result["status"], "uncertain")
        self.assertTrue(result["no_response"])

    def test_reached_with_a_no_response_point_is_still_reached(self):
        result = estimate_points(
            [*ear("right", PTA_55), *no_response_at(ear("left", PTA_55), 2000)]
        )
        self.assertEqual(result["status"], "reached")
        self.assertTrue(result["no_response"])

    def test_no_response_outside_the_four_air_frequencies_does_not_count(self):
        extra = (
            test_audiogram._air("left", 8000, 120, no_response=True),
            test_audiogram._bone("left", 1000, 80, no_response=True),
        )
        result = estimate(PTA_53_75, PTA_60, extra)
        self.assertEqual(result["status"], "not_reached")
        self.assertFalse(result["no_response"])

    def test_a_missing_frequency_leaves_too_little_data(self):
        points = [*ear("right", PTA_55), *ear("left", PTA_55)[:3]]
        result = estimate_points(points)
        self.assertEqual(result["status"], "insufficient")
        self.assertIsNone(result["ratio"])
        self.assertEqual(result["right"]["pta"], 55)


def recommends(points):
    from screening.audiogram import recommends_fitting_assessment

    return recommends_fitting_assessment([mock.Mock(**point) for point in points])


class FittingAssessmentTests(SimpleTestCase):
    """#226, grill Q3: 「建議找聽力師評估選配」 when either ear's PTA is over 25 dB."""

    def test_one_ear_over_25_is_enough(self):
        self.assertIs(recommends([*ear("right", (20, 20, 20, 20)), *ear("left", (45,) * 4)]), True)

    def test_both_ears_at_25_are_not(self):
        self.assertIs(recommends([*ear("right", (25,) * 4), *ear("left", (25,) * 4)]), False)

    def test_one_ear_unknown(self):
        unknown_left = ear("left", (60,) * 4)[:3]
        # The other ear over 25 still recommends; at or under 25 leaves too little data.
        self.assertIs(recommends([*ear("right", (30,) * 4), *unknown_left]), True)
        self.assertIsNone(recommends([*ear("right", (25,) * 4), *unknown_left]))
        self.assertIsNone(recommends(unknown_left))
