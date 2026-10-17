import json
import uuid
from collections import Counter

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Prefetch
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.http import content_disposition_header, url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from screening import models
from screening.api.views import _find_by_key
from screening.audiogram import compare
from screening.forms import (
    AnswerFormSet,
    DeleteAccountForm,
    HearingAidForm,
    RegisterForm,
    answer_choices,
)
from screening.scoring import (
    IOI_HA,
    IOI_HA_CHOICES,
    IOI_HA_ITEM_NAMES,
    IOI_HA_NORMS,
    NORM_COMPARISON_TEXT,
    compare_to_norm,
    get_advice,
    ioi_ha_group,
    max_score,
)

from .models import Answer, AudiogramPoint, Ear, NormGroup, Questionnaire, Submission, User


def _safe_next(request):
    # Only same-site URLs; anything else is treated as no next (open redirect guard).
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return ""


def index(request):
    return render(request, "screening/index.html")


def family_guide(request):
    # Spec phase8_c1_family_guide.md: the same reviewed content for everyone, no user data.
    return render(request, "screening/family_guide.html")


class MonitoringTestError(Exception):
    """Raised on purpose so an admin can check that error monitoring reaches Sentry."""


def monitoring_test(request):
    if not request.user.is_superuser:
        raise Http404
    raise MonitoringTestError


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


@require_http_methods(["GET", "POST"])
def register(request):
    next_url = _safe_next(request)
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
            except IntegrityError:
                # Someone else took this name after is_valid(); any other clash is a real error.
                if not User.objects.filter(username=form.cleaned_data["username"]).exists():
                    raise
                form.add_error("username", form.instance.unique_error_message(User, ["username"]))
            else:
                login(request, user)
                # New accounts agree to the privacy notice before anything else.
                if next_url:
                    return redirect_to_login(next_url, reverse("consent"))
                return redirect("consent")
    else:
        form = RegisterForm()
    return render(request, "screening/register.html", {"form": form, "next": next_url})


def privacy(request):
    return render(
        request,
        "screening/privacy.html",
        {"version": models.CONSENT_VERSION, "updated_on": models.PRIVACY_UPDATED_ON},
    )


@login_required
@require_http_methods(["GET", "POST"])
def consent(request):
    next_url = _safe_next(request)
    if request.method == "POST" and "decline" in request.POST:
        logout(request)
        messages.info(
            request, "沒有同意就不能使用篩檢功能，您的帳號仍在。想使用時，登入後按「我同意」即可。"
        )
        return redirect("index")
    if request.method == "POST" and "agree" in request.POST and not request.user.has_consented():
        request.user.give_consent()
    if request.user.has_consented():
        return HttpResponseRedirect(next_url or reverse("index"))
    return render(request, "screening/consent.html", {"next": next_url})


# Where to start (spec phase9_ui_refresh_4b_questionnaire_cards.md 4.1): HHIE-S, then IOI-HA,
# then any other questionnaire by when it was added. A screen order, not a scoring rule.
LIST_ORDER = ("hhie-s", IOI_HA)


def list_order(questionnaire):
    code = questionnaire.code
    rank = LIST_ORDER.index(code) if code in LIST_ORDER else len(LIST_ORDER)
    return (rank, questionnaire.pk)


@login_required
def questionnaire_list(request):
    # Added order first (the database promises none), so leaving out list_order shows up.
    questionnaires = Questionnaire.objects.annotate(question_count=Count("questions"))
    questionnaires = questionnaires.order_by("pk")
    return render(
        request,
        "screening/questionnaire.html",
        {"questionnaires": sorted(questionnaires, key=list_order)},
    )


def _latest_hhie_s(user, wearing):
    # wearing is True or False; 未記錄 (None) is neither, so it never matches.
    return (
        user.submissions.filter(questionnaire__code="hhie-s", wearing_hearing_aid=wearing)
        .order_by("-created_at", "-id")
        .first()
    )


def _ioi_ha_norm(user):
    basis = _latest_hhie_s(user, wearing=False)
    total = None if basis is None else basis.total_answer_score
    return {"norm_group": ioi_ha_group(total), "norm_basis": basis}


