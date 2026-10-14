from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import (
    password_validators_help_texts,
    validate_password,
)
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from screening.forms import AnswerFormSet, HearingAidForm
from screening.scoring import get_advice, level_to_color

from .models import Answer, Questionnaire, Submission, User


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
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirmation = request.POST.get("confirmation")
        next_url = _safe_next(request)
        if not username or not password or not confirmation or not email:
            return render(
                request,
                "screening/register.html",
                {"messages": ["請完整填寫所有欄位"], "next": next_url},
            )
        if password != confirmation:
            return render(
                request, "screening/register.html", {"messages": ["密碼必須相同"], "next": next_url}
            )

        try:
            user = User(username=username)
            validate_password(password, user=user)
            user = User.objects.create_user(username, email, password)
            user.save()
        except IntegrityError:
            return render(
                request,
                "screening/register.html",
                {"messages": ["使用者名稱已被使用"], "next": next_url},
            )
        except ValidationError as e:
            return render(
                request, "screening/register.html", {"messages": e.messages, "next": next_url}
            )
        login(request, user)
        return HttpResponseRedirect(next_url or reverse("index"))
    else:
        return render(
            request,
            "screening/register.html",
            {"password_messages": password_validators_help_texts(), "next": _safe_next(request)},
        )


@login_required
def questionnaire_list(request):
    return render(
        request,
        "screening/questionnaire.html",
        {"questionnaires": Questionnaire.objects.all()},
    )


@login_required
@require_http_methods(["GET", "POST"])
def screening(request, questionnaire_id):
    if request.method == "GET":
        questionnaire = get_object_or_404(Questionnaire, pk=questionnaire_id)
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
                "questionnaire": questionnaire,
                "formset": formset,
                "hearing_aid_form": HearingAidForm(),
            },
        )
    if request.method == "POST":
        questionnaire = get_object_or_404(Questionnaire, pk=questionnaire_id)
        questions = questionnaire.questions.all()
        if not questions:
            return redirect("questionnaire_list")
        formset = AnswerFormSet(questions=questions, data=request.POST)
        hearing_aid_form = HearingAidForm(data=request.POST)
        # question_form 只有在驗證沒過的時候才會被用到[拿去重新顯示頁面]，而那時的資料可能是壞的
        # ，所以不能用 strict=True
        question_form = list(zip(questions, formset, strict=False))
        if formset.is_valid() and hearing_aid_form.is_valid():
            with transaction.atomic():
                submission = Submission.objects.create(
                    user=request.user,
                    questionnaire=questionnaire,
                    wearing_hearing_aid=hearing_aid_form.cleaned_data["wearing_hearing_aid"],
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
            return render(
                request,
                "screening/screening.html",
                {
                    "message": formset.non_form_errors(),
                    "question_form": question_form,
                    "questionnaire": questionnaire,
                    "formset": formset,
                    "hearing_aid_form": hearing_aid_form,
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
    answers = submission.answers.select_related("question").all()
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
            "classified_score_text": classified_score["text"],
            "classified_score_color": level_to_color(classified_score["level"]),
            "advice": get_advice(classified_score["level"]),
        },
    )
