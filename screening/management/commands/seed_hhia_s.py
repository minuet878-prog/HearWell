from django.core.management.base import BaseCommand
from django.db import transaction

from screening.models import Question, Questionnaire

# 林克寰《助聽器選配與驗證》書內 p.165 (PDF p.166), reviewed for issue #78.
# A published version is immutable: later wording changes need a new code.
QUESTIONS = (
    ("emotional", "認識新朋友時，聽力問題使你不好意思嗎？"),
    ("emotional", "當你與家人談話時，聽力問題會讓你感到挫折嗎？"),
    ("social", "聽力問題會讓你看電影或戲劇表演時感到困難嗎？"),
    ("emotional", "你覺得聽力問題會讓你有障礙嗎？"),
    ("social", "拜訪親朋好友或鄰居時，聽力問題會讓你感到困難嗎？"),
    ("social", "聽力問題會讓你與同事或客戶溝通的聽理解有困難嗎？"),
    ("emotional", "聽力問題讓你和家人相處時產生爭執嗎？"),
    ("social", "當你在看電視或聽收音機時，聽力問題會讓你感到困難嗎？"),
    ("emotional", "你覺得聽力問題會限制你的個人生活或社交生活嗎？"),
    ("social", "和親友在餐館吃飯時，聽力問題會讓你感到困難嗎？"),
)


class Command(BaseCommand):
    help = "Create the reviewed HHIA-S version once, without changing published questionnaires."

    @transaction.atomic
    def handle(self, *args, **options):
        questionnaire, created = Questionnaire.objects.get_or_create(
            code="hhia-s", defaults={"questionnaire_name": "HHIA-S"}
        )
        if created:
            Question.objects.bulk_create(
                Question(
                    questionnaire=questionnaire,
                    question_number=number,
                    category=category,
                    question_text=text,
                )
                for number, (category, text) in enumerate(QUESTIONS, start=1)
            )
        self.stdout.write("HHIA-S created." if created else "HHIA-S already exists; unchanged.")
