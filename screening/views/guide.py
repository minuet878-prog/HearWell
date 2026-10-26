from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.views.decorators.http import require_http_methods

from screening import assessment_hospitals, models
from screening.fitting_route import AUDIOGRAM, STOPS, fitting_state, not_applicable_stops
from screening.forms import STOP_QUESTIONS
from screening.main_flow import get_user_state
from screening.models import Ear, Questionnaire
from screening.questionnaires.ssq12_tw import CODE as SSQ12
from screening.views.answering import _wearing_follow_ups, list_order
from screening.views.common import _safe_next, health_data_page


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
