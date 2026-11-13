"""確認本人 (spec #505, ADR 0057): before deleting the account, or adding or removing a sign-in
method, the account's owner shows it is them: with the password when the account has one,
otherwise by signing in again with a provider already on the account, which must give back
that account's code (`sub`). It holds for 5 minutes and for the one action it was asked for.

For a view that needs it (#511):

    if not use_confirmation(request, "add_google"):
        return ask_confirmation("add_google")
"""

from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from screening import oidc
from screening.forms import PasswordConfirmForm
from screening.models import SignInMethod
from screening.views.common import line_way_out

# What the confirmation is for: the words after 「接下來要」 (the #507 mockup W15) and the page it
# leads back to. 移除 Google 登入 has none: the right password removes it on this page, in the same
# request (the owner's call on the #505 review), so the password is sent once and only here. It
# needs the password: Google is the only provider, and the only way in cannot be removed.
ACTIONS = {
    "delete_account": ("刪除帳號", "delete_account"),
    "add_google": ("新增 Google 登入", "google_add"),
    "remove_google": ("移除 Google 登入", None),
}

# Which action the owner last confirmed for, and when: {"action", "at" (a Unix time)}; taken out
# by the action it is used for.
CONFIRMED = "screening.identity_confirmed"
CONFIRMED_SECONDS = 5 * 60  # #505 acceptance 29

# A message for the confirm page (or the delete page), shown once.
CONFIRM_ERROR = "screening.confirm_error"
NOT_YOURS = "這不是您帳號上的 Google。請改用註冊時用的那個 Google 帳戶。"  # W16
EXPIRED = "確認已經過期，請再確認一次。"  # W18
# Cancelled, refused or Google down: no wording in the mockup (a draft for the owner to settle).
NOT_CONFIRMED = "沒有完成 Google 確認，請再試一次。"
REMOVED = "已移除 Google 登入。"


def _fresh(confirmed):
    return timezone.now().timestamp() - confirmed["at"] <= CONFIRMED_SECONDS


def _confirm(request, action):
    request.session[CONFIRMED] = {"action": action, "at": timezone.now().timestamp()}


def is_confirmed(request, action):
    """Whether the owner confirmed for this action in the last 5 minutes; leaves the
    confirmation in place."""
    confirmed = request.session.get(CONFIRMED)
    return confirmed is not None and confirmed["action"] == action and _fresh(confirmed)


def use_confirmation(request, action):
    """Take the confirmation out of the session: True when it was for this action and is from
    the last 5 minutes. One for another action is used up all the same; a stale one is dropped
    and the next page says so (W18)."""
    confirmed = request.session.pop(CONFIRMED, None)
    if confirmed is None or confirmed["action"] != action:
        return False
    if _fresh(confirmed):
        return True
    request.session[CONFIRM_ERROR] = EXPIRED
    return False


def ask_confirmation(action):
    """Send the user to confirm it is them; they come back to the action's page."""
    return HttpResponseRedirect(f"{reverse('confirm_identity')}?action={action}")


def confirm_error(request):
    """The confirm page's message, once."""
    return request.session.pop(CONFIRM_ERROR, None)


def came_back(request, identity):
    """The provider's callback for a confirm_identity trip: the code that came back must be one
    on this account (#505 acceptance 31); otherwise nothing is confirmed."""
    # The callback is public: whoever started the trip may no longer be signed in (the account
    # turned off meanwhile). Nothing to confirm then; the confirm page asks to log in first.
    if not request.user.is_authenticated:
        return redirect_to_login(identity.next)
    # The trip started on the confirm page, whose URL (its next) names the action.
    action = QueryDict(urlsplit(identity.next).query).get("action")
    if action in ACTIONS and request.user.sign_in_methods.for_identity(identity).exists():
        _confirm(request, action)
    else:
        request.session[CONFIRM_ERROR] = NOT_YOURS
    # The confirm page, which goes on to the action's page once confirmed.
    return redirect(identity.next)


def trip_failed(request, flow, message):
    """A confirm_identity trip that ended without an identity goes back to its confirm page,
    with its own words."""
    request.session[CONFIRM_ERROR] = NOT_CONFIRMED
    return redirect(flow["next"])


def providers(user):
    """The providers on the account that can be signed in with again, to confirm with."""
    return [
        provider
        for provider in user.sign_in_methods.values_list("provider", flat=True)
        if oidc.enabled(provider)
    ]


def _google_to_remove(user):
    """The account's Google sign-in, for 移除 Google 登入 (#505 acceptance 26-28): without the
    Google keys or one on the account, 404; an admin account, or its only way in, 403."""
    if not oidc.enabled("google"):
        raise Http404
    if user.is_admin:
        raise PermissionDenied
    method = get_object_or_404(SignInMethod, user=user, provider=SignInMethod.Provider.GOOGLE)
    if not method.can_be_removed():
        raise PermissionDenied
    return method


@never_cache
@login_required
@require_http_methods(["GET", "POST"])  # the POST is the form's, with this site's CSRF token
def confirm_identity(request):
    action = request.GET.get("action")
    if action not in ACTIONS:
        raise Http404
    words, page = ACTIONS[action]
    # Refused before the password is asked for, as on the POST that removes it.
    google = _google_to_remove(request.user) if action == "remove_google" else None
    # Back here already confirmed (from Google): on to the action's page.
    if page is not None and is_confirmed(request, action):
        return redirect(page)
    user = request.user
    form = None
    if user.has_usable_password():
        form = PasswordConfirmForm(request.POST if request.method == "POST" else None, user=user)
        if form.is_valid():
            if google is not None:
                google.delete()
                messages.success(request, REMOVED)
                return HttpResponseRedirect(f"{reverse('account_settings')}#sign-in-methods")
            _confirm(request, action)
            return redirect(page)
    elif request.method == "POST":
        # No password: a provider on the account, asked to show its account chooser.
        provider = request.POST.get("provider")
        if provider in providers(user):
            return HttpResponseRedirect(
                oidc.begin(request, provider, "confirm_identity", request.get_full_path())
            )
    return render(
        request,
        "screening/confirm_identity.html",
        {
            "action": action,
            "words": words,
            "form": form,
            "providers": providers(user),
            "open_outside_url": line_way_out(request),
            "confirm_error": confirm_error(request),
        },
    )
