"""Small air-conduction drawing of an audiogram for the list page.

Spec docs/specs/phase-09/phase9_ui_refresh_4c_audiogram_thumbnails.md.
Only screen coordinates live here;
what the points mean is in screening.audiogram (rule 9), whose ranges this reuses.
"""

import math

from screening.audiogram import AIR_FREQUENCIES, APPLE_DB_MIN, DB_MAX, DB_MIN, NORMAL_LIMIT

WIDTH, HEIGHT, MARGIN = 120, 90, 4
DB_TOP, DB_BOTTOM = DB_MIN, DB_MAX["air"]
GRID_STEP = 20


def _x(frequency):
    # Octaves from the lowest frequency, as on the full chart.
    octaves = math.log2(frequency / AIR_FREQUENCIES[0])
    span = math.log2(AIR_FREQUENCIES[-1] / AIR_FREQUENCIES[0])
    return round(MARGIN + octaves / span * (WIDTH - 2 * MARGIN), 1)


def _y(db, top=DB_TOP):
    # Worse hearing further down, as on every audiogram. top: -20 for an Apple test below -10.
    return round(MARGIN + (db - top) / (DB_BOTTOM - top) * (HEIGHT - 2 * MARGIN), 1)


def _lines(air, ear, top):
    # Same rule as the full chart's airLines: frequency order, missing frequencies skipped,
    # a no-response point breaks the line, single points get no line.
    pieces = [[]]
    for frequency in AIR_FREQUENCIES:
        point = air.get((ear, frequency))
        if point is None:
            continue
        if point.no_response:
            pieces.append([])
        else:
            pieces[-1].append(point)
    return [
        {"ear": ear, "points": " ".join(f"{_x(p.frequency)},{_y(p.db, top)}" for p in piece)}
        for piece in pieces
        if len(piece) > 1
    ]


def thumbnail(points):
    air = {(p.ear, p.frequency): p for p in points if p.conduction == "air"}
    # Spec #702 (#703 mockup 7A): as the full chart, one row more when a point is below -10.
    top = APPLE_DB_MIN if any(p.db < DB_MIN for p in air.values()) else DB_TOP
    marks = [
        {"ear": ear, "x": _x(frequency), "y": _y(air[(ear, frequency)].db, top)}
        for ear in ("right", "left")
        for frequency in AIR_FREQUENCIES
        if (ear, frequency) in air
    ]
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "lines": _lines(air, "right", top) + _lines(air, "left", top),
        "marks": marks,
        "grid": [_y(db, top) for db in range(0, DB_BOTTOM + 1, GRID_STEP)],
        "normal": {
            "x": MARGIN,
            "y": _y(top, top),
            "width": WIDTH - 2 * MARGIN,
            "height": round(_y(NORMAL_LIMIT, top) - _y(top, top), 1),
        },
        "left_edge": MARGIN,
        "right_edge": WIDTH - MARGIN,
    }
