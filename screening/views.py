from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import (
    password_validators_help_texts,
    validate_password,
)
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

# Create your views here.
from .models import User


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
