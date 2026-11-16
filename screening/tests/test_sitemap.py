"""The sitemap and robots.txt hand search engines the 公開頁面 (spec #583, ticket #586)."""

from unittest import mock
from xml.etree import ElementTree

from django.test import TestCase

from screening import public_pages
from screening.qa_assistant import content

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def sitemap_entries(response):
    """Each <url> of a sitemap, as {tag without its namespace: text}."""
    root = ElementTree.fromstring(response.content)
    return [
        {child.tag.removeprefix(f"{{{SITEMAP_NS}}}"): child.text for child in url}
        for url in root.findall(f"{{{SITEMAP_NS}}}url")
    ]


class SitemapTests(TestCase):
    def test_the_sitemap_lists_the_public_pages_and_nothing_else(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml")
        locations = [entry["loc"] for entry in sitemap_entries(response)]
        expected = [f"https://testserver{path}" for path in public_pages.public_urls()]
        self.assertCountEqual(locations, expected)

    def test_each_entry_is_a_full_address_and_nothing_more(self):
        # Spec #583 acceptance 10: no lastmod, changefreq or priority.
        for entry in sitemap_entries(self.client.get("/sitemap.xml")):
            with self.subTest(entry=entry["loc"]):
                self.assertEqual(set(entry), {"loc"})
                self.assertTrue(entry["loc"].startswith("https://testserver/"))

    def test_every_address_in_it_opens_without_logging_in(self):
        # Spec #583 acceptance 12.
        for entry in sitemap_entries(self.client.get("/sitemap.xml")):
            path = entry["loc"].removeprefix("https://testserver")
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_a_question_taken_out_leaves_the_sitemap(self):
        # Spec #583 acceptance 7 (ADR 0033): a question taken out is no longer in FAQS.
        kept, taken_out = content.FAQS[:-1], content.FAQS[-1]
        public_pages.public_urls.cache_clear()
        self.addCleanup(public_pages.public_urls.cache_clear)
        with mock.patch.object(content, "FAQS", kept):
            locations = [entry["loc"] for entry in sitemap_entries(self.client.get("/sitemap.xml"))]
        self.assertNotIn(f"https://testserver/qa/{taken_out.code}", locations)
        self.assertIn(f"https://testserver/qa/{kept[0].code}", locations)

    def test_a_topic_listing_no_question_is_left_out(self):
        # Spec #583 acceptance 6: 網站怎麼用 has no question yet (2026-11-16).
        locations = [entry["loc"] for entry in sitemap_entries(self.client.get("/sitemap.xml"))]
        listing = {}
        for slug, _name in content.TOPICS:
            listing[slug] = bool(self.client.get(f"/qa/topic/{slug}").context["faqs"])
            with self.subTest(topic=slug):
                self.assertEqual(f"https://testserver/qa/topic/{slug}" in locations, listing[slug])
        # The topic that checks the empty side; change this line the day it gets a question.
        self.assertIn(False, listing.values())


class RobotsTxtTests(TestCase):
    def test_every_crawler_may_read_every_address_and_is_told_the_sitemap(self):
        # Spec #583 acceptance 11; ADR 0062: robots.txt keeps nothing out, noindex does.
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        lines = response.content.decode().splitlines()
        self.assertEqual(
            [line for line in lines if line],
            ["User-agent: *", "Allow: /", "Sitemap: https://testserver/sitemap.xml"],
        )
