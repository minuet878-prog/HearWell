import secrets

from django.conf import settings
from django.db import models


def _cancel_token():
    # As long as a share link's: cannot be guessed, says nothing about the account (spec #656).
    return secrets.token_urlsafe(32)


class RetestReminder(models.Model):
    """The email 重測提醒 (GLOSSARY), one per account, off until its owner turns it on (ADR
    0065). The cancel code is new each time it is turned on again, so an old email's cancel link
    stops working."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="retest_reminder"
    )
    enabled = models.BooleanField(default=False)
    enabled_on = models.DateField(null=True, blank=True)  # the Taiwan date it was turned on
    cancel_token = models.CharField(
        max_length=64, unique=True, default=_cancel_token, editable=False
    )

    def __str__(self):
        return f"{self.user} retest reminder"
