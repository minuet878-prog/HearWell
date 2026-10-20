from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.forms import BaseFormSet, formset_factory
from django.utils import timezone

from screening.models import Answer, Question, Submission, User

ROC_OFFSET = 1911  # 民國 year + 1911 = Western year


class RegisterForm(UserCreationForm):
    email = forms.EmailField(label="電子郵件")
    roc_birth_year = forms.CharField(
        label="出生年",
        required=False,
        help_text="選填。用來推薦適合您年齡的問卷，不會公開。",
        widget=forms.TextInput(attrs={"inputmode": "numeric", "maxlength": 3}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        if not self.is_bound:
            self.fields["username"].widget.attrs.pop("autofocus", None)

    def clean_roc_birth_year(self):
        value = self.cleaned_data["roc_birth_year"]
        if not value:
            return None
        max_roc = date.today().year - 18 - ROC_OFFSET
        # isdecimal() accepts exactly what int() accepts; isdigit() also lets through "²".
        if not value.isdecimal() or not 1 <= int(value) <= max_roc:
            raise forms.ValidationError(f"請輸入民國 1 到 {max_roc} 年之間的數字")
        return int(value)

    def save(self, commit=True):
        user = super().save(commit=False)
        roc = self.cleaned_data["roc_birth_year"]
        user.birth_year = None if roc is None else roc + ROC_OFFSET
        if commit:
            user.save()
        return user


def answer_choices(question):
    return question.questionnaire.definition.choices(question.question_number)


class DeleteAccountForm(forms.Form):
    # strip=False like Django's login and register forms: spaces are part of a password.
    password = forms.CharField(strip=False, error_messages={"required": "請輸入密碼"})

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("密碼不正確")
        return password


class AnswerForm(forms.Form):
    score = forms.TypedChoiceField(
        coerce=int,
        widget=forms.RadioSelect(attrs={"class": "choice-group"}),
        error_messages={"required": "這一題還沒有回答"},
    )
    question_id = forms.ModelChoiceField(
        queryset=Question.objects.all(), widget=forms.HiddenInput()
    )

    def __init__(self, *args, choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["score"].choices = choices
        self.fields["score"].coerce = lambda value: None if value == "na" else int(value)


class HearingAidForm(forms.Form):
    wearing_hearing_aid = forms.TypedChoiceField(
        choices=((True, "有戴"), (False, "沒戴")),
        coerce=lambda value: value == "True",
        widget=forms.RadioSelect(attrs={"class": "choice-group"}),
        error_messages={
            "required": "請選擇這次有沒有戴助聽器",
            "invalid_choice": "請選擇這次有沒有戴助聽器",
        },
    )


class BaseAnswerFormSet(BaseFormSet):
    def __init__(
        self,
        *args,
        questions,
        **kwargs,
    ):
        self.questions = questions
        # A questionnaire has a fixed set of questions, so no form may be left blank. Django lets
        # "extra" forms (index >= INITIAL_FORMS) pass empty; a tampered TOTAL_FORMS then reached
        # clean() with no question_id and returned 500.
        kwargs["form_kwargs"] = {**kwargs.get("form_kwargs", {}), "empty_permitted": False}
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        # Forms past the real questions (tampered TOTAL_FORMS) get no choices, so they fail.
        if index is not None and index < len(self.questions):
            kwargs["choices"] = answer_choices(self.questions[index])
        return kwargs

    def clean(self):
        if any(self.errors):
            raise forms.ValidationError("表單資料有誤，請重新確認每一題的作答")
        expected = [question.id for question in self.questions]
        submitted = []
        for form in self:
            submitted.append(form.cleaned_data["question_id"].id)
        if len(submitted) != len(set(submitted)):
            raise forms.ValidationError("重複題目")
        elif set(submitted) != set(expected):
            raise forms.ValidationError("有題目沒有作答")

    def save(self, user, questionnaire, **extra):
        # All or nothing: no submission without its answers.
        with transaction.atomic():
            submission = Submission.objects.create(user=user, questionnaire=questionnaire, **extra)
            Answer.objects.bulk_create(
                Answer(
                    submission=submission,
                    question=form.cleaned_data["question_id"],
                    score=form.cleaned_data["score"],
                )
                for form in self
            )
        return submission


AnswerFormSet = formset_factory(AnswerForm, formset=BaseAnswerFormSet, extra=0)


class AgeGroupForm(forms.Form):
    age_group = forms.ChoiceField(
        label="您目前的實際年齡？",
        choices=(("adult", "18–64 歲"), ("older", "65 歲以上")),
        widget=forms.RadioSelect(attrs={"class": "choice-group"}),
        error_messages={"required": "請選擇您的年齡區間"},
    )


class ComparisonRecordField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        result = obj.questionnaire.definition.comparison.record_result(obj)
        when = timezone.localtime(obj.created_at).strftime("%Y/%m/%d %H:%M")
        return f"{when}，{obj.get_wearing_hearing_aid_display()}，{result}（紀錄 {obj.pk}）"


class HhiComparisonForm(forms.Form):
    unaided = ComparisonRecordField(
        label="未配戴紀錄",
        queryset=Submission.objects.none(),
        empty_label="請選擇未配戴紀錄",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    aided = ComparisonRecordField(
        label="配戴紀錄",
        queryset=Submission.objects.none(),
        empty_label="請選擇配戴紀錄",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, user, questionnaire, **kwargs):
        super().__init__(*args, **kwargs)
        records = user.submissions.filter(questionnaire=questionnaire).select_related(
            "questionnaire"
        )
        records = questionnaire.definition.comparison.records(records)
        self.fields["unaided"].queryset = records.filter(wearing_hearing_aid=False)
        self.fields["aided"].queryset = records.filter(wearing_hearing_aid=True)
