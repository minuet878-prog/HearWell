from screening.questionnaires.comparison import TotalComparison
from screening.questionnaires.definition import (
    HEARING_CHECK,
    LIFE_IMPACT,
    LIFE_IMPACT_LIMITS,
    RETEST_STEP,
    SAVE_REASONS,
    Definition,
)
from screening.questionnaires.results import GradedResult

CODE = "hhie-s"

CHOICES = ((4, "常常"), (2, "有時"), (0, "從未"))


def choices(number):
    return CHOICES


THRESHOLDS = (
    (8, "無／極輕微影響", "normal"),
    (24, "輕度到中度影響", "mild_to_moderate"),
    (40, "顯著影響", "severe"),
)

# The canvas's words (spec #741, page grill P11).
SHORT_NAMES = {"normal": "極輕微", "mild_to_moderate": "輕到中度", "severe": "顯著"}

# Spec #693: a severe score sends one to a hearing check, in the advice and the first next step.
_SEVERE_CHECK = "並做聽力檢查；有 AirPods Pro 的話，也可以先用 iPhone 做聽力自我測試。"

# One sentence a level since the owner's 2026-11-27 walkthrough.
_LEVEL_ADVICE = {
    "normal": "聽力還沒明顯影響生活，但聽力退化常常不自覺，建議定期做聽力檢查。",
    "mild_to_moderate": "聽力問題開始影響到生活了，建議去耳鼻喉科尋求專業建議。",
    "severe": f"聽力問題已經明顯影響生活，建議盡快去耳鼻喉科尋求專業建議，{_SEVERE_CHECK}",
}
# Spec #693: what the score cannot tell, as HHIA-S says it.
ADVICE = {level: f"{text} {LIFE_IMPACT_LIMITS}" for level, text in _LEVEL_ADVICE.items()}

# Draft reviewed and finalized by the audiologist, issue #156.
NEXT_STEPS = {
    "normal": (
        {
            "text": (
                "這次結果顯示您的聽覺自覺障礙程度為無或僅有輕微障礙，"
                "暫時沒有明顯影響情緒與社交活動。"
            )
        },
        {
            "text": (
                "不過高齡族群的聽力退化通常不容易自己察覺；如果還沒做過聽力檢查，"
                "建議至醫院進行定期篩檢。"
            ),
            "action_label": "記錄聽力圖",
            "action_url": "audiogram_new",
            **HEARING_CHECK,
        },
        RETEST_STEP,
    ),
    "mild_to_moderate": (
        {
            "text": (
                "聽力問題已經慢慢影響您的社交活動與情緒，例如與家人因聽不清楚而起爭執、"
                "在吵雜場合感到窘迫而退縮。"
            )
        },
        {
            # The owner's 2026-11-27 walkthrough.
            "text": (
                "篩檢顯示聽力問題已經影響到您的生活，建議前往醫院或診所耳鼻喉科進行聽力檢查。"
            ),
            **HEARING_CHECK,
        },
        RETEST_STEP,
    ),
    "severe": (
        {
            "text": (
                "聽力問題已經嚴重影響到您的生活了，若您尚未採取任何行動，"
                f"建議立即前往醫院耳鼻喉科尋求專業建議，{_SEVERE_CHECK}"
            ),
            **HEARING_CHECK,
        },
        {
            "text": (
                "聽力喪失影響的並不只是聽不聽得到，無形中也會增加社交活動的壓力，"
                "這些壓力以及情緒的低落會增加長者的認知負擔。"
            )
        },
        RETEST_STEP,
    ),
}

DEFINITION = Definition(
    code=CODE,
    topic="聽力對生活的影響",
    audience="適合 65 歲以上的長輩。",
    minutes=3,
    icon="ear",
    list_rank=0,
    intro_template="screening/questionnaires/hhie_s_intro.html",
    result=GradedResult,
    life_impact=True,
    guest=True,
    save_reasons=SAVE_REASONS,
    concern=LIFE_IMPACT,
    choices=choices,
    thresholds=THRESHOLDS,
    short_names=SHORT_NAMES,
    advice=ADVICE,
    next_steps=NEXT_STEPS,
    # Under the next steps, as HHIA-S's: the full advice is not on the result page.
    result_note=LIFE_IMPACT_LIMITS,
    trend_chart=True,
    records_tab_age="65 歲以上",
    # The report anchor it had before other questionnaires could be compared.
    comparison=TotalComparison(anchor="report-difference"),
)
