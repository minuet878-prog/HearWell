from collections.abc import Callable
from dataclasses import dataclass, field

from screening.questionnaires.comparison import AverageComparison, TotalComparison

# How a questionnaire's result is worked out and shown.
LEVEL = "level"  # total score graded by thresholds, with advice (HHIE-S, HHIA-S)
AVERAGE = "average"  # average of the items, no grade (SSQ12-TW)
NORM = "norm"  # each item against the norms, no total (IOI-HA)
SUBSCALES = "subscales"  # overall and subscale averages, no grade or norms (SADL)


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
    advice: dict = field(default_factory=dict)  # LEVEL only: level -> advice text
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
    # SUBSCALES only: item number -> value or None (不適用) in, overall and subscales out.
    score: Callable[[dict], dict] | None = None

    @property
    def averaged(self):  # for templates, which cannot see the constants above
        return self.result == AVERAGE
