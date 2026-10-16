import json
import os
import platform
import re
import struct
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import ClassVar
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.core.management.utils import get_random_secret_key
from django.db import DatabaseError, IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import RestrictedError
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone

from screening import scoring
from screening.api import views as api_views
from screening.models import Answer, Category, Question, Questionnaire, Submission, User
from screening.scoring import classify, get_advice


class ClassifyTests(SimpleTestCase):
    def test_hhie_s_boundaries(self):
        expected = {
            0: "normal",
            8: "normal",
            10: "mild_to_moderate",
            24: "mild_to_moderate",
            26: "severe",
            40: "severe",
        }
        for score, level in expected.items():
            with self.subTest(score=score):
                self.assertEqual(classify(score, "hhie-s")["level"], level)

    def test_score_out_of_range_is_unknown(self):
        for score in (-2, 42):
            with self.subTest(score=score), self.assertLogs("screening.scoring", "ERROR"):
                self.assertEqual(classify(score, "hhie-s")["level"], "unknown")

    def test_questionnaire_without_thresholds_is_unknown(self):
        with self.assertLogs("screening.scoring", "ERROR"):
            result = classify(10, "hhia-s")
        self.assertEqual(result["level"], "unknown")
        self.assertEqual(result["text"], "無法判讀")


class ClassifyViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="user")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")

    def _make_submission(self, questionnaire, score):
        question = Question.objects.create(
            questionnaire=questionnaire,
            question_text="第一題",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        submission = Submission.objects.create(user=self.user, questionnaire=questionnaire)
        Answer.objects.create(submission=submission, question=question, score=score)
        return submission

    def test_result_page_shows_unknown_for_questionnaire_without_thresholds(self):
        submission = self._make_submission(self.hhia_s, score=4)
        self.client.force_login(self.user)
        with self.assertLogs("screening.scoring", "ERROR"):
            response = self.client.get(reverse("result", args=[submission.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "無法判讀")
        self.assertContains(response, "result-banner-unknown")
        self.assertContains(response, "這次的作答結果無法判讀分級")

    def test_history_page_survives_unknown_submission(self):
        self._make_submission(self.hhie_s, score=4)
        self._make_submission(self.hhia_s, score=4)
        self.client.force_login(self.user)
        # One tab per questionnaire (phase4_history_by_questionnaire.md): each tab must survive.
        with self.assertLogs("screening.scoring", "ERROR") as logs:
            response = self.client.get(reverse("my_hearing") + "?questionnaire=hhia-s")
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "無法判讀")
        response = self.client.get(reverse("my_hearing") + "?questionnaire=hhie-s")
        self.assertContains(response, "無/極輕微影響")

    def test_result_and_history_show_same_classification(self):
        submission = self._make_submission(self.hhie_s, score=4)
        self.client.force_login(self.user)
        result = self.client.get(reverse("result", args=[submission.id]))
        history = self.client.get(reverse("my_hearing"))
        self.assertContains(result, "無/極輕微影響")
        self.assertContains(history, "無/極輕微影響")


class SubmissionResultAccessTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="user_a")
        self.user_b = User.objects.create_user(username="user_b")
        self.questionnaire = Questionnaire.objects.create(
            questionnaire_name="測試問卷", code="test"
        )
        self.submission = Submission.objects.create(
            user=self.user_a, questionnaire=self.questionnaire
        )

    def test_user_cannot_view_others_submission(self):
        self.client.force_login(self.user_b)
        url = reverse("result", kwargs={"submission_id": self.submission.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class LoginRequiredTests(TestCase):
    def test_not_login_visit_can_redirect(self):
        protected_url = reverse("my_hearing")
        response = self.client.get(protected_url)
        login_url = reverse("login")
        expected_reversed_url = f"{login_url}?next={protected_url}"
        self.assertRedirects(response, expected_reversed_url)


class ScreeningViewAcceptValueTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="user_a")
        self.questionnaire = Questionnaire.objects.create(
            questionnaire_name="測試問卷", code="hhie-s"
        )
        self.question = Question.objects.create(
            questionnaire=self.questionnaire,
            question_text="數值正確？",
            question_number=1,
            category=Category.EMOTIONAL,
        )

    def test_screening_view_accept_correct_value(self):
        self.client.force_login(self.user_a)
        url = reverse("screening", kwargs={"questionnaire_id": self.questionnaire.id})
        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-0-score": "4",
            "form-0-question_id": str(self.question.id),
            "wearing_hearing_aid": "True",
        }
        response = self.client.post(url, data)
        submission = Submission.objects.get(user=self.user_a, questionnaire=self.questionnaire)
        expected_reversed_url = reverse("result", kwargs={"submission_id": submission.id})
        self.assertTrue(Answer.objects.filter(question=self.question, score=4).exists())
        self.assertRedirects(response, expected_reversed_url)


class EmptyQuestionnaireSubmissionTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="user_a")
        self.questionnaire = Questionnaire.objects.create(
            questionnaire_name="測試空submission", code="test"
        )

    def test_zero_question_questionnaire(self):
        self.client.force_login(self.user_a)
        url = reverse("screening", kwargs={"questionnaire_id": self.questionnaire.id})
        data = {
            "form-TOTAL_FORMS": 0,
            "form-INITIAL_FORMS": 0,
        }
        self.client.post(url, data)
        self.assertFalse(
            Submission.objects.filter(user=self.user_a, questionnaire=self.questionnaire).exists()
        )


class DuplicateAnswerSubmissionTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="user_a")
        self.questionnaire = Questionnaire.objects.create(
            questionnaire_name="測試重複答案", code="test"
        )
        self.question_1 = Question.objects.create(
            questionnaire=self.questionnaire,
            question_text="第一題",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        self.question_2 = Question.objects.create(
            questionnaire=self.questionnaire,
            question_text="第二題",
            question_number=2,
            category=Category.SOCIAL,
        )

    def test_duplicate_answer_submission(self):
        self.client.force_login(self.user_a)
        url = reverse("screening", kwargs={"questionnaire_id": self.questionnaire.id})
        data = {
            "form-TOTAL_FORMS": 3,
            "form-INITIAL_FORMS": 0,
            "form-0-score": 4,
            "form-0-question_id": str(self.question_1.id),
            "form-1-score": 2,
            "form-1-question_id": str(self.question_2.id),
            "form-2-score": 2,
            "form-2-question_id": str(self.question_1.id),
            "wearing_hearing_aid": "True",
        }
        response = self.client.post(url, data)
        self.assertFalse(
            Submission.objects.filter(user=self.user_a, questionnaire=self.questionnaire).exists()
        )
        self.assertEqual(response.status_code, 200)


class ModelsUniqueConstraintTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="user_a")
        self.questionnaire = Questionnaire.objects.create(
            questionnaire_name="測試問卷", code="test"
        )
        self.question = Question.objects.create(
            questionnaire=self.questionnaire,
            question_text="constraint正確?",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        self.submission = Submission.objects.create(
            user=self.user_a, questionnaire=self.questionnaire
        )
        self.answer = Answer.objects.create(
            submission=self.submission, question=self.question, score=0
        )

    def test_question_model_unique_constraint(self):
        with self.assertRaises(IntegrityError):
            Question.objects.create(
                questionnaire=self.questionnaire,
                question_text="constraint正確?",
                question_number=1,
                category=Category.EMOTIONAL,
            )

    def test_answer_model_unique_constraint(self):
        with self.assertRaises(IntegrityError):
            Answer.objects.create(submission=self.submission, question=self.question, score=0)


class ScoringAggregateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="user")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="測試問卷", code="test")
        questions_emo = [
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"情緒題{i}",
                question_number=i,
                category=Category.EMOTIONAL,
            )
            for i in range(1, 6)
        ]
        questions_soc = [
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"社交題{i}",
                question_number=i,
                category=Category.SOCIAL,
            )
            for i in range(6, 11)
        ]
        cls.questions_e = Question.objects.bulk_create(questions_emo)
        cls.questions_s = Question.objects.bulk_create(questions_soc)

    def _make_submission(self, emotional_score, social_score):
        submission = Submission.objects.create(user=self.user, questionnaire=self.questionnaire)
        answers_e = [
            Answer(submission=submission, question=question, score=emotional_score)
            for question in self.questions_e
        ]
        answers_s = [
            Answer(submission=submission, question=question, score=social_score)
            for question in self.questions_s
        ]
        answers = [*answers_e, *answers_s]
        Answer.objects.bulk_create(answers)
        return submission

    def test_emotional_full_marks(self):
        submission = self._make_submission(emotional_score=4, social_score=0)
        self.assertEqual(submission.total_answer_score, 20)
        self.assertEqual(submission.emotional_score, 20)
        self.assertEqual(submission.social_score, 0)

    def test_social_full_marks(self):
        submission = self._make_submission(emotional_score=0, social_score=4)
        self.assertEqual(submission.total_answer_score, 20)
        self.assertEqual(submission.emotional_score, 0)
        self.assertEqual(submission.social_score, 20)

    def test_mix_marks(self):
        submission = self._make_submission(emotional_score=4, social_score=2)
        self.assertEqual(submission.total_answer_score, 30)
        self.assertEqual(submission.emotional_score, 20)
        self.assertEqual(submission.social_score, 10)

    def test_calculate_score_return_zero(self):
        submission = Submission.objects.create(user=self.user, questionnaire=self.questionnaire)
        self.assertEqual(submission.total_answer_score, 0)
        self.assertEqual(submission.emotional_score, 0)
        self.assertEqual(submission.social_score, 0)


class HistoryScorePathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="user")
        cls.other = User.objects.create_user(username="other")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )

    def _make_submission(self, user, scores):
        submission = Submission.objects.create(user=user, questionnaire=self.questionnaire)
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(self.questions, scores, strict=False)
        )
        return submission

    def _count_history_queries(self, expected_rows):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse("my_hearing"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["submissions"]), expected_rows)
        return len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_submissions(self):
        self.client.force_login(self.user)
        self._make_submission(self.user, [4] * 10)
        one = self._count_history_queries(expected_rows=1)
        for _ in range(4):
            self._make_submission(self.user, [2] * 10)
        five = self._count_history_queries(expected_rows=5)
        self.assertEqual(one, five)

    def test_history_and_result_show_same_scores(self):
        # emotional 5 x 4 = 20, social 3 x 2 = 6 -> total 26 (severe)
        submission = self._make_submission(self.user, [4, 4, 4, 4, 4, 2, 2, 2, 0, 0])
        self.client.force_login(self.user)
        history = self.client.get(reverse("my_hearing"))
        result = self.client.get(reverse("result", args=[submission.id]))
        self.assertContains(history, "總分：26")
        self.assertContains(history, "顯著影響")
        self.assertContains(result, "總分 26 分")
        self.assertContains(result, "情緒分數：20")
        self.assertContains(result, "社交分數：6")
        self.assertContains(result, "顯著影響")

    def test_submission_without_answers_scores_zero(self):
        self._make_submission(self.user, [])
        self.client.force_login(self.user)
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, "總分：0")
        self.assertContains(response, "無/極輕微影響")

    def test_history_only_shows_own_submissions(self):
        own = self._make_submission(self.user, [0] * 10)
        others = self._make_submission(self.other, [4] * 10)
        self.client.force_login(self.user)
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, reverse("result", args=[own.id]))
        self.assertNotContains(response, reverse("result", args=[others.id]))


class AdminLockAnsweredTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(username="admin", password="pw")
        cls.user = User.objects.create_user(username="user")
        cls.answered_q = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.fresh_q = Questionnaire.objects.create(questionnaire_name="新問卷", code="new")
        cls.answered = Question.objects.create(
            questionnaire=cls.answered_q,
            question_text="原本的題目",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        cls.fresh = Question.objects.create(
            questionnaire=cls.fresh_q,
            question_text="原本的題目",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        submission = Submission.objects.create(user=cls.user, questionnaire=cls.answered_q)
        Answer.objects.create(submission=submission, question=cls.answered, score=4)

    def setUp(self):
        self.client.force_login(self.admin)

    def _post_question(self, question):
        url = reverse("admin:screening_question_change", args=[question.pk])
        return self.client.post(
            url,
            {
                "questionnaire": self.fresh_q.pk,
                "question_text": "改過的題目",
                "question_number": 2,
                "category": Category.SOCIAL,
            },
        )

    def _post_questionnaire(self, questionnaire):
        url = reverse("admin:screening_questionnaire_change", args=[questionnaire.pk])
        return self.client.post(
            url, {"questionnaire_name": f"{questionnaire.questionnaire_name}改", "code": "changed"}
        )

    def test_answered_question_is_read_only(self):
        response = self._post_question(self.answered)
        self.assertRedirects(response, reverse("admin:screening_question_changelist"))
        question = Question.objects.get(pk=self.answered.pk)
        self.assertEqual(question.question_text, "原本的題目")
        self.assertEqual(question.category, Category.EMOTIONAL)
        self.assertEqual(question.question_number, 1)
        self.assertEqual(question.questionnaire_id, self.answered_q.pk)

    def test_unanswered_question_is_editable(self):
        self._post_question(self.fresh)
        question = Question.objects.get(pk=self.fresh.pk)
        self.assertEqual(question.question_text, "改過的題目")
        self.assertEqual(question.category, Category.SOCIAL)

    def test_questionnaire_code_locked_after_submissions(self):
        self._post_questionnaire(self.answered_q)
        questionnaire = Questionnaire.objects.get(pk=self.answered_q.pk)
        self.assertEqual(questionnaire.code, "hhie-s")
        self.assertEqual(questionnaire.questionnaire_name, "HHIE-S改")

    def test_questionnaire_code_editable_without_submissions(self):
        self._post_questionnaire(self.fresh_q)
        questionnaire = Questionnaire.objects.get(pk=self.fresh_q.pk)
        self.assertEqual(questionnaire.code, "changed")

    def test_submission_and_answer_are_view_only(self):
        submission = Submission.objects.get(questionnaire=self.answered_q)
        answer = Answer.objects.get(submission=submission)
        submission_url = reverse("admin:screening_submission_change", args=[submission.pk])
        answer_url = reverse("admin:screening_answer_change", args=[answer.pk])

        self.assertEqual(self.client.get(submission_url).status_code, 200)
        self.assertEqual(self.client.get(answer_url).status_code, 200)

        response = self.client.post(
            submission_url, {"user": self.user.pk, "questionnaire": self.fresh_q.pk}
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            answer_url, {"submission": submission.pk, "question": self.answered.pk, "score": 0}
        )
        self.assertEqual(response.status_code, 403)
        delete_url = reverse("admin:screening_answer_delete", args=[answer.pk])
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 403)

        self.assertEqual(
            Submission.objects.get(pk=submission.pk).questionnaire_id, self.answered_q.pk
        )
        self.assertEqual(Answer.objects.get(pk=answer.pk).score, 4)


class SubscaleNoteTests(TestCase):
    NOTE = "情緒與社交分項僅供參考，目前沒有正式的解讀標準，請以總分分級為主。"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="user")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")

    def _make_submission(self, questionnaire):
        question = Question.objects.create(
            questionnaire=questionnaire,
            question_text="第一題",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        submission = Submission.objects.create(user=self.user, questionnaire=questionnaire)
        Answer.objects.create(submission=submission, question=question, score=4)
        return submission

    def setUp(self):
        self.client.force_login(self.user)

    def test_result_page_shows_note_below_subscales(self):
        submission = self._make_submission(self.hhie_s)
        response = self.client.get(reverse("result", args=[submission.id]))
        content = response.content.decode()
        self.assertIn(self.NOTE, content)
        self.assertLess(content.index("建議"), content.index("社交分數"))
        self.assertLess(content.index("社交分數"), content.index(self.NOTE))

    def test_note_shown_when_unclassifiable(self):
        submission = self._make_submission(self.hhia_s)
        with self.assertLogs("screening.scoring", "ERROR"):
            response = self.client.get(reverse("result", args=[submission.id]))
        self.assertContains(response, "無法判讀")
        self.assertContains(response, self.NOTE)

    def test_history_page_has_no_note(self):
        self._make_submission(self.hhie_s)
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, "總分")
        self.assertNotContains(response, self.NOTE)

    def test_note_uses_readable_rem_size(self):
        submission = self._make_submission(self.hhie_s)
        response = self.client.get(reverse("result", args=[submission.id]))
        self.assertContains(response, f'<p class="text-body-emphasis">{self.NOTE}</p>', html=True)


class HearingAidTests(TestCase):
    PROMPT = "這次填答時，您有沒有戴助聽器？"
    ERROR = "請選擇這次有沒有戴助聽器"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="user")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.question = Question.objects.create(
            questionnaire=cls.questionnaire,
            question_text="第一題",
            question_number=1,
            category=Category.EMOTIONAL,
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.questionnaire.id])

    def _post(self, **extra):
        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-0-score": "4",
            "form-0-question_id": str(self.question.id),
            **extra,
        }
        return self.client.post(self.url, data)

    def _make_submission(self, wearing):
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.create(submission=submission, question=self.question, score=4)
        return submission

    def test_failure_midway_leaves_nothing(self):
        # The web form and the API share formset.save(); this guards its all-or-nothing.
        with (
            mock.patch.object(Answer.objects, "bulk_create", side_effect=DatabaseError),
            self.assertRaises(DatabaseError),
        ):
            self._post(wearing_hearing_aid="False")
        self.assertFalse(Submission.objects.exists())

    def test_question_shown_before_first_question_without_default(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertLess(content.index(self.PROMPT), content.index("第一題"))
        self.assertContains(response, 'name="wearing_hearing_aid" value="True"')
        self.assertContains(response, 'name="wearing_hearing_aid" value="False"')
        self.assertContains(response, "有戴")
        self.assertContains(response, "沒戴")
        self.assertNotContains(response, "checked")

    def test_wearing_saved_and_shown_on_result(self):
        response = self._post(wearing_hearing_aid="True")
        submission = Submission.objects.get(user=self.user)
        self.assertIs(submission.wearing_hearing_aid, True)
        response = self.client.get(response.url)
        self.assertContains(response, "助聽器：有戴")

    def test_not_wearing_saved_and_shown_on_result(self):
        response = self._post(wearing_hearing_aid="False")
        submission = Submission.objects.get(user=self.user)
        self.assertIs(submission.wearing_hearing_aid, False)
        response = self.client.get(response.url)
        self.assertContains(response, "助聽器：沒戴")

    def test_missing_answer_rejected_and_answers_kept(self):
        response = self._post()
        self.assertFalse(Submission.objects.exists())
        self.assertContains(response, self.ERROR)
        self.assertContains(
            response,
            '<input type="radio" name="form-0-score" value="4" class="choice-group"'
            ' id="id_form-0-score_0" checked>',
            html=True,
        )

    def test_hearing_aid_choice_kept_when_answer_missing(self):
        response = self._post(**{"form-0-score": "", "wearing_hearing_aid": "False"})
        self.assertFalse(Submission.objects.exists())
        self.assertContains(
            response,
            '<input type="radio" name="wearing_hearing_aid" value="False" class="choice-group"'
            ' required id="id_wearing_hearing_aid_1" checked>',
            html=True,
        )

    def test_tampered_value_rejected(self):
        response = self._post(wearing_hearing_aid="maybe")
        self.assertFalse(Submission.objects.exists())
        self.assertContains(response, self.ERROR)

    def test_unrecorded_submission_shows_unrecorded(self):
        submission = self._make_submission(None)
        response = self.client.get(reverse("result", args=[submission.id]))
        self.assertContains(response, "助聽器：未記錄")
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, "助聽器：未記錄")

    def test_history_shows_each_status(self):
        for wearing in (True, False, None):
            self._make_submission(wearing)
        response = self.client.get(reverse("my_hearing"))
        for label in ("助聽器：有戴", "助聽器：沒戴", "助聽器：未記錄"):
            self.assertContains(response, label, count=1)

    def test_status_does_not_change_score(self):
        wearing = self._make_submission(True)
        not_wearing = self._make_submission(False)
        self.assertEqual(wearing.total_answer_score, not_wearing.total_answer_score)
        self.assertEqual(wearing.classified, not_wearing.classified)

    def test_new_text_uses_readable_style(self):
        submission = self._make_submission(True)
        response = self.client.get(reverse("result", args=[submission.id]))
        self.assertContains(
            response, '<p class="text-body-emphasis mb-1">助聽器：有戴</p>', html=True
        )


