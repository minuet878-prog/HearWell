import re
from unittest.mock import patch

from screening import models, questionnaires
from screening.questionnaires import hhie_s
from screening.questionnaires.definition import LEVEL, Definition


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
        "result": LEVEL,  # without thresholds: graded 「無法判讀」
        "choices": hhie_s.choices,
    }
    return Definition(**(fields | overrides))


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


def step_bar(response):
    """(done, total) segments of the step progress bar on a page, or None without one."""
    content = response.content.decode()
    bar = re.search(r'<div class="step-progress-bar" aria-hidden="true">(.*?)</div>', content, re.S)
    if bar is None:
        return None
    segments = re.findall(r'<span class="step-progress-segment( is-done)?"></span>', bar.group(1))
    return segments.count(" is-done"), len(segments)
