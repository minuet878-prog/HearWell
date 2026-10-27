from django.http import Http404
from django.shortcuts import redirect, render

from screening.qa_assistant import content


def qa_home(request):
    # Spec #396: open without logging in, the same for everyone; it reads no records (ADR 0032),
    # so it is not a 健康資料頁面.
    return render(
        request,
        "screening/qa/home.html",
        {
            "urgent": content.BY_CODE[content.URGENT_CODE],
            "popular": [content.BY_CODE[code] for code in content.POPULAR],
            "topics": content.TOPICS,
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
