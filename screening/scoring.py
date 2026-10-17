import logging

logger = logging.getLogger(__name__)

# Each tuple is (upper bound inclusive, text, level); the last upper bound is the max score.
THRESHOLDS = {
    "hhie-s": (
        (8, "無/極輕微影響", "normal"),
        (24, "輕度到中度影響", "mild_to_moderate"),
        (40, "顯著影響", "severe"),
    ),
}

UNKNOWN = {"text": "無法判讀", "level": "unknown"}

# Shown on the questionnaire list and answer page.
# Questionnaires missing here show only their name and question count.
QUESTIONNAIRE_INFO = {
    "hhie-s": {"subtitle": "聽力障礙自我評估", "audience": "適合 65 歲以上的長輩。", "minutes": 3},
    "ioi-ha": {"subtitle": "助聽器效益量表", "audience": "適合已配戴助聽器的人。", "minutes": 2},
}

IOI_HA = "ioi-ha"

# Answer labels for scores 1-5, by item number (林克寰《助聽器選配與驗證》書頁 167).
IOI_HA_CHOICES = {
    1: ("沒使用", "不到一小時", "一到四小時", "四到八小時", "超過八小時"),
    2: ("完全沒幫助", "只有一點幫助", "有中等幫助", "幫助很大", "非常有幫助"),
    3: ("非常困難", "有很大的困難", "有中等困難", "只有一點困難", "完全沒困難"),
    4: ("完全沒價值", "只有一點價值", "有中等價值", "有很大的價值", "非常有價值"),
    5: ("非常有影響", "有很大的影響", "有中等影響", "只有一點影響", "完全沒影響"),
    6: ("非常有干擾", "有很大程度的干擾", "有中等程度的干擾", "只有一點干擾", "完全沒干擾"),
    7: ("變得更糟", "沒有改變", "稍微提升", "有很大程度的提升", "非常有提升"),
}

# Short column names for the norm chart on the history page.
IOI_HA_ITEM_NAMES = {
    1: "使用時間",
    2: "幫助程度",
    3: "剩餘困難",
    4: "值得程度",
    5: "生活影響",
    6: "干擾他人",
    7: "生活樂趣",
}

# Middle 50% of each item (Cox, Alexander & Beyer 2003), as (lower, upper) inclusive.
# Groups match models.NormGroup values.
IOI_HA_NORMS = {
    "mild_moderate": {
        1: (3, 5),
        2: (3, 4),
        3: (3, 4),
        4: (2, 4),
        5: (3, 4),
        6: (3, 5),
        7: (3, 4),
    },
    "moderately_severe": {
        1: (4, 5),
        2: (3, 4),
        3: (2, 4),
        4: (3, 5),
        5: (3, 4),
        6: (2, 4),
        7: (3, 4),
    },
}

# Unaided HHIE-S 0-24 vs 25-40 (林克寰《助聽器選配與驗證》表 5).
IOI_HA_MILD_MODERATE_MAX = 24


def ioi_ha_group(unaided_hhie_s_total):
    # None means no unaided HHIE-S; 0 is a real score and groups as mild_moderate.
    if unaided_hhie_s_total is None:
        return "ungrouped"
    if unaided_hhie_s_total <= IOI_HA_MILD_MODERATE_MAX:
        return "mild_moderate"
    return "moderately_severe"


NORM_COMPARISON_TEXT = {"below": "低於常模", "within": "在範圍內", "above": "高於常模"}


def compare_to_norm(group, item_number, score):
    lower, upper = IOI_HA_NORMS[group][item_number]
    if score < lower:
        return "below"
    if score > upper:
        return "above"
    return "within"


def max_score(questionnaire_code):
    # None hides "（滿分 Y）"; classify() already logs the missing thresholds.
    thresholds = THRESHOLDS.get(questionnaire_code)
    return thresholds[-1][0] if thresholds else None


def classify(total_score, questionnaire_code):
    thresholds = THRESHOLDS.get(questionnaire_code)
    if thresholds is None:
        logger.error("No thresholds for questionnaire %r", questionnaire_code)
        return UNKNOWN
    if total_score >= 0:
        for upper, text, level in thresholds:
            if total_score <= upper:
                return {"text": text, "level": level}
    logger.error("Score %s out of range for questionnaire %r", total_score, questionnaire_code)
    return UNKNOWN


def get_advice(level):
    advices = {
        "normal": (
            "您的聽覺自覺障礙程度為無或是僅有輕微障礙，聽力的部分並未明顯影響"
            "您的情緒以及社交活動，然而高齡族群的聽力退化往往是較無自覺的，"
            "建議若未進行過聽力檢查能夠至醫院進行定期篩檢。"
        ),
        "mild_to_moderate": (
            "聽力的問題已經慢慢開始影響到您的社交活動以及情緒，例如"
            "與家人之間常常因為聽不清楚或是電視聲音等而產生爭吵、在多人且吵雜的"
            "社交環境當中會因為聽不清楚而導致社交上的窘迫及退縮，許多聽力衰退"
            "帶來的問題是微妙且和緩的，但經過此次篩檢能夠讓您體認到聽力對自身生"
            "活的影響，建議前往醫院耳鼻喉科進行聽力相關檢查及詢問相關專業意見。"
        ),
        "severe": (
            "聽力問題已經嚴重影響到您的生活了，許多人常常會忽視這一塊，聽不到這件事"
            "情往往已經十分嚴重了才會發現，若您尚未採取任何行動建議立即前往醫院耳鼻"
            "喉科尋求專業建議，並且考慮配戴助聽器。聽力喪失影響的並不只是聽不聽得到，"
            "無形中也會增加社交活動的壓力（例如因為聽不清楚常會在聊天的過程中退縮、"
            "裝作聽得懂等），這些壓力以及情緒的低落會增加長者的認知負擔。"
        ),
        "unknown": (
            "這次的作答結果無法判讀分級，可能是資料有誤。建議重新作答一次；"
            "若對聽力有疑慮，請直接諮詢聽力師或耳鼻喉科醫師。"
        ),
    }
    return advices[level]
