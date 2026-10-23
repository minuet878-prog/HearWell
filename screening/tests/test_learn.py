import re

from django.test import TestCase
from django.urls import reverse

from screening.tests import test_pages
from screening.tests.helpers import consented_user

# My guide's six chapters (spec #218), by slug.
GUIDE_CHAPTERS = (
    "before-you-go",
    "assessment",
    "form-9",
    "types-and-prices",
    "after-fitting",
    "form-25",
)

GROUP = re.compile(
    r'<div class="more-group">\s*<h2 class="more-group-title">([^<]*)</h2>(.*?)</div>', re.S
)
CARD = re.compile(
    r'<li><a class="link-card action-card" href="([^"]*)">\s*'
    r'<span class="action-card-icon" aria-hidden="true" data-icon="([^"]+)"><svg[^>]*>.+?</svg>'
    r"</span>\s*<span class=\"link-card-body\">\s*"
    r'<span class="link-card-title">([^<]*)</span>',
    re.S,
)


class LearnPageTests(TestCase):
    """#269 (spec #268 了解入口頁): the public entry to guides and family help, in groups."""

    def groups(self):
        response = self.client.get(reverse("learn"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertRegex(content, r"<h1[^>]*>了解</h1>")
        return [(title, CARD.findall(cards)) for title, cards in GROUP.findall(content)]

    def assert_groups(self):
        self.assertEqual(
            self.groups(),
            [
                ("助聽器", [(reverse("guide"), "guide", "了解助聽器選配與補助")]),
                (
                    "溝通與照顧",
                    [(reverse("family_guide"), "family", "給家人看：怎麼跟聽損的家人溝通")],
                ),
            ],
        )

    def test_groups_and_cards_without_logging_in(self):
        self.assert_groups()

    def test_groups_and_cards_when_logged_in(self):
        self.client.force_login(consented_user(username="learn_reader"))
        self.assert_groups()

    def test_learn_is_the_only_current_tab_on_its_pages(self):
        layout = test_pages.RedesignLayoutTests
        pages = (
            reverse("learn"),
            reverse("guide"),
            *(reverse("guide_chapter", args=[slug]) for slug in GUIDE_CHAPTERS),
            reverse("family_guide"),
        )
        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                nav = layout.NAV.search(response.content.decode()).group()
                self.assertEqual(
                    re.findall(r'aria-current="page"[^>]*>.*?<span>([^<]+)</span>', nav, re.S),
                    ["了解"],
                )
