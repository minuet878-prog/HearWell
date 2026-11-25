import re

from django.test import TestCase
from django.urls import reverse

from screening.models import Questionnaire, Submission
from screening.questionnaires import hhie_s
from screening.tests import test_guide, test_guide_summary
from screening.tests.helpers import consented_user

PTA_55 = test_guide_summary.PTA_55
SOLID = re.compile(r'class="btn btn-primary[ "]')
FOLD = '<details class="result-details">'


class MyGuideRedesignTests(TestCase):
    """#467 (the #466 mockup A): 我的選配指引 with its steps first and the audiogram's long
    paragraphs behind 看完整說明. #779: the steps are the 引導卡 now, in place of the 選配路線
    and its 您在這裡 card (test_guide_cards)."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="guide_redesign")
        self.client.force_login(self.user)

    make = test_guide_summary.GuideSummaryTests.make

    def page(self, query=""):
        return self.client.get(reverse("guide") + query).content.decode()

    def test_the_cards_come_first_and_the_jump_down_to_them_is_gone(self):
        """#780: then the 章節磚, and what the audiogram says in the fold under them."""
        self.make(PTA_55, PTA_55)
        page = self.page()
        cards = page.index('id="contents-title"')
        tiles = page.index('id="chapters-title"')
        numbers = test_guide.NUMBERS_FOLD.search(page).start()
        summary = page.index(">依您 2026/10/01 的聽力圖</h2>")
        self.assertEqual([cards, tiles, numbers, summary], sorted([cards, tiles, numbers, summary]))
        response = self.client.get(reverse("guide"))
        self.assertIn(
            ">依您 2026/10/01 的聽力圖</h2>", test_guide.inside_numbers_fold(self, response)
        )
        self.assertNotIn("看我的路線", page)

    def test_the_long_paragraphs_wait_behind_the_full_explanation(self):
        self.make(PTA_55, PTA_55)
        # #780: all of it in the 看聽力圖數值與計算公式 fold, 看完整說明 a fold in it.
        page = test_guide.inside_numbers_fold(self, self.client.get(reverse("guide")))
        fold = page.index(FOLD)
        # The judgement stays out; what to do about it and how it is worked out fold away.
        self.assertLess(page.index("達到身障鑑定門檻（45%）。實際以鑑定醫院為準。"), fold)
        for words in ("身障補助要先有身心障礙證明", "如果您已經有身障證明", "怎麼算的"):
            with self.subTest(words=words):
                self.assertGreater(page.index(words), fold)
        self.assertIn("看完整說明", page[fold:])

    def test_too_little_data_has_nothing_to_fold(self):
        audiogram = self.make(PTA_55, PTA_55)
        audiogram.points.filter(frequency=4000).delete()
        self.assertNotIn(FOLD, self.page())

    def test_a_questionnaire_without_an_audiogram_links_to_record_one(self):
        # The 記錄聽力圖 card's button, and a plain link in the 聽力圖 part (#779).
        Submission.objects.create(user=self.user, questionnaire=self.hhie_s)
        page = self.page()
        self.assertEqual(SOLID.findall(page), [])
        self.assertIn(
            f'<a class="btn btn-hero btn-lg guide-card-button" href="{reverse("audiogram_new")}">',
            page,
        )
        audiogram = page[page.index('id="audiogram-title"') :]
        self.assertIn(f'<a href="{reverse("audiogram_new")}">記錄聽力圖</a>', audiogram)

    def test_without_records_the_start_button_is_the_one_solid(self):
        page = self.page()
        self.assertEqual(SOLID.findall(page), ['class="btn btn-primary '])
        self.assertIn(">開始篩檢</a>", page)


class ChapterRedesignTests(TestCase):
    """#467 (the owner's pick H1 + H2): each chapter opens on three key cards, its parts are
    titled as questions with one sentence in sight and the rest in a fold, open in the page so
    that a jump (or no JavaScript) finds it."""

    CHAPTERS = (
        "before-you-go",
        "assessment",
        "form-9",
        "types-and-prices",
        "after-fitting",
        "form-25",
    )
    # Where other pages link into a chapter: each still lands on its part.
    ANCHORS = (
        ("form-9", "steps-title"),
        ("form-9", "issuer-title"),
        ("form-9", "reapply"),
        ("form-9", "without-certificate"),
        ("assessment", "apply-title"),
        ("assessment", "hospitals-title"),
        ("types-and-prices", "sound-amplifier-title"),
        ("after-fitting", "record-title"),
    )

    def page(self, slug):
        return self.client.get(reverse("guide_chapter", args=[slug])).content.decode()

    def test_each_chapter_opens_on_three_key_cards(self):
        for slug in self.CHAPTERS:
            with self.subTest(slug=slug):
                page = self.page(slug)
                cards = page[page.index('<ul class="key-cards"') :]
                cards = cards[: cards.index("</ul>")]
                self.assertEqual(cards.count('<li class="key-card">'), 3)
                self.assertLess(page.index('<ul class="key-cards"'), page.index("<h2"))

    def test_form_9_key_cards_say_the_three_things(self):
        text = test_guide.text_of(self.client.get(reverse("guide_chapter", args=["form-9"])))
        for words in (
            # Readability batch 2: the big line says the first half; the small one the rest.
            "先核定，再買 沒核定就先買的不補助。",
            "3 個月內有效 找聽力師或縣市輔具中心。九號表 3 個月內有效。",
        ):
            with self.subTest(words=words):
                self.assertIn(words, text)

    def test_the_parts_are_questions_with_their_ids_kept(self):
        page = self.page("form-9")
        for anchor, question in (
            ("who-title", "我可以申請嗎？"),
            ("steps-title", "要怎麼辦？"),
            ("issuer-title", "九號表去哪裡開？"),
            ("amount-title", "可以補助多少錢？"),
            ("reapply", "用了幾年可以換新的？"),
            ("without-certificate", "沒有身障證明怎麼辦？"),
        ):
            with self.subTest(anchor=anchor):
                self.assertRegex(page, rf'<h2 id="{anchor}" class="h4">{question}</h2>')
        self.assertNotIn("本頁段落", page)

    def test_every_linked_part_is_open_in_the_page(self):
        for slug, anchor in self.ANCHORS:
            with self.subTest(slug=slug, anchor=anchor):
                page = self.page(slug)
                part = page[page.index(f'id="{anchor}"') :]
                part = part[: part.index("</section>")]
                folds = re.findall(r"<details [^>]*>", part)
                for fold in folds:
                    if "data-guide-fold" in fold:
                        self.assertIn(" open", fold)
