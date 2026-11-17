import re
from datetime import date, datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.models import Category, NormGroup, Question, Questionnaire, Submission
from screening.tests import test_layout
from screening.tests.helpers import (
    consented_user,
    fake_definition,
    register,
    submission_with_answers,
)
from screening.views.answering import list_order

GUIDE = "選問卷</h1>"
ICON = re.compile(r'<span class="questionnaire-icon" aria-hidden="true" data-icon="([a-z]+)">')
# #463: the count and minutes in one line of muted words, where they were tags.
FACTS = re.compile(r"<span>(\d+ 題・約 \d+ 分鐘)</span>")


class QuestionnaireCardTests(TestCase):
    """Spec docs/specs/phase-09/phase9_ui_refresh_4b_questionnaire_cards.md, acceptance 1-5."""

    @classmethod
    def setUpTestData(cls):
        # Created in the wrong order on purpose: the page must not rely on the database's.
        cls.ioi_ha = cls._questionnaire("IOI-HA", "ioi-ha", 7)
        cls.hhie_s = cls._questionnaire("HHIE-S", "hhie-s", 10)
        cls.other = cls._questionnaire("假問卷", "fake-later", 3)

    @staticmethod
    def _questionnaire(name, code, count):
        questionnaire = Questionnaire.objects.create(questionnaire_name=name, code=code)
        Question.objects.bulk_create(
            Question(
                questionnaire=questionnaire,
                question_text=f"{name} 假題{i}",
                question_number=i,
                category=Category.SOCIAL,
            )
            for i in range(1, count + 1)
        )
        return questionnaire

    def setUp(self):
        self.client.force_login(consented_user(username="cards_a"))
        self.enterContext(register(fake_definition("fake-later"), fake_definition("fake-last")))

    def _main(self):
        content = self.client.get(reverse("questionnaire_list") + "?choose=self").content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _card(self, questionnaire):
        href = f'href="{reverse("screening", args=[questionnaire.pk])}"'
        return next(c for c in test_layout._cards(self._main()) if href in c)

    # 1
    def test_guide_above_the_cards(self):
        main = self._main()
        self.assertIn(GUIDE, main)
        self.assertLess(main.index(GUIDE), main.index('class="link-card'))

    # 2
    def test_each_card_has_its_hidden_icon(self):
        expected = {self.hhie_s: "ear", self.ioi_ha: "aid", self.other: "clipboard"}
        for questionnaire, icon in expected.items():
            with self.subTest(questionnaire=questionnaire.code):
                self.assertEqual(ICON.findall(self._card(questionnaire)), [icon])

    # 3
    def test_count_minutes_and_audience(self):
        hhie = self._card(self.hhie_s)
        self.assertEqual(FACTS.findall(hhie), ["10 題・約 3 分鐘"])
        self.assertIn("適合 65 歲以上的長輩。", test_layout._text(hhie))
        self.assertEqual(FACTS.findall(self._card(self.ioi_ha)), ["7 題・約 2 分鐘"])
        self.assertEqual(FACTS.findall(self._card(self.other)), ["3 題・約 4 分鐘"])

    # 4
    def test_card_is_one_link_naming_everything(self):
        card = self._card(self.hhie_s)
        self.assertEqual(card.count("<a"), 1)
        text = test_layout._text(card)
        # The 2026-11-14 walkthrough: under 聽力對生活的影響, named by its age.
        for part in ("65 歲以上（HHIE-S）", "適合 65 歲以上的長輩。", "10 題", "約 3 分鐘"):
            self.assertIn(part, text)

    # 5, as grouped since the 2026-11-14 walkthrough: life impact, 其他困擾 (one with no concern
    # among them), then hearing aids.
    def test_order_hhie_s_then_others_then_ioi_ha(self):
        hrefs = re.findall(r'class="link-card[^"]*" href="(/questionnaire/[^"]+)"', self._main())
        expected = [
            reverse("screening", args=[q.pk]) for q in (self.hhie_s, self.other, self.ioi_ha)
        ]
        self.assertEqual(hrefs, expected)

    # 5: the rule itself, fed a wrong order, since the database may happen to return the right one
    def test_list_order_rule(self):
        given = [self.other, self.ioi_ha, self.hhie_s]
        self.assertEqual(sorted(given, key=list_order), [self.hhie_s, self.ioi_ha, self.other])
        later = Questionnaire(pk=self.other.pk + 1, code="fake-last")
        self.assertEqual(sorted([later, self.other], key=list_order), [self.other, later])


