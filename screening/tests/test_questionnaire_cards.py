import re

from django.test import TestCase
from django.urls import reverse

from screening.models import Category, Question, Questionnaire
from screening.tests import test_layout
from screening.tests.helpers import consented_user, fake_definition, register
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
