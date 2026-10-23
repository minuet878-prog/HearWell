import re
from datetime import date, datetime, timedelta
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.tests.helpers import action_cards, consented_user, fake_definition, register


class TrendChartPageTests(TestCase):
    CHART_JS = "screening/frontend/trend-chart.js"

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="tester")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.question = Question.objects.create(
            questionnaire=cls.questionnaire,
            question_text="第1題",
            question_number=1,
            category=Category.EMOTIONAL,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _make_submission(self):
        submission = Submission.objects.create(user=self.user, questionnaire=self.questionnaire)
        Answer.objects.create(submission=submission, question=self.question, score=4)
        return submission

    def test_questionnaire_levels_come_from_thresholds(self):
        response = self.client.get("/api/questionnaires/")
        self.assertEqual(
            response.json()[0]["levels"],
            [
                {
                    "code": "normal",
                    "text": "無/極輕微影響",
                    "max": 8,
                    "color": "normal",
                    "shade": "pale",
                },
                {
                    "code": "mild_to_moderate",
                    "text": "輕度到中度影響",
                    "max": 24,
                    "color": "mild_to_moderate",
                    "shade": "pale",
                },
                {
                    "code": "severe",
                    "text": "顯著影響",
                    "max": 40,
                    "color": "severe",
                    "shade": "pale",
                },
            ],
        )

    def test_levels_empty_without_thresholds(self):
        Questionnaire.objects.create(questionnaire_name="測試問卷", code="no-thresholds")
        with register(fake_definition("no-thresholds")):
            response = self.client.get("/api/questionnaires/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[1]["levels"], [])

    def test_history_page_works_without_js(self):
        submission = self._make_submission()
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, 'id="trend-chart"')
        self.assertContains(response, "總分：4")
        self.assertContains(response, reverse("result", args=[submission.id]))

    def test_history_page_without_submissions_has_no_chart(self):
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, "您還沒有做過篩檢紀錄")
        self.assertNotContains(response, 'id="trend-chart"')
        self.assertNotContains(response, self.CHART_JS)

    def test_only_history_page_loads_chart_js(self):
        submission = self._make_submission()
        self.assertContains(self.client.get(reverse("my_hearing")), self.CHART_JS)
        pages = [
            reverse("index"),
            reverse("questionnaire_list"),
            reverse("screening", args=[self.questionnaire.id]),
            reverse("result", args=[submission.id]),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), self.CHART_JS)
        self.client.logout()
        for url in (reverse("login"), reverse("register")):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), self.CHART_JS)


