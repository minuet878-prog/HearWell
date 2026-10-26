import json
import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import (
    Count,
    F,
    OuterRef,
    Prefetch,
    Subquery,
    prefetch_related_objects,
)
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.http import content_disposition_header, url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from screening import assessment_hospitals, models
from screening.api.views import _find_by_key
from screening.audiogram import compare, recommends_fitting_assessment
from screening.audiogram_thumbnail import thumbnail
from screening.fitting_route import AUDIOGRAM, STOPS, fitting_state, not_applicable_stops
from screening.forms import (
    ROC_OFFSET,
    STOP_QUESTIONS,
    AgeGroupForm,
    AnswerFormSet,
    ConcernForm,
    DeleteAccountForm,
    Form9Form,
    Form25Form,
    HearingAidForm,
    HhiComparisonForm,
    NoticeForm,
    RegisterForm,
    answer_choices,
    offers_not_applicable,
)
from screening.ioi_norm import TOKEN_ERROR, ioi_ha_norm, norm_bases, norm_token
from screening.main_flow import (
    NEW_USER_STATE,
    catalogue_recommendation,
    get_user_state,
    home_more,
    life_impact_questionnaire,
)
from screening.questionnaires import hhia_s, hhie_s
from screening.questionnaires.definition import (
    AVERAGE,
    HEARING_AID,
    LEVEL,
    LIFE_IMPACT,
    LISTENING,
    NORM,
    SUBSCALES,
    TINNITUS,
    UNSURE,
)
from screening.questionnaires.ioi_ha import CODE as IOI_HA
from screening.questionnaires.ioi_ha import ITEM_CHOICES as IOI_HA_CHOICES
from screening.questionnaires.ioi_ha import SCALE_ENDS as IOI_HA_SCALE_ENDS
from screening.questionnaires.ssq12_tw import CODE as SSQ12
from screening.scoring import (
    AIDED_RETAKE_NOTE,
    AIDED_RETAKE_TITLE,
    IOI_HA_BELOW_NORM_NOTES,
    IOI_HA_ITEM_NAMES,
    IOI_HA_NORMS,
    NORM_COMPARISON_TEXT,
    NORM_VERSUS_TEXT,
    RECOMMENDATION_REASONS,
    UNKNOWN,
    classify,
    compare_to_norm,
    get_advice,
    max_score,
    since_last_text,
)

from .models import (
    Answer,
    AudiogramPoint,
    Ear,
    NormGroup,
    Questionnaire,
    Submission,
    User,
    shared_days,
)


def _safe_next(request):
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


# A made-up HHIE-S total for the home page's result preview (spec phase9_ui_refresh_4a_home.md 4.2).
HOME_PREVIEW_SCORE = 18


