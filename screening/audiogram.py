"""Rule-based audiogram interpretation (spec docs/specs/phase-05/phase5_audiogram.md 4.3).

Ported from the standalone audiogram tool; no Django code here.
"""

from decimal import ROUND_HALF_UP, Decimal

AIR_FREQUENCIES = (250, 500, 1000, 2000, 3000, 4000, 6000, 8000)
BONE_FREQUENCIES = (500, 1000, 2000, 4000)
PTA_FREQUENCIES = (500, 1000, 2000, 4000)
DB_MIN = -10
DB_STEP = 5
# The highest level each conduction can mark; a no-response point sits exactly here.
DB_MAX = {"air": 120, "bone": 80}

NORMAL_LIMIT = 25  # dB HL; applies to both air and bone conduction averages
AIR_BONE_GAP = 15  # dB; a gap this large or larger is significant

# Upper limit (inclusive) of each degree, checked in order.
DEGREES = (
    (NORMAL_LIMIT, "正常"),
    (40, "輕度"),
    (55, "中度"),
    (70, "中重度"),
    (90, "重度"),
)


# Colour group of each degree, named like the questionnaire levels so both share one set of
# badge colours (spec phase9_ui_refresh_1_shared.md 4.4; the owner's clinical choice).
DEGREE_LEVELS = {
    "正常": "normal",
    "輕度": "mild_to_moderate",
    "中度": "mild_to_moderate",
    "中重度": "severe",
    "重度": "severe",
    "極重度": "severe",
}


def degree_level(name):
    """Badge level of a degree; None (not enough data) is unknown."""
    return DEGREE_LEVELS.get(name, "unknown")


def pta(thresholds):
    """Four-frequency average, or None if any of the four is missing."""
    values = [thresholds.get(f) for f in PTA_FREQUENCIES]
    if None in values:
        return None
    return sum(values) / len(values)


def degree(ac_pta):
    for limit, name in DEGREES:
        if ac_pta <= limit:
            return name
    return "極重度"


def hearing_type(ac_pta, bc_pta):
    """Type of loss, or None when bone conduction is needed but missing."""
    if ac_pta <= NORMAL_LIMIT:
        return "正常"
    if bc_pta is None:
        return None
    if ac_pta - bc_pta < AIR_BONE_GAP:
        return "感音神經性"
    return "傳導性" if bc_pta <= NORMAL_LIMIT else "混合性"


def _interpret_ear(points):
    air = {p.frequency: p for p in points if p.conduction == "air"}
    bone = {p.frequency: p for p in points if p.conduction == "bone"}
    # No-response points count at the level they were marked (spec 4.3).
    ac_pta = pta({f: p.db for f, p in air.items()})
    if ac_pta is None:
        return {"pta": None, "degree": None, "type": None, "no_response": False}
    bc_pta = pta({f: p.db for f, p in bone.items()})
    used = [air[f] for f in PTA_FREQUENCIES]
    # Bone only enters the result when the type depends on it.
    if ac_pta > NORMAL_LIMIT and bc_pta is not None:
        used += [bone[f] for f in PTA_FREQUENCIES]
    return {
        "pta": ac_pta,
        "degree": degree(ac_pta),
        "type": hearing_type(ac_pta, bc_pta),
        "no_response": any(p.no_response for p in used),
    }


def interpret(points):
    """{"right": {...}, "left": {...}}.

    Each point has ear, conduction, frequency, db and no_response attributes.
    """
    points = list(points)
    return {ear: _interpret_ear([p for p in points if p.ear == ear]) for ear in ("right", "left")}


# Disability assessment, hearing function (b230), level 1 starts at this dual-ear ratio (%):
# 身心障礙者鑑定作業辦法 附表二甲 (docs/planning/hearing-aid-guide/research.md section 1).
ASSESSMENT_THRESHOLD = Decimal("45.0")


def _ear_ratio_uncapped(ear_pta):
    return (Decimal(str(ear_pta)) - NORMAL_LIMIT) * Decimal("1.5")


def _ear_ratio(ear_pta):
    """One ear's impairment ratio (%): (PTA - 25) x 1.5, at most 100. Below 25 dB it counts as 0
    (the form says nothing; the owner's choice, grill Q14)."""
    return min(max(_ear_ratio_uncapped(ear_pta), Decimal(0)), Decimal(100))


