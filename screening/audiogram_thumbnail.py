"""Small air-conduction drawing of an audiogram for the list page.

Spec docs/specs/phase9_ui_refresh_4c_audiogram_thumbnails.md. Only screen coordinates live here;
what the points mean is in screening.audiogram (rule 9), whose ranges this reuses.
"""

import math

from screening.audiogram import AIR_FREQUENCIES, DB_MAX, DB_MIN, NORMAL_LIMIT

WIDTH, HEIGHT, MARGIN = 120, 90, 4
DB_TOP, DB_BOTTOM = DB_MIN, DB_MAX["air"]
GRID_STEP = 20


def _x(frequency):
    # Octaves from the lowest frequency, as on the full chart.
    octaves = math.log2(frequency / AIR_FREQUENCIES[0])
    span = math.log2(AIR_FREQUENCIES[-1] / AIR_FREQUENCIES[0])
    return round(MARGIN + octaves / span * (WIDTH - 2 * MARGIN), 1)


def _y(db):
    # Worse hearing further down, as on every audiogram.
    return round(MARGIN + (db - DB_TOP) / (DB_BOTTOM - DB_TOP) * (HEIGHT - 2 * MARGIN), 1)


def _lines(air, ear):
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
        {"ear": ear, "points": " ".join(f"{_x(p.frequency)},{_y(p.db)}" for p in piece)}
        for piece in pieces
        if len(piece) > 1
    ]


def thumbnail(points):
    air = {(p.ear, p.frequency): p for p in points if p.conduction == "air"}
    marks = [
        {"ear": ear, "x": _x(frequency), "y": _y(air[(ear, frequency)].db)}
        for ear in ("right", "left")
        for frequency in AIR_FREQUENCIES
        if (ear, frequency) in air
    ]
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "lines": _lines(air, "right") + _lines(air, "left"),
        "marks": marks,
        "grid": [_y(db) for db in range(0, DB_BOTTOM + 1, GRID_STEP)],
        "normal": {
            "x": MARGIN,
            "y": _y(DB_TOP),
            "width": WIDTH - 2 * MARGIN,
            "height": round(_y(NORMAL_LIMIT) - _y(DB_TOP), 1),
        },
        "left_edge": MARGIN,
        "right_edge": WIDTH - MARGIN,
    }