class LoginNextTests(TestCase):
    NOTE = "請先登入，沒有帳號請按註冊。登入後會帶您回到剛剛的頁面。"
    HINT = "第一次使用請先註冊，已有帳號請直接登入。"
    PASSWORD = "Xk9#mPq2vLw"
    EXTERNAL = (
        "https://evil.example.com",
        "//evil.example.com",
        "/\\evil.example.com",
        "javascript:alert(1)",
    )

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tester", password=cls.PASSWORD)

    def setUp(self):
        self.target = reverse("questionnaire_list")
        self.login_url = f"{reverse('login')}?next={self.target}"
        self.register_url = f"{reverse('register')}?next={self.target}"

    def _login(self, next_url=None, password=None):
        data = {"username": "tester", "password": password or self.PASSWORD}
        if next_url is not None:
            data["next"] = next_url
        return self.client.post(reverse("login"), data)

    def _register(self, next_url=None, username="newcomer", confirmation=None):
        data = {
            "username": username,
            "email": f"{username}@example.com",
            "password1": self.PASSWORD,
            "password2": confirmation or self.PASSWORD,
        }
        if next_url is not None:
            data["next"] = next_url
        return self.client.post(reverse("register"), data)

    def _assert_next_kept(self, response):
        self.assertContains(
            response, f'<input type="hidden" name="next" value="{self.target}">', html=True
        )

    def test_cta_leads_to_login_with_note(self):
        self.assertContains(self.client.get(reverse("index")), f'href="{self.target}"')
        response = self.client.get(self.target, follow=True)
        self.assertRedirects(response, self.login_url)
        self.assertContains(response, self.NOTE)

    def test_plain_login_page_has_no_note(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, self.NOTE)

    def test_login_redirects_to_next(self):
        self.assertRedirects(self._login(self.target), self.target)

    def test_login_without_next_goes_home(self):
        self.assertRedirects(self._login(), reverse("index"))

    def test_next_kept_after_wrong_password(self):
        response = self._login(self.target, password="wrong-password")
        self.assertContains(response, "使用者名稱或密碼錯誤")
        self.assertContains(response, self.NOTE)
        self._assert_next_kept(response)
        self.assertRedirects(self._login(self.target), self.target)

    def test_external_next_is_ignored_on_login(self):
        for bad in self.EXTERNAL:
            with self.subTest(next=bad):
                self.client.logout()
                response = self.client.get(f"{reverse('login')}?next={bad}")
                self.assertNotContains(response, self.NOTE)
                self.assertRedirects(self._login(bad), reverse("index"))

    def test_register_link_carries_next_and_register_redirects(self):
        response = self.client.get(self.login_url)
        self.assertContains(response, f'href="{self.register_url}"')
        self.assertRedirects(self._register(self.target), self.target)

    def test_next_kept_after_register_error(self):
        response = self._register(self.target, confirmation="Different#123")
        self.assertContains(response, "輸入的兩個密碼不一致。")
        self._assert_next_kept(response)
        self.assertRedirects(self._register(self.target), self.target)

    def test_login_link_on_register_page_carries_next(self):
        response = self.client.get(self.register_url)
        self._assert_next_kept(response)
        self.assertContains(response, f'href="{self.login_url}"')
        self.assertContains(self.client.get(self.login_url), self.NOTE)

    def test_external_next_is_ignored_on_register(self):
        for i, bad in enumerate(self.EXTERNAL):
            with self.subTest(next=bad):
                self.client.logout()
                response = self._register(bad, username=f"newcomer{i}")
                self.assertRedirects(response, reverse("index"))

    def test_next_is_escaped_in_html(self):
        response = self.client.get(reverse("login"), {"next": '/x"><script>alert(1)</script>'})
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_home_hint_only_for_anonymous(self):
        self.assertContains(self.client.get(reverse("index")), self.HINT)
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse("index")), self.HINT)

    def test_new_text_uses_readable_style(self):
        self.assertContains(
            self.client.get(self.login_url),
            f'<p class="text-body-emphasis">{self.NOTE}</p>',
            html=True,
        )
        self.assertContains(
            self.client.get(reverse("index")),
            f'<p class="text-body-emphasis mt-2">{self.HINT}</p>',
            html=True,
        )


class CopyTests(TestCase):
    LONG_QUESTION = "這是一題為了測試截斷而刻意寫得很長的題目，超過三十個字之後也必須完整顯示嗎？"
    INTRO = (
        "本問卷的目的在幫助您了解自己的聽力是否對於日常生活造成了影響。"
        "已選配助聽器一段時間後，可以再填一次，有助於了解所配的助聽器是否真的有幫助。"
        "請在閱讀每項問題後圈選常常、有時或從未。"
    )
    ADVICE: ClassVar[dict[str, str]] = {
        "mild_to_moderate": (
            "聽力的問題已經慢慢開始影響到您的社交活動以及情緒，例如"
            "與家人之間常常因為聽不清楚或是電視聲音等而產生爭吵、在多人且吵雜的"
            "社交環境當中會因為聽不清楚而導致社交上的窘迫及退縮，許多聽力衰退"
            "帶來的問題是微妙且和緩的，但經過此次篩檢能夠讓您體認到聽力對自身生"
            "活的影響，建議前往醫院耳鼻喉科進行聽力相關檢查及詢問相關專業意見。"
        ),
        "severe": (
            "聽力問題已經嚴重影響到您的生活了，許多人常常會忽視這一塊，聽不到這件事"
            "情往往已經十分嚴重了才會發現，若您尚未採取任何行動建議立即前往醫院耳鼻"
            "喉科尋求專業建議，並且考慮配戴助聽器。聽力喪失影響的並不只是聽不聽得到，"
            "無形中也會增加社交活動的壓力（例如因為聽不清楚常會在聊天的過程中退縮、"
            "裝作聽得懂等），這些壓力以及情緒的低落會增加長者的認知負擔。"
        ),
    }

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tester")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.question = Question.objects.create(
            questionnaire=cls.questionnaire,
            question_text=cls.LONG_QUESTION,
            question_number=1,
            category=Category.EMOTIONAL,
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.questionnaire.id])

    def test_question_text_is_not_truncated(self):
        self.assertGreater(len(self.LONG_QUESTION), 30)
        self.assertContains(
            self.client.get(self.url), f"第 1 題／共 1 題</span>{self.LONG_QUESTION}"
        )

    def test_question_text_full_after_validation_error(self):
        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-0-score": "4",
            "form-0-question_id": str(self.question.id),
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"第 1 題／共 1 題</span>{self.LONG_QUESTION}")

    def test_intro_typo_fixed(self):
        response = self.client.get(self.url)
        self.assertContains(response, self.INTRO)
        self.assertNotContains(response, "以選配了助聽器格")

    def test_advice_text(self):
        for level in ("normal", "mild_to_moderate", "severe", "unknown"):
            with self.subTest(level=level):
                advice = get_advice(level)
                for banned in ("ex.", "(", ")", "你"):
                    self.assertNotIn(banned, advice)
                if level in self.ADVICE:
                    self.assertEqual(advice, self.ADVICE[level])

    def test_login_title_in_chinese(self):
        self.client.logout()
        response = self.client.get(reverse("login"))
        self.assertContains(response, '<h1 class="h3 mb-3 fw-normal">登入</h1>', html=True)
        self.assertNotContains(response, "Welcome")

    def test_sign_in_status_in_chinese(self):
        response = self.client.get(reverse("index"))
        self.assertContains(response, "目前登入：<strong>tester</strong>")
        self.assertNotContains(response, "Signed in")
        self.client.logout()
        response = self.client.get(reverse("index"))
        # Logged out: the header shows nothing (spec phase4_ui_redesign 4.2), still no English.
        for english in ("Signed in", "Not signed in"):
            self.assertNotContains(response, english)

    def test_history_button_label(self):
        submission = Submission.objects.create(user=self.user, questionnaire=self.questionnaire)
        result_url = reverse("result", args=[submission.id])
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(
            response,
            f'<a class="btn btn-primary align-self-md-center" href="{result_url}">查看結果</a>',
            html=True,
        )
        self.assertNotContains(response, "連結")

    def test_empty_history_uses_polite_you(self):
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, "您還沒有做過篩檢紀錄")
        self.assertNotContains(response, "你還沒有")

    def test_questionnaire_list_has_no_orphan_li(self):
        content = self.client.get(reverse("questionnaire_list")).content.decode()
        # <li followed by space or >, so <link> in <head> is not counted.
        self.assertEqual(len(re.findall(r"<li[\s>]", content)), content.count("</li>"))


class RegisterFormTests(TestCase):
    PASSWORD = "Xk9#mPq2vLw"
    NOTE = "選填。用來推薦適合您年齡的問卷，不會公開。"

    def setUp(self):
        self.url = reverse("register")
        self.max_roc = date.today().year - 18 - 1911
        self.range_error = f"請輸入民國 1 到 {self.max_roc} 年之間的數字"

    def _post(self, **overrides):
        data = {
            "username": "newcomer",
            "email": "newcomer@example.com",
            "password1": self.PASSWORD,
            "password2": self.PASSWORD,
            "roc_birth_year": "",
            **overrides,
        }
        return self.client.post(self.url, data)

    def test_register_page_fields(self):
        response = self.client.get(self.url)
        for name in ("username", "email", "password1", "password2", "roc_birth_year"):
            self.assertContains(response, f'name="{name}"')
        self.assertContains(response, "民國")
        self.assertContains(response, self.NOTE)
        self.assertContains(response, "<li>你的密碼必須包含至少 8 個字元。</li>", html=True)

    def test_register_without_birth_year(self):
        response = self._post()
        self.assertRedirects(response, reverse("index"))
        user = User.objects.get(username="newcomer")
        self.assertIsNone(user.birth_year)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_roc_year_is_stored_as_western_year(self):
        self._post(roc_birth_year="44")
        self.assertEqual(User.objects.get(username="newcomer").birth_year, 1955)

    def test_roc_year_boundaries_accepted(self):
        for i, roc in enumerate((1, self.max_roc)):
            with self.subTest(roc=roc):
                self.client.logout()
                self._post(
                    username=f"edge{i}", email=f"edge{i}@example.com", roc_birth_year=str(roc)
                )
                self.assertEqual(User.objects.get(username=f"edge{i}").birth_year, roc + 1911)

    def test_invalid_roc_year_rejected(self):
        for value in ("0", str(self.max_roc + 1), "abc", "1955", "²"):
            with self.subTest(value=value):
                response = self._post(roc_birth_year=value)
                self.assertFalse(User.objects.exists())
                self.assertIn(self.range_error, response.context["form"].errors["roc_birth_year"])
                self.assertContains(response, self.range_error)

    def test_password_mismatch_keeps_input(self):
        response = self._post(password2="Different#123", roc_birth_year="44")
        self.assertFalse(User.objects.exists())
        self.assertIn("輸入的兩個密碼不一致。", response.context["form"].errors["password2"])
        self.assertContains(response, 'value="newcomer"')
        self.assertContains(response, 'value="newcomer@example.com"')
        self.assertContains(response, 'value="44"')
        self.assertNotContains(response, self.PASSWORD)
        self.assertContains(response, "你的密碼必須包含至少 8 個字元。")

    def test_duplicate_username_rejected(self):
        User.objects.create_user(username="newcomer")
        response = self._post()
        self.assertEqual(User.objects.count(), 1)
        for error in response.context["form"].errors["username"]:
            self.assertContains(response, error)

    def test_required_fields(self):
        for field in ("username", "email", "password1"):
            with self.subTest(field=field):
                response = self._post(**{field: ""})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(User.objects.exists())
                self.assertIn("這個欄位是必須的。", response.context["form"].errors[field])

    def test_password_similar_to_username_rejected(self):
        response = self._post(
            username="hearwellsenior", password1="hearwellsenior1", password2="hearwellsenior1"
        )
        self.assertFalse(User.objects.exists())
        errors = response.context["form"].errors["password2"]
        self.assertTrue(any("使用者名稱太相近" in error for error in errors), errors)

    def test_age_from_birth_year(self):
        self.assertEqual(User(birth_year=1955).age, date.today().year - 1955)
        self.assertIsNone(User().age)

    def test_note_uses_readable_style(self):
        self.assertContains(
            self.client.get(self.url),
            f'<div id="id_roc_birth_year_helptext" class="text-body-emphasis mt-1">'
            f"{self.NOTE}</div>",
            html=True,
        )

    def test_password_rules_use_rem_size(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, "form-text")
        self.assertContains(response, 'id="id_password1_helptext" class="text-body-emphasis mt-1"')

    def test_aria_describedby_targets_exist(self):
        response = self._post(username="", password2="Different#123", roc_birth_year="abc")
        content = response.content.decode()
        targets = re.findall(r'aria-describedby="([^"]+)"', content)
        self.assertTrue(targets)
        for ids in targets:
            for target in ids.split():
                with self.subTest(target=target):
                    self.assertIn(f'id="{target}"', content)


class BirthYearMigrationTests(TransactionTestCase):
    before = (("screening", "0014_submission_wearing_hearing_aid"),)
    after = (("screening", "0016_remove_user_birth_date"),)

    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(list(targets))
        return executor.loader.project_state(list(targets)).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_birth_date_year_is_kept(self):
        old_user = self._migrate(self.before).get_model("screening", "User")
        old_user.objects.create(username="with_date", birth_date=date(1955, 6, 1))
        old_user.objects.create(username="without_date")
        new_user = self._migrate(self.after).get_model("screening", "User")
        self.assertEqual(new_user.objects.get(username="with_date").birth_year, 1955)
        self.assertIsNone(new_user.objects.get(username="without_date").birth_year)


class AccessibilityTests(TestCase):
    PROMPT = "這次填答時，您有沒有戴助聽器？"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tester")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        for number, category in ((1, Category.EMOTIONAL), (2, Category.SOCIAL)):
            Question.objects.create(
                questionnaire=cls.questionnaire,
                question_text=f"第{number}題",
                question_number=number,
                category=category,
            )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.questionnaire.id])

    def _css(self):
        with open(finders.find("screening/styles.css"), encoding="utf-8") as f:
            return re.sub(r"/\*.*?\*/", "", f.read(), flags=re.DOTALL)

    def _rule(self, selector):
        # Exactly one rule for the selector, so a later rule cannot silently override it.
        bodies = [
            body
            for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", self._css())
            if selectors.strip() == selector
        ]
        self.assertEqual(len(bodies), 1, selector)
        return bodies[0].lower()

    def test_stylesheet_loads_after_bootstrap(self):
        content = self.client.get(reverse("index")).content.decode()
        self.assertLess(content.index("bootstrap.min.css"), content.index("screening/styles"))

    def test_body_and_muted_text_color(self):
        root = self._rule(":root")
        self.assertIn("--bs-body-color: #495057", root)
        self.assertIn("--bs-body-color-rgb: 73, 80, 87", root)
        self.assertIn("--bs-secondary-color: #495057", root)

    def test_level_and_error_text_colors(self):
        expected = {
            ".text-success": "#1e7b55",
            ".text-warning": "#8a5a00",
            ".text-danger": "#c23b1c",
            ".text-secondary": "#495057",
        }
        for selector, color in expected.items():
            with self.subTest(selector=selector):
                self.assertIn(f"color: {color} !important", self._rule(selector))

    def test_each_question_in_fieldset_with_legend(self):
        content = self.client.get(self.url).content.decode()
        self.assertEqual(content.count("<fieldset"), 3)
        legends = (
            self.PROMPT,
            '<span class="question-progress">第 1 題／共 2 題</span>第1題',
            '<span class="question-progress">第 2 題／共 2 題</span>第2題',
        )
        for legend in legends:
            with self.subTest(legend=legend):
                self.assertRegex(content, rf"<legend[^>]*>\s*{re.escape(legend)}\s*</legend>")

    def test_hearing_aid_error_linked_to_group(self):
        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-0-score": "4",
            "form-0-question_id": str(Question.objects.get(question_number=1).id),
        }
        content = self.client.post(self.url, data).content.decode()
        self.assertRegex(content, r'<fieldset[^>]*aria-describedby="id_wearing_hearing_aid_error"')
        self.assertRegex(
            content, r'id="id_wearing_hearing_aid_error">\s*<p[^>]*>請選擇這次有沒有戴助聽器'
        )

    def test_choices_are_large_horizontal_buttons(self):
        response = self.client.get(self.url)
        self.assertContains(response, '<div id="id_wearing_hearing_aid" class="choice-group">')
        self.assertContains(response, '<div id="id_form-0-score" class="choice-group">')
        self.assertIn("min-height: 3rem", self._rule("div.choice-group label"))
        # The input sits inside its label, so the whole button is clickable.
        self.assertRegex(response.content.decode(), r'<label for="id_form-0-score_0">\s*<input')
        self.assertIn("display: flex", self._rule("div.choice-group"))


class ApiFoundationTests(TestCase):
    QUESTIONNAIRES = "/api/questionnaires/"
    SCHEMA = "/api/schema/"
    SCHEMA_FILE = Path(__file__).resolve().parent.parent / "docs" / "api" / "schema.yaml"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tester")

    def test_anonymous_gets_403_json(self):
        response = self.client.get(self.QUESTIONNAIRES)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("detail", response.json())

    def test_anonymous_cannot_read_schema(self):
        # The schema view renders errors in its own OpenAPI format (YAML), not JSON.
        response = self.client.get(self.SCHEMA)
        self.assertEqual(response.status_code, 403)
        content = response.content.decode()
        self.assertIn("detail", content)
        self.assertNotIn("openapi", content)
        self.assertNotIn("/api/questionnaires/", content)

    def test_questionnaire_list_is_read_only(self):
        self.client.force_login(self.user)
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.QUESTIONNAIRES)
                self.assertEqual(response.status_code, 405)

    def test_questionnaire_list(self):
        # Lower id sorts last by code and name, so only ordering by id passes.
        first = Questionnaire.objects.create(questionnaire_name="ZZ 問卷", code="zz")
        second = Questionnaire.objects.create(questionnaire_name="AA 問卷", code="aa")
        self.client.force_login(self.user)
        response = self.client.get(self.QUESTIONNAIRES)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {"id": first.id, "code": "zz", "name": "ZZ 問卷", "levels": []},
                {"id": second.id, "code": "aa", "name": "AA 問卷", "levels": []},
            ],
        )

    def test_questionnaire_list_empty(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.QUESTIONNAIRES).json(), [])

    def test_schema_lists_endpoints(self):
        self.client.force_login(self.user)
        response = self.client.get(self.SCHEMA)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertTrue(content.startswith("openapi:"))
        self.assertIn(self.QUESTIONNAIRES, content)

    def test_schema_is_yaml_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.SCHEMA, {"format": "json"}).status_code, 404)
        self.assertEqual(
            self.client.get(self.SCHEMA, HTTP_ACCEPT="application/json").status_code, 406
        )

    def test_committed_schema_is_up_to_date(self):
        out = StringIO()
        call_command("spectacular", stdout=out)
        self.assertEqual(
            out.getvalue(),
            self.SCHEMA_FILE.read_text(encoding="utf-8"),
            "API changed: run `python manage.py spectacular --file docs/api/schema.yaml`",
        )


