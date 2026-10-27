import json
import uuid
from datetime import date, datetime
from io import StringIO
from urllib.parse import quote

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import (
    AidAndSubsidy,
    Answer,
    Audiogram,
    AudiogramPoint,
    Category,
    GuideChapterView,
    NormGroup,
    Question,
    Questionnaire,
    Submission,
    User,
)
from screening.questionnaires import hhie_s, ioi_ha, sadl, ssq12_tw, thi
from screening.questionnaires.ioi_ha import ITEM_CHOICES as IOI_HA_CHOICES
from screening.scoring import classify
from screening.tests.helpers import consented_user, submission_with_answers

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


class AidAndSubsidyExportTests(TestCase):
    """#286, #293 (spec #291 acceptance 23): the 助聽器與補助資料 in the export, the
    certificate answer too, worded as the question offers it."""

    def setUp(self):
        self.user = consented_user(username="export_aid")
        self.client.force_login(self.user)

    def exported(self):
        response = self.client.get(reverse("download_my_data"))
        return json.loads(response.content)["aid_and_subsidy"]

    def test_the_certificate_as_answered(self):
        other = consented_user(username="export_aid_other")
        AidAndSubsidy.objects.create(user=other, certificate="no_subsidy")
        aid = AidAndSubsidy.objects.create(user=self.user)
        for answer, wording in (
            ("yes", "有"),
            ("applying", "還沒有，正在申請鑑定"),
            ("no_subsidy", "沒有，不申請身障補助"),
        ):
            with self.subTest(answer=answer):
                aid.certificate = answer
                aid.save()
                self.assertEqual(self.exported()["certificate"], wording)
        self.assertNotIn("has_certificate", self.exported())

    def test_unanswered_is_null(self):
        self.assertIsNone(self.exported()["certificate"])
        AidAndSubsidy.objects.create(user=self.user, certificate="")
        self.assertIsNone(self.exported()["certificate"])

    def test_form_9_and_the_notice_as_answered(self):
        # #294: worded as the questions offer them.
        aid = AidAndSubsidy.objects.create(user=self.user)
        for form_9_done, notice_received, ears, wordings in (
            (True, True, "one", ("完成了", "收到了", "單耳")),
            (False, True, "both", ("還沒", "收到了", "雙耳")),
            (None, False, "", (None, "還沒", None)),
        ):
            with self.subTest(wordings=wordings):
                aid.form_9_done, aid.notice_received = form_9_done, notice_received
                aid.approved_ears = ears
                aid.save()
                exported = self.exported()
                self.assertEqual(
                    (
                        exported["form_9_done"],
                        exported["notice_received"],
                        exported["approved_ears"],
                    ),
                    wordings,
                )

    def test_form_25_as_answered(self):
        # #296: worded as the question offers it.
        aid = AidAndSubsidy.objects.create(user=self.user)
        for answer, wording in ((True, "完成了"), (False, "還沒"), (None, None)):
            with self.subTest(answer=answer):
                aid.form_25_done = answer
                aid.save()
                self.assertEqual(self.exported()["form_25_done"], wording)


class HearingAidExportTests(TestCase):
    """#287 (spec #284 acceptance 21): all four in the export, the labels as the form shows
    them, unanswered as null."""

    setUp = AidAndSubsidyExportTests.setUp
    exported = AidAndSubsidyExportTests.exported

    def test_all_four_filled_in(self):
        AidAndSubsidy.objects.create(
            user=self.user,
            certificate="yes",
            form_9_done=True,
            notice_received=True,
            approved_ears="both",
            fitted_on=date(2026, 5, 1),
            ear="both",
            subsidy="disability",
            level="mid",
            form_25_done=True,
        )
        self.assertEqual(
            self.exported(),
            {
                "certificate": "有",
                "form_9_done": "完成了",
                "notice_received": "收到了",
                "approved_ears": "雙耳",
                "fitted_on": "2026-05-01",
                "ear": "雙耳",
                "subsidy": "用身障補助",
                "level": "中階型",
                "form_25_done": "完成了",
                "viewed_chapters": [],
            },
        )

    def test_unanswered_are_null(self):
        unanswered = {
            "certificate": None,
            "form_9_done": None,
            "notice_received": None,
            "approved_ears": None,
            "fitted_on": None,
            "ear": None,
            "subsidy": None,
            "level": None,
            "form_25_done": None,
            "viewed_chapters": [],
        }
        self.assertEqual(self.exported(), unanswered)
        AidAndSubsidy.objects.create(user=self.user)
        self.assertEqual(self.exported(), unanswered)


