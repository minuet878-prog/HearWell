"""The 待辦 (GLOSSARY, ADR 0047, spec #478): what each 照顧旅程 step or 選配路線 stop asks, its
key, wording and kind, and whether the automatic ones are done, judged from the route's records.
A to-do never changes whether a step or a stop is done."""

from collections.abc import Callable
from dataclasses import dataclass

from screening.fitting_route import AUDIOGRAM
from screening.models import FIRST_ROUND


@dataclass(frozen=True)
class JourneyTodo:
    key: str  # kept with a tick (#481), so never renamed
    text: str
    manual: bool  # 手動待辦, ticked by the user; else 自動待辦, ticked from the records
    done: bool
    # An 自動待辦's sentence is its words and then, what doing it brings, and its muted line
    # the hint (the owner's C on 2026-11-14); a 手動待辦 has neither.
    then: str = ""
    hint: str = ""
    # A 手動待辦's round as listed (current_rounds), sent back with a tick so a page left open
    # from an earlier round changes nothing in this one (the cross review on #478); None for
    # an 自動待辦.
    round_key: int | None = None


@dataclass(frozen=True)
class _Todo:
    key: str
    text: str
    # 自動待辦: whether it is done, of a FittingState for a stop's, of whether the step is done
    # for a step's; None for a 手動待辦.
    rule: Callable | None = None
    # 自動待辦: whether done is its stop's or step's being done, or only a part of it, which the
    # muted line says apart (the owner on 2026-11-13, phase-2-grill-decisions.md).
    completes: bool = True


def _stop_done(slug):
    return lambda state: slug in state.done


# Wordings the owner settled on #479 (phase-2-grill-decisions.md), in the order listed: the
# 手動待辦 first, the 自動待辦 last (the owner's C on 2026-11-14).
STOP_TODOS = {
    AUDIOGRAM: (
        _Todo("audiogram-test", "到醫院或診所做聽力檢查"),
        _Todo("audiogram-copy", "跟醫院或診所要一份聽力圖"),
        _Todo("audiogram-record", "把聽力圖記到聽伴", _stop_done(AUDIOGRAM)),
    ),
    "before-you-go": (
        _Todo("before-you-go-book", "預約聽力師"),
        _Todo("before-you-go-read", "看完「去找聽力師之前」這一章", _stop_done("before-you-go")),
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
        _Todo("types-and-prices-try", "試戴過助聽器"),
        _Todo(
            "types-and-prices-read",
            "看完「助聽器的種類與價格」這一章",
            _stop_done("types-and-prices"),
        ),
    ),
    "after-fitting": (
        _Todo("after-fitting-adjust", "配戴後第一次回去調整"),
        # The date alone, where the stop is done only with the subsidy answered too (#295).
        _Todo(
            "after-fitting-date", "記下開始配戴的日期", lambda state: state.fitted, completes=False
        ),
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


# An 自動待辦's sentence and muted line, the owner's C on 2026-11-14 (after
# phase-2-grill-decisions.md's of 2026-11-13): one that is its stop's or step's whole end says
# the route moves on or the step is done, as done the card moves on and never shows it ticked;
# one that is only a part says the site ticks it.
STOP_THEN = "，就會往下一站"
STEP_THEN = "，這一步就完成"
UNDONE_HINT = "不用自己勾，網站會知道"
PART_HINT = "不用自己勾，做完網站會幫您打勾"
DONE_HINT = "網站已幫您打勾"


# Every to-do's wording by its key, and which are 手動待辦, the only ones a tick is kept for (#481).
_ALL_TODOS = tuple(todo for todos in (*STOP_TODOS.values(), *STEP_TODOS.values()) for todo in todos)
TODO_TEXTS = {todo.key: todo.text for todo in _ALL_TODOS}
MANUAL_KEYS = frozenset(todo.key for todo in _ALL_TODOS if todo.rule is None)
# Step 5's round before any life-impact record.
NO_LIFE_IMPACT = 0


def _pair(aid):
    return aid.pair_number if aid is not None else FIRST_ROUND


def _stop_round(slug, aid):
    # 記錄聽力圖's, step 2's card, never starts over (spec #478); the other eight stops' go by
    # the pair of hearing aids (AidAndSubsidy.pair_number).
    return FIRST_ROUND if slug == AUDIOGRAM else _pair(aid)


def _step_round(number, aid, life_impact):
    # Step 4's by the pair; step 5's by the latest life-impact record, kept by its id alone: no
    # foreign key, so deleting records stays as it was (spec #478).
    if number == 5:
        return life_impact.pk if life_impact is not None else NO_LIFE_IMPACT
    return _pair(aid)


def current_rounds(aid, life_impact):
    """The round each 手動待辦 is ticked in now (#482, spec #478), for a tick and for reading
    the ticks alike. aid: the user's AidAndSubsidy, None before any; life_impact: their latest
    life-impact record (UserState.life_impact, the one the 照顧旅程 shows), None before one."""
    rounds = {
        todo.key: _stop_round(slug, aid) for slug, todos in STOP_TODOS.items() for todo in todos
    }
    rounds |= {
        todo.key: _step_round(number, aid, life_impact)
        for number, todos in STEP_TODOS.items()
        for todo in todos
    }
    return {key: number for key, number in rounds.items() if key in MANUAL_KEYS}


def _ticked(user, todos, round_now):
    # The keys of user's 手動待辦 among todos ticked in round_now, their list's round (#481,
    # #482): a tick of an earlier round is kept but not ticked now. Whether a stop is done never
    # reads them (ADR 0047).
    manual = [todo.key for todo in todos if todo.rule is None]
    if not manual:
        return frozenset()
    ticks = user.todo_ticks.filter(key__in=manual, round_key=round_now)
    return frozenset(ticks.values_list("key", flat=True))


def stop_todos(slug, state, user):
    """A route stop's 待辦, judged on state (user's FittingState)."""
    todos = STOP_TODOS.get(slug, ())
    round_now = _stop_round(slug, state.aid)
    return _judged(todos, state, _ticked(user, todos, round_now), round_now, STOP_THEN)


def step_todos(number, done, user, aid, life_impact):
    """A 照顧旅程 step's own 待辦; done, whether the step is done; aid and life_impact as
    current_rounds takes them."""
    todos = STEP_TODOS.get(number, ())
    round_now = _step_round(number, aid, life_impact)
    return _judged(todos, done, _ticked(user, todos, round_now), round_now, STEP_THEN)


def _judged(todos, judged_on, manual_ticked, round_now, then):
    # judged_on: what each 自動待辦's rule reads, a stop's FittingState or whether a step is
    # done; manual_ticked: the keys of the 手動待辦 ticked in round_now, the list's round;
    # then: what an 自動待辦 not done yet that completes its stop or step brings, STOP_THEN or
    # STEP_THEN.
    listed = []
    for todo in todos:
        if todo.rule is None:
            ticked = todo.key in manual_ticked
            listed.append(JourneyTodo(todo.key, todo.text, True, ticked, round_key=round_now))
        else:
            done = bool(todo.rule(judged_on))
            if done:
                todo_then, hint = "", DONE_HINT
            elif todo.completes:
                todo_then, hint = then, UNDONE_HINT
            else:
                todo_then, hint = "", PART_HINT
            listed.append(JourneyTodo(todo.key, todo.text, False, done, todo_then, hint))
    return tuple(listed)
