from django.core.management.base import BaseCommand
from django.db import transaction

from screening.models import Question, Questionnaire
from screening.questionnaires.ssq12_tw import CODE
from screening.ssq12 import QUESTIONS


class Command(BaseCommand):
    help = "Create the reviewed SSQ12-TW version once without changing existing versions."

    @transaction.atomic
    def handle(self, *args, **options):
        questionnaire, created = Questionnaire.objects.get_or_create(
            code=CODE, defaults={"questionnaire_name": "SSQ12-TW"}
        )
        if created:
            Question.objects.bulk_create(
                Question(
                    questionnaire=questionnaire,
                    question_number=number,
                    question_text=text,
                    category="",
                )
                for number, text in enumerate(QUESTIONS, start=1)
            )
        self.stdout.write("SSQ12-TW created." if created else "SSQ12-TW already exists; unchanged.")
