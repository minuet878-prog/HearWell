"""THI on the health report, the family's copy and the data export (#215, spec #208 Q9, Q14)."""

import re

from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Submission
from screening.tests import test_report, test_report_parts, test_thi


class ThiReportTestCase(test_thi.ThiTestCase):
    def record(self, scores, wearing="False"):
        self.post_web(scores, wearing=wearing)
        return Submission.objects.latest("pk")

    def family_report(self):
        self.client.post(reverse("report_share_create"), {"confirm": "1"})
        share = self.user.report_shares.get()
        self.client.logout()
        return self.client.get(reverse("shared_report", args=[share.token]))

    def reports(self):
        """The owner's report, then the family's copy of it."""
        return {"owner": self.client.get(reverse("health_report")), "family": self.family_report()}


def _day(submission):
    return timezone.localtime(submission.created_at).strftime("%Y/%m/%d")


class ThiReportPartTests(ThiReportTestCase):
    def test_owner_and_family_reports_show_the_thi_part(self):
        older = self.record(test_thi.scores_for(38))
        latest = self.record(test_thi.scores_for(58), wearing="True")
        for page, response in self.reports().items():
            with self.subTest(page=page):
                content = response.content.decode()
                thi = test_report._section(content, "report-thi")
                self.assertIn(f"THI（最近一次 {_day(latest)}）", thi)
                self.assertIn(
                    '<span class="report-score">58 分</span>（滿分 100） '
                    '<span class="report-level">重度障礙</span>',
                    thi,
                )
                self.assertIn("助聽器：有戴", thi)
                self.assertIn(f"<p>{test_thi.ADVICE[58]}</p>", thi)
                self.assertIn("共 2 次", thi)
                rows = re.findall(r"<tr><td>.*?</tr>", thi)
                self.assertEqual(
                    rows,
                    [
                        f"<tr><td>{_day(latest)}</td><td>58</td><td>重度障礙</td><td>有戴</td></tr>",
                        f"<tr><td>{_day(older)}</td><td>38</td><td>中度障礙</td><td>沒戴</td></tr>",
                    ],
                )

    def test_thi_is_its_own_part_not_life_impact_and_prints_whole(self):
        # ADR 0016: THI is not a life-impact questionnaire. Printing keeps every section inside a
        # report-part whole (site.css), so the THI section sits in one, as the other results do.
        self.record(test_thi.scores_for(38))
        for page, response in self.reports().items():
            with self.subTest(page=page):
                content = response.content.decode()
                outline = test_report_parts._outline(response)
                self.assertEqual(outline.parents["report-tinnitus"], ())
                self.assertEqual(outline.parents["report-thi"], ("report-tinnitus",))
                self.assertIn('<section id="report-tinnitus" class="report-part"', content)
                self.assertIn(">耳鳴</h2>", test_report._section(content, "report-tinnitus"))
                self.assertNotIn('id="report-life-impact"', content)

    def test_summary_lists_the_latest_thi(self):
        latest = self.record(test_thi.scores_for(58), wearing="True")
        for page, response in self.reports().items():
            with self.subTest(page=page):
                summary = test_report._section(response.content.decode(), "report-summary")
                self.assertIn(
                    f"<li>THI（{_day(latest)}）：58 分，"
                    '<span class="report-level">重度障礙</span>，助聽器：有戴</li>',
                    summary,
                )

    def test_a_record_that_shows_the_support_message_leaves_it_and_the_answers_out(self):
        # Spec #208 Q6, Q9: items 5 (絕望), 11 (憂鬱) and 23 (無法忍受) answered 經常 show the
        # support message on the result page only; family see the level, not those answers.
        scores = [0] * 25
        for number in (5, 11, 23):
            scores[number - 1] = 4
        self.record(scores)
        for page, response in self.reports().items():
            with self.subTest(page=page):
                content = response.content.decode()
                self.assertIn('<span class="report-level">無障礙或輕微障礙</span>', content)
                self.assertNotIn("1925", content)
                self.assertNotIn("逐題回答", content)
                for text in test_thi.QUESTIONS:
                    self.assertNotIn(text, content)
                # No subscores either (spec #208 Q5).
                self.assertNotIn("情緒", content)
                self.assertNotIn("社交", content)

    def test_no_thi_record_leaves_the_part_out(self):
        record = Submission.objects.create(
            user=self.user, questionnaire=self.hhie_s, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=question, score=0)
            for question in self.hhie_s.questions.all()
        )
        for page, response in self.reports().items():
            with self.subTest(page=page):
                self.assertContains(response, 'id="report-life-impact"')
                self.assertNotContains(response, 'id="report-tinnitus"')
                self.assertNotContains(response, 'id="report-thi"')

    def test_lists_the_latest_five_like_the_other_parts(self):
        for _ in range(6):
            self.record(test_thi.scores_for(38))
        thi = test_report._section(
            self.client.get(reverse("health_report")).content.decode(), "report-thi"
        )
        self.assertIn("共 6 次，列出最近 5 次", thi)
        self.assertEqual(len(re.findall(r"<tr><td>", thi)), 5)


class ThiExportTests(ThiReportTestCase):
    def test_each_thi_exports_its_25_answers_total_and_level_as_on_its_result_page(self):
        scores = test_thi.scores_for(58)
        submission = self.record(scores, wearing="True")
        result = self.client.get(reverse("result", args=[submission.pk]))
        self.assertContains(result, "總分 58 分（滿分 100）")
        self.assertContains(result, 'aria-describedby="result-score">重度障礙</h2>')
        exported = self.client.get(reverse("download_my_data")).json()["submissions"]
        self.assertEqual(len(exported), 1)
        thi = exported[0]
        self.assertEqual(thi["questionnaire"], "THI")
        self.assertEqual(thi["wearing_hearing_aid"], "有戴")
        self.assertEqual(thi["total_score"], 58)
        self.assertEqual(thi["level"], "重度障礙")
        labels = {4: "經常", 2: "偶爾", 0: "不會"}
        self.assertEqual(
            [(a["number"], a["question"], a["choice"]) for a in thi["answers"]],
            [
                (number, text, labels[score])
                for number, (text, score) in enumerate(
                    zip(test_thi.QUESTIONS, scores, strict=True), start=1
                )
            ],
        )

    def test_thi_exports_null_subscores(self):
        # Spec #208: THI has no emotional or social subscores (Q5), so they are null, not 0.
        self.record(test_thi.scores_for(58))
        thi = self.client.get(reverse("download_my_data")).json()["submissions"][0]
        self.assertIsNone(thi["emotional_score"])
        self.assertIsNone(thi["social_score"])
