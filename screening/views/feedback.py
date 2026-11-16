from urllib.parse import urlencode

from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from screening.forms import FeedbackForm
from screening.models import Feedback
from screening.qa_assistant import content
from screening.views.common import safe_next
from screening.views.guide import GUIDE_CHAPTERS

# Spec #633 Q5: the page a 意見回饋 was sent from, by URL name, in the words people know it by.
# Only the kind of page: never its address, so no record number or share code comes along.
PAGE_NAMES = {
    "index": "首頁",
    "login": "登入",
    "register": "註冊",
    "password_reset": "忘記密碼",
    "password_reset_sent": "忘記密碼",
    "password_reset_confirm": "設新密碼",
    "google_name": "用 Google 註冊",
    "line_name": "用 LINE 註冊",
    "consent": "同意書",
    "privacy": "隱私權說明",
    "add_to_home": "加到手機主畫面",
    "learn": "了解",
    "hearing_loss_simulator": "聽損模擬",
    "family_guide": "家人專區",
    "family_talk": "家人專區：怎麼跟他說話",
    "family_reluctant": "家人專區：長輩不肯檢查",
    "family_hearing_aids": "家人專區：助聽器",
    "family_visits": "家人專區：陪診",
    "family_subsidy_check": "家人專區：補助還缺什麼",
    "family_deadlines": "家人專區：補助期限試算",
    "qa_home": "問答小助手",
    "qa_topic": "問答小助手",
    "qa_results": "問答小助手",
    "guide": "助聽器選配與補助",
    "questionnaire_list": "選問卷",
    "screening": "作答頁",
    "guest_result": "結果頁",
    "guest_save": "保存結果",
    "result": "結果頁",
    "my_hearing": "我的紀錄",
    "hhi_comparison": "前後比較",
    "health_report": "聽力報告",
    "share_report": "分享報告給家人",
    "shared_cover": "家人看的聽力報告",
    "shared_report": "家人看的聽力報告",
    "account_settings": "帳號設定",
    "delete_account": "刪除帳號",
    "confirm_identity": "確認本人",
    "audiogram_list": "聽力圖",
    "audiogram_new": "記錄聽力圖",
    "audiogram_compare": "聽力圖比較",
    "audiogram_detail": "聽力圖",
    "audiogram_edit": "修改聽力圖",
}
GUIDE_CHAPTER_TITLES = {chapter.slug: chapter.title for chapter in GUIDE_CHAPTERS}


def page_words(page):
    """The words for a footer link's page (feedback_link), or "" for one not known."""
    name, _, code = page.partition(":")
    if name == "guide_chapter" and code in GUIDE_CHAPTER_TITLES:
        return f"選配指引：{GUIDE_CHAPTER_TITLES[code]}"
    if name == "qa_answer" and code in content.BY_CODE:
        return f"問答小助手：{content.BY_CODE[code].question}"
    return "" if code else PAGE_NAMES.get(name, "")


@require_http_methods(["GET", "POST"])
def feedback(request):
    """Spec #633 (#636): the 意見回饋 page, open to everyone, signed in or not."""
    form = FeedbackForm(request.POST or None)
    page = request.POST.get("page") or request.GET.get("page", "")
    # Only to make the sent page's way back; never kept.
    next_url = safe_next(request)
    sent = reverse("feedback_sent")
    if next_url:
        sent = f"{sent}?{urlencode({'next': next_url})}"
    if request.method == "POST":
        # Q9: the box only robots fill. Told it was sent, whatever else it sent, so it learns
        # nothing; nothing is kept.
        if request.POST.get("website"):
            return redirect(sent)
        if form.is_valid():
            # ADR 0064: anonymous, signed in or not.
            Feedback.objects.create(
                text=form.cleaned_data["text"],
                email=form.cleaned_data["email"],
                page=page_words(page),
            )
            # Post/Redirect/Get: reloading the sent page sends nothing again.
            return redirect(sent)
    return render(
        request,
        "screening/feedback.html",
        {
            "form": form,
            "page": page,
            "page_words": page_words(page),
            "next": next_url,
            # Q7: the Q&A assistant's urgent box, before the form.
            "urgent": content.BY_CODE[content.URGENT_CODE],
        },
    )


@require_http_methods(["GET"])
def feedback_sent(request):
    return render(request, "screening/feedback_sent.html", {"next": safe_next(request)})
