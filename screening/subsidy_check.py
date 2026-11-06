"""補助檢核's questions, rules and words (#431, spec #426), in one place for the owner's review.
Plain Python: no request, no database, nothing kept. Words of batch-2-wording.md section 2, drafts
until the owner has reviewed them. ADR 0017: it lists what is still missing and never says someone
qualifies; whether the subsidy is granted is the authority's call."""

from dataclasses import dataclass
from datetime import date

# The answers' values.
HEARING, VISION, NEITHER = "hearing", "vision", "neither"
YES, NO = "yes", "no"
NO_FORM, HAS_FORM, APPLIED, NOTICE = "no_form", "has_form", "applied", "notice"
NOT_BOUGHT, BOUGHT = "not_bought", "bought"
NEVER, PAST_MINIMUM, TOO_SOON = "never", "past_minimum", "too_soon"
UNSURE = "unsure"


@dataclass(frozen=True)
class Link:
    words: str
    url: str


@dataclass(frozen=True)
class Item:
    words: str
    links: tuple = ()


@dataclass(frozen=True)
class Result:
    headline: str
    missing: tuple = ()
    to_confirm: tuple = ()
    reminders: tuple = ()
    next_steps: tuple = ()

    @property
    def groups(self):
        """(heading, items) of each group that has something, in the order the page shows them."""
        groups = (
            ("還缺", self.missing),
            ("要先確認", self.to_confirm),
            ("提醒", self.reminders),
            ("下一步", self.next_steps),
        )
        return tuple(group for group in groups if group[1])


@dataclass(frozen=True)
class Question:
    # The form field's name and the key of this question's answer in check().
    name: str
    label: str
    choices: tuple


QUESTIONS = (
    Question(
        "certificate",
        "申請的人有哪一種身心障礙證明？",
        (
            (HEARING, "聽覺機能（第二類 b230、s260，或舊制 02）"),
            (VISION, "中度以上視覺障礙"),
            (NEITHER, "上面兩種都沒有"),
            (UNSURE, "不確定"),
        ),
    ),
    Question(
        "residence",
        "最近一年，申請的人在國內住超過 183 天嗎？",
        ((YES, "是"), (NO, "否"), (UNSURE, "不確定")),
    ),
    Question(
        "progress",
        "九號表和核定通知辦到哪裡了？",
        (
            (NO_FORM, "還沒有九號表"),
            (HAS_FORM, "有九號表，還沒到公所申請"),
            (APPLIED, "已經到公所申請，在等核定通知"),
            (NOTICE, "已經收到核定通知"),
            (UNSURE, "不確定"),
        ),
    ),
    Question(
        "purchase",
        "助聽器買了嗎？",
        ((NOT_BOUGHT, "還沒買"), (BOUGHT, "已經買了"), (UNSURE, "不確定")),
    ),
    Question(
        "previous",
        "以前領過這項助聽器補助嗎？",
        (
            (NEVER, "沒有"),
            (PAST_MINIMUM, "領過，已滿 4 年（12 歲以下滿 2 年）"),
            (TOO_SOON, "領過，還沒滿"),
            (UNSURE, "不確定"),
        ),
    ),
)

INTRO = (
    "回答幾題，看申請助聽器補助還缺什麼。這裡不判斷能不能拿到補助，"
    "是否補助以主管機關核定為準。回答不會留下來。"
)

CAN_APPLY = "可以去申請，是否補助以主管機關核定為準。"
NOTHING_MISSING = "目前沒有看到缺的項目，是否補助以主管機關核定為準。"
SEE_BELOW = "下面這些要先辦好或確認。"

# At the foot of every result.
FORM_9_LINK = Link("看九號表的流程", "/guide/form-9")
SUBSIDY_SOURCES = (
    (
        "身心障礙者輔具費用補助辦法（全國法規資料庫）",
        "https://law.moj.gov.tw/LawClass/LawAll.aspx?PCODE=D0050060",
    ),
    (
        "身心障礙者輔具費用補助基準表（全國法規資料庫）",
        "https://law.moj.gov.tw/LawClass/LawGetFile.ashx?FileId=0000326887&lan=C",
    ),
)
# Taken over from the form 9 chapter (batch-2-wording.md): the law was not checked again.
SUBSIDY_CHECKED_ON = date(2026, 10, 23)

# Written out rather than reversed, so this module needs nothing of Django. The page's tests open
# each one and look for its anchor, but for the deadlines page, which #432 adds.
_APPLY_FOR_ASSESSMENT = Link("怎麼申請鑑定", "/guide/assessment#apply-title")
_WITHOUT_CERTIFICATE = Link("沒有身障證明時", "/guide/form-9#without-certificate")
_WHO_ISSUES_FORM_9 = Link("九號表找誰開", "/guide/form-9#issuer-title")
_DEADLINES = Link("期限試算", "/family/visits/deadlines")
_FORM_25 = Link("二十五號表", "/guide/form-25")

