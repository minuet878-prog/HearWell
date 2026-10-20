from dataclasses import dataclass, field

# How a questionnaire's result is worked out and shown.
LEVEL = "level"  # total score graded by thresholds, with advice (HHIE-S, HHIA-S)
AVERAGE = "average"  # average of the items, no grade (SSQ12-TW)
NORM = "norm"  # each item against the norms, no total (IOI-HA)


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
    # LEVEL only. Each tuple is (upper bound inclusive, text, level); the last upper bound is
    # the max score. Published numbers never change: a new rule needs a rule version first.
    thresholds: tuple = ()
    advice: dict = field(default_factory=dict)  # LEVEL only: level -> advice text
    trend_chart: bool = False  # the history page draws a score trend chart
