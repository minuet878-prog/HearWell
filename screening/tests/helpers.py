import base64
import json
import re
from unittest.mock import patch
from urllib.parse import parse_qsl, urlsplit

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from screening import models, questionnaires
from screening.questionnaires import hhie_s
from screening.questionnaires.definition import Definition
from screening.questionnaires.results import GradedResult


def consented_user(**kwargs):
    """A user who has agreed to the current privacy notice, so health pages are open to them."""
    user = models.User.objects.create_user(**kwargs)
    user.give_consent()
    return user


def fake_definition(code, **overrides):
    fields = {
        "code": code,
        "topic": "假主題",
        "audience": "適合測試的人。",
        "minutes": 4,
        "icon": "clipboard",
        "list_rank": 2,
        "intro_template": "screening/questionnaires/hhie_s_intro.html",
        "result": GradedResult,  # without thresholds: graded 「無法判讀」
        "choices": hhie_s.choices,
    }
    return Definition(**(fields | overrides))


def submission_with_answers(user, code, scores, **fields):
    """A record of the questionnaire with this code, one answer per item in item-number order;
    a score of None is 「不適用」. fields: other Submission fields (wearing_hearing_aid, ...)."""
    questionnaire = models.Questionnaire.objects.get(code=code)
    submission = models.Submission.objects.create(user=user, questionnaire=questionnaire, **fields)
    models.Answer.objects.bulk_create(
        models.Answer(submission=submission, question=question, score=score)
        for question, score in zip(
            questionnaire.questions.order_by("question_number"), scores, strict=True
        )
    )
    return submission


def register(*definitions):
    """Registers fake questionnaire definitions for the length of one test."""
    return patch.dict(questionnaires.DEFINITIONS, {d.code: d for d in definitions})


ACTION_CARD = re.compile(
    r'<a class="link-card action-card" href="([^"]*)">.*?'
    r'<span class="link-card-title">([^<]*)</span>\s*<span>([^<]*)</span>',
    re.S,
)


def action_cards(html):
    """(href, title, line under it) of each action card (icon, title, one line, arrow)."""
    return ACTION_CARD.findall(html)


# A 選配路線 stop on my guide: its slug and markup, as far as the stop's own end, not one of
# the 您在這裡 card's to-dos (spec #478).
ROUTE_STOP = re.compile(
    r'<li class="route-stop[^"]*" data-stop="([^"]+)"[^>]*>(.*?)</li>'
    r'(?=\s*(?:<li class="route-stop|</ol>))',
    re.S,
)


def route_stops(html):
    """Each 選配路線 stop's (slug, markup) on my guide, in page order."""
    return ROUTE_STOP.findall(html)


def step_bar(response):
    """(done, total) segments of the step progress bar on a page, or None without one."""
    content = response.content.decode()
    bar = re.search(r'<div class="step-progress-bar" aria-hidden="true">(.*?)</div>', content, re.S)
    if bar is None:
        return None
    segments = re.findall(r'<span class="step-progress-segment( is-done)?"></span>', bar.group(1))
    return segments.count(" is-done"), len(segments)


# Spec #505: Google sign-in. Tests turn Google on with these settings; test_settings leaves it off.
GOOGLE_CLIENT_ID = "test-client.apps.googleusercontent.com"
google_on = override_settings(
    GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET="test-secret",
    SITE_URL="https://tingpal.test",
)
GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"


def id_token(**claims):
    """An ID token as Google's token endpoint returns it. Ours reads the payload without the
    signature (Google's docs allow it straight from the token endpoint), so it is left blank."""

    def part(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256', 'typ': 'JWT'})}.{part(claims)}.c2lnbmF0dXJl"


class FakeGoogle:
    """Google for a test: start() follows the Google button to the authorize URL, come_back()
    returns to our callback as Google would. Only screening.oidc.post_to_provider, our server's
    calls to a provider, is replaced: Google's token endpoint answers; state, nonce, PKCE and
    their expiry run for real.

        google = FakeGoogle(self.client)
        google.start()
        response = google.come_back(sub="google-1", email="lin.mei@example.com")
    """

    def __init__(self, client):
        self.client = client
        self.authorize = None  # the last authorize URL's query, one value per name
        self.exchanges = []  # the form fields of each call to Google's token endpoint

    def start(self, **params):
        response = self.client.get(reverse("google_start"), params)
        location = urlsplit(response["Location"])
        assert f"{location.scheme}://{location.netloc}{location.path}" == GOOGLE_AUTHORIZE
        self.authorize = dict(parse_qsl(location.query))
        return response

    def claims(self, sub, email, **overrides):
        """The ID token's claims Google would send back for this trip."""
        now = int(timezone.now().timestamp())
        return {
            "iss": "https://accounts.google.com",
            "aud": GOOGLE_CLIENT_ID,
            "sub": sub,
            "email": email,
            "email_verified": True,
            "iat": now,
            "exp": now + 3600,
            "nonce": self.authorize["nonce"],
        } | overrides

    def come_back(
        self,
        sub="google-sub-1",
        email="lin.mei@example.com",
        *,
        query=None,
        cancelled=False,
        exchange=None,
        **claims,
    ):
        """GET our callback. query: the callback's query instead of Google's code and state.
        cancelled: back as Google sends someone who said no (its error, this trip's state).
        exchange: what the token endpoint does instead of returning the ID token: an exception
        post_to_provider raises, or the JSON (a dict) it gives back."""
        if cancelled:
            query = {"error": "access_denied", "state": self.authorize["state"]}
        if query is None:
            query = {"code": "auth-code", "state": self.authorize["state"]}
        token = {
            "access_token": "never-kept",
            "id_token": id_token(**self.claims(sub, email, **claims)),
        }

        def fake_post(url, fields):
            assert url == GOOGLE_TOKEN, url
            self.exchanges.append(fields)
            if isinstance(exchange, dict):
                return exchange
            if exchange is not None:
                raise exchange
            return token

        with patch("screening.oidc.post_to_provider", side_effect=fake_post):
            return self.client.get(reverse("google_callback"), query)
