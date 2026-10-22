import re

from django.test import TestCase
from django.urls import reverse

from screening.models import Category, Question, Questionnaire
from screening.tests import test_layout
from screening.tests.helpers import consented_user, fake_definition, register
from screening.views import list_order

GUIDE = "自行選擇問卷"
ICON = re.compile(r'<span class="questionnaire-icon" aria-hidden="true" data-icon="([a-z]+)">')
TAGS = re.compile(r'<span class="card-tag">([^<]*)</span>')


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
    def test_tags_and_audience(self):
        hhie = self._card(self.hhie_s)
        self.assertEqual(TAGS.findall(hhie), ["10 題", "約 3 分鐘"])
        self.assertIn("適合 65 歲以上的長輩。", test_layout._text(hhie))
        self.assertEqual(TAGS.findall(self._card(self.ioi_ha)), ["7 題", "約 2 分鐘"])
        self.assertEqual(TAGS.findall(self._card(self.other)), ["3 題", "約 4 分鐘"])

    # 4 (review B): a screen reader pauses between the tags; the comma is not shown
    def test_tags_read_apart(self):
        card = self._card(self.hhie_s)
        self.assertIn(
            '<span class="card-tag">10 題</span><span class="visually-hidden">，</span>'
            '<span class="card-tag">約 3 分鐘</span>',
            card,
        )

    # 4
    def test_card_is_one_link_naming_everything(self):
        card = self._card(self.hhie_s)
        self.assertEqual(card.count("<a"), 1)
        text = test_layout._text(card)
        for part in ("聽力對生活的影響（HHIE-S）", "適合 65 歲以上的長輩。", "10 題", "約 3 分鐘"):
            self.assertIn(part, text)

    # 5
    def test_order_hhie_s_then_ioi_ha_then_others(self):
        hrefs = re.findall(r'class="link-card[^"]*" href="([^"]+)"', self._main())
        expected = [
            reverse("screening", args=[q.pk]) for q in (self.hhie_s, self.ioi_ha, self.other)
        ]
        self.assertEqual(hrefs, expected)

    # 5: the rule itself, fed a wrong order, since the database may happen to return the right one
    def test_list_order_rule(self):
        given = [self.other, self.ioi_ha, self.hhie_s]
        self.assertEqual(sorted(given, key=list_order), [self.hhie_s, self.ioi_ha, self.other])
        later = Questionnaire(pk=self.other.pk + 1, code="fake-last")
        self.assertEqual(sorted([later, self.other], key=list_order), [self.other, later])
