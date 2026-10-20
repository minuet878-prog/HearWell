from screening.questionnaires.definition import NORM, Definition

CODE = "ioi-ha"

# Answer labels for scores 1-5, by item number (林克寰《助聽器選配與驗證》書頁 167).
ITEM_CHOICES = {
    1: ("沒使用", "不到一小時", "一到四小時", "四到八小時", "超過八小時"),
    2: ("完全沒幫助", "只有一點幫助", "有中等幫助", "幫助很大", "非常有幫助"),
    3: ("非常困難", "有很大的困難", "有中等困難", "只有一點困難", "完全沒困難"),
    4: ("完全沒價值", "只有一點價值", "有中等價值", "有很大的價值", "非常有價值"),
    5: ("非常有影響", "有很大的影響", "有中等影響", "只有一點影響", "完全沒影響"),
    6: ("非常有干擾", "有很大程度的干擾", "有中等程度的干擾", "只有一點干擾", "完全沒干擾"),
    7: ("變得更糟", "沒有改變", "稍微提升", "有很大程度的提升", "非常有提升"),
}


def choices(number):
    return list(enumerate(ITEM_CHOICES[number], start=1))


DEFINITION = Definition(
    code=CODE,
    topic="助聽器使用成效",
    audience="適合已配戴助聽器的人。",
    minutes=2,
    icon="aid",
    list_rank=1,
    intro_template="screening/questionnaires/ioi_ha_intro.html",
    result=NORM,
    choices=choices,
)
