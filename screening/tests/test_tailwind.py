"""Site templates use current layout utilities (#119, ADR 0008)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE_DIR = Path(settings.BASE_DIR)

# Legacy names with no current meaning, or different values (w-50 was 50%, now 12.5rem).
# Spacing such as mb-3 exists in both with different values; screenshots cover those.
LEGACY_UTILITIES = re.compile(
    r"d-\S+|[wh]-(?:25|50|75|100)|f[sw]-\S+|text-body-\S+|text-muted|text-break"
    r"|flex-(?:column|row|fill)|flex-\w+-(?:column|row)|align-(?:items|self)-\S+"
    r"|justify-content-\S+"
)
# A template's class="…", or a React className="…" or className={`…`}.
CLASS_ATTRIBUTE = re.compile(r'class(?:Name)?=(?:"([^"]*)"|\{`([^`]*)`\})')


class LayoutUtilityTests(SimpleTestCase):
    SOURCES = (
        *sorted((BASE_DIR / "screening/templates").rglob("*.html")),
        *sorted((BASE_DIR / "frontend/src").rglob("*.jsx")),
    )

    def test_all_templates_have_no_legacy_layout_classes(self):
        found = []
        for path in self.SOURCES:
            name = path.relative_to(BASE_DIR)
            text = path.read_text()
            for lineno, line in enumerate(text.splitlines(), start=1):
                for groups in CLASS_ATTRIBUTE.findall(line):
                    found += [
                        f"{name}:{lineno} {token}"
                        for token in "".join(groups).split()
                        if LEGACY_UTILITIES.fullmatch(token)
                    ]
        self.assertEqual(found, [])
