from django.contrib.auth.views import redirect_to_login
from django.urls import reverse

# Pages a signed-in user may use before agreeing to the privacy notice
# (spec phase7_consent_privacy.md, question 4). Every other page is blocked, so a new
# page is covered without anyone remembering to add it.
# Downloading or deleting one's data is a right, not new processing
# (specs phase7_data_export.md Q5, phase7_account_deletion.md Q4). The family guide holds no
# personal data at all (spec phase8_c1_family_guide.md), and neither do the zone's pages on an
# elder who refuses, on going along to a visit, on what a subsidy still needs and on its deadlines,
# which are for family too and keep nothing (spec #426, #429, #430, #431, #432). The hearing-aid
# guide's chapters show none (spec #218), and keep a 看過 only for a user who has agreed (spec
# #291), so before that they record nothing. Account settings is the way to those two
# rights (spec phase9_ui_refresh_3_structure.md). A shared report is opened by family,
# who may have an account of their own (spec phase8_c1_family_share.md). The Q&A assistant
# reads nobody's records and its answers are the same for everyone (ADR 0032), and family send
# each other its answer links (the owner's call for spec #396, 2026-10-27); typing a question
# there is part of it (#399). The zone's page on how to talk with him came out of the family guide
# with the same words (#469). The forgot-password pages are part of signing in, like the login and
# register pages (owner's acceptance of spec #355, 2026-11-14); so is signing in or up with Google,
# which makes nothing before the name page (spec #505).
OPEN_PAGES = {
    "index",
    "privacy",
    "consent",
    "add_to_home",
    "login",
    "google_start",
    "google_callback",
    "google_name",
    "google_same_email",
    "register",
    "password_reset",
    "password_reset_sent",
    "password_reset_confirm",
    "logout",
    "download_my_data",
    "delete_account",
    "account_settings",
    "family_guide",
    "family_talk",
    "family_reluctant",
    "family_hearing_aids",
    "family_visits",
    "family_subsidy_check",
    "family_deadlines",
    "guide_chapter",
    "shared_cover",
    "shared_report",
    "qa_home",
    "qa_topic",
    "qa_answer",
    "qa_search",
    "qa_results",
}


class ConsentRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        # Namespaced URLs guard themselves: the API with HasConsented, admin and the
        # debug toolbar are staff only.
        if not request.user.is_authenticated or match.namespaces:
            return None
        if match.url_name in OPEN_PAGES or request.user.has_consented():
            return None
        # 確認本人 before deleting the account: without a password it is the only way to delete
        # (spec #505 acceptance 30), and deleting is open before agreeing.
        if match.url_name == "confirm_identity" and request.GET.get("action") == "delete_account":
            return None
        return redirect_to_login(request.get_full_path(), reverse("consent"))
