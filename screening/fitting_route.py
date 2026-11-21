"""Where a user stands on the 選配路線 (GLOSSARY, spec #291): each stop's state, the 目前這一站
and the records behind them, kept in one place for every page that shows the route or points
along it."""

import calendar
from dataclasses import dataclass
from datetime import date

from screening.audiogram import (
    FittingAdvice,
    assessment_estimate,
    fitting_advice,
    readable_for_aid_wearer,
)
from screening.models import (
    AidAndSubsidy,
    AidLevel,
    Audiogram,
    AudiogramSource,
    Certificate,
    GuideChapterView,
    Submission,
    Subsidy,
)
from screening.questionnaires.ioi_ha import CODE as IOI_HA

# The route's first stop, recording an audiogram; the other stops are the guide's chapters,
# but for 等待核定公文 and 等待補助發放, which have none.
AUDIOGRAM = "audiogram"
# The nine stops in route order (spec #291), 去找聽力師之前 after the notice (ADR 0074).
STOPS = (
    AUDIOGRAM,
    "assessment",
    "form-9",
    "notice",
    "before-you-go",
    "types-and-prices",
    "after-fitting",
    "form-25",
    "payout",
)
# Someone wearing hearing aids looks for the 目前這一站 from 配戴之後 on (spec #291 Q5, Q9).
WEARING_STOPS = STOPS[STOPS.index("after-fitting") :]
# 看過指引頁 (spec #741): my guide opened signed in, kept as a chapter view of its own.
GUIDE_PAGE = "guide"
# 點過查詢醫療院所 (spec #741's 實作中本人補充): the 照顧旅程's step 2 opened signed in, kept the
# same way; the Q&A answer it opens is care_journey's WHERE_TO_TEST.
HOSPITAL_SEARCH = "find-a-hospital"
# The stop the home page passes by (ADR 0074): a chapter to read, so the 照顧旅程 shows the one
# after it while my guide is still here.
HOME_SKIPS = "types-and-prices"
# The stops a 看過 makes 已完成 (spec #291 Q4); the other chapters are done by an answer.
DONE_BY_VIEWING = frozenset({"before-you-go", "types-and-prices"})
# The certificate answers that finish 身障鑑定與鑑定醫院 (spec #291 Q2); 還沒有 stays.
CERTIFICATE_DONE = frozenset({Certificate.YES, Certificate.NO_SUBSIDY})
# The 補助站 (GLOSSARY, ADR 0063): folded away until the person answers that they have a
# certificate or are applying, or answers one of them; 沒有 keeps them folded.
SUBSIDY_STOPS = frozenset({"form-9", "notice", "form-25", "payout"})
CERTIFICATE_UNFOLDS = frozenset({Certificate.YES, Certificate.APPLYING})
# Bought paying otherwise, as 配戴之後 asks (spec #291 acceptance 15).
BOUGHT_OTHERWISE = frozenset({"form-25", "payout"})
# The results that suggest no assessment yet, so the route waits (spec #693).
WAITING_ADVICE = frozenset(
    {FittingAdvice.NORMAL, FittingAdvice.TRACK, FittingAdvice.QUESTIONNAIRE_FIRST}
)
REAPPLY_MONTHS = 48  # 身障補助 again 4 years on; #284 leaves out under-12s' 2 years


def add_months(start, months):
    # A day the later month lacks becomes its last day: 1/31 plus a month is 2/28.
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def form_25_window(fitted_on):
    """(from, by): form 25 is done a month to three months after the fitting date, both days
    included (#284 Q7)."""
    return add_months(fitted_on, 1), add_months(fitted_on, 3)


def _fitted(aid):
    return aid is not None and aid.fitted_on is not None


