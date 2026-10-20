from screening.questionnaires.definition import Definition

CODE = "hhia-s"

DEFINITION = Definition(
    code=CODE,
    topic="聽力對生活的影響",
    audience="適合 18–64 歲成人；若您持續使用原問卷追蹤，也可以繼續填寫。",
    minutes=3,
    icon="clipboard",
    list_rank=2,
    intro_template="screening/questionnaires/hhia_s_intro.html",
)
