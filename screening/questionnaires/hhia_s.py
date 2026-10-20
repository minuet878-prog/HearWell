from screening.questionnaires.comparison import TotalComparison
from screening.questionnaires.definition import LEVEL, Definition

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

DEFINITION = Definition(
    code=CODE,
    name="HHIA-S",
    questions=QUESTIONS,
    topic="聽力對生活的影響",
    audience="適合 18–64 歲成人；若您持續使用原問卷追蹤，也可以繼續填寫。",
    minutes=3,
    icon="clipboard",
    list_rank=2,
    intro_template="screening/questionnaires/hhia_s_intro.html",
    result=LEVEL,
    choices=choices,
    thresholds=THRESHOLDS,
    advice=ADVICE,
    comparison=TotalComparison(anchor=f"report-comparison-{CODE}"),
)
