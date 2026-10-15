from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from screening.models import Answer, Questionnaire, Submission
from screening.scoring import THRESHOLDS, get_advice


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
