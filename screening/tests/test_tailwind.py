"""Templates moved off Bootstrap's layout utilities (#119, ADR 0008)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE_DIR = Path(settings.BASE_DIR)

# Names that only Bootstrap gives a meaning, or that Tailwind reads differently (w-50 is 50% in
# Bootstrap, 12.5rem in Tailwind). Spacing such as mb-3 exists in both with different values, so a
# search cannot tell which one a template means; the screenshot comparison covers those.
BOOTSTRAP_ONLY = re.compile(
    r"d-\S+|[wh]-(?:25|50|75|100)|f[sw]-\S+|text-body-\S+|text-muted|text-break"
    r"|flex-(?:column|row|fill)|flex-\w+-(?:column|row)|align-(?:items|self)-\S+"
    r"|justify-content-\S+"
)
# A template's class="…", or a React className="…" or className={`…`}.
CLASS_ATTRIBUTE = re.compile(r'class(?:Name)?=(?:"([^"]*)"|\{`([^`]*)`\})')


class BootstrapUtilityTests(SimpleTestCase):
    MIGRATED = (
        # #127: public and account pages, with the field messages two of them include.
        *(
            f"screening/templates/screening/{name}"
            for name in (
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
        ),
        # #128: questionnaire list, answering and result pages, and the parts they share.
        *(
            f"screening/templates/screening/{name}"
            for name in (
                "questionnaire.html",
                "questionnaire_icon.html",
                "screening.html",
                "questionnaires/hhie_s_intro.html",
                "questionnaires/hhia_s_intro.html",
                "questionnaires/ssq12_tw_intro.html",
                "questionnaires/ioi_ha_intro.html",
                "result.html",
                "ssq12_result.html",
                "result_ioi_ha.html",
                "ioi_ha_source.html",
                "hhi_comparison.html",
                "comparison_content.html",
                "comparisons/average.html",
                "comparisons/total.html",
                "level_badge.html",
            )
        ),
        "frontend/src/AnswerApp.jsx",
        "frontend/src/answer-main.jsx",
        # #129: my hearing history and the audiogram pages.
        *(
            f"screening/templates/screening/{name}"
            for name in (
                "my_hearing.html",
                "comparisons/average_history.html",
                "comparisons/total_history.html",
                "ioi_ha_chart.html",
                "ioi_ha_lines.html",
                "audiogram_list.html",
                "audiogram_new.html",
                "audiogram_detail.html",
                "audiogram_compare.html",
                "audiogram_delete.html",
                "audiogram_point_value.html",
                "audiogram_thumbnail.html",
            )
        ),
        "frontend/src/TrendChart.jsx",
        "frontend/src/AudiogramApp.jsx",
        "frontend/src/AudiogramChart.jsx",
        "frontend/src/audiogram-main.jsx",
        "frontend/src/audiogram-view-main.jsx",
        "frontend/src/main.jsx",
    )

    def test_migrated_templates_have_no_bootstrap_layout_classes(self):
        found = []
        for name in self.MIGRATED:
            text = (BASE_DIR / name).read_text()
            for lineno, line in enumerate(text.splitlines(), start=1):
                for groups in CLASS_ATTRIBUTE.findall(line):
                    found += [
                        f"{name}:{lineno} {token}"
                        for token in "".join(groups).split()
                        if BOOTSTRAP_ONLY.fullmatch(token)
                    ]
        self.assertEqual(found, [])
