"""Each result type's result object (spec #385, ticket #387): what submission.result answers."""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db.models import QuerySet
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from screening.models import NormGroup
from screening.questionnaires import hhie_s, ioi_ha, sadl, ssq12_tw, thi
from screening.tests.helpers import consented_user, submission_with_answers


class ResultTestCase(TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S and IOI-HA

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        cls.user = consented_user(username="result_types")

    def assert_page(self, record, template):
        """The result page draws this template with the result object's data (#388 switches)."""
        result = record.result
        self.assertEqual(result.page_template, template)
        self.client.force_login(self.user)
        response = self.client.get(reverse("result", args=[record.pk]))
        self.assertTemplateUsed(response, template)
        context = result.page_context()
        for key, value in context.items():
            with self.subTest(key=key):
                page_value = response.context[key]
                if isinstance(value, QuerySet):
                    value, page_value = list(value), list(page_value)
                self.assertEqual(value, page_value)
        return context

    def assert_none(self, result, *names):
        for name in names:
            with self.subTest(name=name):
                self.assertIsNone(getattr(result, name))


class GradedResultTests(ResultTestCase):
    def test_hhie_s_answers_total_subscores_and_level(self):
        # Emotional items 1, 2, 4, 7, 9; social items 3, 5, 6, 8, 10 (the fixture).
        record = submission_with_answers(
            self.user, hhie_s.CODE, [4, 4, 2, 0, 0, 0, 4, 0, 0, 2], wearing_hearing_aid=False
        )
        result = record.result
        self.assertEqual(result.total, 16)
        self.assertEqual(result.subscores, {"emotional": 12, "social": 4})
        self.assertEqual(
            result.level,
            {"text": "輕度到中度影響", "level": "mild_to_moderate", "color": "mild_to_moderate"},
        )
        self.assert_none(
            result, "average", "unavailable_reason", "satisfaction", "norm_group", "norm_summary"
        )
        self.assertEqual(result.lowest_answers, [])

    def test_hhie_s_result_page_and_summary(self):
        record = submission_with_answers(
            self.user, hhie_s.CODE, [4, 4, 2, 0, 0, 0, 4, 0, 0, 2], wearing_hearing_aid=False
        )
        context = self.assert_page(record, "screening/result.html")
        self.assertEqual(context["total_score"], 16)
        self.assertEqual((context["emotional"], context["social"]), (12, 4))
        self.assertEqual(context["max_score"], 40)
        self.assertEqual(context["classified_score_text"], "輕度到中度影響")
        self.assertEqual(context["score_bar"]["current_text"], "輕度到中度影響")
        self.assertTrue(context["advice"])
        self.assertEqual(context["optional_ssq12"].code, ssq12_tw.CODE)  # unaided HHIE-S
        summary = render_to_string(record.result.summary_template, {"submission": record})
        self.assertIn("總分：16　助聽器：沒戴", summary)
        self.assertIn("輕度到中度影響", summary)

    def test_all_zero_subscores_are_zero_not_none(self):
        record = submission_with_answers(self.user, hhie_s.CODE, [0] * 10)
        self.assertEqual(record.result.total, 0)
        self.assertEqual(record.result.subscores, {"emotional": 0, "social": 0})

    def test_thi_has_a_total_and_level_but_no_subscores(self):
        record = submission_with_answers(self.user, thi.CODE, [4] * 25)
        result = record.result
        self.assertEqual(result.total, 100)
        self.assertEqual(result.level["level"], "catastrophic")
        self.assertIsNone(result.subscores)

    def test_thi_result_page_has_its_support_message(self):
        # Item 5 answered 經常 (4): the support message, whatever the total (spec #208 Q6).
        record = submission_with_answers(self.user, thi.CODE, [0] * 4 + [4] + [0] * 20)
        context = self.assert_page(record, "screening/result.html")
        self.assertFalse(context["has_subscores"])
        self.assertTrue(context["support_message"])
        self.assertIsNone(context["optional_ssq12"])


class AverageResultTests(ResultTestCase):
    def test_answers_the_average_and_lowest_answers(self):
        record = submission_with_answers(
            self.user, ssq12_tw.CODE, [5, 6, 7, 8, 9, 10, 5, 6, 7, 4, 5, 6]
        )
        result = record.result
        self.assertEqual(result.average, Decimal("6.5"))
        self.assertEqual(
            [(a.question.question_number, a.score) for a in result.lowest_answers],
            [(10, 4), (1, 5), (7, 5)],
        )
        self.assert_none(
            result,
            "total",
            "subscores",
            "level",
            "unavailable_reason",
            "satisfaction",
            "norm_group",
            "norm_summary",
        )

    def test_result_page_and_summary(self):
        record = submission_with_answers(self.user, ssq12_tw.CODE, [6] * 12)
        context = self.assert_page(record, "screening/ssq12_result.html")
        self.assertEqual(len(context["answers"]), 12)
        self.assertEqual(record.result.summary_template, "screening/ssq_average.html")
        summary = render_to_string(record.result.summary_template, {"submission": record})
        self.assertEqual(summary, "整體平均：6.0／10")

    def test_not_applicable_leaves_no_average_and_says_why(self):
        record = submission_with_answers(self.user, ssq12_tw.CODE, [None] + [3] * 11)
        result = record.result
        self.assertIsNone(result.average)
        # ADR 0001's wording.
        self.assertEqual(result.unavailable_reason, "未計算：包含不適用題目")
        self.assertEqual([a.score for a in result.lowest_answers], [3, 3, 3])
        self.assertIsNone(result.total)

    def test_all_not_applicable_has_no_numeric_answer(self):
        record = submission_with_answers(self.user, ssq12_tw.CODE, [None] * 12)
        self.assertEqual(record.result.unavailable_reason, "未計算：沒有可用數值回答")
        self.assertEqual(record.result.lowest_answers, [])


class NormResultTests(ResultTestCase):
    def test_answers_the_norm_group_and_each_item_against_it(self):
        # Mild to moderate norms: item 1 is 3-5, item 7 is 3-4, the rest take these answers.
        record = submission_with_answers(
            self.user, ioi_ha.CODE, [1, 3, 3, 2, 3, 3, 5], norm_group=NormGroup.MILD_MODERATE
        )
        result = record.result
        self.assertEqual(result.norm_group, "輕度至中度")
        summary = result.norm_summary
        self.assertTrue(summary["grouped"])
        self.assertEqual((summary["below"], summary["above"]), (1, 1))
        self.assertEqual(
            [item["comparison_code"] for item in summary["items"]],
            ["below", "within", "within", "within", "within", "within", "above"],
        )
        self.assert_none(
            result, "total", "subscores", "level", "average", "unavailable_reason", "satisfaction"
        )
        self.assertEqual(result.lowest_answers, [])

    def test_result_page_and_summary(self):
        record = submission_with_answers(
            self.user, ioi_ha.CODE, [1, 3, 3, 2, 3, 3, 5], norm_group=NormGroup.MILD_MODERATE
        )
        context = self.assert_page(record, "screening/result_ioi_ha.html")
        self.assertEqual([item["name"] for item in context["below"]], ["使用時間"])
        self.assertEqual(len(context["others"]), 6)
        self.assertEqual(record.result.summary_template, "screening/ioi_ha_summary.html")
        summary = render_to_string(
            record.result.summary_template, {"ioi_ha": record.result.norm_summary}
        )
        self.assertEqual(summary, "7 項中 1 項低於常模、1 項高於常模")

    def test_without_a_norm_basis_nothing_is_compared(self):
        record = submission_with_answers(
            self.user, ioi_ha.CODE, [3] * 7, norm_group=NormGroup.UNGROUPED
        )
        self.assertEqual(record.result.norm_group, "未分組")
        summary = record.result.norm_summary
        self.assertFalse(summary["grouped"])
        self.assertEqual([item["comparison_code"] for item in summary["items"]], [None] * 7)


class SubscaleResultTests(ResultTestCase):
    def test_answers_overall_and_subscale_averages_without_not_applicable_items(self):
        # Items 2, 4, 7 and 13 are reversed (8 - 5 = 3); 11 and 14 are 不適用.
        scores = [5] * 15
        scores[10] = scores[13] = None
        record = submission_with_answers(self.user, sadl.CODE, scores, wearing_hearing_aid=True)
        result = record.result
        satisfaction = result.satisfaction
        self.assertEqual(satisfaction["overall"], Decimal("4.4"))  # 57 / 13
        self.assertEqual(
            [(s["name"], s["score"]) for s in satisfaction["subscales"]],
            [
                ("正面效果", Decimal("5.0")),
                ("服務與費用", Decimal("5.0")),
                ("負面特徵", Decimal("3.0")),
                ("個人形象", Decimal("3.7")),
            ],
        )
        self.assertEqual(satisfaction["not_applicable"], [11, 14])
        self.assert_none(
            result,
            "total",
            "subscores",
            "level",
            "average",
            "unavailable_reason",
            "norm_group",
            "norm_summary",
        )
        self.assertEqual(result.lowest_answers, [])

    def test_result_page_and_summary(self):
        record = submission_with_answers(
            self.user, sadl.CODE, [4] * 15, wearing_hearing_aid=True
        )
        self.assert_page(record, "screening/sadl_result.html")
        self.assertEqual(record.result.summary_template, "screening/sadl_overall.html")
        summary = render_to_string(record.result.summary_template, {"submission": record})
        self.assertEqual(summary, "整體滿意度：4.0")
