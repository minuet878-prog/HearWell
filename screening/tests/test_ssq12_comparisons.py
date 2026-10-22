"""SSQ12 saved comparison public pages (#83)."""

import re
from datetime import datetime
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from screening.models import Answer, Question, Questionnaire, Submission
from screening.questionnaires.definition import AVERAGE
from screening.tests import test_hhi_comparisons
from screening.tests.helpers import consented_user, fake_definition, register


class SsqComparisonTests(TestCase):
    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.questionnaire = Questionnaire.objects.get(code="ssq12-tw")
        self.user = consented_user(username="ssq_compare", password="Test-pass-12345")
        self.other = consented_user(username="ssq_other")
        self.client.force_login(self.user)
        self.url = f"/comparisons/{self.questionnaire.pk}"

    def record(self, wearing, scores, user=None, questionnaire=None):
        questionnaire = questionnaire or self.questionnaire
        record = Submission.objects.create(
            user=user or self.user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=q, score=s)
            for q, s in zip(questionnaire.questions.all(), scores, strict=True)
        )
        return record

    def pair(self, first, second):
        return {"unaided": first.pk, "aided": second.pk, "action": "save"}

    def test_raw_average_difference_and_twelve_item_comparison(self):
        first = self.record(False, [4] * 11 + [8])
        second = self.record(True, [4] * 10 + [6, 10])
        page = self.client.get(self.url, self.pair(first, second))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "4.3")
        self.assertContains(page, "4.7")
        self.assertContains(page, "有戴比沒戴多 0.3 分（分數越高越好）")
        self.assertNotContains(page, "0.4 分")
        for question in self.questionnaire.questions.all():
            self.assertContains(page, question.question_text)

    def test_na_keeps_items_without_difference_and_rejects_foreign_or_incomplete(self):
        first = self.record(False, [None] * 12)
        second = self.record(True, [6] * 12)
        response = self.client.post(self.url, self.pair(first, second))
        self.assertRedirects(response, self.url)
        page = self.client.get(self.url)
        self.assertContains(page, "不適用")
        self.assertContains(page, "未計算整體差值")
        self.assertNotContains(page, "+6.0")
        foreign = self.record(True, [8] * 12, user=self.other)
        incomplete = self.record(True, [4] * 12)
        incomplete.answers.first().delete()
        unknown = self.record(None, [5] * 12)
        version = Questionnaire.objects.create(
            code="ssq12-test-version", questionnaire_name="假版本"
        )
        self.enterContext(register(fake_definition("ssq12-test-version", result=AVERAGE)))
        Question.objects.bulk_create(
            Question(questionnaire=version, question_text=f"另一版本{n}", question_number=n)
            for n in range(1, 13)
        )
        different = self.record(True, [7] * 12, questionnaire=version)
        for record in (foreign, incomplete, first, unknown, different):
            self.assertEqual(self.client.post(self.url, self.pair(first, record)).status_code, 400)
        self.assertEqual(self.client.get(self.url).context["saved"].aided_id, second.pk)
        payload = self.client.get("/my_data/download").json()["report_comparisons"]
        self.assertEqual(len(payload), 1)
        self.assertIsNone(payload[0]["unaided"]["answers"][0]["score"])
        self.record(True, [10] * 12)
        self.assertEqual(self.client.get(self.url).context["saved"].aided_id, second.pk)
        self.client.post(self.url, {"action": "remove"})
        self.assertTrue(Submission.objects.filter(pk=first.pk).exists())
        self.assertFalse(self.user.report_comparisons.exists())

    def test_report_and_family_include_latest_ssq_and_retained_comparison(self):
        first = self.record(False, [4] * 11 + [8])
        second = self.record(True, [4] * 10 + [6, 10])
        self.client.post(self.url, self.pair(first, second))
        self.record(True, [9] * 12)
        page = self.client.get("/report")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "日常聆聽能力")
        self.assertContains(page, "9.0")
        self.assertContains(page, "+0.3")
        self.client.post("/report/share", {"confirm": "1"})
        share = self.user.report_shares.get()
        self.client.logout()
        family = self.client.get(f"/shared/{share.token}/report")
        self.assertContains(family, "+0.3")
        self.assertContains(family, "9.0")
        self.assertNotContains(family, "ssq_compare")
        self.assertNotContains(family, "更換或移除")
        self.assertNotContains(family, 'href="/comparisons/')
        self.assertIn("no-store", family["Cache-Control"])
        self.record(True, [10] * 12)
        family = self.client.get(f"/shared/{share.token}/report")
        self.assertContains(family, "整體平均：10.0")
        self.assertContains(family, "+0.3")
        self.client.force_login(self.user)
        self.client.post(f"/report/share/{share.pk}/cancel")
        self.client.logout()
        self.assertEqual(self.client.get(f"/shared/{share.token}/report").status_code, 404)

    def test_three_pairs_remain_independent_and_account_deletion_cleans_ssq(self):
        call_command("seed_questionnaires", stdout=StringIO())
        hhie = Questionnaire.objects.create(code="hhie-s", questionnaire_name="HHIE-S")
        Question.objects.bulk_create(
            Question(questionnaire=hhie, question_text=f"假題{n}", question_number=n)
            for n in range(1, 11)
        )
        for questionnaire in (hhie, Questionnaire.objects.get(code="hhia-s"), self.questionnaire):
            scores = [2] * questionnaire.questions.count()
            first = self.record(False, scores, questionnaire=questionnaire)
            second = self.record(True, scores, questionnaire=questionnaire)
            self.assertEqual(
                self.client.post(
                    f"/comparisons/{questionnaire.pk}", self.pair(first, second)
                ).status_code,
                302,
            )
        self.assertEqual(self.user.report_comparisons.count(), 3)
        page = self.client.get("/report")
        for text in ("生活影響", "SSQ12-TW", "HHIA-S", "HHIE-S"):
            self.assertContains(page, text)
        hhi_pairs = list(
            self.user.report_comparisons.exclude(questionnaire=self.questionnaire).values_list(
                "questionnaire_id", "unaided_id", "aided_id"
            )
        )
        replacement = self.record(True, [10] * 12)
        self.client.post(self.url, self.pair(first, replacement))
        self.assertEqual(self.client.get(self.url).context["saved"].aided_id, replacement.pk)
        self.client.post(self.url, {"action": "remove"})
        self.assertEqual(
            list(
                self.user.report_comparisons.values_list(
                    "questionnaire_id", "unaided_id", "aided_id"
                )
            ),
            hhi_pairs,
        )
        foreign = self.record(True, [1] * 12, user=self.other)
        self.client.post("/account/delete", {"password": "Test-pass-12345"})
        self.assertFalse(Submission.objects.filter(user_id=self.user.pk).exists())
        self.assertTrue(Submission.objects.filter(pk=foreign.pk).exists())

    def test_query_count_does_not_grow_with_records(self):
        self.record(False, [4] * 12)
        self.record(True, [6] * 12)
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for _ in range(5):
            self.record(False, [4] * 12)
            self.record(True, [6] * 12)
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(many), len(few))


