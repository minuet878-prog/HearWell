import uuid
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import IntegrityError
from django.db.models import Count, OuterRef, Subquery, prefetch_related_objects
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from screening import models
from screening.forms import (
    AgeGroupForm,
    AnswerFormSet,
    ConcernForm,
    HearingAidForm,
    HhiComparisonForm,
    offers_not_applicable,
)
from screening.ioi_norm import TOKEN_ERROR, ioi_ha_norm, norm_bases, norm_token
from screening.main_flow import catalogue_recommendation, get_user_state, life_impact_questionnaire
from screening.models import Questionnaire, Submission
from screening.questionnaires.definition import (
    HEARING_AID,
    LIFE_IMPACT,
    LISTENING,
    TINNITUS,
    UNSURE,
)
from screening.questionnaires.ioi_ha import CODE as IOI_HA
from screening.questionnaires.results import SubscaleResult
from screening.questionnaires.ssq12_tw import CODE as SSQ12
from screening.scoring import AIDED_RETAKE_NOTE, AIDED_RETAKE_TITLE, RECOMMENDATION_REASONS
from screening.views.common import health_data_page


def continue_notice(user, questionnaires=None):
    # #326 E7 (#337): the questionnaires this user can open, which the continue notice's script
    # matches against the drafts in this browser (draft.js); the drafts never reach the server.
    # A page that has already read them in list order passes them in.
    if questionnaires is None:
        questionnaires = sorted(Questionnaire.objects.defined(), key=list_order)
    prefetch_related_objects(questionnaires, "questions")
    return {
        "userId": user.pk,
        "questionnaires": [
            {
                "id": questionnaire.pk,
                # As the catalog card reads it (questionnaire_card.html).
                "name": f"{questionnaire.definition.topic}（{questionnaire}）",
                "url": reverse("screening", args=[questionnaire.pk]),
                "questionIds": [question.id for question in questionnaire.questions.all()],
                # As the answer page decides from the API: a draft may hold 「不適用」 when a
                # question offers it.
                "allowNotApplicable": any(
                    offers_not_applicable(question) for question in questionnaire.questions.all()
                ),
            }
            for questionnaire in questionnaires
        ],
    }


def list_order(questionnaire):
    return (questionnaire.definition.list_rank, questionnaire.pk)


# The recommendation wizard's GET parameters: `wizard` from the catalogue's 「幫我選問卷」, the rest
# its answers. Without any, a returning user sees the catalogue.
WIZARD_PARAMS = ("wizard", "concern", "chosen", "age_group")


def _wizard_step(request, step, total, catalog, **context):
    # Steps go forward by GET parameters, so the wizard works without JavaScript (#152).
    return render(
        request,
        "screening/questionnaire.html",
        context
        | {
            "step": step,
            "total": total,
            "continue_notice": continue_notice(request.user, catalog),
            # Set by the consent page; only its first screen says the account is ready.
            "from_consent": step == 1 and request.GET.get("from") == "consent",
        },
    )


