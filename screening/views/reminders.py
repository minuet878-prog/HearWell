from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone

from screening.models import RetestReminder
from screening.models.reminders import _cancel_token
from screening.views.common import form_address, health_data_page, safe_next


@form_address
@health_data_page
def retest_reminder(request):
    # #659 (spec #656 acceptance 2, 3, 5, 6): request.user's own email 重測提醒 on (enabled=1)
    # or off (0), from the account settings or (#661) a result page, back to its next.
    enabled = request.POST.get("enabled")
    if enabled not in ("0", "1"):
        return HttpResponseBadRequest()
    user = request.user
    if enabled == "0":
        RetestReminder.objects.filter(user=user).update(enabled=False, enabled_on=None)
    elif user.email:  # without one there is nowhere to send it (acceptance 5)
        today = timezone.localdate()
        reminder, created = RetestReminder.objects.get_or_create(
            user=user, defaults={"enabled": True, "enabled_on": today}
        )
        if not created and not reminder.enabled:
            # On again: a new cancel code, so an old email's cancel link no longer works.
            reminder.enabled, reminder.enabled_on = True, today
            reminder.cancel_token = _cancel_token()
            reminder.save()
    return HttpResponseRedirect(safe_next(request) or reverse("account_settings"))
