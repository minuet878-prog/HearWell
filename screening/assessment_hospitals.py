"""Hearing (b230) assessment hospitals taken from the MOHW roster (#222).

The snapshot is written by scripts/extract_assessment_hospitals.py and read on first use.
"""

import json
from functools import cache
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parent / "data" / "assessment_hospitals.json"


@cache
def roster():
    """{"version", "counties", "hospitals": [{"county", "name"}]}, read once per process."""
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