class HistoryTabsTests(TestCase):
    """Spec docs/specs/phase-04/phase4_history_by_questionnaire.md, acceptance 1-19."""

    CHART_JS = "screening/frontend/trend-chart.js"
    NOTE = "分數越低，聽力對生活的影響越小"
    UNGROUPED_NOTE = "需要一筆完整有效的未配戴 HHIA-S／HHIE-S 紀錄，才能跟常模比較"
    # Ticket #161: tabs read 「主題（代碼）」.
    HHIE_S_TAB = "聽力對生活的影響（HHIE-S）"
    HHIA_S_TAB = "聽力對生活的影響（HHIA-S）"
    IOI_HA_TAB = "助聽器使用成效（IOI-HA）"

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="tabs_user")
        cls.other = consented_user(username="tabs_other")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhie_questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhie_s,
                question_text=f"HHIE題{i}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        cls.ioi_questions = Question.objects.bulk_create(
            Question(questionnaire=cls.ioi_ha, question_text=f"IOI題{i}", question_number=i)
            for i in range(1, 8)
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("my_hearing")

    def _at(self, submission, days_ago):
        when = timezone.now() - timedelta(days=days_ago)
        Submission.objects.filter(pk=submission.pk).update(created_at=when)
        return submission

    def _hhie_s(self, total, wearing, days_ago, user=None):
        scores = [4] * (total // 4) + [2] * (total % 4 // 2)
        scores += [0] * (10 - len(scores))
        submission = Submission.objects.create(
            user=user or self.user, questionnaire=self.hhie_s, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(self.hhie_questions, scores, strict=True)
        )
        return self._at(submission, days_ago)

    def _ioi_ha(self, scores, group, days_ago, user=None):
        submission = Submission.objects.create(
            user=user or self.user, questionnaire=self.ioi_ha, norm_group=group
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(self.ioi_questions, scores, strict=True)
        )
        return self._at(submission, days_ago)

    def _main_html(self, response):
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _tab_url(self, code):
        return f"{self.url}?questionnaire={code}"

    def _tabs(self, main):
        match = re.search(r'<nav[^>]*aria-label="問卷"[^>]*>(.*?)</nav>', main, re.DOTALL)
        return None if match is None else match.group(1)

    def _tab_labels(self, tabs):
        tabs = re.findall(r"<a[^>]*>(.*?)</a>", tabs, re.S)
        return [re.sub(r"<[^>]+>", "", tab).strip() for tab in tabs]

    def _current_tab(self, tabs):
        # The code is in its own span (text-heavy pages tidy-up); the tab's text is unchanged.
        tab = re.search(r'<a[^>]*aria-current="page"[^>]*>(.*?)</a>', tabs, re.S).group(1)
        return re.sub(r"<[^>]+>", "", tab).strip()

    def _date(self, submission):
        submission.refresh_from_db()
        return timezone.localtime(submission.created_at).strftime("%Y/%m/%d")

    def _both(self, newest):
        hhie = self._hhie_s(10, False, days_ago=5 if newest == "ioi-ha" else 1)
        ioi = self._ioi_ha((3,) * 7, "mild_moderate", days_ago=1 if newest == "ioi-ha" else 5)
        return hhie, ioi

    # Tabs (1-8)
    def test_default_tab_is_newest_ioi_ha(self):
        hhie, ioi = self._both(newest="ioi-ha")
        main = self._main_html(self.client.get(self.url))
        tabs = self._tabs(main)
        labels = self._tab_labels(tabs)
        self.assertEqual(labels, [self.HHIE_S_TAB, self.IOI_HA_TAB])
        self.assertIn(f'href="{self._tab_url("hhie-s")}"', tabs)
        self.assertIn(f'href="{self._tab_url("ioi-ha")}"', tabs)
        self.assertEqual(self._current_tab(tabs), self.IOI_HA_TAB)
        self.assertIn(reverse("result", args=[ioi.id]), main)
        self.assertNotIn(reverse("result", args=[hhie.id]), main)
        self.assertNotIn("trend-chart", main)

    def test_default_tab_is_newest_hhie_s(self):
        hhie, ioi = self._both(newest="hhie-s")
        response = self.client.get(self.url)
        main = self._main_html(response)
        self.assertEqual(self._current_tab(self._tabs(main)), self.HHIE_S_TAB)
        self.assertIn(reverse("result", args=[hhie.id]), main)
        self.assertNotIn(reverse("result", args=[ioi.id]), main)
        self.assertContains(response, self.CHART_JS)
        self.assertIn('data-questionnaire="hhie-s"', main)

    def test_tab_url_shows_that_questionnaire(self):
        hhie, ioi = self._both(newest="ioi-ha")
        response = self.client.get(self._tab_url("hhie-s"))
        main = self._main_html(response)
        self.assertEqual(self._current_tab(self._tabs(main)), self.HHIE_S_TAB)
        self.assertIn(reverse("result", args=[hhie.id]), main)
        self.assertNotIn(reverse("result", args=[ioi.id]), main)
        self.assertContains(response, self.CHART_JS)

    def test_invalid_tab_falls_back_to_default(self):
        self._hhie_s(10, False, days_ago=1)
        Questionnaire.objects.create(questionnaire_name="其他問卷", code="other")
        for value in ("nope", "ioi-ha", "other", "", "%3Cscript%3E", "1"):
            with self.subTest(value=value):
                response = self.client.get(f"{self.url}?questionnaire={value}")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'data-questionnaire="hhie-s"')

    def test_single_questionnaire_has_no_tabs(self):
        self._hhie_s(10, False, days_ago=1)
        main = self._main_html(self.client.get(self.url))
        self.assertIsNone(self._tabs(main))
        self.assertIn('data-questionnaire="hhie-s"', main)

    def test_no_records(self):
        response = self.client.get(self.url)
        main = self._main_html(response)
        self.assertIn("您還沒有做過篩檢紀錄", main)
        self.assertIsNone(self._tabs(main))
        self.assertNotIn("trend-chart", main)
        self.assertNotIn("ioi-chart", main)
        self.assertNotContains(response, self.CHART_JS)

    def test_only_own_records(self):
        self._hhie_s(10, False, days_ago=1)
        theirs_hhie = self._hhie_s(30, False, days_ago=3, user=self.other)
        self._hhie_s(10, True, days_ago=2, user=self.other)
        theirs_ioi = self._ioi_ha((1,) * 7, "moderately_severe", days_ago=0, user=self.other)
        for url in (self.url, self._tab_url("hhie-s"), self._tab_url("ioi-ha")):
            with self.subTest(url=url):
                main = self._main_html(self.client.get(url))
                self.assertIsNone(self._tabs(main))
                self.assertNotIn("配戴前後比較", main)
                self.assertNotIn("ioi-chart", main)
                self.assertNotIn(reverse("result", args=[theirs_hhie.id]), main)
                self.assertNotIn(reverse("result", args=[theirs_ioi.id]), main)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        for url in (self.url, self._tab_url("ioi-ha")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("login")))

    # Aided difference (10-14)
    def _difference(self, main):
        match = re.search(
            r'<section[^>]*class="aided-difference[^"]*"[^>]*>(.*?)</section>', main, re.DOTALL
        )
        return (
            None if match is None else re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group(1)))
        )

    def _retain(self, unaided, aided):
        response = self.client.post(
            f"/comparisons/{self.hhie_s.pk}",
            {"unaided": unaided.pk, "aided": aided.pk, "action": "save"},
        )
        self.assertEqual(response.status_code, 302)

    def test_difference_uses_selected_pair_instead_of_latest(self):
        unaided = self._hhie_s(28, False, days_ago=20)
        aided = self._hhie_s(12, True, days_ago=10)
        self._retain(unaided, aided)
        self._hhie_s(40, False, days_ago=1)
        self._hhie_s(40, True, days_ago=1)
        text = self._difference(self._main_html(self.client.get(self.url)))
        self.assertIn("配戴狀態比較", text)
        self.assertIn(f"未配戴 {self._date(unaided)}，28 分", text)
        self.assertIn(f"配戴 {self._date(aided)}，12 分", text)
        self.assertIn("少了 16 分", text)
        self.assertIn("不一定是開始使用助聽器前後", text)

    def test_difference_ignores_order(self):
        aided = self._hhie_s(12, True, days_ago=10)
        unaided = self._hhie_s(28, False, days_ago=1)
        self._retain(unaided, aided)
        self.assertIn("少了 16 分", self._difference(self._main_html(self.client.get(self.url))))

    def test_difference_of_zero_is_no_change(self):
        self._retain(self._hhie_s(20, False, days_ago=2), self._hhie_s(20, True, days_ago=1))
        text = self._difference(self._main_html(self.client.get(self.url)))
        self.assertIn("沒有變化", text)

    def test_difference_increase_has_no_verdict(self):
        self._retain(self._hhie_s(10, False, days_ago=2), self._hhie_s(16, True, days_ago=1))
        text = self._difference(self._main_html(self.client.get(self.url)))
        self.assertIn("多了 6 分", text)
        for word in ("改善", "變差", "有效", "無效", "建議"):
            self.assertNotIn(word, text)

    def test_no_automatic_difference_even_with_both_statuses(self):
        self._hhie_s(28, False, days_ago=2)
        self._hhie_s(12, True, days_ago=1)
        main = self._main_html(self.client.get(self.url))
        self.assertIn("尚未保留比較組合", main)
        self.assertNotIn("少了 16 分", main)
        self.assertNotContains(self.client.get("/report"), 'id="report-difference"')

    def test_difference_lives_in_the_for_doctor_card(self):
        # Ticket #161: moved to the bottom, alongside the health report button.
        self._hhie_s(28, False, days_ago=2)
        self._hhie_s(12, True, days_ago=1)
        main = self._main_html(self.client.get(self.url))
        self.assertLess(main.index("要給醫師或家人看"), main.index("配戴狀態比較"))
        self.assertLess(main.index("聽力報告"), main.index("配戴狀態比較"))
        # Acceptance 4: the entry reads 「比較戴與不戴助聽器」, inside the bottom card.
        card = main[main.index('aria-labelledby="for-doctor-title"') :]
        self.assertIn(
            f'href="{reverse("hhi_comparison", args=[self.hhie_s.pk])}">比較戴與不戴助聽器</a>',
            card,
        )

    def test_difference_hidden_without_both_statuses(self):
        # Ticket #161: only shown when this questionnaire has both an aided and unaided record.
        self._hhie_s(28, False, days_ago=2)
        self._hhie_s(30, False, days_ago=1)
        main = self._main_html(self.client.get(self.url))
        self.assertNotIn("配戴狀態比較", main)
        self.assertIsNone(self._difference(main))

    # IOI-HA chart (15-18)
    def _chart(self, main):
        start = main.index('class="ioi-chart')
        return main[start : main.index("<!-- /ioi-chart -->", start)]

    def test_chart_bands_follow_latest_group(self):
        self._ioi_ha((5, 4, 3, 2, 4, 3, 4), "moderately_severe", days_ago=1)
        chart = self._chart(self._main_html(self.client.get(self._tab_url("ioi-ha"))))
        self.assertEqual(chart.count('class="ioi-band"'), 7)
        self.assertEqual(chart.count("ioi-dot-latest"), 7)
        self.assertEqual(chart.count("ioi-dot-previous"), 0)
        self.assertIn("常模組別：中重度以上", chart)
        names = ("使用時間", "幫助程度", "剩餘困難", "值得程度", "生活影響", "干擾他人", "生活樂趣")
        for name in names:
            self.assertIn(name, chart)
        # Screen reader text per item: moderately_severe Use is 4-5, Sat is 3-5.
        self.assertIn("使用時間：最近一次 5 分，常模 4 到 5 分，在範圍內", chart)
        self.assertIn("值得程度：最近一次 2 分，常模 3 到 5 分，低於常模", chart)

    def test_chart_overlays_previous_only_in_same_group(self):
        cases = {
            "moderately_severe": 7,
            "mild_moderate": 0,
            "ungrouped": 0,
        }
        for previous_group, expected in cases.items():
            with self.subTest(previous=previous_group):
                Answer.objects.all().delete()
                Submission.objects.all().delete()
                self._ioi_ha((2,) * 7, previous_group, days_ago=5)
                self._ioi_ha((4,) * 7, "moderately_severe", days_ago=1)
                chart = self._chart(self._main_html(self.client.get(self._tab_url("ioi-ha"))))
                self.assertEqual(chart.count("ioi-dot-previous"), expected)
                if expected:
                    self.assertIn("使用時間：最近一次 4 分，上一次 2 分", chart)
                    self.assertIn("上一次", chart)

    def test_ungrouped_latest_has_no_bands(self):
        self._ioi_ha((2,) * 7, "mild_moderate", days_ago=5)
        self._ioi_ha((4,) * 7, "ungrouped", days_ago=1)
        main = self._main_html(self.client.get(self._tab_url("ioi-ha")))
        chart = self._chart(main)
        self.assertEqual(chart.count('class="ioi-band"'), 0)
        self.assertEqual(chart.count("ioi-dot-latest"), 7)
        self.assertEqual(chart.count("ioi-dot-previous"), 0)
        self.assertIn(self.UNGROUPED_NOTE, main)
        self.assertIn("使用時間：最近一次 4 分", chart)
        for text in ("常模 ", "低於常模", "在範圍內", "高於常模"):
            self.assertNotIn(text, chart)

    def test_ioi_ha_result_links_to_ioi_ha_tab(self):
        submission = self._ioi_ha((3,) * 7, "ungrouped", days_ago=1)
        main = self._main_html(self.client.get(reverse("result", args=[submission.id])))
        self.assertIn(
            (self._tab_url("ioi-ha"), "看我的紀錄", "每一次的結果都在這裡"), action_cards(main)
        )

    # Accessibility (19)
    def test_current_tab_marked_for_screen_readers(self):
        self._both(newest="ioi-ha")
        tabs = self._tabs(self._main_html(self.client.get(self._tab_url("hhie-s"))))
        self.assertEqual(tabs.count('aria-current="page"'), 1)
        self.assertEqual(self._current_tab(tabs), self.HHIE_S_TAB)

    def test_chart_text_alternatives(self):
        self._hhie_s(10, False, days_ago=3)
        self._hhie_s(12, True, days_ago=2)
        self._hhie_s(14, None, days_ago=1)
        main = self._main_html(self.client.get(self.url))
        # The trend chart is drawn by React; its text equivalent is the record list.
        for status in ("助聽器：沒戴", "助聽器：有戴", "助聽器：未記錄"):
            self.assertIn(status, main)
        self._ioi_ha((3,) * 7, "mild_moderate", days_ago=0)
        chart = self._chart(self._main_html(self.client.get(self._tab_url("ioi-ha"))))
        self.assertEqual(chart.count('class="visually-hidden"'), 7)
        self.assertRegex(chart, r'<div[^>]*class="ioi-grid"[^>]*aria-hidden="true"')

    # Review follow-ups
    def _columns(self, chart):
        # Item columns only; the first <li> is the score axis.
        items = re.findall(r"<li>(.*?)</li>", chart.split('class="ioi-columns"')[1], re.DOTALL)
        return [item for item in items if "ioi-grid" in item]

    def test_chart_positions(self):
        # Rows: score 5 is row 1, score 1 is row 5. moderately_severe Use is 4-5.
        self._ioi_ha((2,) * 7, "moderately_severe", days_ago=5)
        self._ioi_ha((5,) * 7, "moderately_severe", days_ago=1)
        chart = self._chart(self._main_html(self.client.get(self._tab_url("ioi-ha"))))
        use = self._columns(chart)[0]
        self.assertIn("使用時間", use)
        self.assertRegex(use, r'class="ioi-band" style="grid-row: 1 / 3"')
        self.assertRegex(use, r'class="[^"]*ioi-dot-latest[^"]*" style="grid-row: 1"')
        self.assertRegex(use, r'class="[^"]*ioi-dot-previous[^"]*" style="grid-row: 4"')

    def test_previous_point_has_another_shape(self):
        self._ioi_ha((2,) * 7, "mild_moderate", days_ago=5)
        self._ioi_ha((4,) * 7, "mild_moderate", days_ago=1)
        chart = self._chart(self._main_html(self.client.get(self._tab_url("ioi-ha"))))
        previous = re.findall(r'class="([^"]*ioi-dot-previous[^"]*)"', chart)
        latest = re.findall(r'class="([^"]*ioi-dot-latest[^"]*)"', chart)
        self.assertEqual(len(previous), 7)
        for classes in previous:
            self.assertIn("ioi-diamond", classes.split())
            self.assertNotIn("ioi-dot", classes.split())
        for classes in latest:
            self.assertIn("ioi-dot", classes.split())
        self.assertIn('class="ioi-legend-previous"', chart)

    def test_no_trend_chart_for_other_questionnaires(self):
        hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")
        question = Question.objects.create(
            questionnaire=hhia_s, question_text="HHIA題1", question_number=1
        )
        self._hhie_s(10, False, days_ago=5)
        submission = Submission.objects.create(user=self.user, questionnaire=hhia_s)
        Answer.objects.create(submission=submission, question=question, score=4)
        response = self.client.get(self._tab_url("hhia-s"))
        main = self._main_html(response)
        # Acceptance 2 of #161: both tabs, told apart by their names.
        labels = self._tab_labels(self._tabs(main))
        self.assertEqual(labels, [self.HHIE_S_TAB, self.HHIA_S_TAB])
        self.assertEqual(self._current_tab(self._tabs(main)), self.HHIA_S_TAB)
        self.assertIn(reverse("result", args=[submission.id]), main)
        self.assertNotIn("trend-chart", main)
        self.assertNotContains(response, self.CHART_JS)

    def test_same_time_records_newest_id_wins(self):
        hhie = self._hhie_s(10, False, days_ago=1)
        older_ioi = self._ioi_ha((2,) * 7, "mild_moderate", days_ago=1)
        newer_ioi = self._ioi_ha((4,) * 7, "mild_moderate", days_ago=1)
        same = Submission.objects.get(pk=hhie.pk).created_at
        Submission.objects.filter(pk__in=[older_ioi.pk, newer_ioi.pk]).update(created_at=same)
        main = self._main_html(self.client.get(self.url))
        self.assertEqual(self._current_tab(self._tabs(main)), self.IOI_HA_TAB)
        self.assertIn("使用時間：最近一次 4 分，上一次 2 分", self._chart(main))

    # The trend chart's text parts, drawn by Django so the record cards below stay put while
    # React draws the chart (docs/verification/trend-chart-layout-shift.md).
    def _trend(self):
        main = self._main_html(self.client.get(self._tab_url("hhie-s")))
        return main[main.index('id="trend-chart"') : main.index('class="link-card"')]

    def _texts(self, html):
        return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", item)).strip() for item in html]

    def _summary(self, trend):
        box = re.search(r'class="trend-summary[^"]*">(.*?)</div>', trend, re.DOTALL).group(1)
        return self._texts(re.findall(r"<p[^>]*>(.*?)</p>", box, re.DOTALL))

    def _legend(self, trend):
        legend = re.search(r'class="trend-legend">(.*?)</ul>', trend, re.DOTALL).group(1)
        return re.findall(r"<li>(.*?)</li>", legend, re.DOTALL)

    def _since_last_html(self, main):
        return re.search(r'<section id="since-last"[^>]*>(.*?)</section>', main, re.S).group(1)

    def test_trend_summary_leaves_the_comparison_to_since_last(self):
        # phase9_ui_refresh_2_data.md acceptance 5 (unaided 26, 24, 20 and aided 14, 10), now
        # compared in 「和上一次比」 instead of the summary (decision 2026-10-22, #162).
        self._hhie_s(26, False, days_ago=30)
        self._hhie_s(24, False, days_ago=20)
        aided = self._hhie_s(14, True, days_ago=10)
        self._hhie_s(20, False, days_ago=5)
        latest = self._hhie_s(10, True, days_ago=1)
        main = self._main_html(self.client.get(self._tab_url("hhie-s")))
        trend = self._trend()
        self.assertEqual(
            self._summary(trend),
            [f"最近一次（{self._date(latest)}，有戴助聽器）", "10 分 輕度到中度影響"],
        )
        self.assertIn("<strong>10 分</strong>", trend)
        since_last = self._since_last_html(main)
        self.assertIn(f"上一次（{self._date(aided)}）：14 分", since_last)
        self.assertIn("比上一次少 4 分（分數越低越好）", since_last)

    def test_trend_summary_has_no_comparison_line_down_to_0(self):
        self._hhie_s(12, False, days_ago=10)
        self._hhie_s(18, False, days_ago=5)
        self.assertEqual(len(self._summary(self._trend())), 2)
        self._hhie_s(0, False, days_ago=1)
        summary = self._summary(self._trend())
        self.assertEqual(summary[1:], ["0 分 無/極輕微影響"])

    def test_since_last_finds_the_previous_status_before_the_charts_five_days(self):
        # Acceptance 17: the chart draws five days, the comparison looks further back.
        aided = self._hhie_s(8, True, days_ago=10)
        for days_ago in range(6, 1, -1):
            self._hhie_s(20, False, days_ago=days_ago)
        self._hhie_s(12, True, days_ago=1)
        since_last = self._since_last_html(
            self._main_html(self.client.get(self._tab_url("hhie-s")))
        )
        self.assertIn(f"上一次（{self._date(aided)}）：8 分", since_last)
        self.assertIn("比上一次多 4 分（分數越低越好）", since_last)

    def test_trend_summary_with_one_record_and_a_score_of_0(self):
        latest = self._hhie_s(0, False, days_ago=1)
        self.assertEqual(
            self._summary(self._trend()),
            [
                f"最近一次（{self._date(latest)}，沒戴助聽器）",
                "0 分 無/極輕微影響",
                "再做一次篩檢，就能看到分數的變化。",
            ],
        )

    def test_trend_summary_first_of_its_status(self):
        # Acceptance 6: only the other status came before.
        self._hhie_s(12, False, days_ago=5)
        self._hhie_s(10, True, days_ago=3)
        self.assertEqual(self._summary(self._trend())[2], "這是第一筆有戴助聽器的紀錄。")
        # And the other way round, for another user.
        self._hhie_s(10, True, days_ago=3, user=self.other)
        self._hhie_s(20, False, days_ago=1, user=self.other)
        self.client.force_login(self.other)
        self.assertEqual(self._summary(self._trend())[2], "這是第一筆沒戴助聽器的紀錄。")

    def test_trend_summary_does_not_compare_an_unrecorded_record(self):
        # Acceptance 7.
        self._hhie_s(12, False, days_ago=5)
        latest = self._hhie_s(14, None, days_ago=1)
        summary = self._summary(self._trend())
        self.assertEqual(summary[0], f"最近一次（{self._date(latest)}，助聽器未記錄）")
        self.assertEqual(summary[2], "這筆沒有記錄助聽器，不和其他紀錄比較。")

    def test_trend_legend_lists_only_the_statuses_that_appear(self):
        self._hhie_s(10, False, days_ago=3)
        legend = self._legend(self._trend())
        self.assertEqual(self._texts(legend), ["沒戴助聽器"])
        self._hhie_s(12, True, days_ago=2)
        self._hhie_s(14, None, days_ago=1)
        legend = self._legend(self._trend())
        self.assertEqual(self._texts(legend), ["沒戴助聽器", "有戴助聽器", "未記錄"])
        # Unaided solid with a filled circle, aided dashed with a hollow square, unrecorded a
        # hollow triangle without a line (spec 4b and phase9_ui_refresh_2_data.md 4.1).
        unaided, aided, unrecorded = legend
        self.assertNotIn("stroke-dasharray", unaided)
        self.assertRegex(unaided, r'<circle[^>]*fill="#1f4e8c"')
        self.assertIn('stroke-dasharray="8 6"', aided)
        self.assertRegex(aided, r'<rect[^>]*fill="#fff"')
        self.assertNotIn("<line", unrecorded)
        self.assertRegex(unrecorded, r'<polygon[^>]*fill="#fff"')

    def test_trend_names_the_levels_top_band_first(self):
        # phase9_ui_refresh_3_structure.md 4.5, in each level's colours.
        self._hhie_s(10, False, days_ago=1)
        bands = re.search(r'class="trend-bands">(.*?)</ul>', self._trend(), re.DOTALL).group(1)
        items = re.findall(r'<li class="trend-band-(\w+)">(.*?)</li>', bands, re.DOTALL)
        self.assertEqual(
            [(level, self._texts([text])[0]) for level, text in items],
            [
                ("severe", "顯著影響"),
                ("mild_to_moderate", "輕度到中度影響"),
                ("normal", "無/極輕微影響"),
            ],
        )

    def test_trend_text_comes_before_the_chart_box(self):
        self._hhie_s(10, False, days_ago=1)
        trend = self._trend()
        self.assertRegex(trend, r"<h2[^>]*>\s*HHIE-S 總分變化\s*</h2>")
        order = ["<h2", self.NOTE, 'class="trend-summary', 'class="card"', 'id="trend-plot"']
        positions = [trend.index(part) for part in order]
        self.assertEqual(positions, sorted(positions))
        # React draws only inside the box; it says it is loading until then. Screen readers skip
        # that line, as they skip the chart; the box itself is not hidden, so they hear errors.
        plot = re.search(r'<div id="trend-plot"([^>]*)>(.*?)</div>', trend, re.DOTALL)
        self.assertIn('data-questionnaire="hhie-s"', plot.group(1))
        self.assertNotIn("aria-hidden", plot.group(1))
        self.assertRegex(plot.group(2), r'<p[^>]*aria-hidden="true"[^>]*>趨勢圖載入中…</p>')

    def test_trend_chart_card_hidden_without_javascript(self):
        # The summary stays; the chart box would only say it is loading, forever.
        self._hhie_s(10, False, days_ago=1)
        response = self.client.get(self._tab_url("hhie-s"))
        hidden = r"<style>\s*#trend-chart \.card \{ display: none; \}\s*</style>"
        self.assertRegex(response.content.decode(), rf"<noscript>\s*{hidden}\s*</noscript>")

    def test_trend_summary_queries_do_not_grow_with_records(self):
        # CODING_STANDARDS 15: the summary reads every record, all from the one listing query.
        self._hhie_s(10, False, days_ago=6)
        self._hhie_s(12, True, days_ago=5)
        with CaptureQueriesContext(connection) as two:
            self.client.get(self._tab_url("hhie-s"))
        for days_ago in range(4, 0, -1):
            self._hhie_s(14, None, days_ago=days_ago)
        with CaptureQueriesContext(connection) as six:
            self.client.get(self._tab_url("hhie-s"))
        self.assertEqual(len(six), len(two))


