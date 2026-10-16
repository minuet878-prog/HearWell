from django.urls import path
from drf_spectacular.views import SpectacularYAMLAPIView

from screening.api import views

app_name = "api"

urlpatterns = [
    path("questionnaires/", views.QuestionnaireList.as_view(), name="questionnaires"),
    path("questionnaires/<int:pk>/", views.QuestionnaireDetail.as_view(), name="questionnaire"),
    path("submissions/", views.SubmissionList.as_view(), name="submissions"),
    path("submissions/<int:pk>/", views.SubmissionDetail.as_view(), name="submission"),
    path("audiograms/", views.AudiogramCreate.as_view(), name="audiograms"),
    path("audiograms/<int:pk>/", views.AudiogramDetail.as_view(), name="audiogram"),
    path("schema/", SpectacularYAMLAPIView.as_view(), name="schema"),
]