class ViewedChaptersExportTests(TestCase):
    """#292 (spec #291 acceptance 23): the chapters read, by name, with the first time each."""

    setUp = AidAndSubsidyExportTests.setUp
    exported = AidAndSubsidyExportTests.exported

    def view(self, user, chapter, moment):
        view = GuideChapterView.objects.create(user=user, chapter=chapter)
        GuideChapterView.objects.filter(pk=view.pk).update(first_viewed_at=moment)

    def test_a_chapter_no_longer_in_the_guide_is_exported_by_its_slug(self):
        taipei = timezone.get_default_timezone()
        self.view(self.user, "old-chapter", datetime(2026, 10, 19, 21, 5, tzinfo=taipei))
        self.assertEqual(
            self.exported()["viewed_chapters"],
            [{"chapter": "old-chapter", "first_viewed_at": "2026-10-19T21:05:00+08:00"}],
        )

    def test_each_chapter_read_with_its_name_and_first_time_in_order(self):
        taipei = timezone.get_default_timezone()
        self.view(self.user, "types-and-prices", datetime(2026, 10, 20, 9, 30, tzinfo=taipei))
        self.view(self.user, "before-you-go", datetime(2026, 10, 19, 21, 5, tzinfo=taipei))
        other = consented_user(username="export_views_other")
        self.view(other, "form-9", datetime(2026, 10, 18, 8, 0, tzinfo=taipei))
        self.assertEqual(
            self.exported()["viewed_chapters"],
            [
                {"chapter": "去找聽力師之前", "first_viewed_at": "2026-10-19T21:05:00+08:00"},
                {
                    "chapter": "助聽器的種類與價格",
                    "first_viewed_at": "2026-10-20T09:30:00+08:00",
                },
            ],
        )


