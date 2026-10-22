"""SADL answering, scoring and pre-launch visibility (#167)."""

import json
import re
import uuid
from dataclasses import replace
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Questionnaire, Submission
from screening.questionnaires import sadl
from screening.tests import test_report
from screening.tests.helpers import consented_user, register


def sadl_submission(user, questionnaire, *, wearing_hearing_aid=True, score=4):
    """A fully-answered SADL record (15 items, none 「不適用」), owned by the given user."""
    submission = Submission.objects.create(
        user=user, questionnaire=questionnaire, wearing_hearing_aid=wearing_hearing_aid
    )
    Answer.objects.bulk_create(
        Answer(submission=submission, question=question, score=score)
        for question in questionnaire.questions.all()
    )
    return submission


class SadlTestCase(TestCase):
    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.questionnaire = Questionnaire.objects.get(code="sadl")
        self.user = consented_user(username="sadl_user", password="Test-pass-12345")
        self.client.force_login(self.user)


class SadlVisibilityTests(SadlTestCase):
    def test_unlisted_sadl_is_hidden_in_production(self):
        catalog = self.client.get(reverse("questionnaire_list"), {"choose": "self"})
        # The full list (choose for myself), with the other questionnaires but not SADL.
        self.assertContains(catalog, "日常聆聽能力（SSQ12-TW）")
        self.assertNotContains(catalog, "SADL")
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk]))
        self.assertEqual(page.status_code, 404)
        codes = [q["code"] for q in self.client.get("/api/questionnaires/").json()]
        self.assertNotIn("sadl", codes)

    @override_settings(DEBUG=True)
    def test_unlisted_sadl_is_offered_on_a_local_debug_site(self):
        catalog = self.client.get(reverse("questionnaire_list"), {"choose": "self"})
        self.assertContains(catalog, "助聽器滿意度（SADL）")
        self.assertContains(catalog, "給正在戴或最近戴過助聽器的人。")
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk]))
        self.assertEqual(page.status_code, 200)

    def test_seeding_creates_fifteen_questions(self):
        self.assertEqual(self.questionnaire.questions.count(), 15)

    def test_listed_sadl_is_offered_in_production(self):
        with register(replace(sadl.DEFINITION, listed=True)):
            catalog = self.client.get(reverse("questionnaire_list"), {"choose": "self"})
        self.assertContains(catalog, "助聽器滿意度（SADL）")


@override_settings(DEBUG=True)
class SadlAnsweringTests(SadlTestCase):
    def test_answer_page_does_not_ask_about_wearing_and_explains_who_answers_item_14(self):
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk]))
        self.assertNotContains(page, "有沒有戴助聽器")
        # React (#170): the page itself has no wearing step, told via data-always-aided.
        self.assertContains(page, 'id="answer-app"')
        self.assertContains(page, "data-always-aided")
        self.assertContains(page, "請依您現在戴著或最近戴過的助聽器回答")
        self.assertContains(page, "拿部分補助、自己也付了錢，請照樣作答")

    def test_every_item_has_seven_labels_and_only_items_11_and_14_take_not_applicable(self):
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk])).content.decode()
        labels = ["一點都沒有", "一點點", "有一些", "中等程度", "相當程度", "非常多", "極度"]
        seven = [(str(value), label) for value, label in enumerate(labels, start=1)]
        not_applicable = {
            11: ("na", "不適用：不戴助聽器講電話也聽得清楚"),
            14: ("na", "不適用：助聽器的錢不是我出的（例如全額補助、家人出錢）"),
        }
        for number in range(1, 16):
            with self.subTest(item=number):
                group = re.search(rf'id="question-{number}".*?</fieldset>', page, re.S).group()
                # Each option is the radio's value and the text right after it, so a letter
                # A–G in front of a label would not match.
                options = re.findall(
                    r'value="([^"]+)" class="choice-group" id="[^"]+">\n (.*?)</label>', group
                )
                expected = seven + ([not_applicable[number]] if number in not_applicable else [])
                self.assertEqual(options, expected)


