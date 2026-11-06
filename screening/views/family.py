from django.shortcuts import render

from screening.family_zone import (
    RELUCTANT_CHECKED_ON,
    RELUCTANT_SITUATIONS,
    RELUCTANT_SOURCES,
    VISIT_BRING,
    VISIT_CHECKED_ON,
    VISIT_QUESTIONS,
    VISIT_SOURCES,
)


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


def family_visits(request):
    # #430 (spec #426): open without logging in (CODING_STANDARDS.md 2): it holds no personal data
    # and is for family members who have no account. The ticks stay on the page in the browser:
    # nothing is sent or kept.
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
