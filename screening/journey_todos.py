"""The 待辦 (GLOSSARY, ADR 0047, spec #478): what each 照顧旅程 step or 選配路線 stop asks, its
key, wording and kind, and whether the automatic ones are done, judged from the route's records.
A to-do never changes whether a step or a stop is done."""

from collections.abc import Callable
from dataclasses import dataclass

from screening.fitting_route import AUDIOGRAM


@dataclass(frozen=True)
class JourneyTodo:
    key: str  # kept with a tick (#481), so never renamed
    text: str
    manual: bool  # 手動待辦, ticked by the user; else 自動待辦, ticked from the records
    done: bool


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


def stop_todos(slug, state):
    """A route stop's 待辦, judged on state (a FittingState); manual ones are left unticked."""
    return _judged(STOP_TODOS.get(slug, ()), state)


def step_todos(number, done):
    """A 照顧旅程 step's own 待辦; done, whether the step is done."""
    return _judged(STEP_TODOS.get(number, ()), done)


def _judged(todos, subject):
    return tuple(
        JourneyTodo(todo.key, todo.text, todo.rule is None, bool(todo.rule and todo.rule(subject)))
        for todo in todos
    )
