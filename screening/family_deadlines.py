"""期限試算 (#432, spec #426): the words and the dates worked out from the days someone types.
Nothing here touches a request or the database, and nothing is kept. The words are drafts until
the owner has reviewed them (batch-2-wording.md section 3)."""

from dataclasses import dataclass
from datetime import date

from screening.family_zone import VISIT_SOURCES
from screening.fitting_route import add_months, form_25_window

FORM_9_VALID_MONTHS = 3
NOTICE_PURCHASE_MONTHS = 6

INTRO = "輸入手上有的日期，只填一個也可以。日期不會留下來。"
FORM_9_LABEL = "九號表開立日期"
NOTICE_LABEL = "收到核定通知日期"
FITTED_LABEL = "開始配戴日期"
SUBMIT_LABEL = "試算"
RESULTS_TITLE = "試算結果"
PASSED_NOTE = "這個日期已過，請向公所或聽力師確認。"
CLOSING_NOTE = "這裡只幫忙算日期，實際期限以主管機關的通知為準。"
BLANK_ERROR = "請至少填一個日期。"
INVALID_ERROR = "請輸入正確的日期。"
FUTURE_ERROR = "這個日期不能是未來。"

# The same two laws 陪診清單 cites.
DEADLINE_SOURCES = VISIT_SOURCES
# The earliest check of the chapters the three deadlines come from.
DEADLINE_CHECKED_ON = date(2026, 10, 22)


@dataclass(frozen=True)
class Deadline:
    words: str
    passed_note: str  # empty until the deadline is before today


def _shown(day):
    return day.strftime("%Y/%m/%d")


def _deadline(words, last_day, today):
    return Deadline(words, PASSED_NOTE if last_day < today else "")


def deadlines(form_9_on, notice_on, fitted_on, *, today):
    """Only the days given (the others None), in the order the form asks them."""
    results = []
    if form_9_on:
        valid_until = add_months(form_9_on, FORM_9_VALID_MONTHS)
        words = f"九號表有效到 {_shown(valid_until)}（{FORM_9_VALID_MONTHS} 個月內有效）。"
        if valid_until >= today:
            words += "請在這天以前到公所申請。"
        results.append(_deadline(words, valid_until, today))
    if notice_on:
        buy_by = add_months(notice_on, NOTICE_PURCHASE_MONTHS)
        words = (
            f"購買並請款的期限：{_shown(buy_by)}"
            f"（收到核定通知後 {NOTICE_PURCHASE_MONTHS} 個月內）。"
        )
        results.append(_deadline(words, buy_by, today))
    if fitted_on:
        first, last = form_25_window(fitted_on)
        words = (
            f"二十五號表可以做的日期：{_shown(first)} 到 {_shown(last)}。"
            "買中階型、進階型或雙對側傳聲型要做，簡易型不需要二十五號表。"
        )
        results.append(_deadline(words, last, today))
    return tuple(results)
