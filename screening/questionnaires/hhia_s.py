from screening.questionnaires.comparison import TotalComparison
from screening.questionnaires.definition import (
    GUIDE_ACTION,
    LEVEL,
    LIFE_IMPACT,
    RETEST_STEP,
    Definition,
)

CODE = "hhia-s"

CHOICES = ((4, "會"), (2, "有時"), (0, "不會"))


def choices(number):
    return CHOICES


# 林克寰《助聽器選配與驗證》書內 p.165 (PDF p.166), reviewed for issue #78.
# A published version is immutable: later wording changes need a new code.
QUESTIONS = (
    ("emotional", "認識新朋友時，聽力問題使你不好意思嗎？"),
    ("emotional", "當你與家人談話時，聽力問題會讓你感到挫折嗎？"),
    ("social", "聽力問題會讓你看電影或戲劇表演時感到困難嗎？"),
    ("emotional", "你覺得聽力問題會讓你有障礙嗎？"),
    ("social", "拜訪親朋好友或鄰居時，聽力問題會讓你感到困難嗎？"),
    ("social", "聽力問題會讓你與同事或客戶溝通的聽理解有困難嗎？"),
    ("emotional", "聽力問題讓你和家人相處時產生爭執嗎？"),
    ("social", "當你在看電視或聽收音機時，聽力問題會讓你感到困難嗎？"),
    ("emotional", "你覺得聽力問題會限制你的個人生活或社交生活嗎？"),
    ("social", "和親友在餐館吃飯時，聽力問題會讓你感到困難嗎？"),
)

THRESHOLDS = (
    (8, "無／極輕微影響", "normal"),
    (24, "輕至中度影響", "mild_to_moderate"),
    (40, "顯著影響", "severe"),
)

EXPLANATION = "這份問卷反映您感受到的生活影響，不能判定聽損程度，也不能單憑分數決定是否需要助聽器。"
_LEVEL_ADVICE = {
    "normal": "您這次回報的生活影響較少。若仍有聽不清楚的困擾，建議安排聽力評估。",
    "mild_to_moderate": (
        "您回報聽力困擾已影響部分日常生活。建議安排聽力評估，"
        "並帶這份結果與聽力師或耳鼻喉科醫師討論。"
    ),
    "severe": (
        "您回報聽力困擾對生活有顯著影響。建議儘早安排聽力評估，"
        "與聽力師或耳鼻喉科醫師討論適合您的協助方式。"
    ),
}
ADVICE = {
    level: f"{text} {EXPLANATION} 已配戴助聽器者，可帶結果回原聽力照護單位討論。"
    for level, text in _LEVEL_ADVICE.items()
}

# Draft reviewed and finalized by the audiologist, issue #156.
NEXT_STEPS = {
    "normal": (
        {"text": "您這次回報的生活影響較少。"},
        {
            "text": "如果您仍覺得聽不清楚，建議安排聽力評估。",
            "action_label": "記錄聽力圖",
            "action_url": "audiogram_new",
            **GUIDE_ACTION,
        },
        RETEST_STEP,
    ),
    "mild_to_moderate": (
        {"text": "您回報的聽力困擾已經影響部分日常生活。"},
        {
            "text": "建議安排聽力評估，並帶這份結果與聽力師或耳鼻喉科醫師討論。",
            "action_label": "看／印聽力報告",
            "action_url": "health_report",
            **GUIDE_ACTION,
        },
        RETEST_STEP,
    ),
    "severe": (
        {"text": "您回報的聽力困擾對生活有顯著影響。"},
        {
            "text": "建議儘早安排聽力評估，與聽力師或耳鼻喉科醫師討論適合您的協助方式。",
            **GUIDE_ACTION,
        },
        RETEST_STEP,
    ),
}

DEFINITION = Definition(
    code=CODE,
    name="HHIA-S",
    questions=QUESTIONS,
    topic="聽力對生活的影響",
    audience="適合 18–64 歲成人。",
    minutes=3,
    icon="ear",
    list_rank=2,
    intro_template="screening/questionnaires/hhia_s_intro.html",
    # Under the answers, as IOI-HA's, so the question is on a phone's first screen (#362).
    source_template="screening/hhia_s_source.html",
    result=LEVEL,
    life_impact=True,
    concern=LIFE_IMPACT,
    records_tab_age="65 歲以下",
    choices=choices,
    thresholds=THRESHOLDS,
    advice=ADVICE,
    next_steps=NEXT_STEPS,
    # Under the next steps: the full advice, the only other place it is said, is folded away.
    result_note=EXPLANATION,
    comparison=TotalComparison(anchor=f"report-comparison-{CODE}"),
)