@login_required
@health_data_page
def questionnaire_list(request):
    questionnaires = Questionnaire.objects.defined().annotate(question_count=Count("questions"))
    user = request.user
    state = get_user_state(user, timezone.localdate())
    returning = not state.is_new
    # A returning user sees the catalogue first; the wizard is one link away (ADR 0030).
    if "choose" in request.GET or (
        returning and not any(name in request.GET for name in WIZARD_PARAMS)
    ):
        # Each card's 「上次」 date in the same query, not one query per card.
        latest = (
            Submission.objects.filter(user=user, questionnaire=OuterRef("pk"))
            .order_by("-created_at")
            .values("created_at")[:1]
        )
        questionnaires = sorted(
            questionnaires.annotate(last_answered_at=Subquery(latest)), key=list_order
        )
        return render(
            request,
            "screening/questionnaire.html",
            {
                "questionnaires": questionnaires,
                "continue_notice": continue_notice(user, questionnaires),
                # A new user has no record to recommend by.
                "recommendation": catalogue_recommendation(user, questionnaires, state)
                if returning
                else None,
            },
        )
    questionnaires = sorted(questionnaires, key=list_order)
    wizard_url = reverse("questionnaire_list")
    # None while the age is still needed: then step 1 says 共 3 步, as a life-impact result asks it.
    life_impact = life_impact_questionnaire(user, questionnaires, state, None)
    concern_form = ConcernForm(
        request.GET if "concern" in request.GET else None,
        # Back from a later step: the answer chosen there is still chosen.
        initial={"concern": request.GET.get("chosen")},
    )
    if not concern_form.is_valid():
        return _wizard_step(
            request,
            1,
            3 if life_impact is None else 2,
            questionnaires,
            field=concern_form["concern"],
            # A returning user came from the catalogue's 「幫我選問卷」.
            back_url=wizard_url if returning else reverse("index"),
        )
    concern = concern_form.cleaned_data["concern"]
    back_url = f"{wizard_url}?{urlencode({'chosen': concern})}"
    has_norm_basis = concern == HEARING_AID and norm_bases(user).exists()
    step = 2
    if concern in (LIFE_IMPACT, UNSURE, HEARING_AID) and life_impact is None:
        age_form = AgeGroupForm(request.GET if "age_group" in request.GET else None)
        if not age_form.is_valid():
            return _wizard_step(
                request,
                2,
                3,
                questionnaires,
                field=age_form["age_group"],
                concern=concern,
                back_url=back_url,
            )
        life_impact = life_impact_questionnaire(
            user, questionnaires, state, age_form.cleaned_data["age_group"]
        )
        step = 3
        back_url = f"{wizard_url}?{urlencode({'concern': concern})}"
    # Asks the definitions, not the codes, per CODING_STANDARDS.md rule 9; IOI-HA alone is
    # named, as the hearing-aid answer's recommendation once there is a norm basis.
    hearing_aid = [q for q in questionnaires if q.definition.concern == HEARING_AID]
    also, retake = [], None
    if concern in (TINNITUS, LISTENING):
        recommended = next(q for q in questionnaires if q.definition.concern == concern)
        reason = concern
    elif concern != HEARING_AID:
        recommended, reason = life_impact, concern
    elif has_norm_basis:
        recommended, reason = next(q for q in hearing_aid if q.code == IOI_HA), "has_norm_basis"
        # Answering the life-impact questionnaire again worn compares with the unaided record
        # (F1); it comes first.
        title = AIDED_RETAKE_TITLE.format(topic=life_impact.definition.topic, name=life_impact)
        retake = {"questionnaire": life_impact, "title": title, "note": AIDED_RETAKE_NOTE}
        also = [q for q in hearing_aid if q != recommended]
    else:
        # IOI-HA compares with the norm group of an unaided record, so that record comes first.
        recommended, reason = life_impact, "needs_norm_basis"
        also = hearing_aid
    start_url = reverse("screening", args=[recommended.pk])
    if reason == "needs_norm_basis":
        # The answer page starts on "沒戴", which the user may still change (#154).
        start_url += "?preselect=unaided"
    return _wizard_step(
        request,
        step,
        step,
        questionnaires,
        recommended=recommended,
        reason=reason,
        why=RECOMMENDATION_REASONS[reason],
        start_url=start_url,
        also=also,
        retake=retake,
        questionnaires=questionnaires,
        back_url=back_url,
    )


def wearing_follow_ups(questionnaires):
    # The follow-ups for someone who wears hearing aids: IOI-HA, then SSQ12-TW and a
    # satisfaction-type questionnaire (SADL) when it is visible (#174). One missing from the
    # database is left out. Asks the definition's result, not SADL's code, per
    # CODING_STANDARDS.md rule 9.
    by_code = {questionnaire.code: questionnaire for questionnaire in questionnaires}
    satisfaction = next((q for q in questionnaires if q.definition.result is SubscaleResult), None)
    return [q for q in (by_code.get(IOI_HA), by_code.get(SSQ12), satisfaction) if q]