# Ticket #162 (ADR 0010): the page states numbers and direction, never a verdict.
VERDICT_WORDS = ("變好", "變差", "影響變小", "影響變大", "改善", "惡化", "進步", "退步")


class HistoryRetestTests(TestCase):
    """Spec #148 batch 2, ticket #162: the retest reminder and 「和上一次比」 on 我的紀錄."""

    # "Today" and every record's time are fixed, never the real clock.
    TODAY = date(2026, 10, 22)
    NOON = timezone.make_aware(datetime(2026, 10, 22, 12))

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="retest_user")
        cls.questions = {}
        for name, code, count in (
            ("HHIE-S", "hhie-s", 10),
            ("HHIA-S", "hhia-s", 10),
            ("IOI-HA", "ioi-ha", 7),
        ):
            questionnaire = Questionnaire.objects.create(questionnaire_name=name, code=code)
            cls.questions[code] = Question.objects.bulk_create(
                Question(
                    questionnaire=questionnaire,
                    question_text=f"{name}題{i}",
                    question_number=i,
                    category=(
                        (Category.EMOTIONAL if i <= 5 else Category.SOCIAL)
                        if code.startswith("hhi")
                        else Category.NONE
                    ),
                )
                for i in range(1, count + 1)
            )
        cls.hhie_s = Questionnaire.objects.get(code="hhie-s")
        cls.hhia_s = Questionnaire.objects.get(code="hhia-s")

    def setUp(self):
        self.client.force_login(self.user)
        real_localdate = timezone.localdate

        def localdate(value=None, timezone=None):
            return self.TODAY if value is None else real_localdate(value, timezone)

        self.enterContext(patch("django.utils.timezone.localdate", localdate))

    def _submit(self, code, scores, days_ago, user=None, **fields):
        # 沒戴 unless a test says otherwise: 「和上一次比」 needs a recorded hearing aid status.
        fields.setdefault("wearing_hearing_aid", False)
        questionnaire = Questionnaire.objects.get(code=code)
        submission = Submission.objects.create(
            user=user or self.user, questionnaire=questionnaire, **fields
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(self.questions[code], scores, strict=True)
        )
        Submission.objects.filter(pk=submission.pk).update(
            created_at=self.NOON - timedelta(days=days_ago)
        )
        return submission

    def _fetch_main_html(self, url=None):
        content = self.client.get(url or reverse("my_hearing")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _retake_url(self, questionnaire):
        return reverse("screening", args=[questionnaire.pk])

    def _reminder(self, main):
        match = re.search(r'<section id="retest-reminder"[^>]*>(.*?)</section>', main, re.S)
        return None if match is None else match.group(1)

    def test_due_reminder_and_retake_button_at_the_top(self):
        # 2026/04/22 is exactly six months before "today" (2026/10/22).
        self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=183)
        main = self._fetch_main_html()
        reminder = self._reminder(main)
        self.assertIn("<p>距離上次的生活影響評估已經滿 6 個月，建議再做一次追蹤。</p>", reminder)
        retake = self._retake_url(self.hhie_s)
        # The home page's button text (decision 2026-10-22).
        self.assertIn(
            f'<a class="btn btn-primary btn-lg" href="{retake}">再做一次（大約 3 分鐘）</a>',
            reminder,
        )
        # At the top: right under the page title, before any record.
        self.assertLess(main.index('id="retest-reminder"'), main.index('class="link-card"'))
        self.assertLess(main.index("<h1"), main.index('id="retest-reminder"'))

    def test_due_reminder_at_the_top_of_a_tab_that_is_not_the_default(self):
        # The HHIE-S is the newest record, so its tab is the default; open IOI-HA's instead.
        self._submit("ioi-ha", [3] * 7, days_ago=300, norm_group="mild_moderate")
        self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=183)
        main = self._fetch_main_html(f"{reverse('my_hearing')}?questionnaire=ioi-ha")
        # The tab's code sits in its own span (text-heavy pages tidy-up).
        # Ticket #270: the records switch above has its own current link; read the tabs' one.
        tabs = main[main.index('aria-label="問卷"') :]
        current = re.search(r'<a[^>]*aria-current="page"[^>]*>(.*?)</a>', tabs, re.S).group(1)
        self.assertEqual(re.sub(r"<[^>]+>", "", current), "助聽器使用成效（IOI-HA）")
        reminder = self._reminder(main)
        self.assertIn("<p>距離上次的生活影響評估已經滿 6 個月，建議再做一次追蹤。</p>", reminder)
        retake = self._retake_url(self.hhie_s)
        self.assertIn(
            f'<a class="btn btn-primary btn-lg" href="{retake}">再做一次（大約 3 分鐘）</a>',
            reminder,
        )
        # At the top: right under the page title, above the tabs and the IOI-HA record.
        self.assertLess(main.index("<h1"), main.index('id="retest-reminder"'))
        self.assertLess(main.index('id="retest-reminder"'), main.index('aria-label="問卷"'))
        self.assertLess(main.index('id="retest-reminder"'), main.index('class="link-card"'))

    def test_no_reminder_before_six_months(self):
        # 2026/04/23: one day short of six months.
        self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=182)
        main = self._fetch_main_html()
        self.assertIsNone(self._reminder(main))
        self.assertNotIn("滿 6 個月", main)
        self.assertNotIn(self._retake_url(self.hhie_s), main)

    def _since_last_lines(self, main):
        match = re.search(r'<section id="since-last"[^>]*>(.*?)</section>', main, re.S)
        if match is None:
            return None
        lines = re.findall(r"<(?:h2|p)[^>]*>(.*?)</(?:h2|p)>", match.group(1), re.S)
        return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", line)).strip() for line in lines]

    def test_since_last_says_how_many_points_fewer(self):
        self._submit("hhie-s", [4, 4, 4, 4] + [0] * 6, days_ago=40)  # 16, 2026/09/12
        self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=10)  # 12, 2026/10/12
        main = self._fetch_main_html()
        self.assertEqual(
            self._since_last_lines(main),
            [
                "和上一次比",
                "上一次（2026/09/12）：16 分",
                "最近一次（2026/10/12）：12 分",
                "比上一次少 4 分（分數越低越好）",
            ],
        )
        # Above the trend chart.
        self.assertLess(main.index('id="since-last"'), main.index('id="trend-chart"'))

    def test_since_last_says_the_same(self):
        self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=40)  # 12
        self._submit("hhie-s", [2] * 6 + [0] * 4, days_ago=10)  # 12, answered differently
        self.assertEqual(self._since_last_lines(self._fetch_main_html())[3], "和上一次一樣")

    def test_since_last_says_how_many_points_more(self):
        self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=40)  # 12
        self._submit("hhie-s", [4, 4, 4, 4, 4, 2] + [0] * 4, days_ago=10)  # 22
        self.assertEqual(
            self._since_last_lines(self._fetch_main_html())[3], "比上一次多 10 分（分數越低越好）"
        )

    def test_no_since_last_with_one_record(self):
        self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=10)
        main = self._fetch_main_html()
        self.assertIsNone(self._since_last_lines(main))
        self.assertNotIn("和上一次比", main)

    def test_no_verdict_words_on_the_page(self):
        for name, newest in (
            ("fewer", [4, 4] + [0] * 8),  # 8
            ("more", [4] * 10),  # 40
            ("same", [4, 4, 4, 4] + [0] * 6),  # 16
        ):
            with self.subTest(name):
                Answer.objects.all().delete()
                Submission.objects.all().delete()
                self._submit("hhie-s", [4, 4, 4, 4] + [0] * 6, days_ago=200)  # 16, due
                self._submit("hhie-s", newest, days_ago=190)
                main = self._fetch_main_html()
                self.assertIsNotNone(self._since_last_lines(main))
                self.assertIsNotNone(self._reminder(main))
                for word in VERDICT_WORDS:
                    self.assertNotIn(word, main)

    def test_hhia_s_tab_compares_too(self):
        # HHIA-S is also a life-impact questionnaire, though it has no trend chart.
        self._submit("hhia-s", [4] * 5 + [0] * 5, days_ago=40)  # 20
        self._submit("hhia-s", [4, 4, 4, 2] + [0] * 6, days_ago=10)  # 14
        main = self._fetch_main_html()
        self.assertNotIn('id="trend-chart"', main)
        self.assertEqual(self._since_last_lines(main)[3], "比上一次少 6 分（分數越低越好）")
        self.assertLess(main.index('id="since-last"'), main.index('class="link-card"'))

    def test_other_questionnaires_do_not_compare(self):
        self._submit("ioi-ha", [3] * 7, days_ago=40, norm_group="mild_moderate")
        self._submit("ioi-ha", [4] * 7, days_ago=10, norm_group="mild_moderate")
        self.assertIsNone(self._since_last_lines(self._fetch_main_html()))

    def test_since_last_compares_with_the_same_hearing_aid_status(self):
        # Decision 2026-10-22: the newest record against the one before it worn the same way,
        # even with a record worn the other way in between.
        self._submit("hhie-s", [4, 4, 4, 4] + [0] * 6, days_ago=40)  # 沒戴 16, 2026/09/12
        self._submit("hhie-s", [4, 4] + [0] * 8, days_ago=20, wearing_hearing_aid=True)  # 8
        self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=10)  # 沒戴 12, 2026/10/12
        main = self._fetch_main_html()
        self.assertEqual(
            self._since_last_lines(main)[1:],
            [
                "上一次（2026/09/12）：16 分",
                "最近一次（2026/10/12）：12 分",
                "比上一次少 4 分（分數越低越好）",
            ],
        )
        # The trend summary leaves the comparison to 「和上一次比」, so it is said once.
        summary = re.search(r'class="trend-summary[^"]*">(.*?)</div>', main, re.S).group(1)
        self.assertEqual(len(re.findall(r"<p[^>]*>", summary)), 2)
        self.assertNotIn("上一次沒戴助聽器", main)

    def test_no_since_last_when_the_newest_status_is_unrecorded(self):
        self._submit("hhie-s", [4, 4, 4, 4] + [0] * 6, days_ago=40)  # 沒戴 16
        self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=20)  # 沒戴 12
        self._submit("hhie-s", [4, 4] + [0] * 8, days_ago=10, wearing_hearing_aid=None)  # 8
        main = self._fetch_main_html()
        self.assertIsNone(self._since_last_lines(main))
        # The trend summary still explains why there is no comparison.
        self.assertIn("這筆沒有記錄助聽器，不和其他紀錄比較。", main)

    def test_no_since_last_for_the_first_record_of_its_status(self):
        self._submit("hhie-s", [4, 4, 4, 4] + [0] * 6, days_ago=40)  # 沒戴 16
        self._submit("hhie-s", [4, 4] + [0] * 8, days_ago=10, wearing_hearing_aid=True)  # 8
        main = self._fetch_main_html()
        self.assertIsNone(self._since_last_lines(main))
        self.assertIn("這是第一筆有戴助聽器的紀錄。", main)

    def test_only_the_logged_in_user_s_records_count(self):
        # This user: 16 then 12, the newer one 2026/04/22, so a retest is due.
        self._submit("hhie-s", [4, 4, 4, 4] + [0] * 6, days_ago=213)
        self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=183)
        # Someone else: a newer record, which would end the reminder and change the comparison.
        other = consented_user(username="retest_other")
        self._submit("hhie-s", [4] * 10, days_ago=1, user=other)  # 40
        main = self._fetch_main_html()
        self.assertIsNotNone(self._reminder(main))
        self.assertEqual(
            self._since_last_lines(main)[1:],
            [
                "上一次（2026/03/23）：16 分",
                "最近一次（2026/04/22）：12 分",
                "比上一次少 4 分（分數越低越好）",
            ],
        )
        # And the other way round: their one record, none of this user's.
        self.client.force_login(other)
        main = self._fetch_main_html()
        self.assertIsNone(self._reminder(main))
        self.assertIsNone(self._since_last_lines(main))

    def test_queries_do_not_grow_with_records(self):
        # CODING_STANDARDS 15: the reminder and the comparison add no query per record.
        self._submit("hhie-s", [4] * 10, days_ago=200)
        self._submit("hhie-s", [4, 4] + [0] * 8, days_ago=190)
        with CaptureQueriesContext(connection) as two:
            self.client.get(reverse("my_hearing"))
        for days_ago in range(189, 184, -1):
            self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=days_ago)
        with CaptureQueriesContext(connection) as seven:
            response = self.client.get(reverse("my_hearing"))
        self.assertIsNotNone(self._reminder(response.content.decode()))
        self.assertEqual(len(seven), len(two))
