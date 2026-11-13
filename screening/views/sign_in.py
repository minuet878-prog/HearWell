"""Signing up and in with Google (spec #505, ADR 0056, ADR 0057)."""

import logging

from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import redirect_to_login
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from screening import oidc
from screening.forms import GoogleNameForm
from screening.models import SignInMethod, User
from screening.views import confirm_identity
from screening.views.accounts import NEW_ACCOUNT
from screening.views.common import SIGN_IN_ERROR, safe_next, sign_in_choices

logger = logging.getLogger(__name__)

# The words a Google trip comes back with (the #507 mockup W4-W7, W10); technical details go to
# error monitoring only.
CANCELLED = "沒有完成 Google 登入。可以再試一次，或用帳號密碼登入。"
UNAVAILABLE = "Google 暫時沒有回應，請稍後再試，或用帳號密碼登入。"
FAILED = "登入沒有完成，請再試一次。"
UNVERIFIED = "這個 Google 帳戶的 email 還沒有驗證，沒辦法用來註冊。請改用帳號密碼註冊。"
NAME_EXPIRED = "等太久了，請再按一次「使用 Google 帳戶登入」。"
# #505 acceptance 11 (no wording in the mockup; a draft for the owner to settle).
ADMIN = "這個帳號請用帳號密碼登入。"

# Who came back from Google for the first time, until the name page makes the account:
# {"provider", "subject", "email", "purpose", "next", "at" (a Unix time)}.
PENDING = "screening.oidc_identity"
PENDING_SECONDS = 10 * 60  # #505 acceptance 7


class LoginView(auth_views.LoginView):
    """Django's login page, with the Google button above the password form (spec #505)."""

    template_name = "screening/login.html"
    http_method_names = ("get", "post")

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | sign_in_choices(self.request)


def _require_google():
    # Without the keys Google does not exist on the site (#505 acceptance 1).
    if not oidc.enabled("google"):
        raise Http404


def _back_to(page, request, message):
    request.session[SIGN_IN_ERROR] = message
    return redirect(page)


@require_http_methods(["GET"])
def google_start(request):
    _require_google()
    return HttpResponseRedirect(oidc.begin(request, "google", "sign_in", safe_next(request)))


@require_http_methods(["GET"])
def google_callback(request):
    _require_google()
    # Read before finish() takes the trip out: where a trip that fails goes back to.
    flow = request.session.get(oidc.FLOW) or {}
    try:
        identity = oidc.finish(request, "google")
    except oidc.Cancelled:
        return _failed(request, flow, CANCELLED)
    except oidc.Unavailable:
        logger.exception("Google token exchange failed")
        return _failed(request, flow, UNAVAILABLE)
    except oidc.Rejected as error:
        logger.warning("Google callback rejected: %s", error)
        return _failed(request, flow, FAILED)
    # The later purposes (add_method #511, save_card #513) add theirs.
    handlers = {"sign_in": _sign_in, "confirm_identity": confirm_identity.came_back}
    return handlers[identity.purpose](request, identity)


def _failed(request, flow, message):
    # 確認本人 goes back to its own page (#510); anything else to the login page.
    if flow.get("purpose") == "confirm_identity":
        return confirm_identity.trip_failed(request, flow)
    return _back_to("login", request, message)


def _sign_in(request, identity):
    method = (
        SignInMethod.objects.select_related("user")
        .filter(provider=identity.provider, subject=identity.subject)
        .first()
    )
    if method is not None:
        user = method.user
        # Admin accounts sign in with a password only (#505 acceptance 11, Q16); login() skips
        # the backend's is_active check, so a deactivated account is turned away here.
        if user.is_staff or user.is_superuser:
            return _back_to("login", request, ADMIN)
        if not user.is_active:
            return _back_to("login", request, FAILED)
        login(request, user)
        return HttpResponseRedirect(identity.next or reverse("consent"))
    # Never seen: only an email Google says is verified becomes an account's (Q3, acceptance 9).
    if not identity.email_verified or not identity.email:
        return _back_to("register", request, UNVERIFIED)
    request.session[PENDING] = {
        "provider": identity.provider,
        "subject": identity.subject,
        "email": identity.email,
        "purpose": identity.purpose,
        "next": identity.next,
        "at": timezone.now().timestamp(),
    }
    # An email already on an account (any case) is never signed into nor merged (ADR 0057).
    if User.objects.filter(email__iexact=identity.email).exists():
        return redirect("google_same_email")
    return redirect("google_name")


def _pending(request):
    """The identity waiting for its name, or None when there is none or it is too old (removed)."""
    pending = request.session.get(PENDING)
    if pending is None or pending["provider"] != "google":
        return None
    if timezone.now().timestamp() - pending["at"] > PENDING_SECONDS:
        del request.session[PENDING]
        return None
    return pending


@never_cache  # it shows the Google email
@require_http_methods(["GET", "POST"])
def google_name(request):
    """#505 acceptance 5-7: the first time back from Google, a name (and a birth year) before the
    account is made; leaving here makes nothing."""
    _require_google()
    pending = _pending(request)
    if pending is None:
        return _back_to("login", request, NAME_EXPIRED)
    form = GoogleNameForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        try:
            with transaction.atomic():
                user = form.save(email=pending["email"])
                SignInMethod.objects.create(
                    user=user,
                    provider=pending["provider"],
                    subject=pending["subject"],
                    used_to_register=True,
                )
        except IntegrityError:
            # Someone else took this name after is_valid(); any other clash is a real error.
            if not User.objects.filter(username=form.cleaned_data["username"]).exists():
                raise
            form.add_error("username", form.instance.unique_error_message(User, ["username"]))
        else:
            del request.session[PENDING]
            login(request, user)
            # As registering with a password does: the consent page greets a new account (#152).
            request.session[NEW_ACCOUNT] = True
            if pending["next"]:
                return redirect_to_login(pending["next"], reverse("consent"))
            return redirect("consent")
    return render(request, "screening/google_name.html", {"form": form, "email": pending["email"]})


@never_cache  # it shows the Google email
@require_http_methods(["GET"])
def google_same_email(request):
    """#505 acceptance 12-14 (the #507 mockup 4, W11): the Google email is already some account's.
    Nobody is signed in; the identity waits, as for the name page, in case it is not theirs."""
    _require_google()
    pending = _pending(request)
    if pending is None:
        return _back_to("login", request, NAME_EXPIRED)
    # After the password, back to account settings to add Google there (acceptance 14).
    # #511: point this at its 登入方式 section (an anchor survives as the login page's next).
    password_next = reverse("account_settings")
    return render(
        request,
        "screening/google_same_email.html",
        {"email": pending["email"], "password_next": password_next},
    )
