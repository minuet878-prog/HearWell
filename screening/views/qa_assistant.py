from django.http import Http404
from django.shortcuts import render

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


def qa_answer(request, code):
    # One question a page (spec #396), its address shared with family: the same for everyone.
    faq = content.BY_CODE.get(code)
    if faq is None:
        raise Http404
    return render(request, "screening/qa/answer.html", {"faq": faq})
