import secrets
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.utils import timezone

from screening import questionnaires
from screening.audiogram import DB_MIN, interpret
from screening.scoring import HHIA_S_CHOICES, classify
from screening.ssq12 import CODE as SSQ12
from screening.ssq12 import scale_labels

# Privacy notice (spec phase7_consent_privacy.md). A major revision (what is collected, why,
# or who receives it) raises CONSENT_VERSION, so everyone agrees again; a minor fix only
# moves PRIVACY_UPDATED_ON.
CONSENT_VERSION = 1
PRIVACY_UPDATED_ON = date(2026, 10, 17)


class User(AbstractUser):
    # Western calendar year; only the year is collected (data minimisation).
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)

    @property
    def age(self):
        if self.birth_year is None:
            return None
        return date.today().year - self.birth_year

    def has_consented(self):
        return self.consents.filter(version__gte=CONSENT_VERSION).exists()

    def give_consent(self):
        Consent.objects.create(user=self, version=CONSENT_VERSION)

    @transaction.atomic
    def delete_with_data(self):
        # Spec phase7_account_deletion.md: the account and everything of it, or nothing.
        # Children first, because every link to the user (and Answer to Submission) is PROTECT.
        self.report_comparisons.all().delete()
        Answer.objects.filter(submission__user=self).delete()
        self.submissions.all().delete()  # norm_basis is RESTRICT, so linked pairs go together
        self.audiograms.all().delete()  # points go with them (CASCADE)
        self.consents.all().delete()
        self.report_shares.all().delete()
        self.delete()


class Consent(models.Model):
    # One row per agreement; older rows stay as proof of what was agreed and when.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="consents"
    )
    version = models.PositiveSmallIntegerField()
    agreed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} v{self.version} {self.agreed_at:%Y-%m-%d}"


SHARE_DAYS = 7


def _share_token():
    # About 256 random bits: cannot be guessed or listed, and says nothing about the user.
    return secrets.token_urlsafe(32)


def _share_expiry():
    return timezone.now() + timedelta(days=SHARE_DAYS)


class ReportShareQuerySet(models.QuerySet):
    def active(self):
        # The only definition of a link that still works (spec phase8_c1_family_share.md).
        return self.filter(revoked_at__isnull=True, expires_at__gt=timezone.now())


class ReportShare(models.Model):
    # Ended links stay as the user's record (exported); they go when the account goes.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="report_shares"
    )
    # Kept in plain text: the owner is shown the link while it works.
    token = models.CharField(max_length=64, unique=True, default=_share_token, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_share_expiry)
    revoked_at = models.DateTimeField(null=True, blank=True)
    open_count = models.PositiveIntegerField(default=0)
    last_opened_at = models.DateTimeField(null=True, blank=True)
    objects = ReportShareQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        return f"{self.user} share {self.created_at:%Y-%m-%d}"


class QuestionnaireQuerySet(models.QuerySet):
    def defined(self):
        # Only questionnaires with a definition are offered (ADR 0005).
        return self.filter(code__in=questionnaires.DEFINITIONS)


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
        if self.questionnaire.code != SSQ12:
            return None
        lower, upper = scale_labels(self.question_number)
        return {"min_label": lower, "max_label": upper}


def _score_expressions():
    # The only definition of score sums: aggregate() for one submission, annotate() for lists.
    return {
        "answer_count": models.Count("answers"),
        "numeric_count": models.Count("answers__score"),
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
    def valid_hhi(self):
        return (
            self.filter(questionnaire__code__in=("hhie-s", "hhia-s"))
            .with_scores()
            .annotate(
                valid_hhi_count=models.Count(
                    "answers",
                    filter=models.Q(
                        answers__score__in=(0, 2, 4),
                        answers__question__questionnaire=models.F("questionnaire"),
                        answers__question__question_number__range=(1, 10),
                    ),
                )
            )
            .filter(answer_count=10, valid_hhi_count=10)
        )

    def with_scores(self):
        # id breaks ties so "newest" is consistent with the API's cursor ordering.
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
    # The unaided HHIA-S / HHIE-S the group came from; None when ungrouped.
    # RESTRICT: the basis cannot go alone, but a user's records can go together.
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
    def ssq_average(self):
        if self.questionnaire.code != SSQ12:
            return None
        scores = self._calculate_scores()
        if scores["numeric_count"] != 12 or scores["answer_count"] != 12:
            return None
        return (Decimal(scores["score_total"]) / 12).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )

    @property
    def ssq_unavailable_reason(self):
        if self.questionnaire.code != SSQ12 or self.ssq_average is not None:
            return None
        if self._calculate_scores()["numeric_count"] == 0:
            return "未計算：沒有可用數值回答"
        return "未計算：包含不適用題目"

    @property
    def classified(self):
        if self.questionnaire.code == SSQ12:
            return None
        return classify(self.total_answer_score, self.questionnaire.code)


