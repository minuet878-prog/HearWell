"""#756 (spec #741 acceptance 50, ADR 0078, canvas ProRecords and TrendA): 紀錄 has the latest
record (its score, its level's short name, against last time), the score trend (a line on the
level bands, month/day under it, the hearing aid shapes and the fitting day) and each record;
no bento grid or hearing passport. The trend chart's drawing is TrendChart.jsx's."""

import datetime
import re
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import AidAndSubsidy, Submission
from screening.questionnaires import hhie_s
from screening.tests.helpers import consented_user, submission_with_answers

TAIPEI = timezone.get_fixed_timezone(8 * 60)


def text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


class RecordsPageTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())

    def setUp(self):
        self.user = consented_user(username="records_page_user")
        self.client.force_login(self.user)

    def hhie_s(self, scores, day, wearing=False):
        submission = submission_with_answers(
            self.user, hhie_s.CODE, scores, wearing_hearing_aid=wearing
        )
        moment = datetime.datetime(*day, 10, 0, tzinfo=TAIPEI)
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def three_records(self):
        # The canvas's three: 20, 16, then 12 with a hearing aid fitted between the last two.
        self.hhie_s([4, 4, 4, 4, 4, 0, 0, 0, 0, 0], (2026, 5, 22))  # 20
        self.hhie_s([4, 4, 4, 4, 0, 0, 0, 0, 0, 0], (2026, 8, 20), wearing=True)  # 16
        self.hhie_s([4, 4, 4, 0, 0, 0, 0, 0, 0, 0], (2026, 11, 19), wearing=True)  # 12
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 7, 1))

    def records(self):
        content = self.client.get(reverse("my_hearing"), {"questionnaire": hhie_s.CODE})
        content = content.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def test_three_records_show_the_latest_the_trend_and_each_record(self):
        self.three_records()
        main = self.records()
        latest = main.index("records-score")
        trend = main.index('id="trend-chart"')
        each = main.index('<h2 id="records-title" class="h4">歷史</h2>')
        self.assertLess(latest, trend)
        self.assertLess(trend, each)
        chart = main[trend:each]
        self.assertRegex(chart, r'<h2 id="trend-title" class="h4">分數趨勢</h2>')
        # The chart draws the days as month/day (TrendChart.jsx); it gets the fitting day.
        plot = re.search(r'<div id="trend-plot"([^>]*)>', chart).group(1)
        self.assertIn('data-fitted-on="2026/07/01"', plot)
        # The shapes for 沒戴 and 有戴 stay, and the day in words under the frame.
        legend = re.search(r'<ul class="trend-legend">(.*?)</ul>', chart, re.S).group(1)
        self.assertEqual(text(legend), "沒戴助聽器 有戴助聽器")
        self.assertIn('<p class="trend-fitted">2026/07/01 開始戴助聽器。</p>', chart)
        self.assertEqual(main[each:].count('class="link-card" href="/submission/'), 3)
        for absent in ("便當", "護照", "bento", "passport"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, main)

    def test_the_level_names_are_inside_the_chart_not_a_list_under_it(self):
        # Canvas TrendA: the bands carry their names; 分數越低 under the chart went in the owner's
        # 2026-11-27 walkthrough.
        self.three_records()
        chart = re.search(r'<div id="trend-chart">(.*?)</section>', self.records(), re.S)
        self.assertNotIn("trend-bands", chart.group(1))
        self.assertRegex(chart.group(1), r'<p class="trend-fitted">[^<]*</p>\s*$')
        self.assertNotIn("trend-note", chart.group(1))

    def test_the_latest_is_large_in_its_short_name_and_read_in_its_full_one(self):
        self.three_records()
        block = re.search(
            r'records-score">(.*?)<div class="result-since-last"', self.records(), re.S
        )
        self.assertIn('<span class="result-number">12</span> 分', block.group(1))
        self.assertIn(
            '<p class="result-level-short" aria-hidden="true">輕到中度</p>', block.group(1)
        )
        self.assertIn(
            '<p class="result-block-level visually-hidden">輕度到中度影響</p>', block.group(1)
        )
        self.assertEqual(
            text(block.group(1)),
            "最近一次（2026/11/19，有戴助聽器） 12 分 輕到中度 輕度到中度影響",
        )

    def test_the_line_draws_once_in_view(self):
        # ADR 0077 through in-view.js: the plot's box is watched from the start, as the chart
        # arrives later; site.css's play-once-trace draws its line from the left.
        self.three_records()
        plot = re.search(r'<div id="trend-plot"([^>]*)>', self.records()).group(1)
        self.assertRegex(plot, r'class="[^"]*\bplay-once-trace\b')
        self.assertIn(" data-play-in-view", plot)
