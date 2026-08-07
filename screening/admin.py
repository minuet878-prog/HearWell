from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

# Register your models here.
from .models import Answer, Question, Questionnaire, Submission, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("birth_date", {"fields": ("birth_date",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("birth_date", {"fields": ("birth_date",)}),)


admin.site.register(Questionnaire)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("question_number", "category", "questionnaire", "question_text")
    ordering = ("question_number",)


admin.site.register(Answer)
admin.site.register(Submission)
