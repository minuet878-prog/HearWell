"""公開頁面 (GLOSSARY.md): the pages open without logging in that search engines may index.

ADR 0062: every other answer carries noindex, so a new page is kept out of search until it is
listed here. The one list of the site: the sitemap reads it too (spec #583).
"""

from dataclasses import dataclass
from functools import cache

from django.urls import reverse

from screening.qa_assistant import content
from screening.views.guide import GUIDE_CHAPTERS
from screening.views.qa_assistant import topic_faqs

# The protocol of every full address this site gives out: canonical links, the sitemap, robots.txt.
PROTOCOL = "https"

# Every other page's description in a LINE preview (the titles table's E1, #587).
SITE_DESCRIPTION = (
    "聽伴是聽力自我照護工具：花 3 分鐘回答問題，看聽力對生活的影響。"
    "內容由台灣執業聽力師設計與審定。"
)

# The one LINE preview image (#588's design C, #590), 1200x630, exported from
# docs/planning/found-by-family/line-preview-image.html.
PREVIEW_IMAGE = "screening/line-preview.png"

# One address each, by URL name: (title, description) as the owner confirmed them (#587).
SINGLE_PAGES = {
    "index": (
        "聽伴｜3 分鐘聽力自我篩檢，不用註冊",  # noqa: RUF001
        "聽力變化很慢，自己常常沒發現。花 3 分鐘回答問題，馬上看到聽力對生活的影響和建議，"
        "不用註冊。內容由台灣執業聽力師設計與審定。",
    ),
    "learn": (
        "認識聽損與助聽器：選配、補助、家人怎麼幫｜聽伴",  # noqa: RUF001
        "助聽器選配與補助、給家人的溝通與陪伴方法、聽損模擬、常見問題，不用登入就能看。",
    ),
    "hearing_loss_simulator": (
        "聽力不好的人聽到的聲音是什麼樣子？聽損模擬｜聽伴",  # noqa: RUF001
        "選一種聽損程度，聽同一句話變成什麼樣子，再切回正常聽比一比。聽聽看他聽到的聲音。",
    ),
    "privacy": (
        "隱私權說明｜聽伴",  # noqa: RUF001
        "聽伴蒐集哪些資料、為什麼蒐集、存放在哪裡、保存多久，以及您可以要求什麼。",
    ),
    # Spec #633 (#640): the owner confirmed its row (A5) in #635.
    "about": (
        "關於聽伴：誰做的、內容怎麼查核｜聽伴",  # noqa: RUF001
        "聽伴是誰做的、內容怎麼查核、資料怎麼處理，以及為什麼不能取代聽力檢查。",
    ),
    "family_guide": (
        "家人聽力不好怎麼辦？給家屬的溝通與陪伴方法｜聽伴",  # noqa: RUF001
        "家人有聽力困難時，日常對話常常要講好幾次。這裡整理怎麼跟他說話、陪診要帶什麼、"
        "長輩不肯去怎麼說，以及怎麼陪他適應助聽器。",
    ),
    "family_talk": (
        "怎麼跟聽力不好的家人說話？不用大喊的溝通方法｜聽伴",  # noqa: RUF001
        "先叫名字、面對面、說清楚不用大喊、聽不懂就換個說法。幾個小方法加上情境題，讓對話輕鬆一點。",
    ),
    "family_reluctant": (
        "長輩不肯檢查聽力、不肯戴助聽器，怎麼開口？｜聽伴",  # noqa: RUF001
        "挑一個不趕時間的時候慢慢談。選一種最接近的狀況，看看可以怎麼說；不一定談一次就有結果。",
    ),
    "family_hearing_aids": (
        "爸媽的助聽器怪怪的、戴不習慣怎麼辦？｜聽伴",  # noqa: RUF001
        "助聽器怪怪的先檢查什麼、怎麼陪長輩適應、怎麼戴上和拿下、日常怎麼保養。",
    ),
    "family_visits": (
        "陪爸媽檢查聽力、配助聽器：要帶什麼、要問什麼｜聽伴",  # noqa: RUF001
        "可以列印的陪診清單：要帶的東西、想問聽力師的問題。要申請身障補助，一定要先拿到核定通知再買。",
    ),
    "family_subsidy_check": (
        "助聽器補助還缺什麼？回答幾題就知道｜聽伴",  # noqa: RUF001
        "回答幾題，看申請助聽器補助還缺什麼。這裡不判斷能不能拿到補助，是否補助以主管機關核定為準。"
        "回答不會留下來。",
    ),
    "family_deadlines": (
        "助聽器補助的期限到哪一天？輸入日期試算｜聽伴",  # noqa: RUF001
        "輸入九號表開立、收到核定通知或開始配戴的日期，算出各個期限。只填一個也可以，日期不會留下來。",
    ),
    # Spec #655 (#675): the three family pages, rows B8–B10 the owner confirmed in #671.
    "family_signs": (
        "爸媽的聽力還好嗎？聽力變差時常見的日常情況｜聽伴",  # noqa: RUF001
        "看電視、講電話、吃飯聊天、在家裡時，有哪些情況值得留意。有這些情況，建議儘早做聽力檢查；"
        "也可以把 3 分鐘的聽力自我篩檢傳給爸媽，不用註冊。",
    ),
    "family_loud_tv": (
        "爸媽看電視開很大聲，怎麼辦？｜聽伴",  # noqa: RUF001
        "開大聲不等於聽得清楚。看看為什麼會這樣、在家可以先試什麼，"
        "再把 3 分鐘的聽力自我篩檢傳給爸媽，不用註冊。",
    ),
    "family_huh": (
        "跟他講話，他一直說「蛤」？聽得到卻聽不清楚的原因｜聽伴",  # noqa: RUF001
        "一直「蛤」常常是聽到聲音、卻聽不清楚在說什麼。看看可能的原因，"
        "戴上耳機聽聽他聽到的聲音，再學幾個不用大喊的說話方法。",
    ),
    "guide": (
        "助聽器選配與補助：從檢查到領補助，一步一步看｜聽伴",  # noqa: RUF001
        "去找聽力師之前要準備什麼、身障鑑定怎麼做、補助怎麼申請、助聽器的種類與價格，"
        "六個章節照順序看，不用登入。",
    ),
    "qa_home": (
        "聽力、助聽器、補助的常見問題｜聽伴",  # noqa: RUF001
        "依主題找，或用自己的話問，答案都經過聽力師審定。突然聽不到、耳朵流血，請盡快就醫。",
    ),
}


