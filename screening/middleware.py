from django.contrib.auth.views import redirect_to_login
from django.urls import reverse

# Pages a signed-in user may use before agreeing to the privacy notice
# (spec phase7_consent_privacy.md, question 4). Every other page is blocked, so a new
# page is covered without anyone remembering to add it.
# Downloading or deleting one's data is a right, not new processing
# (specs phase7_data_export.md Q5, phase7_account_deletion.md Q4).
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
