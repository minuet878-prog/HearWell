"""Each result type's result object (spec #385, ticket #387): what submission.result answers."""

import inspect
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db.models import Prefetch, QuerySet
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from screening import questionnaires
from screening.api import serializers
from screening.models import Answer, NormGroup, Questionnaire, ReportShare, Submission
from screening.questionnaires import definition, hhia_s, hhie_s, ioi_ha, sadl, ssq12_tw, thi
from screening.questionnaires.results import (
    AverageResult,
    GradedResult,
    NormResult,
    SubscaleResult,
)
from screening.tests.helpers import consented_user, submission_with_answers
from screening.views import reports


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
        # The download's fields, in the file's order.
        self.assertEqual(
            list(result.export().items()),
            [
                ("total_score", 16),
                ("emotional_score", 12),
                ("social_score", 4),
                ("level", "輕度到中度影響"),
                ("norm_group", None),
            ],
        )
        self.assertIsNone(result.not_applicable_choice)

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
        self.assertEqual(
            result.export(),
            {
                "total_score": 100,
                "emotional_score": None,
                "social_score": None,
                "level": "極重度障礙",
                "norm_group": None,
            },
        )

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
        self.assertEqual(
            list(result.export().items()),
            [
                ("total_score", None),
                ("emotional_score", None),
                ("social_score", None),
                ("level", None),
                ("norm_group", None),
                ("average_score", "6.5"),
                ("average_unavailable_reason", None),
            ],
        )
        self.assertEqual(result.not_applicable_choice, "不適用")

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
        self.assertIsNone(result.export()["average_score"])
        self.assertEqual(result.export()["average_unavailable_reason"], "未計算：包含不適用題目")

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
        self.assertEqual(
            result.export(),
            {
                "total_score": None,
                "emotional_score": None,
                "social_score": None,
                "level": None,
                "norm_group": "輕度至中度",
            },
        )
        self.assertIsNone(result.not_applicable_choice)

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
        self.assertEqual(
            list(result.export().items())[5:],
            [
                ("overall_score", "4.4"),
                (
                    "subscale_scores",
                    {"正面效果": "5.0", "服務與費用": "5.0", "負面特徵": "3.0", "個人形象": "3.7"},
                ),
            ],
        )
        self.assertEqual(result.not_applicable_choice, "不適用")

    def test_result_page_and_summary(self):
        record = submission_with_answers(
            self.user, sadl.CODE, [4] * 15, wearing_hearing_aid=True
        )
        self.assert_page(record, "screening/sadl_result.html")
        self.assertEqual(record.result.summary_template, "screening/sadl_overall.html")
        summary = render_to_string(record.result.summary_template, {"submission": record})
        self.assertEqual(summary, "整體滿意度：4.0")


class ResultQueryTests(ResultTestCase):
    def test_a_list_asks_its_result_objects_without_querying(self):
        # Lists (我的紀錄, the report, the API) score with with_scores() and prefetch the answers;
        # only one record's extras (lowest answers, the norm summary) may query when asked.
        sadl_scores = [4] * 15
        sadl_scores[10] = None
        for code, scores, fields in (
            (hhie_s.CODE, [2] * 10, {}),
            (thi.CODE, [2] * 25, {}),
            (ssq12_tw.CODE, [None] + [3] * 11, {}),
            (ioi_ha.CODE, [3] * 7, {"norm_group": NormGroup.UNGROUPED}),
            (sadl.CODE, sadl_scores, {}),
        ):
            submission_with_answers(self.user, code, scores, **fields)
        records = list(
            Submission.objects.filter(user=self.user)
            .select_related("questionnaire")
            .prefetch_related(
                Prefetch("answers", queryset=Answer.objects.select_related("question"))
            )
            .with_scores()
        )
        with self.assertNumQueries(0):
            for record in records:
                result = record.result
                for name in (
                    "total",
                    "subscores",
                    "level",
                    "average",
                    "unavailable_reason",
                    "satisfaction",
                    "norm_group",
                    "summary_template",
                ):
                    getattr(result, name)
                result.export()


