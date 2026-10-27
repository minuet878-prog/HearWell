from django.db import models


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