@dataclass(frozen=True)
class FittingState:
    latest: Submission | None  # the newest submission of an offered questionnaire
    audiogram: Audiogram | None  # the newest audiogram, its points prefetched
    wearing: bool
    advice: FittingAdvice | None  # 建議評估選配 (fitting_advice); None without an audiogram
    # assessment_estimate of the newest audiogram, for its ears' 四頻平均 on the 選配 meters;
    # the 身障鑑定門檻 reads `assessment` (an exam's). Without an audiogram None.
    threshold: dict | None
    # 資料不足: the latest audiogram cannot tell whether to suggest an assessment. Shown even
    # when another stop comes first (wearing), but then it is not the 目前這一站.
    insufficient: bool
    done: frozenset  # the 已完成 stops' slugs
    not_applicable: frozenset  # the 不適用 stops' slugs, which 您在這裡 passes by
    stop: str | None  # one of STOPS; None when no stop applies
    today: date  # the day the route is judged on, for its dated rules
    aid: AidAndSubsidy | None  # the user's 助聽器與補助資料, None before they answer any
    # Q7 (spec #693): not wearing hearing aids and no assessment to suggest yet, the route
    # waits until the user starts on a stop; the 照顧旅程's 目前不需要 is part of it (ADR 0067).
    waiting: bool
    subsidy_shown: bool  # the 補助站 on the route (subsidy_stops_shown)
    # 身障鑑定門檻 (ADR 0017) from the newest hearing exam only (ADR 0068): its estimate and
    # the exam, or both None when there is no exam (a self test alone estimates nothing).
    assessment: dict | None
    assessment_exam: Audiogram | None
    home_stop: str | None  # the 目前這一站 on the home page, which passes by HOME_SKIPS
    # 看過: each chapter the user opened signed in, GUIDE_PAGE among them, and when first.
    viewed: dict

    @property
    def stops(self):
        """The stops on the route, in order: five while the 補助站 are folded, else nine."""
        return stops_on_route(self.subsidy_shown)

    @property
    def form_25_on_route(self):
        """Form 25 shown and not 不適用: the route has a line on to it, and a date."""
        return self.subsidy_shown and "form-25" not in self.not_applicable

    @property
    def fitted(self):
        """The user filled in when they started wearing their current pair."""
        return _fitted(self.aid)

    @property
    def has_records(self):
        """A questionnaire, an audiogram, or any 助聽器與補助資料 to place the user on the route."""
        answered = self.aid is not None and not self.aid.unanswered
        return self.audiogram is not None or self.latest is not None or answered

    @property
    def form_25(self):
        """form_25_window of the fitting date; None without the date, without 身障補助 or when
        form 25 is 不適用 or folded away. 要做二十五號表 (spec #291): 身障補助 at a level above
        簡易型 or 不知道."""
        if not self.fitted or not self.aid.uses_disability_subsidy:
            return None
        if not self.form_25_on_route:
            return None
        return form_25_window(self.aid.fitted_on)

    @property
    def reapply_on(self):
        """The day someone who bought with 身障補助 can apply again: four years after the
        fitting date (#284 acceptance 17); None without the subsidy or the date."""
        if not self.fitted or not self.aid.uses_disability_subsidy:
            return None
        return add_months(self.aid.fitted_on, REAPPLY_MONTHS)


def latest_submission(user):
    """The newest submission of an offered questionnaire, None before one."""
    return (
        user.submissions.defined()
        .select_related("questionnaire")
        .order_by("-created_at", "-id")
        .first()
    )


def keep_view(user, chapter):
    """看過 (spec #291 acceptance 4): the first time stays; signed out or before agreeing to the
    privacy notice that covers it, nothing is kept."""
    if user.is_authenticated and user.has_consented():
        GuideChapterView.objects.get_or_create(user=user, chapter=chapter)


def _ioi_ha_since(user, aid):
    # Taken on the fitting date or later (ADR 0074), as the 照顧旅程 counts it.
    since = user.submissions.filter(questionnaire__code=IOI_HA, created_at__date__gte=aid.fitted_on)
    return since.exists()


def wearing_hearing_aids(latest, aid):
    """Whether the user wears hearing aids, from their latest_submission and their
    AidAndSubsidy (None before any)."""
    # IOI-HA saves no wearing answer, but only people wearing hearing aids take it (#220 M16).
    answered = latest is not None and (
        latest.wearing_hearing_aid is True or latest.questionnaire.code == IOI_HA
    )
    # A fitting date the user filled in counts as wearing them too (#284 default 3).
    return answered or _fitted(aid)


