import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

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
        return f"{self.user} share {self.created_at:%Y/%m/%d}"
