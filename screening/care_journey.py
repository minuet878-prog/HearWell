"""Where a user stands on the 照顧旅程 (GLOSSARY, ADR 0044, ADR 0074): each of the seven steps'
state, the 現在這一步 and its card, and the home page's two tiles, the one place the home page and
the result pages ask. It reads the 選配路線 and the main flow's state; it judges nothing anew."""

import math
from dataclasses import dataclass, replace
from datetime import date

from django.urls import reverse
from django.utils import timezone

from screening.audiogram import FittingAdvice, interpret
from screening.fitting_route import (
    GUIDE_PAGE,
    HOSPITAL_SEARCH,
    TYPES_AND_PRICES,
    add_months,
    fitting_state,
    ioi_ha_since,
)
from screening.forms import STOP_QUESTIONS
from screening.main_flow import get_user_state, life_impact_questionnaire
from screening.models import Certificate, Questionnaire, Submission
from screening.questionnaires.ioi_ha import CODE as IOI_HA
from screening.scoring import (
    AFTER_FITTING_WORDS,
    AIRPODS_SELF_TEST,
    ANSWER_CARDS,
    AUDIOGRAM_SOURCES,
    BEFORE_YOU_GO_BUTTON,
    CARE_JOURNEY_ABOUT,
    CARE_JOURNEY_STEPS,
    FIND_A_HOSPITAL,
    FIND_AN_ASSESSMENT_HOSPITAL,
    FIRST_IOI_HA,
    FIRST_IOI_HA_NOTE,
    FIRST_SCREENING_NOT_DONE,
    FITTING_AGAIN_FROM,
    FITTING_COMPARE,
    FORM_9_STEPS,
    FORM_25_BUTTON,
    FORM_25_BY,
    FORM_25_FROM,
    GUIDE_BECAUSE,
    GUIDE_ENTRY,
    HOSPITAL_REPORT,
    INELIGIBLE_MILD,
    INELIGIBLE_NORMAL,
    IOI_HA_BUTTON,
    LIFE_IMPACT_BECAUSE,
    LIFE_IMPACT_BUTTON,
    NEXT_SCREENING,
    NEXT_STEP_REASONS,
    NEXT_STOP_NAMES,
    RECORD_FITTING_DATE,
    RECORD_THE_NOTICE,
    RETEST_BUTTON_TEXT,
    RETEST_TIME_UP,
    TYPES_AND_PRICES_ENTRY,
    TYPES_AND_PRICES_FIRST,
    UNKNOWN,
)
from screening.views.guide import here_stop

# A step's state (GLOSSARY 照顧旅程). LATER is any step not done that is not the 現在這一步,
# steps 1 to 4 left unticked by someone wearing hearing aids too (spec #741 acceptance 28).
DONE = "done"
CURRENT = "current"
LATER = "later"
NOT_NEEDED = "not-needed"  # 目前不需要, steps 4 to 6 only
FITTING_STEPS = (4, 5, 6)
# 目前不需要 while the route waits on these (ADR 0067); waiting on a questionnaire first, the
# steps are 之後, as whether they are needed is not known yet (spec #693 acceptance 8).
NOT_NEEDED_ADVICE = frozenset({FittingAdvice.NORMAL, FittingAdvice.TRACK})
WEARING_FROM = 5  # someone wearing hearing aids looks for the 現在這一步 from step 5 on
LAST_STEP = 7
FITTING_MONTHS = 3  # IOI-HA again once hearing aids are worn 3 months (ADR 0074)
WHERE_TO_TEST = "where-to-get-a-hearing-test"  # the Q&A answer step 2's 查詢醫療院所 opens
# 等待補助發放 is never done and the home page never shows it (grill Q10): step 5 is done once
# the route is past everything else.
ROUTE_DONE_AT = (None, "payout")
# 不符資格 (GLOSSARY): step 4's two cases, by the audiogram's estimates (grill Q12, Q22).
NORMAL_HEARING = "normal"
MILD_HEARING = "mild"


@dataclass(frozen=True)
class HomeCard:
    title: str
    href: str


