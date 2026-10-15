from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from screening.forms import AnswerFormSet, HearingAidForm, RegisterForm
from screening.scoring import (
    IOI_HA,
    IOI_HA_CHOICES,
    NORM_COMPARISON_TEXT,
    compare_to_norm,
    get_advice,
    ioi_ha_group,
    max_score,
)

from .models import Answer, NormGroup, Questionnaire, Submission


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


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        next_url = _safe_next(request)

        if user is not None:
            login(request, user)
            return HttpResponseRedirect(next_url or reverse("index"))
        else:
            return render(
                request,
                "screening/login.html",
                {"message": "使用者名稱或密碼錯誤", "next": next_url},
            )
    else:
        return render(request, "screening/login.html", {"next": _safe_next(request)})


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
            user = form.save()
            login(request, user)
            return HttpResponseRedirect(next_url or reverse("index"))
    else:
        form = RegisterForm()
    return render(request, "screening/register.html", {"form": form, "next": next_url})


@login_required
def questionnaire_list(request):
    return render(
        request,
        "screening/questionnaire.html",
        {"questionnaires": Questionnaire.objects.annotate(question_count=Count("questions"))},
    )


def _ioi_ha_norm(user):
    # Latest HHIE-S answered without a hearing aid; 未記錄 (None) does not count.
    basis = (
        user.submissions.filter(questionnaire__code="hhie-s", wearing_hearing_aid=False)
        .order_by("-created_at", "-id")
        .first()
    )
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
            },
        )
    if request.method == "POST":
        questionnaire = get_object_or_404(Questionnaire, pk=questionnaire_id)
        is_ioi_ha = questionnaire.code == IOI_HA
        questions = questionnaire.questions.all()
        if not questions:
            return redirect("questionnaire_list")
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
            with transaction.atomic():
                submission = Submission.objects.create(
                    user=request.user, questionnaire=questionnaire, **extra
                )
                answers = [
                    Answer(
                        submission=submission,
                        question=form.cleaned_data["question_id"],
                        score=form.cleaned_data["score"],
                    )
                    for form in formset
                ]
                Answer.objects.bulk_create(answers)
            return redirect("result", submission_id=submission.id)
        else:
            # Count only questions shown on the page, so the number matches the marked ones.
            # A form missing its question_id was tampered with: it gets the generic error instead.
            unanswered = sum(
                form.has_error("score", code="required") and not form.has_error("question_id")
                for _, form in question_form
            )
            if unanswered:
                message = f"還有 {unanswered} 題沒有回答，請看標示紅字的題目。"
            else:
                message = formset.non_form_errors()
            return render(
                request,
                "screening/screening.html",
                {
                    "message": message,
                    "question_form": question_form,
                    "question_count": len(questions),
                    "questionnaire": questionnaire,
                    "formset": formset,
                    "hearing_aid_form": hearing_aid_form,
                    "is_ioi_ha": is_ioi_ha,
                },
            )


@login_required
def my_hearing(request):
    submissions = request.user.submissions.select_related("questionnaire").with_scores()
    return render(
        request,
        "screening/my_hearing.html",
        {"submissions": submissions},
    )


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


def _ioi_ha_result(request, submission, answers):
    # No total, level or advice: IOI-HA is read item by item against the fixed norm group.
    grouped = submission.norm_group != NormGroup.UNGROUPED
    items = []
    for answer in answers:
        number = answer.question.question_number
        comparison = (
            compare_to_norm(submission.norm_group, number, answer.score) if grouped else None
        )
        items.append(
            {
                "text": answer.question.question_text,
                "label": IOI_HA_CHOICES[number][answer.score - 1],
                "comparison": NORM_COMPARISON_TEXT.get(comparison),
            }
        )
    return render(
        request,
        "screening/result_ioi_ha.html",
        {"submission": submission, "items": items, "grouped": grouped},
    )
