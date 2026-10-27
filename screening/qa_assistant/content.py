from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Faq:
    # The answer page's address (qa/<code>): English, never changed or reused once live
    # (ADR 0033).
    code: str
    # One of TOPICS' slugs.
    topic: str
    question: str
    # Paragraphs of simple HTML, links as site paths. General wording: 一般來說, 依法規, never
    # 「您……」 (ADR 0032). Where the guide or the family page already says it, a short answer
    # and a link to that chapter, without its amounts or years (ADR 0033).
    answer: str
    # (title, address) pairs, shown under 資料來源.
    sources: tuple
    # 本頁資料查核於: checked with the hearing-aid guide each year (ADR 0033).
    checked_on: date
    # Other ways of asking it, for typed questions (#399).
    other_phrasings: tuple = ()
    # Codes of the related questions shown under the answer (#398).
    related: tuple = ()
    # A referral answer: says where to ask instead of answering (ADR 0032).
    referral: bool = False


# The four topics in display order (spec #396): (slug, name).
TOPICS = (
    ("using-the-site", "網站怎麼用"),
    ("questionnaires", "問卷是什麼"),
    ("hearing-aids", "助聽器選配與補助"),
    ("hearing-health", "聽力保健常識"),
)

# The answers below are placeholders for the owner to review; #402 writes the real ones.
FAQS = (
    Faq(
        code="my-results",
        topic="questionnaires",
        question="我的分數代表什麼？",
        answer=(
            "<p>小助手只回答一般的問題，不解讀個人的結果。每次做完問卷，結果頁都有分級和建議，"
            "做過的問卷都留在「我的紀錄」。</p>"
            "<p>想進一步了解，可以把結果頁帶給聽力師看。</p>"
            '<p><a href="/my_hearing">到「我的紀錄」看結果</a></p>'
        ),
        sources=(("HearWell 隱私權說明：不是醫療診斷", "/privacy#diagnosis-title"),),
        checked_on=date(2026, 10, 27),
        related=("diagnosis-and-medication", "brands-and-shops"),
        referral=True,
    ),
    Faq(
        code="diagnosis-and-medication",
        topic="hearing-health",
        question="聽力變差是什麼病？要吃什麼藥？",
        answer=(
            "<p>診斷和用藥要由醫師看過、做過檢查才能判斷，小助手不回答個人的診斷和用藥。</p>"
            "<p>一般來說，聽力變差、耳朵不舒服，或想知道某種藥會不會影響聽力，"
            "請到耳鼻喉科就診，問耳鼻喉科醫師。</p>"
        ),
        sources=(("HearWell 隱私權說明：不是醫療診斷", "/privacy#diagnosis-title"),),
        checked_on=date(2026, 10, 27),
        related=("sudden-hearing-loss", "my-results"),
        referral=True,
    ),
    Faq(
        code="brands-and-shops",
        topic="hearing-aids",
        question="哪個牌子的助聽器比較好？去哪家店買？",
        answer=(
            "<p>小助手不推薦品牌、型號或店家。一般來說，適合的助聽器要看聽力圖和生活需要，"
            "由聽力師評估後一起挑選。</p>"
            "<p>助聽器有哪些外型、價格和補助上限，請看選配指引的"
            '<a href="/guide/types-and-prices">「助聽器的種類與價格」</a>。'
            "要申請身障補助，先要到鑑定醫院做身障鑑定，可以用"
            '<a href="/guide/assessment#hospitals-title">「找鑑定醫院」</a>查各縣市的醫院。</p>'
        ),
        sources=(
            ("我的選配指引：助聽器的種類與價格", "/guide/types-and-prices"),
            ("我的選配指引：身障鑑定與鑑定醫院", "/guide/assessment"),
        ),
        checked_on=date(2026, 10, 27),
        related=("my-results", "diagnosis-and-medication"),
        referral=True,
    ),
    Faq(
        code="sudden-hearing-loss",
        topic="hearing-health",
        question="突然聽不到、耳朵流血，該怎麼辦？",
        answer=(
            "<p><strong>請盡快到耳鼻喉科就醫，不要等下次回診。</strong></p>"
            "<p>一般來說，突然聽不到或聽力變差（一耳或兩耳，幾小時到幾天內發生）"
            "可能是突發性聽力損失，越早治療效果越好。耳朵痛、流膿或流血、嚴重暈眩，"
            "或頭部受傷後聽力改變，也要盡快就醫。</p>"
            "<p>如果同時出現臉歪嘴斜、單側手腳無力、說話不清楚，可能是中風，"
            "請立刻撥打 119。</p>"
            "<p>完整的說明在給家人看的"
            '<a href="/family#urgent-title">「什麼時候要馬上就醫」</a>。</p>'
        ),
        sources=(
            (
                "AAO-HNSF〈Clinical Practice Guideline: Sudden Hearing Loss (Update)〉",
                "https://pubmed.ncbi.nlm.nih.gov/31369359/",
            ),
            (
                "NIDCD〈Sudden Sensorineural Hearing Loss〉",
                "https://www.nidcd.nih.gov/health/sudden-deafness",
            ),
        ),
        checked_on=date(2026, 10, 27),
        related=("diagnosis-and-medication", "my-results"),
        referral=True,
    ),
)

BY_CODE = {faq.code: faq for faq in FAQS}

# Pinned above everything on the home page (ADR 0032).
URGENT_CODE = "sudden-hearing-loss"

# 大家常問 in display order, the owner's pick (#402 settles the real 3 to 5).
POPULAR = ("my-results", "brands-and-shops", "diagnosis-and-medication")

# Codes of questions taken out (ADR 0033): their old addresses go to the home page, and no new
# question may use them again. Add a code here when its question leaves FAQS.
RETIRED_CODES = frozenset()
