from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from screening import models
from screening.forms import ROC_OFFSET, DeleteAccountForm, RegisterForm
from screening.models import User
from screening.views.common import health_data_page, safe_next


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


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
    return render(request, "screening/register.html", {"form": form, "next": next_url})


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
        {"consent": consent, "share": share, "roc_birth_year": roc_birth_year},
    )


@login_required
@require_http_methods(["GET", "POST"])
def delete_account(request):
    user = request.user
    # Staff could lock everyone out of admin; they remove their staff rights first.
    if user.is_staff or user.is_superuser:
        status = 403 if request.method == "POST" else 200
        return render(request, "screening/delete_account.html", {"is_admin": True}, status=status)
    form = DeleteAccountForm(request.POST if request.method == "POST" else None, user=user)
    if form.is_valid():
        user.delete_with_data()
        logout(request)
        messages.success(request, "您的帳號和資料已經刪除。")
        return redirect("index")
    return render(
        request,
        "screening/delete_account.html",
        {
            "form": form,
            "submission_count": user.submissions.count(),
            "audiogram_count": user.audiograms.count(),
        },
    )