@login_required
@require_http_methods(["GET", "POST"])
def screening(request, questionnaire_id):
    if request.method == "GET":
        questionnaire = get_object_or_404(Questionnaire, pk=questionnaire_id)
        # IOI-HA is answered wearing hearing aids by definition, so it does not ask.
        is_ioi_ha = questionnaire.code == IOI_HA
        questions = questionnaire.questions.all()
        formset = AnswerFormSet(
            questions=questions, initial=[{"question_id": question.id} for question in questions]
        )
        question_form = list(zip(questions, formset, strict=True))
        return render(
            request,
            "screening/screening.html",
            {
                "question_form": question_form,
                "question_count": len(questions),
                "questionnaire": questionnaire,
                "formset": formset,
                "hearing_aid_form": None if is_ioi_ha else HearingAidForm(),
                "is_ioi_ha": is_ioi_ha,
                "use_react": not is_ioi_ha,
                # New for every opened page: answering again later is a new submission.
                "idempotency_key": uuid.uuid4(),
            },
        )
    if request.method == "POST":
        questionnaire = get_object_or_404(Questionnaire, pk=questionnaire_id)
        is_ioi_ha = questionnaire.code == IOI_HA
        questions = questionnaire.questions.all()
        if not questions:
            return redirect("questionnaire_list")
        # Missing or malformed (tampered or very old page): saved as before, just not guarded.
        try:
            key = uuid.UUID(request.POST.get("idempotency_key", ""))
        except ValueError:
            key = None
        # This page was already sent (double click, or back and resend with other answers):
        # show that first result instead of saving again.
        existing = key and _find_by_key(request.user, key)
        if existing:
            return _already_sent(request, existing)
        formset = AnswerFormSet(questions=questions, data=request.POST)
        hearing_aid_form = None if is_ioi_ha else HearingAidForm(data=request.POST)
        # question_form 只有在驗證沒過的時候才會被用到[拿去重新顯示頁面]，而那時的資料可能是壞的
        # ，所以不能用 strict=True
        question_form = list(zip(questions, formset, strict=False))
        if formset.is_valid() and (hearing_aid_form is None or hearing_aid_form.is_valid()):
            if is_ioi_ha:
                extra = _ioi_ha_norm(request.user)
            else:
                extra = {
                    "wearing_hearing_aid": hearing_aid_form.cleaned_data["wearing_hearing_aid"]
                }
            try:
                submission = formset.save(
                    request.user, questionnaire, idempotency_key=key, **extra
                )
            except IntegrityError:
                # Two clicks arrived together and the other one saved first; save() is atomic,
                # so nothing of this one is left behind. Any other clash is a real error.
                existing = key and _find_by_key(request.user, key)
                if not existing:
                    raise
                return _already_sent(request, existing)
            return redirect("result", submission_id=submission.id)
        else:
            # Only questions shown on the page, so the list matches the marked ones. A form
            # missing its question_id was tampered with: it gets the generic error instead.
            # Each entry links to the question's fieldset id in screening.html.
            unanswered = [
                (f"第 {number} 題", f"question-{number}")
                for number, (_, form) in enumerate(question_form, start=1)
                if form.has_error("score", code="required") and not form.has_error("question_id")
            ]
            if hearing_aid_form is not None and hearing_aid_form.has_error(
                "wearing_hearing_aid", code="required"
            ):
                unanswered.insert(0, ("是否戴助聽器", "question-hearing-aid"))
            if unanswered:
                message = f"還有 {len(unanswered)} 題沒有回答，請看標示紅字的題目。"
            else:
                message = formset.non_form_errors()
            return render(
                request,
                "screening/screening.html",
                {
                    "message": message,
                    "unanswered": unanswered,
                    "question_form": question_form,
                    "question_count": len(questions),
                    "questionnaire": questionnaire,
                    "formset": formset,
                    "hearing_aid_form": hearing_aid_form,
                    "is_ioi_ha": is_ioi_ha,
                    # Stay on this form: React would start over and drop the errors and answers.
                    "use_react": False,
                    # Nothing was saved, so the fixed answers go out under the same number.
                    "idempotency_key": key,
                },
            )


def _already_sent(request, submission):
    messages.info(
        request,
        "這份作答剛才已經送出，以下是那次的結果；要重新作答，請從「開始篩檢」進入。",
    )
    return redirect("result", submission_id=submission.id)


