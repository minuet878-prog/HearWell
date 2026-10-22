"""Where a user stands in the main flow: new/old, last result, retest reminder (ADR 0010)."""

import calendar
from dataclasses import dataclass
from datetime import date

from django.utils import timezone

from screening.questionnaires.definition import LEVEL, RETEST_MONTHS
from screening.scoring import RETEST_DUE_TEXT, retest_next_text


def _add_months(start, months):
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(frozen=True)
class LastResult:
    submission: object
    is_life_impact: bool  # a level + classified text, vs. another questionnaire's summary


@dataclass(frozen=True)
class UserState:
    is_new: bool
    last_result: LastResult | None
    retest_due: bool
    next_suggested_date: date | None
    retest_questionnaire: object | None  # the questionnaire "再做一次" should open
    reminder: str | None = None  # the home page's retest line


NEW_USER_STATE = UserState(
    is_new=True,
    last_result=None,
    retest_due=False,
    next_suggested_date=None,
    retest_questionnaire=None,
)


def get_user_state(user, today):
    submissions = list(
        user.submissions.defined().select_related("questionnaire").with_scores()
    )  # newest first
    if not submissions:
        return NEW_USER_STATE
    life_impact = [s for s in submissions if s.questionnaire.definition.result == LEVEL]
    if life_impact:
        latest = life_impact[0]
        next_date = _add_months(timezone.localtime(latest.created_at).date(), RETEST_MONTHS)
        due = next_date <= today
        return UserState(
            is_new=False,
            last_result=LastResult(submission=latest, is_life_impact=True),
            retest_due=due,
            next_suggested_date=None if due else next_date,
            retest_questionnaire=latest.questionnaire,
            reminder=RETEST_DUE_TEXT if due else retest_next_text(next_date),
        )
    latest = submissions[0]
    return UserState(
        is_new=False,
        last_result=LastResult(submission=latest, is_life_impact=False),
        retest_due=False,
        next_suggested_date=None,
        retest_questionnaire=None,
    )