@dataclass(frozen=True)
class NextStep:
    """A result page's 建議下一步 (result_next.html)."""

    card: HomeCard
    button: str
    suggested: str | None  # "print" or "share" off the journey, so the page drops that card


@dataclass(frozen=True)
class Entry:
    """A white entry card (entry_card.html): its words, where it goes and its icon (an
    action_icon.html icon); come_back, its page leads back here (the page adds ?next=)."""

    text: str
    href: str
    icon: str
    come_back: bool = False
    note: str = ""  # a small line beside the words


@dataclass(frozen=True)
class Choice:
    """A box on an answer card: the value its stop's form takes, its word, the small line under
    it, its icon (answer_card.html) and whether it is the answer kept."""

    value: str
    text: str
    note: str
    icon: str
    chosen: bool


@dataclass(frozen=True)
class AnswerCard:
    """A 目前這一站's question on step 5's card (answer_card.html), sent to route_answer as the
    stop's question at the foot of its chapter is: the stop, its form's field and the boxes."""

    stop: str
    field: str
    question: str
    icon: str  # an action_icon.html icon
    choices: tuple[Choice, ...]


@dataclass(frozen=True)
class DateCard:
    """A calendar date card (date_card.html): the day, what it is from, and the line under it."""

    on: date
    text: str
    note: str


@dataclass(frozen=True)
class EarResult:
    label: str  # 右耳, 左耳
    side: str  # right, left
    degree: str | None  # None: no four-frequency average
    pta: float | None


@dataclass(frozen=True)
class AudiogramResult:
    """Step 3 done: the newest audiogram's card, each ear's degree and average, to see it."""

    href: str
    tested_on: date
    ears: tuple[EarResult, ...]


# The countdown ring's drawing (countdown_ring.html): its centre and radius in the SVG's units.
RING_CENTRE = 52
RING_RADIUS = 44


@dataclass(frozen=True)
class Countdown:
    """A countdown card (countdown_card.html, spec #741): the day it counts to, the days left,
    the share of the wait gone (the ring's arc, 0 to under 1), and its words above or below the
    day."""

    on: date
    days_left: int
    elapsed: float
    above: str = ""
    below: str = ""

    @property
    def ring_path(self):
        """The ring's arc of the wait gone, clockwise from the top, as site.css's
        play-once-ring draws it."""
        angle = 2 * math.pi * self.elapsed
        x = round(RING_CENTRE + RING_RADIUS * math.sin(angle), 1)
        y = round(RING_CENTRE - RING_RADIUS * math.cos(angle), 1)
        large = int(self.elapsed > 0.5)
        top = RING_CENTRE - RING_RADIUS
        return f"M{RING_CENTRE} {top}A{RING_RADIUS} {RING_RADIUS} 0 {large} 1 {x:g} {y:g}"


def countdown(start, end, today, **words):
    """The countdown from start to end, as it stands today (before end)."""
    return Countdown(end, (end - today).days, (today - start).days / (end - start).days, **words)


@dataclass(frozen=True)
class JourneyStep:
    title: str
    state: str
    done_on: date | None = None  # the day it was done, said beside a done step (#458 D7)
    about: str = ""  # what the step is, said when it is opened while not done (#459 I1)
    ineligible: bool = False  # step 4 says 不符資格 beside its title while not done
    entries: tuple[Entry, ...] = ()  # entry cards under the about or the stamp when opened
    entries_title: str = ""  # the entry cards' small heading
    countdown: Countdown | None = None  # step 7's countdown card, in place of its about


@dataclass(frozen=True)
class JourneyCard:
    """The 現在這一步's one thing: title and why, its button (text, url), its entry cards, a
    route stop's answer card or date card; nothing to press while counting down or waiting."""

    title: str
    because: str
    button: tuple[str, str] | None = None
    entries: tuple[Entry, ...] = ()
    entries_title: str = ""  # the entry cards' small heading
    countdown: Countdown | None = None
    question: AnswerCard | None = None
    date: DateCard | None = None
    # The question's stop just finished from this card: the stamp, and 接著往下一站 this one.
    moved_on: str = ""
    # An answer card's stop as the route offers it (text, url), where the card is not shown: a
    # result page's 建議下一步.
    away: tuple[str, str] | None = None


