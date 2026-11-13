"""The 登入方式 group in account settings (spec #505 acceptance 22-29, ADR 0057): Google sign-in
is added and removed there, each after 確認本人, and never down to no way to sign in at all.
Admin accounts sign in with a password only, so they have no group and every request here is
refused."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from screening import oidc
from screening.models import SignInMethod
from screening.views import confirm_identity
from screening.views.common import line_way_out

# The #507 mockup W13, W14; a trip that fails has no wording there (a draft for the owner).
TAKEN = "這個 Google 帳號已經用在另一個聽伴帳號，所以沒有新增。"
ADDED = "已新增 Google 登入。下次可以直接用 Google 登入。"
REMOVED = "已移除 Google 登入。"
NOT_ADDED = "沒有完成新增 Google 登入，請再試一次。"


def _is_admin(user):
    return user.is_staff or user.is_superuser


def _keeps_a_way_in(user, method):
    """Whether the account can still be signed into without this method (acceptance 27): a
    usable password, or another sign-in method."""
    return user.has_usable_password() or user.sign_in_methods.exclude(pk=method.pk).exists()


def group(request):
    """What the account settings' 登入方式 group shows; None for an admin account, and without
    the Google keys, when there is nothing to add or remove (acceptance 1)."""
    user = request.user
    if _is_admin(user) or not oidc.enabled("google"):
        return None
    google = user.sign_in_methods.filter(provider=SignInMethod.Provider.GOOGLE).first()
    return {
        "google": google,
        "can_remove": google is not None and _keeps_a_way_in(user, google),
        # Inside LINE Google refuses to sign in, so a way out takes the 新增 button's place.
        "open_outside_url": line_way_out(request),
    }


def _require_google(user):
    # Without the keys Google does not exist on the site (acceptance 1); admin accounts never
    # have a sign-in method (acceptance 28).
    if not oidc.enabled("google"):
        raise Http404
    if _is_admin(user):
        raise PermissionDenied


@never_cache
@login_required
@require_http_methods(["GET"])
def google_add(request):
    """新增 Google 登入: after 確認本人 straight on to Google; came_back adds what comes back."""
    _require_google(request.user)
    if request.user.sign_in_methods.filter(provider=SignInMethod.Provider.GOOGLE).exists():
        return redirect("account_settings")
    if not confirm_identity.use_confirmation(request):
        return confirm_identity.ask_confirmation("add_google")
    return HttpResponseRedirect(oidc.begin(request, "google", "add_method"))


def came_back(request, identity):
    """The provider's callback for an add_method trip (acceptance 24, 25): the code is added to
    this account only when no account has it yet; the account's email stays as it is."""
    user = request.user
    # The trip starts only from google_add, signed in and not admin; checked again where the
    # row is written.
    if not user.is_authenticated or _is_admin(user):
        raise PermissionDenied
    if SignInMethod.objects.filter(provider=identity.provider, subject=identity.subject).exists():
        messages.error(request, TAKEN)
    else:
        SignInMethod.objects.create(
            user=user, provider=identity.provider, subject=identity.subject, used_to_register=False
        )
        messages.success(request, ADDED)
    return redirect("account_settings")


def trip_failed(request):
    """An add_method trip that ended without an identity goes back to account settings."""
    messages.error(request, NOT_ADDED)
    return redirect("account_settings")


@never_cache
@login_required
@require_http_methods(["GET"])
def google_remove(request):
    """移除 Google 登入 after 確認本人, unless it is the account's only way in (acceptance 26,
    27)."""
    _require_google(request.user)
    method = get_object_or_404(
        SignInMethod, user=request.user, provider=SignInMethod.Provider.GOOGLE
    )
    if not _keeps_a_way_in(request.user, method):
        raise PermissionDenied
    if not confirm_identity.use_confirmation(request):
        return confirm_identity.ask_confirmation("remove_google")
    method.delete()
    messages.success(request, REMOVED)
    return redirect("account_settings")
