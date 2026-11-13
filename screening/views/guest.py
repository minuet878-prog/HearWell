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
