from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.utils import timezone

from screening.main_flow import get_user_state
from screening.models import Answer, NormGroup, shared_days
from screening.questionnaires.definition import LEVEL
from screening.questionnaires.ioi_ha import CODE as IOI_HA
from screening.scoring import (
    IOI_HA_ITEM_NAMES,
    IOI_HA_NORMS,
    NORM_COMPARISON_TEXT,
    compare_to_norm,
    since_last_text,
)
from screening.views.common import health_data_page


def _item_scores(submission):
    return {
        answer.question.question_number: answer.score
        for answer in submission.answers.select_related("question")
    }


def _ioi_ha_chart(records):
    # records: this user's IOI-HA, newest first. Grid row 1 is score 5, row 5 is score 1.
    latest = records[0]
    grouped = latest.norm_group != NormGroup.UNGROUPED
    previous = records[1] if grouped and len(records) > 1 else None
    if previous is not None and previous.norm_group != latest.norm_group:
        previous = None  # another group's band would mislead
    latest_scores = _item_scores(latest)
    previous_scores = _item_scores(previous) if previous else {}
    columns = []
    for number, name in IOI_HA_ITEM_NAMES.items():
        score = latest_scores[number]
        column = {"name": name, "latest_row": 6 - score}
        text = f"{name}：最近一次 {score} 分"
        if previous:
            column["previous_row"] = 6 - previous_scores[number]
            text += f"，上一次 {previous_scores[number]} 分"
        if grouped:
            lower, upper = IOI_HA_NORMS[latest.norm_group][number]
            column["band_rows"] = f"{6 - upper} / {7 - lower}"
            comparison = compare_to_norm(latest.norm_group, number, score)
            text += f"，常模 {lower} 到 {upper} 分，{NORM_COMPARISON_TEXT[comparison]}"
        column["text"] = text
        columns.append(column)
    return {"latest": latest, "previous": previous, "grouped": grouped, "columns": columns}


TREND_STATUS_TEXT = {False: "沒戴助聽器", True: "有戴助聽器", None: "助聽器未記錄"}
# 「和上一次比」's extra line when the two records were worn differently (ticket #214). A
# life-impact tab never shows one: it compares records worn the same way.
WEARING_CHANGE_TEXT = {
    (False, True): "上次沒戴、這次有戴助聽器。",
    (True, False): "上次有戴、這次沒戴助聽器。",
}
# Legend order, the template's shape for each status (spec 4b) and its name.
TREND_LEGEND = (
    (False, "unaided", "沒戴助聽器"),
    (True, "aided", "有戴助聽器"),
    (None, "unrecorded", "未記錄"),
)


def _trend_chart(records, since_last):
    # records: one tab's records (HHIE-S, THI), newest first; since_last: the page's
    # 「和上一次比」 or None.
    # React draws only the chart itself, so the text around it is on the page from the start
    # and nothing below moves when it arrives. The wording is fixed by spec
    # phase9_ui_refresh_2_data.md 4.2.
    latest = records[0]
    definition = latest.questionnaire.definition
    wearing = latest.wearing_hearing_aid
    status = TREND_STATUS_TEXT[wearing]
    if since_last is not None:
        change = None  # 「和上一次比」 above the chart says it (decision 2026-10-22, #162)
    elif len(records) == 1:
        # THI is not a screening (GLOSSARY: 篩檢問卷 is not every questionnaire).
        change = f"再做一次{'篩檢' if definition.life_impact else ''}，就能看到分數的變化。"
    elif wearing is None:
        change = "這筆沒有記錄助聽器，不和其他紀錄比較。"
    else:
        change = f"這是第一筆{status}的紀錄。"
    statuses = {r.wearing_hearing_aid for r in records}
    return {
        "latest": latest,
        "status": status,
        "change": change,
        "legend": [
            {"shape": shape, "text": text}
            for value, shape, text in TREND_LEGEND
            if value in statuses
        ],
        # Top band first, as stacked in the chart (phase9_ui_refresh_3_structure.md 4.5).
        "levels": [
            {
                "code": level,
                "text": text,
                "color": definition.color(level),
                "shade": definition.shade(level),
            }
            for _, text, level in reversed(definition.thresholds)
        ],
    }


