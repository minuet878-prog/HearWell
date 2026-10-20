from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Answer, Question, Questionnaire, Submission, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = (
        *UserAdmin.fieldsets,
        ("個人資料", {"fields": ("birth_year",)}),
    )
    add_fieldsets = (
        *UserAdmin.add_fieldsets,
        ("個人資料", {"fields": ("birth_year",)}),
    )


class ViewOnlyAdmin(admin.ModelAdmin):
    # Screening records are health history; admins may look but not rewrite them
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Questionnaires and questions come from their definitions (ADR 0005); a new wording is a new
# definition with a new code, never an admin edit.
admin.site.register(Questionnaire, ViewOnlyAdmin)


@admin.register(Question)
class QuestionAdmin(ViewOnlyAdmin):
    list_display = ("question_number", "category", "questionnaire", "question_text")
    ordering = ("question_number",)


admin.site.register(Answer, ViewOnlyAdmin)
admin.site.register(Submission, ViewOnlyAdmin)
