from collections import Counter
from functools import cached_property

from django.conf import settings
from django.db import models
from django.utils import timezone

from screening import questionnaires
from screening.models.questionnaires import Category, Question, Questionnaire
from screening.questionnaires import hhia_s, hhie_s
from screening.scoring import HIGHER_IS_BETTER, since_last_text


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
        # Answers to emotional or social items: a record has subscores only when it has one
        # (THI has none, spec #208 Q5). The one rule for the result page, export and API (#386).
        "subscore_answer_count": models.Count(
            "answers",
            filter=models.Q(answers__question__category__in=(Category.EMOTIONAL, Category.SOCIAL)),
        ),
    }


class NormGroup(models.TextChoices):
    MILD_MODERATE = "mild_moderate", "輕度至中度"
    MODERATELY_SEVERE = "moderately_severe", "中重度以上"
    UNGROUPED = "ungrouped", "未分組"


class SubmissionQuerySet(models.QuerySet):
    def find_by_key(self, key):
        # Call it on user.submissions: another user's key must never return their record (IDOR).
        return self.filter(idempotency_key=key).first()

    def defined(self):
        # Records of a questionnaire without a definition are not shown (ADR 0005).
        return self.filter(questionnaire__code__in=questionnaires.offered())

    def valid_hhi(self):
        # Basis for the IOI-HA norm group: a complete HHIA-S or HHIE-S.
        return self.filter(questionnaire__code__in=(hhie_s.CODE, hhia_s.CODE)).complete_hhi()

    def complete_hhi(self):
        # All 10 items answered with an HHI choice.
        return (
            self.with_scores()
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


def shared_days(moments):
    # The Taipei dates two or more of these moments fall on: a record made on one shows its time
    # too (spec phase9_ui_refresh_2_data.md 4.3; 我的紀錄 and the comparison page, #190).
    per_day = Counter(timezone.localdate(moment) for moment in moments)
    return frozenset(day for day, count in per_day.items() if count > 1)


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

    @cached_property
    def result(self):
        # This record's result object: its questionnaire's result type bound to it (spec #385).
        return self.questionnaire.definition.result(self)

    @property
    def total_answer_score(self):
        return self._calculate_scores()["score_total"]

    def previous_same_wearing(self, earlier):
        # earlier: this questionnaire's records before this one, newest first. The record this one
        # is compared with: the latest worn the same way (records worn otherwise may sit in
        # between). None when this one has no hearing aid status or is the first of its status.
        if self.wearing_hearing_aid is None:
            return None
        return next((r for r in earlier if r.wearing_hearing_aid == self.wearing_hearing_aid), None)

    @cached_property
    def ssq_since_last(self):
        # SSQ12-TW's 「比上一次」 (ticket #188): the record previous_same_wearing picks, shown only
        # when both have an overall average (ADR 0001).
        if self.result.average is None:
            return None
        earlier = (
            Submission.objects.filter(user_id=self.user_id, questionnaire_id=self.questionnaire_id)
            .filter(
                models.Q(created_at__lt=self.created_at)
                | models.Q(created_at=self.created_at, id__lt=self.id)
            )
            .order_by("-created_at", "-id")
        )
        previous = self.previous_same_wearing(earlier)
        if previous is None or previous.result.average is None:
            return None
        # The difference of the unrounded averages, the same rule as a wearing comparison's.
        difference = self.questionnaire.definition.comparison.difference(previous, self)
        day = timezone.localdate(previous.created_at)
        text = since_last_text(difference, HIGHER_IS_BETTER, day, previous.result.average)
        return {"previous": previous, "text": text}


class Answer(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    # Labels come from the questionnaire's definition (get_answer_display); empty is 「不適用」.
    score = models.IntegerField(null=True, blank=True)

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
        question = self.question
        labels = dict(question.questionnaire.definition.choices(question.question_number))
        return labels.get("na" if self.score is None else self.score, str(self.score))


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
        return self.questionnaire.definition.comparison.difference(self.unaided, self.aided)

    @property
    def difference_text(self):
        return self.questionnaire.definition.comparison.difference_text(self.unaided, self.aided)

    # The comparison page's result card (#191).
    @property
    def unaided_result(self):
        return self.questionnaire.definition.comparison.record_result(self.unaided)

    @property
    def aided_result(self):
        return self.questionnaire.definition.comparison.record_result(self.aided)

    @property
    def direction_text(self):
        return self.questionnaire.definition.comparison.direction_text(self.unaided, self.aided)

    @property
    def summary(self):  # one line of the report summary
        return self.questionnaire.definition.comparison.summary(self.unaided, self.aided)
