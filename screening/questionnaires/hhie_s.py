from screening.questionnaires.comparison import TotalComparison
from screening.questionnaires.definition import LEVEL, Definition

CODE = "hhie-s"

THRESHOLDS = (
    (8, "無/極輕微影響", "normal"),
    (24, "輕度到中度影響", "mild_to_moderate"),
    (40, "顯著影響", "severe"),
)

ADVICE = {
    "normal": (
        "您的聽覺自覺障礙程度為無或是僅有輕微障礙，聽力的部分並未明顯影響"
        "您的情緒以及社交活動，然而高齡族群的聽力退化往往是較無自覺的，"
        "建議若未進行過聽力檢查能夠至醫院進行定期篩檢。"
    ),
    "mild_to_moderate": (
        "聽力的問題已經慢慢開始影響到您的社交活動以及情緒，例如"
        "與家人之間常常因為聽不清楚或是電視聲音等而產生爭吵、在多人且吵雜的"
        "社交環境當中會因為聽不清楚而導致社交上的窘迫及退縮，許多聽力衰退"
        "帶來的問題是微妙且和緩的，但經過此次篩檢能夠讓您體認到聽力對自身生"
        "活的影響，建議前往醫院耳鼻喉科進行聽力相關檢查及詢問相關專業意見。"
    ),
    "severe": (
        "聽力問題已經嚴重影響到您的生活了，許多人常常會忽視這一塊，聽不到這件事"
        "情往往已經十分嚴重了才會發現，若您尚未採取任何行動建議立即前往醫院耳鼻"
        "喉科尋求專業建議，並且考慮配戴助聽器。聽力喪失影響的並不只是聽不聽得到，"
        "無形中也會增加社交活動的壓力（例如因為聽不清楚常會在聊天的過程中退縮、"
        "裝作聽得懂等），這些壓力以及情緒的低落會增加長者的認知負擔。"
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
    result=LEVEL,
    thresholds=THRESHOLDS,
    advice=ADVICE,
    trend_chart=True,
    # The report anchor it had before other questionnaires could be compared.
    comparison=TotalComparison(anchor="report-difference"),
)