def assessment_estimate(points):
    """The dual-ear impairment ratio the b230 assessment would compute from this audiogram (ADR
    0017, spec #218): the better ear (the smaller ratio) counts five times, the worse ear once,
    rounded half up to one decimal as the assessment form says.

    A no-response point counts at its marked level, so the ratio is a lower bound: reaching the
    threshold is certain, missing it is not ("uncertain", grill Q10). Only the air points of the
    four PTA frequencies make the ratio, so only they raise the no-response flag.
    """
    points = list(points)
    ears = {}
    no_response = False
    for ear in ("right", "left"):
        air = {p.frequency: p for p in points if p.ear == ear and p.conduction == "air"}
        ear_pta = pta({f: p.db for f, p in air.items()})
        ears[ear] = {"pta": ear_pta, "ratio": None if ear_pta is None else _ear_ratio(ear_pta)}
        no_response |= any(air[f].no_response for f in PTA_FREQUENCIES if f in air)
    if None in (ears["right"]["pta"], ears["left"]["pta"]):
        return {**ears, "ratio": None, "status": "insufficient", "no_response": no_response}
    better, worse = sorted(e["ratio"] for e in ears.values())
    ratio = ((better * 5 + worse) / 6).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if ratio >= ASSESSMENT_THRESHOLD:
        status = "reached"
    else:
        status = "uncertain" if no_response else "not_reached"
    return {
        **ears,
        "better": better,
        "worse": worse,
        # An ear under the normal limit was counted as 0% rather than below it, and one whose
        # ratio went over 100% as 100% ("超過 100% 以 100% 計", the assessment form).
        "zeroed": any(e["pta"] < NORMAL_LIMIT for e in ears.values()),
        "capped": any(_ear_ratio_uncapped(e["pta"]) > 100 for e in ears.values()),
        "ratio": ratio,
        "status": status,
        "no_response": no_response,
    }


def recommends_fitting_assessment(points):
    """Whether to suggest an audiologist's hearing-aid assessment (grill Q3, ADR 0017): either
    ear's PTA over the normal limit. None when an unknown ear could still decide it."""
    ptas = [r["pta"] for r in interpret(points).values()]
    if any(p is not None and p > NORMAL_LIMIT for p in ptas):
        return True
    return None if None in ptas else False


def _compare_rows(new, old, frequencies):
    rows = []
    for frequency in frequencies:
        n, o = new.get(frequency), old.get(frequency)
        if n is None and o is None:
            continue
        # "missing": one side has no value; "no_response": a value that is only a lower bound.
        if n is None or o is None:
            reason = "missing"
        elif n.no_response or o.no_response:
            reason = "no_response"
        else:
            reason = None
        diff = None if reason else n.db - o.db
        rows.append({"frequency": frequency, "new": n, "old": o, "diff": diff, "reason": reason})
    return rows


def _more_or_less(diff):
    # Numbers and direction only, never better or worse (ADR 0013).
    return f"{'多' if diff > 0 else '少'} {abs(diff):g} dB"


def average_change(pta):
    """「舊 31.25 → 新 36.25 dB HL，多 5 dB」, or None when either average is missing (#203)."""
    if pta["diff"] is None:
        return None
    change = "兩次一樣" if pta["diff"] == 0 else _more_or_less(pta["diff"])
    return f"舊 {pta['old']:g} → 新 {pta['new']:g} dB HL，{change}"


def largest_change(rows):
    """The air frequencies whose difference is largest in size, or None (#203).

    Only rows with both values and a response count; ties are all kept, in frequency order,
    and nothing is returned when every difference is 0.
    """
    diffs = [(row["frequency"], row["diff"]) for row in rows if row["reason"] is None]
    size = max((abs(diff) for _, diff in diffs), default=0)
    if size == 0:
        return None
    pairs = [(frequency, diff) for frequency, diff in diffs if abs(diff) == size]
    same = len({diff for _, diff in pairs}) == 1
    if same:
        each = "各" if len(pairs) > 1 else ""
        text = f"{'、'.join(str(f) for f, _ in pairs)} Hz，{each}{_more_or_less(pairs[0][1])}"
    else:
        text = "、".join(f"{f} Hz {_more_or_less(diff)}" for f, diff in pairs)
    return {"pairs": pairs, "size": size, "same": same, "text": text}


def compare(new_points, old_points):
    """Two audiograms side by side (spec docs/specs/phase-05/phase5_audiogram_2.md 4.2).

    The averages come from interpret(), the same path as the detail page; this only subtracts.
    """
    new_points, old_points = list(new_points), list(old_points)
    new_result, old_result = interpret(new_points), interpret(old_points)

    def by_frequency(points, ear, conduction):
        return {p.frequency: p for p in points if p.ear == ear and p.conduction == conduction}

    result = {}
    for ear in ("right", "left"):
        n, o = new_result[ear], old_result[ear]
        both = n["pta"] is not None and o["pta"] is not None
        # Only the air points the difference is made of; the result cards' flag can include bone.
        pta_points = [
            p
            for p in new_points + old_points
            if p.ear == ear and p.conduction == "air" and p.frequency in PTA_FREQUENCIES
        ]
        air = _compare_rows(
            by_frequency(new_points, ear, "air"),
            by_frequency(old_points, ear, "air"),
            AIR_FREQUENCIES,
        )
        result[ear] = {
            "pta": {
                "new": n["pta"],
                "old": o["pta"],
                "new_degree": n["degree"],
                "old_degree": o["degree"],
                "diff": n["pta"] - o["pta"] if both else None,
                "no_response": both and any(p.no_response for p in pta_points),
            },
            "air": air,
            "largest": largest_change(air),
            "bone": _compare_rows(
                by_frequency(new_points, ear, "bone"),
                by_frequency(old_points, ear, "bone"),
                BONE_FREQUENCIES,
            ),
        }
        result[ear]["pta"]["change"] = average_change(result[ear]["pta"])
    return result
