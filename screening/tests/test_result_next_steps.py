"""Spec #148 batch 2, ticket #157: result page next steps by level."""

from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.questionnaires import hhia_s, hhie_s
from screening.scoring import get_advice
from screening.tests.helpers import consented_user, fake_definition, register


class ResultNextStepsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="next_steps_user")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")
        for questionnaire in (cls.hhie_s, cls.hhia_s):
            Question.objects.bulk_create(
                Question(
                    questionnaire=questionnaire,
                    question_text=f"第{i}題",
                    question_number=i,
                    category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
                )
                for i in range(1, 11)
            )
        cls.unknown = Questionnaire.objects.create(
            questionnaire_name="未設定門檻問卷", code="unconfigured"
        )
        cls.unknown_question = Question.objects.create(
            questionnaire=cls.unknown, question_text="第一題", question_number=1
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.enterContext(register(fake_definition("unconfigured")))

    def _submit(self, questionnaire, total):
        scores = [4] * (total // 4) + [2] * (total % 4 // 2)
        scores += [0] * (10 - len(scores))
        submission = Submission.objects.create(user=self.user, questionnaire=questionnaire)
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(questionnaire.questions.all(), scores, strict=True)
        )
        return submission

    def _get(self, submission):
        return self.client.get(reverse("result", args=[submission.id])).content.decode()

    def test_each_level_shows_its_finalized_steps_and_action_buttons(self):
        for definition_module, questionnaire in (
            (hhie_s, self.hhie_s),
            (hhia_s, self.hhia_s),
        ):
            for total, level in ((4, "normal"), (16, "mild_to_moderate"), (32, "severe")):
                with self.subTest(questionnaire=questionnaire.code, level=level):
                    page = self._get(self._submit(questionnaire, total))
                    for step in definition_module.NEXT_STEPS[level]:
                        self.assertIn(step["text"], page)
                        if step.get("action_label"):
                            self.assertIn(
                                f'href="{reverse(step["action_url"])}">{step["action_label"]}</a>',
                                page,
                            )

    def test_full_advice_is_unchanged(self):
        submission = self._submit(self.hhie_s, 16)
        page = self._get(submission)
        self.assertIn(get_advice("mild_to_moderate"), page)

    def test_no_step_list_when_unclassifiable(self):
        submission = Submission.objects.create(user=self.user, questionnaire=self.unknown)
        Answer.objects.create(submission=submission, question=self.unknown_question, score=4)
        with self.assertLogs("screening.scoring", "ERROR"):
            page = self._get(submission)
        self.assertNotIn("接下來建議您", page)
        self.assertIn("這次的作答結果無法判讀分級", page)

    def test_only_own_submission_is_visible(self):
        other = consented_user(username="someone_else")
        submission = Submission.objects.create(user=other, questionnaire=self.hhie_s)
        Answer.objects.create(
            submission=submission, question=self.hhie_s.questions.first(), score=4
        )
        response = self.client.get(reverse("result", args=[submission.id]))
        self.assertEqual(response.status_code, 404)
