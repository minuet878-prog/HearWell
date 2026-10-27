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
RESULTS = "qa_results"

# 幾題可能相關: the best few, not every question sharing a word.
MOST_RESULTS = 5


def qa_home(request):
    # Spec #396: open without logging in, the same for everyone; it reads no records (ADR 0032),
    # so it is not a 健康資料頁面.
    return _home_page(request, QaQuestionForm())


def _home_page(request, form):
    return render(
        request,
        "screening/qa/home.html",
        {
            "urgent": content.BY_CODE[content.URGENT_CODE],
            "popular": [content.BY_CODE[code] for code in content.POPULAR],
            "topics": content.TOPICS,
            "form": form,
        },
    )


def qa_topic(request, topic):
    # Spec #396: a topic's questions, open to everyone like the home page. The urgent answer is
    # pinned on the home page instead of sitting in a list (prototype #373).
    name = dict(content.TOPICS).get(topic)
    if name is None:
        raise Http404
    faqs = [faq for faq in content.FAQS if faq.topic == topic and faq.code != content.URGENT_CODE]
    return render(request, "screening/qa/topic.html", {"name": name, "faqs": faqs})


def qa_answer(request, code):
    # One question a page (spec #396), its address shared with family: the same for everyone.
    # ADR 0033: a question taken out leaves its shared address leading to the home page.
    if code in content.RETIRED_CODES:
        return redirect("qa_home")
    faq = content.BY_CODE.get(code)
    if faq is None:
        raise Http404
    # The urgent answer is on no topic page, so it leads back to the home page instead (#398).
    topic = None if faq.code == content.URGENT_CODE else faq.topic
    return render(
        request,
        "screening/qa/answer.html",
        {
            "faq": faq,
            "topic": topic,
            "topic_name": dict(content.TOPICS).get(topic),
            "related": [content.BY_CODE[code] for code in faq.related],
        },
    )


@require_http_methods(["POST"])
def qa_search(request):
    # #399: posted, so the question stays out of the address and the history; then
    # Post/Redirect/Get, so going back never asks to send the form again.
    form = QaQuestionForm(request.POST)
    if not form.is_valid():
        return _home_page(request, form)
    question = form.cleaned_data["question"]
    codes = match(question)
    # #400 (ADR 0034): every typed question, anonymously, with the first question it matched.
    QuestionLog.objects.create(question=question, faq_code=codes[0] if codes else "")
    # #401: there is no scheduler, so each new question also clears those past 90 days.
    purge_question_log()
    request.session[RESULTS] = codes[:MOST_RESULTS]
    return HttpResponseRedirect(reverse("qa_results"))


def qa_results(request):
    # #399: kept until the next question, so reloading or going back shows them again.
    codes = request.session.get(RESULTS)
    if codes is None:
        return HttpResponseRedirect(reverse("qa_home"))
    response = render(
        request,
        "screening/qa/results.html",
        {
            # A question taken out since (ADR 0033) is left out.
            "faqs": [content.BY_CODE[code] for code in codes if code in content.BY_CODE],
            "popular": [content.BY_CODE[code] for code in content.POPULAR],
            "topics": content.TOPICS,
        },
    )
    # They come from this browser's session and the next question changes them.
    add_never_cache_headers(response)
    return response
