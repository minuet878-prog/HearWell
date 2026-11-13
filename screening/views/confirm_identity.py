"""確認本人 (spec #505, ADR 0057): before deleting the account, or adding or removing a sign-in
method, the account's owner shows it is them: with the password when the account has one,
otherwise by signing in again with a provider already on the account, which must give back
that account's code (`sub`). It holds for 5 minutes and for one action.

For a view that needs it (#511):

    if not use_confirmation(request):
        return ask_confirmation("add_google")
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from screening import oidc
from screening.forms import PasswordConfirmForm

# What the confirmation is for: the words after 「接下來要」 (the #507 mockup W15) and the page it
# leads back to. #511 adds add_google and remove_google.
ACTIONS = {
    "delete_account": ("刪除帳號", "delete_account"),
}

# When the owner last confirmed (a Unix time); taken out by the action it is used for.
CONFIRMED = "screening.identity_confirmed"
CONFIRMED_SECONDS = 5 * 60  # #505 acceptance 29

# A message for the confirm page (or the delete page), shown once.
CONFIRM_ERROR = "screening.confirm_error"
NOT_YOURS = "這不是您帳號上的 Google。請改用註冊時用的那個 Google 帳戶。"  # W16
EXPIRED = "確認已經過期，請再確認一次。"  # W18
# Cancelled, refused or Google down: no wording in the mockup (a draft for the owner to settle).
NOT_CONFIRMED = "沒有完成 Google 確認，請再試一次。"


def _fresh(confirmed_at):
    return (
        confirmed_at is not None and timezone.now().timestamp() - confirmed_at <= CONFIRMED_SECONDS
    )


def is_confirmed(request):
    """Whether the owner confirmed in the last 5 minutes; leaves the confirmation in place."""
    return _fresh(request.session.get(CONFIRMED))


def use_confirmation(request):
    """Take the confirmation out of the session for the one action it allows: True when it is
    from the last 5 minutes. A stale one is dropped and the next page says so (W18)."""
    confirmed_at = request.session.pop(CONFIRMED, None)
    if _fresh(confirmed_at):
        return True
    if confirmed_at is not None:
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
    if request.user.sign_in_methods.filter(
        provider=identity.provider, subject=identity.subject
    ).exists():
        request.session[CONFIRMED] = timezone.now().timestamp()
    else:
        request.session[CONFIRM_ERROR] = NOT_YOURS
    # The confirm page, which goes on to the action's page once confirmed.
    return redirect(identity.next)


def trip_failed(request, flow):
    """A confirm_identity trip that ended without an identity goes back to its confirm page."""
    request.session[CONFIRM_ERROR] = NOT_CONFIRMED
    return redirect(flow["next"])


def providers(user):
    """The providers on the account that can be signed in with again, to confirm with."""
    return [
        provider
        for provider in user.sign_in_methods.values_list("provider", flat=True)
        if oidc.enabled(provider)
    ]


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def confirm_identity(request):
    action = request.GET.get("action")
    if action not in ACTIONS:
        raise Http404
    words, page = ACTIONS[action]
    if is_confirmed(request):
        return redirect(page)
    user = request.user
    form = None
    if user.has_usable_password():
        form = PasswordConfirmForm(request.POST if request.method == "POST" else None, user=user)
        if form.is_valid():
            request.session[CONFIRMED] = timezone.now().timestamp()
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
            "confirm_error": confirm_error(request),
        },
    )
