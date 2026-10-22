from decimal import ROUND_HALF_UP, Decimal

from screening.questionnaires.definition import SUBSCALES, Definition

CODE = "sadl"

# HARL's Traditional Chinese SADL, the same form as Fang et al. 2013 (CSADL); 林克寰書頁 196.
LABELS = ("一點都沒有", "一點點", "有一些", "中等程度", "相當程度", "非常多", "極度")

QUESTIONS = (
    "和沒有戴助聽器比較起來，戴助聽器之後是否讓您在大多數時間比較能夠了解別人的話語?",
    "您是否會因助聽器所傳輸的聲音與想像中不太相同而感到沮喪?",
    "您是否相信配戴助聽器是符合您最大的利益?",
    "您是否會覺得您戴助聽器之後，別人較會注意到您有聽力損失的問題?",
    "您戴助聽器之後是否會減少要求別人複述講話內容的次數?",
    "您戴助聽器之後是否會覺得戴助聽器所造成的麻煩是值得的?",
    "您是否會因為將助聽器轉調大聲而造成迴音的問題而感到困擾?",
    "您戴助聽器之後是否對自己的外表感到滿意?",
    "您戴助聽器之後是否會增加對自己的自信?",
    "您戴助聽器之後是否覺得聲音自然?",
    "您配戴助聽器對於您在講電話時不用擴音器是否有幫助?",
    "您認為為您調配助聽器的人員在專業上是否稱職?",
    "您是否會覺得戴助聽器讓您看起來很無能?",
    "您覺得您所選配的助聽器價格是否合理?",
    "您是否會對助聽器可靠度感到滿意?",
)

# The English scoring rules let these two be left out; the Chinese form has no box for it (#166).
NOT_APPLICABLE = {
    11: "不適用：不戴助聽器講電話也聽得清楚",
    14: "不適用：助聽器的錢不是我出的（例如全額補助、家人出錢）",
}


def choices(number):
    options = list(enumerate(LABELS, start=1))
    if number in NOT_APPLICABLE:
        options.append(("na", NOT_APPLICABLE[number]))
    return options


# HARL's manual scoring instructions (SADLScoring.pdf, 2003).
SUBSCALE_ITEMS = (
    ("正面效果", (1, 3, 5, 6, 9, 10)),
    ("服務與費用", (12, 14, 15)),
    ("負面特徵", (2, 7, 11)),
    ("個人形象", (4, 8, 13)),
)
REVERSED = {2, 4, 7, 13}

# No norms or grades (#166): the result page explains the scale instead.
RESULT_NOTE = (
    "1 到 7 分，分數越高越滿意，4 分是中間。"
    "這份紀錄反映您對目前或最近使用的助聽器的感受，不能代替專業評估。"
)


def _average(values):
    return (Decimal(sum(values)) / len(values)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def score(answers):
    """answers: item number -> chosen value 1-7, or None for 「不適用」 (left out everywhere)."""
    scored = {
        number: 8 - value if number in REVERSED else value
        for number, value in answers.items()
        if value is not None
    }
    return {
        "overall": _average(scored.values()),
        "subscales": [
            {"name": name, "score": _average([scored[n] for n in items if n in scored])}
            for name, items in SUBSCALE_ITEMS
        ],
        "not_applicable": sorted(number for number, value in answers.items() if value is None),
    }


DEFINITION = Definition(
    code=CODE,
    name="SADL",
    questions=tuple(("", text) for text in QUESTIONS),
    topic="助聽器滿意度",
    audience="給正在戴或最近戴過助聽器的人。",
    minutes=5,
    icon="aid",
    list_rank=1,
    intro_template="screening/questionnaires/sadl_intro.html",
    source_template="screening/sadl_source.html",
    result=SUBSCALES,
    choices=choices,
    result_note=RESULT_NOTE,
    score=score,
    listed=False,
    always_aided=True,
)
