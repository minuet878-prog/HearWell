from dataclasses import dataclass
from datetime import date

from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers

from screening import questionnaires
from screening.care_journey import care_journey
from screening.views.answering import continue_notice


def greeting(hour):
    """#458 D2: by the hour in Taiwan (TIME_ZONE); 晚安 runs past midnight until 5."""
    if 5 <= hour < 12:
        return "早安"
    if 12 <= hour < 18:
        return "午安"
    return "晚安"


def index(request):
    user = request.user
    if not user.is_authenticated:
        # #471 (mockup #458 ⑪): a visitor sees the 空狀態首頁; no one's records, so it may be
        # cached. #499: guest-home.js draws a guest result kept in the browser on top, from each
        # guest questionnaire's topic and result page.
        guest_questionnaires = {
            code: {
                "topic": questionnaires.get(code).topic,
                "url": reverse("guest_result", args=[code]),
            }
            for code in questionnaires.for_guests()
        }
        return render(
            request, "screening/index.html", {"guest_questionnaires": guest_questionnaires}
        )
    # #459 (ADR 0044): the 照顧旅程 for anyone with a questionnaire or an audiogram, else the
    # 空狀態首頁.
    has_records = user.submissions.defined().exists() or user.audiograms.exists()
    journey = care_journey(user, timezone.localdate()) if has_records else None
    response = render(
        request,
        "screening/index.html",
        {
            "journey": journey,
            "greeting": greeting(timezone.localtime().hour),
            "continue_notice": continue_notice(user),
        },
    )
    # The home page shows this account's own records (ticket #159): never cached.
    add_never_cache_headers(response)
    return response


def family_guide(request):
    # Spec phase8_c1_family_guide.md: the same reviewed content for everyone, no user data.
    # #469: its communication tips and scenarios are on family_talk.
    # The address to pass on takes the scheme the page was opened with (https on tingpal.tw).
    context = {"family_url": request.build_absolute_uri(reverse("family_guide"))}
    return render(request, "screening/family_guide.html", context)


# Spec #633 (#640): the day the owner last checked 關於聽伴; on the yearly review list. The
# owner's words were final that day (#635, #642).
ABOUT_CHECKED_ON = date(2026, 11, 16)


def about(request):
    # Spec #633 (#640): open to everyone, like the privacy notice whose highlights it shows; it
    # reads no records.
    return render(request, "screening/about.html", {"checked_on": ABOUT_CHECKED_ON})


@dataclass(frozen=True)
class LearnItem:
    """One of the 了解 page's items: its card in the stack and its row in the list (#754)."""

    key: str  # learn_drawing.html's drawing on its card
    url_name: str
    icon: str  # action_icon.html's, on its row
    title: str
    line: str  # under the card's title
    button: str  # the card's white button
    row_line: str = ""  # under the row's title


# The list's order (#469, #487, #640), its rows' words the canvas's ProLearn. The cards' lines
# and buttons past the simulator's are drafts for the owner's review.
SIMULATOR = LearnItem(
    "simulator",
    "hearing_loss_simulator",
    "sound",
    "聽損模擬",
    "了解聽損者的感覺",
    "聽聽看",
    "聽聽看他聽到的聲音",
)
GUIDE = LearnItem(
    "guide", "guide", "guide", "了解助聽器選配與補助", "從聽力檢查到申請補助", "開始了解"
)
QA = LearnItem(
    "qa", "qa_home", "question", "問答小助手", "常見問題一次查", "問問看", "常見問題一次查"
)
LEARN_ITEMS = (
    GUIDE,
    LearnItem("family", "family_guide", "family", "家人專區", "溝通與陪伴", "去看看", "溝通與陪伴"),
    SIMULATOR,
    QA,
    LearnItem(
        "about",
        "about",
        "info",
        "關於聽伴",
        "誰做的、內容怎麼查核",
        "認識聽伴",
        "誰做的、內容怎麼查核",
    ),
)
# Spec #741 P23: the first card is the item most about the 現在這一步; about none, the
# simulator. Step 2's 查詢醫療院所 is the assistant's answer; the guide is steps 4 to 6's, its
# 配戴之後 chapter step 6's. Drafts for the owner's review.
FIRST_FOR_STEP = {2: QA, 4: GUIDE, 5: GUIDE, 6: GUIDE}


def learn(request):
    # #269 (spec #268): open without logging in, like the guide and the family page it leads to.
    # #754 (spec #741 P23): the stacked cards, the item most about the 現在這一步 first (the
    # simulator when not logged in or without a record, as the home page has no 照顧旅程
    # then), the rest in the list's order; the whole list under them.
    user = request.user
    first = SIMULATOR
    if user.is_authenticated and (user.submissions.defined().exists() or user.audiograms.exists()):
        first = FIRST_FOR_STEP.get(care_journey(user, timezone.localdate()).current, SIMULATOR)
    stack = [first, *(item for item in LEARN_ITEMS if item != first)]
    response = render(request, "screening/learn.html", {"stack": stack, "items": LEARN_ITEMS})
    # Logged in, the first card follows this account's records: never cached (CODING_STANDARDS
    # 24, as the home page).
    if user.is_authenticated:
        add_never_cache_headers(response)
    return response