@dataclass(frozen=True)
class NextScreening:
    """下次篩檢, from the latest life-impact record: the day and the days left, both None once
    due; and step 7's countdown card till then."""

    on: date | None
    days_left: int | None
    due: bool
    href: str  # 再做一次: the same life-impact questionnaire
    countdown: Countdown | None = None


@dataclass(frozen=True)
class CareJourney:
    steps: tuple[JourneyStep, ...]  # step 1 first
    current: int  # the 現在這一步, 1 to 7
    card: JourneyCard
    last_result: Submission | None  # the latest life-impact record, for 上次結果
    # None without a life-impact record: no day to count from, so the tile says it is not set
    # (#458 D6) while step 7 asks for one (spec #453).
    next_screening: NextScreening | None
    audiogram: AudiogramResult | None = None  # step 3 done: what opening it shows


def _hospital_entry():
    return Entry(FIND_A_HOSPITAL, reverse("qa_answer", args=[WHERE_TO_TEST]), "pin")


def _audiogram_sources():
    return (
        Entry(HOSPITAL_REPORT, reverse("audiogram_new"), "report-file", come_back=True),
        Entry(AIRPODS_SELF_TEST, reverse("audiogram_import"), "airpods"),
    )


def care_journey(user, today, done_now=None):
    """done_now: the route stop an answer on the home page's card just finished (route_answer's
    ?done=), which the card then shows stamped, its way on to the next stop."""
    route = fitting_state(user, today)
    main = get_user_state(user, today)
    life_impact = main.life_impact
    fitted_on = route.aid.fitted_on if route.fitted else None
    three_months = add_months(fitted_on, FITTING_MONTHS) if fitted_on is not None else None
    # The second IOI-HA, 3 months on from the fitting date (ADR 0074); the latest gives the day.
    ioi_ha = (
        ioi_ha_since(user, three_months).order_by("-created_at").first()
        if three_months is not None
        else None
    )
    not_needed_now = route.waiting and route.advice in NOT_NEEDED_ADVICE
    eligibility = _eligibility(route, not_needed_now)
    # Step 4: my guide opened; 輕到中度, its types and prices chapter too (grill Q22).
    guide_views = [route.viewed.get(GUIDE_PAGE)]
    if eligibility == MILD_HEARING:
        guide_views.append(route.viewed.get(TYPES_AND_PRICES))
    guide_views = [moment for moment in guide_views if moment is not None]
    # Each step's day, None while it is not done; step 7 never is, a retest only moves the
    # next one on. A 無法判讀 record leaves step 1 to do again, whatever the hearing, as
    # fitting_advice counts it as none (the owner, 2026-11-17). Steps 2 and 3 go together on
    # an audiogram (grill Q9), but one missing a frequency leaves step 3 to edit it; step 2 is
    # also done once 查詢醫療院所 is opened (spec #741's 實作中本人補充), on the earlier day.
    readable = life_impact is not None and life_impact.result.level["level"] != UNKNOWN["level"]
    audiogram_on = route.audiogram.tested_on if route.audiogram is not None else None
    searched = route.viewed.get(HOSPITAL_SEARCH)
    searched_on = timezone.localtime(searched).date() if searched is not None else None
    hospital_on = min((day for day in (audiogram_on, searched_on) if day), default=None)
    route_done = not route.waiting and route.home_stop in ROUTE_DONE_AT
    done_on = {
        1: _day(life_impact) if readable else None,
        2: hospital_on,
        3: None if route.insufficient else audiogram_on,
        4: timezone.localtime(min(guide_views)).date() if guide_views else None,
        5: fitted_on if route_done else None,
        6: _day(ioi_ha) if ioi_ha else None,
        7: None,
    }
    done = {number: day is not None for number, day in done_on.items()}

    def not_needed(number):
        return not_needed_now and number in FITTING_STEPS

    first = WEARING_FROM if route.wearing else 1
    current = next(
        (n for n in range(first, LAST_STEP) if not done[n] and not not_needed(n)), LAST_STEP
    )
    questionnaires = list(Questionnaire.objects.defined())
    life_impact_href = _life_impact_href(user, main, questionnaires)
    if life_impact is None:
        next_screening = None
    elif main.retest_due:
        next_screening = NextScreening(None, None, True, life_impact_href)
    else:
        on = main.next_suggested_date
        wait = countdown(_day(life_impact), on, today, above=NEXT_SCREENING)
        next_screening = NextScreening(on, (on - today).days, False, life_impact_href, wait)
    steps = tuple(
        _step(
            number,
            title,
            about,
            current,
            done_on[number],
            not_needed(number),
            eligibility,
            route.audiogram is None,
            next_screening,
        )
        for number, (title, about) in enumerate(
            zip(CARE_JOURNEY_STEPS, CARE_JOURNEY_ABOUT, strict=True), start=1
        )
    )
    card = _card(
        current,
        route,
        eligibility,
        today,
        fitted_on,
        three_months,
        next_screening,
        life_impact_href,
        questionnaires,
    )
    if current == 5 and done_now in ANSWER_CARDS and done_now in route.done:
        card = _done_card(done_now, route, card)
    return CareJourney(
        steps,
        current,
        card,
        life_impact,
        next_screening,
        _audiogram_result(route.audiogram) if done[3] else None,
    )


