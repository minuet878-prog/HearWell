"""確認本人 (spec #505, ADR 0057; LINE: spec #506 acceptance 19-21): before deleting the account,
or adding or removing a sign-in method, the account's owner shows it is them: with the password
when the account has one, otherwise by signing in again with any provider already on the account,
which must give back that account's code (`sub`). It holds for 5 minutes and for the one action
it was asked for.

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
from screening.views.common import line_way_out, provider_logo, works_here
from screening.views.provider_words import WORDS

# What the confirmation is for: the words after 「接下來要」 (the #507 mockup W15) and the page it
# leads back to. 移除 Google／LINE 登入 has none: the right password removes it on this page, in
# the same request (the owner's call on the #505 review), so the password is sent once and only
# here; without a password the provider's callback removes it as it comes back (came_back).
ACTIONS = {
    "delete_account": ("刪除帳號", "delete_account"),
    "add_google": ("新增 Google 登入", "google_add"),
    "remove_google": ("移除 Google 登入", None),
    "add_line": ("新增 LINE 登入", "line_add"),
    "remove_line": ("移除 LINE 登入", None),
}
# The provider each removing action removes.
REMOVES = {"remove_google": "google", "remove_line": "line"}

# Which action the owner last confirmed for, and when: {"action", "at" (a Unix time)}; taken out
# by the action it is used for.
CONFIRMED = "screening.identity_confirmed"
CONFIRMED_SECONDS = 5 * 60  # #505 acceptance 29

# A message for the confirm page (or the delete page), shown once; each provider's own are in
# provider_words.WORDS.
CONFIRM_ERROR = "screening.confirm_error"
EXPIRED = "確認已經過期，請再確認一次。"  # W18

# The providers to confirm with, in the order of their buttons: LINE above Google, the same
# buttons in the same order as on the login page (the #539 mockup 6, #506 acceptance 2). Not
# account settings' order (sign_in_methods.PROVIDERS, the newest last): on purpose.
ORDER = ("line", "google")


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
        # Removing has no page to go on to: it is done now, as the password does it (#506
        # acceptance 19), checked again in case the account changed during the trip.
        if action in REMOVES:
            return _remove(request, _to_remove(request.user, REMOVES[action]))
        _confirm(request, action)
    else:
        request.session[CONFIRM_ERROR] = WORDS[identity.provider].not_yours
    # The confirm page, which goes on to the action's page once confirmed.
    return redirect(identity.next)


def trip_failed(request, flow, message):
    """A confirm_identity trip that ended without an identity goes back to its confirm page,
    with its own words."""
    request.session[CONFIRM_ERROR] = WORDS[flow["provider"]].not_confirmed
    return redirect(flow["next"])


def providers(user):
    """The providers on the account that can be signed in with again, to confirm with; LINE
    first."""
    on_account = set(user.sign_in_methods.values_list("provider", flat=True))
    return [provider for provider in ORDER if provider in on_account and oidc.enabled(provider)]


def without_password(request):
    """What the confirm and delete pages offer an account without a password (#506 acceptance
    21): a button for each provider on the account, LINE first, and the providers' names for the
    line above them. Inside LINE Google refuses to sign in, so its button is left out; when it is
    the only one, a way out to Safari or Chrome takes its place (#511)."""
    on_account = providers(request.user)
    here = [provider for provider in on_account if works_here(request, provider)]
    return {
        "buttons": [
            {
                "provider": provider,
                "logo": provider_logo(provider),
                "words": WORDS[provider].confirm_button,
            }
            for provider in here
        ],
        "names": [SignInMethod.Provider(provider).label for provider in here or on_account],
        # None of the account's providers works here: only Google, inside LINE.
        "open_outside_url": line_way_out(request) if on_account and not here else "",
    }


def _to_remove(user, provider):
    """The account's sign-in with this provider, for 移除 Google／LINE 登入 (#505 acceptance
    26-28, #506 acceptance 18, 22): without the provider's keys or one on the account, 404; an
    admin account, or its only way in, 403."""
    if not oidc.enabled(provider):
        raise Http404
    if user.is_admin:
        raise PermissionDenied
    method = get_object_or_404(SignInMethod, user=user, provider=provider)
    if not method.can_be_removed():
        raise PermissionDenied
    return method


def _remove(request, method):
    method.delete()
    messages.success(request, WORDS[method.provider].removed)
    return HttpResponseRedirect(f"{reverse('account_settings')}#sign-in-methods")


@never_cache
@login_required
@require_http_methods(["GET", "POST"])  # the POST is the form's, with this site's CSRF token
def confirm_identity(request):
    action = request.GET.get("action")
    if action not in ACTIONS:
        raise Http404
    words, page = ACTIONS[action]
    # Refused before the password is asked for, as on the POST that removes it.
    removing = _to_remove(request.user, REMOVES[action]) if action in REMOVES else None
    # Back here already confirmed (from Google): on to the action's page.
    if page is not None and is_confirmed(request, action):
        return redirect(page)
    user = request.user
    form = None
    if user.has_usable_password():
        form = PasswordConfirmForm(request.POST if request.method == "POST" else None, user=user)
        if form.is_valid():
            if removing is not None:
                return _remove(request, removing)
            _confirm(request, action)
            return redirect(page)
    elif request.method == "POST":
        # No password: any provider on the account (Google asked to show its account chooser).
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
            "confirm_error": confirm_error(request),
            **without_password(request),
        },
    )
