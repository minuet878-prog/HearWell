"""Reads page 1 of the Apple hearing test PDF that 「健康」 exports (spec #702, ADR 0068).

The values are real text, not a picture: each ear's eight values sit in the ear's colour (right
red, left blue) beside a polyline of eight points, one per frequency on a log axis, and the dB
scale is printed in grey down the right edge. Each value goes to the nearest point by its
middle, and the point's height on the scale must agree with it. Only the Traditional Chinese
page is known (one sample, 2026-11-17); anything else is unreadable, and the person marks it by
hand. The PDF is read in memory and dropped: its name and birthday are never kept.
"""

import json
import math
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from pathlib import Path

from django.utils import timezone

from screening.audiogram import AIR_FREQUENCIES, APPLE_DB_MIN, DB_MAX
from screening.models.audiograms import Unreadable

MAX_BYTES = 2 * 1024 * 1024
PAGE_READER = Path(__file__).with_name("pdf_page.py")
READ_SECONDS = 15  # under Gunicorn's 30, which would stop the whole request
EAR_COLOURS = {"right": (1.0, 0.18, 0.33), "left": (0.0, 0.53, 1.0)}
COLOUR_TOLERANCE = 0.03
VALUE_SIZE = 10  # pt, the values beside the points
WORD_GAP = 1.5  # pt between two letters of one word
SAME_BASELINE = 1  # pt between two letters of one line
LOG_AXIS_TOLERANCE = 1.5  # pt a point may sit off the log frequency axis
VALUE_TO_POINT = 6  # pt from a value's middle to its point
CROSS_CHECK_DB = 2  # the 2026-11-17 sample was off by 1.1 dB at most
TEST_DATE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(?:上午|下午)")
VALUE = re.compile(r"(-?\d+)\*?")
TICK = re.compile(r"(-?\d+)(?:分貝)?")


class CannotRead(Exception):
    def __init__(self, reason):
        super().__init__(reason.label)
        self.reason = reason


@dataclass(frozen=True)
class AppleHearingTest:
    tested_on: date
    points: list  # 16 air points: {"ear", "frequency", "db"}
    # Only for the preview's reminders (spec #702 Q11), never saved: a value marked * (background
    # noise may have hidden quieter tones), and 鼻塞 or 最近曾暴露於大聲噪音 answered 是.
    noise_marked: bool = False
    congested: bool = False
    loud_noise: bool = False


@dataclass(frozen=True)
class _Char:
    """A letter on the page, as screening/pdf_page.py writes it."""

    text: str
    colour: object
    size: float
    x0: float
    x1: float
    y0: float
    y1: float
    baseline: float


@dataclass(frozen=True)
class _Word:
    text: str
    colour: tuple
    size: float
    x0: float
    x1: float
    middle: float  # height of its middle, from the bottom of the page


def read(data):
    """The test's date and both ears' points, or CannotRead with the reason."""
    if len(data) > MAX_BYTES or not data.startswith(b"%PDF"):
        raise CannotRead(Unreadable.NOT_A_PDF)
    chars, curves = _first_page(data)
    lines = _lines(chars)
    if not any("Apple聽力測試" in line.replace(" ", "") for line in lines):
        raise CannotRead(Unreadable.NOT_APPLE)
    try:
        return _test(curves, chars, lines)
    # A page shaped otherwise (a colour given as a name, a point with no number): not the layout.
    except (TypeError, ValueError, IndexError) as error:
        raise CannotRead(Unreadable.LAYOUT) from error


def _first_page(data):
    """Page 1's letters, and its lines as (colour, points), read by screening/pdf_page.py in a
    process of its own with a memory and time limit: a PDF can unpack to far more than its size."""
    try:
        done = subprocess.run(
            [sys.executable, "-I", str(PAGE_READER)],
            input=data,
            capture_output=True,
            timeout=READ_SECONDS,
            check=True,
        )
        page = json.loads(done.stdout)
        chars = [_Char(**char) for char in page["chars"]]
        curves = [(curve["colour"], curve["points"]) for curve in page["curves"]]
    # Anything the parser trips on, or a file it cannot read within the limits: the same answer
    # to the person.
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        raise CannotRead(Unreadable.NOT_A_PDF) from error
    return chars, curves


def _test(page_curves, chars, lines):
    tested_on = _tested_on(lines)
    curves = _curves(page_curves)
    words = _words(chars)
    zero, per_db = _scale(words, curves)
    points = []
    for ear in EAR_COLOURS:
        curve = curves[ear]
        # Each of the curve's points (by its x) and the value printed beside it.
        values = _values(words, ear, curve)
        for (x, y), frequency in zip(curve, AIR_FREQUENCIES, strict=True):
            db = values[x]
            # Nothing off the chart can be saved (the database refuses it), so it is not read.
            if not APPLE_DB_MIN <= db <= DB_MAX["air"]:
                raise CannotRead(Unreadable.LAYOUT)
            # The point's height read on the grey scale must agree with its printed value.
            if abs(db - (zero - y) / per_db) > CROSS_CHECK_DB:
                raise CannotRead(Unreadable.CROSS_CHECK)
            points.append({"ear": ear, "frequency": frequency, "db": db})
    return AppleHearingTest(
        tested_on=tested_on,
        points=points,
        noise_marked=any(word.text.endswith("*") and _ear_of(word.colour) for word in words),
        congested=_answered_yes(lines, "鼻塞"),
        loud_noise=_answered_yes(lines, "最近曾暴露於大聲噪音"),
    )