class ApiSubmissionTests(TestCase):
    LIST = "/api/submissions/"
    ITEM_FIELDS: ClassVar[set[str]] = {
        "id",
        "created_at",
        "questionnaire",
        "wearing_hearing_aid",
        "scores",
        "level",
    }

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="alice_account", email="alice@example.com", birth_year=1950
        )
        cls.other = User.objects.create_user(username="bob_account")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _make_submission(self, user=None, scores=(0,) * 10, questionnaire=None, wearing=None):
        submission = Submission.objects.create(
            user=user or self.user,
            questionnaire=questionnaire or self.questionnaire,
            wearing_hearing_aid=wearing,
        )
        # Reversed so answers are stored out of question order.
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in reversed(list(zip(self.questions, scores, strict=False)))
        )
        return submission

    def _detail_url(self, submission_id):
        return f"{self.LIST}{submission_id}/"

    def test_anonymous_gets_403(self):
        submission = self._make_submission()
        self.client.logout()
        for url in (self.LIST, self._detail_url(submission.id)):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_endpoints_are_read_only(self):
        submission = self._make_submission()
        for url in (self.LIST, self._detail_url(submission.id)):
            # POST on the list is the submit endpoint (ApiSubmitTests).
            methods = (
                ("put", "patch", "delete")
                if url == self.LIST
                else ("post", "put", "patch", "delete")
            )
            for method in methods:
                with self.subTest(url=url, method=method):
                    self.assertEqual(getattr(self.client, method)(url).status_code, 405)

    def test_list_only_own_newest_first_with_exact_fields(self):
        older = self._make_submission()
        newer = self._make_submission()
        self._make_submission(user=self.other)
        results = self.client.get(self.LIST).json()["results"]
        self.assertEqual([item["id"] for item in results], [newer.id, older.id])
        for item in results:
            self.assertEqual(set(item), self.ITEM_FIELDS)
            self.assertEqual(item["questionnaire"], {"code": "hhie-s", "name": "HHIE-S"})
            self.assertEqual(set(item["scores"]), {"total", "emotional", "social"})
            self.assertEqual(set(item["level"]), {"code", "text"})

    def test_scores_match_result_page(self):
        # emotional 5 x 4 = 20, social 3 x 2 = 6 -> total 26 (severe)
        submission = self._make_submission(scores=[4, 4, 4, 4, 4, 2, 2, 2, 0, 0])
        page = self.client.get(reverse("result", args=[submission.id])).context
        for url in (self.LIST, self._detail_url(submission.id)):
            with self.subTest(url=url):
                data = self.client.get(url).json()
                item = data["results"][0] if "results" in data else data
                self.assertEqual(
                    item["scores"],
                    {
                        "total": page["total_score"],
                        "emotional": page["emotional"],
                        "social": page["social"],
                    },
                )
                self.assertEqual(item["scores"], {"total": 26, "emotional": 20, "social": 6})
                self.assertEqual(
                    item["level"], {"code": "severe", "text": page["classified_score_text"]}
                )

    def test_wearing_hearing_aid_values(self):
        expected = {}
        for wearing in (True, False, None):
            expected[self._make_submission(wearing=wearing).id] = wearing
        results = self.client.get(self.LIST).json()["results"]
        self.assertEqual({item["id"]: item["wearing_hearing_aid"] for item in results}, expected)

    def test_all_never_scores_zero_not_null(self):
        self._make_submission(scores=[0] * 10)
        item = self.client.get(self.LIST).json()["results"][0]
        self.assertEqual(item["scores"], {"total": 0, "emotional": 0, "social": 0})
        self.assertEqual(item["level"]["code"], "normal")

    def test_unknown_level_still_returns_scores(self):
        no_thresholds = Questionnaire.objects.create(
            questionnaire_name="測試問卷", code="no-thresholds"
        )
        submission = self._make_submission(questionnaire=no_thresholds, scores=[4] * 10)
        for url in (self.LIST, self._detail_url(submission.id)):
            with self.subTest(url=url), self.assertLogs("screening.scoring", "ERROR"):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                data = response.json()
                item = data["results"][0] if "results" in data else data
                self.assertEqual(item["level"], {"code": "unknown", "text": "無法判讀"})
                self.assertEqual(item["scores"]["total"], 40)

    def test_cursor_pagination_has_no_gaps_or_duplicates(self):
        created = {self._make_submission().id for _ in range(21)}
        first = self.client.get(self.LIST).json()
        self.assertEqual(len(first["results"]), 20)
        self.assertIsNotNone(first["next"])
        second = self.client.get(first["next"]).json()
        self.assertEqual(len(second["results"]), 1)
        self.assertIsNone(second["next"])
        ids = [item["id"] for item in first["results"] + second["results"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), created)

    def test_pagination_with_identical_created_at(self):
        # Only the -id tie-breaker keeps equal timestamps from repeating or vanishing.
        created = {self._make_submission().id for _ in range(25)}
        Submission.objects.update(created_at=datetime(2026, 10, 14, 6, 30, tzinfo=ZoneInfo("UTC")))
        ids, url = [], self.LIST
        while url:
            page = self.client.get(url).json()
            ids += [item["id"] for item in page["results"]]
            url = page["next"]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), created)
        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_created_at_is_taipei_time(self):
        submission = self._make_submission()
        Submission.objects.filter(pk=submission.pk).update(
            created_at=datetime(2026, 10, 14, 6, 30, tzinfo=ZoneInfo("UTC"))
        )
        data = self.client.get(self._detail_url(submission.id)).json()
        self.assertEqual(data["created_at"], "2026-10-14T14:30:00+08:00")

    def test_empty_list(self):
        self.assertEqual(
            self.client.get(self.LIST).json(), {"next": None, "previous": None, "results": []}
        )

    def _count_list_queries(self, expected_rows):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.LIST)
        self.assertEqual(len(response.json()["results"]), expected_rows)
        return len(ctx.captured_queries)

    def test_list_query_count_does_not_grow(self):
        self._make_submission(scores=[4] * 10)
        one = self._count_list_queries(expected_rows=1)
        for _ in range(4):
            self._make_submission(scores=[2] * 10)
        five = self._count_list_queries(expected_rows=5)
        self.assertEqual(one, five)

    def test_detail_matches_result_page(self):
        submission = self._make_submission(scores=[4, 2, 0, 0, 0, 0, 0, 0, 0, 0], wearing=True)
        page = self.client.get(reverse("result", args=[submission.id])).context
        data = self.client.get(self._detail_url(submission.id)).json()
        self.assertEqual(set(data), self.ITEM_FIELDS | {"advice", "answers"})
        self.assertEqual(data["id"], submission.id)
        self.assertEqual(data["advice"], page["advice"])
        self.assertEqual([a["number"] for a in data["answers"]], list(range(1, 11)))
        self.assertEqual(
            data["answers"][0], {"number": 1, "text": "第1題", "score": 4, "label": "常常"}
        )
        self.assertEqual(data["answers"][1]["label"], "有時")
        self.assertEqual(data["answers"][2]["label"], "從未")

    def test_others_and_missing_submission_both_404_identically(self):
        others = self._make_submission(user=self.other)
        not_found = self.client.get(self._detail_url(others.id + 1000))
        forbidden = self.client.get(self._detail_url(others.id))
        self.assertEqual(forbidden.status_code, 404)
        self.assertEqual(not_found.status_code, 404)
        self.assertEqual(forbidden.content, not_found.content)

    def test_responses_have_no_personal_data(self):
        submission = self._make_submission()
        for url in (self.LIST, self._detail_url(submission.id)):
            content = self.client.get(url).content.decode()
            for secret in ("alice_account", "alice@example.com", "1950", "birth", "user"):
                with self.subTest(url=url, secret=secret):
                    self.assertNotIn(secret, content)

    def test_schema_lists_submission_endpoints(self):
        content = self.client.get("/api/schema/").content.decode()
        self.assertIn("/api/submissions/:", content)
        self.assertIn("/api/submissions/{id}/:", content)


class TrendChartPageTests(TestCase):
    CHART_JS = "screening/frontend/trend-chart.js"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tester")
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


class RedesignLayoutTests(TestCase):
    NAV = re.compile(r'<nav aria-label="主要導覽".*?</nav>', re.DOTALL)
    LOGGED_IN_ITEMS = ("首頁", "開始篩檢", "我的紀錄", "聽力圖")
    LOGGED_OUT_ITEMS = ("首頁", "登入", "註冊")

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alice_account", password="secret-pass-123")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.submission = Submission.objects.create(user=cls.user, questionnaire=cls.questionnaire)

    def _nav(self, response):
        self.assertEqual(response.status_code, 200)
        navs = self.NAV.findall(response.content.decode())
        self.assertEqual(len(navs), 1)
        return navs[0]

    def _nav_labels(self, nav):
        return re.findall(r"<span[^>]*>([^<]+)</span>\s*</a>", nav)

    def _logged_in_pages(self):
        return {
            reverse("index"): "首頁",
            reverse("questionnaire_list"): "開始篩檢",
            reverse("screening", args=[self.questionnaire.id]): "開始篩檢",
            reverse("result", args=[self.submission.id]): "我的紀錄",
            reverse("my_hearing"): "我的紀錄",
            reverse("audiogram_list"): "聽力圖",
            reverse("audiogram_new"): "聽力圖",
        }

    def test_logged_in_nav_and_header(self):
        self.client.force_login(self.user)
        for url in self._logged_in_pages():
            with self.subTest(url=url):
                response = self.client.get(url)
                nav = self._nav(response)
                self.assertEqual(self._nav_labels(nav), list(self.LOGGED_IN_ITEMS))
                content = response.content.decode()
                self.assertRegex(content, r"目前登入：\s*<strong>alice_account</strong>")
                self.assertRegex(
                    content,
                    rf'<form[^>]*action="{reverse("logout")}"[^>]*method="post"',
                )

    def test_logged_out_nav(self):
        for url in (reverse("index"), reverse("login"), reverse("register")):
            with self.subTest(url=url):
                response = self.client.get(url)
                nav = self._nav(response)
                self.assertEqual(self._nav_labels(nav), list(self.LOGGED_OUT_ITEMS))
                content = response.content.decode()
                self.assertNotIn("目前登入", content)
                self.assertNotIn(f'action="{reverse("logout")}"', content)

    def test_current_page_marked(self):
        self.client.force_login(self.user)
        for url, label in self._logged_in_pages().items():
            with self.subTest(url=url):
                nav = self._nav(self.client.get(url))
                self.assertEqual(nav.count('aria-current="page"'), 1)
                self.assertRegex(nav, rf'(?s)aria-current="page"[^>]*>.*?<span[^>]*>{label}</span>')
        self.client.logout()
        for name, label in (("login", "登入"), ("register", "註冊")):
            with self.subTest(url=name):
                nav = self._nav(self.client.get(reverse(name)))
                self.assertEqual(nav.count('aria-current="page"'), 1)
                self.assertRegex(nav, rf'(?s)aria-current="page"[^>]*>.*?<span[^>]*>{label}</span>')

    def test_index_shows_start_screening_when_logged_in(self):
        self.client.force_login(self.user)
        nav = self._nav(self.client.get(reverse("index")))
        self.assertIn(f'href="{reverse("questionnaire_list")}"', nav)

    def test_page_titles(self):
        suffix = "\uff5cHearWell"  # U+FF5C FULLWIDTH VERTICAL LINE, as written in the spec
        expected = {
            reverse("questionnaire_list"): "選擇問卷" + suffix,
            reverse("screening", args=[self.questionnaire.id]): "HHIE-S 作答" + suffix,
            reverse("result", args=[self.submission.id]): "篩檢結果" + suffix,
            reverse("my_hearing"): "我的紀錄" + suffix,
        }
        self.client.force_login(self.user)
        titles = {url: self._title(url) for url in expected}
        self.client.logout()
        expected.update(
            {
                reverse("index"): "HearWell 聽力自我照護",
                reverse("login"): "登入" + suffix,
                reverse("register"): "註冊" + suffix,
            }
        )
        for name in ("index", "login", "register"):
            titles[reverse(name)] = self._title(reverse(name))
        self.assertEqual(titles, expected)
        self.assertEqual(len(set(titles.values())), len(titles))

    def _title(self, url):
        match = re.search(r"<title>\s*(.*?)\s*</title>", self.client.get(url).content.decode())
        return match.group(1)

    def test_login_uses_plain_labels(self):
        content = self.client.get(reverse("login")).content.decode()
        self.assertNotIn("form-floating", content)
        self.assertRegex(content, r'<label[^>]*for="id_username"[^>]*>使用者名稱</label>')
        self.assertRegex(content, r'<label[^>]*for="id_password"[^>]*>密碼</label>')
        self.assertRegex(content, r'<input[^>]*id="id_username"')
        self.assertRegex(content, r'<input[^>]*id="id_password"')
        response = self.client.post(
            reverse("login"), {"username": "alice_account", "password": "wrong"}
        )
        self.assertContains(response, "使用者名稱或密碼錯誤")

    def _answer_data(self, skip=(), wearing="True"):
        data = {"form-TOTAL_FORMS": 10, "form-INITIAL_FORMS": 0}
        if wearing is not None:
            data["wearing_hearing_aid"] = wearing
        for i, question in enumerate(self.questions):
            data[f"form-{i}-question_id"] = str(question.id)
            if question.question_number not in skip:
                data[f"form-{i}-score"] = "4"
        return data

    def test_unanswered_questions_are_pointed_out(self):
        self.client.force_login(self.user)
        url = reverse("screening", args=[self.questionnaire.id])
        content = self.client.post(url, self._answer_data(skip=(3, 7))).content.decode()
        self.assertIn("還有 2 題沒有回答，請看標示紅字的題目。", content)
        self.assertEqual(content.count("這一題還沒有回答"), 2)
        for index in (2, 6):  # question 3 and 7
            with self.subTest(question=index + 1):
                self.assertRegex(
                    content, rf'<fieldset[^>]*aria-describedby="id_form-{index}-score_error"'
                )
                self.assertRegex(
                    content, rf'id="id_form-{index}-score_error">\s*<p[^>]*>這一題還沒有回答'
                )
        self.assertEqual(content.count('aria-describedby="id_form-'), 2)
        # Answers already chosen stay selected.
        self.assertRegex(content, r'<input[^>]*name="form-0-score"[^>]*value="4"[^>]*checked')
        self.assertNotIn("表單資料有誤", content)

    def test_invalid_choice_is_not_counted_as_unanswered(self):
        self.client.force_login(self.user)
        url = reverse("screening", args=[self.questionnaire.id])
        data = self._answer_data()
        data["form-0-score"] = "9"
        content = self.client.post(url, data).content.decode()
        self.assertNotIn("沒有回答", content)
        self.assertIn("表單資料有誤", content)

    def test_unanswered_count_matches_marked_questions(self):
        # Tampered form counts: extra forms are not on the page, so they must not be counted.
        self.client.force_login(self.user)
        url = reverse("screening", args=[self.questionnaire.id])
        data = self._answer_data()
        data["form-TOTAL_FORMS"] = data["form-INITIAL_FORMS"] = 12
        content = self.client.post(url, data).content.decode()
        self.assertNotIn("沒有回答", content)

    def test_logout_form_has_csrf_token(self):
        # The test client skips CSRF checks, so a missing token would only fail in production.
        self.client.force_login(self.user)
        content = self.client.get(reverse("index")).content.decode()
        form = re.search(rf'<form[^>]*action="{reverse("logout")}".*?</form>', content, re.DOTALL)
        self.assertIn('name="csrfmiddlewaretoken"', form.group(0))

    def test_only_hearing_aid_missing_behaves_as_before(self):
        self.client.force_login(self.user)
        url = reverse("screening", args=[self.questionnaire.id])
        content = self.client.post(url, self._answer_data(wearing=None)).content.decode()
        self.assertNotIn("沒有回答", content)
        self.assertRegex(content, r'<fieldset[^>]*aria-describedby="id_wearing_hearing_aid_error"')

    def test_only_expected_scripts(self):
        # No Bootstrap JS or anything else: only the bundles each page needs.
        def scripts(url):
            content = self.client.get(url).content.decode()
            return re.findall(r'<script[^>]*src="/static/([^"]+)"', content) + (
                ["<inline>"] if re.search(r"<script(?![^>]*src=)", content) else []
            )

        logout_js, answer_js = ReactAnswerPageTests.LOGOUT_JS, ReactAnswerPageTests.ANSWER_JS
        empty_user = User.objects.create_user(username="no_records")
        for url in (reverse("index"), reverse("login"), reverse("register")):
            with self.subTest(url=url):
                self.assertEqual(scripts(url), [])
        self.client.force_login(empty_user)
        with self.subTest(url="my_hearing without records"):
            self.assertEqual(scripts(reverse("my_hearing")), [logout_js])
        self.client.force_login(self.user)
        expected = {
            reverse("index"): [logout_js],
            reverse("questionnaire_list"): [logout_js],
            reverse("screening", args=[self.questionnaire.id]): [logout_js, answer_js],
            reverse("result", args=[self.submission.id]): [logout_js],
            reverse("my_hearing"): [logout_js, TrendChartPageTests.CHART_JS],
        }
        for url, bundles in expected.items():
            with self.subTest(url=url):
                self.assertEqual(scripts(url), bundles)


class TamperedAnswerTests(TestCase):
    ERROR = "表單資料有誤，請重新確認每一題的作答"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tester")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.questionnaire.id])

    def _data(self, skip=()):
        # Same management form the real page sends: every form is an initial form.
        data = {"form-TOTAL_FORMS": 10, "form-INITIAL_FORMS": 10, "wearing_hearing_aid": "True"}
        for i, question in enumerate(self.questions):
            data[f"form-{i}-question_id"] = str(question.id)
            if question.question_number not in skip:
                data[f"form-{i}-score"] = "4"
        return data

    def _assert_rejected(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ERROR)
        # No "還有 N 題" summary; a cleared form may still be marked under its question.
        self.assertNotContains(response, "題沒有回答")
        self.assertFalse(Submission.objects.exists())
        self.assertFalse(Answer.objects.exists())

    def test_extra_empty_forms_are_rejected(self):
        data = self._data()
        data["form-TOTAL_FORMS"] = 12
        self._assert_rejected(self.client.post(self.url, data))

    def test_cleared_new_form_is_rejected(self):
        data = self._data()
        data["form-INITIAL_FORMS"] = 0
        del data["form-4-question_id"], data["form-4-score"]
        self._assert_rejected(self.client.post(self.url, data))

    def test_fewer_forms_than_questions_still_rejected(self):
        data = self._data()
        data["form-TOTAL_FORMS"] = 9
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "有題目沒有作答")
        self.assertFalse(Submission.objects.exists())

    def test_question_from_another_questionnaire_rejected(self):
        other = Questionnaire.objects.create(questionnaire_name="其他問卷", code="other")
        foreign = Question.objects.create(
            questionnaire=other, question_text="別的題", question_number=1, category=Category.SOCIAL
        )
        data = self._data()
        data["form-9-question_id"] = str(foreign.id)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Submission.objects.exists())
        self.assertFalse(Answer.objects.exists())

    def test_normal_answers_still_saved(self):
        response = self.client.post(self.url, self._data())
        submission = Submission.objects.get()
        self.assertRedirects(response, reverse("result", args=[submission.id]))
        self.assertEqual(submission.answers.count(), 10)

    def test_unanswered_question_still_pointed_out(self):
        content = self.client.post(self.url, self._data(skip=(3,))).content.decode()
        self.assertIn("還有 1 題沒有回答，請看標示紅字的題目。", content)
        self.assertFalse(Submission.objects.exists())


