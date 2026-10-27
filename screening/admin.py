from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Answer,
    Question,
    QuestionLog,
    QuestionLogMonth,
    Questionnaire,
    Submission,
    User,
    purge_question_log,
)


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


class MatchedFilter(admin.SimpleListFilter):
    # ADR 0035: the questions that matched nothing are the ones the owner ticks a reason for.
    title = "結果"
    parameter_name = "matched"

    def lookups(self, request, model_admin):
        return (("no", "沒對到"), ("yes", "有對到"))

    def queryset(self, request, queryset):
        if self.value() == "no":
            return queryset.filter(faq_code="")
        if self.value() == "yes":
            return queryset.exclude(faq_code="")
        return queryset


@admin.register(QuestionLog)
class QuestionLogAdmin(admin.ModelAdmin):
    # ADR 0034, 0035 (#400): the first records the admin may change or delete. The owner reads
    # them each month and ticks why one matched nothing; what was typed and what it matched
    # stay as they were. One with a name or a record number in it can go before its 90 days.
    list_display = ("question", "result", "reason", "created_at")
    list_filter = (MatchedFilter, "reason")
    ordering = ("-created_at", "-id")
    fields = ("question", "result", "reason", "created_at")
    readonly_fields = ("question", "result", "created_at")

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        # #401: there is no scheduler, so opening the list clears those past 90 days first.
        purge_question_log()
        return super().changelist_view(request, extra_context)

    @admin.display(description="結果")
    def result(self, log):
        return log.faq_code or "沒對到"


@admin.register(QuestionLogMonth)
class QuestionLogMonthAdmin(ViewOnlyAdmin):
    # #401 (ADR 0035): counted by the purge alone, so the owner reads the months in a row.
    list_display = (
        "month_label",
        "typed",
        "matched",
        "different_wording",
        "not_in_faq",
        "should_not_answer",
    )
    ordering = ("-month",)

    @admin.display(description="月份", ordering="month")
    def month_label(self, stats):
        return str(stats)