@override_settings(DEBUG=True)
class SadlScoringTests(SadlTestCase):
    def answer(self, values):
        """Sends the server form; each value is 1–7, "na", or None for an unanswered item."""
        questions = list(self.questionnaire.questions.all())
        data = {
            "idempotency_key": str(uuid.uuid4()),
            "form-TOTAL_FORMS": len(questions),
            "form-INITIAL_FORMS": 0,
        }
        for index, (question, value) in enumerate(zip(questions, values, strict=True)):
            data[f"form-{index}-question_id"] = question.pk
            if value is not None:
                data[f"form-{index}-score"] = value
        return self.client.post(reverse("screening", args=[self.questionnaire.pk]), data)

    def test_an_unanswered_item_is_not_saved_and_is_listed(self):
        response = self.answer([4, 4, None] + [4] * 12)
        self.assertContains(response, 'href="#question-3">第 3 題</a>')
        self.assertNotContains(response, 'href="#question-2">')
        self.assertFalse(Submission.objects.exists())

    def test_not_applicable_is_refused_outside_items_11_and_14(self):
        response = self.answer(["na"] + [4] * 14)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Submission.objects.exists())

    def test_a_record_is_saved_as_worn(self):
        response = self.answer([4] * 15)
        submission = Submission.objects.get()
        self.assertRedirects(response, reverse("result", args=[submission.pk]))
        self.assertIs(submission.wearing_hearing_aid, True)

    def test_overall_and_subscale_scores_with_reversed_items_and_not_applicable(self):
        # Worked by hand from the official scoring rules: items 2, 4, 7 and 13 are reversed.
        cases = (
            ([4] * 15, "4.0", ("4.0", "4.0", "4.0", "4.0"), False),
            ([1] * 15, "2.6", ("1.0", "1.0", "5.0", "5.0"), False),
            ([1] * 10 + ["na", 1, 1, "na", 1], "2.8", ("1.0", "1.0", "7.0", "5.0"), True),
        )
        names = ("正面效果", "服務與費用", "負面特徵", "個人形象")
        for values, overall, subscales, skipped in cases:
            with self.subTest(overall=overall):
                self.answer(values)
                submission = Submission.objects.latest("pk")
                data = self.client.get(f"/api/submissions/{submission.pk}/").json()
                self.assertEqual(data["satisfaction"]["overall"], overall)
                self.assertEqual(
                    [(s["name"], s["score"]) for s in data["satisfaction"]["subscales"]],
                    list(zip(names, subscales, strict=True)),
                )
                self.assertIsNone(data["scores"])
                self.assertIsNone(data["level"])
                self.assertNotIn("average_score", data)
                page = self.client.get(reverse("result", args=[submission.pk]))
                self.assertContains(page, f"整體滿意度：{overall}")
                for name, score in zip(names, subscales, strict=True):
                    self.assertContains(page, f"{name}：{score}")
                if skipped:
                    self.assertContains(page, "第 11、14 題選了「不適用」，沒有算進分數")
                else:
                    self.assertNotContains(page, "沒有算進分數")

    def test_result_page_explains_the_scale_without_norms_or_grades(self):
        self.answer([4] * 15)
        page = self.client.get(reverse("result", args=[Submission.objects.get().pk]))
        self.assertContains(page, "1 到 7 分，分數越高越滿意，4 分是中間")
        self.assertNotContains(page, "常模")
        self.assertNotContains(page, "level-badge")

    def test_answer_and_result_pages_credit_the_scale_and_its_translators(self):
        credit = "© University of Memphis, 1999；中文版：Fang 等，2013（國泰綜合醫院）"
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk])).content.decode()
        self.assertGreater(page.find(credit), page.index("</form>"))
        self.answer([4] * 15)
        result = self.client.get(reverse("result", args=[Submission.objects.get().pk]))
        result = result.content.decode()
        self.assertGreater(result.find(credit), result.index("選擇問卷</a>"))

    def test_result_page_reads_the_answers_once(self):
        self.answer([4] * 15)
        submission = Submission.objects.get()
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("result", args=[submission.pk]))
        reads = [q for q in ctx.captured_queries if '"screening_question"' in q["sql"]]
        self.assertEqual(len(reads), 1)

    def test_each_subscale_shows_the_owner_approved_explanation(self):
        # Text approved by the owner in #168.
        approved = {
            "正面效果": "戴助聽器帶來多少好處，例如比較聽得懂別人說話、比較少請人重說、"
            "比較有自信、聲音聽起來自然。",
            "服務與費用": "您對幫您調整助聽器的人員、助聽器的價格，"
            "以及助聽器耐不耐用，滿意的程度。",
            "負面特徵": "助聽器帶來的困擾，例如聲音跟預期不同、轉大聲時出現迴音（嘯叫聲），"
            "以及講電話時幫不幫得上忙。分數越高，代表困擾越少。",
            "個人形象": "戴助聽器時，您在不在意外觀和別人的眼光。分數越高，代表越不在意、"
            "對自己的樣子越滿意。",
        }
        self.answer([4] * 15)
        page = self.client.get(reverse("result", args=[Submission.objects.get().pk]))
        for name, text in approved.items():
            with self.subTest(name=name):
                self.assertContains(page, f"<strong>{name}：4.0</strong><br>{text}")

    def test_the_submission_list_reads_answers_the_same_number_of_times_for_two_or_five(self):
        def list_queries():
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get("/api/submissions/")
            self.assertEqual(response.status_code, 200)
            return len(ctx.captured_queries)

        for _ in range(2):
            self.answer([4] * 15)
        two = list_queries()
        for _ in range(3):
            self.answer([4] * 15)
        self.assertEqual(list_queries(), two)


