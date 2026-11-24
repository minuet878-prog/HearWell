"""補助引導與試算's questions, rules and words (#775, spec #774, ADR 0083), in one place for the
owner's review. No request, no database, nothing kept. The words are drafts until the owner has
reviewed them. The amounts are research.md's: the 基準表's items 82–85 and article 3's shares.
ADR 0017: it gives the most the subsidy could be and never says someone will get it."""

from dataclasses import dataclass
from datetime import date

from screening.family_deadlines import FORM_9_VALID_MONTHS, NOTICE_PURCHASE_MONTHS

# The answers' values.
HAS, PLANNING = "has", "planning"
NO_FORM, HAS_FORM, APPLIED, NOTICE = "no_form", "has_form", "applied", "notice"
BASIC, MID, ADVANCED, CROS = "basic", "mid", "advanced", "cros"
ONE, BOTH = "one", "both"
LOW, NEAR_LOW, GENERAL = "low", "near_low", "general"

# The most per hearing aid (基準表 items 82–84), or per set of two for 雙對側傳聲型 (item 85).
MOST_PER_AID = {BASIC: 2000, MID: 10000, ADVANCED: 20000, CROS: 30000}
# Article 3: the share of that most, in percent, by the household.
SHARE_PERCENT = {LOW: 100, NEAR_LOW: 75, GENERAL: 50}


@dataclass(frozen=True)
class Question:
    # The form field's name and the key of this question's answer in estimate().
    name: str
    label: str
    choices: tuple


CERTIFICATE = Question(
    "certificate",
    "有聽覺機能的身心障礙證明嗎？",
    # #776 adds 沒有.
    ((HAS, "有"), (PLANNING, "打算申請或正在申請鑑定")),
)
PROGRESS = Question(
    "progress",
    "補助申請辦到哪一步了？",
    (
        (NO_FORM, "還沒做九號表"),
        (HAS_FORM, "九號表做好了，還沒送件"),
        (APPLIED, "已經送件，在等核定公文"),
        (NOTICE, "已經收到核定公文"),
    ),
)
GRADE = Question(
    "grade",
    "預計買哪一級的助聽器？",
    (
        (BASIC, "簡易型"),
        (MID, "中階型"),
        (ADVANCED, "進階型"),
        (CROS, "雙對側傳聲型（兩件算一組）"),
    ),
)
EARS = Question("ears", "預計配單耳還是雙耳？", ((ONE, "單耳"), (BOTH, "雙耳")))
HOUSEHOLD = Question(
    "household",
    "戶籍的福利身分是哪一種？",
    ((GENERAL, "一般戶"), (NEAR_LOW, "中低收入戶"), (LOW, "低收入戶")),
)


@dataclass(frozen=True)
class Link:
    words: str
    url: str


@dataclass(frozen=True)
class Step:
    """The one thing to do now: its title says by when, its words how."""

    title: str
    words: str
    link: Link | None = None


@dataclass(frozen=True)
class Item:
    words: str
    link: Link | None = None


@dataclass(frozen=True)
class Result:
    amount: int
    next_step: Step
    reminders: tuple = ()

    @property
    def amount_words(self):
        return f"{self.amount:,} 元"


# The page's words around the questions and the result.
INTRO = "回答幾題，算算看助聽器補助最多有多少、現在要做什麼。不用登入，回答不會留下來。"
AMOUNT_LABEL = "預估最高補助"
# Under every amount (ADR 0017: never that someone will get it).
AMOUNT_NOTE = "以實際購買金額為上限，是否補助以主管機關核定為準。"
NEXT_STEP_LABEL = "現在要做的事"
# Not worked into the amount (spec #774, the owner's pick 2026-11-24): only said on every result.
YOUNG_NOTE = "18 歲以下或 25 歲以下在學的人另有規定，金額可能不同，請向戶籍所在地的公所確認。"

