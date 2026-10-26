from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from screening.audiogram import compare, recommends_fitting_assessment
from screening.audiogram_thumbnail import thumbnail
from screening.models import Ear
from screening.views.common import health_data_page


@login_required
@health_data_page
def audiogram_list(request):
    audiograms = list(request.user.audiograms.prefetch_related("points"))
    for audiogram in audiograms:
        # From the points already loaded with the list: no query per card.
        audiogram.thumbnail = thumbnail(audiogram.points.all())
    return render(request, "screening/audiogram_list.html", {"audiograms": audiograms})


def _chart_points(points):
    return [
        {
            "ear": p.ear,
            "conduction": p.conduction,
            "frequency": p.frequency,
            "db": p.db,
            "no_response": p.no_response,
            "masked": p.masked,
        }
        for p in points
    ]


@login_required
def audiogram_new(request):
    return render(request, "screening/audiogram_new.html", {"today": timezone.localdate()})


def _own_audiogram(request, audiogram_id):
    return get_object_or_404(request.user.audiograms.prefetch_related("points"), pk=audiogram_id)


@login_required
@health_data_page
def audiogram_detail(request, audiogram_id):
    audiogram = _own_audiogram(request, audiogram_id)
    context = audiogram_context(audiogram)
    # #201: the report holds the latest audiogram; the compare button picks this one and the one
    # before it (the next newer when this is the oldest), in the model's newest-first order.
    rows = list(request.user.audiograms.values_list("id", "tested_on"))
    ids = [row_id for row_id, _ in rows]
    here = ids.index(audiogram.id)
    if here > 0:
        context["latest_tested_on"] = rows[0][1]
    if len(ids) > 1:
        context["compare_with"] = ids[here + 1] if here + 1 < len(ids) else ids[here - 1]
    # #230: link the guide when either ear's PTA is over 25 dB; not when that is unknown.
    context["fitting_guide"] = recommends_fitting_assessment(context["points"])
    return render(request, "screening/audiogram_detail.html", context)


def audiogram_context(audiogram):
    # Shared by the audiogram page and the health report, so both read it the same way.
    result = audiogram.interpretation()
    # Right ear first, air before bone, as on a clinical record.
    points = sorted(
        audiogram.points.all(), key=lambda p: (p.ear != Ear.RIGHT, p.conduction, p.frequency)
    )
    return {
        "audiogram": audiogram,
        "ears": [(ear.value, ear.label, result[ear.value]) for ear in (Ear.RIGHT, Ear.LEFT)],
        "points": points,
        "chart_points": _chart_points(points),
    }


@login_required
@require_http_methods(["GET", "POST"])
@health_data_page
def audiogram_delete(request, audiogram_id):
    audiogram = _own_audiogram(request, audiogram_id)
    if request.method == "POST":
        audiogram.delete()
        return redirect("audiogram_list")
    audiogram.thumbnail = thumbnail(audiogram.points.all())
    return render(request, "screening/audiogram_delete.html", {"audiogram": audiogram})


@login_required
@health_data_page
def audiogram_edit(request, audiogram_id):
    audiogram = _own_audiogram(request, audiogram_id)
    initial = {
        "tested_on": audiogram.tested_on.isoformat(),
        "points": _chart_points(audiogram.points.all()),
    }
    return render(
        request,
        "screening/audiogram_new.html",
        {"today": timezone.localdate(), "audiogram": audiogram, "initial": initial},
    )


def _compare_ids(request, audiograms):
    if "a" not in request.GET and "b" not in request.GET:
        return [a.id for a in audiograms[:2]]
    try:
        return [int(request.GET["a"]), int(request.GET["b"])]
    except (KeyError, ValueError):
        raise Http404 from None


@login_required
@health_data_page
def audiogram_compare(request):
    audiograms = list(request.user.audiograms.all())
    context = {"audiograms": audiograms}
    if len(audiograms) < 2:
        return render(request, "screening/audiogram_compare.html", context)
    ids = _compare_ids(request, audiograms)
    # Model ordering puts the newer one first, whichever select it was picked in (spec 4.2).
    pair = list(request.user.audiograms.prefetch_related("points").filter(pk__in=ids))
    if len(pair) != len(set(ids)):
        raise Http404
    ear = request.GET.get("ear")
    if ear not in Ear.values:
        ear = Ear.RIGHT
    # #202: the 舊 and 新 rows, newest first as the model orders them, even for one picked twice.
    picked = [audiogram for audiogram in audiograms if audiogram.id in ids]
    context.update(
        a=ids[0],
        b=ids[1],
        ear=ear,
        ears=Ear.choices,
        pick_rows=[("舊", "b", picked[-1]), ("新", "a", picked[0])],
    )
    if len(pair) == 2:
        new, old = pair
        result = compare(new.points.all(), old.points.all())[ear]
        context.update(
            new=new,
            old=old,
            ear_label=Ear(ear).label,
            result=result,
            sections=[("air", "氣導", result["air"]), ("bone", "骨導", result["bone"])],
            chart_points=_chart_points(p for p in new.points.all() if p.ear == ear),
            old_chart_points=_chart_points(p for p in old.points.all() if p.ear == ear),
        )
    return render(request, "screening/audiogram_compare.html", context)
