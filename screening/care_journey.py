"""Where a user stands on the 照顧旅程 (GLOSSARY, ADR 0044, spec #453): each step's state, the
現在這一步 and its card, and the home page's two tiles, the one place both the home page and
the result pages ask. It reads the 選配路線 and the main flow's state; it judges nothing anew."""

from dataclasses import dataclass, field
from datetime import date

from django.urls import reverse
from django.utils import timezone

from screening.fitting_route import AUDIOGRAM, add_months, fitting_state
from screening.journey_todos import step_todos
from screening.main_flow import get_user_state, life_impact_questionnaire
from screening.models import Questionnaire, Submission
from screening.questionnaires.ioi_ha import CODE as IOI_HA
from screening.scoring import (
    CARE_JOURNEY_ABOUT,
    CARE_JOURNEY_STEPS,
    IOI_HA_BUTTON,
    IOI_HA_DUE_BECAUSE,
    LIFE_IMPACT_BECAUSE,
    LIFE_IMPACT_BUTTON,
    NEXT_STEP_REASONS,
    RETEST_BUTTON_TEXT,
    RETEST_COUNTDOWN_TEXT,
    RETEST_DUE_TEXT,
    TYPES_AND_PRICES_BUTTON,
    fitting_countdown_text,
)
from screening.views.guide import here_stop

# A step's state (GLOSSARY 照顧旅程). LATER is any step not done that is not the 現在這一步,
# steps 1 and 2 left unticked by someone wearing hearing aids too (spec #453 Q6).
DONE = "done"
CURRENT = "current"
LATER = "later"
NOT_NEEDED = "not-needed"  # 目前不需要, steps 3 and 4 only
FITTING_STEPS = (3, 4)
WEARING_FROM = 3  # someone wearing hearing aids looks for the 現在這一步 from step 3 on
LAST_STEP = 5
FITTING_MONTHS = 3  # IOI-HA once hearing aids are worn 3 months (spec #453 Q8)


@dataclass(frozen=True)
class HomeCard:
    title: str
    href: str


@dataclass(frozen=True)
class NextStep:
    """A result page's 建議下一步 (result_next.html)."""

    card: HomeCard
    button: str
    suggested: str | None  # "print" or "share" off the journey, so the page drops that card


@dataclass(frozen=True)
class JourneyStep:
    title: str
    state: str
    done_on: date | None = None  # the day it was done, said beside a done step (#458 D7)
    about: str = ""  # what the step is, said when it is opened (#459 I1)


@dataclass(frozen=True)
class JourneyCard:
    """The 現在這一步's one thing: title and why, the place it lives (a route stop's page, else
    None) and its button (text, url), None while counting down or waiting."""

    title: str
    because: str
    icon: str  # an action_icon.html icon
    href: str | None = None
    button: tuple[str, str] | None = None
    # Its 待辦 under the button (spec #478), apart from the one thing: a result page's 建議下一步
    # takes the card without them.
    todos: tuple = field(default=(), compare=False)


@dataclass(frozen=True)
class NextScreening:
    """下次篩檢, from the latest life-impact record: the day and the days left, both None once
    due."""

    on: date | None
    days_left: int | None
    due: bool
    href: str  # 再做一次: the same life-impact questionnaire


@dataclass(frozen=True)
class CareJourney:
    steps: tuple[JourneyStep, ...]  # step 1 first
    current: int  # the 現在這一步, 1 to 5
    card: JourneyCard
    last_result: Submission | None  # the latest life-impact record, for 上次結果
    # None without a life-impact record: no day to count from, so the tile says it is not set
    # (#458 D6) while step 5 asks for one (spec #453).
    next_screening: NextScreening | None

    @property
    def progress(self):
        """The steps passed, done or 目前不需要: at most 4 of 5, as step 5 is never done."""
        return sum(step.state in (DONE, NOT_NEEDED) for step in self.steps)


def care_journey(user, today):
    route = fitting_state(user, today)
    main = get_user_state(user, today)
    life_impact = main.last_result if main.last_result and main.last_result.is_life_impact else None
    fitted_on = route.aid.fitted_on if route.fitted else None
    # IOI-HA from the fitting date on, however soon (spec #453 Q8); the latest gives the day.
    ioi_ha = (
        user.submissions.filter(questionnaire__code=IOI_HA, created_at__date__gte=fitted_on)
        .order_by("-created_at")
        .first()
        if fitted_on is not None
        else None
    )
    # Each step's day, None while it is not done; step 5 never is, a retest only moves the
    # next one on.
    done_on = {
        1: _day(life_impact.submission) if life_impact else None,
        2: route.audiogram.tested_on if AUDIOGRAM in route.done else None,
        3: fitted_on,
        4: _day(ioi_ha) if ioi_ha else None,
        5: None,
    }
    done = {number: day is not None for number, day in done_on.items()}

    def not_needed(number):
        return route.waiting and number in FITTING_STEPS

    first = WEARING_FROM if route.wearing else 1
    current = next(
        (n for n in range(first, LAST_STEP) if not done[n] and not not_needed(n)), LAST_STEP
    )
    steps = tuple(
        JourneyStep(
            title,
            _state(number, current, done[number], not_needed(number)),
            done_on[number],
            about,
        )
        for number, (title, about) in enumerate(
            zip(CARE_JOURNEY_STEPS, CARE_JOURNEY_ABOUT, strict=True), start=1
        )
    )
    life_impact_href = _life_impact_href(user, main)
    if life_impact is None:
        next_screening = None
    elif main.retest_due:
        next_screening = NextScreening(None, None, True, life_impact_href)
    else:
        on = main.next_suggested_date
        next_screening = NextScreening(on, (on - today).days, False, life_impact_href)
    card = _card(current, done[current], route, fitted_on, today, next_screening, life_impact_href)
    return CareJourney(
        steps,
        current,
        card,
        life_impact.submission if life_impact else None,
        next_screening,
    )


