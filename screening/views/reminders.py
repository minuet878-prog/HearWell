from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from screening.models import RetestReminder
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
        reminder = RetestReminder.objects.filter(user=user).first()
        if reminder is not None:
            reminder.turn_off()
    elif user.email:  # without one there is nowhere to send it (acceptance 5)
        reminder, _ = RetestReminder.objects.get_or_create(user=user)
        reminder.turn_on(timezone.localdate())
    return HttpResponseRedirect(safe_next(request) or reverse("account_settings"))


def _email_link_page(request, template, context=None, status=200):
    # Opened from an email without signing in, as a shared report is (reports._family_page): it
    # names the account, so never cached, indexed, or referred on (spec #656 acceptance 39).
    response = render(request, template, context, status=status)
    add_never_cache_headers(response)
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "no-referrer"
    return response


# RFC 8058's one-click: a mail program POSTs List-Unsubscribe=One-Click to this address without a
# CSRF token, so the cancel code alone says whose reminder it is (spec #656).
@csrf_exempt
@require_http_methods(["GET", "POST"])
def reminder_cancel(request, token):
    """#662 (spec #656 acceptance 32-38): GET only shows the page, since an email scanner opening
    the link must not cancel; POST, its button or a mail program's one-click, turns it off."""
    reminder = RetestReminder.objects.select_related("user").filter(cancel_token=token).first()
    if reminder is None:  # wrong, or gone with its account: the same answer for both
        return _email_link_page(request, "screening/reminder_invalid.html", status=404)
    if request.method == "POST":
        reminder.turn_off()  # one already off answers the same
        return HttpResponseRedirect(reverse("reminder_cancelled"))
    return _email_link_page(request, "screening/reminder_cancel.html", {"reminder": reminder})


@require_http_methods(["GET"])
def reminder_cancelled(request):
    return _email_link_page(request, "screening/reminder_cancelled.html")
