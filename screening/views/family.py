from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from screening.family_deadlines import (
    CLOSING_NOTE,
    DEADLINE_CHECKED_ON,
    DEADLINE_SOURCES,
    INTRO,
    RESULTS_TITLE,
    SUBMIT_LABEL,
    deadlines,
)
from screening.family_zone import (
    RELUCTANT_CHECKED_ON,
    RELUCTANT_SITUATIONS,
    RELUCTANT_SOURCES,
    VISIT_BRING,
    VISIT_CHECKED_ON,
    VISIT_QUESTIONS,
    VISIT_SOURCES,
)
from screening.forms import DeadlineForm


def family_reluctant(request):
    # #429 (spec #426): open without logging in (CODING_STANDARDS.md 2): it holds no personal data
    # and is for family members who have no account. The same words for everyone.
    return render(
        request,
        "screening/family/reluctant.html",
        {
            "situations": RELUCTANT_SITUATIONS,
            "sources": RELUCTANT_SOURCES,
            "checked_on": RELUCTANT_CHECKED_ON,
        },
    )


@never_cache
def family_visits(request):
    # #430 (spec #426): open without logging in (CODING_STANDARDS.md 2): it holds no personal data
    # and is for family members who have no account. The ticks stay on the page in the browser:
    # nothing is sent or kept, and never_cache keeps 上一頁 on a shared phone from showing them.
    return render(
        request,
        "screening/family/visits.html",
        {
            "bring": VISIT_BRING,
            "question_groups": VISIT_QUESTIONS,
            "sources": VISIT_SOURCES,
            "checked_on": VISIT_CHECKED_ON,
        },
    )


@never_cache
def family_deadlines(request):
    # #432 (spec #426): open without logging in (CODING_STANDARDS.md 2): it holds no personal data
    # and is for family members who have no account. The dates are worked out and answered in the
    # same response: not kept, not in the address, and never_cache keeps 上一頁 from showing them.
    form = DeadlineForm(request.POST if request.method == "POST" else None)
    results = ()
    if form.is_valid():
        results = deadlines(**form.cleaned_data, today=timezone.localdate())
    return render(
        request,
        "screening/family/deadlines.html",
        {
            "form": form,
            "results": results,
            "intro": INTRO,
            "submit_label": SUBMIT_LABEL,
            "results_title": RESULTS_TITLE,
            "closing_note": CLOSING_NOTE,
            "sources": DEADLINE_SOURCES,
            "checked_on": DEADLINE_CHECKED_ON,
        },
    )
