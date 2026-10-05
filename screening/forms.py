from django import forms
from django.forms import BaseFormSet, formset_factory

from screening.models import Question, Score


class AnswerForm(forms.Form):
    score = forms.TypedChoiceField(
        choices=Score.choices,
        coerce=int,
        widget=forms.RadioSelect(attrs={"class": "score-radio-group"}),
    )
    question_id = forms.ModelChoiceField(
        queryset=Question.objects.all(), widget=forms.HiddenInput()
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
