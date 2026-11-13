import re

from django.test import TestCase
from django.urls import reverse

from screening.models import AidAndSubsidy, GuideChapterView, Questionnaire, Submission
from screening.questionnaires import hhie_s
from screening.tests import test_guide, test_guide_summary
from screening.tests.helpers import consented_user

PTA_55 = test_guide_summary.PTA_55
STOP = (
    r'<li class="route-stop[^"]*" data-stop="([^"]+)"[^>]*>(.*?)</li>'
    # A stop's own end, not one of the 您在這裡 card's to-dos (spec #478).
    r'(?=\s*(?:<li class="route-stop|</ol>))'
)
SOLID = re.compile(r'class="btn btn-primary[ "]')
FOLD = '<details class="result-details">'


class MyGuideRedesignTests(TestCase):
    """#467 (the #466 mockup A): 我的選配指引 with the 選配路線 first, the 您在這裡 card holding
    the page's one solid button, and the audiogram's long paragraphs behind 看完整說明."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="guide_redesign")
        self.client.force_login(self.user)

    make = test_guide_summary.GuideSummaryTests.make

    def page(self, query=""):
        return self.client.get(reverse("guide") + query).content.decode()

    def stops(self, page=None):
        return dict(re.findall(STOP, page or self.page(), re.S))

    def test_the_route_comes_first_and_the_jump_down_to_it_is_gone(self):
        self.make(PTA_55, PTA_55)
        page = self.page()
        route = page.index('id="contents-title"')
        summary = page.index(">依您 2026/10/01 的聽力圖</h2>")
        self.assertLess(route, summary)
        self.assertNotIn("看我的路線", page)

    def test_the_long_paragraphs_wait_behind_the_full_explanation(self):
        self.make(PTA_55, PTA_55)
        page = self.page()
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

    def test_the_here_card_has_the_one_solid_button_above_its_question(self):
        self.make(PTA_55, PTA_55)
        for chapter in ("before-you-go",):
            GuideChapterView.objects.create(user=self.user, chapter=chapter)
        AidAndSubsidy.objects.create(user=self.user, certificate="yes")
        page = self.page()
        here = self.stops(page)["form-9"]
        self.assertIn(
            '<p class="route-here-label"><span class="route-mark">您在這裡</span></p>', here
        )
        button = here.index(">看九號表的流程</a>")
        self.assertLess(button, here.index("九號表完成了嗎？"))
        self.assertRegex(here[: button + 1], r'class="btn btn-primary btn-lg w-full[^"]*"[^>]*>$')
        self.assertEqual(len(SOLID.findall(page)), 1)

    def test_changing_an_answer_marks_it_with_a_frame_and_a_tick(self):
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        AidAndSubsidy.objects.create(user=self.user, certificate="yes")
        page = self.page("?edit=assessment")
        assessment = self.stops(page)["assessment"]
        current = re.search(r'<button [^>]*value="yes"[^>]*>(.*?)</button>', assessment, re.S)
        self.assertIn('class="btn btn-lg btn-outline-primary is-current"', current.group(0))
        self.assertIn('aria-pressed="true"', current.group(0))
        self.assertIn('<svg class="stop-answer-tick"', current.group(1))
        self.assertEqual(len(SOLID.findall(page)), 1)

    def test_other_stops_open_in_place_to_say_what_they_are(self):
        self.make(PTA_55, PTA_55)
        stops = self.stops()
        here = stops.pop("before-you-go")
        self.assertNotIn("<details", here)
        for slug, stop in stops.items():
            with self.subTest(slug=slug):
                self.assertIn('<details class="route-about">', stop)
                summary = stop[stop.index("<summary") : stop.index("</summary>")]
                self.assertIn('<span class="route-title">', summary)
                self.assertNotIn("<a ", summary)
        types = stops["types-and-prices"]
        body = types[types.index("</summary>") : types.index("</details>")]
        self.assertIn("看助聽器有哪些外型、補助多少，和去哪裡買。", body)
        self.assertIn(f'href="{reverse("guide_chapter", args=["types-and-prices"])}"', body)

    def test_the_way_walked_and_the_done_ticks(self):
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        page = self.page()
        stops = re.findall(r'<li class="route-stop([^"]*)" data-stop="([^"]+)"', page)
        walked = [slug for classes, slug in stops if "is-walked" in classes]
        self.assertEqual(walked, ["audiogram", "before-you-go"])
        self.assertIn('style="--route-here: 2"', page)
        done = self.stops(page)["before-you-go"]
        self.assertRegex(
            done,
            r'<span class="route-number"><svg class="route-check" aria-hidden="true" '
            r'focusable="false"[^>]*>.*?</svg><span class="visually-hidden">2</span></span>',
        )

    def test_a_questionnaire_without_an_audiogram_links_once_to_record_one(self):
        Submission.objects.create(user=self.user, questionnaire=self.hhie_s)
        page = self.page()
        self.assertEqual(len(SOLID.findall(page)), 1)
        here = self.stops(page)["audiogram"]
        self.assertRegex(here, r'class="btn btn-primary btn-lg w-full[^"]*"[^>]*>記錄醫院的聽力圖<')
        audiogram = page[page.index('id="audiogram-title"') :]
        self.assertIn(f'<a href="{reverse("audiogram_new")}">記錄醫院的聽力圖</a>', audiogram)

    def test_without_records_the_start_button_is_the_one_solid(self):
        page = self.page()
        self.assertEqual(SOLID.findall(page), ['class="btn btn-primary '])
        self.assertIn(">開始篩檢</a>", page)
        here = self.stops(page)["audiogram"]
        self.assertNotIn("btn-primary", here)


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
            "先核定，再買 重要：一定要先拿到核定通知再買，沒核定就先買的不補助。",
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
