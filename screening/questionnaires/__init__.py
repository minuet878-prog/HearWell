"""One definition per questionnaire; other code asks these instead of checking codes (ADR 0005).

A questionnaire in the database without a definition is not offered to anyone.
"""

from django.conf import settings

from screening.questionnaires import hhia_s, hhie_s, ioi_ha, sadl, ssq12_tw, thi

DEFINITIONS = {
    definition.code: definition
    for definition in (
        hhie_s.DEFINITION,
        ioi_ha.DEFINITION,
        hhia_s.DEFINITION,
        ssq12_tw.DEFINITION,
        sadl.DEFINITION,
        thi.DEFINITION,
    )
}


def get(code):
    return DEFINITIONS.get(code)


def offered():
    # An unlisted questionnaire (ADR 0011) is only offered on a local DEBUG site.
    return [code for code, definition in DEFINITIONS.items() if definition.listed or settings.DEBUG]