def _eligibility(route, not_needed_now):
    """不符資格's case, or None: 聽力正常 while steps 4 to 6 are 目前不需要; 輕到中度, an
    assessment suggested but the newest exam's estimate short of the threshold (ADR 0017,
    0068). Only which sentence step 4 says: the 補助站 are not folded by it (ADR 0063)."""
    if not_needed_now:
        return NORMAL_HEARING
    estimate = route.assessment
    if route.advice == FittingAdvice.RECOMMEND and estimate and estimate["status"] == "not_reached":
        return MILD_HEARING
    return None


def _step(
    number, title, about, current, done_on, not_needed, eligibility, no_audiogram, next_screening
):
    entries, entries_title, ineligible, wait = (), "", False, None
    if number == 2:
        entries = (_hospital_entry(),)
    if number == 3 and no_audiogram:
        # Spec #741 story 4, acceptance 4: without an audiogram step 3 opens to its sources.
        entries, entries_title = _audiogram_sources(), AUDIOGRAM_SOURCES
    if number == 4:
        about, entries = _guide_words(eligibility)
        ineligible = eligibility is not None
    if number == LAST_STEP:
        # What its card says (spec #741, the canvas's 5-a), without its button.
        if next_screening is None:
            about = FIRST_SCREENING_NOT_DONE
        elif next_screening.due:
            about = RETEST_TIME_UP
        else:
            about, wait = "", next_screening.countdown
    if done_on is not None:
        state = DONE
    elif not_needed:
        state = NOT_NEEDED
    else:
        state = CURRENT if number == current else LATER
    if state == DONE and number not in (2, 4):
        # A done step opens to its stamp; step 2's keeps 查詢醫療院所 (spec #741's 實作中本人
        # 補充), step 4's the way to my guide.
        entries = ()
    return JourneyStep(title, state, done_on, about, ineligible, entries, entries_title, wait)


def _guide_words(eligibility):
    """Step 4's sentence and entry card by 不符資格's case (grill Q12, the canvas)."""
    if eligibility == NORMAL_HEARING:
        return INELIGIBLE_NORMAL, ()
    if eligibility == MILD_HEARING:
        chapter = reverse("guide_chapter", args=[TYPES_AND_PRICES])
        return INELIGIBLE_MILD, (Entry(TYPES_AND_PRICES_ENTRY, chapter, "tag"),)
    return GUIDE_BECAUSE, (Entry(GUIDE_ENTRY, reverse("guide"), "guide"),)


