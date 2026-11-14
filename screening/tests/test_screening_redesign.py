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

SOLID = re.compile(r'class="btn btn-primary\b')
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

    def recommended(self, main):
        block = re.search(
            r'<section aria-labelledby="catalogue-recommended"[^>]*>(.*?)</section>', main, re.S
        )
        return block and block.group(1)

    def test_a_card_says_its_count_minutes_and_last_date_in_one_grey_line(self):
        user = self.login()
        self.record(user, "thi", days_ago=0)
        cards = dict(CARD.findall(self.catalogue()))
        today = timezone.localdate().strftime("%Y/%m/%d")
        thi = cards[self.answer_url("thi")]
        last = f'<span class="inline-block max-w-full">上次 {today}</span>'
        self.assertIn(f"<span>25 題・約 5 分鐘・{last}</span>", thi)
        self.assertIn("<span>7 題・約 2 分鐘</span>", cards[self.answer_url("ioi-ha")])
        self.assertNotIn("card-tag", self.catalogue())

    # The 2026-11-14 walkthrough (mockup 8A): 幫我選 under the title, the questionnaires in
    # three groups after any recommendation.
    GROUPS = (
        ("聽力對生活的影響", ("hhie-s", "hhia-s")),
        ("其他困擾", ("ssq12-tw", "thi")),
        ("已經戴助聽器", ("ioi-ha", "sadl")),
    )
    HELP = (
        '<a class="btn btn-outline-primary btn-lg w-full" href="/questionnaire_list?wizard=1">'
        "不確定做哪一份？幫我選</a>"
    )

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
        self.assertIn('<h1 class="h3 mt-2">選問卷</h1>', main)
        self.assertEqual(main.count(self.HELP), 1)
        self.assertLess(main.index("選問卷</h1>"), main.index(self.HELP))
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

    def test_the_groups_come_after_the_recommendation(self):
        user = self.login()
        self.record(user, "hhie-s", wearing=False, days_ago=200)
        main = self.catalogue()
        self.assertLess(main.index(self.HELP), main.index("</section>"))
        self.assertLess(main.index("</section>"), main.index('class="catalogue-group'))

    def test_one_recommendation_is_a_pale_blue_block_with_the_only_solid_button(self):
        user = self.login()
        self.record(user, "hhie-s", wearing=False, days_ago=200)
        main = self.catalogue()
        self.assertIn(
            '<section aria-labelledby="catalogue-recommended" class="recommended-block', main
        )
        block = self.recommended(main)
        self.assertIn(
            '<h2 id="catalogue-recommended" class="recommended-label">推薦您做這一份</h2>', block
        )
        self.assertIn(
            '<h3 id="recommended-title" class="recommended-title">聽力對生活的影響'
            '<span class="recommended-code">HHIE-S</span></h3>',
            block,
        )
        self.assertIn(
            '<p class="recommended-facts">10 題・約 3 分鐘・<span class="inline-block max-w-full">',
            block,
        )
        self.assertIn(f"<strong>為什麼推薦：</strong>{RETEST_DUE_TEXT}</p>", block)
        self.assertEqual(len(SOLID.findall(main)), 1)
        self.assertIn(f'href="{self.answer_url("hhie-s")}">開始作答</a>', block)

    def test_two_recommendations_are_two_rows_and_no_solid_button(self):
        for age in (None, 65):
            with self.subTest(age=age):
                user = self.login(age=age)
                self.record(user, "thi")
                main = self.catalogue()
                block = self.recommended(main)
                self.assertEqual(
                    [href for href, _ in CARD.findall(block)],
                    [self.answer_url("hhie-s"), self.answer_url("hhia-s")],
                )
                self.assertEqual(block.count("為什麼推薦："), 1)
                self.assertLess(block.index("為什麼推薦："), block.index("link-card"))
                self.assertEqual(SOLID.findall(main), [])
                self.assertNotIn("開始作答", main)

    def test_a_new_users_choose_yourself_ends_with_help_me_choose_too(self):
        self.login()
        main = _main(self.client.get(reverse("questionnaire_list"), {"choose": "self"}))
        self.assertIn(self.HELP, main)
        self.assertNotIn("推薦您做這一份", main)
        self.assertEqual(len(self.groups(main)), 3)


class WizardTests(ScreeningPagesMixin, TestCase):
    """The recommendation wizard (#462 section 2)."""

    def test_the_result_is_a_pale_blue_block_with_the_only_solid_button(self):
        self.login(age=70)
        main = _main(self.client.get(reverse("questionnaire_list"), {"concern": "life_impact"}))
        self.assertIn(
            '<section aria-labelledby="recommended-title" class="recommended-block">', main
        )
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
        return content[start : content.index('id="answer-app"', start)]

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
