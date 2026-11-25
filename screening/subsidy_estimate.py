"""補助引導與試算's questions, rules and words (#775, spec #774, ADR 0083), in one place for the
owner's review. No request, no database, nothing kept. The words are drafts until the owner has
reviewed them. The amounts are research.md's: the 基準表's items 82–85 and article 3's shares,
and (#776) 低收入戶老人配戴助聽器獎助基準's 5,500 an aid for those without a certificate.
ADR 0017: it gives the most the subsidy could be and never says someone will get it."""

from dataclasses import dataclass
from datetime import date

from screening.family_deadlines import FORM_9_VALID_MONTHS, NOTICE_PURCHASE_MONTHS

# The answers' values.
HAS, PLANNING, NONE = "has", "planning", "none"
NO_FORM, HAS_FORM, APPLIED, NOTICE = "no_form", "has_form", "applied", "notice"
BASIC, MID, ADVANCED, CROS = "basic", "mid", "advanced", "cros"
ONE, BOTH = "one", "both"
LOW, NEAR_LOW, GENERAL = "low", "near_low", "general"
YES, NO, UNSURE = "yes", "no", "unsure"

# The most per hearing aid (基準表 items 82–84), or per set of two for 雙對側傳聲型 (item 85).
MOST_PER_AID = {BASIC: 2000, MID: 10000, ADVANCED: 20000, CROS: 30000}
# Article 3: the share of that most, in percent, by the household.
SHARE_PERCENT = {LOW: 100, NEAR_LOW: 75, GENERAL: 50}
# The 基準表's special rule (#776): 進階型 for someone first assessed mild at 65 or over has a
# cap on the total within the years it must last, by the household.
MILD_AT_65_CAP = {LOW: 20000, NEAR_LOW: 15000, GENERAL: 10000}
# Without a certificate (#776): 低收入戶老人配戴助聽器補助's most per hearing aid.
ELDER_MOST_PER_AID = 5500


@dataclass(frozen=True)
class Question:
    # The form field's name and the key of this question's answer in estimate().
    name: str
    label: str
    choices: tuple


CERTIFICATE = Question(
    "certificate",
    "有聽覺機能的身心障礙證明嗎？",
    ((HAS, "有"), (PLANNING, "打算申請或正在申請鑑定"), (NONE, "沒有")),
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
# #776: asked with 進階型 alone, for the special rule's cap (MILD_AT_65_CAP).
MILD_AT_65 = Question(
    "mild_at_65",
    "是不是滿 65 歲以後才第一次鑑定為輕度？",
    ((YES, "是"), (NO, "否"), (UNSURE, "不確定")),
)
# #776: the one question asked without a certificate.
ELDER = Question(
    "elder",
    "是不是 65 歲以上（原住民 55 歲以上）的低收入戶？",
    ((YES, "是"), (NO, "不是")),
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
    # None where there is no subsidy to estimate (#776: no certificate, not a low-income elder).
    amount: int | None
    next_step: Step
    reminders: tuple = ()
    # The amount is the most for each hearing aid, not the total.
    each: bool = False

    @property
    def amount_words(self):
        return f"每只 {self.amount:,} 元" if self.each else f"{self.amount:,} 元"


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
    (
        "衛生福利部社會及家庭署低收入戶老人配戴助聽器獎助項目及基準"
        "（114–117 年，嘉義市政府社會處轉載）",
        "https://social.chiayi.gov.tw/News_Content.aspx?n=1101&s=909655",
    ),
)
# Taken over from the form 9 chapter, whose amounts these are: the law was not checked again.
CHECKED_ON = date(2026, 10, 23)

# Written out with their anchors; the page's tests open each one and look for its anchor.
_HOSPITALS = Link("看各縣市的鑑定醫院", "/guide/assessment#hospitals-title")
_WHO_ISSUES_FORM_9 = Link("九號表去哪裡開？", "/guide/form-9#issuer-title")
_FORM_25 = Link("看二十五號表", "/guide/form-25")
_WITHOUT_CERTIFICATE = Link("看沒有身障證明時", "/guide/form-9#without-certificate")

# Without a certificate (#776, the form 9 chapter's 沒有身障證明怎麼辦？).
_ELDER_APPLY = Step(
    "先向縣市政府申請",
    "聽力損失在 45 到 110 分貝之間可以申請。帶 6 個月內的診斷證明書和聽力圖正本，"
    "向設籍或居住的縣市政府申請，審核通過再買。",
    _WITHOUT_CERTIFICATE,
)
_ELDER_AMOUNTS = Item(
    f"低收入戶老人配戴助聽器補助每只最高 {ELDER_MOST_PER_AID:,} 元、"
    f"雙耳 {ELDER_MOST_PER_AID * 2:,} 元，同一耳 4 年一次。"
)
_FITTING_NOW = Step(
    "直接預約聽力師試戴",
    "沒有身障證明，買助聽器不用等公文，可以直接預約聽力師試戴。"
    "有些縣市的輔具中心也有免費評估和試戴。",
    _WITHOUT_CERTIFICATE,
)

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


def _mild_at_65_reminder(cap, amount):
    words = f"如果是滿 65 歲以後才第一次鑑定為輕度，進階型的補助總額最多 {cap:,} 元"
    ending = "，會比上面的金額少。" if cap < amount else "。"
    return Item(words + ending)


def _on_the_way(answers):
    """The questions asked, in order; each one decided only once those before it are answered."""
    yield CERTIFICATE
    if answers[CERTIFICATE.name] == NONE:
        yield ELDER
        return
    # Planning to apply has no application under way yet (the owner's pick after #775).
    if answers[CERTIFICATE.name] != PLANNING:
        yield PROGRESS
    yield GRADE
    # A set of 雙對側傳聲型 counts as one, for either ear (item 85).
    if answers[GRADE.name] != CROS:
        yield EARS
    yield HOUSEHOLD
    if answers[GRADE.name] == ADVANCED:
        yield MILD_AT_65


def estimate(answers):
    """The next Question to ask, or the Result once every question on the way is answered.
    answers: each answer so far, by its question's name, every value one of its choices."""
    for question in _on_the_way(answers):
        if question.name not in answers:
            return question
    if answers[CERTIFICATE.name] == NONE:
        if answers[ELDER.name] == YES:
            return Result(ELDER_MOST_PER_AID, _ELDER_APPLY, (_ELDER_AMOUNTS,), each=True)
        return Result(None, _FITTING_NOW)
    amount, reminders = _amount(answers), []
    if answers[GRADE.name] == ADVANCED:
        cap = MILD_AT_65_CAP[answers[HOUSEHOLD.name]]
        if answers[MILD_AT_65.name] == YES:
            amount = min(amount, cap)
        elif answers[MILD_AT_65.name] == UNSURE:
            reminders.append(_mild_at_65_reminder(cap, amount))
    if answers[CERTIFICATE.name] == PLANNING:
        return Result(amount, _ASSESSMENT_FIRST, (*reminders, _NOTICE_FIRST))
    progress = answers[PROGRESS.name]
    if progress != NOTICE:
        reminders.append(_NOTICE_FIRST)
    elif answers[GRADE.name] != BASIC:
        reminders.append(_FORM_25_DUE)
    return Result(amount, _NEXT_STEPS[progress], tuple(reminders))