@login_required
@require_http_methods(["GET", "POST"])
@health_data_page
def screening(request, questionnaire_id):
    if request.method == "GET":
        questionnaire = get_object_or_404(Questionnaire.objects.defined(), pk=questionnaire_id)
        # IOI-HA is answered wearing hearing aids by definition, so it does not ask.
        is_ioi_ha = questionnaire.code == IOI_HA
        always_aided = questionnaire.definition.always_aided
        norm = ioi_ha_norm(request.user) if is_ioi_ha else None
        # Set by the wizard when catching up an unaided record (#154): only where the hearing aid
        # question starts, so the POST still takes whatever the user chose.
        preselect_unaided = (
            not is_ioi_ha and not always_aided and request.GET.get("preselect") == "unaided"
        )
        hearing_aid_initial = {"wearing_hearing_aid": False} if preselect_unaided else None
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
                "hearing_aid_form": None
                if is_ioi_ha or always_aided
                else HearingAidForm(
                    initial=hearing_aid_initial, message=questionnaire.definition.wearing_error
                ),
                "preselect_unaided": preselect_unaided,
                "is_ioi_ha": is_ioi_ha,
                "ioi_norm": norm,
                "norm_token": norm_token(request.user, norm) if norm else None,
                # Every questionnaire, IOI-HA too since #245; always-aided ones and IOI-HA skip
                # the wearing step there.
                "use_react": True,
                "always_aided": always_aided,
                # New for every opened page: answering again later is a new submission.
                "idempotency_key": uuid.uuid4(),
            },
        )
    if request.method == "POST":
        questionnaire = get_object_or_404(Questionnaire.objects.defined(), pk=questionnaire_id)
        is_ioi_ha = questionnaire.code == IOI_HA
        always_aided = questionnaire.definition.always_aided
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
        existing = key and request.user.submissions.find_by_key(key)
        if existing:
            return _already_sent(request, existing)
        try:
            norm = (
                ioi_ha_norm(request.user, request.POST.get("norm_token") or None)
                if is_ioi_ha
                else None
            )
        except signing.BadSignature:
            return HttpResponseBadRequest(TOKEN_ERROR)
        formset = AnswerFormSet(questions=questions, data=request.POST)
        hearing_aid_form = (
            None
            if is_ioi_ha or always_aided
            else HearingAidForm(data=request.POST, message=questionnaire.definition.wearing_error)
        )
        # question_form 只有在驗證沒過的時候才會被用到[拿去重新顯示頁面]，而那時的資料可能是壞的
        # ，所以不能用 strict=True
        question_form = list(zip(questions, formset, strict=False))
        if formset.is_valid() and (hearing_aid_form is None or hearing_aid_form.is_valid()):
            if is_ioi_ha:
                extra = norm
            elif always_aided:
                extra = {"wearing_hearing_aid": True}
            else:
                extra = {
                    "wearing_hearing_aid": hearing_aid_form.cleaned_data["wearing_hearing_aid"]
                }
            try:
                submission = formset.save(request.user, questionnaire, idempotency_key=key, **extra)
            except IntegrityError:
                # Two clicks arrived together and the other one saved first; save() is atomic,
                # so nothing of this one is left behind. Any other clash is a real error.
                existing = key and request.user.submissions.find_by_key(key)
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
                    "ioi_norm": norm,
                    "norm_token": norm_token(request.user, norm) if norm else None,
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


@login_required
@require_http_methods(["GET", "POST"])
@health_data_page
def hhi_comparison(request, questionnaire_id):
    questionnaire = get_object_or_404(Questionnaire.objects.defined(), pk=questionnaire_id)
    if questionnaire.definition.comparison is None:
        raise Http404
    saved = (
        request.user.report_comparisons.filter(questionnaire=questionnaire)
        .select_related("unaided__questionnaire", "aided__questionnaire")
        .first()
    )
    if request.method == "POST" and request.POST.get("action") == "remove":
        if saved:
            saved.delete()
        messages.success(request, "已從報告移除這一組，原始作答保持不變。")
        return redirect("hhi_comparison", questionnaire_id=questionnaire.pk)
    data = (
        request.POST
        if request.method == "POST"
        else (
            request.GET
            if any(key in request.GET for key in ("unaided", "aided", "action"))
            else None
        )
    )
    form = HhiComparisonForm(
        data=data,
        user=request.user,
        questionnaire=questionnaire,
        initial={"unaided": saved.unaided_id, "aided": saved.aided_id} if saved else None,
    )
    preview = saved if data is None else None
    if form.is_bound and form.is_valid():
        preview = models.ReportComparison(
            user=request.user, questionnaire=questionnaire, **form.cleaned_data
        )
        if request.method == "POST":
            request.user.report_comparisons.update_or_create(
                questionnaire=questionnaire, defaults=form.cleaned_data
            )
            messages.success(request, "已放進聽力報告，新增紀錄不會自動換掉這一組。")
            return redirect("hhi_comparison", questionnaire_id=questionnaire.pk)
    return render(
        request,
        "screening/hhi_comparison.html",
        {
            "questionnaire": questionnaire,
            "form": form,
            "saved": saved,
            "preview": preview,
            # The pair on screen is the one in the report: no button to save it again (#190).
            "preview_is_saved": saved is not None
            and preview is not None
            and (preview.unaided_id, preview.aided_id) == (saved.unaided_id, saved.aided_id),
        },
        status=400 if request.method == "POST" else 200,
    )
