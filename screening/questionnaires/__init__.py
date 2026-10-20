"""One definition per questionnaire; other code asks these instead of checking codes (ADR 0005).

A questionnaire in the database without a definition is not offered to anyone.
"""

from screening.questionnaires import hhia_s, hhie_s, ioi_ha, ssq12_tw

DEFINITIONS = {
    definition.code: definition
    for definition in (
        hhie_s.DEFINITION,
        ioi_ha.DEFINITION,
        hhia_s.DEFINITION,
        ssq12_tw.DEFINITION,
    )
}


def get(code):
    return DEFINITIONS.get(code)
