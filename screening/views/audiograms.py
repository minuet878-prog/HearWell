from datetime import date
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import Resolver404, resolve
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from screening.apple_hearing_test import MAX_BYTES, CannotRead, read
from screening.audiogram import (
    SPEECH_BANANA,
    SPEECH_BANANA_CHECKED_ON,
    SPEECH_GROUPS,
    FittingAdvice,
    air_marks,
    compare,
    fitting_advice,
    speech_banana,
)
from screening.audiogram_thumbnail import thumbnail
from screening.fitting_route import latest_submission, wearing_hearing_aids
from screening.forms import add_attempt, attempts
from screening.main_flow import get_user_state
from screening.models import (
    AidAndSubsidy,
    Audiogram,
    AudiogramEntry,
    AudiogramPoint,
    AudiogramSource,
    Conduction,
    Ear,
    count_import_failure,
)
from screening.views.common import RECENT_SHOWN, health_data_page, older_fold, safe_next


@login_required
@health_data_page
def audiogram_list(request):
    audiograms = list(request.user.audiograms.prefetch_related("points"))
    for audiogram in audiograms:
        # From the points already loaded with the list: no query per card.
        audiogram.thumbnail = thumbnail(audiogram.points.all())
    return render(
        request,
        "screening/audiogram_list.html",
        {
            "audiograms": audiograms,
            "recent": audiograms[:RECENT_SHOWN],
            "older": older_fold(audiograms, lambda a: a.tested_on, "張"),
        },
    )


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
    return render(
        request,
        "screening/audiogram_new.html",
        {"today": timezone.localdate(), "back": way_back(request)},
    )


# The 2026-11-14 walkthrough (mockup 2A): sent here by the care journey's 醫院檢查報告 (spec
# #741), someone who finds they have no report yet goes back home; None: the list, as before.
WAYS_BACK = {"index": "還沒有報告，回首頁"}


def way_back(request):
    next_url = safe_next(request)
    try:
        name = resolve(urlsplit(next_url).path).url_name if next_url else None
    except Resolver404:
        return None
    return (WAYS_BACK[name], next_url) if name in WAYS_BACK else None


# Spec #702 (#703 mockup 2A): the steps in 「健康」, then back here for the file; each with its
# drawing of the phone (#709, the owner's mockup A), in import_drawings/.
IMPORT_STEPS = (
    ("打開「健康」app，點下面的「瀏覽」", "browse"),
    ("點「聽力」", "hearing"),
    ("點「聽力測試結果」，選要匯入的那一次", "results"),
    ("往下滑，點「輸出 PDF」", "export"),
    ("點分享，選「儲存到檔案」", "save"),
    ("回到這裡，選剛剛存的 PDF", "pick"),
)
IMPORT_SALT = "screening.audiogram_import"
# The preview's reading is signed for this person and kept good this long (spec #702).
IMPORT_GOOD_FOR = 30 * 60
IMPORTS_PER_HOUR = 20


@login_required
@health_data_page
@require_http_methods(["GET", "POST"])
def audiogram_import(request):
    """從 iPhone 匯入: the steps and the file; a readable PDF opens its preview (spec #702). The
    PDF is read in memory and dropped, so its name and birthday are never kept."""
    if request.method == "GET":
        return _import_page(request)
    # Each file is read in a process of its own: one account cannot keep the server busy. Only
    # the account's hashed count is kept, for an hour.
    account = str(request.user.pk)
    if attempts("import", account) >= IMPORTS_PER_HOUR:
        return _import_page(request, too_many=True)
    add_attempt("import", account)
    upload = request.FILES.get("pdf")
    try:
        test = read(upload.read(MAX_BYTES + 1) if upload else b"")
    except CannotRead as error:
        count_import_failure(error.reason)
        return _import_page(request, unreadable=True)
    if kept := _imported_before(request.user, test.tested_on, test.points):
        return _import_page(request, already=kept)
    points = [
        AudiogramPoint(
            ear=p["ear"], conduction=Conduction.AIR, frequency=p["frequency"], db=p["db"]
        )
        for p in test.points
    ]
    reading = {
        "user": request.user.pk,
        "tested_on": test.tested_on.isoformat(),
        "points": test.points,
    }
    return render(
        request,
        "screening/audiogram_import_preview.html",
        {
            "tested_on": test.tested_on,
            "chart_points": _chart_points(points),
            "rows": [
                (right.frequency, right.db, left.db)
                for right, left in zip(*_by_ear(points), strict=True)
            ],
            "reading": signing.dumps(reading, salt=IMPORT_SALT),
            # Spec #702 Q11: only for the reminders, never saved.
            "noise_marked": test.noise_marked,
            "congested": test.congested,
            "loud_noise": test.loud_noise,
        },
    )


