from django.core.management.base import BaseCommand
from django.db import transaction

from screening.models import Question, Questionnaire
from screening.questionnaires import DEFINITIONS


class Command(BaseCommand):
    help = (
        "Create each questionnaire whose definition carries its questions, once; "
        "existing questionnaires are left unchanged."
    )

    def handle(self, *args, **options):
        for definition in DEFINITIONS.values():
            if definition.questions:
                self._seed(definition)

    @transaction.atomic
    def _seed(self, definition):
        # Never assigns ids, so fixture-loaded questions (HHIE-S, IOI-HA) are not overwritten.
        questionnaire, created = Questionnaire.objects.get_or_create(
            code=definition.code, defaults={"questionnaire_name": definition.name}
        )
        if created:
            Question.objects.bulk_create(
                Question(
                    questionnaire=questionnaire,
                    question_number=number,
                    category=category,
                    question_text=text,
                )
                for number, (category, text) in enumerate(definition.questions, start=1)
            )
        state = "created." if created else "already exists; unchanged."
        self.stdout.write(f"{definition.name} {state}")
