from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission, User
from screening.tests.helpers import consented_user


class ModelsUniqueConstraintTests(TestCase):
    def setUp(self):
        self.user_a = consented_user(username="user_a")
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


class AdminViewOnlyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(username="admin", password="pw")
        cls.user = consented_user(username="user")
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

    def _assert_view_only(self, model, obj, data):
        changelist = reverse(f"admin:screening_{model}_changelist")
        change = reverse(f"admin:screening_{model}_change", args=[obj.pk])
        self.assertEqual(self.client.get(changelist).status_code, 200)
        self.assertEqual(self.client.get(change).status_code, 200)
        add = reverse(f"admin:screening_{model}_add")
        self.assertEqual(self.client.get(add).status_code, 403)
        self.assertEqual(self.client.post(add, data).status_code, 403)
        self.assertEqual(self.client.post(change, data).status_code, 403)
        delete = reverse(f"admin:screening_{model}_delete", args=[obj.pk])
        self.assertEqual(self.client.post(delete, {"post": "yes"}).status_code, 403)

    def test_questions_are_view_only_answered_or_not(self):
        # Issue #103: questions come from questionnaire definitions, never from the admin.
        for question in (self.answered, self.fresh):
            with self.subTest(question=question.questionnaire.code):
                self._assert_view_only(
                    "question",
                    question,
                    {
                        "questionnaire": self.fresh_q.pk,
                        "question_text": "改過的題目",
                        "question_number": 2,
                        "category": Category.SOCIAL,
                    },
                )
                saved = Question.objects.get(pk=question.pk)
                self.assertEqual(saved.question_text, "原本的題目")
                self.assertEqual(saved.category, Category.EMOTIONAL)
                self.assertEqual(saved.question_number, 1)
                self.assertEqual(saved.questionnaire_id, question.questionnaire_id)
        self.assertEqual(Question.objects.count(), 2)

    def test_questionnaires_are_view_only_answered_or_not(self):
        for questionnaire in (self.answered_q, self.fresh_q):
            with self.subTest(questionnaire=questionnaire.code):
                self._assert_view_only(
                    "questionnaire",
                    questionnaire,
                    {"questionnaire_name": "改過的問卷", "code": "changed"},
                )
                saved = Questionnaire.objects.get(pk=questionnaire.pk)
                self.assertEqual(saved.code, questionnaire.code)
                self.assertEqual(saved.questionnaire_name, questionnaire.questionnaire_name)
        self.assertEqual(Questionnaire.objects.count(), 2)

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
