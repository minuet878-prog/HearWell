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
    COMMUNICATION_CHECKED_ON,
    COMMUNICATION_SCENARIOS,
    COMMUNICATION_SOURCES,
    HEARING_AID_CARE,
    HEARING_AID_CARE_REMINDERS,
    HEARING_AID_CHECKED_ON,
    HEARING_AID_PROBLEMS,
    HEARING_AID_SOURCES,
    HEARING_AID_STAGES,
    HEARING_AID_WEAR,
    RELUCTANT_CHECKED_ON,
    RELUCTANT_SITUATIONS,
    RELUCTANT_SOURCES,
    VISIT_BRING,
    VISIT_CHECKED_ON,
    VISIT_QUESTIONS,
    VISIT_SOURCES,
)
from screening.forms import DeadlineForm, SubsidyCheckForm
from screening.models import Questionnaire
from screening.questionnaires.ioi_ha import CODE as IOI_HA
from screening.subsidy_check import (
    FORM_9_LINK,
    SUBSIDY_CHECKED_ON,
    SUBSIDY_INTRO,
    SUBSIDY_SOURCES,
    check,
)


def family_talk(request):
    # #469 (the #468 mockup): the family guide's 怎麼跟聽損的家人說話 and its scenarios on a page
    # of their own, the words as reviewed. Open without logging in, the same for everyone.
    return render(
        request,
        "screening/family/talk.html",
        {
            "scenarios": COMMUNICATION_SCENARIOS,
            "scenario_sources": COMMUNICATION_SOURCES,
            "scenario_checked_on": COMMUNICATION_CHECKED_ON,
        },
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


@never_cache
def family_hearing_aids(request):
    # #433 (spec #426): open without logging in (CODING_STANDARDS.md 2): it holds no personal data
    # and is for family members who have no account. The same words for everyone. The survey's
    # address needs its id, so this looks up the questionnaire and no one's answers (#434). #435:
    # the care steps' ticks stay on the page in the browser: nothing is sent or kept, and
    # never_cache keeps 上一頁 on a shared phone from showing them. #504: so do 怎麼戴上、拿下's.
    return render(
        request,
        "screening/family/hearing_aids.html",
        {
            "care": HEARING_AID_CARE,
            "care_reminders": HEARING_AID_CARE_REMINDERS,
            "problems": HEARING_AID_PROBLEMS,
            "stages": HEARING_AID_STAGES,
            "wear": HEARING_AID_WEAR,
            "survey": Questionnaire.objects.filter(code=IOI_HA).first(),
            "sources": HEARING_AID_SOURCES,
            "checked_on": HEARING_AID_CHECKED_ON,
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
def family_subsidy_check(request):
    # #431 (spec #426): open without logging in (CODING_STANDARDS.md 2): it holds no personal data
    # and is for family members who have no account. The answers come in this POST and go back in
    # this response, with no redirect, session or database; never_cache keeps 上一頁 on a shared
    # phone from showing them.
    form = SubsidyCheckForm(request.POST if request.method == "POST" else None)
    return render(
        request,
        "screening/family/subsidy_check.html",
        {
            "form": form,
            "result": check(form.cleaned_data) if form.is_valid() else None,
            "intro": SUBSIDY_INTRO,
            "form_9_link": FORM_9_LINK,
            "sources": SUBSIDY_SOURCES,
            "checked_on": SUBSIDY_CHECKED_ON,
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
