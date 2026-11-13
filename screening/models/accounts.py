from datetime import date

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction

from screening.models.hearing_aids import AidAndSubsidy
from screening.models.submissions import Answer

# Privacy notice (spec phase7_consent_privacy.md). A major revision (what is collected, why,
# or who receives it) raises CONSENT_VERSION, so everyone agrees again; a minor fix only
# moves PRIVACY_UPDATED_ON.
# 2: the 助聽器與補助資料 (#286, spec #284 Q9). 3: the operator's name became 聽伴 (ADR 0039).
# 4: the site moved to a Vultr VPS in Tokyo, so the data's country and who stores it changed,
# and the backups keep deleted data up to 10 days (#452, ADR 0042).
# 5: the 照顧旅程's to-do ticks are kept, so what is collected changed (spec #478, the owner on
# 2026-11-13, phase-2-grill-decisions.md).
CONSENT_VERSION = 5
# The 提問紀錄 (#400) is new data but linked to no one, so only the date moved (ADR 0034); the
# cookie sentence's minor fix for public forms (#431) moved it again (ADR 0014); versions 4 and
# 5 moved it with the version (#452, spec #478). A guest's answers stay in the browser (spec
# #492): nothing new is kept, so that sentence needed no version of its own.
PRIVACY_UPDATED_ON = date(2026, 11, 13)


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
        AidAndSubsidy.objects.filter(user=self).delete()
        self.guide_views.all().delete()
        self.todo_ticks.all().delete()
        self.delete()


class Consent(models.Model):
    # One row per agreement; older rows stay as proof of what was agreed and when.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="consents"
    )
    version = models.PositiveSmallIntegerField()
    agreed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} v{self.version} {self.agreed_at:%Y/%m/%d}"
