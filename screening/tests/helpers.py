from unittest.mock import patch

from screening import models, questionnaires
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
    }
    return Definition(**(fields | overrides))


def register(*definitions):
    """Registers fake questionnaire definitions for the length of one test."""
    return patch.dict(questionnaires.DEFINITIONS, {d.code: d for d in definitions})
