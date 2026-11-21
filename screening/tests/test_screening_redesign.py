"""#463: the screening tab and the answer page in the new look (the #462 mockup, ADR 0043)."""

import re
import uuid
from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Questionnaire, Submission
from screening.scoring import RETEST_DUE_TEXT
from screening.tests import test_layout
from screening.tests.helpers import consented_user

# The page's main button: solid, or white on the blue hero card (#749, ADR 0076).
SOLID = re.compile(r'class="btn btn-(?:primary|hero)(?=[ "])')
ARROW = "\u203a"  # the rows' arrow sign
CARD = re.compile(r'<a class="link-card questionnaire-card" href="([^"]+)">(.*?)</a>', re.S)


def _main(page):
    content = page.content.decode()
    return content[content.index("<main") : content.index("</main>")]


class ScreeningPagesMixin:
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        cls.by_code = {q.code: q for q in Questionnaire.objects.defined()}

    def login(self, age=70):
        # age None: no birth year.
        user = consented_user(
            username=f"redesign_{uuid.uuid4().hex[:8]}",
            birth_year=None if age is None else date.today().year - age,
        )
        self.client.force_login(user)
        return user

    def record(self, user, code, *, wearing=None, days_ago=1):
        questionnaire = self.by_code[code]
        submission = Submission.objects.create(
            user=user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=0)
            for question in questionnaire.questions.all()
        )
        Submission.objects.filter(pk=submission.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        return submission

    def answer_url(self, code):
        return reverse("screening", args=[self.by_code[code].pk])


class CatalogueTests(ScreeningPagesMixin, TestCase):
    """The returning user's catalogue (#462 section 1, option B)."""

    def catalogue(self):
        return _main(self.client.get(reverse("questionnaire_list")))

    def stack(self, main):
        # The stacked cards (#753), each card's inside.
        return re.findall(
            r'<article class="hero-card card-stack-card"[^>]*>(.*?)</article>', main, re.S
        )

    def test_a_card_says_its_count_minutes_and_last_date_in_one_grey_line(self):
        user = self.login()
        self.record(user, "thi", days_ago=0)
        cards = dict(CARD.findall(self.catalogue()))
        today = timezone.localdate().strftime("%Y/%m/%d")
        thi = cards[self.answer_url("thi")]
        # #649: then its level, the lowest with every answer 0.
        last = f'<span class="inline-block max-w-full">上次 {today}・無障礙或輕微障礙</span>'
        self.assertIn(f"<span>25 題・約 5 分鐘・{last}</span>", thi)
        self.assertIn("<span>7 題・約 2 分鐘</span>", cards[self.answer_url("ioi-ha")])
        self.assertNotIn("card-tag", self.catalogue())

    # The 2026-11-14 walkthrough (mockup 8A): the questionnaires in three groups after the
    # stacked cards; #753 (P4): 幫我選 in the bird's bubble under the title.
    GROUPS = (
        ("聽力對生活的影響", ("hhie-s", "hhia-s")),
        ("其他困擾", ("ssq12-tw", "thi")),
        ("已經戴助聽器", ("ioi-ha", "sadl")),
    )
    HELP = '<a class="bird-pick" href="/questionnaire_list?wizard=1">'

    def groups(self, main):
        return re.findall(
            r'<h2 class="catalogue-group h4">([^<]+)</h2>(.*?)(?=<h2 class="catalogue-group|$)',
            main,
            re.S,
        )

    def test_help_me_choose_is_a_button_under_the_title(self):
        user = self.login()
        self.record(user, "thi")
        main = self.catalogue()
        self.assertIn('<h1 class="bird-title">問卷</h1>', main)
        self.assertEqual(main.count(self.HELP), 1)
        self.assertLess(main.index("問卷</h1>"), main.index(self.HELP))
        self.assertLess(main.index(self.HELP), main.index('<section class="card-stack"'))
        self.assertLess(main.index(self.HELP), main.index('class="link-card questionnaire-card"'))
        self.assertEqual(len(test_layout.LINK_CARD.findall(main)), 6)
        self.assertNotIn("全部問卷", main)

    def test_the_questionnaires_in_three_groups(self):
        user = self.login()
        self.record(user, "thi")
        groups = self.groups(self.catalogue())
        self.assertEqual([title for title, _ in groups], [title for title, _ in self.GROUPS])
        for (title, part), (_, codes) in zip(groups, self.GROUPS, strict=True):
            with self.subTest(group=title):
                self.assertEqual(
                    [href for href, _ in CARD.findall(part)],
                    [self.answer_url(code) for code in codes],
                )

    def test_the_life_impact_pair_is_named_by_age(self):
        user = self.login()
        self.record(user, "thi")
        _, part = self.groups(self.catalogue())[0]
        titles = re.findall(r'<span class="link-card-title">([^<]+)</span>', part)
        self.assertEqual(titles, ["65 歲以上（HHIE-S）", "65 歲以下（HHIA-S）"])

    def test_the_groups_come_after_the_stacked_cards(self):
        user = self.login()
        self.record(user, "hhie-s", wearing=False, days_ago=200)
        main = self.catalogue()
        stack = main.index('<section class="card-stack"')
        self.assertLess(main.index(self.HELP), stack)
        self.assertLess(main.index("</section>", stack), main.index('class="catalogue-group'))

    def test_the_recommendation_is_the_first_stacked_card_each_with_one_main_button(self):
        # #753: the stacked cards are the page's blue thing (ADR 0076), one shown at a time.
        user = self.login()
        self.record(user, "hhie-s", wearing=False, days_ago=200)
        main = self.catalogue()
        cards = self.stack(main)
        block = cards[0]
        self.assertIn('<p class="hero-card-label">推薦您做這一份</p>', block)
        self.assertIn(
            '<h2 id="stack-hhie-s" class="recommended-title">聽力對生活的影響'
            '<span class="recommended-code">HHIE-S</span></h2>',
            block,
        )
        self.assertIn(
            '<p class="recommended-facts">10 題・約 3 分鐘・<span class="inline-block max-w-full">',
            block,
        )
        self.assertIn(f"<strong>為什麼推薦：</strong>{RETEST_DUE_TEXT}</p>", block)
        self.assertIn(f'href="{self.answer_url("hhie-s")}">開始作答</a>', block)
        for card in cards:
            self.assertEqual(len(SOLID.findall(card)), 1)
        self.assertEqual(len(SOLID.findall(main)), len(cards))

    def test_two_recommendations_are_the_first_two_cards_each_saying_whom_it_suits(self):
        for age in (None, 65):
            with self.subTest(age=age):
                user = self.login(age=age)
                self.record(user, "thi")
                cards = self.stack(self.catalogue())
                for card, code in zip(cards, ("hhie-s", "hhia-s"), strict=False):
                    self.assertIn("推薦您做這一份", card)
                    self.assertIn(f'href="{self.answer_url(code)}">開始作答</a>', card)
                    audience = self.by_code[code].definition.audience
                    self.assertIn(f'<p class="recommended-audience">{audience}</p>', card)
                self.assertNotIn("推薦您做這一份", cards[2])

    def test_a_new_users_choose_yourself_ends_with_help_me_choose_too(self):
        self.login()
        main = _main(self.client.get(reverse("questionnaire_list"), {"choose": "self"}))
        self.assertIn(self.HELP, main)
        self.assertNotIn("推薦您做這一份", main)
        self.assertEqual(len(self.groups(main)), 3)


class WizardTests(ScreeningPagesMixin, TestCase):
    """The recommendation wizard (#462 section 2)."""

    def test_the_result_is_the_hero_card_with_the_only_main_button(self):
        # #749 (ADR 0076): the blue hero card, where it was a pale blue block.
        self.login(age=70)
        main = _main(self.client.get(reverse("questionnaire_list"), {"concern": "life_impact"}))
        self.assertIn('<section class="hero-card" aria-labelledby="recommended-title">', main)
        self.assertIn(
            '<h2 id="recommended-title" class="recommended-title">聽力對生活的影響'
            '<span class="recommended-code">HHIE-S</span></h2>',
            main,
        )
        self.assertIn('<p class="recommended-facts">10 題・約 3 分鐘</p>', main)
        self.assertEqual(len(SOLID.findall(main)), 1)

    def test_other_questionnaires_fold_in_a_list_row(self):
        self.login(age=70)
        main = _main(self.client.get(reverse("questionnaire_list"), {"concern": "tinnitus"}))
        fold = re.search(r'<details class="questionnaire-fold[^"]*">(.*?)</details>', main, re.S)
        summary = re.search(r"<summary>(.*?)</summary>", fold.group(1), re.S).group(1)
        self.assertIn('data-icon="list"', summary)
        self.assertEqual(test_layout._text(summary), "看其他問卷")
        self.assertEqual(len(CARD.findall(fold.group(1))), 6)

    def test_the_answers_are_in_the_form_whose_fields_take_the_darker_edge(self):
        self.login(age=70)
        main = _main(self.client.get(reverse("questionnaire_list"), {"wizard": "1"}))
        self.assertIn('<form class="wizard-form" method="get"', main)


class AnswerPageTests(ScreeningPagesMixin, TestCase):
    """The answer page's Django side (#462 sections 3-5)."""

    NAV = '<nav aria-label="主要導覽" class="site-nav{}">'

    def test_the_phones_tab_bar_is_left_out_on_the_answer_page_alone(self):
        self.login()
        for code in ("hhie-s", "ioi-ha", "sadl"):
            with self.subTest(code=code):
                page = self.client.get(self.answer_url(code))
                self.assertContains(page, self.NAV.format(" site-nav-tucked"))
        for name in ("index", "questionnaire_list", "my_hearing"):
            with self.subTest(name=name):
                self.assertContains(self.client.get(reverse(name)), self.NAV.format(""))

    def intro(self, code):
        content = self.client.get(self.answer_url(code)).content.decode()
        start = content.index('<div id="answer-intro">')
        return content[start : content.index("</details>", start)]

    def test_the_intro_has_no_round_icons_and_holds_the_source(self):
        self.login()
        for code, source in (
            ("hhia-s", "題目中譯來源"),
            ("ioi-ha", "原量表：IOI-HA（Cox 等人）"),
            ("thi", "中文版：黃啟原修訂"),
        ):
            with self.subTest(code=code):
                intro = self.intro(code)
                self.assertIn('class="q-intro-row', intro)
                self.assertNotIn("data-icon", intro)
                self.assertIn(source, intro)

    def test_ioi_ha_keeps_its_norm_basis_apart_for_item_1(self):
        user = self.login()
        basis = self.record(user, "hhie-s", wearing=False, days_ago=3)
        basis.refresh_from_db()
        content = self.client.get(self.answer_url("ioi-ha")).content.decode()
        template = re.search(r'<template id="answer-norm">(.*?)</template>', content, re.S)
        day = timezone.localtime(basis.created_at).strftime("%Y/%m/%d")
        sentence = f"本次常模依據：HHIE-S，{day} 未配戴紀錄，0 分。"
        self.assertIn(sentence, template.group(1))
        self.assertIn("這是常模比較的分組，不代表聽損程度。", template.group(1))
        intro = self.intro("ioi-ha")
        norm = intro[intro.index("data-intro-norm") :]
        self.assertIn(sentence, norm[: norm.index("</section>")])
        self.assertNotIn(
            'id="answer-norm"', self.client.get(self.answer_url("hhie-s")).content.decode()
        )
