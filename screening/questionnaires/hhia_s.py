from screening.questionnaires.definition import LEVEL, Definition

CODE = "hhia-s"

THRESHOLDS = (
    (8, "無／極輕微影響", "normal"),
    (24, "輕至中度影響", "mild_to_moderate"),
    (40, "顯著影響", "severe"),
)

EXPLANATION = (
    "這份問卷反映您感受到的生活影響，不能判定聽損程度，也不能單憑分數決定是否需要助聽器。"
)
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

DEFINITION = Definition(
    code=CODE,
    topic="聽力對生活的影響",
    audience="適合 18–64 歲成人；若您持續使用原問卷追蹤，也可以繼續填寫。",
    minutes=3,
    icon="clipboard",
    list_rank=2,
    intro_template="screening/questionnaires/hhia_s_intro.html",
    result=LEVEL,
    thresholds=THRESHOLDS,
    advice=ADVICE,
)
