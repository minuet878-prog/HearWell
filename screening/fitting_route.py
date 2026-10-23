"""Where a user stands on the 選配路線 (GLOSSARY, spec #257): the 目前這一站 and the records
behind it, kept in one place for every page that shows the route or points along it."""

import calendar
from dataclasses import dataclass
from datetime import date

from screening.audiogram import assessment_estimate, recommends_fitting_assessment
from screening.models import AidAndSubsidy, AidLevel, Audiogram, Submission, Subsidy
from screening.questionnaires.ioi_ha import CODE as IOI_HA

# The route's first stop, recording an audiogram; the other stops are the guide's chapters.
AUDIOGRAM = "audiogram"
# 要做二十五號表 (#284 Q7): 身障補助 at these levels; 不知道 counts as one of them.
FORM_25_LEVELS = (AidLevel.MID, AidLevel.ADVANCED, AidLevel.CROS, AidLevel.UNKNOWN)
REAPPLY_MONTHS = 48  # 身障補助 again 4 years on; #284 leaves out under-12s' 2 years


def add_months(start, months):
    # A day the later month lacks becomes its last day: 1/31 plus a month is 2/28.
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _form_25(aid):
    """(from, by): form 25 is done a month to three months after the fitting date, both days
    included (#284 Q7); None for someone who does not have to do it or gave no date."""
    if aid is None or aid.fitted_on is None:
        return None
    if aid.subsidy != Subsidy.DISABILITY or aid.level not in FORM_25_LEVELS:
        return None
    return add_months(aid.fitted_on, 1), add_months(aid.fitted_on, 3)


@dataclass(frozen=True)
class FittingState:
    latest: Submission | None  # the newest submission of an offered questionnaire
    audiogram: Audiogram | None  # the newest audiogram, its points prefetched
    wearing: bool
    fitting: bool | None  # recommends_fitting_assessment; None without an audiogram too
    threshold: dict | None  # assessment_estimate, without an audiogram None
    stop: str | None  # AUDIOGRAM or a chapter slug; None when no stop applies
    today: date  # the day the route is judged on, for its dated rules
    aid: AidAndSubsidy | None  # the user's 助聽器與補助資料, None before they fill it in

    @property
    def form_25(self):
        """(from, by) for someone who has to do form 25 and gave a fitting date, else None."""
        return _form_25(self.aid)

    @property
    def reapply_on(self):
        """The day someone who bought with 身障補助 can apply again: four years after the
        fitting date (#284 acceptance 17); None without the subsidy or the date."""
        aid = self.aid
        if aid is None or aid.fitted_on is None or aid.subsidy != Subsidy.DISABILITY:
            return None
        return add_months(aid.fitted_on, REAPPLY_MONTHS)

    @property
    def insufficient(self):
        # 資料不足: the latest audiogram cannot tell whether to suggest an assessment. Shown
        # even when another stop comes first (wearing), but then it is not the 目前這一站.
        return self.audiogram is not None and self.fitting is None


def fitting_state(user, today):
    audiogram = user.audiograms.prefetch_related("points").first()
    latest = (
        user.submissions.defined()
        .select_related("questionnaire")
        .order_by("-created_at", "-id")
        .first()
    )
    # IOI-HA saves no wearing answer, but only people wearing hearing aids take it (#220 M16).
    wearing = latest is not None and (
        latest.wearing_hearing_aid is True or latest.questionnaire.code == IOI_HA
    )
    aid = AidAndSubsidy.objects.filter(user=user).first()
    # A fitting date the user filled in counts as wearing them too (#284 default 3).
    wearing = wearing or (aid is not None and aid.fitted_on is not None)
    fitting = threshold = None
    if audiogram is not None:
        points = list(audiogram.points.all())
        fitting = recommends_fitting_assessment(points)
        threshold = assessment_estimate(points)
    certified = aid is not None and aid.has_certificate is True
    form_25 = _form_25(aid)
    due = form_25 is not None and form_25[0] <= today <= form_25[1]
    stop = _stop(wearing, due, certified, audiogram, fitting, threshold)
    return FittingState(latest, audiogram, wearing, fitting, threshold, stop, today, aid)


def _stop(wearing, form_25_due, certified, audiogram, fitting, threshold):
    # Spec #284 (in place of #257 Q18), from the top. Wearing comes first: choosing hearing
    # aids is behind them. A certificate is next, with or without an audiogram (#284 Q6).
    if wearing:
        return "form-25" if form_25_due else "after-fitting"
    if certified:
        return "form-9"
    if audiogram is None or fitting is None:
        return AUDIOGRAM
    if threshold["status"] == "reached":
        return "assessment"  # the certificate comes before form 9's subsidy
    if fitting:
        return "before-you-go"
    return None
