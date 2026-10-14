from rest_framework.generics import ListAPIView

from screening.api.serializers import QuestionnaireSerializer
from screening.models import Questionnaire


class QuestionnaireList(ListAPIView):
    queryset = Questionnaire.objects.order_by("id")
    serializer_class = QuestionnaireSerializer
