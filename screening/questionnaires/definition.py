from collections.abc import Callable
from dataclasses import dataclass, field

from screening.questionnaires.comparison import AverageComparison, TotalComparison

# How a questionnaire's result is worked out and shown.
LEVEL = "level"  # total score graded by thresholds, with advice (HHIE-S, HHIA-S)
AVERAGE = "average"  # average of the items, no grade (SSQ12-TW)
NORM = "norm"  # each item against the norms, no total (IOI-HA)
SUBSCALES = "subscales"  # overall and subscale averages, no grade or norms (SADL)

# What a questionnaire tells about among the recommendation wizard's first answers (ADR 0030),
# the values of a definition's `concern` and of that answer alike; their words are ConcernForm's.
LIFE_IMPACT = "life_impact"
TINNITUS = "tinnitus"
LISTENING = "listening"
HEARING_AID = "hearing_aid"
UNSURE = "unsure"  # an answer alone, no definition's concern: recommended as LIFE_IMPACT

# The retest reminder (ADR 0010): months after the latest life-impact record, and the last
# next step of every life-impact questionnaire, the one step not traced to its advice.
RETEST_MONTHS = 6
RETEST_STEP = {"text": "半年後再做一次，時間到了首頁會提醒您。"}
# The hearing-aid guide link (#220 E4) after the button of the life-impact step that recommends
# a hearing check or assessment (spec #218, ticket #229).
GUIDE_ACTION = {"second_label": "看助聽器選配指引", "second_url": "guide"}


@dataclass(frozen=True)
class SupportMessage:
    # Shown under the level on the result page alone, whatever the total, when any item
    # numbered in `items` is answered `score` (spec #208 Q6).
    items: tuple
    score: int
    text: str


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
    # that takes no arguments), and where a second link follows it, "second_label" and
    # "second_url" likewise. Every clause but the retest reminder traces back to `advice`.
    next_steps: dict = field(default_factory=dict)
    # A life-impact questionnaire (GLOSSARY, ADR 0016): the home page's last result and retest
    # reminder, and 我的紀錄's 「和上一次比」 against the last record worn the same way. Graded
    # is not enough: a graded questionnaire about something else (THI) is not one.
    life_impact: bool = False
    # Which of the recommendation wizard's first answers it tells about: LIFE_IMPACT, TINNITUS,
    # LISTENING or HEARING_AID (ADR 0030). "": none.
    concern: str = ""
    support_message: SupportMessage | None = None  # LEVEL only
    trend_chart: bool = False  # the history page draws a score trend chart
    # How to read the scores, shown above 我的紀錄's record cards (#364); "": nothing.
    records_note: str = ""
    # Who it suits, after the code on 我的紀錄's tab: 「HHIE-S（65 歲以上）」 (#364); "": nothing.
    records_tab_age: str = ""
    scale: Callable[[int], tuple] | None = None  # item n's (label for 0, label for 10)
    # Wearing-status comparison of an unaided and an aided record; None: not offered.
    comparison: TotalComparison | AverageComparison | None = None
    # False until the copyright holders agree in writing (ADR 0011): offered only under DEBUG.
    listed: bool = True
    # Answered about the hearing aids worn now or lately: wearing is not asked, saved as worn.
    always_aided: bool = False
    # The wearing question on the answer page, web and React alike (spec #208).
    wearing_question: str = "這次填答時，您有沒有戴助聽器？"
    # The message when it is left unanswered, asked the same way, web and API alike.
    wearing_error: str = "請選擇這次有沒有戴助聽器"
    # Copyright credit shown at the bottom of the answer page; "" when the intro already has it.
    source_template: str = ""
    # How to read the result, shown on the result page: SADL's in place of norms or grades,
    # HHIA-S's limits under its next steps.
    result_note: str = ""
    # SUBSCALES only: item number -> value or None (不適用) in, overall and subscales out.
    score: Callable[[dict], dict] | None = None

    def color(self, level):
        return self.level_colors.get(level, level)

    def shade(self, level):
        """ "pale" or "deep": levels sharing a colour alternate from the lowest up, so the score
        bar and the trend chart's bands stay apart where two touch (THI's five levels)."""
        levels = [code for _, _, code in self.thresholds]
        i = levels.index(level)
        run = 0
        while i - run > 0 and self.color(levels[i - run - 1]) == self.color(level):
            run += 1
        return "deep" if run % 2 else "pale"

    def support(self, scores):
        """The support message for these answers (item number -> score), or ""."""
        rule = self.support_message
        if rule and any(scores.get(number) == rule.score for number in rule.items):
            return rule.text
        return ""

    @property
    def averaged(self):  # for templates, which cannot see the constants above
        return self.result == AVERAGE
