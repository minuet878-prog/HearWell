"""Issue #102: wearing-status comparisons follow each questionnaire's definition."""

import re

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, NormGroup, Question, Questionnaire, Submission
from screening.questionnaires.comparison import TotalComparison
from screening.tests.helpers import consented_user, fake_definition, register


class ComparisonFromDefinitionTests(TestCase):
    def setUp(self):
        self.user = consented_user(username="comparison_definitions")
        self.client.force_login(self.user)

    def questionnaire(self, code, count):
        questionnaire = Questionnaire.objects.create(code=code, questionnaire_name=code.upper())
        Question.objects.bulk_create(
            Question(questionnaire=questionnaire, question_text=f"{code} 題{n}", question_number=n)
            for n in range(1, count + 1)
        )
        return questionnaire

    def record(self, questionnaire, wearing, scores, **fields):
        record = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=wearing, **fields
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=q, score=s)
            for q, s in zip(questionnaire.questions.all(), scores, strict=True)
        )
        return record

    def test_a_definition_with_a_comparison_can_be_compared(self):
        self.enterContext(
            register(
                fake_definition(
                    "fake-compare",
                    comparison=TotalComparison(anchor="report-fake-anchor"),
                    # The report shows comparisons in the life-impact part (ADR 0016).
                    life_impact=True,
                )
            )
        )
        fake = self.questionnaire("fake-compare", 10)
        unaided = self.record(fake, False, [4] * 10)
        aided = self.record(fake, True, [2] * 10)
        url = reverse("hhi_comparison", args=[fake.pk])
        page = self.client.get(url, {"unaided": unaided.pk, "aided": aided.pk})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "有戴比沒戴少 20 分（分數越低越好）")
        self.client.post(url, {"unaided": unaided.pk, "aided": aided.pk, "action": "save"})
        report = self.client.get(reverse("health_report")).content.decode()
        self.assertRegex(report, r'<section id="report-fake-anchor"')
        self.assertIn("報告保留比較（FAKE-COMPARE）：沒戴 40 分、有戴 20 分，少了 20 分", report)
        history = self.client.get(reverse("my_hearing")).content.decode()
        self.assertIn("配戴狀態比較", history)
        self.assertIn("少了 20 分", history)
        result = self.client.get(reverse("result", args=[aided.pk]))
        self.assertContains(result, f'href="{url}"')

    def test_a_definition_without_a_comparison_offers_none(self):
        self.enterContext(register(fake_definition("fake-alone")))
        fake = self.questionnaire("fake-alone", 10)
        record = self.record(fake, False, [4] * 10)
        url = reverse("hhi_comparison", args=[fake.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertNotContains(self.client.get(reverse("result", args=[record.pk])), url)
        self.assertNotContains(self.client.get(reverse("my_hearing")), "配戴狀態比較")

    def test_ioi_ha_offers_no_comparison(self):
        ioi = self.questionnaire("ioi-ha", 7)
        self.record(ioi, True, [3] * 7, norm_group=NormGroup.UNGROUPED)
        self.assertEqual(self.client.get(reverse("hhi_comparison", args=[ioi.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("my_hearing")), "配戴狀態比較")

    def _options(self, page, field):
        # #190: one radio card per record.
        return re.findall(
            rf'<input type="radio" name="{field}" value="(\d+)"[^>]*>\s*(.*?)</label>', page, re.S
        )

    def _when(self, record):
        return timezone.localtime(record.created_at).strftime("%Y/%m/%d %H:%M")

    def test_hhi_choices_list_complete_records_with_their_totals(self):
        hhia = self.questionnaire("hhia-s", 10)
        unaided = self.record(hhia, False, [4] * 10)
        aided = self.record(hhia, True, [2] * 9 + [0])
        self.record(hhia, True, [2] * 10).answers.first().delete()  # incomplete: not offered
        self.record(hhia, True, [2] * 9 + [1])  # not an HHI answer: not offered
        page = self.client.get(reverse("hhi_comparison", args=[hhia.pk])).content.decode()
        self.assertEqual(
            self._options(page, "unaided"),
            [(str(unaided.pk), f"{self._when(unaided)}・40 分")],
        )
        self.assertEqual(
            self._options(page, "aided"),
            [(str(aided.pk), f"{self._when(aided)}・18 分")],
        )

    def test_ssq12_choices_list_records_with_all_twelve_answers(self):
        ssq = self.questionnaire("ssq12-tw", 12)
        unaided = self.record(ssq, False, [4] * 11 + [8])
        not_applicable = self.record(ssq, False, [None] * 12)
        aided = self.record(ssq, True, [5] * 11 + [None])
        self.record(ssq, True, [6] * 12).answers.first().delete()  # incomplete: not offered
        page = self.client.get(reverse("hhi_comparison", args=[ssq.pk])).content.decode()
        self.assertEqual(
            self._options(page, "unaided"),
            [
                (str(not_applicable.pk), f"{self._when(not_applicable)}・未計算：沒有可用數值回答"),
                (str(unaided.pk), f"{self._when(unaided)}・平均 4.3 分"),
            ],
        )
        self.assertEqual(
            self._options(page, "aided"),
            [(str(aided.pk), f"{self._when(aided)}・未計算：包含不適用題目")],
        )

    def test_ssq12_report_summary_shows_the_average_difference_only(self):
        ssq = self.questionnaire("ssq12-tw", 12)
        unaided = self.record(ssq, False, [4] * 11 + [8])
        aided = self.record(ssq, True, [4] * 10 + [6, 10])
        self.client.post(
            reverse("hhi_comparison", args=[ssq.pk]),
            {"unaided": unaided.pk, "aided": aided.pk, "action": "save"},
        )
        report = self.client.get(reverse("health_report")).content.decode()
        self.assertIn("<li>報告保留比較（SSQ12-TW）：+0.3 分</li>", report)
        self.assertRegex(report, r'<section id="report-comparison-ssq12-tw"')