def shows_wearing_comparison(user, questionnaire):
    # The 「比較戴與不戴助聽器」 entry on 我的紀錄 and the result pages (ticket #186): only once
    # this questionnaire has comparable records both with and without a hearing aid.
    comparison = questionnaire.definition.comparison
    if comparison is None:
        return False
    comparable = comparison.records(user.submissions.filter(questionnaire=questionnaire))
    return (
        comparable.filter(wearing_hearing_aid=True).exists()
        and comparable.filter(wearing_hearing_aid=False).exists()
    )


@login_required
@health_data_page
def my_hearing(request):
    # SADL's satisfaction score reads submission.answers directly (models/submissions.py), so it
    # needs its own prefetch: with_scores() only annotates the LEVEL/AVERAGE aggregates.
    answers = Answer.objects.select_related("question")
    submissions = list(
        request.user.submissions.defined()
        .select_related("questionnaire")
        .prefetch_related(Prefetch("answers", queryset=answers))
        .with_scores()
    )
    if not submissions:
        # Ticket #270 (ADR 0019): opened plainly with only audiograms, show those instead of an
        # empty page; the switch's 問卷 link (view=questionnaires) always stays here.
        if request.GET.get("view") != "questionnaires" and request.user.audiograms.exists():
            return redirect("audiogram_list")
        return render(request, "screening/my_hearing.html", {"submissions": []})
    # One tab per questionnaire this user has answered, in questionnaire order (HHIE-S first).
    questionnaires = sorted({s.questionnaire for s in submissions}, key=lambda q: q.id)
    # Default: the newest record's questionnaire; an unknown or empty choice falls back to it.
    current = next(
        (q for q in questionnaires if q.code == request.GET.get("questionnaire")),
        submissions[0].questionnaire,
    )
    records = [s for s in submissions if s.questionnaire_id == current.id]
    # Records sharing a Taipei date with another of this tab show their time too
    # (spec phase9_ui_refresh_2_data.md 4.3).
    days = shared_days(s.created_at for s in records)
    same_day = {s.id for s in records if timezone.localdate(s.created_at) in days}
    # Ticket #162: the same retest reminder as the home page (ADR 0010).
    user_state = get_user_state(request.user, today=timezone.localdate())
    # Ticket #162: a life-impact tab compares its newest record with the one before it worn
    # the same way, as the trend chart does (decision 2026-10-22). Ticket #214: another graded
    # tab (THI) compares it with the record just before, whatever was worn (ADR 0016).
    since_last = None
    if current.definition.result == LEVEL:
        latest = records[0]
        if current.definition.life_impact:
            previous = latest.previous_same_wearing(records[1:])
        else:
            previous = records[1] if len(records) > 1 else None
        if previous is not None:
            since_last = {
                "latest": latest,
                "previous": previous,
                "text": since_last_text(latest.total_answer_score - previous.total_answer_score),
                "wearing_change": WEARING_CHANGE_TEXT.get(
                    (previous.wearing_hearing_aid, latest.wearing_hearing_aid)
                ),
            }
    return render(
        request,
        "screening/my_hearing.html",
        {
            "submissions": records,
            "same_day": same_day,
            "questionnaires": questionnaires,
            "current": current,
            "user_state": user_state,
            "since_last": since_last,
            "show_comparison": shows_wearing_comparison(request.user, current),
            "saved_comparison": request.user.report_comparisons.filter(questionnaire=current)
            .select_related("unaided", "aided")
            .first(),
            "ioi_ha_chart": _ioi_ha_chart(records) if current.code == IOI_HA else None,
            "trend_chart": (
                _trend_chart(records, since_last) if current.definition.trend_chart else None
            ),
        },
    )
