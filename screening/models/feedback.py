from datetime import timedelta

from django.db import models
from django.utils import timezone

# Spec #633: the longest 意見回饋 kept.
FEEDBACK_MAX_LENGTH = 1000
# ADR 0064: each is kept 90 days, as the 提問紀錄 is.
FEEDBACK_KEPT_FOR = timedelta(days=90)


class Feedback(models.Model):
    # 意見回饋 (GLOSSARY, ADR 0064): a few words anyone sends from the footer, kept to read and
    # answer. Anonymous like the 提問紀錄: no account, IP, session or address, so it is not in
    # 下載我的資料 and stays when an account is deleted. The email is there only when typed.
    text = models.CharField("內容", max_length=FEEDBACK_MAX_LENGTH)
    email = models.EmailField("Email", blank=True, default="")
    # Which kind of page it was sent from, in words (「結果頁」), never the page's address.
    page = models.CharField("從哪一頁", max_length=200, blank=True, default="")
    created_at = models.DateTimeField("送出時間", auto_now_add=True)
    handled = models.BooleanField("已處理", default=False)

    class Meta:
        verbose_name = verbose_name_plural = "意見回饋"

    def __str__(self):
        # Not the words or the email: the admin keeps this in its history after a delete.
        return f"意見回饋 #{self.pk}"


class FeedbackNotice(models.Model):
    # 回饋通知信 (GLOSSARY, spec #633 Q10, #638): the Taipei days a notice was sent for. Only the
    # one request that writes the day sends it, so two feedbacks at the same moment send one.
    day = models.DateField("日期", unique=True)

    class Meta:
        verbose_name = verbose_name_plural = "回饋通知信"

    def __str__(self):
        return f"{self.day:%Y/%m/%d}"


def purge_feedback():
    """Delete each 意見回饋 over 90 days; returns how many (#639).

    Run every day at 02:30 on the VPS, beside purge_question_log, and when the owner opens the
    list in the admin. Nothing is counted first: no month stats are kept.
    """
    purged, _ = Feedback.objects.filter(created_at__lt=timezone.now() - FEEDBACK_KEPT_FOR).delete()
    return purged
