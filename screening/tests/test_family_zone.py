"""Spec #426 (家人專區), ticket #427: the zone's home page and the ways to reach it."""

import re

from django.test import TestCase
from django.urls import reverse

from screening.models import Questionnaire, ReportShare, Submission
from screening.tests import test_pages
from screening.tests.helpers import consented_user

FAMILY_CARD = "我是家人：怎麼陪伴聽損的家人"
LEARN_CARD = "家人專區：溝通與陪伴"
# The footer's words stay as they were (#427).
FOOTER_LINK = "給家人看：怎麼跟聽損的家人溝通"
# As reviewed on 2026-10-17 (spec appendix A).
INTRO = (
    "家人有聽力困難時，日常對話常常要講好幾次，雙方都容易累、容易誤會。"
    "下面幾個小方法，可以讓溝通輕鬆一點。"
)
URGENT = (
    "出現下面任何一種情況，不要等下次回診，請盡快到耳鼻喉科就醫：",
    "突然聽不到或聽力變差（一耳或兩耳，幾小時到幾天內發生），"
    "可能伴隨耳鳴、耳悶或暈眩。這可能是突發性聽力損失，越早治療效果越好。",
    "耳朵痛、流膿或流血。",
    "嚴重暈眩、天旋地轉，或走路不穩。",
    "頭部受傷後聽力改變。",
    "如果同時出現臉歪嘴斜、單側手腳無力、說話不清楚，可能是中風，請立刻撥打 119。",
)
# Drafts for the owner's review, like the card above.
TALK_NOTE = "讓溝通輕鬆一點的小方法"
AID_NOTE = "剛開始不習慣、回診和保養時可以怎麼陪"
# (href, title) of each card in a part of a page, in page order.
CARD = re.compile(
    r'<a class="link-card[^"]*" href="([^"]*)">.*?<span class="link-card-title">([^<]*)</span>',
    re.S,
)
# (href, icon or nothing, title, the line under it or nothing) of each of the zone's entries.
ENTRY = re.compile(
    r'<a class="link-card[^"]*" href="([^"]*)">\s*'
    r'(?:<span class="action-card-icon" aria-hidden="true" data-icon="([^"]+)">.*?</span>\s*)?'
    r'<span class="link-card-body">\s*<span class="link-card-title">([^<]*)</span>\s*'
    r"(?:<span>([^<]*)</span>\s*)?</span>",
    re.S,
)


def _main(content):
    return content[content.index("<main") : content.index("</main>")]


