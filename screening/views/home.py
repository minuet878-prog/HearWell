from datetime import date

from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers

from screening import questionnaires
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
        # cached. #499: guest-home.js draws a guest result kept in the browser on top, from each
        # guest questionnaire's topic and result page.
        guest_questionnaires = {
            code: {
                "topic": questionnaires.get(code).topic,
                "url": reverse("guest_result", args=[code]),
            }
            for code in questionnaires.for_guests()
        }
        return render(
            request, "screening/index.html", {"guest_questionnaires": guest_questionnaires}
        )
    # #459 (ADR 0044): the 照顧旅程 for anyone with a questionnaire or an audiogram, else the
    # 空狀態首頁.
    has_records = user.submissions.defined().exists() or user.audiograms.exists()
    # #745 (grill Q13): the stop an answer card here just finished (route_answer's ?done=),
    # stamped only while it is done and step 5 is still the 現在這一步.
    done_now = request.GET.get("done")
    journey = care_journey(user, timezone.localdate(), done_now) if has_records else None
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
    # The address to pass on takes the scheme the page was opened with (https on tingpal.tw).
    context = {"family_url": request.build_absolute_uri(reverse("family_guide"))}
    return render(request, "screening/family_guide.html", context)


# Spec #633 (#640): the day the owner last checked 關於聽伴; on the yearly review list. The
# owner's words were final that day (#635, #642).
ABOUT_CHECKED_ON = date(2026, 11, 16)


def about(request):
    # Spec #633 (#640): open to everyone, like the privacy notice whose highlights it shows; it
    # reads no records.
    return render(request, "screening/about.html", {"checked_on": ABOUT_CHECKED_ON})


def learn(request):
    # #269 (spec #268): open without logging in, like the guide and the family page it leads to.
    # It reads no records, so it is not a 健康資料頁面.
    return render(request, "screening/learn.html")
