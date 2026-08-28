from django import forms

from screening.models import Answer, Question


class AnswerForm(forms.Form):
    score = forms.TypedChoiceField(choices=Answer.Score.choices, coerce=int)
    question_id = forms.ModelChoiceField(
        queryset=Question.objects.all(), widget=forms.HiddenInput()
    )