class FamilyZoneHomeTests(TestCase):
    def setUp(self):
        self.url = reverse("family_guide")

    def _home(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        return _main(response.content.decode())

    def assert_family_card_under_the_guide_card(self):
        main = self._home()
        self.assertEqual(
            CARD.findall(main),
            [(reverse("guide"), "了解助聽器選配與補助"), (self.url, FAMILY_CARD)],
        )
        # The main buttons keep their place above the cards.
        self.assertLess(main.index("開始篩檢"), main.index("了解助聽器選配與補助"))
        self.assertLess(main.index(FAMILY_CARD), main.index("結果長這樣"))

    def test_visitor_sees_the_family_card_under_the_guide_card(self):
        self.assert_family_card_under_the_guide_card()
        main = self._home()
        self.assertLess(main.index("開始篩檢"), main.index("我已經有帳號，登入"))
        self.assertLess(main.index("我已經有帳號，登入"), main.index("了解助聽器選配與補助"))

    def test_new_user_without_records_sees_the_family_card(self):
        self.client.force_login(consented_user(username="zone_new"))
        self.assert_family_card_under_the_guide_card()

    def test_returning_user_home_has_no_family_card_and_the_same_tabs(self):
        user = consented_user(username="zone_returning")
        questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        Submission.objects.create(user=user, questionnaire=questionnaire)
        self.client.force_login(user)
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("您還可以", content)  # really the returning user's page
        self.assertNotIn(FAMILY_CARD, content)
        nav = test_pages.RedesignLayoutTests.NAV.search(content).group()
        self.assertEqual(
            re.findall(r"<span>([^<]+)</span>", nav),
            ["首頁", "篩檢", "紀錄", "了解"],
        )

    # The zone's home page: picked on the comparison page, option A.
    def _zone(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _entries(self, content):
        start = content.index('aria-label="本頁內容"')
        return content[start : content.index("</nav>", start)]

    def assert_zone_home(self):
        content = self._zone()
        self.assertEqual(re.findall(r"<h1[^>]*>([^<]*)</h1>", content), ["家人專區"])
        self.assertRegex(content, r"<title>\s*家人專區｜聽伴\s*</title>")  # noqa: RUF001
        self.assertEqual(
            ENTRY.findall(self._entries(content)),
            [
                ("#talk-title", "family", "怎麼跟他說話", TALK_NOTE),
                ("#aid-title", "ear", "陪伴配戴助聽器", AID_NOTE),
                ("#urgent-title", "", "什麼時候要馬上就醫", ""),
            ],
        )
        nav = test_pages.RedesignLayoutTests.NAV.search(content).group()
        self.assertEqual(
            re.findall(r'aria-current="page"[^>]*>.*?<span>([^<]+)</span>', nav, re.S),
            ["了解"],
        )

    def test_visitor_sees_the_zone_home_without_logging_in(self):
        self.assert_zone_home()

    def test_signed_in_user_sees_the_same_zone_home_without_their_data(self):
        self.client.force_login(
            consented_user(username="zone_private", email="zone_private@example.com")
        )
        self.assert_zone_home()
        main = _main(self._zone())
        self.assertNotIn("zone_private", main)

    def test_entries_only_for_what_is_live(self):
        entries = self._entries(self._zone())
        for later in ("長輩不肯去", "陪診", "代辦", "/family/"):
            with self.subTest(later=later):
                self.assertNotIn(later, entries)

    # Old links and the reviewed words (the talk and aid tips word by word: test_family_guide).
    def test_old_anchors_land_on_their_original_sections_with_the_reviewed_words(self):
        content = self._zone()
        self.assertIn(INTRO, content)
        for anchor, heading in (
            ("talk-title", "怎麼跟聽損的家人說話"),
            ("aid-title", "陪伴配戴助聽器"),
            ("urgent-title", "什麼時候要馬上就醫"),
        ):
            with self.subTest(anchor=anchor):
                self.assertEqual(content.count(f'id="{anchor}"'), 1)
                self.assertRegex(content, rf'<h2 id="{anchor}"[^>]*>(<svg.*?</svg>)?{heading}</h2>')
        start = content.index('id="urgent-title"')
        urgent = re.sub(r"<[^>]+>", "", content[start : content.index("</section>", start)])
        for words in URGENT:
            with self.subTest(words=words):
                self.assertIn(words, urgent)

    # Each way in, followed: the page answers, and a jump's section is on it.
    def test_entries_from_learn_footer_and_shared_report_reach_the_zone(self):
        user = consented_user(username="zone_sharer")
        share = ReportShare.objects.create(user=user)
        zone = self._zone()
        pages = {
            "了解": (reverse("learn"), LEARN_CARD),
            "頁尾": (reverse("privacy"), FOOTER_LINK),
            "分享報告": (reverse("shared_report", args=[share.token]), "怎麼跟聽損的家人說話"),
        }
        for name, (url, words) in pages.items():
            with self.subTest(page=name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                content = response.content.decode()
                self.assertIn(words, content)
                links = re.findall(rf'href="({self.url}(?:#[^"]*)?)"', content)
                self.assertTrue(links)
                for link in links:
                    path, _, anchor = link.partition("#")
                    self.assertEqual(self.client.get(path).status_code, 200)
                    if anchor:
                        self.assertIn(f'id="{anchor}"', zone)
