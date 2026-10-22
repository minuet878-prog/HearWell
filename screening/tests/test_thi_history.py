"""THI on 我的紀錄: its tab, trend chart and 「和上一次比」 (#214, spec #208, ADR 0016)."""

import re
from datetime import datetime

from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Submission
from screening.tests import test_thi


class ThiHistoryTests(test_thi.ThiTestCase):
    def _record(self, total, wearing, when):
        """A THI record of `total` points, worn or not, made at noon Taipei time on `when`."""
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.thi, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(
                self.thi.questions.all(), test_thi.scores_for(total), strict=True
            )
        )
        moment = timezone.make_aware(datetime(*when, 12))
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def _main(self):
        content = self.client.get(reverse("my_hearing"), {"questionnaire": "thi"})
        html = content.content.decode()
        return html[html.index("<main") : html.index("</main>")]

    def _text(self, html):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()

    def _trend(self, main):
        return main[main.index('id="trend-chart"') : main.index('class="link-card"')]

    def test_tab_has_a_trend_chart_with_five_bands_in_three_colours(self):
        self._record(52, False, (2026, 1, 15))
        self._record(30, True, (2026, 7, 15))
        main = self._main()
        trend = self._trend(main)
        self.assertRegex(trend, r"<h2[^>]*>\s*THI 總分變化\s*</h2>")
        self.assertIn('data-questionnaire="thi"', trend)
        bands = re.search(r'class="trend-bands">(.*?)</ul>', trend, re.S).group(1)
        items = re.findall(r'<li class="trend-band-(\w+)">(.*?)</li>', bands, re.S)
        self.assertEqual(
            [(colour, self._text(text)) for colour, text in items],
            [
                ("severe", "極重度障礙"),
                ("severe", "重度障礙"),
                ("mild_to_moderate", "中度障礙"),
                ("mild_to_moderate", "輕度障礙"),
                ("normal", "無障礙或輕微障礙"),
            ],
        )
        self.assertContains(
            self.client.get(reverse("my_hearing"), {"questionnaire": "thi"}),
            "screening/frontend/trend-chart.js",
        )

    def _since_last_lines(self, main):
        match = re.search(r'<section id="since-last"[^>]*>(.*?)</section>', main, re.S)
        if match is None:
            return None
        lines = re.findall(r"<(?:h2|p)[^>]*>(.*?)</(?:h2|p)>", match.group(1), re.S)
        return [self._text(line) for line in lines]

    def test_since_last_compares_with_the_record_before_whatever_was_worn(self):
        self._record(52, False, (2026, 1, 15))
        self._record(30, True, (2026, 7, 15))
        self.assertEqual(
            self._since_last_lines(self._main()),
            [
                "和上一次比",
                "上一次（2026/01/15）：52 分",
                "最近一次（2026/07/15）：30 分",
                "比上一次少 22 分（分數越低越好）",
                "上次沒戴、這次有戴助聽器。",
            ],
        )

    def test_since_last_says_when_the_hearing_aid_came_off(self):
        self._record(30, True, (2026, 1, 15))
        self._record(36, False, (2026, 7, 15))
        self.assertEqual(
            self._since_last_lines(self._main())[3:],
            ["比上一次多 6 分（分數越低越好）", "上次有戴、這次沒戴助聽器。"],
        )

    def test_no_wearing_line_when_both_were_worn(self):
        self._record(52, True, (2026, 1, 15))
        self._record(30, True, (2026, 7, 15))
        main = self._main()
        self.assertEqual(
            self._since_last_lines(main)[1:],
            [
                "上一次（2026/01/15）：52 分",
                "最近一次（2026/07/15）：30 分",
                "比上一次少 22 分（分數越低越好）",
            ],
        )
        self.assertNotIn("上次", main)

    def test_one_record_has_no_since_last_nor_wearing_groups(self):
        self._record(52, True, (2026, 1, 15))
        main = self._main()
        self.assertIsNone(self._since_last_lines(main))
        self.assertNotIn("和上一次比", main)
        summary = re.search(r'class="trend-summary[^"]*">(.*?)</div>', main, re.S).group(1)
        self.assertEqual(
            [self._text(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", summary, re.S)],
            [
                "最近一次（2026/01/15，有戴助聽器）",
                "52 分 中度障礙",
                "再做一次篩檢，就能看到分數的變化。",
            ],
        )

    def test_since_last_and_trend_summary_are_text_for_screen_readers(self):
        # Drawn by Django, outside the chart that React draws and hides from screen readers.
        self._record(52, False, (2026, 1, 15))
        self._record(30, True, (2026, 7, 15))
        main = self._main()
        since_last = re.search(r'<section id="since-last"([^>]*)>', main).group(1)
        self.assertNotIn("aria-hidden", since_last)
        self.assertNotIn("aria-hidden", re.search(r'class="trend-summary([^>]*)>', main).group(1))
        self.assertLess(main.index("上次沒戴、這次有戴助聽器。"), main.index('id="trend-plot"'))

    def test_hhie_s_still_compares_records_worn_the_same_way(self):
        # A life-impact questionnaire: an unaided then an aided record are not compared.
        for wearing, total, when in ((False, 16, (2026, 1, 15)), (True, 8, (2026, 7, 15))):
            submission = Submission.objects.create(
                user=self.user, questionnaire=self.hhie_s, wearing_hearing_aid=wearing
            )
            scores = [4] * (total // 4) + [0] * (10 - total // 4)
            Answer.objects.bulk_create(
                Answer(submission=submission, question=question, score=score)
                for question, score in zip(self.hhie_s.questions.all(), scores, strict=True)
            )
            moment = timezone.make_aware(datetime(*when, 12))
            Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        content = self.client.get(reverse("my_hearing"), {"questionnaire": "hhie-s"})
        self.assertNotContains(content, "和上一次比")
        self.assertContains(content, "這是第一筆有戴助聽器的紀錄。")

    def test_trend_note_is_about_tinnitus(self):
        self._record(52, False, (2026, 1, 15))
        trend = self._trend(self._main())
        self.assertIn("分數越低，耳鳴對生活的影響越小。", trend)
        self.assertNotIn("聽力對生活的影響", trend)
