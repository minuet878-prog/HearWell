from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Answer, Question, Questionnaire, Submission, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = (
        *UserAdmin.fieldsets,
        ("個人資料", {"fields": ("birth_date",)}),
    )
    add_fieldsets = (
        *UserAdmin.add_fieldsets,
        ("個人資料", {"fields": ("birth_date",)}),
    )


@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        # code picks the scoring thresholds; changing it would rewrite past classifications
        if obj is not None and obj.submissions.exists():
            return ("code",)
        return ()


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("question_number", "category", "questionnaire", "question_text")
    ordering = ("question_number",)

    def get_readonly_fields(self, request, obj=None):
        # Answered questions are immutable; publish a new questionnaire instead
        if obj is not None and obj.answers.exists():
            return ("questionnaire", "question_text", "question_number", "category")
        return ()


class ViewOnlyAdmin(admin.ModelAdmin):
    # Screening records are health history; admins may look but not rewrite them
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Answer, ViewOnlyAdmin)
admin.site.register(Submission, ViewOnlyAdmin)
