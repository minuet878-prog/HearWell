"""The 待辦 (GLOSSARY, ADR 0047, spec #478): what each 照顧旅程 step or 選配路線 stop asks, its
key, wording and kind, and whether the automatic ones are done, judged from the route's records.
A to-do never changes whether a step or a stop is done."""

from collections.abc import Callable
from dataclasses import dataclass

from screening import questionnaires
from screening.fitting_route import AUDIOGRAM
from screening.models import FIRST_ROUND


@dataclass(frozen=True)
class JourneyTodo:
    key: str  # kept with a tick (#481), so never renamed
    text: str
    manual: bool  # 手動待辦, ticked by the user; else 自動待辦, ticked from the records
    done: bool
    hint: str = ""  # an 自動待辦's muted line under its words; a 手動待辦 has none


@dataclass(frozen=True)
class _Todo:
    key: str
    text: str
    # 自動待辦: whether it is done, of a FittingState for a stop's, of whether the step is done
    # for a step's; None for a 手動待辦.
    rule: Callable | None = None


def _stop_done(slug):
    return lambda state: slug in state.done


# Wordings the owner settled on #479 (phase-2-grill-decisions.md), in the order listed.
STOP_TODOS = {
    AUDIOGRAM: (
        _Todo("audiogram-test", "到醫院或診所做聽力檢查"),
        _Todo("audiogram-copy", "跟醫院或診所要一份聽力圖"),
        _Todo("audiogram-record", "把聽力圖記到聽伴", _stop_done(AUDIOGRAM)),
    ),
    "before-you-go": (
        _Todo("before-you-go-read", "看完「去找聽力師之前」這一章", _stop_done("before-you-go")),
        _Todo("before-you-go-book", "預約聽力師"),
    ),
    "assessment": (
        _Todo("assessment-book", "預約鑑定醫院"),
        _Todo("assessment-answer", "回答有沒有身心障礙證明", _stop_done("assessment")),
    ),
    "form-9": (
        _Todo("form-9-book", "預約開九號表"),
        _Todo("form-9-answer", "回答九號表完成了", _stop_done("form-9")),
    ),
    "notice": (_Todo("notice-answer", "記下核定的耳朵與等級", _stop_done("notice")),),
    "types-and-prices": (
        _Todo(
            "types-and-prices-read",
            "看完「助聽器的種類與價格」這一章",
            _stop_done("types-and-prices"),
        ),
        _Todo("types-and-prices-try", "試戴過助聽器"),
    ),
    "after-fitting": (
        # The date alone, where the stop is done only with the subsidy answered too (#295).
        _Todo("after-fitting-date", "記下開始配戴的日期", lambda state: state.fitted),
        _Todo("after-fitting-adjust", "配戴後第一次回去調整"),
    ),
    "form-25": (
        _Todo("form-25-book", "預約開二十五號表"),
        _Todo("form-25-answer", "回答二十五號表完成了", _stop_done("form-25")),
    ),
    "payout": (_Todo("payout-received", "收到補助款"),),
}
# Steps 4 and 5's own, where the card is not a route stop; step 1 has none, as its one thing is
# the button's (spec #478). Step 4's IOI-HA is what makes the step done.
STEP_TODOS = {
    4: (
        _Todo("step-4-adjust", "滿 3 個月前再回去調整一次"),
        _Todo("step-4-ioi-ha", "做完助聽器效益問卷", lambda step_done: step_done),
    ),
    5: (_Todo("step-5-calendar", "把下次篩檢日期記在月曆或手機上"),),
}


# An 自動待辦's muted line, the owner's on 2026-11-13 (phase-2-grill-decisions.md): a stop's is
# mostly the stop's own end, so done, the route moves on and the card never shows it ticked.
DONE_HINT = "已自動打勾"
STOP_HINT = "做完就會往下一站"
STEP_HINT = "做完這一步就完成"


# Every to-do's wording by its key, and which are 手動待辦, the only ones a tick is kept for (#481).
_ALL_TODOS = tuple(todo for todos in (*STOP_TODOS.values(), *STEP_TODOS.values()) for todo in todos)
TODO_TEXTS = {todo.key: todo.text for todo in _ALL_TODOS}
MANUAL_KEYS = frozenset(todo.key for todo in _ALL_TODOS if todo.rule is None)
# 記錄聽力圖's, step 2's card, which never start over (spec #478).
_ONE_ROUND_KEYS = frozenset(todo.key for todo in STOP_TODOS[AUDIOGRAM])
_STEP_5_KEYS = frozenset(todo.key for todo in STEP_TODOS[5])


def current_rounds(user, aid):
    """The round each 手動待辦 is ticked in now (#482, spec #478), for a tick and for reading
    the ticks alike: 記錄聽力圖's the first, always; step 5's the latest life-impact record's id,
    0 before one; the other eight stops' and step 4's the pair of hearing aids
    (AidAndSubsidy.pair_number). aid: the user's, None before any."""
    pair = aid.pair_number if aid is not None else FIRST_ROUND
    life_impact = _latest_life_impact(user)
    rounds = dict.fromkeys(MANUAL_KEYS, pair)
    rounds |= dict.fromkeys(_ONE_ROUND_KEYS, FIRST_ROUND)
    rounds |= dict.fromkeys(_STEP_5_KEYS, life_impact)
    return rounds


def _latest_life_impact(user):
    # The record get_user_state takes for the latest life-impact one, kept by its id alone: no
    # foreign key, so deleting records stays as it was (spec #478).
    codes = [code for code in questionnaires.offered() if questionnaires.get(code).life_impact]
    latest = user.submissions.filter(questionnaire__code__in=codes).order_by("-created_at", "-id")
    return latest.values_list("id", flat=True).first() or 0


def stop_todos(slug, state):
    """A route stop's 待辦, judged on state (a FittingState), its ticks the manual ones'."""
    return _judged(STOP_TODOS.get(slug, ()), state, state.ticked, STOP_HINT)


def step_todos(number, done, ticked):
    """A 照顧旅程 step's own 待辦; done, whether the step is done; ticked, the keys of the
    手動待辦 ticked (FittingState.ticked)."""
    return _judged(STEP_TODOS.get(number, ()), done, ticked, STEP_HINT)


def _judged(todos, subject, ticked, hint):
    listed = []
    for todo in todos:
        if todo.rule is None:
            listed.append(JourneyTodo(todo.key, todo.text, True, todo.key in ticked))
        else:
            done = bool(todo.rule(subject))
            listed.append(JourneyTodo(todo.key, todo.text, False, done, DONE_HINT if done else hint))
    return tuple(listed)