def _audiogram_result(audiogram):
    ears = interpret(audiogram.points.all())
    return AudiogramResult(
        reverse("audiogram_detail", args=[audiogram.pk]),
        audiogram.tested_on,
        tuple(
            EarResult(label, side, ears[side]["degree"], ears[side]["pta"])
            for label, side in (("右耳", "right"), ("左耳", "left"))
        ),
    )


def _day(submission):
    return timezone.localtime(submission.created_at).date()


def _life_impact_href(user, main, questionnaires):
    # Step 1's 去做問卷, also the empty pages' 做第一份問卷 (#648), so both go to one place: the
    # one to do again, or by age; the catalogue, which recommends one, while the age is unknown.
    questionnaire = life_impact_questionnaire(user, questionnaires, main, None)
    if questionnaire is None:
        return reverse("questionnaire_list")
    return reverse("screening", args=[questionnaire.pk])


def first_questionnaire_url(user, today):
    """An empty page's 做第一份問卷 (#648: 我的紀錄, the report, the share page): where the home
    page's step 1 goes."""
    questionnaires = list(Questionnaire.objects.defined())
    return _life_impact_href(user, get_user_state(user, today), questionnaires)


def _card(
    current,
    route,
    eligibility,
    today,
    fitted_on,
    three_months,
    next_screening,
    life_impact_href,
    questionnaires,
):
    title = CARE_JOURNEY_STEPS[current - 1]
    if current == 1:
        button = (LIFE_IMPACT_BUTTON, life_impact_href)
        return JourneyCard(title, LIFE_IMPACT_BECAUSE, button=button)
    if current == 2:
        return JourneyCard(title, "", entries=(_hospital_entry(),))
    if current == 3 and route.audiogram is None:
        # Step 2 done by opening 查詢醫療院所 (spec #741 acceptance 4).
        return JourneyCard(title, "", entries=_audiogram_sources(), entries_title=AUDIOGRAM_SOURCES)
    if current == 3:
        # Step 2 is done on any audiogram, step 3 on one that can tell: here it cannot.
        edit = reverse("audiogram_edit", args=[route.audiogram.pk])
        button = ("修改這張聽力圖", edit)
        return JourneyCard(title, NEXT_STEP_REASONS["edit"], button=button)
    if current == 4:
        because, entries = _guide_words(eligibility)
        return JourneyCard(title, because, entries=entries)
    if current == 5:
        return _stop_card(route, questionnaires)
    if current == 6:
        # The canvas: counting down to 3 months worn, then its button alone (spec #741).
        if today < three_months:
            wait = countdown(fitted_on, three_months, today, below=FITTING_AGAIN_FROM)
            return JourneyCard(title, FITTING_COMPARE, countdown=wait)
        button = (IOI_HA_BUTTON, _ioi_ha_href(questionnaires))
        return JourneyCard(title, "", button=button)
    # Step 7 by the canvas (spec #741 acceptance 26).
    if next_screening is None:
        # Without a life-impact record step 7 is due: one to do first (spec #453).
        button = (LIFE_IMPACT_BUTTON, life_impact_href)
        return JourneyCard(title, FIRST_SCREENING_NOT_DONE, button=button)
    if not next_screening.due:
        return JourneyCard(title, "", countdown=next_screening.countdown)
    button = (RETEST_BUTTON_TEXT, next_screening.href)
    return JourneyCard(title, RETEST_TIME_UP, button=button)


def _ioi_ha_href(questionnaires):
    # IOI-HA from the questionnaires already read; the catalogue where it is not offered.
    ioi_ha = next((q for q in questionnaires if q.code == IOI_HA), None)
    return reverse("screening", args=[ioi_ha.pk]) if ioi_ha else reverse("questionnaire_list")


