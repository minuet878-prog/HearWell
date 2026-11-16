"""Every page pasted into LINE shows a title, a description and the one preview image (spec #583,
ticket #590). LINE reads og:title, og:description and og:image only (search-basics-research.md)."""

import html
import re
import struct

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from screening import public_pages, questionnaires
from screening.models import Questionnaire, ReportShare
from screening.tests import test_search_titles
from screening.tests.helpers import consented_user


def hhie_s_code():
    return questionnaires.hhie_s.CODE


# The table's E1, as the owner confirmed it (#587).
SITE_DESCRIPTION = (
    "聽伴是聽力自我照護工具：花 3 分鐘回答問題，看聽力對生活的影響。"
    "內容由台灣執業聽力師設計與審定。"
)


def preview_of(response):
    """{og:title, og:description, og:image} of a page; a missing one is absent."""
    content = response.content.decode()
    return {
        name: html.unescape(value)
        for name, value in re.findall(r'<meta property="og:(\w+)" content="([^"]*)">', content)
    }


class PublicPagePreviewTests(TestCase):
    def test_each_public_page_shows_its_title_description_and_the_image(self):
        # Spec #583 acceptance 19.
        for url in public_pages.public_urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                title, description = test_search_titles.head_of(response)
                preview = preview_of(response)
                self.assertEqual(preview.get("title"), title)
                self.assertEqual(preview.get("description"), description)
                self.assertTrue(preview.get("image", "").startswith("https://testserver/static/"))


class OtherPagePreviewTests(TestCase):
    def test_pages_kept_out_of_search_show_their_title_and_the_site_description(self):
        # Spec #583 acceptance 20: e.g. the 傳給他 link of item 5 lands on the guest's wizard.
        hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s_code())
        for url in (
            reverse("questionnaire_list"),
            reverse("guest_result", args=[hhie_s.code]),
            reverse("login"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                title, _description = test_search_titles.head_of(response)
                self.assertEqual(
                    preview_of(response),
                    {
                        "title": title,
                        "description": SITE_DESCRIPTION,
                        "image": preview_of(self.client.get("/"))["image"],
                    },
                )

    def test_a_shared_report_link_names_no_one_and_no_score(self):
        # Spec #583 acceptance 21: what a family member sees when the link is pasted into LINE.
        user = consented_user(username="mei", first_name="美玉", birth_year=1950)
        share = ReportShare.objects.create(user=user)
        response = self.client.get(reverse("shared_cover", args=[share.token]))
        # Exactly these: no name, no score, no level can be in them.
        self.assertEqual(
            preview_of(response),
            {
                "title": "聽伴聽力報告",
                "description": SITE_DESCRIPTION,
                "image": preview_of(self.client.get("/"))["image"],
            },
        )
        self.assertNotIn("美玉", response.content.decode())


class PreviewImageTests(TestCase):
    def test_the_image_is_a_1200_by_630_png_served_as_a_static_file(self):
        # Spec #583 acceptances 22 and 23: the address is the static file's, full; the file is the
        # PNG exported at 1200x630 (#588's design C).
        address = preview_of(self.client.get("/"))["image"]
        path = address.removeprefix(f"https://testserver{settings.STATIC_URL}")
        self.assertNotEqual(path, address)
        found = finders.find(path)
        self.assertIsNotNone(found, address)
        with open(found, "rb") as image:
            head = image.read(24)
        self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", head[16:24]), (1200, 630))