class Ssq12ComparisonRadioCardTests(TestCase):
    """SSQ12 radio cards show the average, or why there is none (#190)."""

    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.questionnaire = Questionnaire.objects.get(code="ssq12-tw")
        self.user = consented_user(username="ssq_radio")
        self.client.force_login(self.user)
        self.url = f"/comparisons/{self.questionnaire.pk}"

    def record(self, wearing, scores, when):
        record = Submission.objects.create(
            user=self.user, questionnaire=self.questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=q, score=s)
            for q, s in zip(self.questionnaire.questions.all(), scores, strict=True)
        )
        Submission.objects.filter(pk=record.pk).update(created_at=when)
        return record

    def test_cards_show_average_or_not_calculated(self):
        taipei = test_hhi_comparisons.TAIPEI
        self.record(False, [4] * 11 + [8], datetime(2026, 4, 20, 10, 30, tzinfo=taipei))
        self.record(True, [6] * 11 + [None], datetime(2026, 9, 2, 9, 0, tzinfo=taipei))
        page = self.client.get(self.url)
        cards = test_hhi_comparisons.radio_cards
        self.assertEqual(cards(page, "unaided"), [("2026/04/20・平均 4.3 分", False)])
        self.assertEqual(cards(page, "aided"), [("2026/09/02・未計算：包含不適用題目", False)])


