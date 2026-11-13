"""The 登入方式 group in account settings (spec #505 acceptance 22-29, ADR 0057; spec #506
acceptance 15-18 for LINE): Google and LINE sign-in are added from there and removed from there,
each after 確認本人 (removing on the 確認本人 page itself, confirm_identity.py), and never down to
no way to sign in at all.
Admin accounts sign in with a password only, so they have no group and every request here is
refused."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from screening import oidc
from screening.models import SignInMethod
from screening.views import confirm_identity
from screening.views.common import line_way_out

# The rows after 帳號密碼, in this order (the #539 mockup D4: the newest last).
PROVIDERS = ("google", "line")

# Google: the #507 mockup W13, W14; LINE: the #539 mockup W7, W11. A trip that fails has no
# wording in either mockup (drafts for the owner).
TAKEN = {
    "google": "這個 Google 帳號已經用在另一個聽伴帳號，所以沒有新增。",
    "line": "這個 LINE 帳號已經用在另一個帳號。",
}
ADDED = {
    "google": "已新增 Google 登入。下次可以直接用 Google 登入。",
    "line": "已新增 LINE 登入。下次可以直接用 LINE 登入。",
}
NOT_ADDED = {
    "google": "沒有完成新增 Google 登入，請再試一次。",
    "line": "沒有完成新增 LINE 登入，請再試一次。",
}


def group(request):
    """What the account settings' 登入方式 group shows: a row per provider whose keys are set;
    None for an admin account, and without any provider's keys, when there is nothing to add or
    remove (#505, #506 acceptance 1)."""
    user = request.user
    providers = [provider for provider in PROVIDERS if oidc.enabled(provider)]
    if user.is_admin or not providers:
        return None
    methods = {method.provider: method for method in user.sign_in_methods.all()}
    # Inside LINE Google refuses to sign in, so a way out takes its 新增 button's place; LINE
    # itself works there as anywhere.
    way_out = line_way_out(request) if "google" in providers and "google" not in methods else ""
    rows = []
    for provider in providers:
        method = methods.get(provider)
        can_add = method is None and not (provider == "google" and way_out)
        rows.append(
            {
                "provider": provider,
                "name": SignInMethod.Provider(provider).label,
                "logo": f"screening/{provider}_logo.html",
                "method": method,
                "add_url": reverse(f"{provider}_add") if can_add else "",
                "can_remove": method is not None and method.can_be_removed(),
            }
        )
    return {
        "rows": rows,
        "only_way_in": any(row["method"] and not row["can_remove"] for row in rows),
        "can_change": any(row["add_url"] or row["can_remove"] for row in rows),
        "open_outside_url": way_out,
    }


def _add(request, provider):
    """新增 Google／LINE 登入: after 確認本人 straight on to the provider; came_back adds what
    comes back."""
    # Without the keys the provider does not exist on the site (acceptance 1); admin accounts
    # never have a sign-in method (#505 acceptance 28, #506 acceptance 22).
    if not oidc.enabled(provider):
        raise Http404
    if request.user.is_admin:
        raise PermissionDenied
    if request.user.sign_in_methods.filter(provider=provider).exists():
        return redirect("account_settings")
    action = f"add_{provider}"
    if not confirm_identity.use_confirmation(request, action):
        return confirm_identity.ask_confirmation(action)
    return HttpResponseRedirect(oidc.begin(request, provider, "add_method"))


@never_cache
@login_required
@require_http_methods(["GET"])
def google_add(request):
    return _add(request, "google")


@never_cache
@login_required
@require_http_methods(["GET"])
def line_add(request):
    return _add(request, "line")


def came_back(request, identity):
    """The provider's callback for an add_method trip (#505 acceptance 24, 25; #506 acceptance
    16, 17): the code is added to this account only when no account has it yet; the account's
    email stays as it is."""
    user = request.user
    # The trip starts only from google_add or line_add, signed in and not admin; checked again
    # where the row is written.
    if not user.is_authenticated or user.is_admin:
        raise PermissionDenied
    if SignInMethod.objects.for_identity(identity).exists():
        messages.error(request, TAKEN[identity.provider])
        return redirect("account_settings")
    try:
        with transaction.atomic():
            SignInMethod.objects.create(
                user=user,
                provider=identity.provider,
                subject=identity.subject,
                used_to_register=False,
            )
    except IntegrityError:
        # Another account took this code after the check; any other clash is a real error.
        if not SignInMethod.objects.for_identity(identity).exists():
            raise
        messages.error(request, TAKEN[identity.provider])
    else:
        messages.success(request, ADDED[identity.provider])
    return redirect("account_settings")


def trip_failed(request, flow, message):
    """An add_method trip that ended without an identity goes back to account settings, with its
    own words."""
    messages.error(request, NOT_ADDED[flow["provider"]])
    return redirect("account_settings")
