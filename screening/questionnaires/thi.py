from screening.questionnaires.definition import LEVEL, Definition, SupportMessage

CODE = "thi"

# The owner's hospital form (ADR 0015): 黃啟原修訂，李恆惠信度考驗.
CHOICES = ((4, "經常"), (2, "偶爾"), (0, "不會"))


def choices(number):
    return CHOICES


# Word for word from the hospital form (thi-grill-decisions.md), item 22 included.
# A published version is immutable: later wording changes need a new code.
QUESTIONS = (
    "您是否覺得耳鳴無法控制？",
    "耳鳴的聲音大到讓您聽不清楚別人的談話？",
    "耳鳴會使您感到憤怒？",
    "您會認為您的耳鳴是一種可怕的疾病嗎？",
    "您會因為耳鳴而感到絕望？",
    "耳鳴會使您經常感到疲勞？",
    "您會因為耳鳴而晚上無法入睡嗎？",
    "您是否覺得無法擺脫耳鳴？",
    "耳鳴是否已干擾到您的正常社交活動？（例如出去用餐或看電影）",
    "您會因為耳鳴感到挫折嗎？",
    "您會因為耳鳴而感到憂鬱？",
    "耳鳴會使您感到不安嗎？",
    "耳鳴會干擾您的工作或家務嗎？",
    "您會因為耳鳴而經常情緒不穩定嗎？",
    "您會因為耳鳴而閱讀（書報）困難嗎？",
    "您會因為耳鳴而無法專心嗎？",
    "耳鳴會對於您和家人及朋友的關係帶來壓力嗎？",
    "您是否不容易把注意力從耳鳴轉移至別的事務？",
    "您對您的耳鳴會抱怨連連？",
    "耳鳴會使您感到困擾？",
    "受到壓力時，您的耳鳴會變得更嚴重？",
    "耳鳴會使您心情不好嗎？",
    "您是否覺得已無法忍受耳鳴了？",
    "耳鳴會使您感到焦慮嗎？",
    "耳鳴會使您無法享受人生嗎？",
)

THRESHOLDS = (
    (16, "無障礙或輕微障礙", "none_or_slight"),
    (36, "輕度障礙", "mild"),
    (56, "中度障礙", "moderate"),
    (76, "重度障礙", "severe"),
    (100, "極重度障礙", "catastrophic"),
)

# Like the audiogram's degrees (spec #208 Q13): five levels, ADR 0007's three colours.
LEVEL_COLORS = {
    "none_or_slight": "normal",
    "mild": "mild_to_moderate",
    "moderate": "mild_to_moderate",
    "severe": "severe",
    "catastrophic": "severe",
}

# Draft wording from #211, until the owner finalizes it there.
ADVICE = {
    "none_or_slight": (
        "耳鳴目前對您的生活影響不大。耳鳴在安靜的環境比較明顯，可以讓身邊保持一些柔和的聲音，"
        "例如開著收音機或風扇。若耳鳴突然變大聲、只有一邊耳朵有，或同時聽力變差、頭暈，"
        "請盡快就醫。"
    ),
    "mild": (
        "耳鳴已經對您的生活有些影響。大部分的耳鳴不是嚴重的疾病，越在意、越緊張，"
        "越容易覺得它大聲。注意睡眠、放鬆心情、避免太安靜的環境都有幫助；"
        "如果也覺得聽不清楚，建議做一次聽力檢查。"
    ),
    "moderate": (
        "耳鳴對您的睡眠、專心或心情已經有明顯影響。建議到醫院耳鼻喉科檢查，並請聽力師評估。"
        "如果您也有聽力損失，配戴助聽器常能讓耳鳴比較不明顯；也可以和聽力師討論聲音治療等方式。"
    ),
    "severe": (
        "耳鳴已經嚴重影響您的生活。請盡快到醫院耳鼻喉科就診，並請聽力師評估，"
        "討論助聽器、聲音治療等處理方式。耳鳴讓人心情低落、睡不好是很常見的，"
        "如果覺得很難熬，可以撥 1925 安心專線（24 小時免付費），有專人陪您聊聊。"
    ),
    "catastrophic": (
        "耳鳴已經非常嚴重地影響您的生活和心情。請盡快到醫院耳鼻喉科就診，並請聽力師評估；"
        "如果同時有失眠、焦慮或心情低落，也可以請身心科一起協助。覺得撐不下去時，"
        "請撥 1925 安心專線（24 小時免付費），有專人陪您聊聊。"
    ),
}

