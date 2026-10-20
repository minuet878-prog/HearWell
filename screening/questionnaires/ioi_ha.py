from screening.questionnaires.definition import Definition

CODE = "ioi-ha"

DEFINITION = Definition(
    code=CODE,
    topic="助聽器使用成效",
    audience="適合已配戴助聽器的人。",
    minutes=2,
    icon="aid",
    list_rank=1,
    intro_template="screening/questionnaires/ioi_ha_intro.html",
)
