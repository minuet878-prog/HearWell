from django import forms
from django.forms import formset_factory

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


AnswerFormSet = formset_factory(AnswerForm, extra=0)
