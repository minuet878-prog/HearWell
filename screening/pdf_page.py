"""Reads page 1 of the PDF on standard input and writes its letters and lines as JSON.

screening.apple_hearing_test runs this in a process of its own: a PDF a few hundred KB long can
unpack to more memory than the server has, and the server's memory is shared with the database.
So it limits itself before reading, and imports nothing from the site.
"""

import io
import json
import resource
import sys

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTCurve

MEMORY_BYTES = 256 * 1024 * 1024
CPU_SECONDS = 10


def main():
    # macOS refuses a memory limit (and would not keep to it): only the developer's computer.
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    page = next(extract_pages(io.BytesIO(sys.stdin.buffer.read()), maxpages=1))
    chars, curves = [], []
    for item in _walk(page):
        if isinstance(item, LTChar):
            chars.append(
                {
                    "text": item.get_text(),
                    "colour": item.graphicstate.ncolor,
                    "size": item.size,
                    "x0": item.x0,
                    "x1": item.x1,
                    "y0": item.y0,
                    "y1": item.y1,
                    "baseline": item.matrix[5],
                }
            )
        elif isinstance(item, LTCurve) and not item.fill:
            curves.append({"colour": item.stroking_color, "points": item.pts})
    # A colour the page gives some other way (a name) comes out as words, never a match.
    json.dump({"chars": chars, "curves": curves}, sys.stdout, default=str)


def _walk(item):
    yield item
    if hasattr(item, "__iter__"):
        for child in item:
            yield from _walk(child)


if __name__ == "__main__":
    main()
