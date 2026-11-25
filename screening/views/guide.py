from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from django.http import Http404, HttpRequest, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.views.decorators.cache import never_cache

from screening import assessment_hospitals, device_centres, models, subsidy_estimate
from screening.audiogram import FittingAdvice, over_mild
from screening.fitting_route import (
    AUDIOGRAM,
    GUIDE_PAGE,
    STOPS,
    SUBSIDY_STOPS,
    TYPES_AND_PRICES,
    fitting_state,
    keep_view,
    not_applicable_stops,
    stops_on_route,
    subsidy_declined,
    subsidy_stops_shown,
)
from screening.forms import STOP_QUESTIONS, SubsidyEstimateForm
from screening.main_flow import get_user_state
from screening.models import Ear, Questionnaire
from screening.questionnaires.ssq12_tw import CODE as SSQ12
from screening.scoring import (
    FITTING_ADVICE_BEFORE_YOU_GO,
    FITTING_ADVICE_MILD_IMPACT,
    FITTING_ADVICE_NORMAL,
    FITTING_ADVICE_OVER_MILD,
    FITTING_ADVICE_QUESTIONNAIRE_FIRST,
    FITTING_ADVICE_TRACK,
    LIFE_IMPACT_BUTTON,
)
from screening.views.answering import list_order, wearing_follow_ups
from screening.views.common import form_address, health_data_page, safe_next


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


def _form_9_context(request):
    return {"centres_by_county": device_centres.CENTRES_BY_COUNTY}


def _after_fitting_context(request):
    # #220 H8, H9, then SADL (the owner's addition): what the wizard offers someone who
    # wears hearing aids, not every listed questionnaire. Both life-impact questionnaires too,
    # for answering one again worn (F4): the chapter is the same for everyone, so no age.
    questionnaires = list(Questionnaire.objects.defined())
    return {
        "follow_ups": wearing_follow_ups(questionnaires),
        "life_impact": _life_impact_pair(questionnaires),
    }


