"""Where a user stands on the 選配路線 (GLOSSARY, spec #257): the 目前這一站 and the records
behind it, kept in one place for every page that shows the route or points along it."""

from dataclasses import dataclass
from datetime import date

from screening.audiogram import assessment_estimate, recommends_fitting_assessment
from screening.models import AidAndSubsidy, Audiogram, Submission
from screening.questionnaires.ioi_ha import CODE as IOI_HA

# The route's first stop, recording an audiogram; the other stops are the guide's chapters.
AUDIOGRAM = "audiogram"


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
    fitting = threshold = None
    if audiogram is not None:
        points = list(audiogram.points.all())
        fitting = recommends_fitting_assessment(points)
        threshold = assessment_estimate(points)
    aid = AidAndSubsidy.objects.filter(user=user).first()
    certified = aid is not None and aid.has_certificate is True
    stop = _stop(wearing, certified, audiogram, fitting, threshold)
    return FittingState(latest, audiogram, wearing, fitting, threshold, stop, today, aid)


def _stop(wearing, certified, audiogram, fitting, threshold):
    # Spec #284 (in place of #257 Q18), from the top. Wearing comes first: choosing hearing
    # aids is behind them. A certificate is next, with or without an audiogram (#284 Q6).
    if wearing:
        return "after-fitting"
    if certified:
        return "form-9"
    if audiogram is None or fitting is None:
        return AUDIOGRAM
    if threshold["status"] == "reached":
        return "assessment"  # the certificate comes before form 9's subsidy
    if fitting:
        return "before-you-go"
    return None
