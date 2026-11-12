from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from screening.care_journey import next_step
from screening.models import Submission
from screening.views.common import health_data_page
from screening.views.my_hearing import TREND_STATUS_TEXT, shows_wearing_comparison


@login_required
@health_data_page
def submission_result(request, submission_id):
    submission = get_object_or_404(
        Submission.objects.defined(), pk=submission_id, user=request.user
    )
    result = submission.result
    # #455 (ADR 0044): the 照顧旅程's 現在這一步, by the user's state now, not this record's.
    suggested = next_step(request.user, timezone.localdate())
    shared = {
        "submission": submission,
        "wearing_text": (
            TREND_STATUS_TEXT[submission.wearing_hearing_aid] if result.page_shows_wearing else None
        ),
        "show_comparison": shows_wearing_comparison(request.user, submission.questionnaire),
        "next_step": suggested,
    }
    return render(request, result.page_template, shared | result.page_context())
