import re
from datetime import date
from io import StringIO
from pathlib import Path
from typing import ClassVar

from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

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
        self.assertContains(response, "text-secondary")
        self.assertContains(response, "這次的作答結果無法判讀分級")

    def test_history_page_survives_unknown_submission(self):
        self._make_submission(self.hhie_s, score=4)
        self._make_submission(self.hhia_s, score=4)
        self.client.force_login(self.user)
        with self.assertLogs("screening.scoring", "ERROR") as logs:
            response = self.client.get(reverse("my_hearing"))
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "無/極輕微影響")
        self.assertContains(response, "無法判讀")

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
        self.assertContains(history, "總分:26")
        self.assertContains(history, "顯著影響")
        self.assertContains(result, "總分: 26")
        self.assertContains(result, "情緒分數: 20")
        self.assertContains(result, "社交分數: 6")
        self.assertContains(result, "顯著影響")

    def test_submission_without_answers_scores_zero(self):
        self._make_submission(self.user, [])
        self.client.force_login(self.user)
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, "總分:0")
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
        self.assertLess(content.index("社交分數"), content.index(self.NOTE))
        self.assertLess(content.index(self.NOTE), content.index("建議"))

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
        self.assertContains(
            response, f'<p class="fs-4 text-body-emphasis text-center">{self.NOTE}</p>', html=True
        )


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
            response, '<p class="fs-4 text-body-emphasis text-center">助聽器：有戴</p>', html=True
        )


class LoginNextTests(TestCase):
    NOTE = "請先登入，沒有帳號請按註冊。登入後會帶您回到剛剛的頁面。"
    HINT = "首次使用請先註冊，已有帳號請登入"
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
            f'<p class="fs-5 text-body-emphasis">{self.NOTE}</p>',
            html=True,
        )
        self.assertContains(
            self.client.get(reverse("index")),
            f'<p class="fs-5 text-body-emphasis mt-2">{self.HINT}</p>',
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
        self.assertContains(self.client.get(self.url), f"1. {self.LONG_QUESTION}")

    def test_question_text_full_after_validation_error(self):
        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-0-score": "4",
            "form-0-question_id": str(self.question.id),
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"1. {self.LONG_QUESTION}")

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
        self.assertContains(response, "尚未登入")
        for english in ("Signed in", "Not signed in"):
            self.assertNotContains(response, english)

    def test_history_button_label(self):
        submission = Submission.objects.create(user=self.user, questionnaire=self.questionnaire)
        result_url = reverse("result", args=[submission.id])
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(
            response,
            f'<a class="btn btn-primary mb-2 ms-2" href="{result_url}">查看結果</a>',
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
            f'<div id="id_roc_birth_year_helptext" class="fs-5 text-body-emphasis mt-1">'
            f"{self.NOTE}</div>",
            html=True,
        )

    def test_password_rules_use_rem_size(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, "form-text")
        self.assertContains(
            response, 'id="id_password1_helptext" class="fs-5 text-body-emphasis mt-1"'
        )

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
        for legend in (self.PROMPT, "1. 第1題", "2. 第2題"):
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
                {"id": first.id, "code": "zz", "name": "ZZ 問卷"},
                {"id": second.id, "code": "aa", "name": "AA 問卷"},
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
