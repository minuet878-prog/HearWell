from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import (
    password_validators_help_texts,
    validate_password,
)
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse

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
            return render(request, "screening/register.html", {"message": "密碼必須相同"})

        try:
            validate_password(password)
            user = User.objects.create_user(username, email, password)
            user.save()
        except IntegrityError:
            return render(request, "screening/register.html", {"message": "使用者名稱已被使用"})
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


def which_questionnaire(request):
    return render(
        request,
        "screening/questionnaire.html",
        {"questionnaires": Questionnaire.objects.all()},
    )


def screening(request, questionnaire_id):
    if request.method == "GET":
        q = Questionnaire.objects.get(pk=questionnaire_id)
        return render(
            request,
            "screening/screening.html",
            {"questions": q.questions.all(), "questionnaire": q},
        )
    if request.method == "POST":
        q = Questionnaire.objects.get(pk=questionnaire_id)
        questions = q.questions.all()
        scores = {}
        for question in questions:
            question_id = str(question.id)
            if request.POST.get(question_id) is not None:
                scores[question_id] = int(request.POST.get(question_id))
            else:
                return render(
                    request,
                    "screening/screening.html",
                    {
                        "message": "尚有未作答的題目",
                        "questions": questions,
                        "questionnaire": q,
                    },
                )
        sub = Submission.objects.create(user=request.user, questionnaire=q)
        for question in questions:
            question_id = str(question.id)
            Answer.objects.create(submission=sub, question=question, score=scores[question_id])
        return redirect("result", submission_id=sub.id)


def my_hearing(request):
    submissions = request.user.submissions.annotate(total_score=Sum("answers__score")).order_by(
        "-created_at"
    )
    return render(request, "screening/my_hearing.html", {"submissions": submissions})


def submission_result(request, submission_id):
    sub = Submission.objects.get(pk=submission_id)
    answers = sub.answers.all()
    total_score = answers.aggregate(total=Sum("score"))
    emotional = answers.filter(question__category="emotional").aggregate(total=Sum("score"))
    social = answers.filter(question__category="social").aggregate(total=Sum("score"))

    return render(
        request,
        "screening/result.html",
        {
            "submission": sub,
            "answers": answers,
            "total_score": total_score["total"],
            "emotional": emotional["total"],
            "social": social["total"],
        },
    )