def _answered_yes(lines, question):
    """Whether the line asking question answers 是 after it."""
    for line in lines:
        if question in line:
            return "是" in line[line.index(question) + len(question) :]
    return False


def _same_colour(colour, ear):
    return (
        isinstance(colour, (tuple, list))
        and len(colour) == 3
        and all(
            abs(a - b) <= COLOUR_TOLERANCE for a, b in zip(colour, EAR_COLOURS[ear], strict=True)
        )
    )


def _ear_of(colour):
    return next((ear for ear in EAR_COLOURS if _same_colour(colour, ear)), None)


def _text(char):
    # The page writes some characters as CJK radicals (⼒ for 力, ⽉ for 月); a typeset minus
    # (U+2212), which NFKC leaves alone, is read as the hyphen it means.
    return unicodedata.normalize("NFKC", char.text).replace("\u2212", "-")


def _rows(chars):
    """Characters on the same baseline, left to right, top row first. By baseline, not by the
    letters' bottoms: the page mixes a Latin and a Chinese font on one line, and their letters
    reach down to different heights (the 2026-11-17 sample split 「Apple」 off its line)."""
    rows = []
    for char in sorted(chars, key=lambda c: -_baseline(c)):
        if rows and _baseline(rows[-1][0]) - _baseline(char) <= SAME_BASELINE:
            rows[-1].append(char)
        else:
            rows.append([char])
    return [sorted(row, key=lambda c: c.x0) for row in rows]


def _baseline(char):
    return char.baseline


def _lines(chars):
    lines = []
    for row in _rows(chars):
        line = _text(row[0])
        for before, char in pairwise(row):
            line += (" " if char.x0 - before.x1 > WORD_GAP else "") + _text(char)
        lines.append(line)
    return lines


def _words(chars):
    """Runs of letters with no gap between them, in one colour and size."""
    words = []
    for row in _rows(chars):
        run = [row[0]]
        for char in row[1:]:
            last = run[-1]
            together = (
                char.x0 - last.x1 <= WORD_GAP
                and char.colour == last.colour
                and abs(char.size - last.size) < 0.5
            )
            if not together:
                words.append(_word(run))
                run = []
            run.append(char)
        words.append(_word(run))
    return words


def _word(run):
    return _Word(
        text="".join(_text(char) for char in run),
        colour=run[0].colour,
        size=run[0].size,
        x0=run[0].x0,
        x1=run[-1].x1,
        middle=(min(c.y0 for c in run) + max(c.y1 for c in run)) / 2,
    )


def _tested_on(lines):
    # The header's 輸出時間 is the export's date, never the test's, whatever it carries.
    for line in lines:
        if "輸出" in line:
            continue
        if found := TEST_DATE.search(line):
            year, month, day = map(int, found.groups())
            try:
                tested_on = date(year, month, day)
            except ValueError:
                break
            # A test still to come was misread.
            if tested_on > timezone.localdate():
                break
            return tested_on
    raise CannotRead(Unreadable.LAYOUT)


def _curves(page_curves):
    """Each ear's polyline, its points left to right; exactly one each."""
    found = {}
    for colour, points in page_curves:
        ear = _ear_of(colour)
        if ear is None:
            continue
        if ear in found or len(points) != len(AIR_FREQUENCIES):
            raise CannotRead(Unreadable.LAYOUT)
        found[ear] = sorted(points)
    if set(found) != set(EAR_COLOURS):
        raise CannotRead(Unreadable.LAYOUT)
    for curve in found.values():
        first, last = curve[0][0], curve[-1][0]
        for (x, _), frequency in zip(curve, AIR_FREQUENCIES, strict=True):
            share = math.log2(frequency / 250) / math.log2(8000 / 250)
            if abs(x - (first + (last - first) * share)) > LOG_AXIS_TOLERANCE:
                raise CannotRead(Unreadable.LAYOUT)
    return found


def _scale(words, curves):
    """The height of 0 dB and points per dB, from the grey scale right of the chart."""
    right_edge = max(x for curve in curves.values() for x, _ in curve)
    ticks = {}
    for word in words:
        if word.x0 > right_edge and _ear_of(word.colour) is None:
            if found := TICK.fullmatch(word.text):
                ticks[int(found[1])] = word.middle
    if 0 not in ticks or 120 not in ticks:
        raise CannotRead(Unreadable.LAYOUT)
    per_db = (ticks[0] - ticks[120]) / 120
    # 0 dB above 120 dB, or the heights cannot be read as dB at all.
    if per_db <= 0:
        raise CannotRead(Unreadable.LAYOUT)
    return ticks[0], per_db


def _values(words, ear, curve):
    """Each point's value, keyed by the point's x: the one value nearest it."""
    values = {}
    for word in words:
        found = VALUE.fullmatch(word.text)
        if not found or abs(word.size - VALUE_SIZE) >= 0.5 or not _same_colour(word.colour, ear):
            continue
        middle = (word.x0 + word.x1) / 2
        x = min((x for x, _ in curve), key=lambda x: abs(x - middle))
        if abs(x - middle) > VALUE_TO_POINT or x in values:
            raise CannotRead(Unreadable.LAYOUT)
        values[x] = int(found[1])
    if len(values) != len(curve):
        raise CannotRead(Unreadable.LAYOUT)
    return values