class PageFlowTests(TestCase):
    """Spec docs/specs/phase4_ui_flow.md, acceptance 1-14a."""

    HINT = "第一次使用請先註冊，已有帳號請直接登入。"
    HOME_ORDER = (
        "了解聽力對您生活的影響",
        "回答幾個日常生活情境的問題，大約 3 分鐘。",
        "開始篩檢",
        "回答問題，大約 3 分鐘。",
        "馬上看到結果分級和建議。",
        "隔一段時間再做一次，在「我的紀錄」看分數的變化。",
        "可達 10 年",
        "從察覺聽力問題到尋求協助，往往拖延多年。及早了解，才能及早處理。",
        "本網站由執業聽力師開發，使用經過驗證的標準化量表。"
        "結果僅供參考，不能取代聽力檢查與醫師診斷。",
    )

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="flowtester")
        cls.other = User.objects.create_user(username="someoneelse")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhie_s,
                question_text=f"題目內容{i:02d}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.short = Questionnaire.objects.create(questionnaire_name="短問卷", code="short")
        Question.objects.bulk_create(
            Question(
                questionnaire=cls.short,
                question_text=f"短題{i}",
                question_number=i,
                category=Category.SOCIAL,
            )
            for i in range(1, 4)
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _main(self, response):
        # Only the page body; the header and nav repeat some words (e.g. 開始篩檢, the username).
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _assert_in_order(self, content, parts):
        positions = [content.index(part) for part in parts]
        self.assertEqual(positions, sorted(positions), parts)

    def _submit(self, scores, questionnaire=None, user=None):
        submission = Submission.objects.create(
            user=user or self.user, questionnaire=questionnaire or self.hhie_s
        )
        # Reversed so a missing order_by on the result page shows up.
        for question, score in reversed(list(zip(self.questions, scores, strict=False))):
            Answer.objects.create(submission=submission, question=question, score=score)
        return submission

    # Home (1-3)
    def test_home_order_for_anonymous(self):
        self.client.logout()
        main = self._main(self.client.get(reverse("index")))
        self._assert_in_order(main, self.HOME_ORDER)
        self._assert_in_order(main, ("開始篩檢", self.HINT, "回答問題，大約 3 分鐘。"))
        self.assertNotIn("7–10 年", main)
        self.assertRegex(main, rf'<a[^>]*href="{reverse("questionnaire_list")}"[^>]*>\s*開始篩檢')

    def test_home_order_for_logged_in_without_hint(self):
        main = self._main(self.client.get(reverse("index")))
        self._assert_in_order(main, self.HOME_ORDER)
        self.assertNotIn(self.HINT, main)

    def test_home_has_no_scale_names_or_missing_features(self):
        for logged_in in (True, False):
            if not logged_in:
                self.client.logout()
            content = self.client.get(reverse("index")).content.decode()
            for text in ("HHIE-S", "HHIA-S", "記錄日常聆聽困難", "以白話理解"):
                with self.subTest(logged_in=logged_in, text=text):
                    self.assertNotIn(text, content)

    # Questionnaire list (4-5)
    def test_questionnaire_list_shows_info(self):
        main = self._main(self.client.get(reverse("questionnaire_list")))
        self._assert_in_order(
            main,
            (
                "請選擇問卷",
                "HHIE-S 聽力障礙自我評估",
                "適合 65 歲以上的長輩。",
                "共 10 題，大約 3 分鐘。",
            ),
        )
        self.assertRegex(
            main, rf'<a[^>]*href="{reverse("screening", args=[self.hhie_s.id])}"[^>]*>\s*HHIE-S'
        )

    def test_question_count_is_not_hard_coded(self):
        main = self._main(self.client.get(reverse("questionnaire_list")))
        start = main.index("短問卷")
        card = main[start : main.index("</p>", start)]
        self.assertIn("共 3 題。", card)
        self.assertNotIn("適合", card)
        self.assertNotIn("分鐘", card)
        page = self._main(self.client.get(reverse("screening", args=[self.short.id])))
        self.assertIn("共 3 題。", page)
        self.assertNotIn("分鐘", page)
        self.assertRegex(page, r"<legend[^>]*>(\s*<[^>]+>)*\s*第 3 題／共 3 題")

    # Answer page (6-7)
    def _assert_progress(self, page):
        self.assertIn("共 10 題，大約 3 分鐘。", page)
        for n in (1, 10):
            with self.subTest(question=n):
                self.assertRegex(page, rf"<legend[^>]*>(\s*<[^>]+>)*\s*第 {n} 題／共 10 題")

    def test_answer_page_shows_progress(self):
        response = self.client.get(reverse("screening", args=[self.hhie_s.id]))
        self._assert_progress(self._main(response))

    def test_answer_page_does_not_count_questions_again(self):
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("screening", args=[self.hhie_s.id]))
        self.assertFalse([q for q in ctx.captured_queries if "COUNT(" in q["sql"]])

    def test_progress_kept_after_unanswered_post(self):
        data = {"form-TOTAL_FORMS": 10, "form-INITIAL_FORMS": 10, "wearing_hearing_aid": "True"}
        for i, question in enumerate(self.questions):
            data[f"form-{i}-question_id"] = str(question.id)
            if i != 2:
                data[f"form-{i}-score"] = "4"
        response = self.client.post(reverse("screening", args=[self.hhie_s.id]), data)
        page = self._main(response)
        self._assert_progress(page)
        self.assertIn("還有 1 題沒有回答，請看標示紅字的題目。", page)
        self.assertRegex(page, r'value="4"[^>]*checked')
        self.assertFalse(Submission.objects.exists())

    # Result page (8-13a)
    def _result(self, submission):
        return self._main(self.client.get(reverse("result", args=[submission.id])))

    def test_result_page_order(self):
        submission = self._submit([4, 4, 2, 2, 0, 0, 0, 0, 0, 0])  # 12
        day = timezone.localtime(submission.created_at).strftime("%Y/%m/%d")
        main = self._result(submission)
        self._assert_in_order(
            main,
            (
                f"{day} 作答",
                "輕度到中度影響",
                "總分 12 分（滿分 40）",
                "建議",
                get_advice("mild_to_moderate"),
                "看我的紀錄與趨勢",
                "回首頁",
                "分數細節",
                "情緒分數：12",
                "社交分數：0",
                "助聽器：未記錄",
                "<details",
                "查看我的 10 題作答",
            ),
        )

    def test_result_next_step_links(self):
        main = self._result(self._submit([0] * 10))
        self.assertRegex(main, rf'<a[^>]*href="{reverse("my_hearing")}"[^>]*>\s*看我的紀錄與趨勢')
        self.assertRegex(main, rf'<a[^>]*href="{reverse("index")}"[^>]*>\s*回首頁')

    def test_result_has_no_username_or_halfwidth_colon(self):
        main = self._result(self._submit([2] * 10))
        self.assertNotIn("flowtester", main)
        self.assertNotRegex(main, r"(總分|情緒分數|社交分數|助聽器|建議|結果)\s*:")

    def test_result_answers_collapsed_in_question_order(self):
        main = self._result(self._submit([4, 2, 0, 4, 2, 0, 4, 2, 0, 4]))
        details = re.search(r"<details(\s[^>]*)?>(.*?)</details>", main, re.DOTALL)
        self.assertIsNotNone(details)
        self.assertNotIn("open", details.group(1) or "")
        body = details.group(2)
        self.assertRegex(body, r"<summary[^>]*>\s*查看我的 10 題作答\s*</summary>")
        self._assert_in_order(body, [f"題目內容{i:02d}" for i in range(1, 11)])
        for i, answer in ((1, "常常"), (2, "有時"), (3, "從未"), (10, "常常")):
            with self.subTest(question=i):
                self.assertIn(f"題目內容{i:02d}——{answer}", body)

    def test_result_banner_colors(self):
        css = Path(finders.find("screening/styles.css")).read_text()
        hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")
        cases = (
            ("normal", [0] * 10, self.hhie_s, "#e3f4ec", "#1e7b55"),
            ("mild_to_moderate", [2] * 6 + [0] * 4, self.hhie_s, "#fff4d6", "#8a5a00"),
            ("severe", [4] * 10, self.hhie_s, "#feece7", "#c23b1c"),
            ("unknown", [2] * 10, hhia_s, None, "#495057"),
        )
        for level, scores, questionnaire, background, color in cases:
            with self.subTest(level=level):
                submission = self._submit(scores, questionnaire=questionnaire)
                if level == "unknown":
                    with self.assertLogs("screening.scoring", "ERROR"):
                        main = self._result(submission)
                else:
                    main = self._result(submission)
                self.assertRegex(main, rf'class="[^"]*\bresult-banner-{level}\b')
                rule = re.search(rf"\.result-banner-{level}\s*\{{([^}}]*)\}}", css)
                self.assertIsNotNone(rule)
                self.assertRegex(rule.group(1), rf"(?<!-)color:\s*{color}")
                if background:
                    self.assertRegex(rule.group(1), rf"background-color:\s*{background}")

    def test_result_zero_score(self):
        main = self._result(self._submit([0] * 10))
        self.assertIn("總分 0 分（滿分 40）", main)
        self.assertIn("無/極輕微影響", main)

    def test_result_without_thresholds_has_no_max(self):
        hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")
        submission = self._submit([2] * 10, questionnaire=hhia_s)
        with self.assertLogs("screening.scoring", "ERROR"):
            main = self._result(submission)
        self.assertIn("總分 20 分", main)
        self.assertNotIn("滿分", main)

    # IDOR (14) is covered by SubmissionResultAccessTests; one more for the redesigned page.
    def test_result_of_other_user_is_404(self):
        submission = self._submit([0] * 10, user=self.other)
        response = self.client.get(reverse("result", args=[submission.id]))
        self.assertEqual(response.status_code, 404)

    # History page (14a)
    def test_history_uses_fullwidth_colon(self):
        self._submit([2] * 10)
        content = self.client.get(reverse("my_hearing")).content.decode()
        self.assertIn("總分：20", content)
        self.assertNotIn("總分:", content)


class PwaTests(TestCase):
    """Spec docs/specs/phase4.md batch 2, acceptance 18-23."""

    PWA_DIR = Path(__file__).resolve().parent / "static" / "screening" / "pwa"
    STATIC = "/static/screening/pwa/"
    GUIDE_ORDER = (
        "把 HearWell 加到手機主畫面",
        "加到主畫面後，HearWell 會像其他 app 一樣出現在手機桌面上，"
        "點一下就能打開，不用每次輸入網址。",
        "iPhone（Safari）",
        "用 Safari 打開 HearWell 網站。",
        "點畫面下方的「分享」按鈕（一個方框，上面有向上的箭頭）。如果沒看到，先點「⋯」再點「分享」。",
        "往下滑，點「加入主畫面」。",
        "點右上角的「加入」。",
        "第一次從主畫面打開時，需要再登入一次。",
        "Android 手機（Chrome）",
        "用 Chrome 打開 HearWell 網站。",
        "點右上角的「⋮」（三個點）。",
        "點「加到主畫面」或「安裝應用程式」。",
        "再點一次「安裝」或「新增」。",
        "從主畫面打開時，請用畫面下方的「首頁、開始篩檢、我的紀錄」切換頁面。",
    )

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pwatester")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        question = Question.objects.create(
            questionnaire=cls.questionnaire,
            question_text="第一題",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        cls.submission = Submission.objects.create(user=cls.user, questionnaire=cls.questionnaire)
        Answer.objects.create(submission=cls.submission, question=question, score=2)

    def _head(self, response):
        content = response.content.decode()
        return content[content.index("<head>") : content.index("</head>")]

    def _png_size(self, path):
        data = path.read_bytes()[:24]
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", path)
        return struct.unpack(">II", data[16:24])

    def _manifest(self):
        return json.loads((self.PWA_DIR / "manifest.json").read_text(encoding="utf-8"))

    # 18
    def test_every_page_links_app_info(self):
        self.client.force_login(self.user)
        urls = [
            reverse("index"),
            reverse("questionnaire_list"),
            reverse("screening", args=[self.questionnaire.id]),
            reverse("result", args=[self.submission.id]),
            reverse("my_hearing"),
            reverse("add_to_home"),
        ]
        heads = {url: self._head(self.client.get(url)) for url in urls}
        self.client.logout()
        for name in ("login", "register"):
            heads[reverse(name)] = self._head(self.client.get(reverse(name)))
        for url, head in heads.items():
            with self.subTest(url=url):
                self.assertRegex(head, rf'<link rel="manifest" href="{self.STATIC}manifest\.json')
                self.assertIn('<meta name="theme-color" content="#1f4e8c">', head)
                self.assertRegex(
                    head, rf'<link rel="apple-touch-icon" href="{self.STATIC}apple-touch-icon\.png'
                )
                self.assertIn('<meta name="apple-mobile-web-app-title" content="HearWell">', head)

    # 19
    def test_manifest_fields(self):
        manifest = self._manifest()
        expected = {
            "name": "HearWell 聽力自我照護",
            "short_name": "HearWell",
            "id": "/",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "theme_color": "#1f4e8c",
            "background_color": "#ffffff",
            "lang": "zh-Hant",
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(manifest.get(key), value)

    def test_manifest_icons_exist_with_right_size(self):
        icons = {
            (icon["sizes"], icon.get("purpose", "any")): icon for icon in self._manifest()["icons"]
        }
        self.assertEqual(
            set(icons), {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")}
        )
        for (sizes, purpose), icon in icons.items():
            with self.subTest(sizes=sizes, purpose=purpose):
                self.assertEqual(icon["type"], "image/png")
                path = self.PWA_DIR / icon["src"]
                self.assertTrue(path.is_file(), path)
                width, height = self._png_size(path)
                self.assertEqual(f"{width}x{height}", sizes)

    # 20
    def test_apple_touch_icon_is_180(self):
        self.assertEqual(self._png_size(self.PWA_DIR / "apple-touch-icon.png"), (180, 180))

    # 21
    def test_pwa_folder_has_only_app_info_and_icons(self):
        # Allow-list: a service worker added here under any name fails this test.
        names = {path.name for path in self.PWA_DIR.iterdir()}
        expected = {
            "manifest.json",
            "icon.svg",
            "icon-192.png",
            "icon-512.png",
            "apple-touch-icon.png",
        }
        self.assertEqual(names, expected)
        self.assertNotIn("serviceworker", self._manifest())

    def test_no_service_worker_registration(self):
        root = Path(__file__).resolve().parent.parent
        app = root / "screening"
        sources = [
            *(app / "templates").rglob("*.html"),
            # This file names "serviceWorker" itself; migrations are generated.
            *(p for p in app.rglob("*.py") if "migrations" not in p.parts and p.name != "tests.py"),
            *(root / "config").rglob("*.py"),
            *(root / "frontend" / "src").rglob("*.js*"),
            # The trend chart bundle is a build output (React), not our code.
            *(p for p in (app / "static").rglob("*") if p.is_file() and "trend" not in p.parts),
        ]
        for path in sources:
            if path.suffix in (".html", ".py", ".js", ".jsx", ".json", ".css", ".svg"):
                with self.subTest(path=str(path.relative_to(root))):
                    self.assertNotIn("serviceWorker", path.read_text(encoding="utf-8"))

    # 22
    def test_guide_page_for_anonymous_and_logged_in(self):
        for logged_in in (False, True):
            if logged_in:
                self.client.force_login(self.user)
            with self.subTest(logged_in=logged_in):
                response = self.client.get(reverse("add_to_home"))
                self.assertEqual(response.status_code, 200)
                content = response.content.decode()
                # U+FF5C FULLWIDTH VERTICAL LINE, as in the other page titles
                self.assertIn("<title>加到主畫面\uff5cHearWell</title>", content)
                self.assertNotIn('aria-current="page"', content)
                main = content[content.index("<main") : content.index("</main>")]
                positions = [main.index(part) for part in self.GUIDE_ORDER]
                self.assertEqual(positions, sorted(positions))
                steps = [ol.count("<li>") for ol in re.findall(r"<ol>(.*?)</ol>", main, re.DOTALL)]
                self.assertEqual(steps, [4, 4])

    # 23
    def test_home_links_to_guide_before_disclaimer(self):
        content = self.client.get(reverse("index")).content.decode()
        link = re.search(
            rf'<a[^>]*href="{reverse("add_to_home")}"[^>]*>\s*把 HearWell 加到手機主畫面', content
        )
        self.assertIsNotNone(link)
        self.assertLess(link.start(), content.index("本網站由執業聽力師開發"))


class IoiHaTests(TestCase):
    """Spec docs/specs/phase4_ioi_ha.md, acceptance 1-22."""

    INTRO = "本量表適合已配戴助聽器的人"
    HEARING_AID_PROMPT = "這次填答時，您有沒有戴助聽器？"
    SOURCE = ("原量表：IOI-HA（Cox 等人）", "中譯：林克寰《助聽器選配與驗證》", "CC BY 3.0 台灣")
    NORM_SOURCE = "常模：Cox、Alexander、Beyer（2003）"
    NORM_NOTE = "常模範圍是一般助聽器使用者中，中間一半的人的分數"
    ADVICE = "如有多項低於常模，可以帶這份結果跟您的聽力師討論"
    UNGROUPED_NOTE = "需要一筆沒戴助聽器時填的 HHIE-S，才能跟常模比較"
    COMPARISONS = ("低於常模", "在範圍內", "高於常模")

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="ioi_user")
        cls.other = User.objects.create_user(username="ioi_other")
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
            Question(
                questionnaire=cls.ioi_ha,
                question_text=f"IOI題{i}",
                question_number=i,
                category="",
            )
            for i in range(1, 8)
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.ioi_ha.id])

    def _main(self, response):
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _hhie_s(self, total, wearing, user=None, created_at=None):
        # total must be even: 4s first, then one 2 if needed.
        scores = [4] * (total // 4) + [2] * (total % 4 // 2)
        scores += [0] * (10 - len(scores))
        submission = Submission.objects.create(
            user=user or self.user, questionnaire=self.hhie_s, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(self.hhie_questions, scores, strict=True)
        )
        if created_at is not None:
            Submission.objects.filter(pk=submission.pk).update(created_at=created_at)
        return submission

    def _post(self, scores=(3,) * 7, **extra):
        data = {"form-TOTAL_FORMS": 7, "form-INITIAL_FORMS": 0}
        for i, (question, score) in enumerate(zip(self.ioi_questions, scores, strict=True)):
            data[f"form-{i}-score"] = str(score)
            data[f"form-{i}-question_id"] = str(question.id)
        data.update(extra)
        return self.client.post(self.url, data)

    def _ioi_submission(self):
        return Submission.objects.get(questionnaire=self.ioi_ha)

    def _items(self, main):
        return re.findall(r"<li[^>]*>(.*?)</li>", main, re.DOTALL)

    # Answering (1-4)
    def test_answer_page_items_and_text(self):
        main = self._main(self.client.get(self.url))
        self.assertEqual(main.count("<fieldset"), 7)
        for i in range(7):
            with self.subTest(form=i):
                for value in range(1, 6):
                    self.assertIn(f'name="form-{i}-score" value="{value}"', main)
                self.assertNotIn(f'name="form-{i}-score" value="0"', main)
        for label in scoring.IOI_HA_CHOICES[1]:
            self.assertIn(label, main)
        self.assertNotIn("checked", main)
        self.assertNotIn("常常", main)
        self.assertNotIn(self.HEARING_AID_PROMPT, main)
        self.assertNotIn("wearing_hearing_aid", main)
        self.assertIn(self.INTRO, main)
        for part in self.SOURCE:
            self.assertIn(part, main)

    def test_each_item_shows_its_own_choices(self):
        main = self._main(self.client.get(self.url))
        fieldsets = re.findall(r"<fieldset.*?</fieldset>", main, re.DOTALL)
        for number, fieldset in enumerate(fieldsets, start=1):
            with self.subTest(item=number):
                for label in scoring.IOI_HA_CHOICES[number]:
                    self.assertIn(label, fieldset)

    def test_missing_answer_not_saved_and_answers_kept(self):
        response = self._post(**{"form-6-score": ""})
        self.assertFalse(Submission.objects.filter(questionnaire=self.ioi_ha).exists())
        self.assertContains(response, "還有 1 題沒有回答")
        self.assertContains(
            response,
            '<input type="radio" name="form-0-score" value="3" class="choice-group"'
            ' id="id_form-0-score_2" checked>',
            html=True,
        )

    def test_tampered_score_rejected(self):
        for score in (0, 6):
            with self.subTest(score=score):
                response = self._post(**{"form-0-score": str(score)})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Submission.objects.filter(questionnaire=self.ioi_ha).exists())
                self.assertContains(response, "表單資料有誤")

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    # Grouping (5-12)
    def _group_after_post(self):
        self.assertEqual(self._post().status_code, 302)
        return self._ioi_submission()

    def test_unaided_24_is_mild_moderate(self):
        basis = self._hhie_s(24, wearing=False)
        submission = self._group_after_post()
        self.assertEqual(submission.norm_group, "mild_moderate")
        self.assertEqual(submission.norm_basis, basis)

    def test_unaided_26_is_moderately_severe(self):
        self._hhie_s(26, wearing=False)
        self.assertEqual(self._group_after_post().norm_group, "moderately_severe")

    def test_unaided_0_is_mild_moderate(self):
        self._hhie_s(0, wearing=False)
        self.assertEqual(self._group_after_post().norm_group, "mild_moderate")

    def test_latest_unaided_used_even_if_aided_is_newer(self):
        basis = self._hhie_s(30, wearing=False)
        self._hhie_s(10, wearing=True)
        submission = self._group_after_post()
        self.assertEqual(submission.norm_group, "moderately_severe")
        self.assertEqual(submission.norm_basis, basis)

    def test_latest_of_several_unaided_used(self):
        self._hhie_s(30, wearing=False, created_at=timezone.now() - timedelta(days=9))
        basis = self._hhie_s(10, wearing=False)
        submission = self._group_after_post()
        self.assertEqual(submission.norm_group, "mild_moderate")
        self.assertEqual(submission.norm_basis, basis)

    def test_ungrouped_without_unaided_hhie_s(self):
        cases = {"no HHIE-S": (), "unrecorded": (None,), "aided": (True,), "both": (None, True)}
        for name, statuses in cases.items():
            with self.subTest(case=name):
                Answer.objects.all().delete()
                Submission.objects.all().delete()
                for wearing in statuses:
                    self._hhie_s(10, wearing=wearing)
                submission = self._group_after_post()
                self.assertEqual(submission.norm_group, "ungrouped")
                self.assertIsNone(submission.norm_basis)

    def test_other_users_hhie_s_not_used(self):
        self._hhie_s(30, wearing=False, user=self.other)
        submission = self._group_after_post()
        self.assertEqual(submission.norm_group, "ungrouped")
        self.assertIsNone(submission.norm_basis)

    def test_group_fixed_after_new_hhie_s(self):
        self._hhie_s(10, wearing=False)
        submission = self._group_after_post()
        self._hhie_s(30, wearing=False)
        submission.refresh_from_db()
        self.assertEqual(submission.norm_group, "mild_moderate")
        main = self._main(self.client.get(reverse("result", args=[submission.id])))
        self.assertIn("常模組別：輕度至中度", main)
        self.assertIn("10 分", main)

    def test_ungrouped_stays_ungrouped(self):
        submission = self._group_after_post()
        self._hhie_s(30, wearing=False)
        submission.refresh_from_db()
        self.assertEqual(submission.norm_group, "ungrouped")
        main = self._main(self.client.get(reverse("result", args=[submission.id])))
        self.assertIn("常模組別：未分組", main)

    # Result (13-16)
    def test_compare_to_norm_both_groups(self):
        cases = (
            # mild_moderate item 4 (Sat) is 2-4
            ("mild_moderate", 4, 1, "below"),
            ("mild_moderate", 4, 2, "within"),
            ("mild_moderate", 4, 4, "within"),
            ("mild_moderate", 4, 5, "above"),
            # moderately_severe item 3 (RAL) is 2-4, item 1 (Use) is 4-5
            ("moderately_severe", 3, 1, "below"),
            ("moderately_severe", 3, 3, "within"),
            ("moderately_severe", 3, 5, "above"),
            ("moderately_severe", 1, 3, "below"),
            ("moderately_severe", 1, 5, "within"),
        )
        for group, number, score, expected in cases:
            with self.subTest(group=group, item=number, score=score):
                self.assertEqual(scoring.compare_to_norm(group, number, score), expected)

    def test_result_page_marks_each_item(self):
        self._hhie_s(10, wearing=False)
        # mild_moderate: item 2 (3-4) gets 5, item 4 (2-4) gets 1, item 5 (3-4) gets 4.
        response = self.client.get(self._post(scores=(3, 5, 3, 1, 4, 3, 3)).url)
        items = self._items(self._main(response))
        self.assertEqual(len(items), 7)
        self.assertIn("高於常模", items[1])
        self.assertIn("低於常模", items[3])
        self.assertIn("在範圍內", items[4])
        self.assertIn(scoring.IOI_HA_CHOICES[4][0], items[3])

    def test_grouped_result_page(self):
        when = datetime(2026, 10, 1, 4, 0, tzinfo=ZoneInfo("UTC"))
        self._hhie_s(24, wearing=False, created_at=when)
        with self.assertNoLogs("screening.scoring", level="ERROR"):
            response = self.client.get(self._post().url)
        self.assertContains(response, "<title>IOI-HA 結果\uff5cHearWell</title>", html=False)
        main = self._main(response)
        for text in (
            "常模組別：輕度至中度",
            "2026/10/01",
            "24 分",
            self.NORM_NOTE,
            self.ADVICE,
            self.NORM_SOURCE,
            *self.SOURCE,
        ):
            with self.subTest(text=text):
                self.assertIn(text, main)
        for text in ("總分", "助聽器：", "無法判讀", "建議前往"):
            with self.subTest(absent=text):
                self.assertNotIn(text, main)

    def test_ungrouped_result_page(self):
        with self.assertNoLogs("screening.scoring", level="ERROR"):
            response = self.client.get(self._post().url)
        main = self._main(response)
        items = self._items(main)
        self.assertEqual(len(items), 7)
        self.assertIn("常模組別：未分組", main)
        self.assertIn(self.UNGROUPED_NOTE, main)
        for text in self.COMPARISONS:
            self.assertNotIn(text, main)
        self.assertNotIn("總分", main)

    def test_result_page_uses_moderately_severe_norms(self):
        # Item 1 = 3 is within mild_moderate (3-5) but below moderately_severe (4-5).
        self._hhie_s(30, wearing=False)
        main = self._main(self.client.get(self._post().url))
        self.assertRegex(main, r"<h1[^>]*>IOI-HA 結果</h1>")
        self.assertIn("常模組別：中重度以上", main)
        items = self._items(main)
        self.assertIn("低於常模", items[0])
        self.assertIn("在範圍內", items[1])

    def test_user_records_delete_together_but_basis_not_alone(self):
        basis = self._hhie_s(10, wearing=False)
        self._post()
        basis.answers.all().delete()
        with self.assertRaises(RestrictedError):
            basis.delete()
        Answer.objects.filter(submission__user=self.user).delete()
        Submission.objects.filter(user=self.user).delete()
        self.assertFalse(Submission.objects.filter(user=self.user).exists())

    def test_other_users_result_is_404(self):
        self.client.force_login(self.other)
        self._post()
        submission = self._ioi_submission()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("result", args=[submission.id])).status_code, 404)

    # History, trend chart, API (17-19)
    def test_history_rows(self):
        self._post()
        self._hhie_s(10, wearing=False)
        self._post()
        with self.assertNoLogs("screening.scoring", level="ERROR"):
            main = self._main(self.client.get(reverse("my_hearing")))
        cards = main.split('class="card ')[1:]
        ioi_cards = [card for card in cards if "IOI-HA" in card]
        self.assertEqual(len(ioi_cards), 2)
        self.assertIn("輕度至中度", ioi_cards[0])
        self.assertIn("未分組", ioi_cards[1])
        for card in ioi_cards:
            self.assertRegex(card, r"\d{4}/\d{2}/\d{2}")
            for text in ("總分", "助聽器：", "無法判讀"):
                self.assertNotIn(text, card)

    def test_api_lists_only_hhie_s(self):
        hhie = self._hhie_s(10, wearing=False)
        self._post()
        results = self.client.get("/api/submissions/").json()["results"]
        self.assertEqual([item["id"] for item in results], [hhie.id])
        codes = [item["code"] for item in self.client.get("/api/questionnaires/").json()]
        self.assertEqual(codes, ["hhie-s"])

    def test_api_detail_for_ioi_ha_is_404(self):
        self._post()
        submission = self._ioi_submission()
        self.assertEqual(self.client.get(f"/api/submissions/{submission.id}/").status_code, 404)

    # HHIE-S unchanged (20)
    def test_hhie_s_page_and_answers_unchanged(self):
        main = self._main(self.client.get(reverse("screening", args=[self.hhie_s.id])))
        self.assertIn(self.HEARING_AID_PROMPT, main)
        self.assertIn("常常", main)
        self.assertNotIn(self.INTRO, main)
        self.assertNotIn(self.SOURCE[0], main)
        data = {"form-TOTAL_FORMS": 10, "form-INITIAL_FORMS": 0, "wearing_hearing_aid": "False"}
        for i, question in enumerate(self.hhie_questions):
            data[f"form-{i}-score"] = "4"
            data[f"form-{i}-question_id"] = str(question.id)
        for score in ("1", "3", "5"):
            with self.subTest(score=score):
                response = self.client.post(
                    reverse("screening", args=[self.hhie_s.id]), {**data, "form-0-score": score}
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Submission.objects.exists())
        self.client.post(reverse("screening", args=[self.hhie_s.id]), data)
        submission = Submission.objects.get()
        self.assertEqual(submission.norm_group, "")
        self.assertIsNone(submission.norm_basis)
        self.assertEqual(submission.total_answer_score, 40)

    # Entry (21-22)
    def test_questionnaire_list_card(self):
        response = self.client.get(reverse("questionnaire_list"))
        self.assertContains(response, "<title>選擇問卷\uff5cHearWell</title>")
        main = self._main(response)
        self.assertRegex(main, rf'<a[^>]*href="{self.url}"[^>]*>\s*IOI-HA 助聽器效益量表')
        self.assertIn("適合已配戴助聽器的人。共 7 題，大約 2 分鐘。", main)
        self.assertIn("適合 65 歲以上的長輩。共 10 題，大約 3 分鐘。", main)


