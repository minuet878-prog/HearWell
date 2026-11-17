import logging
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template import loader
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from rest_framework.throttling import BaseThrottle

from screening.forms import (
    FEEDBACKS_PER_ADDRESS,
    FEEDBACKS_PER_DAY,
    HELP_ADDRESS,
    TOO_MANY_FEEDBACKS_AN_HOUR,
    FeedbackForm,
    add_attempt,
    attempts,
)
from screening.models import Feedback, FeedbackNotice
from screening.public_pages import PROTOCOL
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
    "google_same_email": "用 Google 註冊",
    "line_name": "用 LINE 註冊",
    "consent": "同意書",
    "privacy": "隱私權說明",
    "feedback": "意見回饋",
    "feedback_sent": "意見回饋",
    "about": "關於聽伴",
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
    "add_email": "補上 email",
    "confirm_identity": "確認本人",
    "reminder_cancel": "取消重測提醒",
    "reminder_cancelled": "取消重測提醒",
    "audiogram_list": "聽力圖",
    "audiogram_new": "記錄聽力圖",
    "audiogram_compare": "聽力圖比較",
    "audiogram_detail": "聽力圖",
    "audiogram_edit": "修改聽力圖",
    "audiogram_delete": "刪除聽力圖",
    "audiogram_speech_banana": "聽力圖的語言香蕉區",
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


logger = logging.getLogger(__name__)


def notify_owner(request, feedback):
    """#638 (spec #633 Q10): the first 意見回饋 of a Taipei day sends the owner one 回饋通知信,
    the admin list's link and nothing that was sent. A notice that cannot go is not sent again:
    the feedback is kept all the same, and the owner sees the error in Sentry. The day is the
    feedback's own, so one kept at 23:59:59 never takes the next day's notice (cross review)."""
    _, first = FeedbackNotice.objects.get_or_create(day=timezone.localdate(feedback.created_at))
    if not first:
        return
    admin_url = f"{PROTOCOL}://{request.get_host()}{reverse('admin:screening_feedback_changelist')}"
    subject = loader.render_to_string("screening/feedback_notice_subject.txt").strip()
    body = loader.render_to_string("screening/feedback_notice_email.txt", {"admin_url": admin_url})
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [HELP_ADDRESS])
    except Exception:
        # A fixed message: the mail service's own words may hold an address (Sentry and this
        # machine's log drop them: config.monitoring).
        logger.exception("A feedback notice could not be sent")


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
    too_many = ""
    if request.method == "POST":
        # #637: the address as the guest scoring limit takes it (NUM_PROXIES: X-Forwarded-For's
        # last, which Nginx adds). Only its hashed count is kept, for an hour. A mistake to fix
        # is no sending, so it does not count.
        address = BaseThrottle().get_ident(request)
        # Q9: the box only robots fill. Told it was sent, whatever else it sent and however many
        # it sent before, so it learns nothing; nothing is kept. It counts as a sending.
        if request.POST.get("website"):
            add_attempt("feedback", address)
            return redirect(sent)
        if attempts("feedback", address) >= FEEDBACKS_PER_ADDRESS:
            too_many = "hour"
        elif form.is_valid():
            # #637: the site's whole day, Taipei time.
            kept_today = Feedback.objects.filter(created_at__date=timezone.localdate()).count()
            if kept_today >= FEEDBACKS_PER_DAY:
                too_many = "day"
            else:
                add_attempt("feedback", address)
                # ADR 0064: anonymous, signed in or not.
                feedback = Feedback.objects.create(
                    text=form.cleaned_data["text"],
                    email=form.cleaned_data["email"],
                    page=page_words(page),
                )
                notify_owner(request, feedback)
                # Post/Redirect/Get: reloading the sent page sends nothing again.
                return redirect(sent)
    return render(
        request,
        "screening/feedback.html",
        {
            "form": form,
            "too_many": too_many,
            "too_many_an_hour": TOO_MANY_FEEDBACKS_AN_HOUR,
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