@dataclass(frozen=True)
class PublicPage:
    path: str
    # In the browser tab and search results; the page's own big heading stays as it is.
    title: str
    # Under the title in search results.
    description: str


@cache
def pages():
    """{path: PublicPage} of every 公開頁面. Pages are defined in code, so they never change while
    the site runs."""
    pages = [
        *(PublicPage(reverse(name), *head) for name, head in SINGLE_PAGES.items()),
        *(
            PublicPage(
                reverse("guide_chapter", args=[chapter.slug]),
                chapter.search_title,
                chapter.description,
            )
            for chapter in GUIDE_CHAPTERS
        ),
        *(
            PublicPage(reverse("qa_topic", args=[slug]), *content.TOPIC_SEARCH[slug])
            for slug, _name in content.TOPICS
            if topic_faqs(slug)
        ),
        # Every answer, a referral answer too; one taken out (ADR 0033) is no longer in FAQS.
        *(
            PublicPage(
                reverse("qa_answer", args=[faq.code]),
                f"{faq.question}｜聽伴",  # noqa: RUF001
                faq.description,
            )
            for faq in content.FAQS
        ),
    ]
    return {page.path: page for page in pages}


def public_urls():
    """Every 公開頁面's address, as a path."""
    return tuple(pages())


def page_at(path):
    """The 公開頁面 at this path, or None."""
    return pages().get(path)


def is_public(path):
    return page_at(path) is not None