@override_settings(DEBUG=True)
class SadlExportTests(SadlTestCase):
    """Data export includes SADL (#173)."""

    def answer(self, values):
        """Sends the server form; each value is 1–7, "na", or None for an unanswered item."""
        questions = list(self.questionnaire.questions.all())
        data = {
            "idempotency_key": str(uuid.uuid4()),
            "form-TOTAL_FORMS": len(questions),
            "form-INITIAL_FORMS": 0,
        }
        for index, (question, value) in enumerate(zip(questions, values, strict=True)):
            data[f"form-{index}-question_id"] = question.pk
            if value is not None:
                data[f"form-{index}-score"] = value
        return self.client.post(reverse("screening", args=[self.questionnaire.pk]), data)

    def _exported_sadl(self):
        submissions = self.client.get(reverse("download_my_data")).json()["submissions"]
        return next(
            s for s in submissions if s["questionnaire"] == self.questionnaire.questionnaire_name
        )

    def test_export_labels_each_answer_in_chinese_including_not_applicable(self):
        self.answer([1] * 10 + ["na", 1, 1, "na", 1])
        exported = self._exported_sadl()
        self.assertEqual(exported["answers"][0]["choice"], "一點都沒有")
        self.assertIsNone(exported["answers"][10]["score"])
        self.assertEqual(exported["answers"][10]["choice"], "不適用")
        self.assertIsNone(exported["answers"][13]["score"])
        self.assertEqual(exported["answers"][13]["choice"], "不適用")

    def test_export_has_overall_and_subscale_scores_matching_the_result_page(self):
        self.answer([4] * 15)
        exported = self._exported_sadl()
        self.assertEqual(exported["overall_score"], "4.0")
        self.assertEqual(
            exported["subscale_scores"],
            {"正面效果": "4.0", "服務與費用": "4.0", "負面特徵": "4.0", "個人形象": "4.0"},
        )
        self.assertIsNone(exported["level"])
        self.assertIsNone(exported["total_score"])
        self.assertIsNone(exported["emotional_score"])
        self.assertIsNone(exported["social_score"])

    def test_export_does_not_carry_the_ssq12_average_field_when_both_are_answered(self):
        self.answer([4] * 15)
        ssq12 = Questionnaire.objects.get(code="ssq12-tw")
        self.client.post(
            "/api/submissions/",
            {
                "questionnaire": ssq12.pk,
                "wearing_hearing_aid": False,
                "answers": [{"question": q.pk, "score": 6} for q in ssq12.questions.all()],
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        exported = self._exported_sadl()
        self.assertNotIn("average_score", exported)
        self.assertNotIn("average_unavailable_reason", exported)


@override_settings(DEBUG=True)
class SadlHistoryTests(SadlTestCase):
    """我的紀錄的 SADL 分頁 (#171)."""

    def answer(self, values):
        questions = list(self.questionnaire.questions.all())
        data = {
            "idempotency_key": str(uuid.uuid4()),
            "form-TOTAL_FORMS": len(questions),
            "form-INITIAL_FORMS": 0,
        }
        for index, (question, value) in enumerate(zip(questions, values, strict=True)):
            data[f"form-{index}-question_id"] = question.pk
            if value is not None:
                data[f"form-{index}-score"] = value
        return self.client.post(reverse("screening", args=[self.questionnaire.pk]), data)

    def test_the_sadl_tab_lists_each_record_by_overall_score_linking_to_its_result(self):
        # A second questionnaire so the tab nav (and its label) actually renders.
        Submission.objects.create(
            user=self.user, questionnaire=Questionnaire.objects.get(code="ssq12-tw")
        )
        self.answer([4] * 15)
        first = Submission.objects.latest("pk")
        self.answer([1] * 15)
        second = Submission.objects.latest("pk")
        history = self.client.get(reverse("my_hearing"), {"questionnaire": "sadl"})
        self.assertContains(history, "助聽器滿意度（SADL）")
        self.assertContains(history, "整體滿意度：4.0")
        self.assertContains(history, "整體滿意度：2.6")
        self.assertContains(history, reverse("result", args=[first.pk]))
        self.assertContains(history, reverse("result", args=[second.pk]))

    def test_the_sadl_tab_has_no_wearing_comparison_or_trend_chart(self):
        self.answer([4] * 15)
        self.answer([1] * 15)
        history = self.client.get(reverse("my_hearing"), {"questionnaire": "sadl"})
        self.assertNotContains(history, "配戴狀態比較")
        self.assertNotContains(history, "比較戴與不戴助聽器")
        self.assertNotIn("trend-chart", history.content.decode())
        self.assertNotContains(history, "screening/frontend/trend-chart.js")

    def test_another_users_sadl_record_does_not_appear(self):
        self.answer([4] * 15)
        other = consented_user(username="sadl_other", password="Test-pass-12345")
        self.client.force_login(other)
        self.answer([1] * 15)
        self.client.force_login(self.user)
        history = self.client.get(reverse("my_hearing"), {"questionnaire": "sadl"})
        self.assertContains(history, "整體滿意度：4.0")
        self.assertNotContains(history, "整體滿意度：2.6")

    def test_the_tab_reads_answers_the_same_number_of_times_for_two_or_five_records(self):
        def list_queries():
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get(reverse("my_hearing"), {"questionnaire": "sadl"})
            self.assertEqual(response.status_code, 200)
            return len(ctx.captured_queries)

        for _ in range(2):
            self.answer([4] * 15)
        two = list_queries()
        for _ in range(3):
            self.answer([4] * 15)
        self.assertEqual(list_queries(), two)


@override_settings(DEBUG=True)
class SadlReportTests(SadlTestCase):
    """Health report and shared report show a SADL part (#172)."""

    def _record(self, score=4, wearing=True, days_ago=0):
        questions = list(self.questionnaire.questions.order_by("question_number"))
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=q, score=score) for q in questions
        )
        if days_ago:
            Submission.objects.filter(pk=submission.pk).update(
                created_at=timezone.now() - timedelta(days=days_ago)
            )
        return Submission.objects.get(pk=submission.pk)

    def _share_report(self):
        self.client.post("/report/share", {"confirm": "1"})
        share = self.user.report_shares.get()
        self.client.logout()
        return self.client.get(f"/shared/{share.token}/report")

    # acceptance 1
    def test_report_shows_latest_overall_subscales_and_recent_list(self):
        older = self._record(score=4, days_ago=3)
        latest = self._record(score=4, days_ago=0)
        report = self.client.get(reverse("health_report")).content.decode()
        section = test_report._section(report, "report-sadl")
        self.assertIn("整體滿意度：4.0", section)
        for name in ("正面效果", "服務與費用", "負面特徵", "個人形象"):
            with self.subTest(name=name):
                self.assertIn(f"{name}：4.0", section)
        self.assertIn("最近 2 次紀錄", section)
        for record in (older, latest):
            self.assertIn(timezone.localtime(record.created_at).strftime("%Y/%m/%d %H:%M"), section)

    # acceptance 2
    def test_sadl_and_ssq12_sections_stay_separate(self):
        self._record()
        ssq = Questionnaire.objects.get(code="ssq12-tw")
        ssq_submission = Submission.objects.create(
            user=self.user, questionnaire=ssq, wearing_hearing_aid=True
        )
        Answer.objects.bulk_create(
            Answer(submission=ssq_submission, question=q, score=2)
            for q in ssq.questions.order_by("question_number")
        )
        content = self.client.get(reverse("health_report")).content.decode()
        ssq_section = test_report._section(content, "report-ssq12")
        sadl_section = test_report._section(content, "report-sadl")
        self.assertIn("SSQ12-TW", ssq_section)
        self.assertNotIn("SADL", ssq_section)
        self.assertNotIn("整體滿意度", ssq_section)
        self.assertIn("SADL", sadl_section)
        self.assertIn("整體滿意度", sadl_section)
        self.assertNotIn("SSQ12", sadl_section)

    # acceptance 3
    def test_family_shared_report_shows_the_same_sadl_section(self):
        self._record()
        owner_content = self.client.get(reverse("health_report")).content.decode()
        shared_content = self._share_report().content.decode()
        self.assertEqual(
            test_report._section(owner_content, "report-sadl"),
            test_report._section(shared_content, "report-sadl"),
        )

    # acceptance 4
    def test_report_scores_match_the_result_page(self):
        # Same case as SadlScoringTests.test_overall_and_subscale_scores...: items 2/4/7/13
        # are reversed, so an all-1 answer set is not an all-1 score set.
        submission = self._record(score=1)
        report = self.client.get(reverse("health_report")).content.decode()
        result = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        section = test_report._section(report, "report-sadl")
        self.assertIn("整體滿意度：2.6", section)
        self.assertIn("整體滿意度：2.6", result)
        names_and_scores = zip(
            ("正面效果", "服務與費用", "負面特徵", "個人形象"),
            ("1.0", "1.0", "5.0", "5.0"),
            strict=True,
        )
        for name, score in names_and_scores:
            with self.subTest(name=name):
                self.assertIn(f"{name}：{score}", section)
                self.assertIn(f"{name}：{score}", result)

    def test_no_sadl_records_leaves_the_part_out(self):
        content = self.client.get(reverse("health_report")).content.decode()
        self.assertNotIn('id="report-satisfaction"', content)
        self.assertNotIn('id="report-sadl"', content)

    def test_query_count_does_not_grow_with_more_sadl_records(self):
        for _ in range(5):
            self._record()
        with CaptureQueriesContext(connection) as few:
            self.client.get(reverse("health_report"))
        for _ in range(5):
            self._record()
        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse("health_report"))
        self.assertEqual(len(many), len(few))


