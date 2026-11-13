import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_http_methods
from rest_framework.throttling import BaseThrottle

from screening import models
from screening.forms import (
    RESETS_PER_ADDRESS,
    ROC_OFFSET,
    TOO_MANY_RESETS,
    ForgotPasswordForm,
    PasswordConfirmForm,
    RegisterForm,
    ResetEmailNotSent,
    SetNewPasswordForm,
    add_attempt,
    attempts,
    may_reset_password,
)
from screening.models import User
from screening.views import confirm_identity, sign_in_methods
from screening.views.common import health_data_page, safe_next, sign_in_choices


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


logger = logging.getLogger(__name__)

# Set when an account is made; only then does agreeing on the consent page greet the user (#152).
NEW_ACCOUNT = "screening.new_account"


@require_http_methods(["GET", "POST"])
def register(request):
    next_url = safe_next(request)
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
            except IntegrityError:
                # Someone else took this name after is_valid(); any other clash is a real error.
                if not User.objects.filter(username=form.cleaned_data["username"]).exists():
                    raise
                form.add_error("username", form.instance.unique_error_message(User, ["username"]))
            else:
                login(request, user)
                request.session[NEW_ACCOUNT] = True
                # New accounts agree to the privacy notice before anything else.
                if next_url:
                    return redirect_to_login(next_url, reverse("consent"))
                return redirect("consent")
    else:
        form = RegisterForm()
    return render(
        request,
        "screening/register.html",
        {"form": form, "next": next_url} | sign_in_choices(request),
    )


# Spec #355: the email typed on the forgot-password page, for the next page to show; kept in the
# session so it never goes into an address.
RESET_EMAIL = "screening.reset_email"


class ForgotPasswordView(auth_views.PasswordResetView):
    template_name = "screening/password_reset_form.html"
    form_class = ForgotPasswordForm
    subject_template_name = "screening/password_reset_subject.txt"
    email_template_name = "screening/password_reset_email.txt"
    html_email_template_name = "screening/password_reset_email.html"
    success_url = reverse_lazy("password_reset_sent")

    def post(self, request, *args, **kwargs):
        # #528: the address as the guest scoring limit takes it (NUM_PROXIES: X-Forwarded-For's
        # last, which Nginx adds). Past the limit the email is not looked up at all, so the page
        # cannot tell whether it is registered.
        address = BaseThrottle().get_ident(request)
        if attempts("address", address) >= RESETS_PER_ADDRESS:
            form = self.form_class(initial={"email": request.POST.get("email", "")})
            return self.render_to_response(
                self.get_context_data(form=form, too_many=TOO_MANY_RESETS)
            )
        add_attempt("address", address)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        add_attempt("email", email)
        try:
            response = super().form_valid(form)
        except ResetEmailNotSent:
            # #529: the page says so. A fixed message: the mail service's own words may hold the
            # email (Sentry drops them too).
            logger.exception("A password reset email could not be sent")
            return self.render_to_response(self.get_context_data(form=form, send_failed=True))
        self.request.session[RESET_EMAIL] = email
        return response


@require_http_methods(["GET"])
def password_reset_sent(request):
    email = request.session.get(RESET_EMAIL)
    if not email:
        return redirect("password_reset")
    return render(request, "screening/password_reset_sent.html", {"email": email})


class SetNewPasswordView(auth_views.PasswordResetConfirmView):
    """Spec #355: a valid link sets the password and signs in, then the consent page sends on
    those who already agreed; an expired or used link shows its own words on the same address."""

    template_name = "screening/password_reset_confirm.html"
    form_class = SetNewPasswordForm
    post_reset_login = True
    success_url = reverse_lazy("consent")

    def get_user(self, uidb64):
        # An account made an administrator or inactive after the email went out: an expired link.
        user = super().get_user(uidb64)
        return user if user is not None and may_reset_password(user) else None

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "密碼改好了")
        return response


def privacy(request):
    return render(
        request,
        "screening/privacy.html",
        {"version": models.CONSENT_VERSION, "updated_on": models.PRIVACY_UPDATED_ON},
    )


@login_required
@require_http_methods(["GET", "POST"])
def consent(request):
    next_url = safe_next(request)
    if request.method == "POST" and "decline" in request.POST:
        logout(request)
        messages.info(
            request,
            "沒有同意就不能使用篩檢功能，您的帳號仍在。想使用時，登入後按「我同意，開始篩檢」即可。",
        )
        return redirect("index")
    if request.method == "POST" and "agree" in request.POST and not request.user.has_consented():
        request.user.give_consent()
        # Right after registering, into the wizard: its first screen then says the account is
        # ready (#152). Popped on any agreeing, so agreeing again later says nothing.
        parts = urlsplit(next_url)
        if request.session.pop(NEW_ACCOUNT, False) and parts.path == reverse("questionnaire_list"):
            query = urlencode(
                [*parse_qsl(parts.query, keep_blank_values=True), ("from", "consent")]
            )
            return HttpResponseRedirect(urlunsplit(parts._replace(query=query)))
    if request.user.has_consented():
        return HttpResponseRedirect(next_url or reverse("index"))
    return render(request, "screening/consent.html", {"next": next_url})


@login_required
@require_http_methods(["GET"])
@health_data_page
def account_settings(request):
    # Spec phase9_ui_refresh_3_structure.md 4.1: request.user's own account, to look at only.
    user = request.user
    consent = (
        user.consents.filter(version__gte=models.CONSENT_VERSION).order_by("-agreed_at").first()
    )
    # #195: the share status reads only request.user's own live link.
    share = user.report_shares.active().first()
    roc_birth_year = None if user.birth_year is None else user.birth_year - ROC_OFFSET
    return render(
        request,
        "screening/account.html",
        {
            "consent": consent,
            "share": share,
            "roc_birth_year": roc_birth_year,
            "sign_in_methods": sign_in_methods.group(request),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def delete_account(request):
    user = request.user
    # Staff could lock everyone out of admin; they remove their staff rights first.
    if user.is_admin:
        status = 403 if request.method == "POST" else 200
        return render(request, "screening/delete_account.html", {"is_admin": True}, status=status)
    if user.has_usable_password():
        form = PasswordConfirmForm(request.POST if request.method == "POST" else None, user=user)
        delete = form.is_valid()
    else:
        # #505 acceptance 30, #506 acceptance 20: without a password, 確認本人 with a provider on
        # the account first; a confirmation gone stale meanwhile sends the page back with W18.
        form = None
        delete = request.method == "POST" and confirm_identity.use_confirmation(
            request, "delete_account"
        )
        if request.method == "POST" and not delete:
            return redirect("delete_account")
    if delete:
        user.delete_with_data()
        logout(request)
        messages.success(request, "您的帳號和資料已經刪除。")
        return redirect("index")
    return render(
        request,
        "screening/delete_account.html",
        {
            "form": form,
            "confirmed": form is None and confirm_identity.is_confirmed(request, "delete_account"),
            "confirm_error": confirm_identity.confirm_error(request),
            "sign_in_methods": user.sign_in_methods.all(),
            **confirm_identity.without_password(request),
            "submission_count": user.submissions.count(),
            "audiogram_count": user.audiograms.count(),
        },
    )
