"""Where a user stands in the main flow: new/old, last result, retest reminder (ADR 0010)."""

from dataclasses import dataclass
from datetime import date

from django.utils import timezone

from screening.fitting_route import add_months
from screening.forms import AgeGroupForm
from screening.ioi_norm import norm_bases
from screening.questionnaires import hhia_s, hhie_s, ioi_ha
from screening.questionnaires.definition import RETEST_MONTHS
from screening.scoring import (
    CATALOGUE_REASONS,
    RETEST_BUTTON_TEXT,
    RETEST_DUE_TEXT,
    retest_next_text,
)


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
    reminder: str | None = None  # my records' retest line
    retest_button: str | None = None  # the retake button's text, once a retest is due


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
    life_impact = [s for s in submissions if s.questionnaire.definition.life_impact]
    if life_impact:
        latest = life_impact[0]
        next_date = add_months(timezone.localtime(latest.created_at).date(), RETEST_MONTHS)
        due = next_date <= today
        return UserState(
            is_new=False,
            last_result=LastResult(submission=latest, is_life_impact=True),
            retest_due=due,
            next_suggested_date=None if due else next_date,
            retest_questionnaire=latest.questionnaire,
            reminder=RETEST_DUE_TEXT if due else retest_next_text(next_date),
            retest_button=RETEST_BUTTON_TEXT if due else None,
        )
    latest = submissions[0]
    return UserState(
        is_new=False,
        last_result=LastResult(submission=latest, is_life_impact=False),
        retest_due=False,
        next_suggested_date=None,
        retest_questionnaire=None,
    )


def life_impact_questionnaire(user, questionnaires, state, age_group):
    """The life-impact questionnaire to recommend (ADR 0030), one of `questionnaires`: the one of
    the latest life-impact record (`state`, the user's get_user_state()), so retests compare and
    the trend chart goes on; without one, by age, from the birth year or else `age_group`
    (AgeGroupForm's value, or None). None when the age is still needed: no birth year, or one
    that cannot tell 64 from 65."""
    life_impact = [q for q in questionnaires if q.definition.life_impact]
    if state.retest_questionnaire is not None:
        return next(q for q in life_impact if q.pk == state.retest_questionnaire.pk)
    age = user.age
    if age is not None and age != 65:
        age_group = AgeGroupForm.OLDER if age > 65 else AgeGroupForm.ADULT
    if age_group is None:
        return None
    return next(q for q in life_impact if q.code == age_group_code(age_group))


def age_group_code(age_group):
    """The life-impact questionnaire's code for AgeGroupForm's value: HHIE-S from 65 on."""
    return hhie_s.CODE if age_group == AgeGroupForm.OLDER else hhia_s.CODE


@dataclass(frozen=True)
class Recommendation:
    questionnaires: list  # two only for a life-impact one when the age is unknown
    why: str


def catalogue_recommendation(user, questionnaires, state):
    """The 推薦問卷 (GLOSSARY) on top of a returning user's catalogue, apart from the home page's
    建議下一步 (ADR 0030): by the first of #347's rules that holds, or None when none does.
    `questionnaires`: the catalogue's, in its order; `state`: the user's get_user_state()."""
    if state.retest_due or state.retest_questionnaire is None:  # None: no life-impact record
        why = CATALOGUE_REASONS["retest" if state.retest_due else "no_life_impact"]
        life_impact = life_impact_questionnaire(user, questionnaires, state, None)
        if life_impact is None:  # the age is unknown: both, each saying whom it suits
            return Recommendation([q for q in questionnaires if q.definition.life_impact], why)
        return Recommendation([life_impact], why)
    # Worn: answered wearing hearing aids, SADL always. IOI-HA saves no wearing status, but a
    # record of it already rules this one out.
    if (
        user.submissions.defined().filter(wearing_hearing_aid=True).exists()
        and norm_bases(user).exists()
        and not user.submissions.filter(questionnaire__code=ioi_ha.CODE).exists()
    ):
        ioi = next(q for q in questionnaires if q.code == ioi_ha.CODE)
        return Recommendation([ioi], CATALOGUE_REASONS["aided_and_unaided"])
    return None
