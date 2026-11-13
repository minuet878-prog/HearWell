"""The hearing loss simulator's typical degrees and sentences (#487, spec #484, ADR 0052).

Reviewed by the owner on the #485 mockup on 2026-11-13 (phase-3-grill-decisions.md, 聽損模擬內容
定稿); change the words or numbers only after review. A degree's thresholds are a representative
audiogram in dB HL at FREQUENCIES: the player turns every frequency down along its line, and draws
the sound bars from it.
"""

FREQUENCIES = (250, 500, 1000, 2000, 4000, 8000)

# 高頻下降 first: the commonest, picked on opening (#485).
LEVELS = (
    {
        "code": "high-frequency",
        "name": "高頻下降",
        "line": "尖細的聲音大多聽不到",
        "thresholds": (15, 20, 25, 45, 65, 75),
        # Its four-frequency average is only 輕度 on a report (SimulatorDegreeTests).
        "note": (
            "選的是高頻下降：檢查報告上的平均可能只寫「輕度」，可是尖細的聲音大多聽不到，"
            "所以最常「聽得到、聽不清楚」。"
        ),
    },
    {
        "code": "mild",
        "name": "輕度",
        "line": "小聲就漏聽",
        "thresholds": (25, 30, 30, 35, 40, 40),
    },
    {
        "code": "moderate",
        "name": "中度",
        "line": "常聽不完整",
        "thresholds": (40, 45, 50, 55, 60, 65),
    },
    {
        "code": "moderately-severe",
        "name": "中重度",
        "line": "不大聲聽不到",
        "thresholds": (55, 60, 65, 70, 75, 80),
    },
)

NORMAL_LINE = "每一種聲音都聽得到"

# Women and men in turn, a woman first: hardest with 高頻下降. Audio sources:
# docs/planning/redesign/simulator-audio.md.
SENTENCES = (
    ("星期四下午三點去看醫生。", "女"),
    ("這個藥飯後吃，一天三次。", "男"),
    ("孫子說下禮拜六要回來吃飯。", "女"),
    ("謝謝你送的水果，很新鮮。", "男"),
)

# The restaurant behind the speech (#488): the speech this many dB above it (#485).
RESTAURANT_SNR_DB = 5

LIMITS = (
    "這是典型的程度，不是誰真正的聽力。"
    "模擬只把聲音變小聲；真正的聽損還會讓聲音糊在一起，實際可能更吃力。",
    "聽不到聲音？先關掉手機的靜音、把音量調大；戴耳機聽最清楚。",
)
