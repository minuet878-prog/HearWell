from django.db import IntegrityError, connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission, User
from screening.scoring import classify


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
            '<input type="radio" name="form-0-score" value="4" class="score-radio-group"'
            ' id="id_form-0-score_0" checked>',
            html=True,
        )

    def test_hearing_aid_choice_kept_when_answer_missing(self):
        response = self._post(**{"form-0-score": "", "wearing_hearing_aid": "False"})
        self.assertFalse(Submission.objects.exists())
        self.assertContains(
            response,
            '<input type="radio" name="wearing_hearing_aid" value="False" required'
            ' id="id_wearing_hearing_aid_1" checked>',
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