def _day(submission):
    return timezone.localtime(submission.created_at).date()


def _state(number, current, done, not_needed):
    if done:
        return DONE
    if not_needed:
        return NOT_NEEDED
    return CURRENT if number == current else LATER


def _life_impact_href(user, main):
    # The one to do again, or by age; the catalogue, which recommends one, while the age is
    # unknown.
    questionnaire = life_impact_questionnaire(
        user, list(Questionnaire.objects.defined()), main, None
    )
    if questionnaire is None:
        return reverse("questionnaire_list")
    return reverse("screening", args=[questionnaire.pk])


def _card(current, done, route, fitted_on, today, next_screening, life_impact_href):
    # done: whether the 現在這一步 is, for its own 待辦 (step 5 never is).
    if current == 1:
        return JourneyCard(
            CARE_JOURNEY_STEPS[0],
            LIFE_IMPACT_BECAUSE,
            "clipboard",
            button=(LIFE_IMPACT_BUTTON, life_impact_href),
        )
    if current in (2, 3) or (current == 4 and route.stop == "form-25"):
        return _route_card(route)
    if current == 4:
        # Not 等待補助發放, which the home page leaves to my guide (spec #453).
        three_months = add_months(fitted_on, FITTING_MONTHS)
        title = CARE_JOURNEY_STEPS[3]
        todos = step_todos(4, done)
        if today < three_months:
            because = fitting_countdown_text((three_months - today).days)
            return JourneyCard(title, because, "clipboard", todos=todos)
        ioi_ha = Questionnaire.objects.get(code=IOI_HA)
        return JourneyCard(
            title,
            IOI_HA_DUE_BECAUSE,
            "clipboard",
            button=(IOI_HA_BUTTON, reverse("screening", args=[ioi_ha.pk])),
            todos=todos,
        )
    title = CARE_JOURNEY_STEPS[4]
    todos = step_todos(5, done)
    if next_screening is None:
        # Without a life-impact record step 5 is due: one to do first (spec #453).
        button = (LIFE_IMPACT_BUTTON, life_impact_href)
        return JourneyCard(title, LIFE_IMPACT_BECAUSE, "clipboard", button=button, todos=todos)
    if not next_screening.due:
        return JourneyCard(title, RETEST_COUNTDOWN_TEXT, "clipboard", todos=todos)
    button = (RETEST_BUTTON_TEXT, next_screening.href)
    return JourneyCard(title, RETEST_DUE_TEXT, "clipboard", button=button, todos=todos)


def _route_card(route):
    # The 目前這一站 with the route's own button and the home page's 「因為」 for it (#261).
    stop = here_stop(route)
    if stop.slug == AUDIOGRAM:
        reason = "edit" if route.insufficient else "record"
    else:
        reason = stop.slug
    because = NEXT_STEP_REASONS[reason]
    if stop.slug == "form-25":
        because = because.format(deadline=route.form_25[1])
    icon = "audiogram" if stop.slug == AUDIOGRAM else "guide"
    button = stop.action
    if stop.slug == "types-and-prices":
        # The owner on #455: a chapter to read, so the card has a button the route lacks;
        # 等待核定公文 stays without one, as there is nothing to do but wait.
        button = (TYPES_AND_PRICES_BUTTON, stop.url)
    return JourneyCard(stop.title, because, icon, href=stop.url, button=button, todos=stop.todos)


def next_step(user, today):
    """The result pages' 建議下一步 (ADR 0044): the 現在這一步's card, or without a button
    sharing the report, printing it once any link was ever made (#261)."""
    card = care_journey(user, today).card
    if card.button is not None:
        text, href = card.button
        return NextStep(HomeCard(card.title, href), text, None)
    if user.report_shares.exists():
        print_card = HomeCard("印聽力報告給醫師看", reverse("health_report"))
        return NextStep(print_card, "去印報告", "print")
    share_card = HomeCard("分享報告給家人", reverse("share_report"))
    return NextStep(share_card, "去分享", "share")
