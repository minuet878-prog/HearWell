from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import TemplateView

from .views import (
    accounts,
    answering,
    audiograms,
    export,
    guide,
    home,
    monitoring,
    my_hearing,
    qa_assistant,
    reports,
    results,
)

urlpatterns = [
    path("", home.index, name="index"),
    path(
        "login",
        auth_views.LoginView.as_view(
            template_name="screening/login.html", http_method_names=["get", "post"]
        ),
        name="login",
    ),
    path("logout", accounts.logout_view, name="logout"),
    path("register", accounts.register, name="register"),
    path("privacy", accounts.privacy, name="privacy"),
    path("family", home.family_guide, name="family_guide"),
    path("learn", home.learn, name="learn"),
    path("qa", qa_assistant.qa_home, name="qa_home"),
    path("qa/<slug:code>", qa_assistant.qa_answer, name="qa_answer"),
    path("guide", guide.guide, name="guide"),
    path("guide/<slug:chapter>", guide.guide_chapter, name="guide_chapter"),
    path("route_answer", guide.route_answer, name="route_answer"),
    path("consent", accounts.consent, name="consent"),
    path("monitoring-test", monitoring.monitoring_test, name="monitoring_test"),
    path("questionnaire_list", answering.questionnaire_list, name="questionnaire_list"),
    path("questionnaire/<int:questionnaire_id>", answering.screening, name="screening"),
    path("my_hearing", my_hearing.my_hearing, name="my_hearing"),
    path("comparisons/<int:questionnaire_id>", answering.hhi_comparison, name="hhi_comparison"),
    path("report", reports.health_report, name="health_report"),
    path("share", reports.share_report, name="share_report"),
    path("report/share", reports.report_share_create, name="report_share_create"),
    path(
        "report/share/<int:share_id>/cancel",
        reports.report_share_cancel,
        name="report_share_cancel",
    ),
    path("shared/<str:token>", reports.shared_cover, name="shared_cover"),
    path("shared/<str:token>/report", reports.shared_report, name="shared_report"),
    path("my_data/download", export.download_my_data, name="download_my_data"),
    path("account", accounts.account_settings, name="account_settings"),
    path("account/delete", accounts.delete_account, name="delete_account"),
    path("submission/<int:submission_id>", results.submission_result, name="result"),
    path("audiograms", audiograms.audiogram_list, name="audiogram_list"),
    path("audiograms/new", audiograms.audiogram_new, name="audiogram_new"),
    path("audiograms/compare", audiograms.audiogram_compare, name="audiogram_compare"),
    path("audiograms/<int:audiogram_id>", audiograms.audiogram_detail, name="audiogram_detail"),
    path("audiograms/<int:audiogram_id>/edit", audiograms.audiogram_edit, name="audiogram_edit"),
    path(
        "audiograms/<int:audiogram_id>/delete", audiograms.audiogram_delete, name="audiogram_delete"
    ),
    path(
        "add_to_home",
        TemplateView.as_view(template_name="screening/add_to_home.html"),
        name="add_to_home",
    ),
]
