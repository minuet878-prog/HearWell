"""確認信 (security check 2026-11-19, the owner's picks and mockup docs/design/
email-confirmation-mockup.html): an email typed on the site gets the 重設密碼信 and the 重測提醒
only once its owner has pressed 確認信箱 in the 確認信. Otherwise a mistyped address, or someone
else's typed on purpose, would let that mailbox's owner set the account's password, or make the
site write to anyone.
"""

import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from django.urls import reverse

from screening.forms import HELP_ADDRESS, add_attempt, attempts
from screening.models import User

logger = logging.getLogger(__name__)

SALT = "screening.email_confirmation"
GOOD_FOR = 3 * 24 * 60 * 60  # 3 days (the owner's pick)
RESENDS_PER_HOUR = 3
SENT = "已寄確認信到 {email}。請在 3 天內打開信，按「確認信箱」。沒收到的話，可以到帳號設定重寄。"
NOT_SENT = "確認信寄不出去，請稍後到帳號設定重寄。"
TOO_MANY = "試太多次了，請一小時後再試"


def _link(request, user):
    token = signing.dumps({"user": user.pk, "email": user.email}, salt=SALT)
    path = reverse("email_confirm", args=[token])
    # From SITE_URL, never the request's Host header, like the 重設密碼信; the page's own address
    # only in development.
    return settings.SITE_URL + path if settings.SITE_URL else request.build_absolute_uri(path)


def send(request, user):
    """Sends user's email its 確認信 and says so on the next page."""
    link = _link(request, user)
    context = {"user": user, "link": link, "domain": urlsplit(link).netloc}
    message = EmailMultiAlternatives(
        "聽伴 確認您的信箱",
        loader.render_to_string("screening/email_confirmation_email.txt", context),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        reply_to=[HELP_ADDRESS],
    )
    message.attach_alternative(
        loader.render_to_string("screening/email_confirmation_email.html", context), "text/html"
    )
    try:
        message.send()
    except Exception:
        # A fixed message: the mail service's own words may hold the email (config.monitoring).
        logger.exception("An email confirmation could not be sent")
        messages.warning(request, NOT_SENT)
    else:
        messages.info(request, SENT.format(email=user.email))


def resend(request):
    """The account settings' 重寄確認信: 3 an hour for one account."""
    account = str(request.user.pk)
    if attempts("email-confirmation", account) >= RESENDS_PER_HOUR:
        messages.warning(request, TOO_MANY)
        return
    add_attempt("email-confirmation", account)
    send(request, request.user)


def reading(token):
    """The account the link was sent for, while it is active and its email the one sent to;
    None for a link expired, changed, or for an email changed since."""
    try:
        sent = signing.loads(token, salt=SALT, max_age=GOOD_FOR)
    except signing.BadSignature:
        return None
    user = User.objects.filter(pk=sent.get("user"), is_active=True).first()
    if user is None or not user.email or user.email != sent.get("email"):
        return None
    return user
