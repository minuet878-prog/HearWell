from screening.questionnaires.definition import AVERAGE, Definition

CODE = "ssq12-tw"

DEFINITION = Definition(
    code=CODE,
    topic="日常聆聽能力",
    audience="了解您目前生活中的聆聽能力。",
    minutes=5,
    icon="clipboard",
    list_rank=2,
    intro_template="screening/questionnaires/ssq12_tw_intro.html",
    result=AVERAGE,
)
