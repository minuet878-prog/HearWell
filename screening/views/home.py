from django.shortcuts import render
from django.utils import timezone
from django.utils.cache import add_never_cache_headers

from screening.care_journey import care_journey
from screening.views.answering import continue_notice


def greeting(hour):
    """#458 D2: by the hour in Taiwan (TIME_ZONE); 晚安 runs past midnight until 5."""
    if 5 <= hour < 12:
        return "早安"
    if 12 <= hour < 18:
        return "午安"
    return "晚安"


def index(request):
    user = request.user
    if not user.is_authenticated:
        # #471 (mockup #458 ⑪): a visitor sees the 空狀態首頁; no one's records, so it may be
        # cached.
        return render(request, "screening/index.html")
    # #459 (ADR 0044): the 照顧旅程 for anyone with a questionnaire or an audiogram, else the
    # 空狀態首頁.
    has_records = user.submissions.defined().exists() or user.audiograms.exists()
    journey = care_journey(user, timezone.localdate()) if has_records else None
    response = render(
        request,
        "screening/index.html",
        {
            "journey": journey,
            "greeting": greeting(timezone.localtime().hour),
            "continue_notice": continue_notice(user),
        },
    )
    # The home page shows this account's own records (ticket #159): never cached.
    add_never_cache_headers(response)
    return response


def family_guide(request):
    # Spec phase8_c1_family_guide.md: the same reviewed content for everyone, no user data.
    # #469: its communication tips and scenarios are on family_talk.
    return render(request, "screening/family_guide.html")


def learn(request):
    # #269 (spec #268): open without logging in, like the guide and the family page it leads to.
    # It reads no records, so it is not a 健康資料頁面.
    return render(request, "screening/learn.html")
