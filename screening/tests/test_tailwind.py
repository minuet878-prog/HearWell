"""Templates moved off Bootstrap's layout utilities (#119, ADR 0008)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES = Path(settings.BASE_DIR) / "screening" / "templates" / "screening"

# Names that only Bootstrap gives a meaning, or that Tailwind reads differently (w-50 is 50% in
# Bootstrap, 12.5rem in Tailwind). Spacing such as mb-3 exists in both with different values, so a
# search cannot tell which one a template means; the screenshot comparison covers those.
BOOTSTRAP_ONLY = re.compile(
    r"d-\S+|[wh]-(?:25|50|75|100)|f[sw]-\S+|text-body-\S+|text-muted|text-break"
    r"|flex-(?:column|row|fill)|flex-\w+-(?:column|row)|align-(?:items|self)-\S+"
    r"|justify-content-\S+"
)
CLASS_ATTRIBUTE = re.compile(r'class="([^"]*)"')


class BootstrapUtilityTests(SimpleTestCase):
    # #127: public and account pages, with the field messages two of them include.
    MIGRATED = (
        "index.html",
        "login.html",
        "register.html",
        "privacy.html",
        "family_guide.html",
        "add_to_home.html",
        "consent.html",
        "account.html",
        "delete_account.html",
        "field_messages.html",
    )

    def test_migrated_templates_have_no_bootstrap_layout_classes(self):
        found = []
        for name in self.MIGRATED:
            text = (TEMPLATES / name).read_text()
            for lineno, line in enumerate(text.splitlines(), start=1):
                for value in CLASS_ATTRIBUTE.findall(line):
                    found += [
                        f"{name}:{lineno} {token}"
                        for token in value.split()
                        if BOOTSTRAP_ONLY.fullmatch(token)
                    ]
        self.assertEqual(found, [])