TAIPEI = ZoneInfo("Asia/Taipei")
LAST = '<span class="inline-block max-w-full">上次 {}</span>'
LAST_FACTS = re.compile(r"<span>(\d+ 題・約 \d+ 分鐘(?:・<span[^>]*>[^<]*</span>)?)</span>")


class LastResultTests(TestCase):
    """#649 (spec #644 acceptance 28-37): a card says its questionnaire's last result after 上次."""

    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        cls.by_code = {q.code: q for q in Questionnaire.objects.defined()}

    def setUp(self):
        self.user = consented_user(username="last_result", birth_year=1956)
        self.client.force_login(self.user)

    def record(self, code, scores, day, **fields):
        submission = submission_with_answers(self.user, code, scores, **fields)
        moment = datetime(day.year, day.month, day.day, 10, 0, tzinfo=TAIPEI)
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def main(self):
        return self.client.get(reverse("questionnaire_list")).content.decode()

    def facts(self, code, main=None):
        # The card's one grey line, its 上次 part as it is in the page.
        href = f'href="{reverse("screening", args=[self.by_code[code].pk])}"'
        card = next(c for c in test_layout._cards(main or self.main()) if href in c)
        self.assertNotIn("level-badge", card)
        return re.search(
            r"<span>(\d+ 題・約 \d+ 分鐘(?:・<span[^>]*>[^<]*</span>)?)</span>", card
        ).group(1)

    # 28, 34: the level's name in the same plain words as the date, no badge.
    def test_hhie_s_says_its_level(self):
        self.record("hhie-s", [4, 4, 2, 2, 0, 0, 0, 0, 0, 0], date(2026, 9, 26))
        self.assertEqual(
            self.facts("hhie-s"), "10 題・約 3 分鐘・" + LAST.format("2026/09/26・輕度到中度影響")
        )

    # 29
    def test_hhia_s_and_thi_say_their_level(self):
        self.record("hhia-s", [4] * 8 + [0, 0], date(2026, 9, 1))
        self.record("thi", [4] * 5 + [0] * 20, date(2026, 8, 14))
        main = self.main()
        self.assertEqual(
            self.facts("hhia-s", main), "10 題・約 3 分鐘・" + LAST.format("2026/09/01・顯著影響")
        )
        self.assertEqual(
            self.facts("thi", main), "25 題・約 5 分鐘・" + LAST.format("2026/08/14・輕度障礙")
        )

    # 29
    def test_a_level_that_cannot_be_read_says_so(self):
        self.record("hhia-s", [5] * 10, date(2026, 9, 1))
        with self.assertLogs("screening.scoring", "ERROR"):
            facts = self.facts("hhia-s")
        self.assertEqual(facts, "10 題・約 3 分鐘・" + LAST.format("2026/09/01・無法判讀"))

    # 30: the line of its 我的紀錄 row.
    def test_ssq12_says_its_average_or_why_it_has_none(self):
        for scores, said in (
            ([7] * 10 + [8, 8], "整體平均：7.2／10"),
            ([7] * 11 + [None], "未計算：包含不適用題目"),
        ):
            with self.subTest(said=said):
                self.record("ssq12-tw", scores, date(2026, 7, 2))
                facts = self.facts("ssq12-tw")
                self.assertEqual(facts, "12 題・約 5 分鐘・" + LAST.format(f"2026/07/02・{said}"))
                records = self.client.get(reverse("my_hearing"))
                self.assertContains(records, said)

    # 31
    def test_sadl_says_its_overall_satisfaction(self):
        # Items 2, 4, 7 and 13 reversed: (9 x 6 + 2 x 5 + 4 x (8 - 4)) / 15 = 5.3.
        scores = [6, 4, 6, 4, 6, 6, 4, 6, 6, 6, 6, 6, 4, 5, 5]
        self.record("sadl", scores, date(2026, 10, 5), wearing_hearing_aid=True)
        self.assertEqual(
            self.facts("sadl"), "15 題・約 5 分鐘・" + LAST.format("2026/10/05・整體滿意度：5.3")
        )

    # 32
    def test_ioi_ha_says_only_its_date(self):
        self.record("ioi-ha", [3] * 7, date(2026, 10, 5), norm_group=NormGroup.UNGROUPED)
        self.assertEqual(self.facts("ioi-ha"), "7 題・約 2 分鐘・" + LAST.format("2026/10/05"))

    # 33: the latest, worn or not.
    def test_the_last_is_the_latest_however_it_was_worn(self):
        self.record("hhie-s", [4] * 8 + [0, 0], date(2026, 9, 20), wearing_hearing_aid=False)
        self.record("hhie-s", [0] * 10, date(2026, 9, 26), wearing_hearing_aid=True)
        self.record("hhie-s", [4] * 4 + [0] * 6, date(2026, 9, 10), wearing_hearing_aid=True)
        self.assertEqual(
            self.facts("hhie-s"), "10 題・約 3 分鐘・" + LAST.format("2026/09/26・無／極輕微影響")
        )

    # 35
    def test_the_recommendation_says_it_too(self):
        day = date.today() - timedelta(days=200)
        self.record("hhie-s", [4, 4, 2, 2, 0, 0, 0, 0, 0, 0], day, wearing_hearing_aid=False)
        recommended = re.search(
            r'<section aria-labelledby="catalogue-recommended"[^>]*>(.*?)</section>',
            self.main(),
            re.S,
        ).group(1)
        last = LAST.format(f"{day:%Y/%m/%d}・輕度到中度影響")
        self.assertIn(f'<p class="recommended-facts">10 題・約 3 分鐘・{last}</p>', recommended)

    # 36
    def test_a_card_never_answered_stays_as_it_was(self):
        self.record("thi", [0] * 25, date(2026, 8, 14))
        main = self.main()
        for code, facts in (("hhie-s", "10 題・約 3 分鐘"), ("ioi-ha", "7 題・約 2 分鐘")):
            with self.subTest(code=code):
                self.assertEqual(self.facts(code, main), facts)

    # 37: one record of each kind, then several of every questionnaire.
    def test_the_queries_do_not_grow_with_the_cards(self):
        records = (
            ("hhie-s", [0] * 10, {"wearing_hearing_aid": False}),
            ("hhia-s", [0] * 10, {"wearing_hearing_aid": False}),
            ("thi", [0] * 25, {}),
            ("ssq12-tw", [5] * 12, {"wearing_hearing_aid": False}),
            ("sadl", [4] * 15, {}),
            ("ioi-ha", [3] * 7, {"norm_group": NormGroup.UNGROUPED}),
        )
        counts = []
        for many in (False, True):
            self.user = consented_user(username=f"last_result_{many}", birth_year=1956)
            self.client.force_login(self.user)
            for days_ago in (1, 2, 3) if many else (1,):
                for code, scores, fields in records if many else records[:1]:
                    self.record(code, scores, date.today() - timedelta(days=days_ago), **fields)
            with CaptureQueriesContext(connection) as queries:
                page = self.client.get(reverse("questionnaire_list"))
            self.assertIsNone(page.context["recommendation"])
            self.assertEqual(page.content.decode().count("上次 "), 6 if many else 1)
            counts.append(len(queries))
        self.assertEqual(counts[0], counts[1])
