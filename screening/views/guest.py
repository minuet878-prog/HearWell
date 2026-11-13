from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from screening.models import Questionnaire
from screening.views.common import health_data_page


# Open without an account (spec #492): the result kept in this browser is drawn here, by
# guest-result.js, from the scoring-only API; the page itself holds none. Never cached all the
# same, as the result is put into it (test_standards' OPEN_HEALTH_DATA).
@health_data_page
def guest_result(request, code):
    # Someone signed in keeps records instead of a guest result.
    if request.user.is_authenticated:
        return redirect("index")
    questionnaire = get_object_or_404(Questionnaire.objects.for_guests(), code=code)
    return render(request, "screening/guest_result.html", {"questionnaire": questionnaire})


# The save page (spec #492): after registering or logging in, and agreeing (it is not one of the
# consent's OPEN_PAGES), guest-save.js sends every guest result in this browser to the records
# API. From the save card (?from=card) it saves straight away; the other ways in ask first (#497),
# until then saving the same way.
@login_required
@health_data_page
def guest_save(request):
    # Each guest questionnaire's name, to say which one was not saved.
    names = {
        guest.code: f"{guest.definition.topic}（{guest.questionnaire_name}）"
        for guest in Questionnaire.objects.for_guests()
    }
    return render(request, "screening/guest_save.html", {"names": names})