def _imported_before(user, tested_on, points):
    """Spec #702 Q10: the audiogram this person already imported from the same test (same day,
    the same 16 values), or None."""
    wanted = {(p["ear"], p["frequency"], p["db"]) for p in points}
    same_day = user.audiograms.filter(entry=AudiogramEntry.APPLE_PDF, tested_on=tested_on)
    for audiogram in same_day.prefetch_related("points"):
        if {(p.ear, p.frequency, p.db) for p in audiogram.points.all()} == wanted:
            return audiogram
    return None


def _by_ear(points):
    """Right ear's points, then left's, each in frequency order."""
    return [
        sorted((p for p in points if p.ear == ear), key=lambda p: p.frequency)
        for ear in (Ear.RIGHT, Ear.LEFT)
    ]


def _import_page(request, unreadable=False, already=None, not_saved=False, too_many=False):
    # Spec #702 (#703 mockup 4A): whatever happened says so at the top, the file again below.
    return render(
        request,
        "screening/audiogram_import.html",
        {
            "steps": IMPORT_STEPS,
            "unreadable": unreadable,
            "already": already,
            "not_saved": not_saved,
            "too_many": too_many,
        },
    )


@login_required
@health_data_page
@require_POST
def audiogram_import_save(request):
    """存下來: the reading the preview showed, as a self test imported from Apple's PDF."""
    try:
        reading = signing.loads(
            request.POST.get("reading", ""), salt=IMPORT_SALT, max_age=IMPORT_GOOD_FOR
        )
    # Too old (an expiry is a bad signature too), changed, or another person's: nothing saved.
    except signing.BadSignature:
        return _import_page(request, not_saved=True)
    if reading["user"] != request.user.pk:
        return _import_page(request, not_saved=True)
    tested_on = date.fromisoformat(reading["tested_on"])
    if kept := _imported_before(request.user, tested_on, reading["points"]):
        return redirect("audiogram_detail", kept.id)
    with transaction.atomic():
        audiogram = Audiogram.objects.create(
            user=request.user,
            tested_on=tested_on,
            source=AudiogramSource.SELF_TEST,
            entry=AudiogramEntry.APPLE_PDF,
        )
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, conduction=Conduction.AIR, **point)
            for point in reading["points"]
        )
    return redirect("audiogram_detail", audiogram.id)


def _own_audiogram(request, audiogram_id):
    return get_object_or_404(request.user.audiograms.prefetch_related("points"), pk=audiogram_id)


def _fitting_guide(audiogram, points):
    # ADR 0067: the guide only when this audiogram's 建議評估選配 is 建議, judged with its owner's
    # latest life-impact record (spec #693 acceptance 15); only the owner opens it
    # (_own_audiogram). Someone wearing hearing aids is not judged by it and always has the
    # guide, as my guide keeps the route.
    user = audiogram.user
    if wearing_hearing_aids(latest_submission(user), AidAndSubsidy.for_user(user)):
        return True
    life_impact = get_user_state(user, timezone.localdate()).life_impact
    return fitting_advice(points, life_impact) == FittingAdvice.RECOMMEND


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
    context["fitting_guide"] = _fitting_guide(audiogram, context["points"])
    # #440: the speech banana only reads air conduction, so bone alone has nothing to show.
    context["has_air_marks"] = any(air_marks(context["points"], ear) for ear in Ear)
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
@health_data_page
def audiogram_speech_banana(request, audiogram_id):
    audiogram = _own_audiogram(request, audiogram_id)
    points = audiogram.points.all()
    judged = speech_banana(points)
    data = {
        "banana": SPEECH_BANANA,
        "groups": SPEECH_GROUPS,
        "ears": [
            {
                "ear": ear.value,
                "label": ear.label,
                "marks": _chart_points(air_marks(points, ear)),
                **judged[ear.value],
            }
            for ear in (Ear.RIGHT, Ear.LEFT)
        ],
    }
    return render(
        request,
        "screening/audiogram_speech_banana.html",
        {
            "audiogram": audiogram,
            "data": data,
            "checked_on": SPEECH_BANANA_CHECKED_ON,
            "fitting_guide": _fitting_guide(audiogram, points),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
@health_data_page
def audiogram_delete(request, audiogram_id):
    audiogram = _own_audiogram(request, audiogram_id)
    if request.method == "POST":
        audiogram.delete()
        # The feedback batch (F2, the owner's words): which one went, by its date.
        messages.success(request, f"已刪除 {audiogram.tested_on:%Y/%m/%d} 的聽力圖。")
        return redirect("audiogram_list")
    audiogram.thumbnail = thumbnail(audiogram.points.all())
    return render(request, "screening/audiogram_delete.html", {"audiogram": audiogram})


@login_required
@health_data_page
def audiogram_edit(request, audiogram_id):
    audiogram = _own_audiogram(request, audiogram_id)
    # Spec #702 acceptance 13: one imported from Apple's PDF is never edited.
    if audiogram.is_imported:
        raise Http404
    initial = {
        "tested_on": audiogram.tested_on.isoformat(),
        "source": audiogram.source,
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