def _aided_difference(user):
    # Latest unaided vs latest aided HHIE-S, whichever came first; no verdict on the number.
    unaided = _latest_hhie_s(user, wearing=False)
    aided = _latest_hhie_s(user, wearing=True)
    if unaided is None or aided is None:
        return None
    change = unaided.total_answer_score - aided.total_answer_score
    if change > 0:
        text = f"少了 {change} 分"
    elif change < 0:
        text = f"多了 {-change} 分"
    else:
        text = "沒有變化"  # 0 is a real result, not missing data
    return {"unaided": unaided, "aided": aided, "text": text}


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


@login_required
def my_hearing(request):
    submissions = list(request.user.submissions.select_related("questionnaire").with_scores())
    if not submissions:
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
    per_day = Counter(timezone.localdate(s.created_at) for s in records)
    same_day = {s.id for s in records if per_day[timezone.localdate(s.created_at)] > 1}
    return render(
        request,
        "screening/my_hearing.html",
        {
            "submissions": records,
            "same_day": same_day,
            "questionnaires": questionnaires,
            "current": current,
            "difference": _aided_difference(request.user) if current.code == "hhie-s" else None,
            "ioi_ha_chart": _ioi_ha_chart(records) if current.code == IOI_HA else None,
        },
    )


def _taipei(moment):
    return timezone.localtime(moment).isoformat()


def _export_submission(submission):
    # IOI-HA has no total, subscales or level (same as its result page): null, not 0.
    not_scored = submission.questionnaire.code == IOI_HA
    return {
        "questionnaire": submission.questionnaire.questionnaire_name,
        "created_at": _taipei(submission.created_at),
        "wearing_hearing_aid": submission.get_wearing_hearing_aid_display(),
        "answers": [
            {
                "number": answer.question.question_number,
                "question": answer.question.question_text,
                "score": answer.score,
                # null rather than a 500: one odd old answer must not block the whole export.
                "choice": dict(answer_choices(answer.question)).get(answer.score),
            }
            for answer in submission.answers.all()
        ],
        "total_score": None if not_scored else submission.total_answer_score,
        "emotional_score": None if not_scored else submission.emotional_score,
        "social_score": None if not_scored else submission.social_score,
        "level": None if not_scored else submission.classified["text"],
        "norm_group": submission.get_norm_group_display() or None,
    }


@login_required
@require_http_methods(["GET"])
@never_cache
def download_my_data(request):
    # Spec phase7_data_export.md: everything of request.user, nothing else; no ids in the URL.
    user = request.user
    answers = Answer.objects.select_related("question__questionnaire").order_by(
        "question__question_number"
    )
    submissions = (
        user.submissions.select_related("questionnaire")
        .prefetch_related(Prefetch("answers", queryset=answers))
        .with_scores()
    )
    points = AudiogramPoint.objects.order_by("ear", "conduction", "frequency")
    audiograms = user.audiograms.prefetch_related(Prefetch("points", queryset=points))
    data = {
        "account": {
            "username": user.username,
            "email": user.email,
            "birth_year": user.birth_year,
            "date_joined": _taipei(user.date_joined),
        },
        "consents": [
            {"version": consent.version, "agreed_at": _taipei(consent.agreed_at)}
            for consent in user.consents.order_by("agreed_at", "id")
        ],
        "submissions": [_export_submission(submission) for submission in submissions],
        "audiograms": [
            {
                "tested_on": audiogram.tested_on.isoformat(),
                "created_at": _taipei(audiogram.created_at),
                "points": [
                    {
                        "ear": point.get_ear_display(),
                        "conduction": point.get_conduction_display(),
                        "frequency": point.frequency,
                        "db": point.db,
                        "no_response": point.no_response,
                        "masked": point.masked,
                    }
                    for point in audiogram.points.all()
                ],
            }
            for audiogram in audiograms
        ],
        # The link code itself is left out: it would let anyone holding the file open it.
        "report_shares": [
            {
                "created_at": _taipei(share.created_at),
                "expires_at": _taipei(share.expires_at),
                "cancelled": share.revoked_at is not None,
                "open_count": share.open_count,
                "last_opened_at": share.last_opened_at and _taipei(share.last_opened_at),
            }
            for share in user.report_shares.all()
        ],
    }
    filename = f"hearwell-我的資料-{timezone.localdate().isoformat()}.json"
    return HttpResponse(
        json.dumps(data, ensure_ascii=False, indent=2),
        content_type="application/json",
        headers={"Content-Disposition": content_disposition_header(True, filename)},
    )


