from rest_framework.permissions import BasePermission


class HasConsented(BasePermission):
    # Runs after IsAuthenticated, so anonymous requests keep their old 403.
    message = "請先同意隱私權說明。"

    def has_permission(self, request, view):
        return request.user.has_consented()
