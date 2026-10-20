"""IOI-HA fixed norm basis across both HHI questionnaires (#81)."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Questionnaire, Submission
from screening.tests import test_ioi_ha


class AdultIoiNormTests(TestCase):
    setUpTestData = classmethod(test_ioi_ha.IoiHaTests.setUpTestData.__func__)
    _post = test_ioi_ha.IoiHaTests._post
    _hhie_s = test_ioi_ha.IoiHaTests._hhie_s

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.ioi_ha.pk])
        call_command("seed_questionnaires", stdout=StringIO())
        self.hhia = Questionnaire.objects.get(code="hhia-s")

    def hhia_record(self, total=24, user=None, wearing=False):
        record = Submission.objects.create(
            user=user or self.user, questionnaire=self.hhia, wearing_hearing_aid=wearing
        )
        scores = [4] * (total // 4) + ([2] if total % 4 else [])
        scores += [0] * (10 - len(scores))
        Answer.objects.bulk_create(
            Answer(submission=record, question=q, score=score)
            for q, score in zip(self.hhia.questions.all(), scores, strict=True)
        )
        return record

    def test_hhia_is_disclosed_before_answering_and_frozen_after_submission(self):
        self._hhie_s(40, False)
        basis = self.hhia_record(24)
        self.user.birth_year = 1940
        self.user.save()
        page = self.client.get(self.url)
        self.assertContains(page, "本次常模依據")
        self.assertContains(page, "HHIA-S")
        self.assertContains(page, "24 分")
        self._post()
        record = Submission.objects.get(questionnaire=self.ioi_ha)
        self.assertEqual(record.norm_basis_id, basis.pk)
        self.assertEqual(record.norm_group, "mild_moderate")
        self._hhie_s(40, False)
        page = self.client.get(reverse("result", args=[record.pk]))
        self.assertContains(page, "HHIA-S")
        self.assertContains(page, "24 分")
        record.refresh_from_db()
        self.assertEqual(record.norm_basis_id, basis.pk)

    def test_group_boundaries_and_missing_valid_basis(self):
        for total, group in (
            (0, "mild_moderate"),
            (24, "mild_moderate"),
            (26, "moderately_severe"),
            (40, "moderately_severe"),
        ):
            with self.subTest(total=total):
                basis = self.hhia_record(total)
                self._post()
                record = Submission.objects.filter(questionnaire=self.ioi_ha).latest("pk")
                self.assertEqual(record.norm_basis_id, basis.pk)
                self.assertEqual(record.norm_group, group)

    def test_incomplete_invalid_aided_unknown_and_other_users_records_are_skipped(self):
        valid = self.hhia_record(0)
        incomplete = self.hhia_record(24)
        incomplete.answers.first().delete()
        invalid = self.hhia_record(24)
        invalid.answers.filter(question__question_number=1).update(score=3)
        not_applicable = self.hhia_record(24)
        not_applicable.answers.filter(question__question_number=1).update(score=None)
        self.hhia_record(40, wearing=True)
        self.hhia_record(40, wearing=None)
        self.hhia_record(40, user=self.other)
        self._post()
        self.assertEqual(
            Submission.objects.filter(questionnaire=self.ioi_ha).latest("pk").norm_basis_id,
            valid.pk,
        )

    def test_basis_shown_on_open_page_is_kept_if_new_hhi_arrives(self):
        basis = self.hhia_record(24)
        page = self.client.get(self.url)
        token = page.context["norm_token"]
        self._hhie_s(40, False)
        self._post(norm_token=token)
        record = Submission.objects.filter(questionnaire=self.ioi_ha).latest("pk")
        self.assertEqual(record.norm_basis_id, basis.pk)
        self.assertEqual(record.norm_group, "mild_moderate")
        other_client = self.client_class()
        other_client.force_login(self.other)
        self.assertEqual(other_client.get(reverse("result", args=[record.pk])).status_code, 404)
        self.assertEqual(other_client.post(self.url, {"norm_token": token}).status_code, 400)

    def test_no_basis_remains_ungrouped_even_after_new_hhi(self):
        page = self.client.get(self.url)
        token = page.context["norm_token"]
        self.hhia_record(40)
        self._post(norm_token=token)
        record = Submission.objects.get(questionnaire=self.ioi_ha)
        self.assertIsNone(record.norm_basis_id)
        self.assertEqual(record.norm_group, "ungrouped")
        result = self.client.get(reverse("result", args=[record.pk]))
        self.assertContains(result, "完整有效的未配戴 HHIA-S／HHIE-S")
        self.assertNotContains(result, "（低於常模）")
        self.assertNotContains(result, 'class="ioi-note"')

    def test_saved_comparison_and_later_age_do_not_rewrite_completed_or_old_ioi(self):
        basis = self.hhia_record(24)
        self._post()
        fixed = Submission.objects.get(questionnaire=self.ioi_ha)
        old = Submission.objects.create(
            user=self.user, questionnaire=self.ioi_ha, norm_group="ungrouped"
        )
        replacement = self.hhia_record(40)
        aided = self.hhia_record(0, wearing=True)
        response = self.client.post(
            f"/comparisons/{self.hhia.pk}",
            {"unaided": replacement.pk, "aided": aided.pk, "action": "save"},
        )
        self.assertEqual(response.status_code, 302)
        self.user.birth_year = 1940
        self.user.save()
        for record in (fixed, old):
            self.client.get(reverse("result", args=[record.pk]))
            record.refresh_from_db()
        self.assertEqual(fixed.norm_basis_id, basis.pk)
        self.assertEqual(fixed.norm_group, "mild_moderate")
        self.assertIsNone(old.norm_basis_id)
        self.assertEqual(old.norm_group, "ungrouped")
        self.user.delete_with_data()
        self.assertFalse(Submission.objects.filter(pk__in=(fixed.pk, basis.pk, old.pk)).exists())
