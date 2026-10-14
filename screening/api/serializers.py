from rest_framework import serializers

from screening.models import Questionnaire


class QuestionnaireSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="questionnaire_name")

    class Meta:
        model = Questionnaire
        fields = ("id", "code", "name")
