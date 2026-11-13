"""The 登入方式 group in account settings (spec #505 acceptance 22-29, ADR 0057): Google sign-in
is added from there and removed from there, each after 確認本人 (removing on the 確認本人 page
itself, confirm_identity.py), and never down to no way to sign in at all.
Admin accounts sign in with a password only, so they have no group and every request here is
refused."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from screening import oidc
from screening.models import SignInMethod
from screening.views import confirm_identity
from screening.views.common import line_way_out

# The #507 mockup W13, W14; a trip that fails has no wording there (a draft for the owner).
TAKEN = "這個 Google 帳號已經用在另一個聽伴帳號，所以沒有新增。"
ADDED = "已新增 Google 登入。下次可以直接用 Google 登入。"
NOT_ADDED = "沒有完成新增 Google 登入，請再試一次。"


def group(request):
    """What the account settings' 登入方式 group shows; None for an admin account, and without
    the Google keys, when there is nothing to add or remove (acceptance 1)."""
    user = request.user
    if user.is_admin or not oidc.enabled("google"):
        return None
    google = user.sign_in_methods.filter(provider=SignInMethod.Provider.GOOGLE).first()
    return {
        "google": google,
        "can_remove": google is not None and google.can_be_removed(),
        # Inside LINE Google refuses to sign in, so a way out takes the 新增 button's place.
        "open_outside_url": line_way_out(request),
    }


def _require_google_keys_and_not_admin(user):
    # Without the keys Google does not exist on the site (acceptance 1); admin accounts never
    # have a sign-in method (acceptance 28).
    if not oidc.enabled("google"):
        raise Http404
    if user.is_admin:
        raise PermissionDenied


@never_cache
@login_required
@require_http_methods(["GET"])
def google_add(request):
    """新增 Google 登入: after 確認本人 straight on to Google; came_back adds what comes back."""
    _require_google_keys_and_not_admin(request.user)
    if request.user.sign_in_methods.filter(provider=SignInMethod.Provider.GOOGLE).exists():
        return redirect("account_settings")
    if not confirm_identity.use_confirmation(request, "add_google"):
        return confirm_identity.ask_confirmation("add_google")
    return HttpResponseRedirect(oidc.begin(request, "google", "add_method"))


def came_back(request, identity):
    """The provider's callback for an add_method trip (acceptance 24, 25): the code is added to
    this account only when no account has it yet; the account's email stays as it is."""
    user = request.user
    # The trip starts only from google_add, signed in and not admin; checked again where the
    # row is written.
    if not user.is_authenticated or user.is_admin:
        raise PermissionDenied
    if SignInMethod.objects.for_identity(identity).exists():
        messages.error(request, TAKEN)
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
        # Another account took this Google after the check; any other clash is a real error.
        if not SignInMethod.objects.for_identity(identity).exists():
            raise
        messages.error(request, TAKEN)
    else:
        messages.success(request, ADDED)
    return redirect("account_settings")


def trip_failed(request, flow, message):
    """An add_method trip that ended without an identity goes back to account settings, with its
    own words."""
    messages.error(request, NOT_ADDED)
    return redirect("account_settings")
