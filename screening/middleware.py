from django.contrib.auth.views import redirect_to_login
from django.urls import reverse

# Pages a signed-in user may use before agreeing to the privacy notice
# (spec phase7_consent_privacy.md, question 4). Every other page is blocked, so a new
# page is covered without anyone remembering to add it.
# Downloading or deleting one's data is a right, not new processing
# (specs phase7_data_export.md Q5, phase7_account_deletion.md Q4). The family guide holds no
# personal data at all (spec phase8_c1_family_guide.md). The hearing-aid guide's chapters show
# none (spec #218), and keep a 看過 only for a user who has agreed (spec #291), so before that
# they record nothing. Account settings is the way to those two
# rights (spec phase9_ui_refresh_3_structure.md). A shared report is opened by family,
# who may have an account of their own (spec phase8_c1_family_share.md). The Q&A assistant
# reads nobody's records and its answers are the same for everyone (ADR 0032), and family send
# each other its answer links (the owner's call for spec #396, 2026-10-27).
OPEN_PAGES = {
    "index",
    "privacy",
    "consent",
    "add_to_home",
    "login",
    "register",
    "logout",
    "download_my_data",
    "delete_account",
    "account_settings",
    "family_guide",
    "guide_chapter",
    "shared_cover",
    "shared_report",
    "qa_home",
    "qa_topic",
    "qa_answer",
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
        return redirect_to_login(request.get_full_path(), reverse("consent"))