class IoiHaFixtureTests(TestCase):
    def test_fixture_matches_rule_tables(self):
        call_command("loaddata", "questions_fixture.json", verbosity=0)
        self.assertEqual(Questionnaire.objects.get(code="hhie-s").questions.count(), 10)
        questions = Questionnaire.objects.get(code="ioi-ha").questions.all()
        numbers = [question.question_number for question in questions]
        self.assertEqual(numbers, list(range(1, 8)))
        self.assertEqual({question.category for question in questions}, {""})
        self.assertEqual(set(scoring.IOI_HA_CHOICES), set(numbers))
        for labels in scoring.IOI_HA_CHOICES.values():
            self.assertEqual(len(labels), 5)
        for group in ("mild_moderate", "moderately_severe"):
            norms = scoring.IOI_HA_NORMS[group]
            self.assertEqual(set(norms), set(numbers))
            for low, high in norms.values():
                self.assertTrue(1 <= low <= high <= 5)


class HistoryTabsTests(TestCase):
    """Spec docs/specs/phase4_history_by_questionnaire.md, acceptance 1-19."""

    CHART_JS = "screening/frontend/trend-chart.js"
    NOTE = "分數越低，聽力對生活的影響越小"
    UNGROUPED_NOTE = "需要一筆沒戴助聽器時填的 HHIE-S，才能跟常模比較"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tabs_user")
        cls.other = User.objects.create_user(username="tabs_other")
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

    def test_difference_uses_latest_unaided_and_aided(self):
        self._hhie_s(30, False, days_ago=30)
        unaided = self._hhie_s(28, False, days_ago=20)
        aided = self._hhie_s(12, True, days_ago=10)
        self._hhie_s(40, None, days_ago=1)
        text = self._difference(self._main(self.client.get(self.url)))
        self.assertIn("配戴前後比較", text)
        self.assertIn(f"沒戴助聽器（{self._date(unaided)}）：28 分", text)
        self.assertIn(f"有戴助聽器（{self._date(aided)}）：12 分", text)
        self.assertIn("少了 16 分", text)
        self.assertIn(self.NOTE, text)

    def test_difference_ignores_order(self):
        self._hhie_s(12, True, days_ago=10)
        self._hhie_s(28, False, days_ago=1)
        self.assertIn("少了 16 分", self._difference(self._main(self.client.get(self.url))))

    def test_difference_of_zero_is_no_change(self):
        self._hhie_s(20, False, days_ago=2)
        self._hhie_s(20, True, days_ago=1)
        text = self._difference(self._main(self.client.get(self.url)))
        self.assertIn("沒有變化", text)
        self.assertIn(self.NOTE, text)

    def test_difference_increase_has_no_verdict(self):
        self._hhie_s(10, False, days_ago=2)
        self._hhie_s(16, True, days_ago=1)
        text = self._difference(self._main(self.client.get(self.url)))
        self.assertIn("多了 6 分", text)
        for word in ("改善", "變差", "有效", "無效", "建議"):
            self.assertNotIn(word, text)

    def test_no_difference_without_both(self):
        cases = {
            "unaided only": (False,),
            "aided only": (True,),
            "unrecorded only": (None,),
            "unrecorded and unaided": (None, False),
            "unrecorded and aided": (None, True),
        }
        for name, statuses in cases.items():
            with self.subTest(case=name):
                Answer.objects.all().delete()
                Submission.objects.all().delete()
                for days_ago, wearing in enumerate(statuses, start=1):
                    self._hhie_s(10, wearing, days_ago=days_ago)
                main = self._main(self.client.get(self.url))
                self.assertIsNone(self._difference(main))
                self.assertNotIn("配戴前後比較", main)

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


