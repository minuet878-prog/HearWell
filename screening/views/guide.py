from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from django.http import Http404, HttpRequest, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers

from screening import assessment_hospitals, device_centres, models
from screening.audiogram import FittingAdvice, over_mild
from screening.fitting_route import (
    AUDIOGRAM,
    SUBSIDY_STOPS,
    fitting_state,
    not_applicable_stops,
    stops_on_route,
    subsidy_declined,
)
from screening.forms import STOP_QUESTIONS
from screening.journey_todos import stop_todos
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


# The hearing-aid guide's chapters in reading order (spec #218).
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
        context["life_impact"] = get_user_state(request.user, today=today).life_impact
        # Whether the latest record was answered wearing hearing aids (#220 M16, grill Q4), or
        # a fitting date is filled in (#287).
        context["wearing"] = state.wearing
        if state.audiogram is not None:
            context |= _guide_audiogram(state)
            context["fitting_words"] = _fitting_words(state, request.user, today)
    context["route"] = route = _route(state, request.user, edit, question)
    # #596 (ADR 0063): the 補助站 folded into a line under the route, signed out too.
    context["subsidy_folded"] = state is None or not state.subsidy_shown
    # #467 (I2): the line is blue as far as the 目前這一站, and its entrance is paced by how far
    # that is, so it takes about the same time wherever the stop is.
    here = next((i for i, stop in enumerate(route) if stop.here), None)
    context["route_here"] = here
    context["route_pace"] = max(here or 0, 1)
    response = render(request, "screening/guide/index.html", context)
    if request.user.is_authenticated:
        # Shows this account's records (GLOSSARY 健康資料頁面): never cached.
        add_never_cache_headers(response)
    return response


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
    # The latest audiogram's 選配 and 身障鑑定門檻 meters (#226, #227, #260, ADR 0017).
    estimate = state.threshold
    ears = [(ear.label, ear.value, estimate[ear.value]) for ear in (Ear.RIGHT, Ear.LEFT)]
    context = {
        "audiogram": state.audiogram,
        "ears": ears,
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
    answer_link: tuple[str, str] | None = None  # (wording, url) under the answer (#597)
    questions: tuple = ()  # the stop's question forms shown open (#293, #294)
    editable: bool = False  # 修改 opens questions answered but not shown (#294)
    gap: str = ""  # said on the line on to the next stop (#296)
    todos: tuple = ()  # the 您在這裡 stop's 待辦 (spec #478), the 照顧旅程's card takes them too

    @property
    def here(self):
        return "您在這裡" in self.marks

    @property
    def below(self):
        return "估算未達門檻" in self.marks

    @property
    def not_applicable(self):
        return "不適用" in self.marks

    @property
    def done(self):
        return "已完成" in self.marks

    @property
    def other_marks(self):
        """The marks besides 您在這裡, which the 您在這裡 card says as its label (#467)."""
        return tuple(mark for mark in self.marks if mark != "您在這裡")

    @property
    def about(self):
        return ROUTE_ABOUT[self.slug][0]

    @property
    def about_link(self):
        """The wording of the link under what the stop is about; none where 修改這張聽力圖 is
        already the way on."""
        if "資料不足" in self.marks:
            return ""
        return ROUTE_ABOUT[self.slug][1]


# #293: each answer in short, under its stop.
CERTIFICATE_ANSWERS = {
    models.Certificate.YES: "有身障證明",
    models.Certificate.APPLYING: "打算申請或正在申請鑑定",  # #597 (spec #593)
    models.Certificate.NO_SUBSIDY: "沒有身障證明",
}
FORM_9_ANSWERS = {True: "九號表完成了", False: "九號表還沒完成"}  # #294
FORM_25_ANSWERS = {True: "二十五號表完成了", False: "二十五號表還沒完成"}  # #296
# Said under the stop for everyone the 補助站 are shown to (#294, spec #291 Q12: the notice's
# date is not asked; #596: not while they are folded, as there is no notice).
ROUTE_REMINDERS = {"types-and-prices": ("收到核定通知後 6 個月內要買。",)}
# #467 (I1, the owner's pick on the step interactions page): what each stop is about, said when
# its row is opened, and the wording of its link on. Drafts for the owner to review.
ROUTE_ABOUT = {
    AUDIOGRAM: (
        "把醫院給的聽力圖記下來，這裡就能整理要不要找聽力師評估，和有沒有達到身障鑑定門檻。",
        "記錄聽力圖",
    ),
    "before-you-go": ("第一次去評估選配助聽器前，先看要帶什麼、可以問聽力師哪些問題。", "看這一章"),
    "assessment": (
        "要申請助聽器的身障補助，先要有身心障礙證明；這一章說明鑑定門檻、怎麼申請和鑑定醫院。",
        "看這一章",
    ),
    "form-9": (
        "九號表是買助聽器前要做的評估報告；有身障證明的人，帶著它到公所申請補助。",
        "看這一章",
    ),
    "notice": ("到公所申請後，等主管機關核定；一定要先拿到核定通知再買。", "看申請流程"),
    "types-and-prices": ("看助聽器有哪些外型、補助多少，和去哪裡買。", "看這一章"),
    "after-fitting": ("剛開始戴要慢慢適應；也可以用聽伴的問卷記錄配戴的效果。", "看這一章"),
    "form-25": (
        "買中階型、進階型或雙對側傳聲型的人，配戴滿 1 個月後、3 個月內要做使用效益驗證。",
        "看這一章",
    ),
    "payout": ("帶購買憑證、保固書影本（和二十五號表）核銷，受理後 1 個月內撥款。", "看申請流程"),
}
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


def _route(state, user, edit=None, question=None):
    # 選配路線 (#258, spec #291): recording an audiogram, then the chapters in reading order
    # and the two waits, which have no chapter and point to form 9's 申請流程 (Q15). Signed
    # out, no stop is marked. user: state's, whose ticks the 您在這裡 stop's 待辦 read.
    steps = reverse("guide_chapter", args=["form-9"]) + "#steps-title"
    places = {c.slug: (c.title, reverse("guide_chapter", args=[c.slug])) for c in GUIDE_CHAPTERS}
    places |= {
        AUDIOGRAM: ("記錄聽力圖", reverse("audiogram_new")),
        "notice": ("等待核定公文", steps),
        "payout": ("等待補助發放", steps),
    }
    # Signed out, the 補助站 are folded, so neither the reminder nor the line on to form 25.
    shown = stops_on_route(False) if state is None else state.stops
    stops = [(slug, *places[slug]) for slug in shown]
    if state is None:
        return [RouteStop(slug=slug, title=title, url=url) for slug, title, url in stops]
    return [_route_stop(state, user, *stop, edit, question) for stop in stops]


def here_stop(state, user):
    """The 目前這一站 as the route shows it (title, url, button), or None without one; the
    照顧旅程's card takes it (ADR 0044). state: user's FittingState."""
    return next((stop for stop in _route(state, user) if stop.here), None)


def _route_stop(state, user, slug, title, url, edit=None, question=None):
    marks, links, action, tested_on = [], [], None, None
    notes = list(ROUTE_REMINDERS.get(slug, ())) if state.subsidy_shown else []
    form_9 = reverse("guide_chapter", args=["form-9"])
    without_certificate = ("看沒有身障證明時", f"{form_9}#without-certificate")
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
            AUDIOGRAM: ("記錄聽力圖", url),
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
        links.append(without_certificate)
    # #597 (spec #593 acceptance 21, the #595 mockup): 沒有 always leads on to the help there is
    # without a certificate, under the answer, whatever the estimate.
    declined = slug == "assessment" and subsidy_declined(state.aid)
    answer_link = without_certificate if declined else None
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
    # On the line on to form 25, unless form 25 is 不適用 or folded away (#596).
    gap = FORM_25_GAP if slug == "after-fitting" and state.form_25_on_route else ""
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
        answer_link=answer_link,
        questions=shown,
        editable=editable,
        gap=gap,
        todos=stop_todos(slug, state, user) if slug == state.stop else (),
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
    where the stop is 不適用 (#291 review) or a 補助站 after 沒有 (#596); question is a form sent
    back with its errors."""
    # #579 (spec #576): the next chapter in reading order, the same for everyone; the route's
    # progress is not read. None after the last.
    following = GUIDE_CHAPTERS[GUIDE_CHAPTERS.index(chapter) + 1 :]
    context = {"chapter": chapter, "next_chapter": following[0] if following else None}
    if chapter.extra_context:
        context.update(chapter.extra_context(request))
    user = request.user
    asked = chapter.slug in STOP_QUESTIONS and user.is_authenticated and user.has_consented()
    aid = models.AidAndSubsidy.for_user(user) if asked else None
    declined = subsidy_declined(aid) and chapter.slug in SUBSIDY_STOPS
    if asked and (chapter.slug in not_applicable_stops(aid) or declined):
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


@form_address
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
    next_url = safe_next(request)
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
