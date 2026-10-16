"""Rule-based audiogram interpretation (spec docs/specs/phase5_audiogram.md 4.3).

Ported from the standalone audiogram tool; no Django code here.
"""

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