class DevChecksTests(SimpleTestCase):
    """Spec docs/specs/phase0_dev_checks.md, acceptance 2-9 and the Python version."""

    ROOT = Path(__file__).resolve().parent.parent
    # Settings are computed when the module loads, so DEBUG=False is checked in a fresh process.
    # Only settings are read; nothing touches the database.
    DUMP = """
import json, sys
if sys.argv[1] == "without-toolbar":
    sys.modules["debug_toolbar"] = None  # as if requirements-dev.txt was not installed
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.test import Client
from django.urls import Resolver404, resolve
call_command("check")
try:
    resolve("/__debug__/render_panel/")
    debug_url = True
except Resolver404:
    debug_url = False
# An API URL: answers 403 without touching the database or static files.
response = Client().get("/api/questionnaires/", secure=True, HTTP_HOST="localhost")
print(json.dumps({
    "debug_url": debug_url,
    "hsts_header": response.headers.get("Strict-Transport-Security"),
    "apps": settings.INSTALLED_APPS,
    "middleware": settings.MIDDLEWARE,
    "hsts_seconds": getattr(settings, "SECURE_HSTS_SECONDS", 0),
    "hsts_subdomains": getattr(settings, "SECURE_HSTS_INCLUDE_SUBDOMAINS", False),
    "hsts_preload": getattr(settings, "SECURE_HSTS_PRELOAD", False),
    "silenced": settings.SILENCED_SYSTEM_CHECKS,
}))
"""

    def _run(self, args, debug, module="config.settings"):
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": module,
            "DEBUG": "True" if debug else "False",
            # A throwaway key for this process only; never written anywhere.
            "SECRET_KEY": get_random_secret_key(),
        }
        return subprocess.run(
            [sys.executable, *args], cwd=self.ROOT, env=env, capture_output=True, text=True
        )

    def _settings(self, debug, toolbar="as-installed", module="config.settings"):
        result = self._run(["-c", self.DUMP, toolbar], debug, module)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def _uses_toolbar(self, dumped):
        return "debug_toolbar" in dumped["apps"] or any(
            m.startswith("debug_toolbar") for m in dumped["middleware"]
        )

    # 2, 6
    def test_production_settings(self):
        dumped = self._settings(debug=False)
        self.assertFalse(self._uses_toolbar(dumped))
        self.assertFalse(dumped["debug_url"])
        self.assertEqual(dumped["hsts_header"], "max-age=3600; includeSubDomains")
        self.assertEqual(dumped["hsts_seconds"], 3600)
        self.assertIs(dumped["hsts_subdomains"], True)
        self.assertIs(dumped["hsts_preload"], False)

    # 4, 7
    def test_debug_without_dev_packages_still_works(self):
        dumped = self._settings(debug=True, toolbar="without-toolbar")
        self.assertFalse(self._uses_toolbar(dumped))
        self.assertFalse(dumped["debug_url"])
        self.assertIsNone(dumped["hsts_header"])
        self.assertEqual(dumped["hsts_seconds"], 0)

    # 3
    def test_tests_never_load_toolbar(self):
        # Set DEBUG=True explicitly instead of relying on a local .env.
        dev = self._settings(debug=True)
        if not self._uses_toolbar(dev):
            self.skipTest("requirements-dev.txt is not installed, nothing to leave out")
        self.assertTrue(dev["debug_url"])
        tests = self._settings(debug=True, module="config.test_settings")
        self.assertFalse(self._uses_toolbar(tests))
        self.assertFalse(tests["debug_url"])
        self.assertNotIn("debug_toolbar", settings.INSTALLED_APPS)
        self.assertFalse([m for m in settings.MIDDLEWARE if m.startswith("debug_toolbar")])
        with self.assertRaises(Resolver404):
            resolve("/__debug__/render_panel/")

    # 5
    def test_toolbar_only_in_dev_requirements(self):
        production = (self.ROOT / "requirements.txt").read_text(encoding="utf-8")
        dev = (self.ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertNotIn("debug-toolbar", production.lower())
        self.assertEqual(dev.splitlines()[0], "-r requirements.txt")
        self.assertRegex(dev, r"(?m)^django-debug-toolbar==\d+\.\d+\.\d+$")

    # 8
    def test_deploy_check_passes_with_warnings_as_errors(self):
        result = self._run(["manage.py", "check", "--deploy", "--fail-level", "WARNING"], False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no issues (1 silenced)", result.stdout)
        self.assertEqual(self._settings(debug=False)["silenced"], ["security.W021"])

    # 9
    def test_build_runs_deploy_check_before_anything_changes(self):
        lines = (self.ROOT / "build.sh").read_text(encoding="utf-8").splitlines()
        self.assertIn("set -o errexit", lines)
        check = lines.index("python manage.py check --deploy --fail-level WARNING")
        for step in (
            "npm run build --prefix frontend",
            "python manage.py collectstatic --no-input",
            "python manage.py migrate",
            "python manage.py loaddata questions_fixture.json",
        ):
            with self.subTest(step=step):
                self.assertLess(check, lines.index(step))

    def test_production_python_matches_tests(self):
        pinned = (self.ROOT / ".python-version").read_text(encoding="utf-8").strip()
        self.assertEqual(pinned, platform.python_version())


class ApiQuestionnaireDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tester")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        # Created out of order so the response has to sort by number.
        for number in (2, 1):
            Question.objects.create(
                questionnaire=cls.questionnaire,
                question_text=f"第{number}題的完整題目文字，超過三十個字也要完整回傳，不可以被截斷掉喔",
                question_number=number,
                category=Category.EMOTIONAL,
            )
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")

    def setUp(self):
        self.client.force_login(self.user)

    def _url(self, pk):
        return f"/api/questionnaires/{pk}/"

    def test_anonymous_gets_403(self):
        self.client.logout()
        self.assertEqual(self.client.get(self._url(self.questionnaire.pk)).status_code, 403)

    def test_returns_questions_in_order_with_choices(self):
        response = self.client.get(self._url(self.questionnaire.pk))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(set(data), {"id", "code", "name", "levels", "questions"})
        self.assertEqual(data["code"], "hhie-s")
        self.assertEqual(len(data["levels"]), 3)
        self.assertEqual([q["number"] for q in data["questions"]], [1, 2])
        first = data["questions"][0]
        self.assertEqual(set(first), {"id", "number", "text", "choices"})
        self.assertEqual(first["text"], Question.objects.get(question_number=1).question_text)
        self.assertEqual(
            first["choices"],
            [
                {"value": 4, "label": "常常"},
                {"value": 2, "label": "有時"},
                {"value": 0, "label": "從未"},
            ],
        )

    def test_missing_or_ioi_ha_gets_404(self):
        for pk in (self.ioi_ha.pk, 9999):
            with self.subTest(pk=pk):
                self.assertEqual(self.client.get(self._url(pk)).status_code, 404)


class ApiSubmitTests(TestCase):
    URL = "/api/submissions/"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="alice_account")
        cls.other = User.objects.create_user(username="bob_account")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        cls.ioi_questions = Question.objects.bulk_create(
            Question(questionnaire=cls.ioi_ha, question_text=f"IOI 第{i}題", question_number=i)
            for i in range(1, 8)
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _body(self, scores=(4,) * 5 + (2,) * 5, wearing=False, questions=None, questionnaire=None):
        questions = self.questions if questions is None else questions
        return {
            "questionnaire": (questionnaire or self.questionnaire).pk,
            "wearing_hearing_aid": wearing,
            # Reversed: the API must not depend on answer order.
            "answers": [
                {"question": q.pk, "score": s}
                for q, s in reversed(list(zip(questions, scores, strict=False)))
            ],
        }

    def _post(self, body, key="__new__", client=None):
        headers = {}
        if key == "__new__":
            key = str(uuid.uuid4())
        if key is not None:
            headers["Idempotency-Key"] = key
        return (client or self.client).post(
            self.URL, json.dumps(body), content_type="application/json", headers=headers
        )

    def assertNothingSaved(self):
        self.assertEqual(Submission.objects.count(), 0)
        self.assertEqual(Answer.objects.count(), 0)

    # 送出作答
    def test_anonymous_gets_403(self):
        self.client.logout()
        self.assertEqual(self._post(self._body()).status_code, 403)
        self.assertNothingSaved()

    def test_missing_csrf_token_gets_403(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(self._post(self._body(), client=client).status_code, 403)
        self.assertNothingSaved()

    def test_valid_submission_is_saved_and_scored(self):
        response = self._post(self._body(wearing=True))
        self.assertEqual(response.status_code, 201)
        submission = Submission.objects.get()
        self.assertEqual(submission.user, self.user)
        self.assertIs(submission.wearing_hearing_aid, True)
        self.assertEqual(submission.answers.count(), 10)
        data = response.json()
        self.assertEqual(data["id"], submission.pk)
        self.assertEqual(data["scores"], {"total": 30, "emotional": 20, "social": 10})
        self.assertEqual(data["level"], {"code": "severe", "text": "顯著影響"})
        # Same numbers as the history page.
        page = self.client.get(reverse("my_hearing")).content.decode()
        self.assertIn("總分：30", page)
        self.assertIn("顯著影響", page)

    def test_all_zero_is_a_real_score(self):
        response = self._post(self._body(scores=(0,) * 10))
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["scores"]["total"], 0)
        self.assertEqual(data["level"]["code"], "normal")

    def test_user_in_body_is_ignored(self):
        body = {**self._body(), "user": self.other.pk}
        self.assertEqual(self._post(body).status_code, 201)
        self.assertEqual(Submission.objects.get().user, self.user)
        self.assertFalse(self.other.submissions.exists())

    def test_invalid_answers_get_400(self):
        foreign = [*self.questions[:9], self.ioi_questions[0]]
        cases = {
            "missing": (
                self._body(scores=(0,) * 9, questions=self.questions[:9]),
                "有題目沒有作答",
            ),
            "duplicate": (
                self._body(questions=[*self.questions[:9], self.questions[0]]),
                "重複題目",
            ),
            "foreign": (self._body(questions=foreign), "有題目沒有作答"),
            "bad score": (self._body(scores=(3,) + (0,) * 9), None),
        }
        for name, (body, message) in cases.items():
            with self.subTest(name):
                response = self._post(body)
                self.assertEqual(response.status_code, 400)
                errors = response.json()
                self.assertEqual(set(errors), {"answers"})
                if message:
                    self.assertIn(message, errors["answers"])
                self.assertNothingSaved()

    def test_wearing_hearing_aid_is_required(self):
        body = self._body()
        # Only JSON true/false: DRF would otherwise read 1, "yes", "on", "true" as True.
        for value in ("missing", None, "maybe", 1, 0, "yes", "on", "true"):
            with self.subTest(value=value):
                if value == "missing":
                    body.pop("wearing_hearing_aid", None)
                else:
                    body["wearing_hearing_aid"] = value
                response = self._post(body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(), {"wearing_hearing_aid": ["請選擇這次有沒有戴助聽器"]}
                )
                self.assertNothingSaved()

    def test_unknown_questionnaire_gets_400(self):
        body = {**self._body(), "questionnaire": 9999}
        response = self._post(body)
        self.assertEqual(response.status_code, 400)
        self.assertIn("questionnaire", response.json())
        self.assertNothingSaved()

    def test_questionnaire_without_questions_gets_400(self):
        empty = Questionnaire.objects.create(questionnaire_name="空問卷", code="empty")
        body = {"questionnaire": empty.pk, "wearing_hearing_aid": False, "answers": []}
        response = self._post(body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"questionnaire": ["這份問卷沒有題目"]})
        self.assertNothingSaved()

    def test_ioi_ha_gets_400(self):
        body = self._body(scores=(3,) * 7, questions=self.ioi_questions, questionnaire=self.ioi_ha)
        response = self._post(body)
        self.assertEqual(response.status_code, 400)
        self.assertIn("questionnaire", response.json())
        self.assertNothingSaved()

    def test_failure_midway_leaves_nothing(self):
        with (
            mock.patch.object(Answer.objects, "bulk_create", side_effect=DatabaseError),
            self.assertRaises(DatabaseError),
        ):
            self._post(self._body())
        self.assertNothingSaved()

    def test_schema_documents_write_endpoints(self):
        content = self.client.get("/api/schema/").content.decode()
        self.assertIn("/api/questionnaires/{id}/:", content)
        submissions = content.split("/api/submissions/:", 1)[1].split("/api/submissions/{id}/:")[0]
        self.assertIn("post:", submissions)
        self.assertIn("Idempotency-Key", submissions)

    def test_detail_stays_read_only(self):
        submission = Submission.objects.create(user=self.user, questionnaire=self.questionnaire)
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(f"{self.URL}{submission.pk}/")
                self.assertEqual(response.status_code, 405)

    # 收據編號
    def test_same_key_same_body_returns_first(self):
        key = str(uuid.uuid4())
        first = self._post(self._body(), key=key)
        second = self._post(self._body(), key=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(Submission.objects.count(), 1)

    def test_same_key_different_body_gets_409(self):
        key = str(uuid.uuid4())
        self._post(self._body(), key=key)
        # A valid HHIA-S body: only the questionnaire differs from the first request.
        hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")
        hhia_questions = Question.objects.bulk_create(
            Question(questionnaire=hhia_s, question_text=f"HHIA 第{i}題", question_number=i)
            for i in range(1, 11)
        )
        different = {
            "scores": self._body(scores=(0,) * 10),
            "wearing": self._body(wearing=True),
            "questionnaire": self._body(questions=hhia_questions, questionnaire=hhia_s),
        }
        for name, body in different.items():
            with self.subTest(name):
                response = self._post(body, key=key)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json(), {"detail": "這個收據編號已經用過"})
                self.assertEqual(Submission.objects.count(), 1)
                self.assertEqual(Submission.objects.get().total_answer_score, 30)

    def test_missing_or_invalid_key_gets_400(self):
        for key in (None, "", "not-a-uuid"):
            with self.subTest(key=key):
                response = self._post(self._body(), key=key)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"detail": "缺少或無效的收據編號"})
                self.assertNothingSaved()

    def test_key_is_scoped_to_user(self):
        key = str(uuid.uuid4())
        self.client.force_login(self.other)
        self._post(self._body(scores=(0,) * 10), key=key)
        self.client.force_login(self.user)
        response = self._post(self._body(), key=key)
        self.assertEqual(response.status_code, 201)
        mine = self.user.submissions.get()
        self.assertEqual(response.json()["id"], mine.pk)
        self.assertEqual(response.json()["scores"]["total"], 30)

    def test_concurrent_same_key_returns_first_not_500(self):
        key = str(uuid.uuid4())
        first = self._post(self._body(), key=key)
        # The second request checks before the first has saved, then hits the unique constraint.
        existing = Submission.objects.get()
        with mock.patch.object(api_views, "_find_by_key", side_effect=[None, existing]):
            second = self._post(self._body(), key=key)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(Submission.objects.count(), 1)

    # 回傳內容
    def test_created_body_matches_detail_get(self):
        response = self._post(self._body())
        detail = self.client.get(f"{self.URL}{response.json()['id']}/")
        self.assertEqual(response.json(), detail.json())

    def test_errors_are_in_chinese_by_field(self):
        response = self._post({"answers": "not a list"})
        self.assertEqual(response.status_code, 400)
        errors = response.json()
        self.assertEqual(set(errors), {"questionnaire", "wearing_hearing_aid", "answers"})
        for messages in errors.values():
            for message in messages:
                self.assertRegex(message, r"[一-鿿]")

    # 兩支 API 接得起來
    def test_questionnaire_detail_feeds_submit(self):
        detail = self.client.get(f"/api/questionnaires/{self.questionnaire.pk}/").json()
        body = {
            "questionnaire": detail["id"],
            "wearing_hearing_aid": False,
            "answers": [
                {"question": q["id"], "score": q["choices"][-1]["value"]}
                for q in detail["questions"]
            ],
        }
        self.assertEqual(self._post(body).status_code, 201)


class ReactAnswerPageTests(TestCase):
    """Spec docs/specs/phase5_react_answer.md: Django side of the React answer page."""

    ANSWER_JS = "screening/frontend/answer.js"
    LOGOUT_JS = "screening/frontend/logout.js"
    VITE_CONFIG = Path(__file__).resolve().parent.parent / "frontend" / "vite.config.js"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="react_answer")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        for questionnaire in (cls.hhie_s, cls.hhia_s, cls.ioi_ha):
            Question.objects.create(
                questionnaire=questionnaire,
                question_text=f"{questionnaire.code} 第1題",
                question_number=1,
                category="" if questionnaire.code == "ioi-ha" else Category.EMOTIONAL,
            )

    def setUp(self):
        self.client.force_login(self.user)

    def _page(self, questionnaire):
        return self.client.get(reverse("screening", args=[questionnaire.id]))

    def test_hhie_s_and_hhia_s_load_react_with_their_data(self):
        for questionnaire in (self.hhie_s, self.hhia_s):
            with self.subTest(code=questionnaire.code):
                response = self._page(questionnaire)
                self.assertContains(response, self.ANSWER_JS)
                self.assertContains(response, 'id="answer-app"')
                self.assertContains(response, f'data-questionnaire-id="{questionnaire.id}"')
                self.assertContains(response, f'data-user-id="{self.user.id}"')

    def test_django_form_is_still_complete_without_js(self):
        # Fallback when the JS does not load: the full form is rendered and posts as before.
        response = self._page(self.hhie_s)
        self.assertContains(response, 'id="answer-form"')
        self.assertContains(response, 'name="wearing_hearing_aid"')
        self.assertContains(response, "hhie-s 第1題")
        self.assertContains(response, 'type="submit"')
        question = self.hhie_s.questions.get()
        response = self.client.post(
            reverse("screening", args=[self.hhie_s.id]),
            {
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-0-question_id": str(question.id),
                "form-0-score": "4",
                "wearing_hearing_aid": "False",
            },
        )
        submission = Submission.objects.get(user=self.user)
        self.assertRedirects(response, reverse("result", args=[submission.id]))

    def test_intro_is_outside_the_form(self):
        # React hides the form, so the name, count and instructions must stay visible outside it.
        content = self._page(self.hhie_s).content.decode()
        form_start = content.index('id="answer-form"')
        self.assertLess(content.index("<h2"), form_start)
        self.assertLess(content.index("共 1 題"), form_start)
        self.assertLess(content.index("本問卷的目的"), form_start)

    def test_ioi_ha_stays_django_only(self):
        response = self._page(self.ioi_ha)
        self.assertNotContains(response, self.ANSWER_JS)
        self.assertNotContains(response, 'id="answer-app"')
        self.assertContains(response, 'id="answer-form"')

    def test_answer_js_only_on_answer_pages(self):
        for url in (reverse("index"), reverse("questionnaire_list"), reverse("my_hearing")):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), self.ANSWER_JS)

    def test_logout_js_when_logged_in_only(self):
        for url in (reverse("index"), reverse("questionnaire_list"), reverse("my_hearing")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, self.LOGOUT_JS)
                self.assertContains(response, 'id="logout-form"')
        self.client.logout()
        for url in (reverse("index"), reverse("login"), reverse("register")):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), self.LOGOUT_JS)

    def test_bundle_paths_match_vite_output(self):
        # The templates and the Vite build must agree on where the bundles live.
        config = self.VITE_CONFIG.read_text(encoding="utf-8")
        self.assertIn('"../screening/static/screening/frontend"', config)
        for entry in ('"trend-chart"', '"answer"', '"logout"'):
            with self.subTest(entry=entry):
                self.assertIn(entry, config)


def _point(conduction, ear, frequency, db, no_response):
    return {
        "ear": ear,
        "conduction": conduction,
        "frequency": frequency,
        "db": db,
        "no_response": no_response,
    }


def _air(ear, frequency, db, no_response=False):
    return _point("air", ear, frequency, db, no_response)


def _bone(ear, frequency, db, no_response=False):
    return _point("bone", ear, frequency, db, no_response)


def _four(maker, ear, values):
    return [maker(ear, f, db) for f, db in zip((500, 1000, 2000, 4000), values, strict=True)]


class AudiogramRuleTests(SimpleTestCase):
    """Spec docs/specs/phase5_audiogram.md 4.3, acceptance 18-27 (the rules alone)."""

    def _interpret(self, points):
        from screening.audiogram import interpret

        objects = [mock.Mock(**point) for point in points]
        return interpret(objects)

    def test_pta_and_degree(self):
        right = self._interpret(_four(_air, "right", (40, 45, 50, 55)))["right"]
        self.assertEqual(right["pta"], 47.5)
        self.assertEqual(right["degree"], "中度")

    def test_degree_boundaries(self):
        from screening.audiogram import degree

        expected = {
            25: "正常",
            26.25: "輕度",
            40: "輕度",
            41.25: "中度",
            55: "中度",
            56.25: "中重度",
            70: "中重度",
            71.25: "重度",
            90: "重度",
            91.25: "極重度",
        }
        for value, name in expected.items():
            with self.subTest(value=value):
                self.assertEqual(degree(value), name)

    def test_type(self):
        cases = {(45,) * 4: "感音神經性", (20,) * 4: "傳導性", (30,) * 4: "混合性"}
        for bone, expected in cases.items():
            with self.subTest(bone=bone):
                points = _four(_air, "right", (50,) * 4) + _four(_bone, "right", bone)
                self.assertEqual(self._interpret(points)["right"]["type"], expected)

    def test_type_boundaries(self):
        from screening.audiogram import hearing_type

        self.assertEqual(hearing_type(25, None), "正常")
        self.assertEqual(hearing_type(50, 35.25), "感音神經性")  # gap 14.75
        self.assertEqual(hearing_type(50, 35), "混合性")  # gap 15, bone > 25
        self.assertEqual(hearing_type(40, 25), "傳導性")  # gap 15, bone 25

    def test_normal_air_needs_no_bone(self):
        right = self._interpret(_four(_air, "right", (20,) * 4))["right"]
        self.assertEqual(right["degree"], "正常")
        self.assertEqual(right["type"], "正常")

    def test_missing_air_frequency_is_insufficient(self):
        points = [_air("right", f, 40) for f in (500, 1000, 4000)] + _four(_air, "left", (40,) * 4)
        result = self._interpret(points)
        self.assertIsNone(result["right"]["pta"])
        self.assertIsNone(result["right"]["degree"])
        self.assertEqual(result["left"]["degree"], "輕度")

    def test_incomplete_bone_leaves_type_open(self):
        bone = [_bone("right", f, 45) for f in (500, 2000, 4000)]
        points = _four(_air, "right", (50,) * 4) + bone
        right = self._interpret(points)["right"]
        self.assertEqual(right["degree"], "中度")
        self.assertIsNone(right["type"])

    def test_only_outer_frequencies_is_insufficient(self):
        points = [_air(ear, f, 40) for ear in ("right", "left") for f in (250, 8000)]
        result = self._interpret(points)
        self.assertIsNone(result["right"]["pta"])
        self.assertIsNone(result["left"]["pta"])

    def test_no_response_uses_marked_value(self):
        points = [_air("right", f, db) for f, db in ((500, 90), (1000, 100), (2000, 110))]
        points.append(_air("right", 4000, 120, no_response=True))
        right = self._interpret(points)["right"]
        self.assertEqual(right["pta"], 105)
        self.assertEqual(right["degree"], "極重度")
        self.assertTrue(right["no_response"])

    def test_bone_no_response_uses_80(self):
        points = _four(_air, "right", (100,) * 4)
        points += [_bone("right", f, db) for f, db in ((500, 60), (1000, 70), (2000, 75))]
        points.append(_bone("right", 4000, 80, no_response=True))
        right = self._interpret(points)["right"]
        self.assertEqual(right["type"], "混合性")  # bone 71.25, gap 28.75
        self.assertTrue(right["no_response"])

    def test_bone_no_response_value_decides_type(self):
        # Review 3-3: at an air average of 86.25 only 80 gives a gap of 15 or more.
        points = [_air("right", f, db) for f, db in ((500, 85), (1000, 85), (2000, 85), (4000, 90))]
        points += [_bone("right", f, db) for f, db in ((500, 60), (1000, 70), (2000, 75))]
        points.append(_bone("right", 4000, 80, no_response=True))
        self.assertEqual(self._interpret(points)["right"]["type"], "混合性")

    def test_masked_counts_like_unmasked(self):
        # Acceptance 39: interpretation reads values only.
        points = [{**p, "masked": True} for p in _four(_air, "right", (40, 45, 50, 55))]
        right = self._interpret(points)["right"]
        self.assertEqual(right["pta"], 47.5)
        self.assertEqual(right["degree"], "中度")

    def test_no_response_outside_pta_has_no_note(self):
        points = [*_four(_air, "right", (40,) * 4), _air("right", 8000, 120, no_response=True)]
        self.assertFalse(self._interpret(points)["right"]["no_response"])


