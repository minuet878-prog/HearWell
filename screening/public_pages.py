"""公開頁面 (GLOSSARY.md): the pages open without logging in that search engines may index.

ADR 0062: every other answer carries noindex, so a new page is kept out of search until it is
listed here. The one list of the site: the sitemap reads it too (spec #583).
"""

from functools import cache

from django.urls import reverse

from screening.qa_assistant import content
from screening.views.guide import GUIDE_CHAPTERS
from screening.views.qa_assistant import topic_faqs

# One address each, by URL name.
SINGLE_PAGES = (
    "index",
    "learn",
    "hearing_loss_simulator",
    "privacy",
    "family_guide",
    "family_talk",
    "family_reluctant",
    "family_hearing_aids",
    "family_visits",
    "family_subsidy_check",
    "family_deadlines",
    "guide",
    "qa_home",
)


@cache
def public_urls():
    """Every 公開頁面's address, as a path. Pages are defined in code, so they never change while
    the site runs."""
    return (
        *(reverse(name) for name in SINGLE_PAGES),
        *(reverse("guide_chapter", args=[chapter.slug]) for chapter in GUIDE_CHAPTERS),
        *(reverse("qa_topic", args=[slug]) for slug, _name in content.TOPICS if topic_faqs(slug)),
        # Every answer, a referral answer too; one taken out (ADR 0033) is no longer in FAQS.
        *(reverse("qa_answer", args=[faq.code]) for faq in content.FAQS),
    )


def is_public(path):
    return path in public_urls()
