from django.shortcuts import render
from django.utils import timezone
from django.utils.cache import add_never_cache_headers

from screening.main_flow import NEW_USER_STATE, get_user_state, home_more
from screening.questionnaires import hhie_s
from screening.questionnaires.definition import NORM
from screening.scoring import classify, max_score
from screening.views.answering import continue_notice
from screening.views.results import ioi_ha_summary, score_bar, score_gauge

# A made-up HHIE-S total for the home page's result preview (spec phase9_ui_refresh_4a_home.md 4.2).
HOME_PREVIEW_SCORE = 18


def index(request):
    preview = classify(HOME_PREVIEW_SCORE, hhie_s.CODE)
    today = timezone.localdate()
    user_state = (
        get_user_state(request.user, today=today)
        if request.user.is_authenticated
        else NEW_USER_STATE
    )
    last = user_state.last_result
    last_ioi_ha = (
        ioi_ha_summary(last.submission)
        if last and last.submission.questionnaire.definition.result == NORM
        else None
    )
    # Welcome back option D (ADR 0026): a life-impact result's gauge and top score.
    last_gauge = last_max_score = None
    if last and last.is_life_impact:
        questionnaire = last.submission.questionnaire
        last_gauge = score_gauge(
            score_bar(
                questionnaire.definition,
                last.submission.total_answer_score,
                last.submission.classified["level"],
            )
        )
        last_max_score = max_score(questionnaire.code)
    # #261: the returning user's 建議下一步 and the other cards; a new user's home is unchanged.
    next_step, more_groups = (None, None) if user_state.is_new else home_more(request.user, today)
    response = render(
        request,
        "screening/index.html",
        {
            "preview_score": HOME_PREVIEW_SCORE,
            "preview_color": preview["color"],
            "preview_text": preview["text"],
            "preview_max_score": max_score(hhie_s.CODE),
            "preview_score_bar": score_bar(hhie_s.DEFINITION, HOME_PREVIEW_SCORE, preview["level"]),
            "user_state": user_state,
            "last_ioi_ha": last_ioi_ha,
            "last_gauge": last_gauge,
            "last_max_score": last_max_score,
            "next_step": next_step,
            "more_groups": more_groups,
            "continue_notice": continue_notice(request.user)
            if request.user.is_authenticated
            else None,
        },
    )
    if request.user.is_authenticated:
        # The home page shows this account's own records (ticket #159): never cached.
        add_never_cache_headers(response)
    return response


def family_guide(request):
    # Spec phase8_c1_family_guide.md: the same reviewed content for everyone, no user data.
    return render(request, "screening/family_guide.html")


def learn(request):
    # #269 (spec #268): open without logging in, like the guide and the family page it leads to.
    # It reads no records, so it is not a 健康資料頁面.
    return render(request, "screening/learn.html")
