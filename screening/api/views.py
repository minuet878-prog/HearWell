import uuid

from django.db import IntegrityError
from django.db.models import Prefetch
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response

from screening.api.serializers import (
    QuestionnaireDetailSerializer,
    QuestionnaireSerializer,
    SubmissionCreateSerializer,
    SubmissionDetailSerializer,
    SubmissionSerializer,
)
from screening.models import Answer, Question, Questionnaire
from screening.scoring import IOI_HA


class QuestionnaireList(ListAPIView):
    # IOI-HA has no API yet (spec phase4_ioi_ha.md); the trend chart only needs HHIE-S.
    queryset = Questionnaire.objects.exclude(code=IOI_HA).order_by("id")
    serializer_class = QuestionnaireSerializer


class QuestionnaireDetail(RetrieveAPIView):
    queryset = Questionnaire.objects.exclude(code=IOI_HA).prefetch_related(
        Prefetch("questions", queryset=Question.objects.select_related("questionnaire"))
    )
    serializer_class = QuestionnaireDetailSerializer


class SubmissionPagination(CursorPagination):
    page_size = 20
    # id gives equal created_at a stable order; without it forward paging repeats or skips rows.
    ordering = ("-created_at", "-id")


def _own_submissions(request):
    # Same query as the my_hearing page: scoped to request.user (IDOR) and scored once.
    # IOI-HA has no total or level, so it is left out until it has its own API.
    return (
        request.user.submissions.exclude(questionnaire__code=IOI_HA)
        .select_related("questionnaire")
        .with_scores()
    )


def _own_submission_details(request):
    answers = Answer.objects.select_related("question").order_by("question__question_number")
    return _own_submissions(request).prefetch_related(Prefetch("answers", queryset=answers))


def _find_by_key(user, key):
    # Scoped to the user: another user's key must never return their record (IDOR).
    return user.submissions.filter(idempotency_key=key).first()


def _same_content(submission, data):
    answers = {answer.question_id: answer.score for answer in submission.answers.all()}
    return (
        submission.questionnaire_id == data["questionnaire"].id
        and submission.wearing_hearing_aid == data["wearing_hearing_aid"]
        and answers == {answer["question"]: answer["score"] for answer in data["answers"]}
    )


def _parse_key(request):
    try:
        return uuid.UUID(request.headers.get("Idempotency-Key", ""))
    except ValueError:
        return None


class SubmissionList(ListAPIView):
    serializer_class = SubmissionSerializer
    pagination_class = SubmissionPagination

    def get_queryset(self):
        return _own_submissions(self.request)

    @extend_schema(
        request=SubmissionCreateSerializer,
        parameters=[
            OpenApiParameter(
                "Idempotency-Key",
                str,
                OpenApiParameter.HEADER,
                required=True,
                description="UUID made when answering starts; resend the same one on retry.",
            )
        ],
        responses={
            201: SubmissionDetailSerializer,
            200: OpenApiResponse(SubmissionDetailSerializer, "Retry: the first submission"),
            400: OpenApiResponse(description="Invalid answers or Idempotency-Key"),
            409: OpenApiResponse(description="Idempotency-Key used with different answers"),
        },
    )
    def post(self, request):
        key = _parse_key(request)
        if key is None:
            return Response({"detail": "缺少或無效的收據編號"}, status.HTTP_400_BAD_REQUEST)
        serializer = SubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        existing = _find_by_key(request.user, key)
        if existing is None:
            try:
                # save() is atomic, so a concurrent request with the same key that loses at the
                # unique constraint leaves nothing behind and can look up the winner.
                existing = data["formset"].save(
                    request.user,
                    data["questionnaire"],
                    wearing_hearing_aid=data["wearing_hearing_aid"],
                    idempotency_key=key,
                )
                created = True
            except IntegrityError:
                existing = _find_by_key(request.user, key)
                created = False
        else:
            created = False
        if not created and not _same_content(existing, data):
            return Response({"detail": "這個收據編號已經用過"}, status.HTTP_409_CONFLICT)
        # Same query and serializer as GET /api/submissions/{id}/, so the bodies match.
        submission = _own_submission_details(request).get(pk=existing.pk)
        return Response(
            SubmissionDetailSerializer(submission).data,
            status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class SubmissionDetail(RetrieveAPIView):
    serializer_class = SubmissionDetailSerializer

    def get_queryset(self):
        return _own_submission_details(self.request)
