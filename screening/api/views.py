import uuid

from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.template.loader import render_to_string
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import Throttled
from rest_framework.generics import GenericAPIView, ListAPIView, RetrieveAPIView
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from screening.api.serializers import (
    AudiogramCreateSerializer,
    AudiogramSerializer,
    GuestAnswersSerializer,
    GuestScoreSerializer,
    QuestionnaireDetailSerializer,
    QuestionnaireSerializer,
    SubmissionCreateSerializer,
    SubmissionDetailSerializer,
    SubmissionSerializer,
)
from screening.models import (
    Answer,
    Audiogram,
    AudiogramPoint,
    Question,
    Questionnaire,
    count_guest,
)
from screening.questionnaires.ioi_ha import CODE as IOI_HA
from screening.scoring import TREND_STATUS_TEXT


class QuestionnaireList(ListAPIView):
    serializer_class = QuestionnaireSerializer

    def get_queryset(self):
        # IOI-HA has no API yet (spec phase4_ioi_ha.md); the trend chart only needs HHIE-S.
        # Built per request: defined() reads the definitions then, not at import.
        return Questionnaire.objects.defined().exclude(code=IOI_HA).order_by("id")


class QuestionnaireDetail(RetrieveAPIView):
    serializer_class = QuestionnaireDetailSerializer

    def get_permissions(self):
        # A guest answers HHIE-S or HHIA-S on the React answer page (spec #492): their questions
        # are open to anyone; every other questionnaire's still need an account.
        if (
            not self.request.user.is_authenticated
            and Questionnaire.objects.for_guests().filter(pk=self.kwargs.get("pk")).exists()
        ):
            return []
        return super().get_permissions()

    def get_queryset(self):
        return Questionnaire.objects.defined().prefetch_related(
            Prefetch("questions", queryset=Question.objects.select_related("questionnaire"))
        )


class SubmissionPagination(CursorPagination):
    page_size = 20
    # id gives equal created_at a stable order; without it forward paging repeats or skips rows.
    ordering = ("-created_at", "-id")


def _own_submissions(request, with_ioi_ha=False):
    # Same query as the my_hearing page: scoped to request.user (IDOR) and scored once.
    # IOI-HA has no total or level, so lists and GET leave it out until it has its own API;
    # a submit still answers with the record it saved (#245).
    submissions = request.user.submissions.defined()
    if not with_ioi_ha:
        submissions = submissions.exclude(questionnaire__code=IOI_HA)
    return submissions.select_related("questionnaire").with_scores()


