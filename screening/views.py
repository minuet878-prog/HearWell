from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import (
    password_validators_help_texts,
    validate_password,
)
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from screening.forms import AnswerFormSet
from screening.scoring import classify

# Create your views here.
from .models import Answer, Questionnaire, Submission, User


def index(request):
    return render(request, "screening/index.html")


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return HttpResponseRedirect(reverse("index"))
        else:
            return render(request, "screening/login.html", {"message": "使用者名稱或密碼錯誤"})
    else:
        return render(request, "screening/login.html")


def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


def register(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirmation = request.POST.get("confirmation")
        if password != confirmation:
            return render(request, "screening/register.html", {"messages": ["密碼必須相同"]})

        try:
            validate_password(password)
            user = User.objects.create_user(username, email, password)
            user.save()
        except IntegrityError:
            return render(request, "screening/register.html", {"messages": ["使用者名稱已被使用"]})
        except ValidationError as e:
            return render(request, "screening/register.html", {"messages": e.messages})
        login(request, user)
        return HttpResponseRedirect(reverse("index"))
    else:
        return render(
            request,
            "screening/register.html",
            {"password_messages": password_validators_help_texts()},
        )


@login_required
def which_questionnaire(request):
    return render(
        request,
        "screening/questionnaire.html",
        {"questionnaires": Questionnaire.objects.all()},
    )


@login_required
def screening(request, questionnaire_id):
    if request.method == "GET":
        questionnaire = Questionnaire.objects.get(pk=questionnaire_id)
        questions = questionnaire.questions.all()
        formset = AnswerFormSet(initial=[{"question_id": q.id} for q in questions])
        question_form = list(zip(questions, formset))
        return render(
            request,
            "screening/screening.html",
            {"question_form": question_form, "questionnaire": questionnaire, "formset": formset},
        )
    if request.method == "POST":
        q = Questionnaire.objects.get(pk=questionnaire_id)
        questions = q.questions.all()
        scores = {}
        for question in questions:
            question_id = str(question.id)
            raw_value = request.POST.get(question_id)
            if raw_value is None:
                return render(
                    request,
                    "screening/screening.html",
                    {"message": "尚有未作答的題目", "questions": questions, "questionnaire": q},
                )
            else:
                try:
                    score = int(raw_value)
                except ValueError:
                    return render(
                        request,
                        "screening/screening.html",
                        {
                            "message": "請重新填寫,偵測到不正確的答案格式",
                            "questions": questions,
                            "questionnaire": q,
                        },
                    )
                if score not in Answer.Score.values:
                    return render(
                        request,
                        "screening/screening.html",
                        {
                            "message": "請重新填寫,數字不正確",
                            "questions": questions,
                            "questionnaire": q,
                        },
                    )
                scores[question_id] = score

        sub = Submission.objects.create(user=request.user, questionnaire=q)
        for question in questions:
            question_id = str(question.id)
            Answer.objects.create(submission=sub, question=question, score=scores[question_id])
        return redirect("result", submission_id=sub.id)


@login_required
def my_hearing(request):
    submissions = request.user.submissions.annotate(
        total_score=Sum("answers__score", default=0)
    ).order_by("-created_at")
    for submission in submissions:
        submission.classified = classify(submission.total_score)
    return render(
        request,
        "screening/my_hearing.html",
        {"submissions": submissions},
    )


@login_required
def submission_result(request, submission_id):
    sub = get_object_or_404(Submission, pk=submission_id, user=request.user)
    answers = sub.answers.all()
    total_score = answers.aggregate(total=Sum("score", default=0))
    emotional = answers.filter(question__category="emotional").aggregate(
        total=Sum("score", default=0)
    )
    social = answers.filter(question__category="social").aggregate(total=Sum("score", default=0))
    classified_score = classify(total_score["total"])
    return render(
        request,
        "screening/result.html",
        {
            "submission": sub,
            "answers": answers,
            "total_score": total_score["total"],
            "emotional": emotional["total"],
            "social": social["total"],
            "classified_score_text": classified_score["text"],
            "classified_score_color": classified_score["color"],
        },
    )