class AudiogramApiTests(TestCase):
    """Spec docs/specs/phase5_audiogram.md, acceptance 12-17 and 30 (API side)."""

    URL = "/api/audiograms/"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="audiogram_api")
        cls.other = User.objects.create_user(username="audiogram_other")

    def setUp(self):
        self.client.force_login(self.user)

    def _body(self, points=None, tested_on="2026-10-01"):
        points = _four(_air, "right", (40, 45, 50, 55)) if points is None else points
        return {"tested_on": tested_on, "points": points}

    def _post(self, body, key="__new__"):
        headers = {"Idempotency-Key": str(uuid.uuid4()) if key == "__new__" else key}
        return self.client.post(
            self.URL, json.dumps(body), content_type="application/json", headers=headers
        )

    def _models(self):
        from screening.models import Audiogram, AudiogramPoint

        return Audiogram, AudiogramPoint

    def assertNothingSaved(self):
        Audiogram, AudiogramPoint = self._models()
        self.assertEqual(Audiogram.objects.count(), 0)
        self.assertEqual(AudiogramPoint.objects.count(), 0)

    def test_create(self):
        response = self._post(self._body())
        self.assertEqual(response.status_code, 201)
        Audiogram, _ = self._models()
        audiogram = Audiogram.objects.get()
        self.assertEqual(audiogram.user, self.user)
        self.assertEqual(audiogram.tested_on, date(2026, 10, 1))
        self.assertEqual(audiogram.points.count(), 4)
        body = response.json()
        self.assertEqual(body["id"], audiogram.id)
        self.assertEqual(body["interpretation"]["right"]["pta"], 47.5)
        self.assertEqual(body["interpretation"]["right"]["degree"], "中度")

    def test_zero_and_minus_ten_are_kept(self):
        points = [_air("right", 500, 0), _air("right", 1000, -10)]
        self.assertEqual(self._post(self._body(points)).status_code, 201)
        Audiogram, _ = self._models()
        saved = {p.frequency: p.db for p in Audiogram.objects.get().points.all()}
        self.assertEqual(saved, {500: 0, 1000: -10})

    def test_no_response_points(self):
        points = [
            _air("left", 4000, 120, no_response=True),
            _bone("left", 1000, 80, no_response=True),
        ]
        self.assertEqual(self._post(self._body(points)).status_code, 201)
        Audiogram, _ = self._models()
        self.assertTrue(all(p.no_response for p in Audiogram.objects.get().points.all()))

    def test_masked(self):
        # Acceptance 41: missing means unmasked; only true/false accepted.
        points = [{**_air("right", 1000, 50), "masked": True}, _air("right", 2000, 50)]
        response = self._post(self._body(points))
        self.assertEqual(response.status_code, 201)
        Audiogram, _ = self._models()
        saved = {p.frequency: p.masked for p in Audiogram.objects.get().points.all()}
        self.assertEqual(saved, {1000: True, 2000: False})
        self.assertIn({**_air("right", 1000, 50), "masked": True}, response.json()["points"])
        Audiogram.objects.all().delete()
        for value in ("yes", 1, None):
            with self.subTest(masked=value):
                bad = [{**_air("right", 1000, 50), "masked": value}]
                self.assertEqual(self._post(self._body(bad)).status_code, 400)
                self.assertNothingSaved()

    def test_same_key_different_masking_is_409(self):
        key = str(uuid.uuid4())
        self._post(self._body([_air("right", 1000, 50)]), key=key)
        masked = [{**_air("right", 1000, 50), "masked": True}]
        self.assertEqual(self._post(self._body(masked), key=key).status_code, 409)

    def test_retry_with_same_key_returns_first(self):
        key = str(uuid.uuid4())
        first = self._post(self._body(), key=key)
        second = self._post(self._body(), key=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["id"], first.json()["id"])
        Audiogram, _ = self._models()
        self.assertEqual(Audiogram.objects.count(), 1)

    def test_same_key_different_content_is_409(self):
        key = str(uuid.uuid4())
        self._post(self._body(), key=key)
        response = self._post(self._body(tested_on="2026-09-01"), key=key)
        self.assertEqual(response.status_code, 409)

    def test_missing_key_is_400(self):
        response = self._post(self._body(), key="")
        self.assertEqual(response.status_code, 400)
        self.assertNothingSaved()

    def test_invalid_points_are_400_and_save_nothing(self):
        invalid = {
            "frequency not listed": [_air("right", 750, 40)],
            "db not multiple of 5": [_air("right", 1000, 42)],
            "air above 120": [_air("right", 1000, 125)],
            "below -10": [_air("right", 1000, -15)],
            "bone above 80": [_bone("right", 1000, 85)],
            "bone at 3000": [_bone("right", 3000, 40)],
            "bone at 8000": [_bone("right", 8000, 40)],
            "air no response not at 120": [_air("right", 1000, 100, no_response=True)],
            "bone no response not at 80": [_bone("right", 1000, 70, no_response=True)],
            "duplicate point": [_air("right", 1000, 40), _air("right", 1000, 60)],
            "bad ear": [{**_air("right", 1000, 40), "ear": "both"}],
            "bad conduction": [{**_air("right", 1000, 40), "conduction": "bc"}],
            "no points": [],
        }
        for name, points in invalid.items():
            with self.subTest(name):
                # A valid point alongside makes sure nothing is saved partially.
                extra = [] if name == "no points" else [_air("left", 500, 30)]
                response = self._post(self._body(points + extra))
                self.assertEqual(response.status_code, 400)
                self.assertNothingSaved()

    def test_no_points_message(self):
        response = self._post(self._body([]))
        self.assertIn("請至少標記一個點", json.dumps(response.json(), ensure_ascii=False))

    def test_date_required_and_not_future(self):
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        for tested_on, message in ((None, "請填寫檢查日期"), (tomorrow, "檢查日期不能是未來")):
            with self.subTest(tested_on=tested_on):
                response = self._post(self._body(tested_on=tested_on))
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, json.dumps(response.json(), ensure_ascii=False))
                self.assertNothingSaved()
        today = timezone.localdate().isoformat()
        self.assertEqual(self._post(self._body(tested_on=today)).status_code, 201)

    def test_detail_is_own_only(self):
        mine = self._post(self._body()).json()["id"]
        self.assertEqual(self.client.get(f"{self.URL}{mine}/").status_code, 200)
        other = Client()
        other.force_login(self.other)
        self.assertEqual(other.get(f"{self.URL}{mine}/").status_code, 404)

    def test_same_key_from_another_user_is_separate(self):
        key = str(uuid.uuid4())
        self._post(self._body(), key=key)
        self.client.force_login(self.other)
        response = self._post(self._body(), key=key)
        self.assertEqual(response.status_code, 201)
        Audiogram, _ = self._models()
        self.assertEqual(Audiogram.objects.filter(user=self.other).count(), 1)

    def test_anonymous_gets_403(self):
        self.client.logout()
        self.assertEqual(self._post(self._body()).status_code, 403)


class AudiogramPageTests(TestCase):
    """Spec docs/specs/phase5_audiogram.md, acceptance 12, 18-33 (pages)."""

    INPUT_JS = "screening/frontend/audiogram-input.js"
    VIEW_JS = "screening/frontend/audiogram-view.js"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="audiogram_page")
        cls.other = User.objects.create_user(username="audiogram_page_other")

    def setUp(self):
        self.client.force_login(self.user)

    def _make(self, points, tested_on=date(2026, 10, 1), user=None):
        from screening.models import Audiogram, AudiogramPoint

        audiogram = Audiogram.objects.create(user=user or self.user, tested_on=tested_on)
        AudiogramPoint.objects.bulk_create(AudiogramPoint(audiogram=audiogram, **p) for p in points)
        return audiogram

    def _main(self, response):
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _ear_card(self, response, ear):
        main = self._main(response)
        match = re.search(rf'<section[^>]*data-ear="{ear}"[^>]*>(.*?)</section>', main, re.DOTALL)
        return match.group(1)

    # 新增頁
    def test_new_page_loads_react(self):
        response = self.client.get(reverse("audiogram_new"))
        self.assertContains(response, self.INPUT_JS)
        self.assertContains(response, 'id="audiogram-app"')
        self.assertContains(response, f'data-today="{timezone.localdate().isoformat()}"')
        self.assertContains(response, "需要開啟 JavaScript")

    def test_input_js_only_on_new_page(self):
        for url in (reverse("index"), reverse("my_hearing"), reverse("audiogram_list")):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), self.INPUT_JS)

    # 檢視頁
    def test_detail_shows_interpretation(self):
        points = _four(_air, "right", (40, 45, 50, 55)) + _four(_bone, "right", (40, 45, 50, 55))
        audiogram = self._make(points)
        response = self.client.get(reverse("audiogram_detail", args=[audiogram.id]))
        self.assertContains(response, "2026/10/01")
        right = self._ear_card(response, "right")
        self.assertIn("47.5", right)
        self.assertIn("中度", right)
        self.assertIn("感音神經性", right)
        self.assertContains(response, "這是依固定規則算出的參考結果，不能取代聽力師的判讀。")
        self.assertNotContains(response, "診斷")
        self.assertContains(response, self.VIEW_JS)

    def test_detail_insufficient_and_missing_bone(self):
        points = [_air("right", f, 40) for f in (500, 1000, 4000)] + _four(_air, "left", (50,) * 4)
        response = self.client.get(reverse("audiogram_detail", args=[self._make(points).id]))
        self.assertIn("資料不足，無法判讀", self._ear_card(response, "right"))
        left = self._ear_card(response, "left")
        self.assertIn("中度", left)
        self.assertIn("需要骨導資料才能判斷", left)

    def test_detail_pta_formats(self):
        points = _four(_air, "right", (100,) * 4) + _four(_air, "left", (50,) * 4)
        points += [_bone("right", f, db) for f, db in ((500, 60), (1000, 70), (2000, 75))]
        points.append(_bone("right", 4000, 80, no_response=True))
        response = self.client.get(reverse("audiogram_detail", args=[self._make(points).id]))
        right = self._ear_card(response, "right")
        self.assertIn("混合性", right)
        self.assertIn("含無反應的頻率，實際聽力可能更差", right)
        left = self._ear_card(response, "left")
        self.assertRegex(left, r"\b50 dB HL")
        self.assertNotIn("50.0", left)
        self.assertNotIn("含無反應", left)

    def test_detail_air_no_response_note(self):
        # Acceptance 25 on the page (second review 3-2).
        points = [_air("right", f, db) for f, db in ((500, 90), (1000, 100), (2000, 110))]
        points.append(_air("right", 4000, 120, no_response=True))
        response = self.client.get(reverse("audiogram_detail", args=[self._make(points).id]))
        right = self._ear_card(response, "right")
        self.assertIn("四頻平均：105 dB HL", right)
        self.assertIn("極重度", right)
        self.assertIn("含無反應的頻率，實際聽力可能更差", right)

    def test_detail_table_lists_points(self):
        points = [
            _air("right", 1000, 0),
            _air("right", 2000, -10),
            _air("left", 4000, 120, no_response=True),
        ]
        response = self.client.get(reverse("audiogram_detail", args=[self._make(points).id]))
        self.assertContains(response, 'id="audiogram-points"')  # json_script for the chart
        main = self._main(response)
        self.assertIn("<table", main)
        # Whole cells: "120 dB" alone would also contain "0 dB" (review 3-1).
        self.assertIn("<td>0 dB</td>", main)
        self.assertIn("<td>-10 dB</td>", main)
        self.assertIn("<td>120 dB（無反應）</td>", main)

    def test_detail_shows_masking(self):
        # Acceptance 40.
        points = [
            {**_air("right", 1000, 50), "masked": True},
            {**_bone("left", 1000, 80, no_response=True), "masked": True},
        ]
        response = self.client.get(reverse("audiogram_detail", args=[self._make(points).id]))
        main = self._main(response)
        self.assertIn("<td>50 dB（遮蔽）</td>", main)
        self.assertIn("<td>80 dB（遮蔽、無反應）</td>", main)
        chart = json.loads(re.search(r'id="audiogram-points"[^>]*>(.*?)</script>', main).group(1))
        self.assertTrue(all(p["masked"] for p in chart))

    def test_only_outer_frequencies_render(self):
        points = [_air(ear, f, 40) for ear in ("right", "left") for f in (250, 8000)]
        response = self.client.get(reverse("audiogram_detail", args=[self._make(points).id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("資料不足，無法判讀", self._ear_card(response, "right"))
        self.assertIn("資料不足，無法判讀", self._ear_card(response, "left"))

    # 清單
    def test_list_newest_test_date_first(self):
        old = self._make(_four(_air, "right", (20,) * 4), tested_on=date(2026, 1, 1))
        new = self._make(_four(_air, "right", (50,) * 4), tested_on=date(2026, 9, 1))
        same_day_later = self._make(_four(_air, "right", (80,) * 4), tested_on=date(2026, 9, 1))
        main = self._main(self.client.get(reverse("audiogram_list")))
        links = re.findall(r'href="/audiograms/(\d+)"', main)
        self.assertEqual(links, [str(same_day_later.id), str(new.id), str(old.id)])
        self.assertIn("2026/09/01", main)
        self.assertIn("右耳：重度", main)
        self.assertIn("左耳：資料不足", main)

    def test_empty_list(self):
        main = self._main(self.client.get(reverse("audiogram_list")))
        self.assertIn("還沒有聽力圖", main)
        self.assertIn(f'href="{reverse("audiogram_new")}"', main)

    def test_list_queries_do_not_grow(self):
        self._make(_four(_air, "right", (40,) * 4))
        self._make(_four(_air, "left", (40,) * 4))
        with CaptureQueriesContext(connection) as two:
            self.client.get(reverse("audiogram_list"))
        for _ in range(18):
            self._make(_four(_air, "right", (40,) * 4) + _four(_bone, "right", (40,) * 4))
        with CaptureQueriesContext(connection) as twenty:
            self.client.get(reverse("audiogram_list"))
        self.assertEqual(len(twenty), len(two))

    # 權限
    def test_other_users_audiogram_is_404(self):
        theirs = self._make(_four(_air, "right", (40,) * 4), user=self.other)
        for name in ("audiogram_detail", "audiogram_delete"):
            with self.subTest(name=name):
                url = reverse(name, args=[theirs.id])
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url).status_code, 404)
        listing = self._main(self.client.get(reverse("audiogram_list")))
        self.assertNotIn(f"/audiograms/{theirs.id}", listing)
        from screening.models import Audiogram

        self.assertTrue(Audiogram.objects.filter(pk=theirs.pk).exists())

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        for url in (reverse("audiogram_list"), reverse("audiogram_new")):
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url),
                    f"{reverse('login')}?next={url}",
                    fetch_redirect_response=False,
                )

    # 刪除
    def test_delete_asks_first_then_deletes_with_points(self):
        from screening.models import Audiogram, AudiogramPoint

        audiogram = self._make(_four(_air, "right", (40,) * 4))
        url = reverse("audiogram_delete", args=[audiogram.id])
        response = self.client.get(url)
        self.assertContains(response, "確定要刪除 2026/10/01 的聽力圖嗎？")
        self.assertTrue(Audiogram.objects.filter(pk=audiogram.pk).exists())
        response = self.client.post(url)
        self.assertRedirects(response, reverse("audiogram_list"))
        self.assertFalse(Audiogram.objects.filter(pk=audiogram.pk).exists())
        self.assertEqual(AudiogramPoint.objects.count(), 0)

    def test_detail_links_to_delete(self):
        audiogram = self._make(_four(_air, "right", (40,) * 4))
        response = self.client.get(reverse("audiogram_detail", args=[audiogram.id]))
        self.assertContains(response, f'href="{reverse("audiogram_delete", args=[audiogram.id])}"')

    # 導覽列：聽力圖是獨立的一項，不在我的紀錄的分頁籤裡
    def test_nav_marks_every_audiogram_page(self):
        audiogram = self._make(_four(_air, "right", (40,) * 4))
        urls = (
            reverse("audiogram_list"),
            reverse("audiogram_new"),
            reverse("audiogram_detail", args=[audiogram.id]),
            reverse("audiogram_delete", args=[audiogram.id]),
        )
        for url in urls:
            with self.subTest(url=url):
                nav = RedesignLayoutTests.NAV.search(self.client.get(url).content.decode()).group()
                current = re.findall(r'aria-current="page">.*?<span>([^<]+)</span>', nav, re.DOTALL)
                self.assertEqual(current, ["聽力圖"])

    def test_not_a_my_hearing_tab(self):
        main = self._main(self.client.get(reverse("my_hearing")))
        self.assertNotIn(reverse("audiogram_list"), main)

    def test_bundle_entries_in_vite_config(self):
        config = ReactAnswerPageTests.VITE_CONFIG.read_text(encoding="utf-8")
        for entry in ('"audiogram-input"', '"audiogram-view"'):
            with self.subTest(entry=entry):
                self.assertIn(entry, config)


def _masked(point):
    return {**point, "masked": True}


class AudiogramCompareRuleTests(SimpleTestCase):
    """Spec docs/specs/phase5_audiogram_2.md 4.2, acceptance 13-17 (the rules alone)."""

    def _compare(self, new, old):
        from screening.audiogram import compare

        def objects(points):
            return [mock.Mock(**{"masked": False, **p}) for p in points]

        return compare(objects(new), objects(old))

    def _row(self, result, ear, conduction, frequency):
        rows = [r for r in result[ear][conduction] if r["frequency"] == frequency]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_difference_is_new_minus_old(self):
        result = self._compare([_air("right", 1000, 45)], [_air("right", 1000, 30)])
        row = self._row(result, "right", "air", 1000)
        self.assertEqual((row["old"].db, row["new"].db, row["diff"]), (30, 45, 15))
        self.assertIsNone(row["reason"])

    def test_zero_and_minus_ten_are_values(self):
        result = self._compare([_air("right", 1000, -10)], [_air("right", 1000, 0)])
        self.assertEqual(self._row(result, "right", "air", 1000)["diff"], -10)
        result = self._compare([_air("right", 1000, 0)], [_air("right", 1000, 0)])
        row = self._row(result, "right", "air", 1000)
        self.assertEqual(row["diff"], 0)
        self.assertIsNone(row["reason"])

    def test_only_one_side_has_a_value(self):
        result = self._compare([_air("right", 6000, 70)], [])
        row = self._row(result, "right", "air", 6000)
        self.assertIsNone(row["old"])
        self.assertIsNone(row["diff"])
        self.assertEqual(row["reason"], "missing")
        result = self._compare([], [_bone("right", 500, 20)])
        self.assertEqual(self._row(result, "right", "bone", 500)["reason"], "missing")

    def test_no_response_cannot_be_compared(self):
        result = self._compare(
            [_air("right", 8000, 120, no_response=True)], [_air("right", 8000, 60)]
        )
        row = self._row(result, "right", "air", 8000)
        self.assertIsNone(row["diff"])
        self.assertEqual(row["reason"], "no_response")
        # A missing side comes first: there is nothing on the other side to compare against.
        result = self._compare([_air("right", 8000, 120, no_response=True)], [])
        self.assertEqual(self._row(result, "right", "air", 8000)["reason"], "missing")

    def test_only_marked_frequencies_listed_in_order(self):
        result = self._compare(
            [_air("right", 4000, 50), _air("right", 500, 20)], [_air("right", 2000, 30)]
        )
        self.assertEqual([r["frequency"] for r in result["right"]["air"]], [500, 2000, 4000])
        self.assertEqual(result["right"]["bone"], [])
        self.assertEqual(result["left"]["air"], [])

    def test_pta_difference(self):
        result = self._compare(
            _four(_air, "right", (40, 45, 50, 55)), _four(_air, "right", (30,) * 4)
        )
        pta = result["right"]["pta"]
        self.assertEqual((pta["old"], pta["new"], pta["diff"]), (30, 47.5, 17.5))
        self.assertEqual((pta["old_degree"], pta["new_degree"]), ("輕度", "中度"))
        self.assertFalse(pta["no_response"])

    def test_pta_difference_needs_both(self):
        result = self._compare(_four(_air, "right", (40,) * 4), [_air("right", 500, 30)])
        pta = result["right"]["pta"]
        self.assertIsNone(pta["old"])
        self.assertEqual(pta["new"], 40)
        self.assertIsNone(pta["diff"])

    def test_pta_with_no_response_is_noted(self):
        new = [*_four(_air, "right", (90, 100, 110, 120))[:3], _air("right", 4000, 120, True)]
        result = self._compare(new, _four(_air, "right", (80,) * 4))
        pta = result["right"]["pta"]
        self.assertEqual(pta["diff"], 25)
        self.assertTrue(pta["no_response"])
        # Same as the detail page: no response outside the four frequencies is not noted.
        result = self._compare(
            [*_four(_air, "right", (40,) * 4), _air("right", 8000, 120, True)],
            _four(_air, "right", (40,) * 4),
        )
        self.assertFalse(result["right"]["pta"]["no_response"])

    def test_bone_no_response_is_not_noted(self):
        # Review 1(a): the difference uses air only, so bone's no response does not touch it.
        new = [
            *_four(_air, "right", (50,) * 4),
            *_four(_bone, "right", (20, 20, 20, 80))[:3],
            _bone("right", 4000, 80, True),
        ]
        result = self._compare(new, _four(_air, "right", (40,) * 4))
        self.assertEqual(result["right"]["pta"]["diff"], 10)
        self.assertFalse(result["right"]["pta"]["no_response"])

    def test_no_note_without_a_difference(self):
        # Review 1(b): no difference shown ("—"), so nothing to warn about.
        new = [_air("right", f, 120, True) for f in (500, 1000, 2000, 4000)]
        result = self._compare(new, [_air("right", 500, 40)])
        self.assertIsNone(result["right"]["pta"]["diff"])
        self.assertFalse(result["right"]["pta"]["no_response"])