_REAPPLY_AFTER = "滿 4 年可再申請（12 歲以下每 2 年）。"
_NO_NOTICE_NO_SUBSIDY = "沒核定就先買的不補助。"
_NOTICE_FIRST = f"一定要先拿到核定通知再買，{_NO_NOTICE_NO_SUBSIDY}"


def check(answers):
    """The Result for one set of answers: each question's in QUESTIONS, by its name. One `if` per
    row of the draft's table, in its order."""
    certificate = answers["certificate"]
    residence = answers["residence"]
    progress = answers["progress"]
    purchase = answers["purchase"]
    previous = answers["previous"]
    missing, to_confirm, reminders, next_steps = [], [], [], []

    if certificate == VISION:
        to_confirm.append(Item("好的那一耳聽力損失是否大於 40 dB。"))
    elif certificate == NEITHER:
        missing.append(
            Item(
                "要有聽覺機能的身心障礙證明，或中度以上視覺障礙且好的那一耳聽力損失大於 40 dB，"
                "才能申請這項補助。"
            )
        )
        next_steps.append(
            Item(
                "到戶籍所在縣市的公所申請身障鑑定，再帶公所給的鑑定表到鑑定醫院。",
                (_APPLY_FOR_ASSESSMENT, _WITHOUT_CERTIFICATE),
            )
        )
    elif certificate == UNSURE:
        to_confirm.append(Item("有沒有上面兩種身心障礙證明，可以問戶籍所在地公所。"))

    if residence == NO:
        missing.append(Item("最近一年要在國內住超過 183 天。實際情況請向戶籍所在地公所確認。"))
    elif residence == UNSURE:
        to_confirm.append(Item("最近一年在國內是否住超過 183 天。"))

    # Bought with no notice: telling them to go and apply would sit beside 沒核定就先買的不補助, so
    # question 3 adds nothing and only that reminder stays (batch-2-wording.md section 2).
    bought_without_notice = purchase == BOUGHT and progress in (NO_FORM, HAS_FORM, APPLIED)
    if bought_without_notice:
        pass
    elif progress == NO_FORM:
        missing.append(
            Item(
                "九號表：找聽力師或縣市輔具中心做評估。九號表 3 個月內有效。",
                (_WHO_ISSUES_FORM_9,),
            )
        )
    elif progress == HAS_FORM:
        next_steps.append(
            Item(
                "帶申請表、身分證正本和九號表，到戶籍所在地的公所申請，也可以線上申請。"
                "九號表 3 個月內有效。",
                (_DEADLINES,),
            )
        )
    elif progress == APPLIED:
        next_steps.append(Item("主管機關收到評估報告後，10 天內會核定。"))
    elif progress == NOTICE:
        next_steps.append(
            Item(
                "收到核定通知後 6 個月內購買並請款。"
                "買中階型、進階型或雙對側傳聲型的人，配戴滿 1 個月到 3 個月內要做二十五號表。",
                (_DEADLINES, _FORM_25),
            )
        )
    elif progress == UNSURE:
        to_confirm.append(Item("九號表和核定通知辦到哪裡了，可以問戶籍所在地公所。"))

    if purchase == NOT_BOUGHT:
        reminders.append(Item(_NOTICE_FIRST))
    elif bought_without_notice:
        reminders.append(Item(f"{_NO_NOTICE_NO_SUBSIDY}請向戶籍所在地公所確認實際情況。"))
    elif purchase == BOUGHT and progress == NOTICE:
        to_confirm.append(
            Item(f"是不是收到核定通知之後才買的，而且在 6 個月內。{_NO_NOTICE_NO_SUBSIDY}")
        )
    elif purchase == BOUGHT:  # question 3 unsure
        to_confirm.append(Item(f"有沒有核定通知，請向戶籍所在地公所確認。{_NO_NOTICE_NO_SUBSIDY}"))
    elif purchase == UNSURE:
        to_confirm.append(Item(f"助聽器買了沒有。{_NOTICE_FIRST}"))

    if previous == PAST_MINIMUM:
        next_steps.append(Item("再次申請簡易型，不需要重新評估。"))
    elif previous == TOO_SOON:
        missing.append(Item(_REAPPLY_AFTER))
    elif previous == UNSURE:
        to_confirm.append(Item(f"上次領補助是哪一年。{_REAPPLY_AFTER}"))

    if missing or to_confirm or bought_without_notice:
        headline = SEE_BELOW
    elif progress == HAS_FORM:
        headline = CAN_APPLY
    else:
        headline = NOTHING_MISSING
    return Result(headline, tuple(missing), tuple(to_confirm), tuple(reminders), tuple(next_steps))
