from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from screening.scoring import classify

# Create your models here.


class User(AbstractUser):
    birth_date = models.DateField(null=True, blank=True)


class Questionnaire(models.Model):
    questionnaire_name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.questionnaire_name


class Category(models.TextChoices):
    EMOTIONAL = "emotional"
    SOCIAL = "social"


class Question(models.Model):
    questionnaire = models.ForeignKey(
        Questionnaire, on_delete=models.PROTECT, related_name="questions"
    )
    question_text = models.TextField()
    question_number = models.IntegerField()
    category = models.CharField(max_length=64, choices=Category.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["question_number", "questionnaire"], name="unique_question"
            ),
            models.CheckConstraint(
                condition=models.Q(category__in=Category.values), name="category_must_be"
            ),
        ]
        ordering = ["question_number"]

    def __str__(self):
        return f"{self.question_number}: {self.question_text[:30]}"


class SubmissionQuerySet(models.QuerySet):
    def with_scores(self):
        return self.annotate(total_score=models.Sum("answers__score", default=0)).order_by(
            "-created_at"
        )


class Submission(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="submissions"
    )
    questionnaire = models.ForeignKey(
        Questionnaire, on_delete=models.PROTECT, related_name="submissions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    objects = SubmissionQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at"], name="user_created_at_index")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} submit at {self.created_at}"

    def _calculate_scores(self):
        if getattr(self, "_scores_cache", None) is None:
            self._scores_cache = self.answers.aggregate(
                total=models.Sum("score", default=0),
                emotional=models.Sum(
                    models.Case(
                        models.When(
                            question__category=Category.EMOTIONAL,
                            then=models.F("score"),
                        ),
                        default=0,
                    )
                ),
                social=models.Sum(
                    models.Case(
                        models.When(question__category=Category.SOCIAL, then=models.F("score")),
                        default=0,
                    )
                ),
            )
        return self._scores_cache

    @property
    def total_answer_score(self):
        return self._calculate_scores()["total"]

    @property
    def emotional_score(self):
        return self._calculate_scores()["emotional"]

    @property
    def social_score(self):
        return self._calculate_scores()["social"]

    @property
    def classified(self):
        return classify(self.total_answer_score)


class Score(models.IntegerChoices):
    ALWAYS = 4, "是"
    SOMETIMES = 2, "有時"
    NEVER = 0, "否"


class Answer(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    score = models.IntegerField(choices=Score.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "question"], name="unique_submission_question"
            ),
            models.CheckConstraint(
                condition=models.Q(score__in=Score.values), name="score_must_be"
            ),
        ]

    def __str__(self):
        return f"{self.question}: {self.score}"
