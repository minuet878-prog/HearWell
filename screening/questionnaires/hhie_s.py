from screening.questionnaires.definition import Definition

CODE = "hhie-s"

DEFINITION = Definition(
    code=CODE,
    topic="聽力對生活的影響",
    audience="適合 65 歲以上的長輩。",
    minutes=3,
    icon="ear",
    list_rank=0,
    intro_template="screening/questionnaires/hhie_s_intro.html",
)
