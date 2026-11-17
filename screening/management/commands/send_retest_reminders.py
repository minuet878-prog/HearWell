import logging
from dataclasses import dataclass
from datetime import date
from time import sleep
from urllib.parse import quote, urlsplit

from anymail.exceptions import AnymailAPIError
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.db import transaction
from django.template import loader
from django.urls import reverse
from django.utils import timezone

from screening.forms import HELP_ADDRESS
from screening.main_flow import get_user_state, retest_due_on
from screening.models import Questionnaire, RetestReminder, RetestReminderSent, count_guest

logger = logging.getLogger(__name__)

# Resend takes 10 requests a second for the whole team, the password and feedback mails too
# (resend.com/docs/api-reference/rate-limit): at most 2 a second leaves them room.
SEND_INTERVAL = 0.5  # seconds
# Resend's 429 for the quota used up, the day's (free plan) or the month's; its other 429 is the
# rate, rate_limit_exceeded (resend.com/docs/api-reference/errors).
QUOTA_USED_UP = ("daily_quota_exceeded", "monthly_quota_exceeded")


@dataclass(frozen=True)
class Due:
    """An account to send to today (spec #656 誰會收到)."""

    reminder: RetestReminder
    due_on: date
    questionnaire: Questionnaire  # the home page's 再做一次 opens the same one


class QuotaUsedUp(Exception):
    """Resend sends no more: the rest wait for the next day's run, none counted as failed."""


class Command(BaseCommand):
    help = (
        "Send each 重測提醒信 falling due today, the oldest first, at most "
        "RETEST_REMINDER_DAILY_LIMIT (spec #656; run every day at 09:00 on the VPS)."
    )

    def handle(self, *args, **options):
        today = timezone.localdate()
        due = sorted(_due(today), key=lambda each: (each.due_on, each.reminder.pk))
        # What the day's earlier runs sent counts too: one run again by hand, or after a restart.
        sent_today = RetestReminderSent.objects.filter(sent_at__date=today).count()
        left = max(settings.RETEST_REMINDER_DAILY_LIMIT - sent_today, 0)
        sent = 0
        for number, each in enumerate(due[:left]):
            if number:
                sleep(SEND_INTERVAL)
            try:
                sent += _send(each, today)
            except QuotaUsedUp:
                break
        self.stdout.write(f"Sent {sent} retest reminder(s).")


def _sendable():
    """The reminders that may be sent: on, with an email, of an active account."""
    return (
        # Not the admins: create_superuser makes staff too.
        RetestReminder.objects.filter(enabled=True, user__is_active=True, user__is_staff=False)
        .exclude(user__email="")
        .select_related("user")
    )


def _due(today):
    """A Due for each account to send to today."""
    for reminder in _sendable():
        due = _due_for(reminder, today)
        if due is None:
            continue
        record = RetestReminderSent.objects.filter(user=reminder.user, due_on=due.due_on).first()
        if record is None or record.to_try_on(today):
            yield due


def _due_for(reminder, today):
    """Its Due when it has fallen due by today, None when not."""
    state = get_user_state(reminder.user, today)
    if state.life_impact is None:
        return None
    due_on = retest_due_on(state.life_impact)  # the home page's 下次篩檢
    # Already due when it was turned on: not this time (Q6).
    if not reminder.enabled_on <= due_on <= today:
        return None
    return Due(reminder, due_on, state.retest_questionnaire)


def _send(due, today):
    """1 when it went, 0 when it did not. The row stays locked while sending, so a run at the same
    moment waits, then finds it sent."""
    with transaction.atomic():
        # Looked at again just before it goes (cross review, Codex 2): the list was made before
        # the first one went, and since then it may have been turned off, done again and so on.
        reminder = _sendable().select_for_update(of=("self",)).filter(pk=due.reminder.pk).first()
        now = None if reminder is None else _due_for(reminder, today)
        if now is None or now.due_on != due.due_on:
            return 0
        record, _ = RetestReminderSent.objects.select_for_update().get_or_create(
            user=reminder.user, due_on=now.due_on
        )
        if not record.to_try_on(today):
            return 0
        record.attempts += 1
        try:
            _message(now.reminder, now.questionnaire).send()
        except AnymailAPIError as error:
            # Raised out of the transaction, so the row is as it was.
            if _quota_used_up(error):
                raise QuotaUsedUp from error
            _failed(record, today)
            return 0
        except Exception:
            _failed(record, today)
            return 0
        record.sent_at = timezone.now()
        record.save()
        count_guest("reminders_sent")
        return 1


def _quota_used_up(error):
    # Resend names the limit in its JSON body; anymail keeps the response.
    return error.status_code == 429 and error.response.json().get("name") in QUOTA_USED_UP


def _failed(record, today):
    # A fixed message: the mail service's own words may hold the address (Sentry drops them).
    logger.exception("A retest reminder could not be sent")
    record.last_failed_on = today
    record.save()


def _message(reminder, questionnaire):
    user = reminder.user
    # The home page's 再做一次, through the consent page: it signs in first when needed (signed
    # out, the address alone would open the guest version), then goes straight on.
    retest_path = reverse("screening", args=[questionnaire.pk])
    retest_url = f"{settings.SITE_URL}{reverse('consent')}?next={quote(retest_path)}"
    cancel_url = settings.SITE_URL + reverse("reminder_cancel", args=[reminder.cancel_token])
    context = {
        "user": user,
        "retest_url": retest_url,
        "cancel_url": cancel_url,
        "site_url": settings.SITE_URL,
        "domain": urlsplit(settings.SITE_URL).netloc,
    }
    subject = "".join(
        loader.render_to_string("screening/retest_reminder_subject.txt", context).splitlines()
    )
    message = EmailMultiAlternatives(
        subject,
        loader.render_to_string("screening/retest_reminder_email.txt", context),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        reply_to=[HELP_ADDRESS],
        # RFC 8058: Gmail and Outlook show 取消訂閱 and POST to the cancel address themselves.
        headers={
            "List-Unsubscribe": f"<{cancel_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    message.attach_alternative(
        loader.render_to_string("screening/retest_reminder_email.html", context), "text/html"
    )
    return message
