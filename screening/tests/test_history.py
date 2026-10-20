import re
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.tests.helpers import consented_user, fake_definition, register


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
                {"code": "normal", "text": "無/極輕微影響", "max": 8},
                {"code": "mild_to_moderate", "text": "輕度到中度影響", "max": 24},
                {"code": "severe", "text": "顯著影響", "max": 40},
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

    def _main(self, response):
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _tab_url(self, code):
        return f"{self.url}?questionnaire={code}"

    def _tabs(self, main):
        match = re.search(r'<nav[^>]*aria-label="問卷"[^>]*>(.*?)</nav>', main, re.DOTALL)
        return None if match is None else match.group(1)

    def _current_tab(self, tabs):
        return re.search(r'<a[^>]*aria-current="page"[^>]*>\s*([^<]+?)\s*</a>', tabs).group(1)

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
        main = self._main(self.client.get(self.url))
        tabs = self._tabs(main)
        labels = re.findall(r"<a[^>]*>\s*([^<]+?)\s*</a>", tabs)
        self.assertEqual(labels, ["HHIE-S", "IOI-HA"])
        self.assertIn(f'href="{self._tab_url("hhie-s")}"', tabs)
        self.assertIn(f'href="{self._tab_url("ioi-ha")}"', tabs)
        self.assertEqual(self._current_tab(tabs), "IOI-HA")
        self.assertIn(reverse("result", args=[ioi.id]), main)
        self.assertNotIn(reverse("result", args=[hhie.id]), main)
        self.assertNotIn("trend-chart", main)

    def test_default_tab_is_newest_hhie_s(self):
        hhie, ioi = self._both(newest="hhie-s")
        response = self.client.get(self.url)
        main = self._main(response)
        self.assertEqual(self._current_tab(self._tabs(main)), "HHIE-S")
        self.assertIn(reverse("result", args=[hhie.id]), main)
        self.assertNotIn(reverse("result", args=[ioi.id]), main)
        self.assertContains(response, self.CHART_JS)
        self.assertIn('data-questionnaire="hhie-s"', main)

    def test_tab_url_shows_that_questionnaire(self):
        hhie, ioi = self._both(newest="ioi-ha")
        response = self.client.get(self._tab_url("hhie-s"))
        main = self._main(response)
        self.assertEqual(self._current_tab(self._tabs(main)), "HHIE-S")
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
        main = self._main(self.client.get(self.url))
        self.assertIsNone(self._tabs(main))
        self.assertIn('data-questionnaire="hhie-s"', main)

    def test_no_records(self):
        response = self.client.get(self.url)
        main = self._main(response)
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
                main = self._main(self.client.get(url))
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
        text = self._difference(self._main(self.client.get(self.url)))
        self.assertIn("配戴狀態比較", text)
        self.assertIn(f"未配戴 {self._date(unaided)}，28 分", text)
        self.assertIn(f"配戴 {self._date(aided)}，12 分", text)
        self.assertIn("少了 16 分", text)
        self.assertIn("不一定是開始使用助聽器前後", text)

    def test_difference_ignores_order(self):
        aided = self._hhie_s(12, True, days_ago=10)
        unaided = self._hhie_s(28, False, days_ago=1)
        self._retain(unaided, aided)
        self.assertIn("少了 16 分", self._difference(self._main(self.client.get(self.url))))

    def test_difference_of_zero_is_no_change(self):
        self._retain(self._hhie_s(20, False, days_ago=2), self._hhie_s(20, True, days_ago=1))
        text = self._difference(self._main(self.client.get(self.url)))
        self.assertIn("沒有變化", text)

    def test_difference_increase_has_no_verdict(self):
        self._retain(self._hhie_s(10, False, days_ago=2), self._hhie_s(16, True, days_ago=1))
        text = self._difference(self._main(self.client.get(self.url)))
        self.assertIn("多了 6 分", text)
        for word in ("改善", "變差", "有效", "無效", "建議"):
            self.assertNotIn(word, text)

    def test_no_automatic_difference_even_with_both_statuses(self):
        self._hhie_s(28, False, days_ago=2)
        self._hhie_s(12, True, days_ago=1)
        main = self._main(self.client.get(self.url))
        self.assertIn("尚未保留比較組合", main)
        self.assertNotIn("少了 16 分", main)
        self.assertNotContains(self.client.get("/report"), 'id="report-difference"')

    # IOI-HA chart (15-18)
    def _chart(self, main):
        start = main.index('class="ioi-chart')
        return main[start : main.index("<!-- /ioi-chart -->", start)]

    def test_chart_bands_follow_latest_group(self):
        self._ioi_ha((5, 4, 3, 2, 4, 3, 4), "moderately_severe", days_ago=1)
        chart = self._chart(self._main(self.client.get(self._tab_url("ioi-ha"))))
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
                chart = self._chart(self._main(self.client.get(self._tab_url("ioi-ha"))))
                self.assertEqual(chart.count("ioi-dot-previous"), expected)
                if expected:
                    self.assertIn("使用時間：最近一次 4 分，上一次 2 分", chart)
                    self.assertIn("上一次", chart)

    def test_ungrouped_latest_has_no_bands(self):
        self._ioi_ha((2,) * 7, "mild_moderate", days_ago=5)
        self._ioi_ha((4,) * 7, "ungrouped", days_ago=1)
        main = self._main(self.client.get(self._tab_url("ioi-ha")))
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
        main = self._main(self.client.get(reverse("result", args=[submission.id])))
        self.assertRegex(
            main, rf'<a[^>]*href="{re.escape(self._tab_url("ioi-ha"))}"[^>]*>\s*看我的紀錄'
        )

    # Accessibility (19)
    def test_current_tab_marked_for_screen_readers(self):
        self._both(newest="ioi-ha")
        tabs = self._tabs(self._main(self.client.get(self._tab_url("hhie-s"))))
        self.assertEqual(tabs.count('aria-current="page"'), 1)
        self.assertEqual(self._current_tab(tabs), "HHIE-S")

    def test_chart_text_alternatives(self):
        self._hhie_s(10, False, days_ago=3)
        self._hhie_s(12, True, days_ago=2)
        self._hhie_s(14, None, days_ago=1)
        main = self._main(self.client.get(self.url))
        # The trend chart is drawn by React; its text equivalent is the record list.
        for status in ("助聽器：沒戴", "助聽器：有戴", "助聽器：未記錄"):
            self.assertIn(status, main)
        self._ioi_ha((3,) * 7, "mild_moderate", days_ago=0)
        chart = self._chart(self._main(self.client.get(self._tab_url("ioi-ha"))))
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
        chart = self._chart(self._main(self.client.get(self._tab_url("ioi-ha"))))
        use = self._columns(chart)[0]
        self.assertIn("使用時間", use)
        self.assertRegex(use, r'class="ioi-band" style="grid-row: 1 / 3"')
        self.assertRegex(use, r'class="[^"]*ioi-dot-latest[^"]*" style="grid-row: 1"')
        self.assertRegex(use, r'class="[^"]*ioi-dot-previous[^"]*" style="grid-row: 4"')

    def test_previous_point_has_another_shape(self):
        self._ioi_ha((2,) * 7, "mild_moderate", days_ago=5)
        self._ioi_ha((4,) * 7, "mild_moderate", days_ago=1)
        chart = self._chart(self._main(self.client.get(self._tab_url("ioi-ha"))))
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
        main = self._main(response)
        self.assertEqual(self._current_tab(self._tabs(main)), "HHIA-S")
        self.assertIn(reverse("result", args=[submission.id]), main)
        self.assertNotIn("trend-chart", main)
        self.assertNotContains(response, self.CHART_JS)

    def test_same_time_records_newest_id_wins(self):
        hhie = self._hhie_s(10, False, days_ago=1)
        older_ioi = self._ioi_ha((2,) * 7, "mild_moderate", days_ago=1)
        newer_ioi = self._ioi_ha((4,) * 7, "mild_moderate", days_ago=1)
        same = Submission.objects.get(pk=hhie.pk).created_at
        Submission.objects.filter(pk__in=[older_ioi.pk, newer_ioi.pk]).update(created_at=same)
        main = self._main(self.client.get(self.url))
        self.assertEqual(self._current_tab(self._tabs(main)), "IOI-HA")
        self.assertIn("使用時間：最近一次 4 分，上一次 2 分", self._chart(main))
