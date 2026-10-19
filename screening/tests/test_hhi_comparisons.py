"""Selected HHI comparisons are explicit and persist per questionnaire (#82)."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from screening.models import Answer, Question, Questionnaire, Submission
from screening.tests.helpers import consented_user


class HhiComparisonTests(TestCase):
    def setUp(self):
        call_command("seed_hhia_s", stdout=StringIO())
        self.questionnaire = Questionnaire.objects.get(code="hhia-s")
        self.user = consented_user(username="compare_user", password="Test-pass-12345")
        self.other = consented_user(username="compare_other")
        self.client.force_login(self.user)
        self.url = f"/comparisons/{self.questionnaire.pk}"

    def record(self, wearing, score=2, user=None, questionnaire=None):
        questionnaire = questionnaire or self.questionnaire
        record = Submission.objects.create(
            user=user or self.user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=q, score=score)
            for q in questionnaire.questions.all()
        )
        return record

    def test_preview_does_not_save_and_saved_pair_survives_new_records(self):
        unaided = self.record(False, 4)
        aided = self.record(True, 2)
        data = {"unaided": unaided.pk, "aided": aided.pk}
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "尚未保留")
        page = self.client.get(self.url, data)
        self.assertContains(page, "目前查看的兩筆")
        self.assertContains(page, "40 分")
        self.assertContains(page, "20 分")
        self.assertContains(page, "尚未保留")
        response = self.client.post(self.url, {**data, "action": "save"})
        self.assertRedirects(response, self.url)
        self.record(False, 0)
        self.record(True, 0)
        self.client.logout()
        self.client.login(username="compare_user", password="Test-pass-12345")
        page = self.client.get(self.url)
        saved = page.context["saved"]
        self.assertEqual(saved.unaided_id, unaided.pk)
        self.assertEqual(saved.aided_id, aided.pk)
        self.assertContains(page, "報告保留組合")
        self.assertContains(page, "不一定是開始使用助聽器前後")

    def test_versions_keep_independent_pairs_and_removal_keeps_answers(self):
        hhie = Questionnaire.objects.create(code="hhie-s", questionnaire_name="HHIE-S")
        Question.objects.bulk_create(
            Question(questionnaire=hhie, question_text=f"題{n}", question_number=n)
            for n in range(1, 11)
        )
        first = self.record(False)
        second = self.record(True)
        self.client.post(self.url, {"unaided": first.pk, "aided": second.pk, "action": "save"})
        other_first = self.record(False, questionnaire=hhie)
        other_second = self.record(True, questionnaire=hhie)
        other_url = f"/comparisons/{hhie.pk}"
        self.client.post(
            other_url, {"unaided": other_first.pk, "aided": other_second.pk, "action": "save"}
        )
        replacement = self.record(True, 0)
        self.client.post(self.url, {"unaided": first.pk, "aided": replacement.pk, "action": "save"})
        self.assertEqual(self.client.get(self.url).context["saved"].aided_id, replacement.pk)
        self.assertEqual(self.client.get(other_url).context["saved"].aided_id, other_second.pk)
        count = Answer.objects.count()
        self.client.post(self.url, {"action": "remove"})
        self.assertFalse(
            self.user.report_comparisons.filter(questionnaire=self.questionnaire).exists()
        )
        self.assertEqual(self.user.report_comparisons.count(), 1)
        self.assertEqual(Answer.objects.count(), count)
        self.assertTrue(Submission.objects.filter(pk=second.pk).exists())

    def test_invalid_selections_cannot_replace_saved_pair_or_leak_other_users(self):
        first = self.record(False)
        second = self.record(True)
        data = {"unaided": first.pk, "aided": second.pk, "action": "save"}
        self.client.post(self.url, data)
        stranger = self.record(True, user=self.other)
        unknown = self.record(None)
        incomplete = self.record(True)
        incomplete.answers.first().delete()
        other_questionnaire = Questionnaire.objects.create(
            code="hhie-s", questionnaire_name="HHIE-S"
        )
        different = self.record(True, questionnaire=other_questionnaire)
        for bad in (first, stranger, unknown, incomplete, different):
            with self.subTest(record=bad.pk):
                response = self.client.post(self.url, {**data, "aided": bad.pk})
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, 'id="comparison-errors"', status_code=400)
                self.assertEqual(self.user.report_comparisons.get().aided_id, second.pk)
        self.client.force_login(self.other)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.other.report_comparisons.exists())
        self.client.post(self.url, {"action": "remove"})
        self.assertTrue(self.user.report_comparisons.exists())
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_export_and_account_deletion_include_only_own_saved_comparisons(self):
        first = self.record(False, 4)
        second = self.record(True, 2)
        self.client.post(self.url, {"unaided": first.pk, "aided": second.pk, "action": "save"})
        stranger = self.record(False, user=self.other)
        payload = self.client.get("/my_data/download").json()
        comparisons = payload["report_comparisons"]
        self.assertEqual(len(comparisons), 1)
        self.assertEqual(comparisons[0]["questionnaire"], self.questionnaire.questionnaire_name)
        self.assertEqual(comparisons[0]["unaided"]["total_score"], 40)
        self.assertEqual(comparisons[0]["aided"]["total_score"], 20)
        response = self.client.post("/account/delete", {"password": "Test-pass-12345"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Submission.objects.filter(user_id=self.user.pk).exists())
        self.assertTrue(Submission.objects.filter(pk=stranger.pk).exists())