SOURCES = (
    (
        "身心障礙者輔具費用補助辦法（全國法規資料庫）",
        "https://law.moj.gov.tw/LawClass/LawAll.aspx?PCODE=D0050060",
    ),
    (
        "身心障礙者輔具費用補助基準表（全國法規資料庫）",
        "https://law.moj.gov.tw/LawClass/LawGetFile.ashx?FileId=0000326887&lan=C",
    ),
)
# Taken over from the form 9 chapter, whose amounts these are: the law was not checked again.
CHECKED_ON = date(2026, 10, 23)

# Written out with their anchors; the page's tests open each one and look for its anchor.
_HOSPITALS = Link("看各縣市的鑑定醫院", "/guide/assessment#hospitals-title")
_WHO_ISSUES_FORM_9 = Link("九號表去哪裡開？", "/guide/form-9#issuer-title")
_FORM_25 = Link("看二十五號表", "/guide/form-25")

# Planning to apply: there is no 九號表 to speak of before the certificate (spec #774).
_ASSESSMENT_FIRST = Step(
    "先找醫院做身障鑑定",
    "先到戶籍所在地的公所申請鑑定，再帶公所給的鑑定表到鑑定醫院。"
    "拿到聽覺機能的身心障礙證明，才能申請這項補助。",
    _HOSPITALS,
)
_NEXT_STEPS = {
    NO_FORM: Step(
        "找聽力師做九號表",
        f"找聽力師或縣市輔具中心做評估，拿到九號表。九號表 {FORM_9_VALID_MONTHS} 個月內有效。",
        _WHO_ISSUES_FORM_9,
    ),
    HAS_FORM: Step(
        f"{FORM_9_VALID_MONTHS} 個月內送件",
        f"九號表 {FORM_9_VALID_MONTHS} 個月內有效。帶申請表、身分證正本和九號表，"
        "到戶籍所在地的公所申請，也可以線上申請。",
    ),
    APPLIED: Step("等核定公文", "主管機關收到九號表後 10 天內會核定，再寄核定公文給您。"),
    NOTICE: Step(
        f"{NOTICE_PURCHASE_MONTHS} 個月內購買",
        f"收到核定公文後 {NOTICE_PURCHASE_MONTHS} 個月內買好助聽器並請款。",
    ),
}

_NOTICE_FIRST = Item("先拿核定公文再買，先買不補助。")
# Items 83–85 are checked after fitting with form 25; the basic type (item 82) is not.
_FORM_25_DUE = Item("中階型以上要在配戴 1 到 3 個月內做二十五號表，核銷時要附上。", _FORM_25)


def _amount(answers):
    grade = answers[GRADE.name]
    aids = 2 if grade != CROS and answers[EARS.name] == BOTH else 1
    return MOST_PER_AID[grade] * SHARE_PERCENT[answers[HOUSEHOLD.name]] // 100 * aids


def _on_the_way(answers):
    """The questions asked, in order; each one decided only once those before it are answered."""
    yield CERTIFICATE
    yield PROGRESS
    yield GRADE
    # A set of 雙對側傳聲型 counts as one, for either ear (item 85).
    if answers[GRADE.name] != CROS:
        yield EARS
    yield HOUSEHOLD


def estimate(answers):
    """The next Question to ask, or the Result once every question on the way is answered.
    answers: each answer so far, by its question's name, every value one of its choices."""
    for question in _on_the_way(answers):
        if question.name not in answers:
            return question
    if answers[CERTIFICATE.name] == PLANNING:
        return Result(_amount(answers), _ASSESSMENT_FIRST, (_NOTICE_FIRST,))
    progress = answers[PROGRESS.name]
    if progress != NOTICE:
        reminders = (_NOTICE_FIRST,)
    elif answers[GRADE.name] != BASIC:
        reminders = (_FORM_25_DUE,)
    else:
        reminders = ()
    return Result(_amount(answers), _NEXT_STEPS[progress], reminders)
