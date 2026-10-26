import math

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, prefetch_related_objects
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from screening.main_flow import home_more
from screening.models import Answer, Category, NormGroup, Questionnaire, Submission
from screening.questionnaires import hhia_s, hhie_s
from screening.questionnaires.definition import AVERAGE, NORM, SUBSCALES
from screening.questionnaires.ioi_ha import ITEM_CHOICES as IOI_HA_CHOICES
from screening.questionnaires.ioi_ha import SCALE_ENDS as IOI_HA_SCALE_ENDS
from screening.questionnaires.ssq12_tw import CODE as SSQ12
from screening.scoring import (
    IOI_HA_BELOW_NORM_NOTES,
    IOI_HA_ITEM_NAMES,
    IOI_HA_NORMS,
    NORM_COMPARISON_TEXT,
    NORM_VERSUS_TEXT,
    UNKNOWN,
    compare_to_norm,
    get_advice,
    max_score,
)
from screening.views.common import health_data_page
from screening.views.my_hearing import TREND_STATUS_TEXT, shows_wearing_comparison


def score_bar(definition, score, level):
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


def score_gauge(bar):
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


def has_subscores(answers):
    # Only items marked emotional or social make subscores; THI has none (spec #208 Q5). Reads
    # the answers already loaded with their questions, no query of its own.
    return any(answer.question.category != Category.NONE for answer in answers)


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
                "show_comparison": shows_wearing_comparison(request.user, submission.questionnaire),
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
            "has_subscores": has_subscores(answers),
            "max_score": max_score(submission.questionnaire.code),
            "classified_score_text": classified_score["text"],
            "classified_score_color": classified_score["color"],
            "score_bar": score_bar(
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
            "show_comparison": shows_wearing_comparison(request.user, submission.questionnaire),
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


def ioi_ha_summary(submission):
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