def fitting_state(user, today):
    audiogram = user.audiograms.prefetch_related("points").first()
    latest = latest_submission(user)
    aid = AidAndSubsidy.for_user(user)
    wearing = wearing_hearing_aids(latest, aid)
    advice = threshold = None
    insufficient = False
    if audiogram is not None:
        points = list(audiogram.points.all())
        # Imported here: main_flow imports this module for add_months.
        from screening.main_flow import get_user_state

        advice = fitting_advice(points, get_user_state(user, today).life_impact)
        threshold = assessment_estimate(points)
        # Someone wearing hearing aids is not judged by 建議評估選配, so their audiogram tells
        # as it did before it (spec #693 acceptance 12).
        if wearing:
            insufficient = not readable_for_aid_wearer(points)
        else:
            insufficient = advice == FittingAdvice.UNKNOWN
    # ADR 0068: a self test estimates no 身障鑑定; the newest exam does, the newest audiogram
    # or an older one.
    exam = audiogram
    if audiogram is not None and audiogram.is_self_test:
        exams = user.audiograms.filter(source=AudiogramSource.EXAM).prefetch_related("points")
        exam = exams.first()
    assessment = assessment_estimate(list(exam.points.all())) if exam is not None else None
    viewed = dict(user.guide_views.values_list("chapter", "first_viewed_at"))
    done = set(viewed) & DONE_BY_VIEWING
    if audiogram is not None and not insufficient:
        done.add(AUDIOGRAM)  # an audiogram that can tell; one missing a frequency is not done
    if aid is not None and aid.certificate in CERTIFICATE_DONE:
        done.add("assessment")
    if aid is not None and aid.form_9_done:
        done.add("form-9")
    if aid is not None and aid.notice_received and aid.approved_ears and aid.level:
        done.add("notice")  # #294: 收到了 is done only with both of the notice's answers
    if _fitted(aid) and (aid.notice_received or aid.subsidy) and _ioi_ha_since(user, aid):
        # #295, spec #291 Q16: the fitting date, and without the notice the subsidy answered;
        # ADR 0074: and a first IOI-HA from that day on.
        done.add("after-fitting")
    if aid is not None and aid.form_25_done:
        done.add("form-25")  # #296; 等待補助發放 is never done
    shown = subsidy_stops_shown(aid)
    # 不適用 only among the 補助站 shown (ADR 0063): folded away, none is marked anything.
    not_applicable = not_applicable_stops(aid) if shown else frozenset()
    done -= not_applicable  # a stop is never both: 不適用 wins (#291 review)
    if not shown:
        done -= SUBSIDY_STOPS  # folded away, a 補助站 is neither done nor here
    # Q7: not suggested an assessment (spec #693), the route waits until the user starts on a
    # stop; only an answer on the route starts it, a chapter viewed does not (spec #693 Q9).
    started = aid is not None and not aid.unanswered
    waiting = not wearing and advice in WAITING_ADVICE and not started
    passed = done | not_applicable | (frozenset() if shown else SUBSIDY_STOPS)
    stop = _stop(wearing, passed, waiting)
    home_stop = _stop(wearing, passed | {HOME_SKIPS}, waiting)
    return FittingState(
        latest,
        audiogram,
        wearing,
        advice,
        threshold,
        insufficient,
        frozenset(done),
        not_applicable,
        stop,
        today,
        aid,
        waiting,
        shown,
        assessment,
        exam,
        home_stop,
        viewed,
    )


def stops_on_route(subsidy_shown):
    """The route's stops in order, the 補助站 only when shown."""
    return tuple(slug for slug in STOPS if subsidy_shown or slug not in SUBSIDY_STOPS)


def subsidy_declined(aid):
    """沒有 to the certificate question (aid, or None): the 補助站 stay folded, whatever else
    is answered, and their chapters do not ask their questions."""
    return aid is not None and aid.certificate == Certificate.NO_SUBSIDY


def subsidy_stops_shown(aid):
    """Whether the 補助站 are on the route (ADR 0063): 有 or 正在申請 to the certificate
    question, or, that unanswered, an answer to one of them or 用身障補助 at 配戴之後."""
    if aid is None or subsidy_declined(aid):
        return False
    if aid.certificate in CERTIFICATE_UNFOLDS:
        return True
    answered = (aid.form_9_done, aid.notice_received, aid.form_25_done)
    return any(answer is not None for answer in answered) or aid.subsidy == Subsidy.DISABILITY


def not_applicable_stops(aid):
    """The 補助站 that do not apply by the user's 助聽器與補助資料 (aid, or None), shown or
    not: a chapter of one asks nothing at its foot; the route marks them only while shown."""
    not_applicable = set()
    if aid is not None and aid.subsidy == Subsidy.OTHER:
        not_applicable |= BOUGHT_OTHERWISE  # #296: no 身障補助 to verify or pay out
    if aid is not None and aid.level == AidLevel.BASIC:
        not_applicable.add("form-25")  # #296: 簡易型 is paid out without form 25
    return frozenset(not_applicable)


def _stop(wearing, passed, waiting):
    # Spec #291 (in place of #284's and #257 Q18's rules): the first stop neither done nor
    # 不適用, from 配戴之後 on for someone wearing hearing aids; none while the route waits.
    if wearing:
        stops = WEARING_STOPS
    elif waiting:
        return None
    else:
        stops = STOPS
    return next((slug for slug in stops if slug not in passed), None)
