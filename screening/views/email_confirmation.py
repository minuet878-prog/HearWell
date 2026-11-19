from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from screening import email_confirmation
from screening.views.common import email_link_page, form_address

PAGE = "screening/email_confirm.html"


@require_http_methods(["GET", "POST"])
def email_confirm(request, token):
    """The 確認信's link (docs/design/email-confirmation-mockup.html 3a-3c), signed in or not:
    GET asks, since a mail program's link scanner opens it too; POST confirms."""
    user = email_confirmation.account_for(token)
    if user is None:
        return email_link_page(request, PAGE, status=404)
    if request.method == "POST":
        user.confirmed_email = user.email
        user.save(update_fields=["confirmed_email"])
        return email_link_page(request, PAGE, {"user_to_confirm": user, "confirmed": True})
    return email_link_page(request, PAGE, {"user_to_confirm": user})


@form_address
def email_confirm_resend(request):
    """The account settings' 重寄確認信 (mockup 4), for request.user's own email."""
    user = request.user
    if user.email and not user.email_confirmed:
        email_confirmation.resend(request)
    return HttpResponseRedirect(reverse("account_settings"))
