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


# Spec #505: why a Google trip did not end signed in, said once on the login or register page.
SIGN_IN_ERROR = "screening.sign_in_error"


def sign_in_choices(request):
    """What the login and register pages show above the password form: the Google button when
    Google is set up, and the error a Google trip came back with (taken out, so said once)."""
    return {
        "google_sign_in": oidc.enabled("google"),
        "sign_in_error": request.session.pop(SIGN_IN_ERROR, ""),
    }
