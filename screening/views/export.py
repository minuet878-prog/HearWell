import json

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_http_methods

from screening import models
from screening.forms import Form9Form, Form25Form, NoticeForm, answer_choices
from screening.models import Answer, AudiogramPoint, Questionnaire
from screening.questionnaires.definition import AVERAGE, LEVEL, SUBSCALES
from screening.views.common import health_data_page
from screening.views.guide import GUIDE_CHAPTERS


def _taipei(moment):
    return timezone.localtime(moment).isoformat()


def _export_submission(submission):
    # Only graded questionnaires have a total, subscales and level (same as their result
    # pages); the others export null, not 0.
    result = submission.questionnaire.definition.result
    not_scored = result != LEVEL
    has_subscores = not not_scored and submission.has_subscores
    data = {
        "questionnaire": submission.questionnaire.questionnaire_name,
        "created_at": _taipei(submission.created_at),
        "wearing_hearing_aid": submission.get_wearing_hearing_aid_display(),
        "answers": [
            {
                "number": answer.question.question_number,
                "question": answer.question.question_text,
                "score": answer.score,
                # null rather than a 500: one odd old answer must not block the whole export.
                "choice": dict(answer_choices(answer.question)).get(answer.score),
            }
            for answer in submission.answers.all()
        ],
        "total_score": None if not_scored else submission.total_answer_score,
        "emotional_score": submission.emotional_score if has_subscores else None,
        "social_score": submission.social_score if has_subscores else None,
        "level": None if not_scored else submission.classified["text"],
        "norm_group": submission.get_norm_group_display() or None,
    }

    if result == AVERAGE:
        data["average_score"] = (
            str(submission.ssq_average) if submission.ssq_average is not None else None
        )
        data["average_unavailable_reason"] = submission.ssq_unavailable_reason
        _mark_not_applicable_answers(data)
    if result == SUBSCALES:
        satisfaction = submission.satisfaction
        data["overall_score"] = str(satisfaction["overall"])
        data["subscale_scores"] = {s["name"]: str(s["score"]) for s in satisfaction["subscales"]}
        _mark_not_applicable_answers(data)
    return data


def _mark_not_applicable_answers(data):
    for answer in data["answers"]:
        if answer["score"] is None:
            answer["choice"] = "不適用"


def _offered(form_class, name, value):
    """The wording the question offers for the answer value; None unanswered."""
    return dict(form_class.base_fields[name].choices).get(value)


@login_required
@require_http_methods(["GET"])
@health_data_page
def download_my_data(request):
    # Spec phase7_data_export.md: everything of request.user, nothing else; no ids in the URL.
    user = request.user
    answers = Answer.objects.select_related("question__questionnaire").order_by(
        "question__question_number"
    )
    submissions = (
        user.submissions.defined()
        .select_related("questionnaire")
        .prefetch_related(Prefetch("answers", queryset=answers))
        .with_scores()
    )
    points = AudiogramPoint.objects.order_by("ear", "conduction", "frequency")
    audiograms = user.audiograms.prefetch_related(Prefetch("points", queryset=points))
    aid = models.AidAndSubsidy.for_user(user)
    chapter_titles = {chapter.slug: chapter.title for chapter in GUIDE_CHAPTERS}
    data = {
        "account": {
            "username": user.username,
            "email": user.email,
            "birth_year": user.birth_year,
            "date_joined": _taipei(user.date_joined),
        },
        "consents": [
            {"version": consent.version, "agreed_at": _taipei(consent.agreed_at)}
            for consent in user.consents.order_by("agreed_at", "id")
        ],
        "submissions": [_export_submission(submission) for submission in submissions],
        "report_comparisons": [
            {
                "questionnaire": comparison.questionnaire.questionnaire_name,
                "unaided": _export_submission(comparison.unaided),
                "aided": _export_submission(comparison.aided),
            }
            for comparison in user.report_comparisons.filter(
                questionnaire__in=Questionnaire.objects.defined()
            )
            .select_related("questionnaire")
            .prefetch_related(
                Prefetch("unaided", queryset=submissions),
                Prefetch("aided", queryset=submissions),
            )
            .order_by("questionnaire_id")
        ],
        "audiograms": [
            {
                "tested_on": audiogram.tested_on.isoformat(),
                "created_at": _taipei(audiogram.created_at),
                "points": [
                    {
                        "ear": point.get_ear_display(),
                        "conduction": point.get_conduction_display(),
                        "frequency": point.frequency,
                        "db": point.db,
                        "no_response": point.no_response,
                        "masked": point.masked,
                    }
                    for point in audiogram.points.all()
                ],
            }
            for audiogram in audiograms
        ],
        # The link code itself is left out: it would let anyone holding the file open it.
        "report_shares": [
            {
                "created_at": _taipei(share.created_at),
                "expires_at": _taipei(share.expires_at),
                "cancelled": share.revoked_at is not None,
                "open_count": share.open_count,
                "last_opened_at": share.last_opened_at and _taipei(share.last_opened_at),
            }
            for share in user.report_shares.all()
        ],
        # Spec #284, #291: what the user answered, unanswered as null, the certificate included.
        "aid_and_subsidy": {
            "certificate": (aid and aid.get_certificate_display()) or None,
            # #294: worded as the questions offer them.
            "form_9_done": _offered(Form9Form, "form_9_done", aid and aid.form_9_done),
            "notice_received": _offered(NoticeForm, "notice_received", aid and aid.notice_received),
            "approved_ears": (aid and aid.get_approved_ears_display()) or None,
            "fitted_on": aid.fitted_on.isoformat() if aid and aid.fitted_on else None,
            "ear": (aid and aid.get_ear_display()) or None,
            "subsidy": (aid and aid.get_subsidy_display()) or None,
            "level": (aid and aid.get_level_display()) or None,
            "form_25_done": _offered(Form25Form, "form_25_done", aid and aid.form_25_done),
            # Spec #291 acceptance 23: the chapters read, by name, first read first.
            "viewed_chapters": [
                {
                    # A chapter since taken out of the guide keeps its slug.
                    "chapter": chapter_titles.get(view.chapter, view.chapter),
                    "first_viewed_at": _taipei(view.first_viewed_at),
                }
                for view in user.guide_views.order_by("first_viewed_at")
            ],
        },
    }
    filename = f"hearwell-我的資料-{timezone.localdate().isoformat()}.json"
    return HttpResponse(
        json.dumps(data, ensure_ascii=False, indent=2),
        content_type="application/json",
        headers={"Content-Disposition": content_disposition_header(True, filename)},
    )
