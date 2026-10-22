"""seed_questionnaires builds questionnaires from their definitions, issue #103."""

import hashlib
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from screening.models import Questionnaire

# sha256 of repr(list of (question_number, category, question_text)), taken from what
# seed_hhia_s and seed_ssq12 created before #103: the wording must not change by a character.
SEEDED = {
    "hhia-s": (
        "HHIA-S",
        10,
        "54b6ad3cee92f138abea412e5133c96352c0c8405c549981d7bd94698e1941f5",
    ),
    "ssq12-tw": (
        "SSQ12-TW",
        12,
        "c53b9a53c0836c8d8316ec99c823144a09026e083266426d41b0c0c832ae069e",
    ),
}


def _questions(questionnaire):
    return list(
        questionnaire.questions.order_by("question_number").values_list(
            "pk", "question_number", "category", "question_text"
        )
    )


def _seed():
    call_command("seed_questionnaires", stdout=StringIO())


class SeedQuestionnairesTests(TestCase):
    def test_empty_database_gets_the_same_questions_as_the_old_seeds(self):
        _seed()
        for code, (name, count, digest) in SEEDED.items():
            with self.subTest(code=code):
                questionnaire = Questionnaire.objects.get(code=code)
                self.assertEqual(questionnaire.questionnaire_name, name)
                rows = [row[1:] for row in _questions(questionnaire)]
                self.assertEqual(len(rows), count)
                self.assertEqual(hashlib.sha256(repr(rows).encode()).hexdigest(), digest)
        hhia_s = Questionnaire.objects.get(code="hhia-s")
        self.assertEqual(
            hhia_s.questions.get(question_number=3).question_text,
            "聽力問題會讓你看電影或戲劇表演時感到困難嗎？",
        )
        self.assertEqual(hhia_s.questions.get(question_number=3).category, "social")

    def test_rerun_leaves_every_questionnaire_as_it_was(self):
        call_command("loaddata", "questions_fixture.json", verbosity=0)
        _seed()
        # An already published version that differs from its definition must stay as it is.
        ssq12 = Questionnaire.objects.get(code="ssq12-tw")
        ssq12.questions.filter(question_number=1).update(question_text="已上線的舊文字")
        before = {
            questionnaire.code: (questionnaire.pk, questionnaire.questionnaire_name)
            for questionnaire in Questionnaire.objects.all()
        }
        questions = {
            questionnaire.code: _questions(questionnaire)
            for questionnaire in Questionnaire.objects.all()
        }

        _seed()

        self.assertEqual(sorted(before), ["hhia-s", "hhie-s", "ioi-ha", "sadl", "ssq12-tw", "thi"])
        after = {
            questionnaire.code: (questionnaire.pk, questionnaire.questionnaire_name)
            for questionnaire in Questionnaire.objects.all()
        }
        self.assertEqual(after, before)
        for questionnaire in Questionnaire.objects.all():
            with self.subTest(code=questionnaire.code):
                self.assertEqual(_questions(questionnaire), questions[questionnaire.code])
        self.assertEqual(
            Questionnaire.objects.get(code="ssq12-tw")
            .questions.get(question_number=1)
            .question_text,
            "已上線的舊文字",
        )
