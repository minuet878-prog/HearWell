"""Each result type's result object (spec #385, ticket #387): what submission.result answers."""

import re
from datetime import datetime
from decimal import Decimal
from io import StringIO
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.db.models import Prefetch, QuerySet
from django.template import Context, Template
from django.template.loader import get_template, render_to_string
from django.test import TestCase
from django.urls import reverse

from screening import questionnaires
from screening.models import Answer, NormGroup, Submission
from screening.questionnaires import definition, hhia_s, hhie_s, ioi_ha, sadl, ssq12_tw, thi
from screening.questionnaires.results import (
    AverageResult,
    GradedResult,
    NormResult,
    SubscaleResult,
)
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
        record = submission_with_answers(self.user, sadl.CODE, [4] * 15, wearing_hearing_aid=True)
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


class SummaryTemplateTests(ResultTestCase):
    """#389: the home page's last result and each row of 我的紀錄 draw the record's summary
    template. The expected HTML is each page as rendered before the change, spaces aside."""

    ARROW = '<span aria-hidden="true">\u203a</span>'  # the links' arrow (U+203A)

    SADL_NOT_APPLICABLE = [4] * 15
    SADL_NOT_APPLICABLE[10] = None
    # Two records of each type, older first: (code, scores, fields, Taipei date).
    RECORDS = (
        (hhie_s.CODE, [2] * 10, {"wearing_hearing_aid": False}, (2026, 3, 1)),
        (hhie_s.CODE, [4] * 10, {"wearing_hearing_aid": False}, (2026, 4, 1)),
        (thi.CODE, [2] * 25, {"wearing_hearing_aid": True}, (2026, 3, 2)),
        (thi.CODE, [4] * 25, {"wearing_hearing_aid": None}, (2026, 4, 2)),
        (ssq12_tw.CODE, [None] + [3] * 11, {"wearing_hearing_aid": False}, (2026, 3, 3)),
        (ssq12_tw.CODE, [5] * 12, {"wearing_hearing_aid": True}, (2026, 4, 3)),
        (ioi_ha.CODE, [4] * 7, {"norm_group": NormGroup.UNGROUPED}, (2026, 3, 4)),
        (ioi_ha.CODE, [3] * 7, {"norm_group": NormGroup.MILD_MODERATE}, (2026, 4, 4)),
        (sadl.CODE, SADL_NOT_APPLICABLE, {"wearing_hearing_aid": True}, (2026, 3, 5)),
        (sadl.CODE, [5] * 15, {"wearing_hearing_aid": True}, (2026, 4, 5)),
    )

    def record(self, user, code, scores, fields, day):
        submission = submission_with_answers(user, code, scores, **fields)
        created = datetime(*day, 10, tzinfo=ZoneInfo("Asia/Taipei"))
        Submission.objects.filter(pk=submission.pk).update(created_at=created)
        return submission

    def home_banner(self, user):
        self.client.force_login(user)
        html = self.client.get(reverse("index")).content.decode()
        return re.search(
            r'<div class="result-banner result-banner-.*?看這次結果'
            + re.escape(self.ARROW)
            + r"</a>\s*</div>",
            html,
            re.S,
        ).group(0)

    def my_hearing(self, code):
        self.client.force_login(self.user)
        html = self.client.get(reverse("my_hearing"), {"questionnaire": code}).content.decode()
        rows = re.findall(r'<a class="link-card" href="[^"]*">.*?</a>', html, re.S)
        since_last = re.search(r'<section id="since-last".*?</section>', html, re.S)
        return rows, since_last and since_last.group(0)

    def test_home_shows_a_life_impact_last_result_with_its_gauge_and_level(self):
        user = consented_user(username="home_hhie_s")
        record = self.record(user, *self.RECORDS[0])
        self.assertHTMLEqual(
            self.home_banner(user),
            '<div class="result-banner result-banner-mild_to_moderate"><div>上次結果</div>'
            '<svg class="score-gauge" viewBox="0 0 220 130" aria-hidden="true" focusable="false"'
            ' data-play-in-view style="--angle: 90.00deg">'
            '<path class="score-gauge-arc score-gauge-arc-normal" pathLength="1"'
            ' d="M30.00 105.00A80 80 0 0 1 44.55 59.00"/>'
            '<path class="score-gauge-arc score-gauge-arc-mild_to_moderate" pathLength="1"'
            ' d="M46.03 56.97A80 80 0 0 1 133.52 28.54"/>'
            '<path class="score-gauge-arc score-gauge-arc-severe" pathLength="1"'
            ' d="M135.91 29.31A80 80 0 0 1 190.00 105.00"/>'
            '<line class="score-gauge-needle" x1="110" y1="105" x2="52" y2="105"/>'
            '<circle class="score-gauge-hub" cx="110" cy="105" r="7"/>'
            '<text x="30" y="126">0</text><text x="190" y="126">40</text></svg>'
            '<h2 class="result-level mb-0">輕度到中度影響</h2>'
            "<div>HHIE-S 總分 20 分（滿分 40）</div>"
            f'<a class="welcome-result-link" href="{reverse("result", args=[record.pk])}">'
            f"看這次結果{self.ARROW}</a></div>",
        )

    def test_home_shows_another_last_result_by_its_type(self):
        # THI is graded but not life impact: its topic only, no summary.
        for index, summary in (
            (2, '<h2 class="result-level mb-0">耳鳴對生活的影響（THI）</h2>'),
            (
                4,
                '<h2 class="result-level mb-0">日常聆聽能力（SSQ12-TW）</h2>'
                "<div>未計算：包含不適用題目</div>",
            ),
            (
                5,
                '<h2 class="result-level mb-0">日常聆聽能力（SSQ12-TW）</h2>'
                "<div>整體平均：5.0／10</div>",
            ),
            (
                6,
                '<h2 class="result-level mb-0">助聽器使用成效（IOI-HA）</h2>'
                "<div>未分組，無法和常模比較</div>",
            ),
            (
                7,
                '<h2 class="result-level mb-0">助聽器使用成效（IOI-HA）</h2>'
                "<div>7 項中 0 項低於常模、0 項高於常模</div>",
            ),
            (
                8,
                '<h2 class="result-level mb-0">助聽器滿意度（SADL）</h2><div>整體滿意度：4.0</div>',
            ),
        ):
            with self.subTest(record=self.RECORDS[index][:2]):
                user = consented_user(username=f"home_{index}")
                record = self.record(user, *self.RECORDS[index])
                self.assertHTMLEqual(
                    self.home_banner(user),
                    '<div class="result-banner result-banner-unknown"><div>上次結果</div>'
                    f"{summary}"
                    f'<a class="welcome-result-link" href="{reverse("result", args=[record.pk])}">'
                    f"看這次結果{self.ARROW}</a></div>",
                )

    def test_my_hearing_rows_and_since_last_by_type(self):
        records = [self.record(self.user, *fields) for fields in self.RECORDS]

        def row(index, date, summary):
            href = reverse("result", args=[records[index].pk])
            return (
                f'<a class="link-card" href="{href}"><span class="link-card-body">'
                f"<strong>{date}</strong>{summary}</span>"
                f'<span class="link-card-arrow" aria-hidden="true">\u203a</span></a>'
            )

        def since_last(previous, latest, text):
            def cell(label, date, score, newest=""):
                return (
                    f'<p class="since-last-cell{newest}"><span class="since-last-label">{label}'
                    '</span><span class="since-last-date"><span class="visually-hidden">（</span>'
                    f'{date}<span class="visually-hidden">）：</span></span>'
                    f'<span class="since-last-score">{score}<span class="since-last-unit"> 分'
                    "</span></span></p>"
                )

            return (
                '<section id="since-last" class="since-last mb-6 wrap-anywhere"'
                ' aria-labelledby="since-last-title">'
                '<h2 id="since-last-title" class="h4">和上一次比</h2>'
                f'<div class="since-last-pair">{cell("上一次", *previous)}'
                '<span class="since-last-arrow" aria-hidden="true">→</span>'
                f"{cell('最近一次', *latest, newest=' since-last-latest')}</div>"
                f'<p class="mb-0 text-subhead text-heading"><strong>{text}</strong></p>'
                "</section>"
            )

        def badge(level, text):
            return f'<span><span class="level-badge level-badge-{level}">{text}</span></span>'

        for code, expected_rows, expected_since_last in (
            (
                hhie_s.CODE,
                [
                    row(
                        1,
                        "2026/04/01",
                        "<span>總分：40　助聽器：沒戴</span>" + badge("severe", "顯著影響"),
                    ),
                    row(
                        0,
                        "2026/03/01",
                        "<span>總分：20　助聽器：沒戴</span>"
                        + badge("mild_to_moderate", "輕度到中度影響"),
                    ),
                ],
                since_last(
                    ("2026/03/01", 20), ("2026/04/01", 40), "比上一次多 20 分（分數越低越好）"
                ),
            ),
            (
                thi.CODE,
                [
                    row(
                        3,
                        "2026/04/02",
                        "<span>總分：100　助聽器：未記錄</span>" + badge("severe", "極重度障礙"),
                    ),
                    row(
                        2,
                        "2026/03/02",
                        "<span>總分：50　助聽器：有戴</span>"
                        + badge("mild_to_moderate", "中度障礙"),
                    ),
                ],
                since_last(
                    ("2026/03/02", 50), ("2026/04/02", 100), "比上一次多 50 分（分數越低越好）"
                ),
            ),
            (
                ssq12_tw.CODE,
                [
                    row(5, "2026/04/03", "<span>整體平均：5.0／10</span><span>助聽器：有戴</span>"),
                    row(
                        4,
                        "2026/03/03",
                        "<span>未計算：包含不適用題目</span><span>助聽器：沒戴</span>",
                    ),
                ],
                None,
            ),
            (
                ioi_ha.CODE,
                [
                    row(7, "2026/04/04", "<span>IOI-HA　常模組別：輕度至中度</span>"),
                    row(6, "2026/03/04", "<span>IOI-HA　常模組別：未分組</span>"),
                ],
                None,
            ),
            (
                sadl.CODE,
                [
                    row(9, "2026/04/05", "<span>整體滿意度：4.5</span>"),
                    row(8, "2026/03/05", "<span>整體滿意度：4.0</span>"),
                ],
                None,
            ),
        ):
            with self.subTest(code=code):
                rows, since = self.my_hearing(code)
                self.assertEqual(len(rows), len(expected_rows))
                for html, expected in zip(rows, expected_rows, strict=True):
                    self.assertHTMLEqual(html, expected)
                if expected_since_last is None:
                    self.assertIsNone(since)
                else:
                    self.assertHTMLEqual(since, expected_since_last)

    def test_the_pages_include_the_summary_template_instead_of_asking_the_type(self):
        # The IOI-HA chart of 我的紀錄 (ioi_ha_chart) goes by its questionnaire, not its type.
        type_check = re.compile(
            r"{%\s*(?:el)?if\b[^%]*\b(?:averaged|satisfaction|norm_group|ioi_ha|classified)\b"
        )
        for name, place in (
            ("screening/index.html", "home"),
            ("screening/my_hearing.html", "records"),
        ):
            with self.subTest(template=name):
                source = get_template(name).template.source
                self.assertIn(
                    f'{{% include submission.result.summary_template with place="{place}"', source
                )
                self.assertIsNone(type_check.search(source))

    def test_my_hearing_takes_the_same_queries_for_two_or_four_records_of_each_type(self):
        # Counts measured before the change; 我的紀錄's HHIE-S tab is test_thi's 8.
        self.client.force_login(self.user)
        for round_ in range(2):
            for code, scores, fields, (year, month, day) in self.RECORDS:
                self.record(self.user, code, scores, fields, (year, month + 2 * round_, day))
            for code, queries in (
                (hhie_s.CODE, 8),
                (thi.CODE, 7),
                (ssq12_tw.CODE, 9),
                (ioi_ha.CODE, 8),
                (sadl.CODE, 7),
            ):
                with self.subTest(records=2 * (round_ + 1), code=code):
                    with self.assertNumQueries(queries):
                        self.client.get(reverse("my_hearing"), {"questionnaire": code})

    def test_home_takes_the_same_queries_for_each_last_result_type(self):
        # Counts measured before the change. SADL's satisfaction reads each answer's question.
        for index, queries in ((0, 9), (2, 9), (4, 9), (6, 10), (8, 25)):
            code, scores, fields, (year, month, day) = self.RECORDS[index]
            user = consented_user(username=f"home_queries_{index}")
            for older in range(2):
                self.record(user, code, scores, fields, (year, month, day + older))
            self.client.force_login(user)
            with self.subTest(code=code), self.assertNumQueries(queries):
                self.client.get(reverse("index"))
