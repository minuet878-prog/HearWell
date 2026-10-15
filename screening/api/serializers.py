from rest_framework import serializers

from screening.models import Answer, Questionnaire, Submission
from screening.scoring import get_advice


class QuestionnaireSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="questionnaire_name")

    class Meta:
        model = Questionnaire
        fields = ("id", "code", "name")


class QuestionnaireSummarySerializer(QuestionnaireSerializer):
    class Meta(QuestionnaireSerializer.Meta):
        fields = ("code", "name")


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
