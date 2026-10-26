import math

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from screening.main_flow import home_more
from screening.models import Submission
from screening.questionnaires.results import _ioi_ha_items
from screening.scoring import NORM_COMPARISON_TEXT
from screening.views.common import health_data_page
from screening.views.my_hearing import TREND_STATUS_TEXT, _shows_wearing_comparison


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
    result = submission.result
    # #304 (ADR 0023): the home page's 建議下一步, by the user's state now, not this record's.
    next_step, _ = home_more(request.user, timezone.localdate())
    shared = {
        "submission": submission,
        "wearing_text": TREND_STATUS_TEXT[submission.wearing_hearing_aid],
        "show_comparison": _shows_wearing_comparison(request.user, submission.questionnaire),
        "next_step": next_step,
    }
    return render(request, result.page_template, shared | result.page_context())


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
