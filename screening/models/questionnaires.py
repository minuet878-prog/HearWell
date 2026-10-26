from django.db import models

from screening import questionnaires


class QuestionnaireQuerySet(models.QuerySet):
    def defined(self):
        # Only questionnaires with a definition are offered (ADR 0005).
        return self.filter(code__in=questionnaires.offered())


class Questionnaire(models.Model):
    questionnaire_name = models.CharField(max_length=64, unique=True)
    code = models.SlugField(max_length=32, unique=True)

    objects = QuestionnaireQuerySet.as_manager()

    def __str__(self):
        return self.questionnaire_name

    @property
    def definition(self):
        return questionnaires.get(self.code)


class Category(models.TextChoices):
    EMOTIONAL = "emotional"
    SOCIAL = "social"
    NONE = "", "無"  # IOI-HA items have no subscale


class Question(models.Model):
    questionnaire = models.ForeignKey(
        Questionnaire, on_delete=models.PROTECT, related_name="questions"
    )
    question_text = models.TextField()
    question_number = models.IntegerField()
    category = models.CharField(max_length=64, choices=Category.choices, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["question_number", "questionnaire"], name="unique_question"
            ),
            models.CheckConstraint(
                condition=models.Q(category__in=Category.values), name="category_must_be"
            ),
        )
        ordering = ("question_number",)

    def __str__(self):
        return f"{self.question_number}: {self.question_text[:30]}"

    @property
    def scale(self):
        scale = self.questionnaire.definition.scale
        if scale is None:
            return None
        lower, upper = scale(self.question_number)
        return {"min_label": lower, "max_label": upper}
