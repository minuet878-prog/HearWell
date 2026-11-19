from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from screening.models import RetestReminder
from screening.views.common import email_link_page, form_address, health_data_page, safe_next


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
        reminder = RetestReminder.objects.filter(user=user).first()
        if reminder is not None:
            reminder.turn_off()
    # Without one there is nowhere to send it (acceptance 5); without its 確認信 answered, it
    # may be someone else's (security check 2026-11-19).
    elif user.email_confirmed:
        reminder, _ = RetestReminder.objects.get_or_create(user=user)
        reminder.turn_on(timezone.localdate())
    return HttpResponseRedirect(safe_next(request) or reverse("account_settings"))


# RFC 8058's one-click: a mail program POSTs List-Unsubscribe=One-Click to this address without a
# CSRF token, so the cancel code alone says whose reminder it is (spec #656).
@csrf_exempt
@require_http_methods(["GET", "POST"])
def reminder_cancel(request, token):
    """#662 (spec #656 acceptance 32-38): GET only shows the page, since an email scanner opening
    the link must not cancel; POST, its button or a mail program's one-click, turns it off."""
    if request.method == "GET":
        reminder = RetestReminder.objects.select_related("user").filter(cancel_token=token).first()
        if reminder is not None:
            return email_link_page(
                request, "screening/reminder_cancel.html", {"reminder": reminder}
            )
    elif RetestReminder.cancel(token):  # one already off answers the same
        if request.POST.get("List-Unsubscribe") == "One-Click":
            # RFC 8058: a mail program's one-click is answered here, not sent on.
            return email_link_page(request, "screening/reminder_cancelled.html")
        return HttpResponseRedirect(reverse("reminder_cancelled"))
    # Wrong, or gone with its account: the same answer for both.
    return email_link_page(request, "screening/reminder_invalid.html", status=404)


@require_http_methods(["GET"])
def reminder_cancelled(request):
    return email_link_page(request, "screening/reminder_cancelled.html")