class AudiogramEditApiTests(TestCase):
    """Spec docs/specs/phase5_audiogram_2.md 4.1, acceptance 2-4, 6, 7 (API side)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="audiogram_edit_api")
        cls.other = User.objects.create_user(username="audiogram_edit_other")

    def setUp(self):
        self.client.force_login(self.user)
        self.audiogram = self._make(self.user)

    def _make(self, user):
        from screening.models import Audiogram, AudiogramPoint

        audiogram = Audiogram.objects.create(user=user, tested_on=date(2026, 1, 10))
        points = [_masked(_air("right", 1000, 40)), _air("right", 2000, 120, no_response=True)]
        AudiogramPoint.objects.bulk_create(AudiogramPoint(audiogram=audiogram, **p) for p in points)
        return audiogram

    def _url(self, audiogram=None):
        return f"/api/audiograms/{(audiogram or self.audiogram).id}/"

    def _put(self, body, audiogram=None):
        return self.client.put(
            self._url(audiogram), json.dumps(body), content_type="application/json"
        )

    def _snapshot(self, audiogram=None):
        from screening.models import Audiogram

        fresh = Audiogram.objects.get(pk=(audiogram or self.audiogram).pk)
        fields = ("ear", "conduction", "frequency", "db", "no_response", "masked")
        return fresh.tested_on, sorted(fresh.points.values_list(*fields))

    def test_replaces_points_and_date(self):
        points = [
            _air("right", 500, 40),
            _masked(_air("right", 1000, 60)),
            _air("right", 2000, 50),
            _air("right", 4000, 55),
        ]
        body = {"tested_on": "2026-01-12", "points": points}
        response = self._put(body)
        self.assertEqual(response.status_code, 200)
        tested_on, points = self._snapshot()
        self.assertEqual(tested_on, date(2026, 1, 12))
        self.assertEqual(
            points,
            [
                ("right", "air", 500, 40, False, False),
                ("right", "air", 1000, 60, False, True),
                ("right", "air", 2000, 50, False, False),
                ("right", "air", 4000, 55, False, False),
            ],
        )
        self.assertEqual(response.json()["interpretation"]["right"]["pta"], 51.25)
        self.assertEqual(response.json()["tested_on"], "2026-01-12")

    def test_invalid_leaves_everything_unchanged(self):
        before = self._snapshot()
        future = (timezone.localdate() + timedelta(days=1)).isoformat()
        cases = {
            "future": {"tested_on": future, "points": [_air("right", 500, 40)]},
            "no date": {"points": [_air("right", 500, 40)]},
            "no points": {"tested_on": "2026-01-12", "points": []},
            "bad frequency": {"tested_on": "2026-01-12", "points": [_air("right", 750, 40)]},
            "bad step": {"tested_on": "2026-01-12", "points": [_air("right", 500, 42)]},
            "bone too loud": {"tested_on": "2026-01-12", "points": [_bone("right", 500, 85)]},
            "bone at 3000": {"tested_on": "2026-01-12", "points": [_bone("right", 3000, 40)]},
            "no response not at max": {
                "tested_on": "2026-01-12",
                "points": [_air("right", 500, 100, no_response=True)],
            },
            "duplicate": {
                "tested_on": "2026-01-12",
                "points": [_air("right", 500, 40), _air("right", 500, 50)],
            },
            "masked not boolean": {
                "tested_on": "2026-01-12",
                "points": [{**_air("right", 500, 40), "masked": "yes"}],
            },
        }
        for name, body in cases.items():
            with self.subTest(name):
                self.assertEqual(self._put(body).status_code, 400)
                self.assertEqual(self._snapshot(), before)

    def test_failure_while_saving_rolls_back(self):
        from screening.models import AudiogramPoint

        before = self._snapshot()
        body = {"tested_on": "2026-01-12", "points": [_air("right", 500, 40)]}
        with (
            mock.patch.object(AudiogramPoint.objects, "bulk_create", side_effect=DatabaseError),
            self.assertRaises(DatabaseError),
        ):
            self._put(body)
        self.assertEqual(self._snapshot(), before)

    def test_someone_elses_is_404_and_unchanged(self):
        theirs = self._make(self.other)
        before = self._snapshot(theirs)
        body = {"tested_on": "2026-01-12", "points": [_air("right", 500, 40)]}
        self.assertEqual(self._put(body, theirs).status_code, 404)
        self.assertEqual(self._snapshot(theirs), before)

    def test_putting_twice_gives_the_same_result(self):
        body = {
            "tested_on": "2026-01-12",
            "points": [_air("right", 500, 40), _air("left", 500, 50)],
        }
        self.assertEqual(self._put(body).status_code, 200)
        once = self._snapshot()
        self.assertEqual(self._put(body).status_code, 200)
        self.assertEqual(self._snapshot(), once)
        self.assertEqual(len(once[1]), 2)

    def test_no_partial_update(self):
        response = self.client.patch(
            self._url(), json.dumps({"tested_on": "2026-01-12"}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 405)

    def test_anonymous_cannot_edit(self):
        self.client.logout()
        before = self._snapshot()
        body = {"tested_on": "2026-01-12", "points": [_air("right", 500, 40)]}
        self.assertIn(self._put(body).status_code, (401, 403))
        self.assertEqual(self._snapshot(), before)


class AudiogramEditPageTests(TestCase):
    """Spec docs/specs/phase5_audiogram_2.md 4.1, acceptance 1, 2, 4, 5, 8 (pages)."""

    INPUT_JS = AudiogramPageTests.INPUT_JS

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="audiogram_edit_page")
        cls.other = User.objects.create_user(username="audiogram_edit_page_other")

    def setUp(self):
        self.client.force_login(self.user)

    # Borrow the batch-1 helpers without inheriting (and rerunning) its tests.
    _make = AudiogramPageTests._make
    _main = AudiogramPageTests._main
    _ear_card = AudiogramPageTests._ear_card

    def _initial(self, response):
        match = re.search(
            r'<script id="audiogram-initial" type="application/json">(.*?)</script>',
            response.content.decode(),
            re.DOTALL,
        )
        return json.loads(match.group(1))

    def test_edit_page_prefills(self):
        audiogram = self._make(
            [_masked(_air("right", 1000, 40)), _air("right", 2000, 120, True)],
            tested_on=date(2026, 1, 10),
        )
        response = self.client.get(reverse("audiogram_edit", args=[audiogram.id]))
        self.assertContains(response, "修改聽力圖")
        self.assertContains(response, self.INPUT_JS)
        self.assertContains(response, f'data-audiogram-id="{audiogram.id}"')
        initial = self._initial(response)
        self.assertEqual(initial["tested_on"], "2026-01-10")
        self.assertCountEqual(
            initial["points"],
            [
                {
                    "ear": "right",
                    "conduction": "air",
                    "frequency": 1000,
                    "db": 40,
                    "no_response": False,
                    "masked": True,
                },
                {
                    "ear": "right",
                    "conduction": "air",
                    "frequency": 2000,
                    "db": 120,
                    "no_response": True,
                    "masked": False,
                },
            ],
        )

    def test_new_page_has_no_initial_data(self):
        response = self.client.get(reverse("audiogram_new"))
        self.assertContains(response, "新增聽力圖")
        self.assertNotContains(response, "audiogram-initial")
        self.assertNotContains(response, "data-audiogram-id")

    def test_detail_links_to_edit(self):
        audiogram = self._make(_four(_air, "right", (40,) * 4))
        response = self.client.get(reverse("audiogram_detail", args=[audiogram.id]))
        self.assertContains(response, f'href="{reverse("audiogram_edit", args=[audiogram.id])}"')

    def test_someone_elses_edit_page_is_404(self):
        theirs = self._make(_four(_air, "right", (40,) * 4), user=self.other)
        self.assertEqual(
            self.client.get(reverse("audiogram_edit", args=[theirs.id])).status_code, 404
        )

    def test_anonymous_edit_page_redirects_to_login(self):
        audiogram = self._make(_four(_air, "right", (40,) * 4))
        self.client.logout()
        url = reverse("audiogram_edit", args=[audiogram.id])
        self.assertRedirects(
            self.client.get(url), f"{reverse('login')}?next={url}", fetch_redirect_response=False
        )

    def test_edit_page_marks_nav(self):
        audiogram = self._make(_four(_air, "right", (40,) * 4))
        nav = RedesignLayoutTests.NAV.search(
            self.client.get(reverse("audiogram_edit", args=[audiogram.id])).content.decode()
        ).group()
        current = re.findall(r'aria-current="page">.*?<span>([^<]+)</span>', nav, re.DOTALL)
        self.assertEqual(current, ["聽力圖"])

    def test_after_edit_detail_and_list_follow(self):
        first = self._make(_four(_air, "right", (40,) * 4), tested_on=date(2026, 1, 10))
        second = self._make(_four(_air, "right", (40,) * 4), tested_on=date(2026, 5, 1))
        body = {"tested_on": "2026-09-10", "points": _four(_air, "right", (60,) * 4)}
        response = self.client.put(
            f"/api/audiograms/{first.id}/", json.dumps(body), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        detail = self.client.get(reverse("audiogram_detail", args=[first.id]))
        self.assertContains(detail, "2026/09/10")
        self.assertIn("中重度", self._ear_card(detail, "right"))
        listing = self._main(self.client.get(reverse("audiogram_list")))
        self.assertLess(
            listing.index(f'/audiograms/{first.id}"'), listing.index(f'/audiograms/{second.id}"')
        )


class AudiogramComparePageTests(TestCase):
    """Spec docs/specs/phase5_audiogram_2.md 4.2, acceptance 9-22 (page)."""

    @property
    def URL(self):
        return reverse("audiogram_compare")

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="audiogram_compare")
        cls.other = User.objects.create_user(username="audiogram_compare_other")

    def setUp(self):
        self.client.force_login(self.user)

    _make = AudiogramPageTests._make
    _main = AudiogramPageTests._main

    def _three(self):
        return (
            self._make(_four(_air, "right", (30,) * 4), tested_on=date(2026, 1, 10)),
            self._make(_four(_air, "right", (35,) * 4), tested_on=date(2026, 5, 1)),
            self._make(_four(_air, "right", (40,) * 4), tested_on=date(2026, 9, 10)),
        )

    def _get(self, **params):
        return self.client.get(self.URL, params)

    def _row(self, response, section, key):
        main = self._main(response)
        table = re.search(
            rf'<table[^>]*data-section="{section}"[^>]*>(.*?)</table>', main, re.DOTALL
        )
        self.assertIsNotNone(table, section)
        row = re.search(rf'<tr data-row="{key}">(.*?)</tr>', table.group(1), re.DOTALL)
        self.assertIsNotNone(row, key)
        return [
            re.sub(r"<[^>]+>", "", cell).strip()
            for cell in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row.group(1), re.DOTALL)
        ]

    def _chart(self, response, name):
        match = re.search(
            rf'<script id="{name}" type="application/json">(.*?)</script>',
            response.content.decode(),
            re.DOTALL,
        )
        return json.loads(match.group(1))

    def _legend(self, response):
        return re.search(
            r'<p class="[^"]*compare-legend[^"]*">(.*?)</p>', self._main(response), re.DOTALL
        ).group(1)

    # 清單頁的入口
    def test_list_button_needs_two(self):
        self._make(_four(_air, "right", (30,) * 4))
        main = self._main(self.client.get(reverse("audiogram_list")))
        self.assertIn("要有兩張聽力圖才能比較", main)
        self.assertNotIn(f'href="{self.URL}"', main)
        self.assertRegex(main, r"<button[^>]*disabled[^>]*>比較聽力圖</button>")
        self._make(_four(_air, "right", (30,) * 4))
        main = self._main(self.client.get(reverse("audiogram_list")))
        self.assertIn(f'href="{self.URL}"', main)
        self.assertNotIn("要有兩張聽力圖才能比較", main)

    def test_compare_page_with_fewer_than_two(self):
        self._make(_four(_air, "right", (30,) * 4))
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "要有兩張聽力圖才能比較")
        self.assertNotContains(response, 'data-section="pta"')

    # 選哪兩張
    def test_defaults_to_latest_two(self):
        _, middle, latest = self._three()
        response = self._get()
        self.assertEqual(self._legend(response).count("2026/09/10"), 1)
        legend = self._legend(response)
        self.assertLess(legend.index("2026/09/10"), legend.index("2026/05/01"))
        self.assertNotIn("2026/01/10", legend)
        self.assertEqual(self._row(response, "pta", "pta")[1:3], ["35 dB（輕度）", "40 dB（輕度）"])
        main = self._main(response)
        self.assertRegex(main, rf'<option value="{latest.id}" selected>')
        self.assertRegex(main, rf'<option value="{middle.id}" selected>')

    def test_new_and_old_follow_dates_not_selects(self):
        oldest, _, latest = self._three()
        for a, b in ((oldest, latest), (latest, oldest)):
            with self.subTest(a=a.tested_on):
                response = self._get(a=a.id, b=b.id)
                # Header: old date first, then new.
                header = self._row(response, "pta", "head")
                self.assertEqual(header[1:3], ["2026/01/10", "2026/09/10"])
                self.assertEqual(self._row(response, "pta", "pta")[3], "+10")
                self.assertEqual(self._chart(response, "audiogram-points")[0]["db"], 40)
                self.assertEqual(self._chart(response, "audiogram-old-points")[0]["db"], 30)

    def test_same_day_later_saved_is_new(self):
        first = self._make(_four(_air, "right", (30,) * 4), tested_on=date(2026, 5, 1))
        second = self._make(_four(_air, "right", (50,) * 4), tested_on=date(2026, 5, 1))
        response = self._get(a=first.id, b=second.id)
        self.assertEqual(self._row(response, "pta", "pta")[3], "+20")

    def test_same_audiogram_twice(self):
        _, _, latest = self._three()
        response = self._get(a=latest.id, b=latest.id)
        self.assertContains(response, "請選兩張不同的聽力圖")
        self.assertNotContains(response, 'data-section="pta"')
        self.assertNotContains(response, 'id="audiogram-points"')

    # 對照表
    def test_table_values(self):
        old = self._make(
            [
                *_four(_air, "right", (30,) * 4),
                _air("right", 8000, 60),
                _masked(_bone("right", 1000, 20)),
            ],
            tested_on=date(2026, 5, 1),
        )
        new = self._make(
            [
                _air("right", 500, 30),
                _air("right", 1000, 45),
                _air("right", 2000, 50),
                _air("right", 4000, 65),
                _air("right", 6000, 70),
                _air("right", 8000, 120, True),
                _masked(_bone("right", 1000, 25)),
            ],
            tested_on=date(2026, 9, 10),
        )
        response = self._get(a=new.id, b=old.id)
        self.assertEqual(self._row(response, "air", "1000"), ["1000 Hz", "30 dB", "45 dB", "+15"])
        self.assertEqual(self._row(response, "air", "6000"), ["6000 Hz", "", "70 dB", "—"])
        self.assertEqual(
            self._row(response, "air", "8000"), ["8000 Hz", "60 dB", "120 dB（無反應）", "無法比較"]
        )
        self.assertEqual(
            self._row(response, "bone", "1000"), ["1000 Hz", "20 dB（遮蔽）", "25 dB（遮蔽）", "+5"]
        )
        self.assertEqual(
            self._row(response, "pta", "pta"),
            ["四頻平均", "30 dB（輕度）", "47.5 dB（中度）", "+17.5"],
        )
        main = self._main(response)
        self.assertIn("差值＝新 − 舊，正數＝要更大聲才聽得到", main)  # noqa: RUF001
        self.assertIn("兩次檢查的條件（機器、地點、耳機）不同，數字也會有幾 dB 的差異。", main)
        self.assertIn("這只是數字的對照，不能取代聽力師的判讀。", main)

    def test_zero_minus_and_equal(self):
        old = self._make(
            [_air("right", 500, 0), _air("right", 1000, 20)], tested_on=date(2026, 5, 1)
        )
        new = self._make(
            [_air("right", 500, -10), _air("right", 1000, 20)], tested_on=date(2026, 9, 1)
        )
        response = self._get(a=new.id, b=old.id)
        self.assertEqual(self._row(response, "air", "500")[1:], ["0 dB", "-10 dB", "-10"])
        self.assertEqual(self._row(response, "air", "1000")[3], "0")
        self.assertEqual(self._row(response, "pta", "pta")[1:], ["資料不足", "資料不足", "—"])

    def test_pta_no_response_note(self):
        old = self._make(_four(_air, "right", (80,) * 4), tested_on=date(2026, 5, 1))
        new = self._make(
            [*_four(_air, "right", (90, 100, 110, 0))[:3], _air("right", 4000, 120, True)],
            tested_on=date(2026, 9, 1),
        )
        response = self._get(a=new.id, b=old.id)
        self.assertEqual(self._row(response, "pta", "pta")[3], "+25")
        self.assertContains(response, "含無反應的頻率，實際差距可能不同")
        plain = self._get(a=old.id, b=self._make(_four(_air, "right", (70,) * 4)).id)
        self.assertNotContains(plain, "含無反應的頻率，實際差距可能不同")

    def test_no_judgement_words_or_colours(self):
        old = self._make(_four(_air, "right", (20,) * 4), tested_on=date(2026, 1, 1))
        new = self._make(_four(_air, "right", (50,) * 4), tested_on=date(2026, 9, 1))
        main = self._main(self._get(a=new.id, b=old.id))
        for word in ("變差", "進步", "惡化", "改善", "診斷"):
            with self.subTest(word=word):
                self.assertNotIn(word, main)
        tables = "".join(re.findall(r"<table.*?</table>", main, re.DOTALL))
        self.assertNotRegex(tables, r"(text|bg|table)-(danger|success|warning)")
        self.assertNotIn("style=", tables)

    # 左右耳
    def test_ear_switch(self):
        old = self._make(
            [*_four(_air, "right", (30,) * 4), *_four(_air, "left", (60,) * 4)],
            tested_on=date(2026, 1, 1),
        )
        new = self._make(
            [*_four(_air, "right", (40,) * 4), *_four(_air, "left", (65,) * 4)],
            tested_on=date(2026, 9, 1),
        )
        right = self._get(a=new.id, b=old.id)
        self.assertEqual(self._row(right, "pta", "pta")[3], "+10")
        self.assertEqual({p["ear"] for p in self._chart(right, "audiogram-points")}, {"right"})
        main = self._main(right)
        self.assertRegex(main, r'<a[^>]*aria-current="true"[^>]*>右耳</a>')
        left_link = (
            re.search(r'<a[^>]*href="([^"]+)"[^>]*>左耳</a>', main).group(1).replace("&amp;", "&")
        )
        left = self.client.get(self.URL + left_link)
        self.assertEqual(self._row(left, "pta", "pta")[3], "+5")
        self.assertEqual({p["ear"] for p in self._chart(left, "audiogram-points")}, {"left"})
        self.assertEqual({p["ear"] for p in self._chart(left, "audiogram-old-points")}, {"left"})
        self.assertRegex(self._main(left), r'<a[^>]*aria-current="true"[^>]*>左耳</a>')
        # Unknown ear falls back to the right ear.
        self.assertEqual(self._row(self._get(a=new.id, b=old.id, ear="x"), "pta", "pta")[3], "+10")

    def test_bone_in_chart_and_table(self):
        old = self._make(_four(_bone, "right", (20,) * 4), tested_on=date(2026, 1, 1))
        new = self._make(_four(_bone, "right", (30,) * 4), tested_on=date(2026, 9, 1))
        response = self._get(a=new.id, b=old.id)
        self.assertEqual(self._row(response, "bone", "500")[1:], ["20 dB", "30 dB", "+10"])
        self.assertEqual(len(self._chart(response, "audiogram-old-points")), 4)
        legend = self._legend(response)
        self.assertIn("2026/09/01", legend)
        self.assertIn("2026/01/01", legend)
        self.assertContains(response, AudiogramPageTests.VIEW_JS)

    # 權限
    def test_someone_elses_audiogram_is_404(self):
        _, _, latest = self._three()
        theirs = self._make(_four(_air, "right", (30,) * 4), user=self.other)
        for params in ({"a": latest.id, "b": theirs.id}, {"a": theirs.id, "b": latest.id}):
            with self.subTest(params=params):
                self.assertEqual(self._get(**params).status_code, 404)
        main = self._main(self._get())
        self.assertNotIn(f'value="{theirs.id}"', main)

    def test_bad_ids_are_404(self):
        _, _, latest = self._three()
        for params in ({"a": latest.id, "b": 999999}, {"a": "x", "b": latest.id}, {"a": latest.id}):
            with self.subTest(params=params):
                self.assertEqual(self._get(**params).status_code, 404)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        self.assertRedirects(
            self.client.get(self.URL),
            f"{reverse('login')}?next={self.URL}",
            fetch_redirect_response=False,
        )

    def test_nav_marks_compare_page(self):
        nav = RedesignLayoutTests.NAV.search(self._get().content.decode()).group()
        current = re.findall(r'aria-current="page">.*?<span>([^<]+)</span>', nav, re.DOTALL)
        self.assertEqual(current, ["聽力圖"])

    def test_query_count_does_not_grow(self):
        def queries():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self._get().status_code, 200)
            return len(ctx)

        from screening.models import Audiogram

        for _ in range(2):
            self._make([_air("right", 500, 30)])
        few = queries()
        Audiogram.objects.all().delete()
        for _ in range(20):
            self._make([*_four(_air, "right", (30,) * 4), *_four(_bone, "left", (20,) * 4)])
        self.assertEqual(queries(), few)
