from decimal import ROUND_HALF_UP, Decimal

from screening.questionnaires.definition import HEARING_AID, Definition
from screening.questionnaires.results import SubscaleResult

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


# Items from HARL's manual scoring instructions (SADLScoring.pdf, 2003); explanations approved
# by the owner in #168.
SUBSCALE_ITEMS = (
    (
        "正面效果",
        (1, 3, 5, 6, 9, 10),
        "戴助聽器帶來多少好處，例如比較聽得懂別人說話、比較少請人重說、比較有自信、"
        "聲音聽起來自然。",
    ),
    (
        "服務與費用",
        (12, 14, 15),
        "您對幫您調整助聽器的人員、助聽器的價格，以及助聽器耐不耐用，滿意的程度。",
    ),
    (
        "負面特徵",
        (2, 7, 11),
        "助聽器帶來的困擾，例如聲音跟預期不同、轉大聲時出現迴音（嘯叫聲），"
        "以及講電話時幫不幫得上忙。分數越高，代表困擾越少。",
    ),
    (
        "個人形象",
        (4, 8, 13),
        "戴助聽器時，您在不在意外觀和別人的眼光。分數越高，代表越不在意、對自己的樣子越滿意。",
    ),
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
            {
                "name": name,
                "score": _average([scored[n] for n in items if n in scored]),
                "explanation": explanation,
            }
            for name, items, explanation in SUBSCALE_ITEMS
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
    concern=HEARING_AID,
    intro_template="screening/questionnaires/sadl_intro.html",
    source_template="screening/sadl_source.html",
    result=SubscaleResult,
    choices=choices,
    result_note=RESULT_NOTE,
    score=score,
    always_aided=True,
)