class DefinitionResultTypeTests(TestCase):
    def test_each_definition_names_its_result_type(self):
        self.assertEqual(
            {code: d.result for code, d in questionnaires.DEFINITIONS.items()},
            {
                hhie_s.CODE: GradedResult,
                hhia_s.CODE: GradedResult,
                thi.CODE: GradedResult,
                ssq12_tw.CODE: AverageResult,
                ioi_ha.CODE: NormResult,
                sadl.CODE: SubscaleResult,
            },
        )

    def test_the_old_names_still_compare(self):
        # Until #391 every `result == LEVEL` and the like keeps working.
        self.assertEqual(thi.DEFINITION.result, definition.LEVEL)
        self.assertNotEqual(thi.DEFINITION.result, definition.AVERAGE)
        self.assertTrue(ssq12_tw.DEFINITION.averaged)
        self.assertIn(sadl.DEFINITION.result, (definition.SUBSCALES, definition.NORM))

    def test_templates_see_the_type_without_making_one(self):
        template = Template("{{ d.result.page_template }}")
        context = Context({"d": hhie_s.DEFINITION})
        self.assertEqual(template.render(context), "screening/result.html")


class ApiFieldsTests(ResultTestCase):
    # #390: the API and the hearing report ask the result object; their output is pinned here as
    # it was before (every type, more than one record of each).
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        sadl_scores = [5] * 15
        sadl_scores[10] = sadl_scores[13] = None
        start = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)  # 17:00 in Taipei
        for day, (code, scores, fields) in enumerate(
            (
                (hhie_s.CODE, [4, 4, 2, 0, 0, 0, 4, 0, 0, 2], {"wearing_hearing_aid": False}),
                (hhie_s.CODE, [0] * 10, {"wearing_hearing_aid": True}),
                (thi.CODE, [4] * 25, {}),
                (thi.CODE, [2] * 25, {}),
                (
                    ssq12_tw.CODE,
                    [5, 6, 7, 8, 9, 10, 5, 6, 7, 4, 5, 6],
                    {"wearing_hearing_aid": True},
                ),
                (ssq12_tw.CODE, [None] + [3] * 11, {"wearing_hearing_aid": False}),
                (sadl.CODE, sadl_scores, {"wearing_hearing_aid": True}),
                (sadl.CODE, [4] * 15, {"wearing_hearing_aid": True}),
                (ioi_ha.CODE, [3] * 7, {"norm_group": NormGroup.UNGROUPED}),
                (ioi_ha.CODE, [1, 3, 3, 2, 3, 3, 5], {"norm_group": NormGroup.MILD_MODERATE}),
            )
        ):
            record = submission_with_answers(cls.user, code, scores, **fields)
            Submission.objects.filter(pk=record.pk).update(created_at=start + timedelta(days=day))

    def setUp(self):
        self.client.force_login(self.user)

    # Each record's fields after id and created_at, newest first; IOI-HA is not listed (#245).
    LISTED = (
        {
            "questionnaire": {"code": "sadl", "name": "SADL"},
            "wearing_hearing_aid": True,
            "scores": None,
            "level": None,
            "satisfaction": {
                "overall": "4.0",
                "subscales": [
                    {"name": "正面效果", "score": "4.0"},
                    {"name": "服務與費用", "score": "4.0"},
                    {"name": "負面特徵", "score": "4.0"},
                    {"name": "個人形象", "score": "4.0"},
                ],
                "not_applicable": [],
            },
        },
        {
            "questionnaire": {"code": "sadl", "name": "SADL"},
            "wearing_hearing_aid": True,
            "scores": None,
            "level": None,
            "satisfaction": {
                "overall": "4.4",
                "subscales": [
                    {"name": "正面效果", "score": "5.0"},
                    {"name": "服務與費用", "score": "5.0"},
                    {"name": "負面特徵", "score": "3.0"},
                    {"name": "個人形象", "score": "3.7"},
                ],
                "not_applicable": [11, 14],
            },
        },
        {
            "questionnaire": {"code": "ssq12-tw", "name": "SSQ12-TW"},
            "wearing_hearing_aid": False,
            "scores": None,
            "level": None,
            "average_score": None,
            "average_unavailable_reason": "未計算：包含不適用題目",
        },
        {
            "questionnaire": {"code": "ssq12-tw", "name": "SSQ12-TW"},
            "wearing_hearing_aid": True,
            "scores": None,
            "level": None,
            "average_score": "6.5",
            "average_unavailable_reason": None,
        },
        {
            "questionnaire": {"code": "thi", "name": "THI"},
            "wearing_hearing_aid": None,
            "scores": {"total": 50, "emotional": None, "social": None},
            "level": {"code": "moderate", "text": "中度障礙"},
        },
        {
            "questionnaire": {"code": "thi", "name": "THI"},
            "wearing_hearing_aid": None,
            "scores": {"total": 100, "emotional": None, "social": None},
            "level": {"code": "catastrophic", "text": "極重度障礙"},
        },
        {
            "questionnaire": {"code": "hhie-s", "name": "HHIE-S"},
            "wearing_hearing_aid": True,
            "scores": {"total": 0, "emotional": 0, "social": 0},  # all 0 is 0, not null
            "level": {"code": "normal", "text": "無／極輕微影響"},
        },
        {
            "questionnaire": {"code": "hhie-s", "name": "HHIE-S"},
            "wearing_hearing_aid": False,
            "scores": {"total": 16, "emotional": 12, "social": 4},
            "level": {"code": "mild_to_moderate", "text": "輕度到中度影響"},
        },
    )
    ANSWER_COUNTS = (15, 15, 12, 12, 25, 25, 10, 10)

    def test_the_list_answers_as_before(self):
        records = self.client.get(reverse("api:submissions")).json()["results"]
        self.assertEqual(
            [{k: v for k, v in r.items() if k not in ("id", "created_at")} for r in records],
            list(self.LISTED),
        )
        self.assertEqual([list(r)[:2] for r in records], [["id", "created_at"]] * len(self.LISTED))

    def test_each_detail_answers_as_before(self):
        advice = {
            "hhie-s": hhie_s.DEFINITION.advice,
            "thi": thi.DEFINITION.advice,
        }
        records = self.client.get(reverse("api:submissions")).json()["results"]
        for listed, expected, count in zip(records, self.LISTED, self.ANSWER_COUNTS, strict=True):
            with self.subTest(code=expected["questionnaire"]["code"], id=listed["id"]):
                detail = self.client.get(reverse("api:submission", args=[listed["id"]])).json()
                # The list's fields in the same order, then advice and the answers.
                self.assertEqual(list(detail), [*listed, "advice", "answers"])
                self.assertEqual({k: detail[k] for k in listed}, listed)
                self.assertEqual(len(detail["answers"]), count)
                level = expected["level"]
                self.assertEqual(
                    detail["advice"],
                    advice[expected["questionnaire"]["code"]][level["code"]] if level else None,
                )

    def test_an_ioi_ha_submit_answers_without_scores(self):
        page = self.client.get(reverse("screening", args=[self.ioi_ha().pk]))
        body = {
            "questionnaire": self.ioi_ha().pk,
            "norm_token": page.context["norm_token"],
            "answers": [{"question": q.pk, "score": 3} for q in self.ioi_ha().questions.all()],
        }
        response = self.client.post(
            reverse("api:submissions"),
            json.dumps(body),
            content_type="application/json",
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(
            list(data),
            [
                "id",
                "created_at",
                "questionnaire",
                "wearing_hearing_aid",
                "scores",
                "level",
                "advice",
                "answers",
            ],
        )
        self.assertEqual(
            {k: data[k] for k in ("questionnaire", "wearing_hearing_aid", "scores", "level")},
            {
                "questionnaire": {"code": "ioi-ha", "name": "IOI-HA"},
                "wearing_hearing_aid": None,
                "scores": None,
                "level": None,
            },
        )
        self.assertIsNone(data["advice"])
        self.assertEqual(len(data["answers"]), 7)

    def ioi_ha(self):
        return Questionnaire.objects.get(code=ioi_ha.CODE)

    def report_pages(self):
        share = ReportShare.objects.create(user=self.user)
        for name, args in (("health_report", []), ("shared_report", [share.token])):
            with self.subTest(page=name):
                yield self.client.get(reverse(name, args=args)).content.decode()

    def test_the_report_shows_each_type_as_before(self):
        for html in self.report_pages():
            for line in (
                # 重點: each type's latest record.
                '<li>HHIE-S（2026/01/02）：0 分，<span class="report-level '
                'report-level-normal">無／極輕微影響</span>，助聽器：有戴</li>',
                '<li>THI（2026/01/04）：50 分，<span class="report-level '
                'report-level-mild_to_moderate">中度障礙</span>，助聽器：未記錄</li>',
                "<li>日常聆聽能力（SSQ12-TW，2026/01/06）：未計算：包含不適用題目</li>",
                "<li>助聽器滿意度（SADL，2026/01/08）：整體滿意度 4.0</li>",
                "<li>IOI-HA（2026/01/10）：7 項中 1 項低於常模、1 項高於常模</li>",
                # The graded parts: subscores only for life impact, every record in the table.
                "<p>情緒 0、社交 0（分項僅供參考）　助聽器：有戴</p>",
                '<td role="cell" data-label="總分">16</td>'
                '<td role="cell" data-label="分級">輕度到中度影響</td>',
                '<td role="cell" data-label="總分">100</td>'
                '<td role="cell" data-label="分級">極重度障礙</td>',
                # The average and subscale parts' recent records.
                "<ul><li>2026/01/06 17:00，沒戴：未計算：包含不適用題目</li>"
                "<li>2026/01/05 17:00，有戴：平均 6.5 分</li></ul>",
                "<ul><li>2026/01/08 17:00，有戴：整體滿意度 4.0</li>"
                "<li>2026/01/07 17:00，有戴：整體滿意度 4.4</li></ul>",
                # The norm part: the latest IOI-HA against its fixed group.
                '<p class="mb-1">常模組別：輕度至中度</p>',
                '<td role="cell" data-label="項目">使用時間</td><td role="cell" data-label="回答">'
                '沒使用</td><td role="cell" data-label="與常模比較">低於常模</td>',
            ):
                self.assertIn(line, html)
            self.assertNotIn("情緒 0、社交 0（分項僅供參考）　助聽器：未記錄", html)  # THI

    def test_lists_take_the_same_queries(self):
        # Counts measured before #390 with these records.
        share = ReportShare.objects.create(user=self.user)
        for url, queries in (
            (reverse("api:submissions"), 5),
            (reverse("health_report"), 46),
            (reverse("shared_report", args=[share.token]), 47),
        ):
            with self.subTest(url=url), self.assertNumQueries(queries):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_the_api_and_the_report_ask_the_result_object(self):
        # The serializer names no result type; the report groups by result type class (ADR 0036).
        report_types = {"GradedResult", "AverageResult", "SubscaleResult", "NormResult"}
        for module, allowed in ((serializers, set()), (reports, report_types)):
            with self.subTest(module=module.__name__):
                source = inspect.getsource(module)
                names = set(re.findall(r"\b(LEVEL|AVERAGE|NORM|SUBSCALES|\w+Result)\b", source))
                self.assertEqual(names, allowed)
