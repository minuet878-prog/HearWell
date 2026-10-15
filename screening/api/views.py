from django.db.models import Prefetch
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import CursorPagination

from screening.api.serializers import (
    QuestionnaireSerializer,
    SubmissionDetailSerializer,
    SubmissionSerializer,
)
from screening.models import Answer, Questionnaire


class QuestionnaireList(ListAPIView):
    queryset = Questionnaire.objects.order_by("id")
    serializer_class = QuestionnaireSerializer


class SubmissionPagination(CursorPagination):
    page_size = 20
    # id gives equal created_at a stable order; without it forward paging repeats or skips rows.
    ordering = ("-created_at", "-id")


def _own_submissions(request):
    # Same query as the my_hearing page: scoped to request.user (IDOR) and scored once.
    return request.user.submissions.select_related("questionnaire").with_scores()


class SubmissionList(ListAPIView):
    serializer_class = SubmissionSerializer
    pagination_class = SubmissionPagination

    def get_queryset(self):
        return _own_submissions(self.request)


class SubmissionDetail(RetrieveAPIView):
    serializer_class = SubmissionDetailSerializer

    def get_queryset(self):
        answers = Answer.objects.select_related("question").order_by("question__question_number")
        return _own_submissions(self.request).prefetch_related(
            Prefetch("answers", queryset=answers)
        )
