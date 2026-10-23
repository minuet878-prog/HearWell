"""Where a user stands on the 選配路線 (GLOSSARY, spec #257): the 目前這一站 and the records
behind it. My guide and the home page's 建議下一步 both read it, so they never disagree."""

from dataclasses import dataclass

from screening.audiogram import assessment_estimate, recommends_fitting_assessment
from screening.questionnaires.ioi_ha import CODE as IOI_HA

# The route's first stop, recording an audiogram; the other stops are the guide's chapters.
AUDIOGRAM = "audiogram"


@dataclass(frozen=True)
class FittingState:
    latest: object | None  # the newest submission of an offered questionnaire
    audiogram: object | None  # the newest audiogram, its points prefetched
    wearing: bool
    fitting: bool | None  # recommends_fitting_assessment; None without an audiogram too
    threshold: dict | None  # assessment_estimate, without an audiogram None
    stop: str | None  # AUDIOGRAM or a chapter slug; None when no stop applies

    @property
    def insufficient(self):
        # 資料不足: the latest audiogram cannot tell whether to suggest an assessment.
        return self.stop == AUDIOGRAM and self.audiogram is not None


def fitting_state(user):
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
    stop = _stop(wearing, audiogram, fitting, threshold)
    return FittingState(latest, audiogram, wearing, fitting, threshold, stop)


def _stop(wearing, audiogram, fitting, threshold):
    # Spec #257 Q18, from the top. Wearing comes first: choosing hearing aids is behind them.
    if wearing:
        return "after-fitting"
    if audiogram is None or fitting is None:
        return AUDIOGRAM
    if threshold["status"] == "reached":
        return "assessment"  # the certificate comes before form 9's subsidy
    if fitting:
        return "before-you-go"
    return None
