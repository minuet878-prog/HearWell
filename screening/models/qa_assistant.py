from collections import Counter
from datetime import timedelta

from django.db import models, transaction
from django.db.models import F
from django.utils import timezone

# ADR 0034: a question is kept 90 days, then only its month's counts are.
KEPT_FOR = timedelta(days=90)


class NoMatchReason(models.TextChoices):
    # ADR 0035: why a typed question matched nothing, ticked by the owner in the admin.
    DIFFERENT_WORDING = "different_wording", "問法不同"
    NOT_IN_FAQ = "not_in_faq", "題庫沒有"
    SHOULD_NOT_ANSWER = "should_not_answer", "不該回答"


class QuestionLog(models.Model):
    # 提問紀錄 (GLOSSARY, ADR 0034, #400): a question typed into the Q&A assistant, kept to add
    # questions and tune the matching. Anonymous: no account, IP or session, so it is not in
    # 下載我的資料 and stays when an account is deleted. Clicking the lists keeps nothing.
    question = models.CharField("問句", max_length=200)  # QaQuestionForm's limit
    # The first question it matched, as shown on the results; blank when it matched nothing.
    faq_code = models.CharField("結果", max_length=50, blank=True, default="")
    created_at = models.DateTimeField("日期", auto_now_add=True)
    reason = models.CharField(
        "沒對到的原因", max_length=20, choices=NoMatchReason, blank=True, default=""
    )

    class Meta:
        verbose_name = verbose_name_plural = "提問紀錄"

    def __str__(self):
        return self.question


class QuestionLogMonth(models.Model):
    # 月統計 (spec #396, #401): a month's counts of the 提問紀錄, kept after the questions are
    # purged or deleted, so the owner can read three months in a row (ADR 0035). Never what was
    # typed.
    # Field names other than month and the two counts are NoMatchReason's values.
    month = models.DateField("月份", unique=True)  # the month's first day, Taipei time
    typed = models.PositiveIntegerField("打字提問數", default=0)
    matched = models.PositiveIntegerField("對到數", default=0)
    different_wording = models.PositiveIntegerField(
        NoMatchReason.DIFFERENT_WORDING.label, default=0
    )
    not_in_faq = models.PositiveIntegerField(NoMatchReason.NOT_IN_FAQ.label, default=0)
    should_not_answer = models.PositiveIntegerField(
        NoMatchReason.SHOULD_NOT_ANSWER.label, default=0
    )

    class Meta:
        verbose_name = verbose_name_plural = "月統計"

    def __str__(self):
        return f"{self.month.year}/{self.month.month:02d}"


def purge_question_log():
    """Count each question over 90 days into its month, then delete it; returns how many.

    Called when a question is saved, when the owner opens the log in the admin and on each
    deploy, since there is no scheduler (spec #396).
    """
    return count_and_delete_questions(
        QuestionLog.objects.filter(created_at__lt=timezone.now() - KEPT_FOR)
    )


def count_and_delete_questions(logs):
    """Count these questions into their months, then delete them; returns how many.

    The 90-day purge and the owner deleting one early in the admin (the owner's call,
    2026-10-27) both come here, so the month stats count every question typed. Counting and
    deleting share one transaction and the rows stay locked until both are done, so a question
    is counted once: a purge or delete running at the same time waits, then no longer finds it.
    """
    with transaction.atomic():
        counted = list(logs.select_for_update())
        months = {}
        for log in counted:
            counts = months.setdefault(timezone.localdate(log.created_at).replace(day=1), Counter())
            counts["typed"] += 1
            counts["matched"] += bool(log.faq_code)
            if log.reason:
                counts[log.reason] += 1
        for month, counts in months.items():
            QuestionLogMonth.objects.get_or_create(month=month)
            # F(): added in the database, so a purge of other rows into this month adds too.
            QuestionLogMonth.objects.filter(month=month).update(
                **{field: F(field) + count for field, count in counts.items()}
            )
        QuestionLog.objects.filter(pk__in=[log.pk for log in counted]).delete()
    return len(counted)