@override_settings(DEBUG=True)
class SadlRecommendationTests(SadlTestCase):
    """Wizard "也可以做" and the home-page overall-score card for SADL (#174)."""

    fixtures = ("questions_fixture.json",)

    def setUp(self):
        super().setUp()
        self.hhie = Questionnaire.objects.get(code="hhie-s")
        self.ssq12 = Questionnaire.objects.get(code="ssq12-tw")

    def wizard(self, **params):
        return self.client.get(reverse("questionnaire_list"), params)

    def also_list(self, page):
        main = page.content.decode()
        return main[main.index("也可以做") : main.index("看其他問卷")]

    def test_aided_also_lists_ssq12_and_sadl_when_sadl_is_visible(self):
        page = self.wizard(age_group="older", hearing_aid="yes")
        also = self.also_list(page)
        self.assertIn(f'href="{reverse("screening", args=[self.ssq12.pk])}"', also)
        self.assertIn(f'href="{reverse("screening", args=[self.questionnaire.pk])}"', also)
        self.assertEqual(also.count("questionnaire-card"), 2)

    def test_unlisted_sadl_is_not_in_the_also_list_in_production(self):
        with override_settings(DEBUG=False):
            page = self.wizard(age_group="older", hearing_aid="yes")
        self.assertNotContains(page, "SADL")
        also = self.also_list(page)
        self.assertIn(f'href="{reverse("screening", args=[self.ssq12.pk])}"', also)
        self.assertNotIn(f'href="{reverse("screening", args=[self.questionnaire.pk])}"', also)
        self.assertEqual(also.count("questionnaire-card"), 1)

    def test_aided_with_only_a_sadl_record_still_recommends_life_impact_and_says_why(self):
        # SADL is not a life-impact record (#166): having only one still needs the unaided
        # HHIE-S/HHIA-S catch-up, same as having no records at all.
        sadl_submission(self.user, self.questionnaire)
        page = self.wizard(age_group="older", hearing_aid="yes")
        self.assertEqual(page.context["recommended"], self.hhie)
        self.assertEqual(page.context["reason"], "needs_norm_basis")
        self.assertContains(
            page,
            "<p><strong>為什麼推薦：</strong>"
            "您有戴助聽器，但還沒有沒戴助聽器時的紀錄。"
            "先了解沒戴助聽器時的情況，之後做助聽器成效問卷才能比較。</p>",
        )

    def test_home_page_shows_the_overall_score_for_a_sadl_only_history(self):
        sadl_submission(self.user, self.questionnaire)
        page = self.client.get(reverse("index"))
        self.assertContains(page, "歡迎回來")
        self.assertContains(page, "整體滿意度：4.0")
        # Not a life-impact record (#166): no retest reminder of either phrasing.
        self.assertNotContains(page, "距離上次的生活影響評估")
        self.assertNotContains(page, "下次建議")
        self.assertNotContains(page, "再做一次")

    def test_another_users_sadl_record_does_not_make_a_new_user_look_returning(self):
        other = consented_user(username="other_sadl_user", password="Test-pass-12345")
        sadl_submission(other, self.questionnaire)
        page = self.client.get(reverse("index"))
        self.assertContains(page, "了解聽力對您生活的影響")
        self.assertNotContains(page, "歡迎回來")


