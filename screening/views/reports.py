from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.views.decorators.http import require_http_methods

from screening import models
from screening.main_flow import get_user_state
from screening.models import Answer, Questionnaire, User
from screening.questionnaires.results import AverageResult, GradedResult, NormResult, SubscaleResult
from screening.scoring import get_advice, max_score
from screening.views.audiograms import audiogram_context
from screening.views.common import health_data_page

REPORT_RECENT = 5  # history rows per questionnaire on the health report


def _report_context(user):
    # One builder for the owner's report and the family's copy (rule 10: same scoring path).
    # Answers are prefetched so SADL's per-record satisfaction (#172) reads them once, not once
    # per record shown.
    answers = Answer.objects.select_related("question").order_by("question__question_number")
    submissions = list(
        user.submissions.defined()
        .select_related("questionnaire")
        .prefetch_related(Prefetch("answers", queryset=answers))
        .with_scores()
    )
    by_questionnaire = {}
    for submission in submissions:  # newest first
        if submission.questionnaire.definition.result is GradedResult:
            by_questionnaire.setdefault(submission.questionnaire, []).append(submission)
    comparisons = list(
        user.report_comparisons.filter(questionnaire__in=Questionnaire.objects.defined())
        .select_related("questionnaire", "unaided__questionnaire", "aided__questionnaire")
        .prefetch_related("unaided__answers__question", "aided__answers__question")
        .order_by("questionnaire_id")
    )
    # #90: each saved comparison is shown with its own questionnaire's part.
    comparison_for = {comparison.questionnaire_id: comparison for comparison in comparisons}
    sections = [
        {
            "questionnaire": questionnaire,
            "latest": records[0],
            "count": len(records),
            "recent": records[:REPORT_RECENT],
            "max_score": max_score(questionnaire.code),
            "advice": get_advice(records[0].result.level["level"], questionnaire.code),
            "comparison": comparison_for.get(questionnaire.id),
        }
        for questionnaire, records in sorted(by_questionnaire.items(), key=lambda kv: kv[0].id)
    ]
    ssq_records = [s for s in submissions if s.questionnaire.definition.result is AverageResult]
    sadl_records = [s for s in submissions if s.questionnaire.definition.result is SubscaleResult]
    context = {
        "comparisons": comparisons,
        "ssq_comparison": next(
            (c for c in comparisons if c.questionnaire.definition.result is AverageResult), None
        ),
        "ssq_latest": ssq_records[0] if ssq_records else None,
        "ssq_recent": ssq_records[:REPORT_RECENT],
        "sadl_latest": sadl_records[0] if sadl_records else None,
        "sadl_recent": sadl_records[:REPORT_RECENT],
        "sections": [s for s in sections if s["questionnaire"].definition.life_impact],
        # Graded but not life impact (ADR 0016): THI, in its own part with no subscores,
        # answers or comparison (spec #208 Q5, Q9).
        "tinnitus_sections": [s for s in sections if not s["questionnaire"].definition.life_impact],
        "recent_limit": REPORT_RECENT,
        "today": timezone.localdate(),
    }
    ioi_ha = next((s for s in submissions if s.questionnaire.definition.result is NormResult), None)
    if ioi_ha:
        context["ioi_ha"] = ioi_ha.result.norm_summary
    audiogram = user.audiograms.prefetch_related("points").first()
    if audiogram:
        context.update(audiogram_context(audiogram))
    context["has_records"] = bool(submissions or audiogram)
    return context


@login_required
@health_data_page
def health_report(request):
    # Spec phase8_c3_report.md: only results the site already shows, laid out for printing.
    context = _report_context(request.user)
    # #287: the owner's report only; the family's copy shares the template but not this.
    aid = models.AidAndSubsidy.for_user(request.user)
    context["aid_report_text"] = aid.report_text if aid else ""
    return render(request, "screening/health_report.html", context)


@login_required
@health_data_page
def share_report(request):
    # #193: what the family will see, then one press makes the link; only the user's own link.
    user = request.user
    context = {
        "has_records": user.submissions.exists() or user.audiograms.exists(),
        "share": user.report_shares.active().first(),
    }
    return render(request, "screening/share_report.html", context)


@login_required
@require_http_methods(["POST"])
def report_share_create(request):
    # Spec phase8_c1_family_share.md: only after the explicit confirm, one live link at most.
    user = request.user
    has_records = user.submissions.exists() or user.audiograms.exists()
    if "confirm" in request.POST and has_records:
        with transaction.atomic():
            # Lock the user's row so two quick submits cannot both find "no live link".
            User.objects.select_for_update().get(pk=user.pk)
            if not user.report_shares.active().exists():
                models.ReportShare.objects.create(user=user)
    return redirect("share_report")


@login_required
@require_http_methods(["POST"])
def report_share_cancel(request, share_id):
    share = get_object_or_404(models.ReportShare.objects.active(), pk=share_id, user=request.user)
    share.revoked_at = timezone.now()
    share.save(update_fields=["revoked_at"])
    return redirect("share_report")


def _family_page(request, template, context=None, status=200):
    # Family pages hold health data without a login: never cached, indexed, or referred on.
    response = render(request, template, context, status=status)
    add_never_cache_headers(response)
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _live_share(request, token):
    # Expired, cancelled, deleted with the account, or never made: the same answer for all.
    share = models.ReportShare.objects.active().select_related("user").filter(token=token).first()
    if share is None:
        return None, _family_page(request, "screening/share_invalid.html", status=404)
    return share, None


@require_http_methods(["GET"])
def shared_cover(request, token):
    # What a link preview (e.g. LINE) fetches: no health data, and not counted as an open.
    share, invalid = _live_share(request, token)
    return invalid or _family_page(request, "screening/shared_cover.html", {"share": share})


@require_http_methods(["GET"])
def shared_report(request, token):
    share, invalid = _live_share(request, token)
    if invalid:
        return invalid
    models.ReportShare.objects.filter(pk=share.pk).update(
        open_count=F("open_count") + 1, last_opened_at=timezone.now()
    )
    context = _report_context(share.user)
    # #194 "先看重點": the latest life-impact record, picked as the home page's last result is.
    last = get_user_state(share.user, today=timezone.localdate()).last_result
    context.update(
        {
            "share": share,
            "shared": True,
            "owner": share.user,
            "life_impact": last.submission if last and last.is_life_impact else None,
        }
    )
    return _family_page(request, "screening/shared_report.html", context)