@login_required
@require_http_methods(["GET"])
def account_settings(request):
    # Spec phase9_ui_refresh_3_structure.md 4.1: request.user's own account, to look at only.
    user = request.user
    consent = (
        user.consents.filter(version__gte=models.CONSENT_VERSION).order_by("-agreed_at").first()
    )
    return render(request, "screening/account.html", {"consent": consent})


@login_required
@require_http_methods(["GET", "POST"])
def delete_account(request):
    user = request.user
    # Staff could lock everyone out of admin; they remove their staff rights first.
    if user.is_staff or user.is_superuser:
        status = 403 if request.method == "POST" else 200
        return render(request, "screening/delete_account.html", {"is_admin": True}, status=status)
    form = DeleteAccountForm(request.POST if request.method == "POST" else None, user=user)
    if form.is_valid():
        user.delete_with_data()
        logout(request)
        messages.success(request, "您的帳號和資料已經刪除。")
        return redirect("index")
    return render(
        request,
        "screening/delete_account.html",
        {
            "form": form,
            "submission_count": user.submissions.count(),
            "audiogram_count": user.audiograms.count(),
        },
    )


REPORT_RECENT = 5  # history rows per questionnaire on the health report


def _report_context(user):
    # One builder for the owner's report and the family's copy (rule 10: same scoring path).
    submissions = list(user.submissions.select_related("questionnaire").with_scores())
    by_questionnaire = {}
    for submission in submissions:  # newest first
        if submission.questionnaire.code != IOI_HA:
            by_questionnaire.setdefault(submission.questionnaire, []).append(submission)
    sections = [
        {
            "questionnaire": questionnaire,
            "latest": records[0],
            "count": len(records),
            "recent": records[:REPORT_RECENT],
            "max_score": max_score(questionnaire.code),
        }
        for questionnaire, records in sorted(by_questionnaire.items(), key=lambda kv: kv[0].id)
    ]
    context = {
        "sections": sections,
        "recent_limit": REPORT_RECENT,
        "difference": _aided_difference(user),
        "today": timezone.localdate(),
    }
    ioi_ha = next((s for s in submissions if s.questionnaire.code == IOI_HA), None)
    if ioi_ha:
        answers = ioi_ha.answers.select_related("question").order_by("question__question_number")
        items, grouped = _ioi_ha_items(ioi_ha, answers)
        context["ioi_ha"] = {
            "submission": ioi_ha,
            "items": items,
            "grouped": grouped,
            "below": sum(item["comparison"] == NORM_COMPARISON_TEXT["below"] for item in items),
            "above": sum(item["comparison"] == NORM_COMPARISON_TEXT["above"] for item in items),
        }
    audiogram = user.audiograms.prefetch_related("points").first()
    if audiogram:
        context.update(_audiogram_context(audiogram))
    context["has_records"] = bool(submissions or audiogram)
    return context


@login_required
def health_report(request):
    # Spec phase8_c3_report.md: only results the site already shows, laid out for printing.
    context = _report_context(request.user)
    context["share"] = request.user.report_shares.active().first()
    return render(request, "screening/health_report.html", context)


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
    return redirect("health_report")


@login_required
@require_http_methods(["POST"])
def report_share_cancel(request, share_id):
    share = get_object_or_404(models.ReportShare.objects.active(), pk=share_id, user=request.user)
    share.revoked_at = timezone.now()
    share.save(update_fields=["revoked_at"])
    return redirect("health_report")


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
    context.update({"share": share, "shared": True, "owner": share.user})
    return _family_page(request, "screening/shared_report.html", context)


@login_required
def submission_result(request, submission_id):
    submission = get_object_or_404(Submission, pk=submission_id, user=request.user)
    answers = submission.answers.select_related("question").order_by("question__question_number")
    if submission.norm_group:
        return _ioi_ha_result(request, submission, answers)
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
            "total_score": total_score,
            "emotional": emotional,
            "social": social,
            "max_score": max_score(submission.questionnaire.code),
            "classified_score_text": classified_score["text"],
            "classified_score_level": classified_score["level"],
            "advice": get_advice(classified_score["level"]),
        },
    )


def _ioi_ha_items(submission, answers):
    # The only place IOI-HA answers meet the norms; the result page and the report both use it.
    grouped = submission.norm_group != NormGroup.UNGROUPED
    items = []
    for answer in answers:
        number = answer.question.question_number
        comparison = (
            compare_to_norm(submission.norm_group, number, answer.score) if grouped else None
        )
        items.append(
            {
                "name": IOI_HA_ITEM_NAMES[number],
                "text": answer.question.question_text,
                "label": IOI_HA_CHOICES[number][answer.score - 1],
                "comparison": NORM_COMPARISON_TEXT.get(comparison),
            }
        )
    return items, grouped