def _continue_notice(user, questionnaires=None):
    # #326 E7 (#337): the questionnaires this user can open, which the continue notice's script
    # matches against the drafts in this browser (draft.js); the drafts never reach the server.
    # A page that has already read them in list order passes them in.
    if questionnaires is None:
        questionnaires = sorted(Questionnaire.objects.defined(), key=list_order)
    prefetch_related_objects(questionnaires, "questions")
    return {
        "userId": user.pk,
        "questionnaires": [
            {
                "id": questionnaire.pk,
                # As the catalog card reads it (questionnaire_card.html).
                "name": f"{questionnaire.definition.topic}（{questionnaire}）",
                "url": reverse("screening", args=[questionnaire.pk]),
                "questionIds": [question.id for question in questionnaire.questions.all()],
                # As the answer page decides from the API: a draft may hold 「不適用」 when a
                # question offers it.
                "allowNotApplicable": any(
                    offers_not_applicable(question) for question in questionnaire.questions.all()
                ),
            }
            for questionnaire in questionnaires
        ],
    }


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
        _ioi_ha_summary(last.submission)
        if last and last.submission.questionnaire.definition.result == NORM
        else None
    )
    # Welcome back option D (ADR 0026): a life-impact result's gauge and top score.
    last_gauge = last_max_score = None
    if last and last.is_life_impact:
        questionnaire = last.submission.questionnaire
        last_gauge = _score_gauge(
            _score_bar(
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
            "preview_score_bar": _score_bar(
                hhie_s.DEFINITION, HOME_PREVIEW_SCORE, preview["level"]
            ),
            "user_state": user_state,
            "last_ioi_ha": last_ioi_ha,
            "last_gauge": last_gauge,
            "last_max_score": last_max_score,
            "next_step": next_step,
            "more_groups": more_groups,
            "continue_notice": _continue_notice(request.user)
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


def _assessment_context(request):
    # An unknown county is treated like none chosen: the menu again, not an error.
    roster = assessment_hospitals.roster()
    county = request.GET.get("county")
    if county not in roster["counties"]:
        county = None
    return {
        "roster_version": roster["version"],
        "counties": roster["counties"],
        "county": county,
        # #367: 查詢 was pressed, so a missing county is worth saying.
        "searched": "county" in request.GET,
        "hospitals": [h for h in roster["hospitals"] if h["county"] == county],
    }


def _after_fitting_context(request):
    # #220 H8, H9, then SADL (the owner's addition): what the wizard offers someone who
    # wears hearing aids, not every listed questionnaire. Both life-impact questionnaires too,
    # for answering one again worn (F4): the chapter is the same for everyone, so no age.
    questionnaires = list(Questionnaire.objects.defined())
    return {
        "follow_ups": _wearing_follow_ups(questionnaires),
        "life_impact": _life_impact_pair(questionnaires),
    }


def _form_25_context(request):
    # What to answer before the verification visit (F3): the life-impact pair worn, IOI-HA and
    # SADL; SSQ12-TW stays the after-fitting chapter's.
    questionnaires = list(Questionnaire.objects.defined())
    return {
        "follow_ups": [q for q in _wearing_follow_ups(questionnaires) if q.code != SSQ12],
        "life_impact": _life_impact_pair(questionnaires),
    }


def _life_impact_pair(questionnaires):
    # HHIE-S, then HHIA-S, as the catalogue lists them.
    return sorted((q for q in questionnaires if q.definition.life_impact), key=list_order)


@dataclass(frozen=True)
class GuideChapter:
    slug: str
    title: str
    template: str
    extra_context: Callable[[HttpRequest], dict] | None = None


# The hearing-aid guide's chapters in reading order (spec #218).
GUIDE_CHAPTERS = (
    GuideChapter("before-you-go", "去找聽力師之前", "screening/guide/before_you_go.html"),
    GuideChapter(
        "assessment", "身障鑑定與鑑定醫院", "screening/guide/assessment.html", _assessment_context
    ),
    GuideChapter("form-9", "九號表：申請助聽器補助", "screening/guide/form_9.html"),
    GuideChapter("types-and-prices", "助聽器的種類與價格", "screening/guide/types_and_prices.html"),
    # F5: the first weeks wearing them come before the visit 1 to 3 months in.
    GuideChapter(
        "after-fitting",
        "配戴助聽器之後",
        "screening/guide/after_fitting.html",
        _after_fitting_context,
    ),
    GuideChapter(
        "form-25", "二十五號表：使用效益驗證", "screening/guide/form_25.html", _form_25_context
    ),
)


# #336 (spec #326 E5): the stop an answer on the route just made 已完成, ticked once on the
# route it goes back to. Kept in the session, which logging out or in as someone else empties.
DONE_NOW = "screening.route_done_now"


def guide(request):
    # Open without logging in (spec #218): the contents are for family too. ?edit=<slug>
    # opens an answered stop's question again (#293).
    done_now = request.session.pop(DONE_NOW, None)
    return _guide_page(request, edit=request.GET.get("edit"), done_now=done_now)


def _guide_page(request, edit=None, question=None, done_now=None):
    """我的選配指引, the stop being edited showing its question: question, a form sent back
    with its errors, or else one holding the current answer; done_now, the stop to tick."""
    context, state = {"done_now": done_now}, None
    if request.user.is_authenticated:
        today = timezone.localdate()
        state = fitting_state(request.user, today)
        context["has_records"] = state.has_records
        context["latest"] = state.latest  # 問卷結果 without an audiogram asks for one
        # The same life-impact record the home page shows as the last result.
        last = get_user_state(request.user, today=today).last_result
        context["life_impact"] = last.submission if last and last.is_life_impact else None
        # Whether the latest record was answered wearing hearing aids (#220 M16, grill Q4), or
        # a fitting date is filled in (#287).
        context["wearing"] = state.wearing
        if state.audiogram is not None:
            context |= _guide_audiogram(state)
    context["route"] = _route(state, edit, question)
    response = render(request, "screening/guide/index.html", context)
    if request.user.is_authenticated:
        # Shows this account's records (GLOSSARY 健康資料頁面): never cached.
        add_never_cache_headers(response)
    return response


def _percent(ratio):
    # 43.125 and 52.5 and 100, as the worked steps write them.
    return format(ratio.normalize(), "f")


def _guide_audiogram(state):
    # The latest audiogram's 選配 and 身障鑑定門檻 meters (#226, #227, #260, ADR 0017).
    estimate = state.threshold
    ears = [(ear.label, ear.value, estimate[ear.value]) for ear in (Ear.RIGHT, Ear.LEFT)]
    context = {
        "audiogram": state.audiogram,
        "ears": ears,
        "fitting": state.fitting,
        "threshold": estimate,
    }
    if estimate["ratio"] is not None:
        context["worked"] = {
            "ears": [(label, e["pta"], _percent(e["ratio"])) for label, _, e in ears],
            "better": _percent(estimate["better"]),
            "worse": _percent(estimate["worse"]),
        }
    return context


@dataclass(frozen=True)
class RouteStop:
    slug: str
    title: str
    url: str
    marks: tuple[str, ...] = ()  # 已完成, 您在這裡, 資料不足, 估算未達門檻, in that order
    tested_on: object | None = None  # the recorded audiogram's date, on the done first stop
    links: tuple[tuple[str, str], ...] = ()  # (wording, url) under the title
    action: tuple[str, str] | None = None  # the 目前這一站's button
    notes: tuple[str, ...] = ()  # dated (#288) or fixed (#294) wordings under the title
    answer: str = ""  # the user's answer in short (#293)
    questions: tuple = ()  # the stop's question forms shown open (#293, #294)
    editable: bool = False  # 修改 opens questions answered but not shown (#294)
    gap: str = ""  # said on the line on to the next stop (#296)

    @property
    def here(self):
        return "您在這裡" in self.marks

    @property
    def below(self):
        return "估算未達門檻" in self.marks

    @property
    def not_applicable(self):
        return "不適用" in self.marks


# #293: each answer in short, under its stop.
CERTIFICATE_ANSWERS = {
    models.Certificate.YES: "有身障證明",
    models.Certificate.APPLYING: "正在申請鑑定",
    models.Certificate.NO_SUBSIDY: "不申請身障補助",
}
FORM_9_ANSWERS = {True: "九號表完成了", False: "九號表還沒完成"}  # #294
FORM_25_ANSWERS = {True: "二十五號表完成了", False: "二十五號表還沒完成"}  # #296
# Said under the stop for everyone (#294, spec #291 Q12: the notice's date is not asked).
ROUTE_REMINDERS = {"types-and-prices": ("收到核定通知後 6 個月內要買。",)}
# #296 (spec #291 acceptance 14): form 25 comes at least a month after the fitting date.
FORM_25_GAP = "至少 1 個月"


def _answer(slug, aid):
    """The stop's answer in short, "" unanswered (#293, #294)."""
    if aid is None:
        return ""
    if slug == "assessment":
        return CERTIFICATE_ANSWERS.get(aid.certificate, "")
    if slug == "form-9":
        return FORM_9_ANSWERS.get(aid.form_9_done, "")
    if slug == "form-25":
        return FORM_25_ANSWERS.get(aid.form_25_done, "")
    if slug == "after-fitting":
        # #295: 2026/05/01 開始戴、雙耳, with the subsidy and its level where this stop asked.
        if aid.fitted_on is None:
            return ""
        parts = [f"{aid.fitted_on:%Y/%m/%d} 開始戴", aid.get_ear_display()]
        if aid.subsidy:
            parts += [aid.get_subsidy_display(), aid.get_level_display()]
        return "、".join(filter(None, parts))
    # The notice: 雙耳、中階型 once both are answered, else how far it has got.
    if aid.notice_received is None:
        return ""
    if not aid.notice_received:
        return "還沒收到核定公文"
    if aid.approved_ears and aid.level:
        return f"{aid.get_approved_ears_display()}、{aid.get_level_display()}"
    if aid.approved_ears:
        return f"收到核定公文，{aid.get_approved_ears_display()}"
    return "收到核定公文"


def _reached(slug, aid):
    """The stop's questions asked so far, in order; the last is the one to answer next. The
    notice asks 單耳 or 雙耳 once 收到了, then the level (#294)."""
    questions = STOP_QUESTIONS[slug]
    if slug != "notice" or aid is None or not aid.notice_received:
        return questions[:1]
    return questions if aid.approved_ears else questions[:2]


def _route(state, edit=None, question=None):
    # 選配路線 (#258, spec #291): recording an audiogram, then the chapters in reading order
    # and the two waits, which have no chapter and point to form 9's 申請流程 (Q15). Signed
    # out, no stop is marked.
    steps = reverse("guide_chapter", args=["form-9"]) + "#steps-title"
    places = {c.slug: (c.title, reverse("guide_chapter", args=[c.slug])) for c in GUIDE_CHAPTERS}
    places |= {
        AUDIOGRAM: ("記錄聽力圖", reverse("audiogram_new")),
        "notice": ("等待核定公文", steps),
        "payout": ("等待補助發放", steps),
    }
    stops = [(slug, *places[slug]) for slug in STOPS]
    if state is None:
        return [
            RouteStop(
                slug=slug,
                title=title,
                url=url,
                notes=ROUTE_REMINDERS.get(slug, ()),
                gap=FORM_25_GAP if slug == "after-fitting" else "",
            )
            for slug, title, url in stops
        ]
    return [_route_stop(state, *stop, edit, question) for stop in stops]


def _route_stop(state, slug, title, url, edit=None, question=None):
    marks, links, action, tested_on = [], [], None, None
    notes = list(ROUTE_REMINDERS.get(slug, ()))
    form_9 = reverse("guide_chapter", args=["form-9"])
    if slug == AUDIOGRAM and state.insufficient:
        # Never 已完成 (grill Q9): the title and a link go to editing it instead.
        url = reverse("audiogram_edit", args=[state.audiogram.pk])
    if slug in state.done:
        marks.append("已完成")
        if slug == AUDIOGRAM:
            tested_on = state.audiogram.tested_on
    if slug == state.stop:
        marks.append("您在這裡")
    if slug in state.not_applicable:
        marks.append("不適用")
    if slug == AUDIOGRAM and state.insufficient:
        marks.append("資料不足")
        if slug == state.stop:
            action = ("修改這張聽力圖", url)
        else:
            links.append(("修改這張聽力圖", url))
    elif slug == state.stop:
        # The waits and types and prices have no button: the title is the only link.
        action = {
            AUDIOGRAM: ("記錄醫院的聽力圖", url),
            "before-you-go": ("去之前要準備什麼", url),
            "assessment": ("找鑑定醫院", url),
            "form-9": ("看九號表的流程", url),
            "after-fitting": ("記錄配戴的效果", f"{url}#record-title"),
            "form-25": ("看二十五號表要帶什麼", url),
        }.get(slug)
    # Only what ADR 0017 lets the page say: 未達到 is said, 無法確定 is not marked. Once the
    # certificate is answered the estimate is left out (#293).
    if (
        slug == "assessment"
        and slug not in state.done
        and state.threshold
        and state.threshold["status"] == "not_reached"
    ):
        marks.append("估算未達門檻")
        links.append(("看沒有身障證明時", f"{form_9}#without-certificate"))
    if slug == "form-9" and state.reapply_on:
        notes.append(f"{state.reapply_on:%Y/%m/%d} 起可以再申請補助")  # #284 acceptance 17
    if slug == "form-9" and state.wearing:
        links.append(("看再次申請的規定", f"{form_9}#reapply"))
    if slug == "form-25" and state.form_25:
        # #296 (spec #291 acceptance 14): from when before it opens, by when while open, and
        # once it has closed the deadline, never saying it is overdue.
        opens, closes = state.form_25
        if state.today < opens:
            notes.append(f"{opens:%Y/%m/%d} 起可以做")
        elif state.today <= closes:
            notes.append(f"{closes:%Y/%m/%d} 前要做完")
        else:
            notes.append(f"期限是 {closes:%Y/%m/%d}")
    answer, shown, editable = "", (), False
    if slug in STOP_QUESTIONS:
        answer = _answer(slug, state.aid)
        reached = _reached(slug, state.aid)
        # Spec #291 Q14: open at the 目前這一站, the next question only; where the user chose
        # 修改, every one asked so far, and then only that stop. A form sent back with its
        # errors is the edited stop's.
        if slug == edit and question is not None:
            shown = (question,)
        elif slug == edit:
            shown = tuple(form_class(instance=state.aid) for form_class in reached)
        elif slug == state.stop and edit not in STOP_QUESTIONS:
            shown = (reached[-1](instance=state.aid),)
        editable = bool(answer) and len(shown) < len(reached)
    # On the line on to form 25, unless form 25 is 不適用.
    gap = FORM_25_GAP if slug == "after-fitting" and "form-25" not in state.not_applicable else ""
    return RouteStop(
        slug=slug,
        title=title,
        url=url,
        marks=tuple(marks),
        tested_on=tested_on,
        links=tuple(links),
        action=action,
        notes=tuple(notes),
        answer=answer,
        questions=shown,
        editable=editable,
        gap=gap,
    )


def guide_chapter(request, chapter):
    # Like the family guide: the same reviewed content for everyone, no user data shown.
    found = next((c for c in GUIDE_CHAPTERS if c.slug == chapter), None)
    if found is None:
        raise Http404
    if request.user.is_authenticated and request.user.has_consented():
        # 看過 (spec #291 acceptance 4): the first time stays; signed out or before agreeing
        # to the privacy notice that covers it, nothing is kept.
        models.GuideChapterView.objects.get_or_create(user=request.user, chapter=chapter)
    return _chapter_page(request, found)


def _chapter_page(request, chapter, question=None):
    """A chapter, with its stop's question at the foot (#293) while a signed-in, consented
    user has not answered it, and 已記下 with the answer once they have (#294), but neither
    where the stop is 不適用 (#291 review); question is a form sent back with its errors."""
    context = {"chapter": chapter}
    if chapter.extra_context:
        context.update(chapter.extra_context(request))
    user = request.user
    asked = chapter.slug in STOP_QUESTIONS and user.is_authenticated and user.has_consented()
    aid = models.AidAndSubsidy.for_user(user) if asked else None
    if asked and chapter.slug in not_applicable_stops(aid):
        asked, question = False, None
    if question is None and asked:
        context["answered"] = _answer(chapter.slug, aid)
        if not context["answered"]:
            question = STOP_QUESTIONS[chapter.slug][0](instance=aid)
    context["question"] = question
    response = render(request, chapter.template, context)
    if user.is_authenticated:
        # Whether the question shows depends on this account's answers.
        add_never_cache_headers(response)
    return response


@login_required
@require_http_methods(["POST"])
@health_data_page
def route_answer(request):
    # #293 (spec #291 acceptance 28): a stop's answer, request.user's own only; back to the
    # stop on the route, or to the chapter's question.
    stop = request.POST.get("stop")
    questions = STOP_QUESTIONS.get(stop)
    if questions is None:
        return HttpResponseBadRequest()
    # The question whose answer was pressed (#294: the notice has three).
    form_class = next((q for q in questions if q.base_fields.keys() & request.POST.keys()), None)
    form_class = form_class or questions[0]
    aid = models.AidAndSubsidy.for_user(request.user)
    form = form_class(request.POST, instance=aid or models.AidAndSubsidy(user=request.user))
    next_url = _safe_next(request)
    if form.is_valid():
        today = timezone.localdate()
        here = fitting_state(request.user, today).stop
        form.save()
        on_route = urlsplit(next_url).path in ("", reverse("guide"))
        # #336: only the 您在這裡 stop turning 已完成, which a stop turning 不適用 is not.
        if on_route and here == stop and stop in fitting_state(request.user, today).done:
            request.session[DONE_NOW] = stop
        return HttpResponseRedirect(next_url or f"{reverse('guide')}#stop-{stop}")
    if urlsplit(next_url).path == reverse("guide_chapter", args=[stop]):
        chapter = next(c for c in GUIDE_CHAPTERS if c.slug == stop)
        return _chapter_page(request, chapter, form)
    return _guide_page(request, edit=stop, question=form)


class MonitoringTestError(Exception):
    """Raised on purpose so an admin can check that error monitoring reaches Sentry."""


def monitoring_test(request):
    if not request.user.is_superuser:
        raise Http404
    raise MonitoringTestError


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


# Set when an account is made; only then does agreeing on the consent page greet the user (#152).
NEW_ACCOUNT = "screening.new_account"


@require_http_methods(["GET", "POST"])
def register(request):
    next_url = _safe_next(request)
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
            except IntegrityError:
                # Someone else took this name after is_valid(); any other clash is a real error.
                if not User.objects.filter(username=form.cleaned_data["username"]).exists():
                    raise
                form.add_error("username", form.instance.unique_error_message(User, ["username"]))
            else:
                login(request, user)
                request.session[NEW_ACCOUNT] = True
                # New accounts agree to the privacy notice before anything else.
                if next_url:
                    return redirect_to_login(next_url, reverse("consent"))
                return redirect("consent")
    else:
        form = RegisterForm()
    return render(request, "screening/register.html", {"form": form, "next": next_url})


def privacy(request):
    return render(
        request,
        "screening/privacy.html",
        {"version": models.CONSENT_VERSION, "updated_on": models.PRIVACY_UPDATED_ON},
    )


@login_required
@require_http_methods(["GET", "POST"])
def consent(request):
    next_url = _safe_next(request)
    if request.method == "POST" and "decline" in request.POST:
        logout(request)
        messages.info(
            request,
            "沒有同意就不能使用篩檢功能，您的帳號仍在。想使用時，登入後按「我同意，開始篩檢」即可。",
        )
        return redirect("index")
    if request.method == "POST" and "agree" in request.POST and not request.user.has_consented():
        request.user.give_consent()
        # Right after registering, into the wizard: its first screen then says the account is
        # ready (#152). Popped on any agreeing, so agreeing again later says nothing.
        parts = urlsplit(next_url)
        if request.session.pop(NEW_ACCOUNT, False) and parts.path == reverse("questionnaire_list"):
            query = urlencode(
                [*parse_qsl(parts.query, keep_blank_values=True), ("from", "consent")]
            )
            return HttpResponseRedirect(urlunsplit(parts._replace(query=query)))
    if request.user.has_consented():
        return HttpResponseRedirect(next_url or reverse("index"))
    return render(request, "screening/consent.html", {"next": next_url})


def list_order(questionnaire):
    return (questionnaire.definition.list_rank, questionnaire.pk)


# The recommendation wizard's GET parameters: `wizard` from the catalogue's 「幫我選問卷」, the rest
# its answers. Without any, a returning user sees the catalogue.
WIZARD_PARAMS = ("wizard", "concern", "chosen", "age_group")


def _wizard_step(request, step, total, catalog, **context):
    # Steps go forward by GET parameters, so the wizard works without JavaScript (#152).
    return render(
        request,
        "screening/questionnaire.html",
        context
        | {
            "step": step,
            "total": total,
            "continue_notice": _continue_notice(request.user, catalog),
            # Set by the consent page; only its first screen says the account is ready.
            "from_consent": step == 1 and request.GET.get("from") == "consent",
        },
    )


@login_required
@health_data_page
def questionnaire_list(request):
    questionnaires = Questionnaire.objects.defined().annotate(question_count=Count("questions"))
    user = request.user
    state = get_user_state(user, timezone.localdate())
    returning = not state.is_new
    # A returning user sees the catalogue first; the wizard is one link away (ADR 0030).
    if "choose" in request.GET or (
        returning and not any(name in request.GET for name in WIZARD_PARAMS)
    ):
        # Each card's 「上次」 date in the same query, not one query per card.
        latest = (
            Submission.objects.filter(user=user, questionnaire=OuterRef("pk"))
            .order_by("-created_at")
            .values("created_at")[:1]
        )
        questionnaires = sorted(
            questionnaires.annotate(last_answered_at=Subquery(latest)), key=list_order
        )
        return render(
            request,
            "screening/questionnaire.html",
            {
                "questionnaires": questionnaires,
                "continue_notice": _continue_notice(user, questionnaires),
                # A new user has no record to recommend by.
                "recommendation": catalogue_recommendation(user, questionnaires, state)
                if returning
                else None,
            },
        )
    questionnaires = sorted(questionnaires, key=list_order)
    wizard_url = reverse("questionnaire_list")
    # None while the age is still needed: then step 1 says 共 3 步, as a life-impact result asks it.
    life_impact = life_impact_questionnaire(user, questionnaires, state, None)
    concern_form = ConcernForm(
        request.GET if "concern" in request.GET else None,
        # Back from a later step: the answer chosen there is still chosen.
        initial={"concern": request.GET.get("chosen")},
    )
    if not concern_form.is_valid():
        return _wizard_step(
            request,
            1,
            3 if life_impact is None else 2,
            questionnaires,
            field=concern_form["concern"],
            # A returning user came from the catalogue's 「幫我選問卷」.
            back_url=wizard_url if returning else reverse("index"),
        )
    concern = concern_form.cleaned_data["concern"]
    back_url = f"{wizard_url}?{urlencode({'chosen': concern})}"
    has_norm_basis = concern == HEARING_AID and norm_bases(user).exists()
    step = 2
    if concern in (LIFE_IMPACT, UNSURE, HEARING_AID) and life_impact is None:
        age_form = AgeGroupForm(request.GET if "age_group" in request.GET else None)
        if not age_form.is_valid():
            return _wizard_step(
                request,
                2,
                3,
                questionnaires,
                field=age_form["age_group"],
                concern=concern,
                back_url=back_url,
            )
        life_impact = life_impact_questionnaire(
            user, questionnaires, state, age_form.cleaned_data["age_group"]
        )
        step = 3
        back_url = f"{wizard_url}?{urlencode({'concern': concern})}"
    # Asks the definitions, not the codes, per CODING_STANDARDS.md rule 9; IOI-HA alone is
    # named, as the hearing-aid answer's recommendation once there is a norm basis.
    hearing_aid = [q for q in questionnaires if q.definition.concern == HEARING_AID]
    also, retake = [], None
    if concern in (TINNITUS, LISTENING):
        recommended = next(q for q in questionnaires if q.definition.concern == concern)
        reason = concern
    elif concern != HEARING_AID:
        recommended, reason = life_impact, concern
    elif has_norm_basis:
        recommended, reason = next(q for q in hearing_aid if q.code == IOI_HA), "has_norm_basis"
        # Answering the life-impact questionnaire again worn compares with the unaided record
        # (F1); it comes first.
        title = AIDED_RETAKE_TITLE.format(topic=life_impact.definition.topic, name=life_impact)
        retake = {"questionnaire": life_impact, "title": title, "note": AIDED_RETAKE_NOTE}
        also = [q for q in hearing_aid if q != recommended]
    else:
        # IOI-HA compares with the norm group of an unaided record, so that record comes first.
        recommended, reason = life_impact, "needs_norm_basis"
        also = hearing_aid
    start_url = reverse("screening", args=[recommended.pk])
    if reason == "needs_norm_basis":
        # The answer page starts on "沒戴", which the user may still change (#154).
        start_url += "?preselect=unaided"
    return _wizard_step(
        request,
        step,
        step,
        questionnaires,
        recommended=recommended,
        reason=reason,
        why=RECOMMENDATION_REASONS[reason],
        start_url=start_url,
        also=also,
        retake=retake,
        questionnaires=questionnaires,
        back_url=back_url,
    )


def _wearing_follow_ups(questionnaires):
    # The follow-ups for someone who wears hearing aids: IOI-HA, then SSQ12-TW and a
    # satisfaction-type questionnaire (SADL) when it is visible (#174). One missing from the
    # database is left out. Asks the definition's result, not SADL's code, per
    # CODING_STANDARDS.md rule 9.
    by_code = {questionnaire.code: questionnaire for questionnaire in questionnaires}
    satisfaction = next((q for q in questionnaires if q.definition.result == SUBSCALES), None)
    return [q for q in (by_code.get(IOI_HA), by_code.get(SSQ12), satisfaction) if q]


@login_required
@require_http_methods(["GET", "POST"])
@health_data_page
def screening(request, questionnaire_id):
    if request.method == "GET":
        questionnaire = get_object_or_404(Questionnaire.objects.defined(), pk=questionnaire_id)
        # IOI-HA is answered wearing hearing aids by definition, so it does not ask.
        is_ioi_ha = questionnaire.code == IOI_HA
        always_aided = questionnaire.definition.always_aided
        norm = ioi_ha_norm(request.user) if is_ioi_ha else None
        # Set by the wizard when catching up an unaided record (#154): only where the hearing aid
        # question starts, so the POST still takes whatever the user chose.
        preselect_unaided = (
            not is_ioi_ha and not always_aided and request.GET.get("preselect") == "unaided"
        )
        hearing_aid_initial = {"wearing_hearing_aid": False} if preselect_unaided else None
        questions = questionnaire.questions.all()
        formset = AnswerFormSet(
            questions=questions, initial=[{"question_id": question.id} for question in questions]
        )
        question_form = list(zip(questions, formset, strict=True))
        return render(
            request,
            "screening/screening.html",
            {
                "question_form": question_form,
                "question_count": len(questions),
                "questionnaire": questionnaire,
                "formset": formset,
                "hearing_aid_form": None
                if is_ioi_ha or always_aided
                else HearingAidForm(
                    initial=hearing_aid_initial, message=questionnaire.definition.wearing_error
                ),
                "preselect_unaided": preselect_unaided,
                "is_ioi_ha": is_ioi_ha,
                "ioi_norm": norm,
                "norm_token": norm_token(request.user, norm) if norm else None,
                # Every questionnaire, IOI-HA too since #245; always-aided ones and IOI-HA skip
                # the wearing step there.
                "use_react": True,
                "always_aided": always_aided,
                # New for every opened page: answering again later is a new submission.
                "idempotency_key": uuid.uuid4(),
            },
        )
    if request.method == "POST":
        questionnaire = get_object_or_404(Questionnaire.objects.defined(), pk=questionnaire_id)
        is_ioi_ha = questionnaire.code == IOI_HA
        always_aided = questionnaire.definition.always_aided
        questions = questionnaire.questions.all()
        if not questions:
            return redirect("questionnaire_list")
        # Missing or malformed (tampered or very old page): saved as before, just not guarded.
        try:
            key = uuid.UUID(request.POST.get("idempotency_key", ""))
        except ValueError:
            key = None
        # This page was already sent (double click, or back and resend with other answers):
        # show that first result instead of saving again.
        existing = key and _find_by_key(request.user, key)
        if existing:
            return _already_sent(request, existing)
        try:
            norm = (
                ioi_ha_norm(request.user, request.POST.get("norm_token") or None)
                if is_ioi_ha
                else None
            )
        except signing.BadSignature:
            return HttpResponseBadRequest(TOKEN_ERROR)
        formset = AnswerFormSet(questions=questions, data=request.POST)
        hearing_aid_form = (
            None
            if is_ioi_ha or always_aided
            else HearingAidForm(data=request.POST, message=questionnaire.definition.wearing_error)
        )
        # question_form 只有在驗證沒過的時候才會被用到[拿去重新顯示頁面]，而那時的資料可能是壞的
        # ，所以不能用 strict=True
        question_form = list(zip(questions, formset, strict=False))
        if formset.is_valid() and (hearing_aid_form is None or hearing_aid_form.is_valid()):
            if is_ioi_ha:
                extra = norm
            elif always_aided:
                extra = {"wearing_hearing_aid": True}
            else:
                extra = {
                    "wearing_hearing_aid": hearing_aid_form.cleaned_data["wearing_hearing_aid"]
                }
            try:
                submission = formset.save(request.user, questionnaire, idempotency_key=key, **extra)
            except IntegrityError:
                # Two clicks arrived together and the other one saved first; save() is atomic,
                # so nothing of this one is left behind. Any other clash is a real error.
                existing = key and _find_by_key(request.user, key)
                if not existing:
                    raise
                return _already_sent(request, existing)
            return redirect("result", submission_id=submission.id)
        else:
            # Only questions shown on the page, so the list matches the marked ones. A form
            # missing its question_id was tampered with: it gets the generic error instead.
            # Each entry links to the question's fieldset id in screening.html.
            unanswered = [
                (f"第 {number} 題", f"question-{number}")
                for number, (_, form) in enumerate(question_form, start=1)
                if form.has_error("score", code="required") and not form.has_error("question_id")
            ]
            if hearing_aid_form is not None and hearing_aid_form.has_error(
                "wearing_hearing_aid", code="required"
            ):
                unanswered.insert(0, ("是否戴助聽器", "question-hearing-aid"))
            if unanswered:
                message = f"還有 {len(unanswered)} 題沒有回答，請看標示紅字的題目。"
            else:
                message = formset.non_form_errors()
            return render(
                request,
                "screening/screening.html",
                {
                    "message": message,
                    "unanswered": unanswered,
                    "question_form": question_form,
                    "question_count": len(questions),
                    "questionnaire": questionnaire,
                    "formset": formset,
                    "hearing_aid_form": hearing_aid_form,
                    "is_ioi_ha": is_ioi_ha,
                    "ioi_norm": norm,
                    "norm_token": norm_token(request.user, norm) if norm else None,
                    # Stay on this form: React would start over and drop the errors and answers.
                    "use_react": False,
                    # Nothing was saved, so the fixed answers go out under the same number.
                    "idempotency_key": key,
                },
            )


def _already_sent(request, submission):
    messages.info(
        request,
        "這份作答剛才已經送出，以下是那次的結果；要重新作答，請從「開始篩檢」進入。",
    )
    return redirect("result", submission_id=submission.id)


@login_required
@require_http_methods(["GET", "POST"])
@health_data_page
def hhi_comparison(request, questionnaire_id):
    questionnaire = get_object_or_404(Questionnaire.objects.defined(), pk=questionnaire_id)
    if questionnaire.definition.comparison is None:
        raise Http404
    saved = (
        request.user.report_comparisons.filter(questionnaire=questionnaire)
        .select_related("unaided", "aided")
        .first()
    )
    if request.method == "POST" and request.POST.get("action") == "remove":
        if saved:
            saved.delete()
        messages.success(request, "已從報告移除這一組，原始作答保持不變。")
        return redirect("hhi_comparison", questionnaire_id=questionnaire.pk)
    data = (
        request.POST
        if request.method == "POST"
        else (
            request.GET
            if any(key in request.GET for key in ("unaided", "aided", "action"))
            else None
        )
    )
    form = HhiComparisonForm(
        data=data,
        user=request.user,
        questionnaire=questionnaire,
        initial={"unaided": saved.unaided_id, "aided": saved.aided_id} if saved else None,
    )
    preview = saved if data is None else None
    if form.is_bound and form.is_valid():
        preview = models.ReportComparison(
            user=request.user, questionnaire=questionnaire, **form.cleaned_data
        )
        if request.method == "POST":
            request.user.report_comparisons.update_or_create(
                questionnaire=questionnaire, defaults=form.cleaned_data
            )
            messages.success(request, "已放進聽力報告，新增紀錄不會自動換掉這一組。")
            return redirect("hhi_comparison", questionnaire_id=questionnaire.pk)
    return render(
        request,
        "screening/hhi_comparison.html",
        {
            "questionnaire": questionnaire,
            "form": form,
            "saved": saved,
            "preview": preview,
            # The pair on screen is the one in the report: no button to save it again (#190).
            "preview_is_saved": saved is not None
            and preview is not None
            and (preview.unaided_id, preview.aided_id) == (saved.unaided_id, saved.aided_id),
        },
        status=400 if request.method == "POST" else 200,
    )


def _item_scores(submission):
    return {
        answer.question.question_number: answer.score
        for answer in submission.answers.select_related("question")
    }


def _ioi_ha_chart(records):
    # records: this user's IOI-HA, newest first. Grid row 1 is score 5, row 5 is score 1.
    latest = records[0]
    grouped = latest.norm_group != NormGroup.UNGROUPED
    previous = records[1] if grouped and len(records) > 1 else None
    if previous is not None and previous.norm_group != latest.norm_group:
        previous = None  # another group's band would mislead
    latest_scores = _item_scores(latest)
    previous_scores = _item_scores(previous) if previous else {}
    columns = []
    for number, name in IOI_HA_ITEM_NAMES.items():
        score = latest_scores[number]
        column = {"name": name, "latest_row": 6 - score}
        text = f"{name}：最近一次 {score} 分"
        if previous:
            column["previous_row"] = 6 - previous_scores[number]
            text += f"，上一次 {previous_scores[number]} 分"
        if grouped:
            lower, upper = IOI_HA_NORMS[latest.norm_group][number]
            column["band_rows"] = f"{6 - upper} / {7 - lower}"
            comparison = compare_to_norm(latest.norm_group, number, score)
            text += f"，常模 {lower} 到 {upper} 分，{NORM_COMPARISON_TEXT[comparison]}"
        column["text"] = text
        columns.append(column)
    return {"latest": latest, "previous": previous, "grouped": grouped, "columns": columns}


TREND_STATUS_TEXT = {False: "沒戴助聽器", True: "有戴助聽器", None: "助聽器未記錄"}
# 「和上一次比」's extra line when the two records were worn differently (ticket #214). A
# life-impact tab never shows one: it compares records worn the same way.
WEARING_CHANGE_TEXT = {
    (False, True): "上次沒戴、這次有戴助聽器。",
    (True, False): "上次有戴、這次沒戴助聽器。",
}
# Legend order, the template's shape for each status (spec 4b) and its name.
TREND_LEGEND = (
    (False, "unaided", "沒戴助聽器"),
    (True, "aided", "有戴助聽器"),
    (None, "unrecorded", "未記錄"),
)


def _trend_chart(records, since_last):
    # records: one tab's records (HHIE-S, THI), newest first; since_last: the page's
    # 「和上一次比」 or None.
    # React draws only the chart itself, so the text around it is on the page from the start
    # and nothing below moves when it arrives. The wording is fixed by spec
    # phase9_ui_refresh_2_data.md 4.2.
    latest = records[0]
    definition = latest.questionnaire.definition
    wearing = latest.wearing_hearing_aid
    status = TREND_STATUS_TEXT[wearing]
    if since_last is not None:
        change = None  # 「和上一次比」 above the chart says it (decision 2026-10-22, #162)
    elif len(records) == 1:
        # THI is not a screening (GLOSSARY: 篩檢問卷 is not every questionnaire).
        change = f"再做一次{'篩檢' if definition.life_impact else ''}，就能看到分數的變化。"
    elif wearing is None:
        change = "這筆沒有記錄助聽器，不和其他紀錄比較。"
    else:
        change = f"這是第一筆{status}的紀錄。"
    statuses = {r.wearing_hearing_aid for r in records}
    return {
        "latest": latest,
        "status": status,
        "change": change,
        "legend": [
            {"shape": shape, "text": text}
            for value, shape, text in TREND_LEGEND
            if value in statuses
        ],
        # Top band first, as stacked in the chart (phase9_ui_refresh_3_structure.md 4.5).
        "levels": [
            {
                "code": level,
                "text": text,
                "color": definition.color(level),
                "shade": definition.shade(level),
            }
            for _, text, level in reversed(definition.thresholds)
        ],
    }


def _shows_wearing_comparison(user, questionnaire):
    # The 「比較戴與不戴助聽器」 entry on 我的紀錄 and the result pages (ticket #186): only once
    # this questionnaire has comparable records both with and without a hearing aid.
    comparison = questionnaire.definition.comparison
    if comparison is None:
        return False
    comparable = comparison.records(user.submissions.filter(questionnaire=questionnaire))
    return (
        comparable.filter(wearing_hearing_aid=True).exists()
        and comparable.filter(wearing_hearing_aid=False).exists()
    )


@login_required
@health_data_page
def my_hearing(request):
    # SADL's satisfaction score reads submission.answers directly (models/submissions.py), so it
    # needs its own prefetch: with_scores() only annotates the LEVEL/AVERAGE aggregates.
    answers = Answer.objects.select_related("question")
    submissions = list(
        request.user.submissions.defined()
        .select_related("questionnaire")
        .prefetch_related(Prefetch("answers", queryset=answers))
        .with_scores()
    )
    if not submissions:
        # Ticket #270 (ADR 0019): opened plainly with only audiograms, show those instead of an
        # empty page; the switch's 問卷 link (view=questionnaires) always stays here.
        if request.GET.get("view") != "questionnaires" and request.user.audiograms.exists():
            return redirect("audiogram_list")
        return render(request, "screening/my_hearing.html", {"submissions": []})
    # One tab per questionnaire this user has answered, in questionnaire order (HHIE-S first).
    questionnaires = sorted({s.questionnaire for s in submissions}, key=lambda q: q.id)
    # Default: the newest record's questionnaire; an unknown or empty choice falls back to it.
    current = next(
        (q for q in questionnaires if q.code == request.GET.get("questionnaire")),
        submissions[0].questionnaire,
    )
    records = [s for s in submissions if s.questionnaire_id == current.id]
    # Records sharing a Taipei date with another of this tab show their time too
    # (spec phase9_ui_refresh_2_data.md 4.3).
    days = shared_days(s.created_at for s in records)
    same_day = {s.id for s in records if timezone.localdate(s.created_at) in days}
    # Ticket #162: the same retest reminder as the home page (ADR 0010).
    user_state = get_user_state(request.user, today=timezone.localdate())
    # Ticket #162: a life-impact tab compares its newest record with the one before it worn
    # the same way, as the trend chart does (decision 2026-10-22). Ticket #214: another graded
    # tab (THI) compares it with the record just before, whatever was worn (ADR 0016).
    since_last = None
    if current.definition.result == LEVEL:
        latest = records[0]
        if current.definition.life_impact:
            previous = latest.previous_same_wearing(records[1:])
        else:
            previous = records[1] if len(records) > 1 else None
        if previous is not None:
            since_last = {
                "latest": latest,
                "previous": previous,
                "text": since_last_text(latest.total_answer_score - previous.total_answer_score),
                "wearing_change": WEARING_CHANGE_TEXT.get(
                    (previous.wearing_hearing_aid, latest.wearing_hearing_aid)
                ),
            }
    return render(
        request,
        "screening/my_hearing.html",
        {
            "submissions": records,
            "same_day": same_day,
            "questionnaires": questionnaires,
            "current": current,
            "user_state": user_state,
            "since_last": since_last,
            "show_comparison": _shows_wearing_comparison(request.user, current),
            "saved_comparison": request.user.report_comparisons.filter(questionnaire=current)
            .select_related("unaided", "aided")
            .first(),
            "ioi_ha_chart": _ioi_ha_chart(records) if current.code == IOI_HA else None,
            "trend_chart": (
                _trend_chart(records, since_last) if current.definition.trend_chart else None
            ),
        },
    )


def _taipei(moment):
    return timezone.localtime(moment).isoformat()


def _has_subscores(answers):
    # Only items marked emotional or social make subscores; THI has none (spec #208 Q5). Reads
    # the answers already loaded with their questions, no query of its own.
    return any(answer.question.category != models.Category.NONE for answer in answers)


def _export_submission(submission):
    # Only graded questionnaires have a total, subscales and level (same as their result
    # pages); the others export null, not 0.
    result = submission.questionnaire.definition.result
    not_scored = result != LEVEL
    has_subscores = not not_scored and _has_subscores(submission.answers.all())
    data = {
        "questionnaire": submission.questionnaire.questionnaire_name,
        "created_at": _taipei(submission.created_at),
        "wearing_hearing_aid": submission.get_wearing_hearing_aid_display(),
        "answers": [
            {
                "number": answer.question.question_number,
                "question": answer.question.question_text,
                "score": answer.score,
                # null rather than a 500: one odd old answer must not block the whole export.
                "choice": dict(answer_choices(answer.question)).get(answer.score),
            }
            for answer in submission.answers.all()
        ],
        "total_score": None if not_scored else submission.total_answer_score,
        "emotional_score": submission.emotional_score if has_subscores else None,
        "social_score": submission.social_score if has_subscores else None,
        "level": None if not_scored else submission.classified["text"],
        "norm_group": submission.get_norm_group_display() or None,
    }

    if result == AVERAGE:
        data["average_score"] = (
            str(submission.ssq_average) if submission.ssq_average is not None else None
        )
        data["average_unavailable_reason"] = submission.ssq_unavailable_reason
        _mark_not_applicable_answers(data)
    if result == SUBSCALES:
        satisfaction = submission.satisfaction
        data["overall_score"] = str(satisfaction["overall"])
        data["subscale_scores"] = {s["name"]: str(s["score"]) for s in satisfaction["subscales"]}
        _mark_not_applicable_answers(data)
    return data


def _mark_not_applicable_answers(data):
    for answer in data["answers"]:
        if answer["score"] is None:
            answer["choice"] = "不適用"


def _offered(form_class, name, value):
    """The wording the question offers for the answer value; None unanswered."""
    return dict(form_class.base_fields[name].choices).get(value)


@login_required
@require_http_methods(["GET"])
@health_data_page
def download_my_data(request):
    # Spec phase7_data_export.md: everything of request.user, nothing else; no ids in the URL.
    user = request.user
    answers = Answer.objects.select_related("question__questionnaire").order_by(
        "question__question_number"
    )
    submissions = (
        user.submissions.defined()
        .select_related("questionnaire")
        .prefetch_related(Prefetch("answers", queryset=answers))
        .with_scores()
    )
    points = AudiogramPoint.objects.order_by("ear", "conduction", "frequency")
    audiograms = user.audiograms.prefetch_related(Prefetch("points", queryset=points))
    aid = models.AidAndSubsidy.for_user(user)
    chapter_titles = {chapter.slug: chapter.title for chapter in GUIDE_CHAPTERS}
    data = {
        "account": {
            "username": user.username,
            "email": user.email,
            "birth_year": user.birth_year,
            "date_joined": _taipei(user.date_joined),
        },
        "consents": [
            {"version": consent.version, "agreed_at": _taipei(consent.agreed_at)}
            for consent in user.consents.order_by("agreed_at", "id")
        ],
        "submissions": [_export_submission(submission) for submission in submissions],
        "report_comparisons": [
            {
                "questionnaire": comparison.questionnaire.questionnaire_name,
                "unaided": _export_submission(comparison.unaided),
                "aided": _export_submission(comparison.aided),
            }
            for comparison in user.report_comparisons.filter(
                questionnaire__in=Questionnaire.objects.defined()
            )
            .select_related("questionnaire")
            .prefetch_related(
                Prefetch("unaided", queryset=submissions),
                Prefetch("aided", queryset=submissions),
            )
            .order_by("questionnaire_id")
        ],
        "audiograms": [
            {
                "tested_on": audiogram.tested_on.isoformat(),
                "created_at": _taipei(audiogram.created_at),
                "points": [
                    {
                        "ear": point.get_ear_display(),
                        "conduction": point.get_conduction_display(),
                        "frequency": point.frequency,
                        "db": point.db,
                        "no_response": point.no_response,
                        "masked": point.masked,
                    }
                    for point in audiogram.points.all()
                ],
            }
            for audiogram in audiograms
        ],
        # The link code itself is left out: it would let anyone holding the file open it.
        "report_shares": [
            {
                "created_at": _taipei(share.created_at),
                "expires_at": _taipei(share.expires_at),
                "cancelled": share.revoked_at is not None,
                "open_count": share.open_count,
                "last_opened_at": share.last_opened_at and _taipei(share.last_opened_at),
            }
            for share in user.report_shares.all()
        ],
        # Spec #284, #291: what the user answered, unanswered as null, the certificate included.
        "aid_and_subsidy": {
            "certificate": (aid and aid.get_certificate_display()) or None,
            # #294: worded as the questions offer them.
            "form_9_done": _offered(Form9Form, "form_9_done", aid and aid.form_9_done),
            "notice_received": _offered(NoticeForm, "notice_received", aid and aid.notice_received),
            "approved_ears": (aid and aid.get_approved_ears_display()) or None,
            "fitted_on": aid.fitted_on.isoformat() if aid and aid.fitted_on else None,
            "ear": (aid and aid.get_ear_display()) or None,
            "subsidy": (aid and aid.get_subsidy_display()) or None,
            "level": (aid and aid.get_level_display()) or None,
            "form_25_done": _offered(Form25Form, "form_25_done", aid and aid.form_25_done),
            # Spec #291 acceptance 23: the chapters read, by name, first read first.
            "viewed_chapters": [
                {
                    # A chapter since taken out of the guide keeps its slug.
                    "chapter": chapter_titles.get(view.chapter, view.chapter),
                    "first_viewed_at": _taipei(view.first_viewed_at),
                }
                for view in user.guide_views.order_by("first_viewed_at")
            ],
        },
    }
    filename = f"hearwell-我的資料-{timezone.localdate().isoformat()}.json"
    return HttpResponse(
        json.dumps(data, ensure_ascii=False, indent=2),
        content_type="application/json",
        headers={"Content-Disposition": content_disposition_header(True, filename)},
    )


@login_required
@require_http_methods(["GET"])
@health_data_page
def account_settings(request):
    # Spec phase9_ui_refresh_3_structure.md 4.1: request.user's own account, to look at only.
    user = request.user
    consent = (
        user.consents.filter(version__gte=models.CONSENT_VERSION).order_by("-agreed_at").first()
    )
    # #195: the share status reads only request.user's own live link.
    share = user.report_shares.active().first()
    roc_birth_year = None if user.birth_year is None else user.birth_year - ROC_OFFSET
    return render(
        request,
        "screening/account.html",
        {"consent": consent, "share": share, "roc_birth_year": roc_birth_year},
    )


@login_required
@require_http_methods(["GET", "POST"])
def delete_account(request):
    user = request.user
    # Staff could lock everyone out of admin; they remove their staff rights first.
    if user.is_staff or user.is_superuser:
        status = 403 if request.method == "POST" else 200
        return render(request, "screening/delete_account.html", {"is_admin": True}, status=status)
    form = DeleteAccountForm(request.POST if request.method == "POST" else None, user=user)
    if form.is_valid():
        user.delete_with_data()
        logout(request)
        messages.success(request, "您的帳號和資料已經刪除。")
        return redirect("index")
    return render(
        request,
        "screening/delete_account.html",
        {
            "form": form,
            "submission_count": user.submissions.count(),
            "audiogram_count": user.audiograms.count(),
        },
    )


REPORT_RECENT = 5  # history rows per questionnaire on the health report


def _report_context(user):
    # One builder for the owner's report and the family's copy (rule 10: same scoring path).
    # Answers are prefetched so SADL's per-record satisfaction (#172) reads them once, not once
    # per record shown.
    answers = Answer.objects.select_related("question").order_by("question__question_number")
    submissions = list(
        user.submissions.defined()
        .select_related("questionnaire")
        .prefetch_related(Prefetch("answers", queryset=answers))
        .with_scores()
    )
    by_questionnaire = {}
    for submission in submissions:  # newest first
        if submission.questionnaire.definition.result == LEVEL:
            by_questionnaire.setdefault(submission.questionnaire, []).append(submission)
    comparisons = list(
        user.report_comparisons.filter(questionnaire__in=Questionnaire.objects.defined())
        .select_related("questionnaire", "unaided__questionnaire", "aided__questionnaire")
        .prefetch_related("unaided__answers__question", "aided__answers__question")
        .order_by("questionnaire_id")
    )
    # #90: each saved comparison is shown with its own questionnaire's part.
    comparison_for = {comparison.questionnaire_id: comparison for comparison in comparisons}
    sections = [
        {
            "questionnaire": questionnaire,
            "latest": records[0],
            "count": len(records),
            "recent": records[:REPORT_RECENT],
            "max_score": max_score(questionnaire.code),
            "advice": get_advice(records[0].classified["level"], questionnaire.code),
            "comparison": comparison_for.get(questionnaire.id),
        }
        for questionnaire, records in sorted(by_questionnaire.items(), key=lambda kv: kv[0].id)
    ]
    ssq_records = [s for s in submissions if s.questionnaire.definition.result == AVERAGE]
    sadl_records = [s for s in submissions if s.questionnaire.definition.result == SUBSCALES]
    context = {
        "comparisons": comparisons,
        "ssq_comparison": next(
            (c for c in comparisons if c.questionnaire.definition.result == AVERAGE), None
        ),
        "ssq_latest": ssq_records[0] if ssq_records else None,
        "ssq_recent": ssq_records[:REPORT_RECENT],
        "sadl_latest": sadl_records[0] if sadl_records else None,
        "sadl_recent": sadl_records[:REPORT_RECENT],
        "sections": [s for s in sections if s["questionnaire"].definition.life_impact],
        # Graded but not life impact (ADR 0016): THI, in its own part with no subscores,
        # answers or comparison (spec #208 Q5, Q9).
        "tinnitus_sections": [s for s in sections if not s["questionnaire"].definition.life_impact],
        "recent_limit": REPORT_RECENT,
        "today": timezone.localdate(),
    }
    ioi_ha = next((s for s in submissions if s.questionnaire.definition.result == NORM), None)
    if ioi_ha:
        context["ioi_ha"] = _ioi_ha_summary(ioi_ha)
    audiogram = user.audiograms.prefetch_related("points").first()
    if audiogram:
        context.update(_audiogram_context(audiogram))
    context["has_records"] = bool(submissions or audiogram)
    return context


@login_required
@health_data_page
def health_report(request):
    # Spec phase8_c3_report.md: only results the site already shows, laid out for printing.
    context = _report_context(request.user)
    # #287: the owner's report only; the family's copy shares the template but not this.
    aid = models.AidAndSubsidy.for_user(request.user)
    context["aid_report_text"] = aid.report_text if aid else ""
    return render(request, "screening/health_report.html", context)


@login_required
@health_data_page
def share_report(request):
    # #193: what the family will see, then one press makes the link; only the user's own link.
    user = request.user
    context = {
        "has_records": user.submissions.exists() or user.audiograms.exists(),
        "share": user.report_shares.active().first(),
    }
    return render(request, "screening/share_report.html", context)


@login_required
@require_http_methods(["POST"])
def report_share_create(request):
    # Spec phase8_c1_family_share.md: only after the explicit confirm, one live link at most.
    user = request.user
    has_records = user.submissions.exists() or user.audiograms.exists()
    if "confirm" in request.POST and has_records:
        with transaction.atomic():
            # Lock the user's row so two quick submits cannot both find "no live link".
            User.objects.select_for_update().get(pk=user.pk)
            if not user.report_shares.active().exists():
                models.ReportShare.objects.create(user=user)
    return redirect("share_report")


@login_required
@require_http_methods(["POST"])
def report_share_cancel(request, share_id):
    share = get_object_or_404(models.ReportShare.objects.active(), pk=share_id, user=request.user)
    share.revoked_at = timezone.now()
    share.save(update_fields=["revoked_at"])
    return redirect("share_report")


def _family_page(request, template, context=None, status=200):
    # Family pages hold health data without a login: never cached, indexed, or referred on.
    response = render(request, template, context, status=status)
    add_never_cache_headers(response)
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _live_share(request, token):
    # Expired, cancelled, deleted with the account, or never made: the same answer for all.
    share = models.ReportShare.objects.active().select_related("user").filter(token=token).first()
    if share is None:
        return None, _family_page(request, "screening/share_invalid.html", status=404)
    return share, None


@require_http_methods(["GET"])
def shared_cover(request, token):
    # What a link preview (e.g. LINE) fetches: no health data, and not counted as an open.
    share, invalid = _live_share(request, token)
    return invalid or _family_page(request, "screening/shared_cover.html", {"share": share})


@require_http_methods(["GET"])
def shared_report(request, token):
    share, invalid = _live_share(request, token)
    if invalid:
        return invalid
    models.ReportShare.objects.filter(pk=share.pk).update(
        open_count=F("open_count") + 1, last_opened_at=timezone.now()
    )
    context = _report_context(share.user)
    # #194 "先看重點": the latest life-impact record, picked as the home page's last result is.
    last = get_user_state(share.user, today=timezone.localdate()).last_result
    context.update(
        {
            "share": share,
            "shared": True,
            "owner": share.user,
            "life_impact": last.submission if last and last.is_life_impact else None,
        }
    )
    return _family_page(request, "screening/shared_report.html", context)


def _score_bar(definition, score, level):
    # Ticket #158: a bar segmented by the thresholds, with a marker at this score's position.
    # "無法判讀" (no thresholds, or an out-of-range score) draws no bar.
    thresholds = definition.thresholds
    if level == "unknown" or not thresholds:
        return None
    ceiling = thresholds[-1][0]
    segments = []
    start = 0
    for upper, text, segment_level in thresholds:
        segments.append(
            {
                "level": segment_level,
                "color": definition.color(segment_level),
                "shade": definition.shade(segment_level),
                "text": text,
                "width": (upper - start) / ceiling * 100,
                "current": segment_level == level,
            }
        )
        start = upper
    position = max(0, min(100, score / ceiling * 100))
    return {
        "segments": segments,
        "position": position,
        "ceiling": ceiling,
        "current_text": next(segment["text"] for segment in segments if segment["current"]),
    }


# The welcome-back gauge (option D, ADR 0026): a half circle centred at (110, 105) in its 220 x 130
# drawing, with a small gap between the levels' arcs.
# score_gauge.html and site.css use the same centre for the needle.
GAUGE_CENTRE = (110, 105)
GAUGE_RADIUS = 80
GAUGE_GAP = 0.5  # percent of the half circle on each side of a join
HALF_CIRCLE_DEGREES = 180


def _gauge_point(percent):
    angle = math.pi * (1 - percent / 100)
    x, y = GAUGE_CENTRE
    return f"{x + GAUGE_RADIUS * math.cos(angle):.2f} {y - GAUGE_RADIUS * math.sin(angle):.2f}"


def _score_gauge(bar):
    # The score bar's segments as arcs, 0 on the left; the needle turns from 0 by the score's share
    # of 180 degrees. No bar ("無法判讀", or no levels), no gauge.
    if bar is None:
        return None
    segments = bar["segments"]
    arcs = []
    start = 0
    for number, segment in enumerate(segments, start=1):
        end = start + segment["width"]
        arc_start = start + (GAUGE_GAP if number > 1 else 0)
        arc_end = end - (GAUGE_GAP if number < len(segments) else 0)
        arcs.append(
            {
                "color": segment["color"],
                "d": f"M{_gauge_point(arc_start)}A{GAUGE_RADIUS} {GAUGE_RADIUS} 0 0 1 "
                f"{_gauge_point(arc_end)}",
            }
        )
        start = end
    angle = bar["position"] / 100 * HALF_CIRCLE_DEGREES
    return {"arcs": arcs, "angle": angle, "ceiling": bar["ceiling"]}


@login_required
@health_data_page
def submission_result(request, submission_id):
    submission = get_object_or_404(
        Submission.objects.defined(), pk=submission_id, user=request.user
    )
    answers = submission.answers.select_related("question__questionnaire").order_by(
        "question__question_number"
    )
    result = submission.questionnaire.definition.result
    # #304 (ADR 0023): the home page's 建議下一步, by the user's state now, not this record's.
    next_step, _ = home_more(request.user, timezone.localdate())
    if result == AVERAGE:
        return render(
            request,
            "screening/ssq12_result.html",
            {
                "submission": submission,
                "answers": answers,
                "wearing_text": TREND_STATUS_TEXT[submission.wearing_hearing_aid],
                "show_comparison": _shows_wearing_comparison(
                    request.user, submission.questionnaire
                ),
                "next_step": next_step,
            },
        )
    if result == NORM:
        return _ioi_ha_result(request, submission, answers, next_step)
    if result == SUBSCALES:
        prefetch_related_objects(
            [submission], Prefetch("answers", queryset=Answer.objects.select_related("question"))
        )
        return render(
            request,
            "screening/sadl_result.html",
            {"submission": submission, "next_step": next_step},
        )
    total_score = submission.total_answer_score
    emotional = submission.emotional_score
    social = submission.social_score
    classified_score = submission.classified
    return render(
        request,
        "screening/result.html",
        {
            "submission": submission,
            "answers": answers,
            "wearing_text": TREND_STATUS_TEXT[submission.wearing_hearing_aid],
            "total_score": total_score,
            "emotional": emotional,
            "social": social,
            "has_subscores": _has_subscores(answers),
            "max_score": max_score(submission.questionnaire.code),
            "classified_score_text": classified_score["text"],
            "classified_score_color": classified_score["color"],
            "score_bar": _score_bar(
                submission.questionnaire.definition,
                submission.total_answer_score,
                classified_score["level"],
            ),
            "next_steps": submission.questionnaire.definition.next_steps.get(
                classified_score["level"], ()
            ),
            "advice": get_advice(classified_score["level"], submission.questionnaire.code),
            # #363: 「無法判讀」 has nothing else saying why, so its advice is not folded away.
            "advice_open": classified_score["level"] == UNKNOWN["level"],
            "support_message": submission.questionnaire.definition.support(
                {answer.question.question_number: answer.score for answer in answers}
            ),
            "show_comparison": _shows_wearing_comparison(request.user, submission.questionnaire),
            "optional_ssq12": (
                Questionnaire.objects.filter(code=SSQ12).first()
                if submission.questionnaire.code in (hhie_s.CODE, hhia_s.CODE)
                and submission.wearing_hearing_aid is False
                else None
            ),
            "next_step": next_step,
        },
    )


def _ioi_ha_items(submission, answers, texts):
    # The only place IOI-HA answers meet the norms; the result page and the report both use it,
    # each with its own words for the comparison (texts: NORM_VERSUS_TEXT or NORM_COMPARISON_TEXT).
    grouped = submission.norm_group != NormGroup.UNGROUPED
    items = []
    for answer in answers:
        number = answer.question.question_number
        comparison = (
            compare_to_norm(submission.norm_group, number, answer.score) if grouped else None
        )
        norm = IOI_HA_NORMS[submission.norm_group][number] if grouped else None
        items.append(
            {
                "name": IOI_HA_ITEM_NAMES[number],
                "text": answer.question.question_text,
                "label": IOI_HA_CHOICES[number][answer.score - 1],
                "comparison_code": comparison,
                "comparison": texts.get(comparison),
                "note": IOI_HA_BELOW_NORM_NOTES[number] if comparison == "below" else None,
                # The result page's 5-cell scale, scores 1-5: the norm cells and the answer.
                "cells": [
                    {
                        "band": norm is not None and norm[0] <= score <= norm[1],
                        "mine": score == answer.score,
                    }
                    for score in range(1, 6)
                ],
            }
        )
    return items, grouped


def _ioi_ha_summary(submission):
    # One IOI-HA record against the norms, for the report and the home page's last result.
    answers = submission.answers.select_related("question").order_by("question__question_number")
    items, grouped = _ioi_ha_items(submission, answers, NORM_COMPARISON_TEXT)
    return {
        "submission": submission,
        "items": items,
        "grouped": grouped,
        "below": sum(item["comparison_code"] == "below" for item in items),
        "above": sum(item["comparison_code"] == "above" for item in items),
    }


def _ioi_ha_result(request, submission, answers, next_step):
    # No total, level or advice: IOI-HA is read item by item against the fixed norm group.
    items, grouped = _ioi_ha_items(submission, answers, NORM_VERSUS_TEXT)
    # Items below the norm come first and open; the rest are folded under 「其他 n 項」 (#187).
    below = [item for item in items if item["comparison_code"] == "below"]
    return render(
        request,
        "screening/result_ioi_ha.html",
        {
            "submission": submission,
            "items": items,
            "grouped": grouped,
            "below": below,
            "below_text": NORM_VERSUS_TEXT["below"],
            "others": [item for item in items if item not in below],
            "scale_ends": IOI_HA_SCALE_ENDS,
            "next_step": next_step,
        },
    )


@login_required
@health_data_page
def audiogram_list(request):
    audiograms = list(request.user.audiograms.prefetch_related("points"))
    for audiogram in audiograms:
        # From the points already loaded with the list: no query per card.
        audiogram.thumbnail = thumbnail(audiogram.points.all())
    return render(request, "screening/audiogram_list.html", {"audiograms": audiograms})


def _chart_points(points):
    return [
        {
            "ear": p.ear,
            "conduction": p.conduction,
            "frequency": p.frequency,
            "db": p.db,
            "no_response": p.no_response,
            "masked": p.masked,
        }
        for p in points
    ]


@login_required
def audiogram_new(request):
    return render(request, "screening/audiogram_new.html", {"today": timezone.localdate()})


def _own_audiogram(request, audiogram_id):
    return get_object_or_404(request.user.audiograms.prefetch_related("points"), pk=audiogram_id)


@login_required
@health_data_page
def audiogram_detail(request, audiogram_id):
    audiogram = _own_audiogram(request, audiogram_id)
    context = _audiogram_context(audiogram)
    # #201: the report holds the latest audiogram; the compare button picks this one and the one
    # before it (the next newer when this is the oldest), in the model's newest-first order.
    rows = list(request.user.audiograms.values_list("id", "tested_on"))
    ids = [row_id for row_id, _ in rows]
    here = ids.index(audiogram.id)
    if here > 0:
        context["latest_tested_on"] = rows[0][1]
    if len(ids) > 1:
        context["compare_with"] = ids[here + 1] if here + 1 < len(ids) else ids[here - 1]
    # #230: link the guide when either ear's PTA is over 25 dB; not when that is unknown.
    context["fitting_guide"] = recommends_fitting_assessment(context["points"])
    return render(request, "screening/audiogram_detail.html", context)


def _audiogram_context(audiogram):
    # Shared by the audiogram page and the health report, so both read it the same way.
    result = audiogram.interpretation()
    # Right ear first, air before bone, as on a clinical record.
    points = sorted(
        audiogram.points.all(), key=lambda p: (p.ear != Ear.RIGHT, p.conduction, p.frequency)
    )
    return {
        "audiogram": audiogram,
        "ears": [(ear.value, ear.label, result[ear.value]) for ear in (Ear.RIGHT, Ear.LEFT)],
        "points": points,
        "chart_points": _chart_points(points),
    }


@login_required
@require_http_methods(["GET", "POST"])
@health_data_page
def audiogram_delete(request, audiogram_id):
    audiogram = _own_audiogram(request, audiogram_id)
    if request.method == "POST":
        audiogram.delete()
        return redirect("audiogram_list")
    audiogram.thumbnail = thumbnail(audiogram.points.all())
    return render(request, "screening/audiogram_delete.html", {"audiogram": audiogram})


@login_required
@health_data_page
def audiogram_edit(request, audiogram_id):
    audiogram = _own_audiogram(request, audiogram_id)
    initial = {
        "tested_on": audiogram.tested_on.isoformat(),
        "points": _chart_points(audiogram.points.all()),
    }
    return render(
        request,
        "screening/audiogram_new.html",
        {"today": timezone.localdate(), "audiogram": audiogram, "initial": initial},
    )


def _compare_ids(request, audiograms):
    if "a" not in request.GET and "b" not in request.GET:
        return [a.id for a in audiograms[:2]]
    try:
        return [int(request.GET["a"]), int(request.GET["b"])]
    except (KeyError, ValueError):
        raise Http404 from None


@login_required
@health_data_page
def audiogram_compare(request):
    audiograms = list(request.user.audiograms.all())
    context = {"audiograms": audiograms}
    if len(audiograms) < 2:
        return render(request, "screening/audiogram_compare.html", context)
    ids = _compare_ids(request, audiograms)
    # Model ordering puts the newer one first, whichever select it was picked in (spec 4.2).
    pair = list(request.user.audiograms.prefetch_related("points").filter(pk__in=ids))
    if len(pair) != len(set(ids)):
        raise Http404
    ear = request.GET.get("ear")
    if ear not in Ear.values:
        ear = Ear.RIGHT
    # #202: the 舊 and 新 rows, newest first as the model orders them, even for one picked twice.
    picked = [audiogram for audiogram in audiograms if audiogram.id in ids]
    context.update(
        a=ids[0],
        b=ids[1],
        ear=ear,
        ears=Ear.choices,
        pick_rows=[("舊", "b", picked[-1]), ("新", "a", picked[0])],
    )
    if len(pair) == 2:
        new, old = pair
        result = compare(new.points.all(), old.points.all())[ear]
        context.update(
            new=new,
            old=old,
            ear_label=Ear(ear).label,
            result=result,
            sections=[("air", "氣導", result["air"]), ("bone", "骨導", result["bone"])],
            chart_points=_chart_points(p for p in new.points.all() if p.ear == ear),
            old_chart_points=_chart_points(p for p in old.points.all() if p.ear == ear),
        )
    return render(request, "screening/audiogram_compare.html", context)
