from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening.models import AidAndSubsidy
from screening.tests import test_guide, test_guide_summary
from screening.tests.helpers import consented_user

# #779 (spec #774, ADR 0083): my guide no longer draws the 選配路線, so the tests of its stops,
# marks, notes and folded line on the page went with it. Its states are fitting_state's
# (test_fitting_route, test_route_steps, test_route_answers); the cards are test_guide_cards.

PTA_55 = test_guide_summary.PTA_55


class NoAidCardTests(TestCase):
    """#258 acceptance 26: my guide has no 我的助聽器與補助 card."""

    def setUp(self):
        self.user = consented_user(username="route_reader")
        self.client.force_login(self.user)

    make = test_guide_summary.GuideSummaryTests.make

    def test_there_is_no_aid_and_subsidy_card(self):
        self.make(PTA_55, PTA_55)
        self.assertNotContains(self.client.get(reverse("guide")), "我的助聽器與補助")


class AidOnlyRecordsTests(TestCase):
    """Only 助聽器與補助資料, no questionnaire or audiogram: still records, so the page does
    not ask for them (#284 review)."""

    def setUp(self):
        self.user = consented_user(username="aid_only_reader")
        self.client.force_login(self.user)

    def text(self):
        return test_guide.text_of(self.client.get(reverse("guide")))

    def test_any_answer_is_a_record(self):
        for fields in (
            {"certificate": "yes"},
            {"certificate": "applying"},
            {"certificate": "no_subsidy"},
            {"fitted_on": date(2026, 5, 1)},
            {"ear": "both"},
            {"subsidy": "other"},
        ):
            with self.subTest(**fields):
                AidAndSubsidy.objects.filter(user=self.user).delete()
                AidAndSubsidy.objects.create(user=self.user, **fields)
                text = self.text()
                self.assertNotIn(test_guide_summary.NO_RECORDS, text)
                self.assertNotIn(test_guide_summary.START, text)
                self.assertNotIn(test_guide_summary.NO_AUDIOGRAM, text)

    def test_a_row_left_unanswered_is_not_a_record(self):
        AidAndSubsidy.objects.create(user=self.user)
        self.assertIn(test_guide_summary.NO_RECORDS, self.text())
