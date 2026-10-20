from screening.questionnaires.comparison import AverageComparison
from screening.questionnaires.definition import AVERAGE, Definition

CODE = "ssq12-tw"

# Reviewed SSQ12-TW item text (#79), Wang 2023.
QUESTIONS = (
    "您在開著電視的房間裡與人說話。在沒有降低電視音量的情況下，您能跟上對方說話的內容嗎？",
    "您和大約五個人在忙碌的餐廳裡，您可以看到同行的每個人。這樣的情況下，您能跟上大家對話的內容嗎?",
    "您在聆聽某人與您說話，也想聽懂電視新聞的內容。您能同時聽懂兩人說話的內容嗎？",
    "您在房間跟某人交談，房間裡同時有許多人在說話。您能聽懂跟您對話的人在說什麼嗎？",
    "您和一群人在一起，大家輪流交談。您能輕鬆跟上對話，而且不會錯過每個新發言者開頭講的內容嗎？",
    "您正在外面，有一隻狗大聲吠叫。您不用看就能馬上判斷出狗在哪裡嗎？",
    "您能透過聲音判斷公車或卡車距離您多遠嗎？",
    "您能透過聲音，分辨一輛公車或卡車向您開過來或是遠離您嗎？",
    "當您同時聽一種以上的聲音時，您覺得聲音是分開還是混亂的?",
    "當您聆聽音樂時，能辨識有哪些樂器正在演奏嗎？",
    "您平常能輕鬆聽到的聲音是清晰的嗎？",
    "您在聽別人說話或事物的聲音時，要非常專心嗎？",
)

DEFINITION = Definition(
    code=CODE,
    name="SSQ12-TW",
    questions=tuple(("", text) for text in QUESTIONS),
    topic="日常聆聽能力",
    audience="了解您目前生活中的聆聽能力。",
    minutes=5,
    icon="clipboard",
    list_rank=2,
    intro_template="screening/questionnaires/ssq12_tw_intro.html",
    result=AVERAGE,
    comparison=AverageComparison(anchor=f"report-comparison-{CODE}"),
)