def _ioi_ha_result(request, submission, answers):
    # No total, level or advice: IOI-HA is read item by item against the fixed norm group.
    items, grouped = _ioi_ha_items(submission, answers)
    return render(
        request,
        "screening/result_ioi_ha.html",
        {"submission": submission, "items": items, "grouped": grouped},
    )


@login_required
def audiogram_list(request):
    return render(
        request,
        "screening/audiogram_list.html",
        {"audiograms": request.user.audiograms.prefetch_related("points")},
    )


def _chart_points(points):
    return [
        {
            "ear": p.ear,
            "conduction": p.conduction,
            "frequency": p.frequency,
            "db": p.db,
            "no_response": p.no_response,
            "masked": p.masked,
        }
        for p in points
    ]


@login_required
def audiogram_new(request):
    return render(request, "screening/audiogram_new.html", {"today": timezone.localdate()})


def _own_audiogram(request, audiogram_id):
    return get_object_or_404(
        request.user.audiograms.prefetch_related("points"), pk=audiogram_id
    )


@login_required
def audiogram_detail(request, audiogram_id):
    audiogram = _own_audiogram(request, audiogram_id)
    return render(request, "screening/audiogram_detail.html", _audiogram_context(audiogram))


def _audiogram_context(audiogram):
    # Shared by the audiogram page and the health report, so both read it the same way.
    result = audiogram.interpretation()
    # Right ear first, air before bone, as on a clinical record.
    points = sorted(
        audiogram.points.all(), key=lambda p: (p.ear != Ear.RIGHT, p.conduction, p.frequency)
    )
    return {
        "audiogram": audiogram,
        "ears": [(ear.value, ear.label, result[ear.value]) for ear in (Ear.RIGHT, Ear.LEFT)],
        "points": points,
        "chart_points": _chart_points(points),
    }


@login_required
@require_http_methods(["GET", "POST"])
def audiogram_delete(request, audiogram_id):
    audiogram = _own_audiogram(request, audiogram_id)
    if request.method == "POST":
        audiogram.delete()
        return redirect("audiogram_list")
    return render(request, "screening/audiogram_delete.html", {"audiogram": audiogram})


@login_required
def audiogram_edit(request, audiogram_id):
    audiogram = _own_audiogram(request, audiogram_id)
    initial = {
        "tested_on": audiogram.tested_on.isoformat(),
        "points": _chart_points(audiogram.points.all()),
    }
    return render(
        request,
        "screening/audiogram_new.html",
        {"today": timezone.localdate(), "audiogram": audiogram, "initial": initial},
    )


def _compare_ids(request, audiograms):
    if "a" not in request.GET and "b" not in request.GET:
        return [a.id for a in audiograms[:2]]
    try:
        return [int(request.GET["a"]), int(request.GET["b"])]
    except (KeyError, ValueError):
        raise Http404 from None


@login_required
def audiogram_compare(request):
    audiograms = list(request.user.audiograms.all())
    context = {"audiograms": audiograms}
    if len(audiograms) < 2:
        return render(request, "screening/audiogram_compare.html", context)
    ids = _compare_ids(request, audiograms)
    # Model ordering puts the newer one first, whichever select it was picked in (spec 4.2).
    pair = list(request.user.audiograms.prefetch_related("points").filter(pk__in=ids))
    if len(pair) != len(set(ids)):
        raise Http404
    ear = request.GET.get("ear")
    if ear not in Ear.values:
        ear = Ear.RIGHT
    context.update(a=ids[0], b=ids[1], ear=ear, ears=Ear.choices)
    if len(pair) == 2:
        new, old = pair
        result = compare(new.points.all(), old.points.all())[ear]
        context.update(
            new=new,
            old=old,
            ear_label=Ear(ear).label,
            result=result,
            sections=[("air", "氣導", result["air"]), ("bone", "骨導", result["bone"])],
            chart_points=_chart_points(p for p in new.points.all() if p.ear == ear),
            old_chart_points=_chart_points(p for p in old.points.all() if p.ear == ear),
        )
    return render(request, "screening/audiogram_compare.html", context)
