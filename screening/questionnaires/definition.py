from collections.abc import Callable
from dataclasses import dataclass, field

from screening.questionnaires.comparison import AverageComparison, TotalComparison

# How a questionnaire's result is worked out and shown.
LEVEL = "level"  # total score graded by thresholds, with advice (HHIE-S, HHIA-S)
AVERAGE = "average"  # average of the items, no grade (SSQ12-TW)
NORM = "norm"  # each item against the norms, no total (IOI-HA)
SUBSCALES = "subscales"  # overall and subscale averages, no grade or norms (SADL)

# The retest reminder (ADR 0010): months after the latest life-impact record, and the last
# next step of every life-impact questionnaire, the one step not traced to its advice.
RETEST_MONTHS = 6
RETEST_STEP = {"text": "半年後再做一次，時間到了首頁會提醒您。"}


@dataclass(frozen=True)
class Definition:
    code: str
    topic: str  # the catalog card reads 「topic（name）」
    audience: str
    minutes: int
    icon: str  # "ear", "aid" or "clipboard" (questionnaire_icon.html)
    # Catalog order (spec phase9_ui_refresh_4b_questionnaire_cards.md 4.1); equal ranks keep
    # the order the questionnaires were added. A screen order, not a scoring rule.
    list_rank: int
    intro_template: str  # shown above the questions on the answer page
    result: str  # LEVEL, AVERAGE or NORM
    # Item n's answer choices as (value, label). The value "na" is an explicit 「不適用」,
    # saved as an empty score; only questionnaires that list it accept it.
    choices: Callable[[int], list]
    # seed_questionnaires creates the questionnaire from these when its code is missing;
    # empty for questionnaires loaded from the fixture (HHIE-S, IOI-HA).
    name: str = ""  # questionnaire_name
    questions: tuple = ()  # (category, text) in question-number order
    # LEVEL only. Each tuple is (upper bound inclusive, text, level); the last upper bound is
    # the max score. Published numbers never change: a new rule needs a rule version first.
    thresholds: tuple = ()
    # LEVEL only: level -> its colour, one of ADR 0007's three (normal green, mild_to_moderate
    # orange, severe red), which badges, banners, the score bar and the trend chart draw. A level
    # not listed is coloured by its own code: HHIE-S and HHIA-S levels are named like the colours.
    level_colors: dict = field(default_factory=dict)
    advice: dict = field(default_factory=dict)  # LEVEL only: level -> advice text
    # LEVEL only: level -> numbered "接下來建議您" steps (ADR 0010). Each step is a dict with
    # "text" and, where it links to a next action, "action_label" and "action_url" (a URL name
    # that takes no arguments). Every clause but the retest reminder traces back to `advice`.
    next_steps: dict = field(default_factory=dict)
    # A life-impact questionnaire (GLOSSARY, ADR 0016): the home page's last result and retest
    # reminder, and 我的紀錄's 「和上一次比」 against the last record worn the same way. Graded
    # is not enough: a graded questionnaire about something else (THI) is not one.
    life_impact: bool = False
    trend_chart: bool = False  # the history page draws a score trend chart
    scale: Callable[[int], tuple] | None = None  # item n's (label for 0, label for 10)
    # Wearing-status comparison of an unaided and an aided record; None: not offered.
    comparison: TotalComparison | AverageComparison | None = None
    # False until the copyright holders agree in writing (ADR 0011): offered only under DEBUG.
    listed: bool = True
    # Answered about the hearing aids worn now or lately: wearing is not asked, saved as worn.
    always_aided: bool = False
    # Copyright credit shown at the bottom of the answer page; "" when the intro already has it.
    source_template: str = ""
    # SUBSCALES only: how to read the scores, in place of norms or grades.
    result_note: str = ""
    # SUBSCALES only: item number -> value or None (不適用) in, overall and subscales out.
    score: Callable[[dict], dict] | None = None

    def color(self, level):
        return self.level_colors.get(level, level)

    @property
    def averaged(self):  # for templates, which cannot see the constants above
        return self.result == AVERAGE
