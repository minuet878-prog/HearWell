"""The family zone's words (spec #426): one definition to review, no words in the templates."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Option:
    label: str
    # What this choice does, in plain words. Every choice has one and none is a verdict: no right,
    # wrong or score (#428).
    explanation: str


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