class ResultTypesExportTests(TestCase):
    """#387: the export of every result type, the same before and after it asks submission.result.

    Expected from the download before the change; key order matters, since the file is
    json.dumps of these dicts. Question texts are left out: they come from the questions alone.
    """

    fixtures = ("questions_fixture.json",)

    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.user = consented_user(username="export_result_types")
        self.client.force_login(self.user)
        sadl_scores = [4] * 15
        sadl_scores[10] = sadl_scores[13] = None  # items 11 and 14 are 不適用
        records = (
            (hhie_s.CODE, [4, 4, 2, 0, 0, 0, 4, 0, 0, 2], {"wearing_hearing_aid": False}),
            (thi.CODE, [2] * 25, {"wearing_hearing_aid": False}),
            (ssq12_tw.CODE, [6] * 12, {"wearing_hearing_aid": True}),
            (ssq12_tw.CODE, [None] + [3] * 11, {"wearing_hearing_aid": False}),
            (ioi_ha.CODE, [3] * 7, {"norm_group": NormGroup.MILD_MODERATE}),
            (sadl.CODE, sadl_scores, {"wearing_hearing_aid": True}),
        )
        taipei = timezone.get_default_timezone()
        for day, (code, scores, fields) in enumerate(records, start=1):
            record = submission_with_answers(self.user, code, scores, **fields)
            moment = datetime(2026, 10, day, 9, 0, tzinfo=taipei)
            Submission.objects.filter(pk=record.pk).update(created_at=moment)

    def exported(self):
        data = json.loads(self.client.get(reverse("download_my_data")).content)
        return data["submissions"]

    def test_each_result_type_exports_as_before(self):
        exported = self.exported()
        for entry in exported:
            for answer in entry["answers"]:
                del answer["question"]
        no_wearing = "未記錄"
        self.assertEqual(
            [list(entry.items()) for entry in exported],
            [
                [
                    ("questionnaire", "SADL"),
                    ("created_at", "2026-10-06T09:00:00+08:00"),
                    ("wearing_hearing_aid", "有戴"),
                    (
                        "answers",
                        [
                            {
                                "number": n,
                                "score": None if n in (11, 14) else 4,
                                "choice": "不適用" if n in (11, 14) else "中等程度",
                            }
                            for n in range(1, 16)
                        ],
                    ),
                    ("total_score", None),
                    ("emotional_score", None),
                    ("social_score", None),
                    ("level", None),
                    ("norm_group", None),
                    ("overall_score", "4.0"),
                    (
                        "subscale_scores",
                        {
                            "正面效果": "4.0",
                            "服務與費用": "4.0",
                            "負面特徵": "4.0",
                            "個人形象": "4.0",
                        },
                    ),
                ],
                [
                    ("questionnaire", "IOI-HA"),
                    ("created_at", "2026-10-05T09:00:00+08:00"),
                    ("wearing_hearing_aid", no_wearing),
                    (
                        "answers",
                        [
                            {"number": n, "score": 3, "choice": IOI_HA_CHOICES[n][2]}
                            for n in range(1, 8)
                        ],
                    ),
                    ("total_score", None),
                    ("emotional_score", None),
                    ("social_score", None),
                    ("level", None),
                    ("norm_group", "輕度至中度"),
                ],
                [
                    ("questionnaire", "SSQ12-TW"),
                    ("created_at", "2026-10-04T09:00:00+08:00"),
                    ("wearing_hearing_aid", "沒戴"),
                    (
                        "answers",
                        [{"number": 1, "score": None, "choice": "不適用"}]
                        + [{"number": n, "score": 3, "choice": "3"} for n in range(2, 13)],
                    ),
                    ("total_score", None),
                    ("emotional_score", None),
                    ("social_score", None),
                    ("level", None),
                    ("norm_group", None),
                    ("average_score", None),
                    ("average_unavailable_reason", "未計算：包含不適用題目"),
                ],
                [
                    ("questionnaire", "SSQ12-TW"),
                    ("created_at", "2026-10-03T09:00:00+08:00"),
                    ("wearing_hearing_aid", "有戴"),
                    (
                        "answers",
                        [{"number": n, "score": 6, "choice": "6"} for n in range(1, 13)],
                    ),
                    ("total_score", None),
                    ("emotional_score", None),
                    ("social_score", None),
                    ("level", None),
                    ("norm_group", None),
                    ("average_score", "6.0"),
                    ("average_unavailable_reason", None),
                ],
                [
                    ("questionnaire", "THI"),
                    ("created_at", "2026-10-02T09:00:00+08:00"),
                    ("wearing_hearing_aid", "沒戴"),
                    (
                        "answers",
                        [{"number": n, "score": 2, "choice": "偶爾"} for n in range(1, 26)],
                    ),
                    ("total_score", 50),
                    ("emotional_score", None),
                    ("social_score", None),
                    ("level", "中度障礙"),
                    ("norm_group", None),
                ],
                [
                    ("questionnaire", "HHIE-S"),
                    ("created_at", "2026-10-01T09:00:00+08:00"),
                    ("wearing_hearing_aid", "沒戴"),
                    (
                        "answers",
                        [
                            {"number": n, "score": score, "choice": label}
                            for n, score, label in (
                                (1, 4, "常常"),
                                (2, 4, "常常"),
                                (3, 2, "有時"),
                                (4, 0, "從未"),
                                (5, 0, "從未"),
                                (6, 0, "從未"),
                                (7, 4, "常常"),
                                (8, 0, "從未"),
                                (9, 0, "從未"),
                                (10, 2, "有時"),
                            )
                        ],
                    ),
                    ("total_score", 16),
                    ("emotional_score", 12),
                    ("social_score", 4),
                    ("level", "輕度到中度影響"),
                    ("norm_group", None),
                ],
            ],
        )
