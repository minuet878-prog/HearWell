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


class RetestReminderSent(models.Model):
    """One 重測提醒信 per account and due day (spec #656): the unique pair is what keeps a schedule
    run again, or two at once, from sending it twice. attempts counts every try, the one that sent
    it too; a day that failed is tried again the next, at most MAX_ATTEMPTS days."""

    MAX_ATTEMPTS = 3

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="retest_reminders_sent"
    )
    due_on = models.DateField()
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_failed_on = models.DateField(null=True, blank=True)  # Taiwan date

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=("user", "due_on"), name="one_reminder_per_due_day"),
        )

    def __str__(self):
        return f"{self.user} {self.due_on:%Y/%m/%d}"

    def to_try_on(self, today):
        """Whether today's run still sends it: not sent, not given up, not failed today already."""
        return (
            self.sent_at is None
            and self.attempts < self.MAX_ATTEMPTS
            and self.last_failed_on != today
        )