# HHIE-S answers; other questionnaires get their choices from scoring (see forms.answer_choices).
class Score(models.IntegerChoices):
    ALWAYS = 4, "常常"
    SOMETIMES = 2, "有時"
    NEVER = 0, "從未"


class Answer(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    score = models.IntegerField(choices=Score.choices, null=True, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["submission", "question"], name="unique_submission_question"
            ),
            models.CheckConstraint(
                # Each questionnaire's exact values and explicit N/A are checked by its form.
                condition=models.Q(score__isnull=True) | models.Q(score__gte=0, score__lte=10),
                name="score_must_be",
            ),
        )

    def __str__(self):
        return f"{self.question}: {self.score}"

    def get_answer_display(self):
        if self.question.questionnaire.code == SSQ12:
            return "不適用" if self.score is None else str(self.score)
        if self.question.questionnaire.code == "hhia-s":
            return dict(HHIA_S_CHOICES).get(self.score, str(self.score))
        return self.get_score_display()


class ReportComparison(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="report_comparisons"
    )
    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.PROTECT)
    unaided = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="+")
    aided = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=("user", "questionnaire"), name="one_report_comparison"),
        )

    def __str__(self):
        return f"{self.user_id} comparison for {self.questionnaire_id}"

    @property
    def item_pairs(self):
        aided = {a.question_id: a for a in self.aided.answers.all()}
        return [
            {"question": a.question, "unaided": a, "aided": aided[a.question_id]}
            for a in sorted(self.unaided.answers.all(), key=lambda a: a.question.question_number)
        ]

    @property
    def difference(self):
        if self.questionnaire.code == SSQ12:
            if self.unaided.ssq_average is None or self.aided.ssq_average is None:
                return None
            return (
                Decimal(self.aided.total_answer_score - self.unaided.total_answer_score) / 12
            ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return self.aided.total_answer_score - self.unaided.total_answer_score

    @property
    def difference_text(self):
        change = self.difference
        if self.questionnaire.code == SSQ12:
            if change is None:
                return "未計算整體差值：包含不適用題目或缺少完整回答"
            return f"{change:+.1f} 分"
        if change < 0:
            return f"少了 {-change} 分"
        if change > 0:
            return f"多了 {change} 分"
        return "沒有變化"


class Audiogram(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="audiograms"
    )
    tested_on = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    # Same retry guard as Submission.idempotency_key.
    idempotency_key = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["user", "idempotency_key"], name="unique_audiogram_idempotency_key"
            ),
        )
        # Saved later on the same test date comes first.
        ordering = ("-tested_on", "-id")

    def __str__(self):
        return f"{self.user} audiogram {self.tested_on}"

    def interpretation(self):
        # The only path to an audiogram's result; pages and the API all read it here.
        return interpret(self.points.all())


class Ear(models.TextChoices):
    RIGHT = "right", "右耳"
    LEFT = "left", "左耳"


class Conduction(models.TextChoices):
    AIR = "air", "氣導"
    BONE = "bone", "骨導"


class AudiogramPoint(models.Model):
    # CASCADE, unlike the rest: a point means nothing without its audiogram, and users can
    # delete their audiograms.
    audiogram = models.ForeignKey(Audiogram, on_delete=models.CASCADE, related_name="points")
    ear = models.CharField(max_length=8, choices=Ear.choices)
    conduction = models.CharField(max_length=8, choices=Conduction.choices)
    frequency = models.PositiveSmallIntegerField()
    db = models.SmallIntegerField()
    no_response = models.BooleanField(default=False)
    # Only how the point is drawn; interpretation reads the value either way.
    masked = models.BooleanField(default=False)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["audiogram", "ear", "conduction", "frequency"],
                name="unique_audiogram_point",
            ),
            # The full rules (frequencies, step, bone limit) are checked by the API serializer.
            models.CheckConstraint(
                condition=models.Q(db__gte=DB_MIN, db__lte=120), name="audiogram_db_range"
            ),
        )
        ordering = ("ear", "conduction", "frequency")

    def __str__(self):
        return f"{self.ear} {self.conduction} {self.frequency} Hz: {self.db}"
