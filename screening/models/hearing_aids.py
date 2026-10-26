from django.conf import settings
from django.db import models


class AidEar(models.TextChoices):
    LEFT = "left", "左耳"
    RIGHT = "right", "右耳"
    BOTH = "both", "雙耳"


class Subsidy(models.TextChoices):
    DISABILITY = "disability", "用身障補助"
    OTHER = "other", "自費或其他補助"


class AidLevel(models.TextChoices):
    BASIC = "basic", "簡易型"
    MID = "mid", "中階型"
    ADVANCED = "advanced", "進階型"
    CROS = "cros", "雙對側傳聲型"
    UNKNOWN = "unknown", "不知道"


class Certificate(models.TextChoices):
    # Spec #291 Q2: a 聽覺機能 身心障礙證明, or why there is none.
    YES = "yes", "有"
    APPLYING = "applying", "還沒有，正在申請鑑定"
    NO_SUBSIDY = "no_subsidy", "沒有，不申請身障補助"


class ApprovedEars(models.TextChoices):
    # 等待核定公文 (#294): what the notice approved.
    ONE = "one", "單耳"
    BOTH = "both", "雙耳"


class AidAndSubsidy(models.Model):
    # 助聽器與補助資料 (GLOSSARY, spec #284): what the user says about their certificate and
    # their current hearing aids. Every field may be left unanswered; only the current pair.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="aid_and_subsidy"
    )
    # 身障鑑定與鑑定醫院's answer (#293); "" is unanswered.
    certificate = models.CharField(max_length=10, choices=Certificate, blank=True, default="")
    # 九號表 and 等待核定公文's answers (#294): None unanswered, False 還沒, True 完成了 / 收到了.
    form_9_done = models.BooleanField(null=True, blank=True)
    notice_received = models.BooleanField(null=True, blank=True)
    # What the notice approved, kept only once it is received; the level is the one below.
    approved_ears = models.CharField(max_length=4, choices=ApprovedEars, blank=True, default="")
    # The current pair (#287); "" is unanswered. The level is kept only with 身障補助.
    fitted_on = models.DateField(null=True, blank=True)
    ear = models.CharField(max_length=5, choices=AidEar, blank=True, default="")
    subsidy = models.CharField(max_length=10, choices=Subsidy, blank=True, default="")
    level = models.CharField(max_length=8, choices=AidLevel, blank=True, default="")
    # 二十五號表's answer (#296): None unanswered, False 還沒, True 完成了.
    form_25_done = models.BooleanField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} aid and subsidy"

    @classmethod
    def for_user(cls, user):
        """The user's row, None before their first save."""
        return cls.objects.filter(user=user).first()

    def clean(self):
        # What the notice approved goes with it: 還沒 clears 單耳 or 雙耳 (#294).
        if not self.notice_received:
            self.approved_ears = ""
        # A level means a 身障補助 one (#284 acceptance 3, 6): with any other answer, cleared.
        if not self.uses_disability_subsidy:
            self.level = ""

    @property
    def uses_disability_subsidy(self):
        # 用身障補助 (spec #291): the notice received, or bought with it as 配戴之後 says.
        return self.notice_received is True or self.subsidy == Subsidy.DISABILITY

    @property
    def unanswered(self):
        return (
            self.fitted_on is None
            and self.form_9_done is None
            and self.notice_received is None
            and self.form_25_done is None
            and not (
                self.certificate or self.approved_ears or self.ear or self.subsidy or self.level
            )
        )

    @property
    def hearing_aids_text(self):
        """雙耳，2026/05/01 開始戴: the ear and the fitting date filled in, "" with neither."""
        parts = [self.get_ear_display()] if self.ear else []
        if self.fitted_on:
            parts.append(f"{self.fitted_on:%Y/%m/%d} 開始戴")
        return "，".join(parts)

    @property
    def report_text(self):
        """雙耳，2026/05/01 開始戴，中階型 on the printed report (#284 Q12): no certificate, and
        a level only when it says something (paying otherwise has none)."""
        level = "" if self.level == AidLevel.UNKNOWN else self.get_level_display()
        return "，".join(filter(None, [self.hearing_aids_text, level]))
