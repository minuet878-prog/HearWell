"""A thin OpenID Connect client for signing in with Google (spec #505, ADR 0056).

Python's own library only. begin() keeps what a trip needs in the session; finish() takes it out
again on the way back (once used, gone) and checks it before and after calling the provider.
Every call our server makes to a provider goes through post_to_provider(), the only thing tests
replace. Provider and purpose are parameters: LINE joins this flow in its own spec.
"""

import base64
import hashlib
import hmac
import http.client
import json
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse
from django.utils import timezone


@dataclass(frozen=True)
class Provider:
    authorize_url: str
    token_url: str
    issuers: tuple
    scope: str


# Google's discovery document (https://accounts.google.com/.well-known/openid-configuration).
PROVIDERS = {
    "google": Provider(
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        # Google's ID tokens carry either form (developers.google.com/identity/openid-connect).
        issuers=("https://accounts.google.com", "accounts.google.com"),
        # The `sub` and the email only: no name, no picture (spec #505, Q2).
        scope="openid email",
    ),
}

# The trip in the session: {"provider", "purpose", "state", "nonce", "code_verifier",
# "started_at" (a Unix time), "next"}. One at a time; a new trip replaces an unfinished one.
FLOW = "screening.oidc_flow"
FLOW_SECONDS = 10 * 60  # #505 acceptance 16
PROVIDER_TIMEOUT_SECONDS = 10


class SignInFailed(Exception):
    """The trip did not end with an identity."""


class Cancelled(SignInFailed):
    """The user said no on the provider's page (the callback carries `error`)."""


class Unavailable(SignInFailed):
    """The provider did not answer, or answered with an error, when we exchanged the code."""


class Rejected(SignInFailed):
    """The callback or the ID token failed a check: forged, replayed, too old or not for us."""


@dataclass(frozen=True)
class Identity:
    provider: str
    subject: str
    email: str
    email_verified: bool
    purpose: str
    next: str


def _setting(provider, name):
    return getattr(settings, f"{provider.upper()}_{name}")


def enabled(provider):
    """Whether the provider's keys are set; without them it does not exist on the site."""
    return bool(_setting(provider, "CLIENT_ID") and _setting(provider, "CLIENT_SECRET"))


def callback_url(provider):
    # A fixed string from SITE_URL, never from the request's Host header (#505 acceptance 21).
    return settings.SITE_URL + reverse(f"{provider}_callback")


def _code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def begin(request, provider, purpose, next_url=""):
    """Keep a new trip in the session and give the provider's authorize URL to send the user to.
    purpose: what the trip is for, one of the callback's (views/sign_in.py TRIPS), which hands
    the identity on by it."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)  # 86 characters; PKCE allows 43 to 128
    request.session[FLOW] = {
        "provider": provider,
        "purpose": purpose,
        "state": state,
        "nonce": nonce,
        "code_verifier": verifier,
        "started_at": timezone.now().timestamp(),
        "next": next_url,
    }
    query = {
        "response_type": "code",
        "client_id": _setting(provider, "CLIENT_ID"),
        "redirect_uri": callback_url(provider),
        "scope": PROVIDERS[provider].scope,
        "state": state,
        "nonce": nonce,
        "code_challenge": _code_challenge(verifier),
        "code_challenge_method": "S256",
    }
    if purpose in ("confirm_identity", "add_method"):
        # Google cannot be made to ask for the password again (no max_age, no prompt=login;
        # login-research.md section 8): its account chooser at least shows which Google is used,
        # to confirm with or to add. No login_hint, which would skip the chooser.
        query["prompt"] = "select_account"
    return f"{PROVIDERS[provider].authorize_url}?{urlencode(query)}"


def post_to_provider(url, fields):
    """Our server's one way of calling a provider: a form POST of fields to url. Gives the JSON
    answer, {} for an empty one, also when the provider refuses the request (HTTP 4xx, with an
    `error` in its JSON); raises Unavailable when there is no usable answer: no connection, a
    timeout, a server error (5xx), or an answer that is not a JSON object."""
    request = urllib.request.Request(
        url,
        data=urlencode(fields).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        try:
            with urllib.request.urlopen(request, timeout=PROVIDER_TIMEOUT_SECONDS) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            if error.code >= 500:
                raise
            with error:
                body = error.read()
        answer = json.loads(body) if body else {}
    except (OSError, http.client.HTTPException, ValueError) as error:
        # OSError covers URLError, a 5xx HTTPError and timeouts; HTTPException a connection cut
        # while reading; ValueError an answer that is not JSON.
        raise Unavailable(f"{url}: {type(error).__name__}") from error
    if not isinstance(answer, dict):
        raise Unavailable(f"{url}: not a JSON object")
    return answer


def _claims(id_token):
    """The ID token's payload. Its signature is not checked: the token comes straight from the
    provider's token endpoint over HTTPS for our client secret (Google's OpenID Connect docs)."""
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (AttributeError, IndexError, ValueError) as error:
        raise Rejected("unreadable ID token") from error
    if not isinstance(claims, dict):
        raise Rejected("unreadable ID token")
    return claims


def _same(a, b):
    # As bytes: compare_digest refuses str with anything but ASCII, and the callback's state or
    # the token's nonce can be anything.
    return isinstance(a, str) and isinstance(b, str) and hmac.compare_digest(a.encode(), b.encode())


def finish(request, provider):
    """Check the callback and the ID token; give who came back, or raise a SignInFailed."""
    # Out of the session before anything else: a callback is used once (#505 acceptance 18),
    # whatever comes of it, and before login() changes the session.
    flow = request.session.pop(FLOW, None)
    if flow is None or flow["provider"] != provider:
        raise Rejected("no trip in the session")
    if not _same(request.GET.get("state"), flow["state"]):
        raise Rejected("state does not match")
    now = timezone.now().timestamp()
    if now - flow["started_at"] > FLOW_SECONDS:
        raise Rejected("trip too old")
    # A cancel only once it is known to be this trip's, in time: anyone can send `error`.
    if "error" in request.GET:
        raise Cancelled(request.GET["error"])
    code = request.GET.get("code")
    if not code:
        raise Rejected("no code")
    # The code for tokens, at the provider's token endpoint.
    tokens = post_to_provider(
        PROVIDERS[provider].token_url,
        {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": flow["code_verifier"],
            "redirect_uri": callback_url(provider),
            "client_id": _setting(provider, "CLIENT_ID"),
            "client_secret": _setting(provider, "CLIENT_SECRET"),
        },
    )
    # An answer without an ID token (an error in its JSON, whatever its HTTP status) is the
    # provider not answering (#505 acceptance 20).
    if "id_token" not in tokens:
        raise Unavailable(f"{provider} token endpoint: no id_token")
    claims = _claims(tokens["id_token"])
    if claims.get("iss") not in PROVIDERS[provider].issuers:
        raise Rejected("iss is not the provider")
    if claims.get("aud") != _setting(provider, "CLIENT_ID"):
        raise Rejected("aud is not our client")
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) or exp <= now:
        raise Rejected("ID token expired")
    if not _same(claims.get("nonce"), flow["nonce"]):
        raise Rejected("nonce does not match")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise Rejected("no sub")
    email = claims.get("email")
    return Identity(
        provider=provider,
        subject=subject,
        email=email if isinstance(email, str) else "",
        # Google sends true; some older answers send the string "true".
        email_verified=claims.get("email_verified") in (True, "true"),
        purpose=flow["purpose"],
        next=flow["next"],
    )
