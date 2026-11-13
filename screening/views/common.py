import re

from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache

from screening import oidc


def safe_next(request):
    # Only same-site URLs; anything else is treated as no next (open redirect guard).
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return ""


def health_data_page(view):
    """Mark a 健康資料頁面 (GLOSSARY.md): never cached, so after logging out on a shared computer
    the back button cannot show it again (#182). test_standards checks every logged-in view."""
    view = never_cache(view)
    view.health_data_page = True
    return view


# #465 (the #464 mockup 8A, 8E): 我的紀錄 lists the newest this many records of a tab, or
# audiograms, and folds the older ones under 「看以前的 N 筆／張」.
RECENT_SHOWN = 3


def older_fold(rows, day, unit):
    """The rows past the newest RECENT_SHOWN (rows: newest first), the fold's title (a draft)
    and the first to last day folded; None when nothing is folded. day: a row's date."""
    older = rows[RECENT_SHOWN:]
    if not older:
        return None
    return {
        "rows": older,
        "title": f"看以前的 {len(older)} {unit}",
        "dates": f"{day(older[-1]):%Y/%m/%d} 到 {day(older[0]):%Y/%m/%d}",
    }


# Spec #505, #506: why a Google or LINE trip did not end signed in, said once on the login or
# register page.
SIGN_IN_ERROR = "screening.sign_in_error"


# LINE publishes no User-Agent format (looked up 2026-11-13; login-research.md section 9). LINE's
# own LIFF SDK decides "is this LINE's browser" with exactly this pattern: @liff/util 2.32.0
# (npm, published 2026-11-09), isLINEBrowser = /Line\/\d+\.\d+\.\d+/ (isLIFFBrowser adds " LIFF").
# Strings seen in the wild, both covered:
#   iOS (Classmethod, 2025-08-18): "... Mobile/15E148 Safari Line/15.12.1"
#   Android (ua-parser-js 2.0.10 test data): "... Mobile Safari/537.36 Line/6.5.1/IAB"
# It also matches the LIFF browser, where Google is just as blocked. Case-sensitive, as in LIFF.
LINE_USER_AGENT = re.compile(r"Line/\d+\.\d+\.\d+")


def is_line_in_app_browser(request):
    """True when the page was opened inside LINE, where Google refuses to sign in (an embedded
    web view, Google's disallowed_useragent). The login, register and save card pages and the
    LINE spec (#506) all ask here."""
    return bool(LINE_USER_AGENT.search(request.headers.get("user-agent", "")))


def sign_in_choices(request):
    """What the login and register pages show around the password form: above it the LINE and
    the Google button, each when set up, but inside LINE no Google: a way out to Safari or Chrome
    under the form instead (#506, the #539 mockup D3); and the error a trip came back with (taken
    out, so said once)."""
    google = oidc.enabled("google")
    return {
        "line_sign_in": oidc.enabled("line"),
        "google_sign_in": google and not is_line_in_app_browser(request),
        "open_outside_url": line_way_out(request) if google else "",
        "sign_in_error": request.session.pop(SIGN_IN_ERROR, ""),
    }


def line_way_out(request):
    """Inside LINE, the open-in-Safari-or-Chrome URL that takes a Google button's place on a
    page; empty anywhere else (#511: account settings, the confirm and delete pages)."""
    return open_outside_url(request) if is_line_in_app_browser(request) else ""


def open_outside_url(request):
    """This page again with LINE's openExternalBrowser=1, which makes LINE open it in Safari or
    Chrome instead of its own browser (login-research.md L10); the page's own query is kept."""
    query = request.GET.copy()
    query["openExternalBrowser"] = "1"
    return f"{request.path}?{query.urlencode()}"
