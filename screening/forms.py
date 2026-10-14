from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.forms import BaseFormSet, formset_factory

from screening.models import Question, Score, User

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


class AnswerForm(forms.Form):
    score = forms.TypedChoiceField(
        choices=Score.choices,
        coerce=int,
        widget=forms.RadioSelect(attrs={"class": "score-radio-group"}),
    )
    question_id = forms.ModelChoiceField(
        queryset=Question.objects.all(), widget=forms.HiddenInput()
    )


class HearingAidForm(forms.Form):
    wearing_hearing_aid = forms.TypedChoiceField(
        choices=((True, "有戴"), (False, "沒戴")),
        coerce=lambda value: value == "True",
        widget=forms.RadioSelect,
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
        super().__init__(*args, **kwargs)

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


AnswerFormSet = formset_factory(AnswerForm, formset=BaseAnswerFormSet, extra=0)
