from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("login", views.login_view, name="login"),
    path("logout", views.logout_view, name="logout"),
    path("register", views.register, name="register"),
    path("questionnaire_list", views.questionnaire_list, name="questionnaire_list"),
    path("questionnaire/<int:questionnaire_id>", views.screening, name="screening"),
    path("my_hearing", views.my_hearing, name="my_hearing"),
    path("submission/<int:submission_id>", views.submission_result, name="result"),
]
