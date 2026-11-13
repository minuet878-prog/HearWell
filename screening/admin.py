from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Answer,
    GuestMonth,
    Question,
    QuestionLog,
    QuestionLogMonth,
    Questionnaire,
    SignInMethod,
    Submission,
    User,
    count_and_delete_questions,
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


# Spec #505: a sign-in method is made and removed by its owner only; an admin edit could hand an
# account to another Google.
@admin.register(SignInMethod)
class SignInMethodAdmin(ViewOnlyAdmin):
    list_display = ("user", "provider", "created_at", "used_to_register")


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
        # #401: besides the VPS's daily 02:30 run (#452), opening the list clears those past
        # 90 days first.
        purge_question_log()
        return super().changelist_view(request, extra_context)

    # The owner's call (2026-10-27): one deleted early, alone or selected with others, is still
    # counted in its month's stats first, the same way the 90-day purge counts.
    def delete_model(self, request, obj):
        count_and_delete_questions(QuestionLog.objects.filter(pk=obj.pk))

    def delete_queryset(self, request, queryset):
        count_and_delete_questions(queryset)

    @admin.display(description="結果")
    def result(self, log):
        return log.faq_code or "沒對到"


@admin.register(QuestionLogMonth)
class QuestionLogMonthAdmin(ViewOnlyAdmin):
    # #401 (ADR 0035): counted only as questions go, so the owner reads the months in a row.
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


@admin.register(GuestMonth)
class GuestMonthAdmin(ViewOnlyAdmin):
    # Spec #492 (#500): the owner reads whether going without an account brings more people in.
    list_display = ("month_label", "completed", "saved")
    ordering = ("-month",)

    @admin.display(description="月份", ordering="month")
    def month_label(self, counts):
        return str(counts)