@override_settings(DEBUG=True)
class SadlAnswerApiTests(SadlTestCase):
    """SADL answered through /api/submissions/ (#170): always-aided, no wearing field needed."""

    def _body(self, values, **overrides):
        """values: 15 item scores, 1-7 or None for 「不適用」 (API score, not the "na" sentinel)."""
        questions = list(self.questionnaire.questions.all())
        body = {
            "questionnaire": self.questionnaire.pk,
            "answers": [
                {"question": question.pk, "score": value}
                for question, value in zip(questions, values, strict=True)
            ],
        }
        body.update(overrides)
        return body

    def _post(self, body):
        return self.client.post(
            "/api/submissions/",
            json.dumps(body),
            content_type="application/json",
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )

    def test_a_submission_without_a_wearing_field_is_saved_as_worn(self):
        response = self._post(self._body([4] * 15))
        self.assertEqual(response.status_code, 201)
        submission = Submission.objects.get()
        self.assertIs(submission.wearing_hearing_aid, True)

    def test_a_submission_sending_wearing_false_is_still_saved_as_worn(self):
        # The web form never offers this choice either (views.screening, always_aided); the API
        # must not trust a caller that sends it anyway.
        response = self._post(self._body([4] * 15, wearing_hearing_aid=False))
        self.assertEqual(response.status_code, 201)
        submission = Submission.objects.get()
        self.assertIs(submission.wearing_hearing_aid, True)

    def test_a_missing_answer_is_rejected_with_the_same_message_as_the_web_form(self):
        questions = list(self.questionnaire.questions.all())
        body = {
            "questionnaire": self.questionnaire.pk,
            "answers": [{"question": question.pk, "score": 4} for question in questions[:-1]],
        }
        response = self._post(body)
        self.assertEqual(response.status_code, 400)
        # Same message as forms.BaseAnswerFormSet.clean() (shared by the web form).
        self.assertEqual(response.json(), {"answers": ["有題目沒有作答"]})
        self.assertFalse(Submission.objects.exists())

    def test_not_applicable_outside_item_11_or_14_is_rejected_like_the_web_form(self):
        response = self._post(self._body([None] + [4] * 14))
        self.assertEqual(response.status_code, 400)
        # Same message as forms.BaseAnswerFormSet.clean() (shared by the web form).
        self.assertEqual(response.json(), {"answers": ["表單資料有誤，請重新確認每一題的作答"]})
        self.assertFalse(Submission.objects.exists())
