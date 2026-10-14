from django.urls import path
from drf_spectacular.views import SpectacularYAMLAPIView

from screening.api import views

app_name = "api"

urlpatterns = [
    path("questionnaires/", views.QuestionnaireList.as_view(), name="questionnaires"),
    path("schema/", SpectacularYAMLAPIView.as_view(), name="schema"),
]
