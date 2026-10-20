import json
import uuid
from datetime import date
from urllib.parse import quote

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import (
    Answer,
    Audiogram,
    AudiogramPoint,
    Category,
    NormGroup,
    Question,
    Questionnaire,
    Submission,
    User,
)
from screening.questionnaires.ioi_ha import ITEM_CHOICES as IOI_HA_CHOICES
from screening.scoring import classify
from screening.tests.helpers import consented_user

FORBIDDEN_KEYS = {"id", "password", "is_staff", "is_superuser", "last_login", "idempotency_key"}


def _all_keys(data):
    if isinstance(data, dict):
        for key, value in data.items():
            yield key
            yield from _all_keys(value)
    elif isinstance(data, list):
        for item in data:
            yield from _all_keys(item)


class DownloadMyDataTests(TestCase):
    """Spec docs/specs/phase-07/phase7_data_export.md, acceptance 1-16."""

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(
            username="export_a", email="a@example.com", password="Xk9#mPq2vLw", birth_year=1950
        )
        cls.other = consented_user(username="export_b", email="b@example.com")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.emotional = Question.objects.create(
            questionnaire=cls.hhie_s,
            question_text="假題目一",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        cls.social = Question.objects.create(
            questionnaire=cls.hhie_s,
            question_text="假題目二",
            question_number=2,
            category=Category.SOCIAL,
        )
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        cls.ioi_question = Question.objects.create(
            questionnaire=cls.ioi_ha, question_text="假 IOI 題目", question_number=1
        )

    def setUp(self):
        self.url = reverse("download_my_data")
        self.client.force_login(self.user)

    def _hhie_s(self, user, emotional, social, wearing=True):
        submission = Submission.objects.create(
            user=user, questionnaire=self.hhie_s, wearing_hearing_aid=wearing
        )
        Answer.objects.create(submission=submission, question=self.emotional, score=emotional)
        Answer.objects.create(submission=submission, question=self.social, score=social)
        return submission

    def _audiogram(self, user, tested_on=date(2026, 3, 4)):
        audiogram = Audiogram.objects.create(user=user, tested_on=tested_on)
        AudiogramPoint.objects.create(
            audiogram=audiogram, ear="right", conduction="air", frequency=1000, db=35
        )
        AudiogramPoint.objects.create(
            audiogram=audiogram,
            ear="left",
            conduction="bone",
            frequency=2000,
            db=70,
            no_response=True,
            masked=True,
        )
        return audiogram

    def _download(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    # 1
    def test_contains_all_of_my_records(self):
        self._hhie_s(self.user, 4, 2)
        self._hhie_s(self.user, 2, 0)
        self._audiogram(self.user)
        data = self._download()

        self.assertEqual(data["account"]["username"], "export_a")
        self.assertEqual(data["account"]["email"], "a@example.com")
        self.assertEqual(data["account"]["birth_year"], 1950)
        self.assertTrue(data["account"]["date_joined"].endswith("+08:00"))

        self.assertEqual(len(data["consents"]), 1)
        self.assertEqual(data["consents"][0]["version"], self.user.consents.get().version)
        self.assertTrue(data["consents"][0]["agreed_at"].endswith("+08:00"))

        self.assertEqual(len(data["submissions"]), 2)
        newest = data["submissions"][0]
        self.assertEqual(newest["questionnaire"], "HHIE-S")
        self.assertTrue(newest["created_at"].endswith("+08:00"))
        self.assertEqual(newest["total_score"], 2)
        self.assertEqual(newest["emotional_score"], 2)
        self.assertEqual(newest["social_score"], 0)
        self.assertEqual(newest["level"], classify(2, "hhie-s")["text"])
        self.assertEqual(
            newest["answers"],
            [
                {"number": 1, "question": "假題目一", "score": 2, "choice": "有時"},
                {"number": 2, "question": "假題目二", "score": 0, "choice": "從未"},
            ],
        )
        self.assertEqual(data["submissions"][1]["total_score"], 6)

        self.assertEqual(len(data["audiograms"]), 1)
        audiogram = data["audiograms"][0]
        self.assertEqual(audiogram["tested_on"], "2026-03-04")
        self.assertTrue(audiogram["created_at"].endswith("+08:00"))
        self.assertCountEqual(
            audiogram["points"],
            [
                {
                    "ear": "右耳",
                    "conduction": "氣導",
                    "frequency": 1000,
                    "db": 35,
                    "no_response": False,
                    "masked": False,
                },
                {
                    "ear": "左耳",
                    "conduction": "骨導",
                    "frequency": 2000,
                    "db": 70,
                    "no_response": True,
                    "masked": True,
                },
            ],
        )

    # 2
    def test_contains_nothing_of_other_users(self):
        self._hhie_s(self.user, 4, 4)
        self._hhie_s(self.other, 2, 2)
        self._audiogram(self.other, tested_on=date(2025, 1, 2))
        response = self.client.get(self.url)
        data = json.loads(response.content)
        self.assertEqual(len(data["submissions"]), 1)
        self.assertEqual(data["submissions"][0]["total_score"], 8)
        self.assertEqual(data["audiograms"], [])
        content = response.content.decode()
        self.assertNotIn("export_b", content)
        self.assertNotIn("b@example.com", content)
        self.assertNotIn("2025-01-02", content)

    # 3
    def test_signed_out_goes_to_login_and_back(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )

    # 4
    def test_new_account_downloads_empty_lists(self):
        user = consented_user(username="export_new")
        self.client.force_login(user)
        data = self._download()
        self.assertEqual(data["account"]["username"], "export_new")
        self.assertIsNone(data["account"]["birth_year"])
        self.assertEqual(data["submissions"], [])
        self.assertEqual(data["audiograms"], [])

    # 5
    def test_zero_score_is_zero_not_blank(self):
        self._hhie_s(self.user, 0, 0)
        submission = self._download()["submissions"][0]
        self.assertEqual(submission["total_score"], 0)
        self.assertEqual(submission["emotional_score"], 0)
        self.assertEqual(submission["social_score"], 0)
        self.assertEqual(submission["level"], classify(0, "hhie-s")["text"])

    # 6
    def test_no_secrets_or_internal_ids(self):
        key = uuid.uuid4()
        submission = self._hhie_s(self.user, 4, 4)
        Submission.objects.filter(pk=submission.pk).update(idempotency_key=key)
        self._audiogram(self.user)
        response = self.client.get(self.url)
        self.assertEqual(FORBIDDEN_KEYS & set(_all_keys(json.loads(response.content))), set())
        content = response.content.decode()
        self.assertNotIn(User.objects.get(pk=self.user.pk).password, content)
        self.assertNotIn(str(key), content)

    # 7
    def test_hearing_aid_unrecorded_is_not_no(self):
        self._hhie_s(self.user, 0, 0, wearing=None)
        self._hhie_s(self.user, 0, 0, wearing=False)
        submissions = self._download()["submissions"]
        self.assertEqual(submissions[0]["wearing_hearing_aid"], "沒戴")
        self.assertEqual(submissions[1]["wearing_hearing_aid"], "未記錄")

    # 8
    def test_downloads_as_uncached_json_file(self):
        response = self.client.get(self.url)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        filename = f"hearwell-我的資料-{timezone.localdate().isoformat()}.json"
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))
        self.assertIn(quote(filename), response["Content-Disposition"])
        # Chinese is written as is, not as \uXXXX escapes.
        self.assertNotIn(b"\\u", response.content)

    # 9
    def test_query_count_does_not_grow_with_records(self):
        self._hhie_s(self.user, 4, 4)
        self._audiogram(self.user)
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for _ in range(19):
            self._hhie_s(self.user, 2, 2)
            self._audiogram(self.user)
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(many), len(few))

    # 10
    def test_privacy_page_links_to_download(self):
        response = self.client.get(reverse("privacy"))
        self.assertContains(response, "下載自己的資料")
        self.assertContains(response, f'href="{self.url}"')

    # 11
    def test_other_methods_are_405(self):
        for method in ("post", "put", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)

    # 12
    def test_user_without_consent_can_download_but_nothing_else(self):
        user = User.objects.create_user(username="export_old")
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        response = self.client.get(reverse("my_hearing"))
        self.assertTrue(response.url.startswith(reverse("consent")))

    # 13
    def test_history_page_has_download_button(self):
        for has_records in (False, True):
            if has_records:
                self._hhie_s(self.user, 4, 4)
            with self.subTest(has_records=has_records):
                # The entry moved to account settings (spec phase9_ui_refresh_3_structure.md 4.2).
                response = self.client.get(reverse("account_settings"))
                self.assertContains(response, "下載我的資料")
                self.assertContains(response, f'href="{self.url}"')

    # 14
    def test_choice_text_matches_answer_page(self):
        self._hhie_s(self.user, 4, 0)
        Submission.objects.create(
            user=self.user, questionnaire=self.ioi_ha, norm_group=NormGroup.UNGROUPED
        ).answers.create(question=self.ioi_question, score=3)
        ioi_ha, hhie_s = self._download()["submissions"]
        self.assertEqual(hhie_s["answers"][0]["choice"], "常常")
        self.assertEqual(ioi_ha["answers"][0]["choice"], IOI_HA_CHOICES[1][2])

    # 15
    def test_not_applicable_is_null(self):
        self._hhie_s(self.user, 4, 0)
        Submission.objects.create(
            user=self.user, questionnaire=self.ioi_ha, norm_group=NormGroup.MILD_MODERATE
        ).answers.create(question=self.ioi_question, score=3)
        ioi_ha, hhie_s = self._download()["submissions"]
        for field in ("total_score", "emotional_score", "social_score", "level"):
            with self.subTest(field=field):
                self.assertIsNone(ioi_ha[field])
        self.assertEqual(ioi_ha["norm_group"], "輕度至中度")
        self.assertIsNone(hhie_s["norm_group"])

    # 16
    def test_score_outside_choices_still_downloads(self):
        submission = self._hhie_s(self.user, 4, 4)
        submission.answers.filter(question=self.social).update(score=1)
        answers = self._download()["submissions"][0]["answers"]
        self.assertEqual(answers[1]["score"], 1)
        self.assertIsNone(answers[1]["choice"])