# THI's own last step (spec #208 Q10): not a life-impact questionnaire, so no home reminder
# and not the six-month RETEST_STEP.
RETAKE_STEP = {"text": "3 個月後，或開始新的處置（例如配戴助聽器）3 個月後再做一次。"}
AUDIOGRAM = {"action_label": "記錄聽力圖", "action_url": "audiogram_new"}
REPORT = {"action_label": "看／印聽力報告", "action_url": "health_report"}

# Draft wording from #211, until the owner finalizes it there.
NEXT_STEPS = {
    "none_or_slight": (
        {"text": "耳鳴目前對您的生活影響不大。"},
        {
            "text": (
                "避免待在太安靜的環境，可以開著柔和的背景聲音；若耳鳴突然變大聲、只有一邊耳朵有，"
                "或同時聽力變差、頭暈，請盡快就醫。"
            )
        },
        RETAKE_STEP,
    ),
    "mild": (
        {
            "text": (
                "耳鳴已經對您的生活有些影響。大部分的耳鳴不是嚴重的疾病，越在意、越緊張，"
                "越容易覺得它大聲。"
            )
        },
        {
            "text": (
                "注意睡眠、放鬆心情，避免太安靜的環境；如果也覺得聽不清楚，建議做一次聽力檢查。"
            ),
            **AUDIOGRAM,
        },
        RETAKE_STEP,
    ),
    "moderate": (
        {"text": "耳鳴對您的睡眠、專心或心情已經有明顯影響。"},
        {"text": "建議到醫院耳鼻喉科檢查，並請聽力師評估，可以帶著聽力報告去。", **REPORT},
        {
            "text": (
                "如果您也有聽力損失，配戴助聽器常能讓耳鳴比較不明顯；"
                "也可以和聽力師討論聲音治療等方式。"
            )
        },
        RETAKE_STEP,
    ),
    "severe": (
        {
            "text": "耳鳴已經嚴重影響您的生活，請盡快到醫院耳鼻喉科就診，並請聽力師評估。",
            **REPORT,
        },
        {"text": "可以和聽力師討論助聽器、聲音治療等處理方式。"},
        {
            "text": (
                "如果耳鳴讓您心情低落、很難熬，可以撥 1925 安心專線（24 小時免付費），"
                "有專人陪您聊聊。"
            )
        },
        RETAKE_STEP,
    ),
    "catastrophic": (
        {
            "text": (
                "耳鳴已經非常嚴重地影響您的生活和心情，請盡快到醫院耳鼻喉科就診，並請聽力師評估。"
            ),
            **REPORT,
        },
        {"text": "如果同時有失眠、焦慮或心情低落，也可以請身心科一起協助。"},
        {"text": "覺得撐不下去時，請撥 1925 安心專線（24 小時免付費），有專人陪您聊聊。"},
        RETAKE_STEP,
    ),
}

# Draft wording from #211, until the owner finalizes it there. Only on the result page, never
# in the report, the family page or 我的紀錄 (spec #208 story 20).
SUPPORT_MESSAGE = (
    "如果耳鳴讓您覺得心情低落、很難熬，可以撥 1925 安心專線（24 小時免付費），有專人陪您聊聊。"
    "也可以把這份結果帶給醫師或聽力師，一起討論怎麼減輕耳鳴的困擾。"
)

DEFINITION = Definition(
    code=CODE,
    name="THI",
    questions=tuple(("", text) for text in QUESTIONS),
    topic="耳鳴對生活的影響",
    audience="給有耳鳴的人，不限年齡。",
    minutes=5,
    icon="ear",
    list_rank=3,
    intro_template="screening/questionnaires/thi_intro.html",
    result=LEVEL,
    choices=choices,
    thresholds=THRESHOLDS,
    level_colors=LEVEL_COLORS,
    advice=ADVICE,
    next_steps=NEXT_STEPS,
    wizard_offer="如果您有耳鳴：耳鳴障礙量表（THI）",
    trend_chart=True,
    # The hospital form's numbering (not the English original's): 5 絕望, 11 憂鬱, 23 無法忍受,
    # answered 經常, whatever the total (spec #208 Q6).
    support_message=SupportMessage(items=(5, 11, 23), score=4, text=SUPPORT_MESSAGE),
    # Saved as background only (spec #208 Q4): tinnitus cannot be answered as if unaided.
    wearing_question="您現在有沒有配戴助聽器？",
    wearing_error="請選擇您現在有沒有配戴助聽器",
)
