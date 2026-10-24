"""#335 (spec #326 E1, acceptance 20): 回到頂端 on the long pages."""

import re

from django.test import TestCase
from django.urls import reverse

from screening.tests.helpers import consented_user
from screening.views import GUIDE_CHAPTERS

SCRIPT = "/static/screening/back-to-top.js"
# Starts hidden: back-to-top.js shows it once the page has scrolled, so without JavaScript it
# never shows.
BUTTON = re.compile(
    r'<button id="back-to-top" type="button"[^>]* hidden>.*?回到頂端</button>', re.S
)


class BackToTopPageTests(TestCase):
    def assert_has_button(self, url):
        content = self.client.get(url).content.decode()
        main = content[content.index("<main") : content.index("</main>")]
        self.assertRegex(main, BUTTON)
        self.assertEqual(content.count(f'src="{SCRIPT}"'), 1)

    def test_on_the_guide_and_its_chapters_signed_out(self):
        for url in [reverse("guide")] + [
            reverse("guide_chapter", args=[chapter.slug]) for chapter in GUIDE_CHAPTERS
        ]:
            with self.subTest(url=url):
                self.assert_has_button(url)

    def test_on_the_guide_and_the_report_signed_in(self):
        self.client.force_login(consented_user(username="back_to_top"))
        for name in ("guide", "health_report"):
            with self.subTest(page=name):
                self.assert_has_button(reverse(name))

    def test_on_the_privacy_and_family_pages(self):
        for name in ("privacy", "family_guide"):
            with self.subTest(page=name):
                self.assert_has_button(reverse(name))

    def test_not_on_other_pages(self):
        self.client.force_login(consented_user(username="back_to_top"))
        for name in ("index", "questionnaire_list", "my_hearing"):
            with self.subTest(page=name):
                content = self.client.get(reverse(name)).content.decode()
                self.assertNotIn("回到頂端", content)
                self.assertNotIn(SCRIPT, content)
