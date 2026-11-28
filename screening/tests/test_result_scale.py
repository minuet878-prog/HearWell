"""An ungraded result's block: pale blue, its score on a bar (the owner's 2026-11-28 pick, the
result page mockup's 4A)."""

import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from screening.tests.helpers import consented_user, submission_with_answers

SCALE = re.compile(
    r'<div class="result-scale" aria-hidden="true">.*?'
    r'<span class="result-scale-fill" style="width: ([\d.]+)%">.*?'
    r'<span class="result-scale-dot" style="left: ([\d.]+)%">.*?'
    r'<span class="result-scale-ends"><span>(.*?)</span><span>(.*?)</span></span>',
    re.S,
)


class ResultScaleTests(TestCase):
    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.user = consented_user(username="scale_user")
        self.client.force_login(self.user)

    def page(self, submission):
        return self.client.get(f"/submission/{submission.pk}").content.decode()

    def test_ssq12_s_average_is_on_a_bar_from_0_to_10(self):
        record = submission_with_answers(self.user, "ssq12-tw", [6] * 11 + [7])
        page = self.page(record)
        # 平均 6.1: the bar filled to 61%, its dot there; the ends the scale's anchors.
        self.assertEqual(
            SCALE.search(page).groups(), ("61.00", "61.00", "0 完全不行", "10 輕鬆做到")
        )
        self.assertIn("整體平均", page)

    def test_an_ssq12_average_not_worked_out_has_no_bar(self):
        record = submission_with_answers(self.user, "ssq12-tw", [6] * 11 + [None])
        page = self.page(record)
        self.assertIn("未計算：包含不適用題目", page)
        self.assertNotIn('class="result-scale"', page)

    def test_sadl_s_overall_is_on_a_bar_from_1_to_7(self):
        record = submission_with_answers(self.user, "sadl", [4] * 15)
        page = self.page(record)
        # 4 of 1 to 7: the middle, 50%.
        self.assertEqual(SCALE.search(page).groups(), ("50.00", "50.00", "1 分", "7 分"))
