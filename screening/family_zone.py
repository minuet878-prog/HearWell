"""The family zone's definitions (spec #426): scenarios, options, explanations, sources and checked
dates are here, for review in one place; each page's fixed sentences are in its template."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CareStep:
    title: str
    # How often, or when: shown in brackets after the title.
    frequency: str
    words: str
    # The file's name in templates/screening/family/care_drawings/. Never all a step says: the
    # words above say everything, and the drawing is hidden from screen readers.
    drawing: str


@dataclass(frozen=True)
class Option:
    label: str
    # What this choice does, in plain words. None is a verdict: no right, wrong or score (#428).
    # Empty where the groups below say it all (#433).
    explanation: str = ""
    # Only where a page has more to show than that paragraph (#429). Things to say and things that
    # tend to backfire, each one line; next steps as (words, URL name) pairs.
    try_saying: tuple = ()
    avoid_saying: tuple = ()
    next_steps: tuple = ()
    # Other lists under their own titles, as (title, (line, ...)) pairs (#433).
    sections: tuple = ()
    # What cannot wait, in bold above the rest (#433).
    urgent: str = ""
    # Links to a place on a page, with no heading above them: (words, path#anchor) pairs (#433).
    links: tuple = ()
    # Steps to follow, each with a drawing and a box to tick (#435), and a sentence after them.
    steps: tuple = ()
    steps_note: str = ""


@dataclass(frozen=True)
class PickExplain:
    # English, unique on its page: it names the question's radio group.
    code: str
    prompt: str
    options: tuple


# Drafts for the owner's review (#428). Only from /family's nine reviewed tips: no new medical
# claims or numbers. The reader is 「您」, the one with hearing loss 「他」.
COMMUNICATION_SCENARIOS = (
    PickExplain(
        code="dinner-question",
        prompt="吃飯時，您問他一句話，他沒有回應。",
        options=(
            Option(
                label="再說一次，大聲一點",
                explanation=(
                    "您是想讓他聽到。不過大喊會讓聲音變形，反而更難聽懂，也容易聽起來像在生氣。"
                    "可以試試說清楚、稍微放慢，不用加大音量。"
                ),
            ),
            Option(
                label="先叫他的名字，等他看您再問",
                explanation=(
                    "這樣有幫助，因為他知道您在跟他說話，也看得到您的表情和嘴型。"
                    "也可以先把嘴裡的東西吃完再開口。"
                ),
            ),
            Option(
                label="算了，等一下再說",
                explanation=(
                    "吃飯時不急著說也沒關係。不過常常說「算了」，會讓他覺得被排除在對話外。"
                    "可以試試等他看向您，再問一次。"
                ),
            ),
        ),
    ),
    PickExplain(
        code="tv-on",
        prompt="他在看電視，聲音開得很大，您想跟他說話。",
        options=(
            Option(
                label="提高音量，蓋過電視",
                explanation=(
                    "背景聲音大的時候，大喊也不容易聽清楚，還可能聽起來像在生氣。"
                    "可以試試先把電視關小聲再說。"
                ),
            ),
            Option(
                label="先把電視關小聲，再跟他說",
                explanation=(
                    "這樣有幫助，因為背景噪音少了，比較容易聽清楚。"
                    "可以先跟他說一聲，再把電視關小聲，等他看您再開口。"
                ),
            ),
            Option(
                label="走到他面前再說，電視照開",
                explanation=(
                    "面對面有幫助，因為表情和嘴型能幫助理解。"
                    "如果再把電視關小聲一點，會更容易聽清楚。"
                ),
            ),
        ),
    ),
    PickExplain(
        code="other-room",
        prompt="您在廚房，想請在客廳的他來吃飯。",
        options=(
            Option(
                label="從廚房大聲叫他",
                explanation=(
                    "隔著房間，他看不到您的臉，聲音也不容易聽清楚。"
                    "可以試試走到他看得到您的地方再說。"
                ),
            ),
            Option(
                label="走到他面前，叫他的名字再說",
                explanation=(
                    "這樣有幫助，因為他看得到您的臉，表情和嘴型能幫助理解。"
                    "站在光線照得到您臉的地方會更清楚。"
                ),
            ),
            Option(
                label="走到他背後，直接開口說",
                explanation=(
                    "您已經走近了。不過從背後說話，他可能不知道您在跟他說，也看不到您的嘴型。"
                    "可以試試輕拍他的肩膀，等他看您再說。"
                ),
            ),
        ),
    ),
    PickExplain(
        code="not-understood",
        prompt="同一句話您說了兩次，他還是聽不懂。",
        options=(
            Option(
                label="一樣的話再說一次",
                explanation=("同一句話重複很多次不一定有用。可以試試換成比較簡單或不同的詞。"),
            ),
            Option(
                label="換一種說法",
                explanation=(
                    "這樣有幫助，因為換個詞，他多一個機會聽懂。"
                    "同時讓他看得到您的臉，說清楚、稍微放慢。"
                ),
            ),
            Option(
                label="跟他說「算了，沒事」",
                explanation=(
                    "說了好幾次，雙方都容易累。不過被排除在對話外，會讓人更不想說話。"
                    "如果是重要的事，可以試試寫下來，請他確認。"
                ),
            ),
        ),
    ),
    PickExplain(
        code="doctor-visit",
        prompt="陪他看診時，醫師講得比較快，您發現他沒聽清楚。",
        options=(
            Option(
                label="直接替他回答醫師",
                explanation=(
                    "您是想幫忙。不過替他回答，他就少了參與的機會，也可能更不想說話。"
                    "可以試試換個說法告訴他，讓他自己回答。"
                ),
            ),
            Option(
                label="請醫師面對他，說慢一點",
                explanation=("這樣有幫助，因為看得到臉，加上說清楚、稍微放慢，都比較容易理解。"),
            ),
            Option(
                label="把看診時間和吃藥方式寫下來，請他確認",
                explanation=(
                    "這樣有幫助，因為重要的事寫下來，他可以用看的，也可以確認有沒有弄清楚。"
                ),
            ),
        ),
    ),
)

# /family's communication sources: (title, address) pairs, shown under 出處.
COMMUNICATION_SOURCES = (
    (
        "美國聽語學會（ASHA）〈Tips for Communicating With Someone Who Has Hearing Loss〉",
        "https://www.asha.org/about/press-room/articles/tips-for-communicating-with-someone-who-has-hearing-loss/",
    ),
    (
        "美國聽損協會（HLAA）〈Communication Tips〉",
        "https://www.hearingloss.org/managing-hearing-loss/hearing-loss-101/communication-tips/",
    ),
)
COMMUNICATION_CHECKED_ON = date(2026, 11, 6)

# Drafts for the owner's review (#429), in our own words from the sources below; no diagnosis,
# promise, fright or number (ADR 0013). The reader is 「您」, the one with hearing loss 「他」.
# The sources say people may blame others for mumbling, but not that arguing backfires: 「爭對錯」
# below is for the owner's clinical review.
RELUCTANT_SITUATIONS = PickExplain(
    code="reluctant-situation",
    prompt="他現在的狀況，最接近哪一種？",
    options=(
        Option(
            label="他不承認聽不到",
            explanation="有些人自己沒有察覺聽力變了，會覺得是別人講話太小聲或不清楚。",
            try_saying=(
                "「這幾次講電話，我發現有些話要講兩次。您自己有這種感覺嗎？」",
                "「我想一直跟您好好聊天，所以才提這件事。」",
                "「不急著決定。您想談的時候，再跟我說。」",
            ),
            avoid_saying=(
                "「您就是聽不到，還不承認。」他可能覺得被指責，反而不想談。",
                "「是您聽不到，不是我講話太小聲。」他可能真的沒有察覺，爭對錯不容易談下去。",
            ),
            next_steps=(("他願意的話，一起做一份問卷（要先註冊或登入）", "questionnaire_list"),),
        ),
        Option(
            label="他不想去檢查",
            explanation="有些人會覺得難為情，也需要時間接受別人注意到他的聽力。",
            try_saying=(
                "「我陪您去。要不要我們一起做一次檢查？」",
                "「檢查聽力跟檢查眼睛一樣，都是照顧身體。」",
                "「先檢查一次留個紀錄，以後可以比較。不是檢查了就要戴助聽器。」",
            ),
            avoid_saying=(
                "「我都幫您約好了，今天一定要去。」逼得太緊容易有反效果，可以等他準備好再幫忙。",
                "「這有什麼好丟臉的，去就對了。」這樣像是在說他的感受不重要。",
            ),
            next_steps=(
                ("還不想去檢查，可以先一起做問卷（要先註冊或登入）", "questionnaire_list"),
                ("檢查完了，把聽力圖記下來（要先註冊或登入）", "audiogram_new"),
            ),
        ),
        Option(
            label="他不想戴助聽器",
            explanation=("有些人擔心戴了顯老、跟別人不一樣，也有人是不喜歡戴起來的感覺或聲音。"),
            try_saying=(
                "「您最想聽清楚什麼？孫子講話，還是講電話？」",
                "「戴起來不舒服或太吵，我們可以一起回去請聽力師調整。」",
                "「要不要先跟有戴助聽器的朋友聊聊？」",
            ),
            avoid_saying=(
                "「戴上去就跟以前一樣了。」助聽器不會讓聽力回到從前，他戴了可能會失望。",
                "「大家早就知道您聽不到了，戴了有什麼關係。」他可能正為這件事覺得難為情。",
            ),
            next_steps=(("看助聽器選配指引", "guide"),),
        ),
    ),
)

RELUCTANT_SOURCES = (
    (
        "美國國家老化委員會（NCOA）"
        "〈How to Talk about Hearing Loss: Signs, Tips, and How to Encourage Treatment〉",
        "https://www.ncoa.org/article/how-to-talk-about-hearing-loss/",
    ),
    (
        "美國聽語學會（ASHA）〈Support for Caregivers and Families of People With Hearing Loss〉",
        "https://www.asha.org/siteassets/ais/ais-support-for-caregivers.pdf",
    ),
    (
        "美國聽語學會（ASHA）〈Helping Others Cope With Hearing Loss〉",
        "https://www.asha.org/siteassets/ais/ais-hearing-loss-helping-others-cope.pdf",
    ),
    (
        "美國國家耳聾及其他溝通障礙研究院（NIDCD）〈Hearing Aids〉",
        "https://www.nidcd.nih.gov/health/hearing-aids",
    ),
)
RELUCTANT_CHECKED_ON = date(2026, 11, 6)

# Drafts for the owner's review (#430, batch-2-wording.md section 1), from the guide's
# 去找聽力師之前 chapter. Its one sentence on the printed report is an item here, and its questions,
# in the reader's own voice there, speak of 他 here (Q17).
VISIT_BRING = (
    "醫院的聽力檢查報告（聽力圖）",
    "身分證",
    "身心障礙證明（有的話）",
    "現在用的助聽器（有的話）",
    "聽伴印的聽力報告（有的話）",
)
# (category, its questions) pairs.
VISIT_QUESTIONS = (
    (
        "適不適合",
        (
            "哪一種助聽器適合他？為什麼？",
            "可以先試戴嗎？試戴多久？要收費嗎？",
        ),
    ),
    (
        "價格與保固",
        (
            "價格包含哪些服務？之後回來調整要另外收費嗎？",
            "保固多久？包含哪些？",
            "可以給我們書面的報價單和保固內容嗎？",
        ),
    ),
    (
        "補助",
        (
            "這一台是補助的哪一個等級（簡易型、中階型、進階型、雙對側傳聲型）？",
            "可以幫他開九號表嗎？",
        ),
    ),
)

# The same chapter's sources and the date it was checked.
VISIT_SOURCES = (
    (
        "身心障礙者輔具費用補助辦法（全國法規資料庫）",
        "https://law.moj.gov.tw/LawClass/LawAll.aspx?PCODE=D0050060",
    ),
    (
        "身心障礙者輔具費用補助基準表（全國法規資料庫）",
        "https://law.moj.gov.tw/LawClass/LawGetFile.ashx?FileId=0000326887&lan=C",
    ),
)
VISIT_CHECKED_ON = date(2026, 10, 22)

# Drafts for the owner's review (#433, batch-3-wording.md section 1). General to every maker: no
# brand names, amounts or laws (types and prices are the guide's). The one to see a doctor comes
# first, so no one spends time checking the aid before it.
_CHECK_FIRST = "可以先檢查"
_SEE_AUDIOLOGIST = "該回去找聽力師"
_URGENT_SECTION = "/family#urgent-title"
HEARING_AID_PROBLEMS = PickExplain(
    code="hearing-aid-problem",
    prompt="現在是什麼狀況？",
    options=(
        Option(
            label="耳朵痛、流膿或突然聽不到",
            urgent="不用先檢查助聽器，請盡快到耳鼻喉科就醫。",
            links=(("什麼時候要馬上就醫", _URGENT_SECTION),),
        ),
        Option(
            label="沒聲音或變小聲",
            urgent="如果是幾小時到幾天內突然聽不到或聽力變差，不用先檢查，請盡快到耳鼻喉科就醫。",
            sections=(
                (
                    _CHECK_FIRST,
                    (
                        "有沒有戴好、有沒有開機；有音量鍵的話，音量是不是太小。",
                        "電池有沒有裝對方向、貼紙撕了沒。不確定就換一顆新的；"
                        "充電式的看有沒有充飽。",
                        "耳模或耳塞有沒有被耳垢或水氣堵住，導管有沒有折到或堵住。",
                    ),
                ),
                (
                    _SEE_AUDIOLOGIST,
                    (
                        "檢查完還是沒聲音，或聲音變形。",
                        "聽力慢慢變差，助聽器需要調整。",
                    ),
                ),
            ),
            links=(("什麼時候要馬上就醫", _URGENT_SECTION),),
        ),
        Option(
            label="一直嘯叫",
            sections=(
                (
                    _CHECK_FIRST,
                    (
                        "有沒有戴好，耳朵和助聽器之間有沒有縫。",
                        "帽子、圍巾或耳機有沒有蓋到助聽器。",
                        "耳模或耳塞有沒有太鬆或破損，導管有沒有裂開。",
                        "有音量鍵的話，可以先暫時調小。",
                    ),
                ),
                (
                    _SEE_AUDIOLOGIST,
                    (
                        "檢查完還是一直叫，或耳模已經鬆了。",
                        "耳朵裡可能有很多耳垢：不要自己挖，請耳鼻喉科或聽力師看看。",
                    ),
                ),
            ),
        ),
        Option(
            label="太吵或聲音太大",
            sections=(
                (
                    _CHECK_FIRST,
                    (
                        "是不是剛開始戴。前幾週可能覺得環境很吵、自己的聲音怪怪的，要時間適應。",
                        "有音量鍵的話，音量是不是太大。",
                    ),
                ),
                (
                    _SEE_AUDIOLOGIST,
                    (
                        "太吵、太小聲或不舒服，都可以請聽力師調整，不用勉強忍耐。",
                        "助聽器沒辦法把想聽和不想聽的聲音完全分開。"
                        "記下哪些場合最困擾，回診時告訴聽力師。",
                    ),
                ),
            ),
        ),
        Option(
            label="有嗡嗡聲",
            sections=(
                (
                    _CHECK_FIRST,
                    ("關機再開機，回到平常的設定。可能是不小心切到感應線圈（T）的設定。",),
                ),
                (
                    _SEE_AUDIOLOGIST,
                    (
                        "開關機之後還有雜音，或聲音變形。",
                        "拿下助聽器還是聽得到，可能不是助聽器的問題，請問耳鼻喉科或聽力師。",
                    ),
                ),
            ),
        ),
        Option(
            label="戴起來會磨、會緊",
            urgent="如果是耳朵痛或流膿，請選第一項。",
            sections=(
                (_CHECK_FIRST, ("有沒有戴對位置、左右耳有沒有戴反。",)),
                (
                    _SEE_AUDIOLOGIST,
                    ("戴對了還是不舒服。耳模或耳塞通常可以調整，不用硬撐。",),
                ),
            ),
        ),
    ),
)

# Drafts for the owner's review (#434, batch-3-wording.md section 2). What /family/reluctant covers
# is linked, not written again; /family's 陪伴配戴助聽器 stays as reviewed.
_YOU_CAN_DO = "您可以做的事"
HEARING_AID_STAGES = PickExplain(
    code="hearing-aid-stage",
    prompt="他現在是哪個階段？",
    options=(
        Option(
            label="剛開始戴",
            sections=(
                (
                    _YOU_CAN_DO,
                    (
                        "告訴他前幾週覺得自己的聲音怪、環境很吵是常見的，大腦需要時間適應。",
                        "照聽力師的建議，陪他從安靜的地方、短時間開始，再慢慢拉長。",
                        "回診時一起學怎麼戴上、拿下、清潔和換電池，回家才幫得上忙。",
                    ),
                ),
            ),
        ),
        Option(
            label="戴了不習慣",
            sections=(
                (
                    _YOU_CAN_DO,
                    (
                        "一起記下哪些場合聽不清楚、哪裡不舒服，回診時告訴聽力師。",
                        "陪他回去調整。適應可能要好幾個月，設定也可能要調整不只一次。",
                        "在吵雜的餐廳、多人聊天時還是可能聽不清楚，說話的方法依然有用。",
                    ),
                ),
            ),
            links=(("怎麼跟聽損的家人說話", "/family#talk-title"),),
        ),
        Option(
            label="不想再戴",
            urgent="如果是耳朵痛或流膿，請盡快就醫。",
            sections=(
                (
                    _YOU_CAN_DO,
                    (
                        "先問他是哪裡不舒服：聲音、耳朵、操作，還是覺得沒有幫助。",
                        "告訴他這些都可以回去請聽力師調整，不用勉強忍耐。",
                        "他不想談的時候，可以看「長輩不肯去怎麼說」。",
                    ),
                ),
            ),
            links=(
                ("什麼時候要馬上就醫", _URGENT_SECTION),
                ("長輩不肯去怎麼說", "/family/reluctant"),
            ),
        ),
    ),
)

# Drafts for the owner's review (#435, batch-3-wording.md section 3). General to every maker, like
# the problems above; the drawings are the ones the owner went through (batch-3-drawings.html).
_CARE_STORE_WORDS = (
    "不戴的時候關機，放進盒子，遠離高溫和潮濕，也放在小孩和寵物拿不到的地方。充電式的照說明書充電。"
)
HEARING_AID_CARE = PickExplain(
    code="hearing-aid-care",
    prompt="他的助聽器是哪一種？",
    options=(
        Option(
            label="掛在耳後",
            steps=(
                CareStep(
                    title="擦乾淨",
                    frequency="每天",
                    words=(
                        "拿下來後，用乾的軟布或面紙擦機身和耳模或耳塞。"
                        "不要弄濕，也不要用含酒精或化學成分的濕紙巾。"
                    ),
                    drawing="behind_ear_wipe",
                ),
                CareStep(
                    title="清耳垢",
                    frequency="每天",
                    words=(
                        "用聽力師給的工具，清掉耳模或耳塞出口的耳垢，不要硬戳。"
                        "耳塞裡有濾網的，濾網有耳垢就換新。"
                    ),
                    drawing="behind_ear_clear_wax",
                ),
                CareStep(
                    title="看導管",
                    frequency="每天",
                    words="導管有沒有折到、堵住或裂開，裡面有沒有水氣。處理不來就問聽力師。",
                    drawing="behind_ear_check_tube",
                ),
                CareStep(
                    title="洗耳模",
                    frequency="有耳模的，約一週一次",
                    words=(
                        "把導管從助聽器的掛鉤拔下來，導管不要從耳模拔出。耳模泡溫肥皂水洗乾淨，"
                        "沖乾淨後把導管裡的水吹出來，放到隔天全乾再裝回去。機身不能碰水。"
                    ),
                    drawing="behind_ear_wash_mould",
                ),
                CareStep(
                    title="關機收好",
                    frequency="每天",
                    words=_CARE_STORE_WORDS,
                    drawing="behind_ear_store",
                ),
            ),
        ),
        Option(
            label="戴在耳內",
            steps=(
                CareStep(
                    title="刷開口",
                    frequency="每天",
                    words="一天結束時，用聽力師給的軟刷，刷掉開口上的耳垢和碎屑。",
                    drawing="in_ear_brush",
                ),
                CareStep(
                    title="挑耳垢",
                    frequency="刷不掉時",
                    words="刷不掉的，用挑耳垢的工具輕輕挑，不要硬戳。",
                    drawing="in_ear_pick",
                ),
                CareStep(
                    title="擦乾淨",
                    frequency="每天",
                    words="用乾淨的乾布或面紙全部擦過。不要弄濕。",
                    drawing="in_ear_wipe",
                ),
                CareStep(
                    title="關機收好",
                    frequency="每天",
                    words=_CARE_STORE_WORDS,
                    drawing="in_ear_store",
                ),
            ),
            steps_note="深耳道型這種放在耳道很深處的，由聽力師在回診時清潔。",
        ),
    ),
)
HEARING_AID_CARE_REMINDERS = (
    "戴著助聽器時不要噴髮膠或用其他美髮產品。",
    "沒電的電池馬上換；電池放在小孩和寵物拿不到的地方。",
)

# The sources of batch-3-wording.md section 4, for the whole page. Medical care is rewritten for
# Taiwan: from the UK and US sources, only the things to check are taken.
HEARING_AID_SOURCES = (
    (
        "RNID：Solving common hearing aid problems（2026/06/02 更新）",
        "https://rnid.org.uk/information-and-support/hearing-aids/solving-common-problems/",
    ),
    (
        "RNID：Cleaning and maintaining your hearing aids（2026/06/01 更新）",
        "https://rnid.org.uk/information-and-support/hearing-aids/cleaning-maintaining/",
    ),
    (
        "NIDCD：Hearing Aids（2022/10/11 更新）",
        "https://www.nidcd.nih.gov/health/hearing-aids",
    ),
    (
        "FDA：Hearing Aid Benefits and Limitations（2022/11/18 更新）",
        "https://www.fda.gov/medical-devices/hearing-aids/hearing-aid-benefits-and-limitations",
    ),
    (
        "Cambridge University Hospitals：NHS hearing aids problem solving（2025/04/15 核定）",
        "https://www.cuh.nhs.uk/patient-information/nhs-hearing-aids-problem-solving/",
    ),
    (
        "Hampshire Hospitals：Hearing Aid Troubleshooting Guide（沒有標日期）",
        "https://www.hampshirehospitals.nhs.uk/our-services/az-departments-and-specialties/"
        "audiology-1/adult-services/hearing-aid-troubleshooting-guide",
    ),
    ("聽伴選配指引「配戴之後」的審定內容", "/guide/after-fitting"),
    ("家人專區的審定內容", "/family"),
)
HEARING_AID_CHECKED_ON = date(2026, 11, 6)