def _form_25_context(request):
    # What to answer before the verification visit (F3): the life-impact pair worn, IOI-HA and
    # SADL; SSQ12-TW stays the after-fitting chapter's.
    questionnaires = list(Questionnaire.objects.defined())
    return {
        "follow_ups": [q for q in wearing_follow_ups(questionnaires) if q.code != SSQ12],
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
    # In the browser tab and search results, in the words family type (spec #583, #587); the
    # chapter's own heading stays `title`.
    search_title: str = field(kw_only=True)
    description: str = field(kw_only=True)


# The hearing-aid guide's chapters (spec #218); read in the fitting route's order (#760).
GUIDE_CHAPTERS = (
    GuideChapter(
        "before-you-go",
        "去找聽力師之前",
        "screening/guide/before_you_go.html",
        search_title="第一次配助聽器要準備什麼？去找聽力師之前｜聽伴",  # noqa: RUF001
        description="去找聽力師之前要帶什麼、可以問聽力師什麼。",
    ),
    GuideChapter(
        "assessment",
        "身障鑑定與鑑定醫院",
        "screening/guide/assessment.html",
        _assessment_context,
        search_title="聽力要多差才能申請身障證明？鑑定門檻與鑑定醫院｜聽伴",  # noqa: RUF001
        description="聽力要到多少才達到門檻、鑑定時要做哪些檢查、要怎麼申請，以及各縣市可以鑑定的醫院。",
    ),
    GuideChapter(
        "form-9",
        "九號表：申請助聽器補助",
        "screening/guide/form_9.html",
        _form_9_context,
        search_title="助聽器補助怎麼申請？可以補助多少錢｜聽伴",  # noqa: RUF001
        description="誰可以申請、要怎麼辦、九號表去哪裡開、可以補助多少錢、用了幾年可以換新的，以及沒有身障證明怎麼辦。",
    ),
    GuideChapter(
        "types-and-prices",
        "助聽器的種類與價格",
        "screening/guide/types_and_prices.html",
        search_title="助聽器是不是都很貴？種類、價格與補助上限｜聽伴",  # noqa: RUF001
        description="助聽器有哪幾種外型、擴音器和輔聽器可不可以代替、補助分哪幾級、要去哪裡買。",
    ),
    # F5: the first weeks wearing them come before the visit 1 to 3 months in.
    GuideChapter(
        "after-fitting",
        "配戴助聽器之後",
        "screening/guide/after_fitting.html",
        _after_fitting_context,
        search_title="剛戴助聽器不習慣怎麼辦？配戴之後｜聽伴",  # noqa: RUF001
        description="剛開始戴會怎麼樣、怎麼記錄戴了之後的感受。",
    ),
    GuideChapter(
        "form-25",
        "二十五號表：使用效益驗證",
        "screening/guide/form_25.html",
        _form_25_context,
        search_title="助聽器補助核銷要做什麼？二十五號表｜聽伴",  # noqa: RUF001
        description="二十五號表誰要做、什麼時候做，以及回診前可以先準備什麼。",
    ),
)


def guide(request):
    # Open without logging in (spec #218): the contents are for family too. The old ?edit=<slug>
    # (#293) opens nothing now the route is gone (#779): the page shows as it is.
    keep_view(request.user, GUIDE_PAGE)
    context, state = {}, None
    if request.user.is_authenticated:
        today = timezone.localdate()
        state = fitting_state(request.user, today)
        context["has_records"] = state.has_records
        context["latest"] = state.latest  # 問卷結果 without an audiogram asks for one
        # The same life-impact record the home page shows as the last result.
        context["life_impact"] = get_user_state(request.user, today=today).life_impact
        # Whether the latest record was answered wearing hearing aids (#220 M16, grill Q4), or
        # a fitting date is filled in (#287).
        context["wearing"] = state.wearing
        if state.audiogram is not None:
            context |= _guide_audiogram(state)
            context["fitting_words"] = _fitting_words(state, request.user, today)
    context["cards"] = _guide_cards(state)
    context["tiles"] = CHAPTER_TILES
    response = render(request, "screening/guide/index.html", context)
    if request.user.is_authenticated:
        # Shows this account's records (GLOSSARY 健康資料頁面): never cached.
        add_never_cache_headers(response)
    return response


@dataclass(frozen=True)
class GuideCard:
    """An 引導卡 (GLOSSARY, ADR 0083): a short title, one line, one button and an icon."""

    slug: str
    title: str
    point: str
    button: tuple[str, str]  # (wording, url)
    icon: str  # one of guide/card_icon.html's
    done: bool = False


def _guide_cards(state):
    """#779 (spec #774): the five 引導卡, the same five for everyone; each 已完成 by the 選配路線
    stops behind it (the owner's pick of 2026-11-24), none signed out (state None). The words
    are drafts for the owner to review."""
    chapter = {c.slug: reverse("guide_chapter", args=[c.slug]) for c in GUIDE_CHAPTERS}
    audiogram = ("記錄聽力圖", reverse("audiogram_new"))
    done, form_25_passed = frozenset(), False
    if state is not None:
        done = state.done
        if state.insufficient:
            # As the route did (grill Q9): never 已完成, and the button edits that audiogram.
            audiogram = ("修改這張聽力圖", reverse("audiogram_edit", args=[state.audiogram.pk]))
        # Form 25 done, or 不適用 by the answers whether the 補助站 are shown or folded.
        form_25_passed = "form-25" in done or "form-25" in not_applicable_stops(state.aid)
    return (
        GuideCard(
            AUDIOGRAM,
            "記錄聽力圖",
            "把醫院給的聽力圖記下來，這裡就能幫您整理下一步。",
            audiogram,
            "audiogram",
            AUDIOGRAM in done,
        ),
        GuideCard(
            "subsidy",
            "申請助聽器補助",
            "有身障證明可以申請補助；一定要先拿到核定公文再買。",
            ("算算看可以補助多少", reverse("guide_subsidy")),
            "document",
            # The notice's stop, never done after 沒有: the 補助站 stay folded (ADR 0063).
            "notice" in done,
        ),
        GuideCard(
            "before-you-go",
            "去找聽力師之前",
            "第一次去評估前，先看要帶什麼、可以問聽力師什麼。",
            ("看要準備什麼", chapter["before-you-go"]),
            "ear",
            "before-you-go" in done,
        ),
        GuideCard(
            TYPES_AND_PRICES,
            "助聽器的種類與價格",
            "看助聽器有哪些外型、補助分幾級，和去哪裡買。",
            ("看種類與價格", chapter[TYPES_AND_PRICES]),
            "aid",
            TYPES_AND_PRICES in done,
        ),
        GuideCard(
            "after-fitting",
            "配戴與核銷",
            "剛戴要慢慢適應；用身障補助的，之後還要做二十五號表、核銷補助。",
            ("看配戴之後", chapter["after-fitting"]),
            "calendar",
            "after-fitting" in done and form_25_passed,
        ),
    )


# #779 (spec #774): the 章節磚, the six chapters in the route's reading order (#760), each with
# an icon and a short name (drafts for the owner to review).
CHAPTER_TILES = (
    ("assessment", "身障鑑定", "certificate"),
    ("form-9", "九號表補助", "document"),
    ("before-you-go", "找聽力師之前", "ear"),
    (TYPES_AND_PRICES, "種類與價格", "aid"),
    ("after-fitting", "配戴之後", "calendar"),
    ("form-25", "二十五號表", "seal"),
)


def _fitting_words(state, user, today):
    """要不要找聽力師評估's sentence by 建議評估選配 (ADR 0067) and its link (text, url) or None;
    None for 無法判斷, which the page words with its audiogram's edit link."""
    if state.advice == FittingAdvice.RECOMMEND:
        # Of the two 建議 wordings, the one for an ear over 40 dB HL (spec #693).
        ptas = (state.threshold["right"]["pta"], state.threshold["left"]["pta"])
        words = FITTING_ADVICE_OVER_MILD if over_mild(ptas) else FITTING_ADVICE_MILD_IMPACT
        before_you_go = reverse("guide_chapter", args=["before-you-go"])
        return words, (FITTING_ADVICE_BEFORE_YOU_GO, before_you_go)
    if state.advice == FittingAdvice.QUESTIONNAIRE_FIRST:
        # Imported here: care_journey imports this module for here_stop.
        from screening.care_journey import first_questionnaire_url

        # The questionnaire the 照顧旅程's step 1 asks for (spec #693).
        link = (LIFE_IMPACT_BUTTON, first_questionnaire_url(user, today))
        return FITTING_ADVICE_QUESTIONNAIRE_FIRST, link
    if state.advice == FittingAdvice.TRACK:
        return FITTING_ADVICE_TRACK, None
    if state.advice == FittingAdvice.NORMAL:
        return FITTING_ADVICE_NORMAL, None
    return None


def _percent(ratio):
    # 43.125 and 52.5 and 100, as the worked steps write them.
    return format(ratio.normalize(), "f")


def _guide_audiogram(state):
    # The latest audiogram's 選配 meters, and the 身障鑑定門檻's from the newest hearing exam
    # (#226, #227, #260, ADR 0017, 0068).
    latest = state.threshold
    ears = [(ear.label, ear.value, latest[ear.value]) for ear in (Ear.RIGHT, Ear.LEFT)]
    estimate = state.assessment
    context = {
        "audiogram": state.audiogram,
        "ears": ears,
        "threshold": latest,
        "assessment": estimate,
        "assessment_exam": state.assessment_exam,
        # The estimate's exam is older than the page's audiogram, a newer self test (#706).
        "older_exam": state.assessment_exam not in (None, state.audiogram),
    }
    if estimate is not None and estimate["ratio"] is not None:
        assessed = [(label, estimate[side]) for label, side, _ in ears]
        context["worked"] = {
            "ears": [(label, e["pta"], _percent(e["ratio"])) for label, e in assessed],
            "better": _percent(estimate["better"]),
            "worse": _percent(estimate["worse"]),
        }
    return context


@dataclass(frozen=True)
class RouteStop:
    """The 目前這一站 the 照顧旅程's card and the 建議下一步 take (ADR 0044)."""

    slug: str
    title: str
    url: str
    action: tuple[str, str] | None = None  # its button
    questions: tuple = ()  # its next question's form (#293, #294)


# #293: each answer in short, under its stop.
CERTIFICATE_ANSWERS = {
    models.Certificate.YES: "有身障證明",
    models.Certificate.APPLYING: "打算申請或正在申請鑑定",  # #597 (spec #593)
    models.Certificate.NO_SUBSIDY: "沒有身障證明",
}
FORM_9_ANSWERS = {True: "九號表完成了", False: "九號表還沒完成"}  # #294
FORM_25_ANSWERS = {True: "二十五號表完成了", False: "二十五號表還沒完成"}  # #296


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


def here_stop(state):
    """The 目前這一站 (title, url, button, question), or None without one; the 照顧旅程's card
    takes it (ADR 0044). #779: my guide no longer draws the 選配路線 it is a stop of."""
    slug = state.stop
    if slug not in state.stops:
        return None
    steps = reverse("guide_chapter", args=["form-9"]) + "#steps-title"
    places = {c.slug: (c.title, reverse("guide_chapter", args=[c.slug])) for c in GUIDE_CHAPTERS}
    places |= {
        AUDIOGRAM: ("記錄聽力圖", reverse("audiogram_new")),
        "notice": ("等待核定公文", steps),
        "payout": ("等待補助發放", steps),
    }
    title, url = places[slug]
    if slug == AUDIOGRAM and state.insufficient:
        # Never 已完成 (grill Q9): the title and the button go to editing it instead.
        url = reverse("audiogram_edit", args=[state.audiogram.pk])
        action = ("修改這張聽力圖", url)
    else:
        # The waits and types and prices have no button: the title is the only link.
        action = {
            AUDIOGRAM: ("記錄聽力圖", url),
            "before-you-go": ("去之前要準備什麼", url),
            "assessment": ("找鑑定醫院", url),
            "form-9": ("看九號表的流程", url),
            "after-fitting": ("記錄配戴的效果", f"{url}#record-title"),
            "form-25": ("看二十五號表要帶什麼", url),
        }.get(slug)
    # Spec #291 Q14: the next question only.
    questions = ()
    if slug in STOP_QUESTIONS:
        questions = (_reached(slug, state.aid)[-1](instance=state.aid),)
    return RouteStop(slug, title, url, action, questions)


def guide_chapter(request, chapter):
    # Like the family guide: the same reviewed content for everyone, no user data shown.
    found = next((c for c in GUIDE_CHAPTERS if c.slug == chapter), None)
    if found is None:
        raise Http404
    keep_view(request.user, chapter)
    return _chapter_page(request, found)


def _next_chapter(chapter, aid):
    """#760: the next stop on the fitting route with a chapter, the 補助站 skipped while folded
    (ADR 0063), as the route goes; None after the last. #579 (spec #576): the route's progress
    is not read, only whether the 補助站 are on it."""
    chapters = {c.slug: c for c in GUIDE_CHAPTERS}
    on_route = stops_on_route(subsidy_stops_shown(aid))
    later = STOPS[STOPS.index(chapter.slug) + 1 :]
    return next((chapters[slug] for slug in later if slug in chapters and slug in on_route), None)


# #777 (spec #774 acceptance 22): the notice, which has no chapter, is asked at form 9's foot
# once form 9 is done.
NOTICE_CHAPTER = "form-9"


def _chapter_page(request, chapter, sent=None):
    """A chapter, with its stop's question at the foot (#293) while a signed-in, consented
    user has not answered it, and 已記下 with the answer once they have (#294), but neither
    where the stop is 不適用 (#291 review) or a 補助站 after 沒有 (#596). ?edit=1 opens the
    answered question again in place, ?edit=notice the notice's (#777); sent is (stop, form),
    a form sent back with its errors."""
    user = request.user
    aid = models.AidAndSubsidy.for_user(user) if user.is_authenticated else None
    context = {"chapter": chapter, "next_chapter": _next_chapter(chapter, aid)}
    if chapter.extra_context:
        context.update(chapter.extra_context(request))
    if user.is_authenticated:
        context["notes"] = _foot_notes(chapter.slug, user, aid)
    asked = chapter.slug in STOP_QUESTIONS and user.is_authenticated and user.has_consented()
    declined = subsidy_declined(aid) and chapter.slug in SUBSIDY_STOPS
    if asked and not (chapter.slug in not_applicable_stops(aid) or declined):
        edit = request.GET.get("edit")
        stop, form = sent or (None, None)
        own = form if stop == chapter.slug else None
        context["foot"] = _foot(chapter.slug, aid, edit == "1", own)
        form_9_done = aid is not None and aid.form_9_done
        if chapter.slug == NOTICE_CHAPTER and form_9_done and subsidy_stops_shown(aid):
            sent_here = form if stop == "notice" else None
            context["notice"] = notice = _foot("notice", aid, edit == "notice", sent_here)
            if aid.notice_received and not notice["halfway"]:
                notice["answer"] = f"核定公文：{notice['answer']}"  # 核定公文：雙耳、中階型
    response = render(request, chapter.template, context)
    if user.is_authenticated:
        # Whether the question shows depends on this account's answers.
        add_never_cache_headers(response)
    return response


# #779 (the owner's pick of 2026-11-24, #774's 實作中本人補充): what the 選配路線 said under its
# stops, said at the chapter's foot under the answer now my guide no longer draws the route.
PURCHASE_REMINDER = "收到核定通知後 6 個月內要買。"  # #294 (spec #291 Q12)


def _foot_notes(slug, user, aid):
    """The chapter's notes at its foot, each (wording, url or None): 沒有 leads on to the help
    without a certificate (#597); 種類與價格 says the six months to buy in while the 補助站 are
    shown (#294, #596); form 9 says when 身障補助 can be applied for again (#288), form 25 its
    dates (#296, spec #291 acceptance 14). The rules are the route's."""
    if slug == "assessment" and subsidy_declined(aid):
        form_9 = reverse("guide_chapter", args=["form-9"])
        return (("看沒有身障證明時", f"{form_9}#without-certificate"),)
    if slug == TYPES_AND_PRICES and subsidy_stops_shown(aid):
        return ((PURCHASE_REMINDER, None),)
    if slug not in ("form-9", "form-25") or subsidy_declined(aid):
        return ()
    state = fitting_state(user, timezone.localdate())
    if slug == "form-9":
        reapply = state.reapply_on
        return ((f"{reapply:%Y/%m/%d} 起可以再申請補助", None),) if reapply else ()
    if state.form_25 is None:
        return ()
    # From when before it opens, by when while open, and once it has closed the deadline,
    # never saying it is overdue.
    opens, closes = state.form_25
    if state.today < opens:
        return ((f"{opens:%Y/%m/%d} 起可以做", None),)
    if state.today <= closes:
        return ((f"{closes:%Y/%m/%d} 前要做完", None),)
    return ((f"期限是 {closes:%Y/%m/%d}", None),)


def _foot(slug, aid, editing, sent):
    """A stop at a chapter's foot: its answer in short, and the questions shown open: sent, a
    form sent back with its errors; editing, every one asked so far (#777); else the next one
    while unanswered or halfway, the notice received without its ears or level (#294). An
    answered stop with its questions open, not halfway, is being edited."""
    answer = _answer(slug, aid)
    reached = _reached(slug, aid)
    halfway = slug == "notice" and aid.notice_received and not (aid.approved_ears and aid.level)
    if sent is not None:
        questions = (sent,)
    elif editing and answer:
        questions = tuple(form_class(instance=aid) for form_class in reached)
    elif not answer or halfway:
        questions = (reached[-1](instance=aid),)
    else:
        questions = ()
    editing = bool(answer and questions) and not halfway
    return {"answer": answer, "questions": questions, "halfway": halfway, "editing": editing}


@form_address
@health_data_page
def route_answer(request):
    # #293 (spec #291 acceptance 28): a stop's answer, request.user's own only; back to where it
    # was asked, a chapter's foot or the home page's card, else (#779) to the stop's chapter.
    stop = request.POST.get("stop")
    questions = STOP_QUESTIONS.get(stop)
    if questions is None:
        return HttpResponseBadRequest()
    # The question whose answer was pressed (#294: the notice has three).
    form_class = next((q for q in questions if q.base_fields.keys() & request.POST.keys()), None)
    form_class = form_class or questions[0]
    aid = models.AidAndSubsidy.for_user(request.user)
    form = form_class(request.POST, instance=aid or models.AidAndSubsidy(user=request.user))
    next_url = safe_next(request)
    # The notice is asked at form 9's foot (#777), every other stop at its own chapter's.
    slug = NOTICE_CHAPTER if stop == "notice" else stop
    chapter = next(c for c in GUIDE_CHAPTERS if c.slug == slug)
    if form.is_valid():
        today = timezone.localdate()
        here = fitting_state(request.user, today).stop
        form.save()
        # #336: only the 您在這裡 stop turning 已完成, which a stop turning 不適用 is not.
        if urlsplit(next_url).path == reverse("index"):
            if here == stop and stop in fitting_state(request.user, today).done:
                # #745 (grill Q13): the home page's answer card, back at the step with the stop
                # just finished in the address, so 接著往下一站 to the page itself loads it anew.
                return HttpResponseRedirect(f"{reverse('index')}?done={stop}#journey-now")
        place = "#stop-notice" if stop == "notice" else "#stop-question"
        foot = reverse("guide_chapter", args=[chapter.slug]) + place
        return HttpResponseRedirect(next_url or foot)
    # #779: the errors at the stop's chapter's foot, wherever it was sent from.
    return _chapter_page(request, chapter, (stop, form))


@never_cache
def guide_subsidy(request):
    # #775 (spec #774, ADR 0083): 補助引導與試算, open without logging in (CODING_STANDARDS.md
    # 2): it reads and keeps no one's data, signed in or not. The answers so far come in this
    # POST and go back in this response as hidden fields, with no redirect, session or database;
    # never_cache keeps 上一頁 on a shared phone from showing them.
    sent = request.POST
    answers, step = {}, subsidy_estimate.estimate({})
    while isinstance(step, subsidy_estimate.Question) and step.name in sent:
        form = SubsidyEstimateForm(step, sent)
        if not form.is_valid():
            break
        answers |= form.cleaned_data
        step = subsidy_estimate.estimate(answers)
    if "back" in sent:
        # 上一題: the question before the one shown (or before the result), its answer chosen.
        names = list(answers)
        if sent["back"] in names:
            names = names[: names.index(sent["back"])]
        initial = {names[-1]: answers[names[-1]]} if names else {}
        answers = {name: answers[name] for name in names[:-1]}
        step = subsidy_estimate.estimate(answers)
        form = SubsidyEstimateForm(step, initial=initial)
    elif isinstance(step, subsidy_estimate.Question):
        # The question sent without an answer (or a made-up one) says so; the next comes fresh.
        asked = step.name in sent or sent.get("shown") == step.name
        form = SubsidyEstimateForm(step, sent if asked else None)
    is_result = isinstance(step, subsidy_estimate.Result)
    return render(
        request,
        "screening/guide/subsidy.html",
        {
            "question": None if is_result else step,
            "form": None if is_result else form,
            "result": step if is_result else None,
            "answers": answers,
            "number": len(answers) + 1,
            # After a press, focus goes to what is new: the question's title or the result's.
            "moved": request.method == "POST",
            "intro": subsidy_estimate.INTRO,
            "amount_label": subsidy_estimate.AMOUNT_LABEL,
            "amount_note": subsidy_estimate.AMOUNT_NOTE,
            "next_step_label": subsidy_estimate.NEXT_STEP_LABEL,
            "young_note": subsidy_estimate.YOUNG_NOTE,
            "sources": subsidy_estimate.SOURCES,
            "checked_on": subsidy_estimate.CHECKED_ON,
        },
    )
