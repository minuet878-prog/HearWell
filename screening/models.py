from datetime import date

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from screening.scoring import QUESTIONNAIRE_INFO, classify


class User(AbstractUser):
    # Western calendar year; only the year is collected (data minimisation).
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)

    @property
    def age(self):
        if self.birth_year is None:
            return None
        return date.today().year - self.birth_year


class Questionnaire(models.Model):
    questionnaire_name = models.CharField(max_length=64, unique=True)
    code = models.SlugField(max_length=32, unique=True)

    def __str__(self):
        return self.questionnaire_name

    @property
    def info(self):
        return QUESTIONNAIRE_INFO.get(self.code)


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


def _score_expressions():
    # The only definition of score sums: aggregate() for one submission, annotate() for lists.
    return {
        "score_total": models.Sum("answers__score", default=0),
        "score_emotional": models.Sum(
            "answers__score",
            filter=models.Q(answers__question__category=Category.EMOTIONAL),
            default=0,
        ),
        "score_social": models.Sum(
            "answers__score",
            filter=models.Q(answers__question__category=Category.SOCIAL),
            default=0,
        ),
    }


class NormGroup(models.TextChoices):
    MILD_MODERATE = "mild_moderate", "輕度至中度"
    MODERATELY_SEVERE = "moderately_severe", "中重度以上"
    UNGROUPED = "ungrouped", "未分組"


class SubmissionQuerySet(models.QuerySet):
    def with_scores(self):
        # id breaks ties so "newest" matches _latest_hhie_s and the API's cursor ordering.
        return self.annotate(**_score_expressions()).order_by("-created_at", "-id")


class Submission(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="submissions"
    )
    questionnaire = models.ForeignKey(
        Questionnaire, on_delete=models.PROTECT, related_name="submissions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # None means the submission predates this question, not "not wearing".
    wearing_hearing_aid = models.BooleanField(
        null=True, choices=((True, "有戴"), (False, "沒戴"), (None, "未記錄"))
    )
    # IOI-HA only, fixed when submitted; "" on other questionnaires (not applicable).
    norm_group = models.CharField(max_length=32, choices=NormGroup.choices, blank=True)
    # The unaided HHIE-S the group came from; None when ungrouped.
    # RESTRICT, not PROTECT: the HHIE-S cannot go alone, but a user's records can go together.
    norm_basis = models.ForeignKey(
        "self", on_delete=models.RESTRICT, null=True, blank=True, related_name="+"
    )
    # Sent by API clients so a retried submit returns the first record instead of a duplicate.
    # None for web-form submissions; PostgreSQL does not compare NULLs in the unique constraint.
    idempotency_key = models.UUIDField(null=True, blank=True, editable=False)
    objects = SubmissionQuerySet.as_manager()

    class Meta:
        indexes = (models.Index(fields=["user", "-created_at"], name="user_created_at_index"),)
        constraints = (
            models.UniqueConstraint(
                fields=["user", "idempotency_key"], name="unique_user_idempotency_key"
            ),
        )
        ordering = (("-created_at"),)

    def __str__(self):
        return f"{self.user} submit at {self.created_at}"

    def _calculate_scores(self):
        if getattr(self, "_scores_cache", None) is None:
            expressions = _score_expressions()
            if hasattr(self, "score_total"):  # already annotated by with_scores()
                self._scores_cache = {name: getattr(self, name) for name in expressions}
            else:
                self._scores_cache = Submission.objects.filter(pk=self.pk).aggregate(**expressions)
        return self._scores_cache

    @property
    def total_answer_score(self):
        return self._calculate_scores()["score_total"]

    @property
    def emotional_score(self):
        return self._calculate_scores()["score_emotional"]

    @property
    def social_score(self):
        return self._calculate_scores()["score_social"]

    @property
    def classified(self):
        return classify(self.total_answer_score, self.questionnaire.code)


# HHIE-S answers; other questionnaires get their choices from scoring (see forms.answer_choices).
class Score(models.IntegerChoices):
    ALWAYS = 4, "常常"
    SOMETIMES = 2, "有時"
    NEVER = 0, "從未"


class Answer(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    score = models.IntegerField(choices=Score.choices)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["submission", "question"], name="unique_submission_question"
            ),
            models.CheckConstraint(
                # 0-5 covers every questionnaire; the form checks each one's own values.
                condition=models.Q(score__gte=0, score__lte=5),
                name="score_must_be",
            ),
        )

    def __str__(self):
        return f"{self.question}: {self.score}"