class Ssq12ComparisonResultCardTests(TestCase):
    """The comparison page's result card for SSQ12-TW (#191): averages, higher is better."""

    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.questionnaire = Questionnaire.objects.get(code="ssq12-tw")
        self.user = consented_user(username="ssq_card")
        self.client.force_login(self.user)
        self.url = f"/comparisons/{self.questionnaire.pk}"

    def preview(self, unaided, aided):
        pair = []
        for wearing, scores in ((False, unaided), (True, aided)):
            record = Submission.objects.create(
                user=self.user, questionnaire=self.questionnaire, wearing_hearing_aid=wearing
            )
            Answer.objects.bulk_create(
                Answer(submission=record, question=q, score=s)
                for q, s in zip(self.questionnaire.questions.all(), scores, strict=True)
            )
            pair.append(record)
        return self.client.get(
            self.url, {"unaided": pair[0].pk, "aided": pair[1].pk, "action": "preview"}
        )

    def test_card_shows_both_averages_and_the_direction(self):
        # Unrounded averages subtracted (ADR 0001): 52/12 = 4.33…, 56/12 = 4.67…, difference 0.3.
        for unaided, aided, sentence in (
            ([4] * 11 + [8], [4] * 10 + [6, 10], "有戴比沒戴多 0.3 分（分數越高越好）"),
            ([4] * 10 + [6, 10], [4] * 11 + [8], "有戴比沒戴少 0.3 分（分數越高越好）"),
            ([4] * 11 + [8], [4] * 10 + [6, 6], "有戴和沒戴的平均一樣"),
        ):
            with self.subTest(sentence=sentence):
                card = test_hhi_comparisons.preview_text(self.preview(unaided, aided))
                self.assertIn("沒戴 平均", card)
                self.assertIn(sentence, card)
                self.assertIn("差值不能單獨判定助聽器效益", card)
                self.assertIn("兩筆是不同時間填的，不一定是開始戴之前和之後的比較", card)
                self.assertNotIn("差值（配戴", card)
        card = test_hhi_comparisons.preview_text(self.preview([4] * 11 + [8], [4] * 10 + [6, 10]))
        self.assertIn("沒戴 平均 4.3 分", card)
        self.assertIn("有戴 平均 4.7 分", card)

    def test_not_applicable_skips_the_difference_and_keeps_the_items(self):
        page = self.preview([None] + [4] * 11, [6] * 12)
        card = test_hhi_comparisons.preview_text(page)
        self.assertIn("未計算整體差值：包含不適用題目或缺少完整回答", card)
        self.assertNotIn("有戴比沒戴", card)
        self.assertIn("差值不能單獨判定助聽器效益", card)
        self.assertIn("兩筆是不同時間填的，不一定是開始戴之前和之後的比較", card)
        details = re.search(
            r"<details>\s*<summary>看每一題的回答</summary>.*?</details>",
            page.content.decode(),
            re.S,
        )
        self.assertIsNotNone(details)
        for question in self.questionnaire.questions.all():
            self.assertIn(question.question_text, details.group(0))
        first = self.questionnaire.questions.get(question_number=1).question_text
        self.assertIn(
            f"{first}<br>沒戴：<strong>不適用</strong>；有戴：<strong>6</strong>", details.group(0)
        )
