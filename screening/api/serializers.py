from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from screening.forms import AnswerFormSet, HearingAidForm, answer_choices
from screening.models import Answer, Question, Questionnaire, Submission
from screening.scoring import IOI_HA, THRESHOLDS, get_advice


class QuestionnaireSummarySerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="questionnaire_name")

    class Meta:
        model = Questionnaire
        fields = ("code", "name")


class LevelBandSerializer(serializers.Serializer):
    code = serializers.CharField()
    text = serializers.CharField()
    max = serializers.IntegerField()


class QuestionnaireSerializer(QuestionnaireSummarySerializer):
    levels = serializers.SerializerMethodField()

    class Meta(QuestionnaireSummarySerializer.Meta):
        fields = ("id", "code", "name", "levels")

    @extend_schema_field(LevelBandSerializer(many=True))
    def get_levels(self, questionnaire):
        # Read straight from the one threshold table so the chart's bands match classify().
        return [
            {"code": level, "text": text, "max": upper}
            for upper, text, level in THRESHOLDS.get(questionnaire.code, ())
        ]


class ChoiceSerializer(serializers.Serializer):
    value = serializers.IntegerField()
    label = serializers.CharField()


class QuestionSerializer(serializers.ModelSerializer):
    number = serializers.IntegerField(source="question_number")
    text = serializers.CharField(source="question_text")
    choices = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ("id", "number", "text", "choices")

    @extend_schema_field(ChoiceSerializer(many=True))
    def get_choices(self, question):
        # Same choices the answer form accepts.
        return [{"value": value, "label": label} for value, label in answer_choices(question)]


class QuestionnaireDetailSerializer(QuestionnaireSerializer):
    questions = QuestionSerializer(many=True)

    class Meta(QuestionnaireSerializer.Meta):
        fields = (*QuestionnaireSerializer.Meta.fields, "questions")


class ScoresSerializer(serializers.Serializer):
    total = serializers.IntegerField(source="total_answer_score")
    emotional = serializers.IntegerField(source="emotional_score")
    social = serializers.IntegerField(source="social_score")


class LevelSerializer(serializers.Serializer):
    code = serializers.CharField(source="level")
    text = serializers.CharField()


class SubmissionSerializer(serializers.ModelSerializer):
    questionnaire = QuestionnaireSummarySerializer()
    wearing_hearing_aid = serializers.BooleanField(allow_null=True)
    # Scores and level come from Submission's single scoring path, never recomputed here.
    scores = ScoresSerializer(source="*")
    level = LevelSerializer(source="classified")

    class Meta:
        model = Submission
        fields = ("id", "created_at", "questionnaire", "wearing_hearing_aid", "scores", "level")


class AnswerSerializer(serializers.ModelSerializer):
    number = serializers.IntegerField(source="question.question_number")
    text = serializers.CharField(source="question.question_text")
    label = serializers.CharField(source="get_score_display")

    class Meta:
        model = Answer
        fields = ("number", "text", "score", "label")


class SubmissionDetailSerializer(SubmissionSerializer):
    advice = serializers.SerializerMethodField()
    answers = AnswerSerializer(many=True)

    class Meta(SubmissionSerializer.Meta):
        fields = (*SubmissionSerializer.Meta.fields, "advice", "answers")

    def get_advice(self, submission) -> str:
        return get_advice(submission.classified["level"])


WEARING_MESSAGE = HearingAidForm.base_fields["wearing_hearing_aid"].error_messages["required"]


class StrictBooleanField(serializers.BooleanField):
    # JSON true/false only; DRF's BooleanField also takes 1, "yes", "on" for HTML forms.
    def to_internal_value(self, data):
        if not isinstance(data, bool):
            self.fail("invalid", input=data)
        return data


class AnswerInputSerializer(serializers.Serializer):
    question = serializers.IntegerField()
    score = serializers.IntegerField()


class SubmissionCreateSerializer(serializers.Serializer):
    # IOI-HA needs norm grouping and has no API yet (spec phase5_api_submit.md).
    questionnaire = serializers.PrimaryKeyRelatedField(
        queryset=Questionnaire.objects.exclude(code=IOI_HA)
    )
    wearing_hearing_aid = StrictBooleanField(
        error_messages={
            "required": WEARING_MESSAGE,
            "null": WEARING_MESSAGE,
            "invalid": WEARING_MESSAGE,
        }
    )
    answers = serializers.ListField(child=AnswerInputSerializer())

    def validate(self, attrs):
        # The rules live in the answer formset, shared with the web form; this only feeds it.
        questions = list(attrs["questionnaire"].questions.all())
        if not questions:
            raise serializers.ValidationError({"questionnaire": "這份問卷沒有題目"})
        # The formset pairs form i with question i for choices, so send answers in question order.
        position = {question.id: index for index, question in enumerate(questions)}
        answers = sorted(
            attrs["answers"], key=lambda answer: position.get(answer["question"], len(questions))
        )
        data = {"form-TOTAL_FORMS": len(answers), "form-INITIAL_FORMS": 0}
        for index, answer in enumerate(answers):
            data[f"form-{index}-question_id"] = answer["question"]
            data[f"form-{index}-score"] = answer["score"]
        formset = AnswerFormSet(questions=questions, data=data)
        if not formset.is_valid():
            raise serializers.ValidationError({"answers": list(formset.non_form_errors())})
        attrs["formset"] = formset
        return attrs
