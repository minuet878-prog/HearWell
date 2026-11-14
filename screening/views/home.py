from django.http import Http404, HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers

from screening import questionnaires
from screening.care_journey import care_journey
from screening.journey_todos import MANUAL_KEYS, TODO_TEXTS, current_rounds
from screening.main_flow import get_user_state
from screening.models import AidAndSubsidy, TodoTick
from screening.views.answering import continue_notice
from screening.views.common import form_address, health_data_page, safe_next


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
    journey = care_journey(user, timezone.localdate()) if has_records else None
    response = render(
        request,
        "screening/index.html",
        {
            "journey": journey,
            "greeting": greeting(timezone.localtime().hour),
            "continue_notice": continue_notice(user),
            # The 2026-11-14 walkthrough (mockup 6): the save page sends a saved guest result here.
            "saved": request.GET.get("from") == "save",
        },
    )
    # The home page shows this account's own records (ticket #159): never cached.
    add_never_cache_headers(response)
    return response


@form_address
@health_data_page
def journey_todo_tick(request):
    # #481 (spec #478 acceptance 10–18): a 手動待辦 ticked (ticked=1) or unticked (0), on
    # request.user's own account only. An 自動待辦 is judged from the records, so never ticked.
    key, ticked = request.POST.get("todo"), request.POST.get("ticked")
    if key not in TODO_TEXTS:
        raise Http404
    if key not in MANUAL_KEYS or ticked not in ("0", "1"):
        return HttpResponseBadRequest()
    # In its current round (#482): an earlier round's tick stays as it was.
    life_impact = get_user_state(request.user, timezone.localdate()).life_impact
    current = current_rounds(AidAndSubsidy.for_user(request.user), life_impact)[key]
    # journey-todos.js asks for JSON and stays on the page; a plain form goes back to its row.
    wants_json = request.get_preferred_type(["text/html", "application/json"]) == "application/json"
    back_to_row = HttpResponseRedirect(f"{safe_next(request) or reverse('index')}#todo-{key}")
    # A page left open from an earlier round (the cross review on #478): nothing written, the
    # page shown afresh; journey-todos.js reloads it.
    if request.POST.get("round") != str(current):
        if wants_json:
            return JsonResponse({"reload": True}, status=409)
        return back_to_row
    if ticked == "1":
        TodoTick.objects.get_or_create(user=request.user, key=key, round_key=current)
    else:
        TodoTick.objects.filter(user=request.user, key=key, round_key=current).delete()
    if wants_json:
        return JsonResponse({"ticked": ticked == "1"})
    return back_to_row


def family_guide(request):
    # Spec phase8_c1_family_guide.md: the same reviewed content for everyone, no user data.
    # #469: its communication tips and scenarios are on family_talk.
    return render(request, "screening/family_guide.html")


def learn(request):
    # #269 (spec #268): open without logging in, like the guide and the family page it leads to.
    # It reads no records, so it is not a 健康資料頁面.
    return render(request, "screening/learn.html")
