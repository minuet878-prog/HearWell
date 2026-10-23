"""Where a user stands in the main flow: new/old, last result, retest reminder (ADR 0010)."""

import calendar
from dataclasses import dataclass
from datetime import date

from django.urls import reverse
from django.utils import timezone

from screening.fitting_route import AUDIOGRAM, fitting_state
from screening.questionnaires.definition import RETEST_MONTHS
from screening.scoring import (
    NEXT_STEP_REASONS,
    RETEST_BUTTON_TEXT,
    RETEST_DUE_TEXT,
    retest_next_text,
)


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
        next_date = _add_months(timezone.localtime(latest.created_at).date(), RETEST_MONTHS)
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


@dataclass(frozen=True)
class HomeCard:
    title: str
    href: str
    icon: str  # an action_icon.html icon


@dataclass(frozen=True)
class NextStep:
    card: HomeCard
    because: str
    button: str


# #261 (spec #257): the returning user's 「您還可以」 cards in four groups by use, each
# (key, title, card keys).
HOME_GROUPS = (
    ("record", "記錄", ("record",)),
    ("show", "給別人看", ("print", "share")),
    ("learn", "了解", ("guide",)),
    ("convenience", "方便使用", ("add-home",)),
)
# The group pwa-nav.js hides in the home-screen app (ticket #160): it is added already.
HIDDEN_IN_APP = "convenience"


def home_more(user, today):
    """The 建議下一步 (GLOSSARY) and the other cards, in their groups with none left empty:
    each group (title, cards, hidden in the home-screen app)."""
    cards = {
        "record": HomeCard("記錄醫院的聽力圖", reverse("audiogram_new"), "audiogram"),
        "print": HomeCard("印聽力報告給醫師看", reverse("health_report"), "report"),
        "share": HomeCard("分享報告給家人", reverse("share_report"), "share"),
        "guide": HomeCard("了解助聽器選配與補助", reverse("guide"), "guide"),
        "add-home": HomeCard("加到手機主畫面", reverse("add_to_home"), "add-home"),
    }
    state = fitting_state(user, today)
    if state.stop == AUDIOGRAM and state.insufficient:
        suggested = None  # not a card of its own: 記錄醫院的聽力圖 stays in its group
        edit = HomeCard(
            "修改這張聽力圖", reverse("audiogram_edit", args=[state.audiogram.pk]), "audiogram"
        )
        next_step = NextStep(edit, NEXT_STEP_REASONS["edit"], "修改這張聽力圖")
    elif state.stop == AUDIOGRAM:
        suggested = "record"
        next_step = NextStep(cards[suggested], NEXT_STEP_REASONS[suggested], "去記錄")
    elif state.stop:
        suggested = "guide"
        next_step = NextStep(cards[suggested], NEXT_STEP_REASONS[state.stop], "看我的選配指引")
    elif user.report_shares.exists():  # any link ever made, ended ones too
        suggested = "print"
        next_step = NextStep(cards[suggested], NEXT_STEP_REASONS[suggested], "去印報告")
    else:
        suggested = "share"
        next_step = NextStep(cards[suggested], NEXT_STEP_REASONS[suggested], "去分享")
    groups = (
        (title, [cards[key] for key in keys if key != suggested], group == HIDDEN_IN_APP)
        for group, title, keys in HOME_GROUPS
    )
    return next_step, [(title, shown, hidden) for title, shown, hidden in groups if shown]