def _own_submission_details(request, with_ioi_ha=False):
    answers = Answer.objects.select_related("question__questionnaire").order_by(
        "question__question_number"
    )
    return _own_submissions(request, with_ioi_ha).prefetch_related(
        Prefetch("answers", queryset=answers)
    )


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
        # With the answers: SADL's scores are worked out from them (submission.result.satisfaction).
        return _own_submission_details(self.request)

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
        serializer = SubmissionCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        existing = request.user.submissions.find_by_key(key)
        if existing is None:
            try:
                # save() is atomic, so a concurrent request with the same key that loses at the
                # unique constraint leaves nothing behind and can look up the winner.
                existing = data["formset"].save(
                    request.user,
                    data["questionnaire"],
                    wearing_hearing_aid=data["wearing_hearing_aid"],
                    idempotency_key=key,
                    **data.get("norm", {}),
                )
                created = True
            except IntegrityError:
                existing = request.user.submissions.find_by_key(key)
                created = False
        else:
            created = False
        if not created and not _same_content(existing, data):
            return Response({"detail": "這個收據編號已經用過"}, status.HTTP_409_CONFLICT)
        # A guest result newly saved counts (#500); sent again and found, it does not.
        if created and data["from_guest"]:
            count_guest("saved")
        # Same query and serializer as GET /api/submissions/{id}/, so the bodies match.
        submission = _own_submission_details(request, with_ioi_ha=True).get(pk=existing.pk)
        return Response(
            SubmissionDetailSerializer(submission).data,
            status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class GuestScoreThrottle(SimpleRateThrottle):
    # Spec #492: 40 an hour from one connection source (DRF's get_ident), counted in the server's
    # memory cache only, never in the database. 40, not the grill's 20 (implementation decision
    # I1): one questionnaire scores twice, on the answer page and on the guest result page.
    scope = "guest_score"
    rate = "40/hour"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


GUEST_LIMIT = "剛才做了很多次，請過一小時再試。您的作答沒有不見。"


class GuestScore(GenericAPIView):
    """Scores a guest's HHIE-S or HHIA-S answers without saving anything (spec #492, ADR 0055):
    no account, no consent, nothing written."""

    serializer_class = GuestAnswersSerializer
    permission_classes = ()
    throttle_classes = (GuestScoreThrottle,)

    def throttled(self, request, wait):
        raise Throttled(detail=GUEST_LIMIT)

    @extend_schema(
        responses={
            200: GuestScoreSerializer,
            400: OpenApiResponse(description="Invalid answers, or not HHIE-S or HHIA-S"),
            429: OpenApiResponse(description="More than 40 in an hour from this address"),
        },
    )
    def post(self, request):
        serializer = GuestAnswersSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        questionnaire, wearing = data["questionnaire"], data["wearing_hearing_aid"]
        result = questionnaire.definition.result.from_answers(
            questionnaire, data["scored"], wearing
        )
        html = render_to_string(
            "screening/graded_result.html",
            {"submission": result.submission} | result.page_context(),
        )
        # The answer page's send counts; the guest result page sending them again does not.
        if data["just_finished"]:
            count_guest("completed")
        return Response(
            GuestScoreSerializer(
                {
                    "questionnaire": questionnaire,
                    "wearing_hearing_aid": wearing,
                    "wearing_text": TREND_STATUS_TEXT[wearing],
                    "result": result,
                    "html": html,
                }
            ).data
        )


class SubmissionDetail(RetrieveAPIView):
    serializer_class = SubmissionDetailSerializer

    def get_queryset(self):
        return _own_submission_details(self.request)


def _own_audiograms(request):
    # Scoped to request.user (IDOR); points prefetched for interpretation().
    return request.user.audiograms.prefetch_related("points")


def _point_set(points):
    fields = ("ear", "conduction", "frequency", "db", "no_response", "masked")
    return {tuple(p[field] for field in fields) for p in points}


def _same_audiogram(audiogram, data):
    saved = audiogram.points.values()
    return audiogram.tested_on == data["tested_on"] and _point_set(saved) == _point_set(
        data["points"]
    )


@transaction.atomic
def _create_audiogram(user, data, key):
    audiogram = Audiogram.objects.create(
        user=user, tested_on=data["tested_on"], idempotency_key=key
    )
    AudiogramPoint.objects.bulk_create(
        AudiogramPoint(audiogram=audiogram, **point) for point in data["points"]
    )
    return audiogram


class AudiogramCreate(GenericAPIView):
    serializer_class = AudiogramCreateSerializer

    @extend_schema(
        request=AudiogramCreateSerializer,
        parameters=[
            OpenApiParameter(
                "Idempotency-Key",
                str,
                OpenApiParameter.HEADER,
                required=True,
                description="UUID made when the input page opens; resend the same one on retry.",
            )
        ],
        responses={
            201: AudiogramSerializer,
            200: OpenApiResponse(AudiogramSerializer, "Retry: the first audiogram"),
            400: OpenApiResponse(description="Invalid points, date or Idempotency-Key"),
            409: OpenApiResponse(description="Idempotency-Key used with a different audiogram"),
        },
    )
    def post(self, request):
        # Same receipt-number flow as SubmissionList.post.
        key = _parse_key(request)
        if key is None:
            return Response({"detail": "缺少或無效的收據編號"}, status.HTTP_400_BAD_REQUEST)
        serializer = AudiogramCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        existing = request.user.audiograms.filter(idempotency_key=key).first()
        created = False
        if existing is None:
            try:
                existing = _create_audiogram(request.user, data, key)
                created = True
            except IntegrityError:
                existing = request.user.audiograms.get(idempotency_key=key)
        if not created and not _same_audiogram(existing, data):
            return Response({"detail": "這個收據編號已經用過"}, status.HTTP_409_CONFLICT)
        audiogram = _own_audiograms(request).get(pk=existing.pk)
        return Response(
            AudiogramSerializer(audiogram).data,
            status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


@transaction.atomic
def _replace_audiogram(audiogram, data):
    audiogram.tested_on = data["tested_on"]
    audiogram.save(update_fields=["tested_on"])
    audiogram.points.all().delete()
    AudiogramPoint.objects.bulk_create(
        AudiogramPoint(audiogram=audiogram, **point) for point in data["points"]
    )


class AudiogramDetail(RetrieveAPIView):
    serializer_class = AudiogramSerializer

    def get_queryset(self):
        return _own_audiograms(self.request)

    @extend_schema(
        request=AudiogramCreateSerializer,
        responses={
            200: AudiogramSerializer,
            400: OpenApiResponse(description="Invalid points or date; nothing changed"),
            404: OpenApiResponse(description="Not this user's audiogram"),
        },
    )
    def put(self, request, pk):
        # The whole audiogram is replaced, so sending it twice changes nothing more: no receipt
        # number needed. Same validation as creating one.
        audiogram = self.get_object()
        serializer = AudiogramCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _replace_audiogram(audiogram, serializer.validated_data)
        return Response(AudiogramSerializer(self.get_object()).data)
