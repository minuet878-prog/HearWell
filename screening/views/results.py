from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from screening.care_journey import next_step
from screening.main_flow import get_user_state
from screening.models import RetestReminder, Submission
from screening.scoring import TREND_STATUS_TEXT
from screening.views.common import JUST_SAVED, health_data_page
from screening.views.my_hearing import shows_wearing_comparison


@login_required
@health_data_page
def submission_result(request, submission_id):
    submission = get_object_or_404(
        Submission.objects.defined(), pk=submission_id, user=request.user
    )
    result = submission.result
    just_saved = request.session.pop(JUST_SAVED, None) == submission.pk
    # #455 (ADR 0044): the 照顧旅程's 現在這一步, by the user's state now, not this record's.
    suggested = next_step(request.user, timezone.localdate())
    # Spec #644 H3: which time this is, worn or not, in the order since_last uses (a tie by id).
    attempt_number = (
        Submission.objects.filter(user=request.user, questionnaire_id=submission.questionnaire_id)
        .earlier_than(submission)
        .count()
        + 1
    )
    shared = {
        "submission": submission,
        "just_saved": just_saved,
        "attempt_number": attempt_number,
        "wearing_text": (
            TREND_STATUS_TEXT[submission.wearing_hearing_aid] if result.page_shows_wearing else None
        ),
        "show_comparison": shows_wearing_comparison(request.user, submission.questionnaire),
        "next_step": suggested,
        "retest_reminder": _retest_reminder(request.user, submission),
    }
    return render(request, result.page_template, shared | result.page_context())


def _retest_reminder(user, submission):
    # #661 (spec #656 acceptance 12-15): the email 重測提醒 block, on life-impact result pages
    # only (not THI's or IOI-HA's); while off, the next date by the home page's own reckoning.
    if not submission.questionnaire.definition.life_impact:
        return None
    if RetestReminder.objects.filter(user=user, enabled=True).exists():
        return {"on": True}
    state = get_user_state(user, timezone.localdate())
    return {"on": False, "next_date": state.next_suggested_date}
