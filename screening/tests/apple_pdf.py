"""Made-up Apple hearing test PDFs for tests (spec #702): the owner's real one stays out of this
public repo, so these copy its layout instead. Page 1 of 「健康」's 輸出 PDF, as read on
2026-11-17: the right ear red and the left blue, each a polyline of eight points with its value
in the same colour beside each point (an asterisk when background noise may have interfered),
the dB scale in grey down the right edge, the test's date and 「來源：Apple聽力測試」."""

import io
import math
import re
from datetime import datetime

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

FREQUENCIES = (250, 500, 1000, 2000, 3000, 4000, 6000, 8000)
RIGHT_RED = (1.0, 0.176, 0.333)
LEFT_BLUE = (0.0, 0.533, 1.0)
GREY = (0.557, 0.557, 0.577)
CHINESE = "STSong-Light"  # MSung-Light comes back garbled through pdfminer
pdfmetrics.registerFont(UnicodeCIDFont(CHINESE))

# Where the real page draws the chart, in points from the bottom left of an A4 page.
X_250, X_8000 = 151.8, 441.4
Y_ZERO_DB, POINTS_PER_DB = 558.3, 2.237

# A mild sloping loss, both ears; values chosen so none is a multiple of 5 everywhere.
RIGHT = (11, 14, 18, 29, 33, 41, 47, 52)
LEFT = (6, 9, 13, 24, 31, 38, 44, 49)


def x_of(frequency):
    return X_250 + (X_8000 - X_250) * math.log2(frequency / 250) / math.log2(8000 / 250)


def y_of(db):
    return Y_ZERO_DB - db * POINTS_PER_DB


def apple_pdf(
    right=RIGHT,
    left=LEFT,
    tested_at=datetime(2026, 11, 10, 20, 15),
    exported_on="2026年11月17日",
    stars=True,
    source="來源：Apple聽力測試",
):
    """The PDF's bytes. right and left: dB HL at FREQUENCIES."""
    out = io.BytesIO()
    page = canvas.Canvas(out, pagesize=(595.28, 841.89))

    def text(x, y, words, colour=(0, 0, 0), size=10, font=CHINESE, centred=False):
        page.setFillColorRGB(*colour)
        page.setFont(font, size)
        (page.drawCentredString if centred else page.drawString)(x, y, words)

    def mixed(x, y, words, size=10):
        """Like the real page: Latin letters and digits in a Latin font, the rest in a Chinese
        one, on one baseline; the two fonts' letters reach down to different heights."""
        page.setFillColorRGB(0, 0, 0)
        for run in re.findall(r"[A-Za-z0-9:]+|[^A-Za-z0-9:]+", words):
            font = "Helvetica" if run[0].isascii() else CHINESE
            page.setFont(font, size)
            page.drawString(x, y, run)
            x += pdfmetrics.stringWidth(run, font, size)

    text(36, 790, "王小明", size=16)
    text(36, 772, f"生日：1950年1月2日（76歲）　輸出時間：{exported_on}")
    text(36, 735, "聽力測試結果")
    text(46, 700, "右耳", RIGHT_RED)
    text(170, 700, "左耳", LEFT_BLUE)
    noon = "上午" if tested_at.hour < 12 else "下午"
    hour = tested_at.hour if tested_at.hour <= 12 else tested_at.hour - 12
    stamp = f"{tested_at.year}年{tested_at.month}月{tested_at.day}日 {noon}{hour}:{tested_at:%M}"
    # At these baselines the Latin letters' bottoms (2.07 pt down) and the Chinese ones' (2.71 pt
    # down) round to different whole points, as on the real page, so reading must go by baseline.
    mixed(36, 640.9, stamp)
    mixed(36, 628.9, source)
    for db in range(-20, 121, 10):
        label = f"{db}分貝" if db in (-20, 120) else str(db)
        # A 10 pt label's middle sits about 2.9 pt over its baseline.
        text(
            509.3,
            y_of(db) - 2.9,
            label,
            GREY,
            font="Helvetica" if db not in (-20, 120) else CHINESE,
        )
    for frequency, label in ((125, "125 Hz"), (250, "250 Hz"), (500, "500 Hz"), (1000, "1 kHz")):
        text(x_of(frequency), 270, label, GREY, font="Helvetica", centred=True)
    for values, colour, nudge in ((right, RIGHT_RED, 7), (left, LEFT_BLUE, -16)):
        points = [(x_of(f), y_of(db)) for f, db in zip(FREQUENCIES, values, strict=True)]
        page.setStrokeColorRGB(*colour)
        path = page.beginPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        page.drawPath(path, stroke=1, fill=0)
        for (x, y), db in zip(points, values, strict=True):
            text(
                x, y + nudge, f"{db}{'*' if stars else ''}", colour, font="Helvetica", centred=True
            )
    text(36, 240, "鼻塞：否")
    text(36, 228, "最近曾暴露於大聲噪音：否")
    page.showPage()
    page.save()
    return out.getvalue()