def _stop_card(route, questionnaires):
    # Spec #741 (the canvas's 照顧旅程展開): the home page's 目前這一站, past 助聽器的種類與價格
    # (ADR 0074), and its one thing. Never 記錄聽力圖, which is step 3: step 5 comes once step 3
    # is done, or from 配戴之後 for someone wearing hearing aids; never 等待補助發放, at which
    # step 5 is done (ROUTE_DONE_AT).
    stop = here_stop(replace(route, stop=route.home_stop))
    slug, aid = stop.slug, route.aid
    if slug in ANSWER_CARDS:
        question = _answer_card(slug, aid)
        return JourneyCard(stop.title, "", _way_on(slug, aid), question=question, away=stop.action)
    if slug == "before-you-go":
        return JourneyCard(stop.title, "", (BEFORE_YOU_GO_BUTTON, stop.url))
    if slug == "after-fitting":
        # Grill Q15, Q16, Q18: the date and the first IOI-HA, both needed, side by side.
        entries = (
            Entry(RECORD_FITTING_DATE, f"{stop.url}#stop-question", "calendar"),
            Entry(FIRST_IOI_HA, _ioi_ha_href(questionnaires), "clipboard", note=FIRST_IOI_HA_NOTE),
        )
        return JourneyCard(stop.title, AFTER_FITTING_WORDS, entries=entries)
    # Form 25: from when it can be done, a calendar's day, and the deadline under it; with no
    # date (no 身障補助 at a level that needs it) only what to bring.
    day = None
    if route.form_25 is not None:
        opens, closes = route.form_25
        day = DateCard(opens, FORM_25_FROM, FORM_25_BY.format(day=closes))
    return JourneyCard(stop.title, "", (FORM_25_BUTTON, stop.url), date=day)


def _answer_card(slug, aid):
    """The stop's answer card: its question form's field and choices, the kept one chosen."""
    question, icon, words = ANSWER_CARDS[slug]
    form_class = STOP_QUESTIONS[slug][0]
    name = next(iter(form_class.base_fields))
    kept = "" if aid is None else str(getattr(aid, name))
    choices = tuple(
        Choice(str(value), *words[str(value)], chosen=str(value) == kept)
        for value, _ in form_class.base_fields[name].choices
    )
    return AnswerCard(slug, name, question, icon, choices)


def _way_on(slug, aid):
    """Under an answer that leaves the stop to do: where to go on (text, url), else None."""
    if aid is None:
        return None
    if slug == "assessment" and aid.certificate == Certificate.APPLYING:
        hospitals = reverse("guide_chapter", args=["assessment"]) + "#hospitals-title"
        return FIND_AN_ASSESSMENT_HOSPITAL, hospitals
    if slug == "form-9" and aid.form_9_done is False:
        return FORM_9_STEPS, reverse("guide_chapter", args=["form-9"])
    if slug == "notice" and aid.notice_received is True:
        # The ears and the level, asked on my guide where the notice is the 目前這一站.
        return RECORD_THE_NOTICE, f"{reverse('guide')}#stop-notice"
    if slug == "notice" and aid.notice_received is False:
        return TYPES_AND_PRICES_FIRST, reverse("guide_chapter", args=[TYPES_AND_PRICES])
    return None


def _done_card(slug, route, card):
    """Grill Q13: the answer card of the stop just finished, stamped, and 接著往下一站 the stop
    card is at now, pressed to move on."""
    title = here_stop(replace(route, stop=slug)).title
    question = _answer_card(slug, route.aid)
    moved_on = NEXT_STOP_NAMES.get(route.home_stop, card.title)
    return JourneyCard(title, "", question=question, moved_on=moved_on)


def next_step(user, today):
    """The result pages' 建議下一步 (ADR 0044): the 現在這一步's card, its button (an answer card's
    stop, the route's) or its entry card; without either sharing the report, printing it once
    any link was ever made (#261)."""
    card = care_journey(user, today).card
    button = card.button or card.away
    if button is not None:
        text, href = button
        return NextStep(HomeCard(card.title, href), text, None)
    if card.entries:
        # Steps 2 and 4 have one each; 配戴之後's first of two is its date (#745).
        entry = card.entries[0]
        return NextStep(HomeCard(card.title, entry.href), entry.text, None)
    if user.report_shares.exists():
        print_card = HomeCard("印聽力報告給醫師看", reverse("health_report"))
        return NextStep(print_card, "去印報告", "print")
    share_card = HomeCard("分享報告給家人", reverse("share_report"))
    return NextStep(share_card, "去分享", "share")
