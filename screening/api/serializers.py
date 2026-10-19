from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from screening.audiogram import (
    AIR_FREQUENCIES,
    BONE_FREQUENCIES,
    DB_MAX,
    DB_MIN,
    DB_STEP,
)
from screening.forms import AnswerFormSet, HearingAidForm, answer_choices
from screening.models import (
    Answer,
    Audiogram,
    AudiogramPoint,
    Conduction,
    Ear,
    Question,
    Questionnaire,
    Submission,
)
from screening.scoring import IOI_HA, THRESHOLDS, get_advice
from screening.ssq12 import CODE as SSQ12


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
    value = serializers.IntegerField(allow_null=True)
    label = serializers.CharField()


class ScaleSerializer(serializers.Serializer):
    min_label = serializers.CharField()
    max_label = serializers.CharField()


class QuestionSerializer(serializers.ModelSerializer):
    scale = ScaleSerializer(required=False, allow_null=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.questionnaire.code != SSQ12:
            data.pop("scale")
        return data

    number = serializers.IntegerField(source="question_number")
    text = serializers.CharField(source="question_text")
    choices = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ("id", "number", "text", "choices", "scale")

    @extend_schema_field(ChoiceSerializer(many=True))
    def get_choices(self, question):
        # Same choices the answer form accepts.
        return [
            {"value": None if value == "na" else value, "label": label}
            for value, label in answer_choices(question)
        ]


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
    average_score = serializers.DecimalField(
        source="ssq_average", max_digits=3, decimal_places=1, allow_null=True, required=False
    )
    average_unavailable_reason = serializers.CharField(
        source="ssq_unavailable_reason", allow_null=True, required=False
    )
    questionnaire = QuestionnaireSummarySerializer()
    wearing_hearing_aid = serializers.BooleanField(allow_null=True)
    # Scores and level come from Submission's single scoring path, never recomputed here.
    scores = ScoresSerializer(source="*", allow_null=True)
    level = LevelSerializer(source="classified", allow_null=True)

    class Meta:
        model = Submission
        fields = (
            "id",
            "created_at",
            "questionnaire",
            "wearing_hearing_aid",
            "scores",
            "level",
            "average_score",
            "average_unavailable_reason",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.questionnaire.code == SSQ12:
            data["scores"] = None
        else:
            data.pop("average_score")
            data.pop("average_unavailable_reason")
        return data


class AnswerSerializer(serializers.ModelSerializer):
    score = serializers.IntegerField(min_value=0, max_value=10, allow_null=True)
    number = serializers.IntegerField(source="question.question_number")
    text = serializers.CharField(source="question.question_text")
    label = serializers.CharField(source="get_answer_display")

    class Meta:
        model = Answer
        fields = ("number", "text", "score", "label")


class SubmissionDetailSerializer(SubmissionSerializer):
    advice = serializers.SerializerMethodField()
    answers = AnswerSerializer(many=True)

    class Meta(SubmissionSerializer.Meta):
        fields = (*SubmissionSerializer.Meta.fields, "advice", "answers")

    def get_advice(self, submission) -> str | None:
        if submission.questionnaire.code == SSQ12:
            return None
        return get_advice(submission.classified["level"], submission.questionnaire.code)


WEARING_MESSAGE = HearingAidForm.base_fields["wearing_hearing_aid"].error_messages["required"]


class StrictBooleanField(serializers.BooleanField):
    # JSON true/false only; DRF's BooleanField also takes 1, "yes", "on" for HTML forms.
    def to_internal_value(self, data):
        if not isinstance(data, bool):
            self.fail("invalid", input=data)
        return data


class AnswerInputSerializer(serializers.Serializer):
    question = serializers.IntegerField()
    score = serializers.IntegerField(allow_null=True)


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
        if attrs["questionnaire"].code == SSQ12:
            for answer in self.initial_data.get("answers", []):
                value = answer.get("score")
                if value is not None and type(value) is not int:
                    raise serializers.ValidationError({"answers": "請選擇 0–10 整數或不適用"})
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
            data[f"form-{index}-score"] = (
                "na"
                if attrs["questionnaire"].code == SSQ12 and answer["score"] is None
                else answer["score"]
            )
        formset = AnswerFormSet(questions=questions, data=data)
        if not formset.is_valid():
            raise serializers.ValidationError({"answers": list(formset.non_form_errors())})
        attrs["formset"] = formset
        return attrs


class AudiogramPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = AudiogramPoint
        fields = ("ear", "conduction", "frequency", "db", "no_response", "masked")


class EarResultSerializer(serializers.Serializer):
    pta = serializers.FloatField(allow_null=True)
    degree = serializers.CharField(allow_null=True)
    type = serializers.CharField(allow_null=True)
    no_response = serializers.BooleanField()


class InterpretationSerializer(serializers.Serializer):
    right = EarResultSerializer()
    left = EarResultSerializer()


class AudiogramSerializer(serializers.ModelSerializer):
    points = AudiogramPointSerializer(many=True)
    # Computed by Audiogram.interpretation(), never in the client.
    interpretation = InterpretationSerializer()

    class Meta:
        model = Audiogram
        fields = ("id", "tested_on", "created_at", "points", "interpretation")


FREQUENCIES = {Conduction.AIR: AIR_FREQUENCIES, Conduction.BONE: BONE_FREQUENCIES}


class AudiogramPointInputSerializer(serializers.Serializer):
    ear = serializers.ChoiceField(choices=Ear.choices)
    conduction = serializers.ChoiceField(choices=Conduction.choices)
    frequency = serializers.IntegerField()
    db = serializers.IntegerField()
    no_response = StrictBooleanField(default=False)
    masked = StrictBooleanField(default=False)

    def validate(self, attrs):
        conduction, db = attrs["conduction"], attrs["db"]
        if attrs["frequency"] not in FREQUENCIES[conduction]:
            raise serializers.ValidationError("這個頻率不能標記")
        if not DB_MIN <= db <= DB_MAX[conduction] or db % DB_STEP:
            raise serializers.ValidationError("dB 值不正確")
        if attrs["no_response"] and db != DB_MAX[conduction]:
            raise serializers.ValidationError("無反應的點要標在最大值")
        return attrs


class AudiogramCreateSerializer(serializers.Serializer):
    DATE_REQUIRED = "請填寫檢查日期"

    tested_on = serializers.DateField(
        error_messages={"required": DATE_REQUIRED, "null": DATE_REQUIRED}
    )
    points = serializers.ListField(
        child=AudiogramPointInputSerializer(),
        allow_empty=False,
        error_messages={"empty": "請至少標記一個點"},
    )

    def validate_tested_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("檢查日期不能是未來")
        return value

    def validate_points(self, points):
        keys = [(p["ear"], p["conduction"], p["frequency"]) for p in points]
        if len(set(keys)) != len(keys):
            raise serializers.ValidationError("同一耳、同一導程、同一頻率只能有一個點")
        return points
