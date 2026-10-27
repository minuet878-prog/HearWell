from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers
from django.views.decorators.http import require_http_methods

from screening.forms import QaQuestionForm
from screening.models import QuestionLog, purge_question_log
from screening.qa_assistant import content
from screening.qa_assistant.matching import match

# #399 (spec #396): the codes of the questions a typed question matched, never the question
# itself: the session is tied to the cookie, so to whoever is signed in.
RESULTS_SESSION_KEY = "qa_results"
# A blank or too long question's hints for the home page, shown once; never the question.
HINT_SESSION_KEY = "qa_hint"

# 幾題可能相關: the best few, not every question sharing a word.
MOST_RESULTS = 5

TOPIC_NAMES = dict(content.TOPICS)
# Each topic tile's icon (action_icon.html), the owner's pick (2026-10-27).
TOPIC_ICONS = {
    "using-the-site": "home",
    "questionnaires": "clipboard",
    "hearing-aids": "guide",
    "hearing-health": "ear",
}


def _topics():
    # 依主題找, on the home page and when a typed question matched nothing.
    return [(slug, name, TOPIC_ICONS[slug]) for slug, name in content.TOPICS]


def _popular():
    # 大家常問, on the home page and when a typed question matched nothing.
    return [content.BY_CODE[code] for code in content.POPULAR]


def _listed_topic(faq):
    # The topic page listing a question. The urgent answer is on none: it is pinned on the home
    # page instead (prototype #373), and its answer leads back there (#398).
    return None if faq.code == content.URGENT_CODE else faq.topic


def qa_home(request):
    # Spec #396: open without logging in, the same for everyone; it reads no records (ADR 0032),
    # so it is not a 健康資料頁面.
    hints = request.session.pop(HINT_SESSION_KEY, None)
    form = QaQuestionForm() if hints is None else QaQuestionForm.showing(hints)
    return render(
        request,
        "screening/qa/home.html",
        {
            "urgent": content.BY_CODE[content.URGENT_CODE],
            "popular": _popular(),
            "topics": _topics(),
            "form": form,
        },
    )


def qa_topic(request, topic):
    # Spec #396: a topic's questions, open to everyone like the home page.
    name = TOPIC_NAMES.get(topic)
    if name is None:
        raise Http404
    faqs = [faq for faq in content.FAQS if _listed_topic(faq) == topic]
    return render(request, "screening/qa/topic.html", {"name": name, "faqs": faqs})


def qa_answer(request, code):
    # One question a page (spec #396), its address shared with family: the same for everyone.
    # ADR 0033: a question taken out leaves its shared address leading to the home page.
    if code in content.RETIRED_CODES:
        return redirect("qa_home")
    faq = content.BY_CODE.get(code)
    if faq is None:
        raise Http404
    topic = _listed_topic(faq)
    return render(
        request,
        "screening/qa/answer.html",
        {
            "faq": faq,
            "topic": topic,
            "topic_name": TOPIC_NAMES.get(topic),
            "related": [content.BY_CODE[code] for code in faq.related],
        },
    )


@require_http_methods(["POST"])
def qa_search(request):
    # #399: posted, so the question stays out of the address and the history; then
    # Post/Redirect/Get, a blank or too long one too, so going back never meets a posted page.
    form = QaQuestionForm(request.POST)
    if not form.is_valid():
        request.session[HINT_SESSION_KEY] = form.errors.get_json_data()["question"]
        return HttpResponseRedirect(reverse("qa_home"))
    question = form.cleaned_data["question"]
    codes = match(question)
    # #400 (ADR 0034): every typed question, anonymously, with the first question it matched.
    QuestionLog.objects.create(question=question, faq_code=codes[0] if codes else "")
    # #401: there is no scheduler, so each new question also clears those past 90 days.
    purge_question_log()
    request.session[RESULTS_SESSION_KEY] = codes[:MOST_RESULTS]
    return HttpResponseRedirect(reverse("qa_results"))


def qa_results(request):
    # #399: kept until the next question, so reloading or going back shows them again.
    codes = request.session.get(RESULTS_SESSION_KEY)
    if codes is None:
        return HttpResponseRedirect(reverse("qa_home"))
    response = render(
        request,
        "screening/qa/results.html",
        {
            # A question taken out since (ADR 0033) is left out.
            "faqs": [content.BY_CODE[code] for code in codes if code in content.BY_CODE],
            "popular": _popular(),
            "topics": _topics(),
        },
    )
    # They come from this browser's session and the next question changes them.
    add_never_cache_headers(response)
    return response
