import dataclasses
import re
from collections import Counter
from datetime import date

from django.test import SimpleTestCase
from django.urls import Resolver404, resolve

from screening.qa_assistant import content

# ADR 0032: the four referral answers, by code.
REFERRALS = {"my-results", "diagnosis-and-medication", "brands-and-shops", "sudden-hearing-loss"}


def duplicate_codes(faqs):
    return sorted(code for code, count in Counter(faq.code for faq in faqs).items() if count > 1)


def without_sources_or_date(faqs):
    return [
        faq.code
        for faq in faqs
        if not faq.sources
        or not all(title and url for title, url in faq.sources)
        or not isinstance(faq.checked_on, date)
    ]


def missing_referrals(faqs):
    referrals = {faq.code for faq in faqs if faq.referral}
    return sorted(REFERRALS - referrals)


def unknown_codes(codes, faqs):
    known = {faq.code for faq in faqs}
    return [code for code in codes if code not in known]


def broken_site_links(faqs):
    """Every site path an answer or its sources link to, that no page answers."""
    broken = []
    for faq in faqs:
        paths = re.findall(r'href="(/[^"#]*)', faq.answer)
        paths += [url.split("#")[0] for _, url in faq.sources if url.startswith("/")]
        for path in paths:
            try:
                resolve(path)
            except Resolver404:
                broken.append((faq.code, path))
    return broken


class FaqDefinitionTests(SimpleTestCase):
    """#397 (spec #396, ADR 0033): mistakes in content.py fail here, not on the site."""

    def test_codes_are_unique(self):
        self.assertEqual(duplicate_codes(content.FAQS), [])

    def test_every_question_has_sources_and_a_check_date(self):
        self.assertEqual(without_sources_or_date(content.FAQS), [])

    def test_the_four_referral_answers_are_there(self):
        self.assertEqual(missing_referrals(content.FAQS), [])

    def test_popular_and_the_urgent_answer_point_at_questions_that_exist(self):
        self.assertEqual(unknown_codes(content.POPULAR, content.FAQS), [])
        self.assertEqual(unknown_codes((content.URGENT_CODE,), content.FAQS), [])

    def test_every_question_is_in_one_of_the_four_topics(self):
        topics = {slug for slug, _ in content.TOPICS}
        self.assertEqual([faq.code for faq in content.FAQS if faq.topic not in topics], [])

    def test_answers_link_to_pages_that_exist(self):
        self.assertEqual(broken_site_links(content.FAQS), [])


class FaqDefinitionChecksCatchMistakesTests(SimpleTestCase):
    """The checks above fail on a broken definition, so passing means something."""

    def setUp(self):
        self.faq = content.FAQS[0]

    def test_a_repeated_code(self):
        self.assertEqual(duplicate_codes((self.faq, self.faq)), [self.faq.code])

    def test_a_question_without_sources_or_check_date(self):
        no_sources = dataclasses.replace(self.faq, code="no-sources", sources=())
        no_title = dataclasses.replace(self.faq, code="no-title", sources=(("", "/guide"),))
        no_date = dataclasses.replace(self.faq, code="no-date", checked_on=None)
        self.assertEqual(
            without_sources_or_date((self.faq, no_sources, no_title, no_date)),
            ["no-sources", "no-title", "no-date"],
        )

    def test_a_missing_referral_answer(self):
        others = [faq for faq in content.FAQS if faq.code != "brands-and-shops"]
        self.assertEqual(missing_referrals(others), ["brands-and-shops"])
        unmarked = [dataclasses.replace(faq, referral=False) for faq in content.FAQS]
        self.assertEqual(missing_referrals(unmarked), sorted(REFERRALS))

    def test_popular_pointing_at_no_question(self):
        self.assertEqual(unknown_codes(("my-results", "gone"), content.FAQS), ["gone"])

    def test_a_link_to_no_page(self):
        broken = dataclasses.replace(self.faq, answer='<p><a href="/no-such-page">x</a></p>')
        self.assertEqual(broken_site_links((broken,)), [(self.faq.code, "/no-such-page")])
