from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "login",
        auth_views.LoginView.as_view(
            template_name="screening/login.html", http_method_names=["get", "post"]
        ),
        name="login",
    ),
    path("logout", views.logout_view, name="logout"),
    path("register", views.register, name="register"),
    path("privacy", views.privacy, name="privacy"),
    path("family", views.family_guide, name="family_guide"),
    path("learn", views.learn, name="learn"),
    path("guide", views.guide, name="guide"),
    path("guide/<slug:chapter>", views.guide_chapter, name="guide_chapter"),
    path("route_answer", views.route_answer, name="route_answer"),
    path("consent", views.consent, name="consent"),
    path("monitoring-test", views.monitoring_test, name="monitoring_test"),
    path("questionnaire_list", views.questionnaire_list, name="questionnaire_list"),
    path("questionnaire/<int:questionnaire_id>", views.screening, name="screening"),
    path("my_hearing", views.my_hearing, name="my_hearing"),
    path("comparisons/<int:questionnaire_id>", views.hhi_comparison, name="hhi_comparison"),
    path("report", views.health_report, name="health_report"),
    path("share", views.share_report, name="share_report"),
    path("report/share", views.report_share_create, name="report_share_create"),
    path(
        "report/share/<int:share_id>/cancel",
        views.report_share_cancel,
        name="report_share_cancel",
    ),
    path("shared/<str:token>", views.shared_cover, name="shared_cover"),
    path("shared/<str:token>/report", views.shared_report, name="shared_report"),
    path("my_data/download", views.download_my_data, name="download_my_data"),
    path("account", views.account_settings, name="account_settings"),
    path("account/delete", views.delete_account, name="delete_account"),
    path("submission/<int:submission_id>", views.submission_result, name="result"),
    path("audiograms", views.audiogram_list, name="audiogram_list"),
    path("audiograms/new", views.audiogram_new, name="audiogram_new"),
    path("audiograms/compare", views.audiogram_compare, name="audiogram_compare"),
    path("audiograms/<int:audiogram_id>", views.audiogram_detail, name="audiogram_detail"),
    path("audiograms/<int:audiogram_id>/edit", views.audiogram_edit, name="audiogram_edit"),
    path("audiograms/<int:audiogram_id>/delete", views.audiogram_delete, name="audiogram_delete"),
    path(
        "add_to_home",
        TemplateView.as_view(template_name="screening/add_to_home.html"),
        name="add_to_home",
    ),
]
