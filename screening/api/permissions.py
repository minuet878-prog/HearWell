from rest_framework.permissions import BasePermission, IsAuthenticated

from screening.models import Questionnaire


class HasConsented(BasePermission):
    # Runs after IsAuthenticated, so anonymous requests keep their old 403.
    message = "請先同意隱私權說明。"

    def has_permission(self, request, view):
        return request.user.has_consented()


class GuestQuestionnaire(BasePermission):
    # A guest answers HHIE-S or HHIA-S on the React answer page (spec #492): their questions are
    # open to anyone. Asked only on a real request, so drawing the schema reads no table.
    def has_permission(self, request, view):
        return (
            not request.user.is_authenticated
            and Questionnaire.objects.for_guests().filter(pk=view.kwargs.get("pk")).exists()
        )


# Every other questionnaire's questions still need an account that has agreed.
GUEST_OR_CONSENTED = GuestQuestionnaire | (IsAuthenticated & HasConsented)
