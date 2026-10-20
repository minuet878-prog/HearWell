from django.test import TestCase
from django.urls import reverse

from screening.models import Category, Question, Questionnaire
from screening.tests import test_layout
from screening.tests.helpers import consented_user, fake_definition, register


class CatalogFromDefinitionTests(TestCase):
    """Issue #105: the catalog reads each questionnaire's definition."""

    @classmethod
    def setUpTestData(cls):
        cls.fake = Questionnaire.objects.create(questionnaire_name="假問卷", code="fake")
        Question.objects.bulk_create(
            Question(
                questionnaire=cls.fake,
                question_text=f"假題{i}",
                question_number=i,
                category=Category.SOCIAL,
            )
            for i in range(1, 4)
        )

    def setUp(self):
        self.client.force_login(consented_user(username="definitions_a"))

    def _card(self):
        content = self.client.get(reverse("questionnaire_list")).content.decode()
        main = content[content.index("<main") : content.index("</main>")]
        href = f'href="{reverse("screening", args=[self.fake.pk])}"'
        return next((c for c in test_layout._cards(main) if href in c), None)

    def test_registered_questionnaire_card_uses_its_definition(self):
        with register(fake_definition("fake", icon="aid")):
            card = self._card()
        self.assertIn('data-icon="aid"', card)
        text = test_layout._text(card)
        for part in ("假主題（假問卷）", "適合測試的人。", "3 題", "約 4 分鐘"):
            self.assertIn(part, text)


class UndefinedQuestionnaireTests(TestCase):
    """Issue #105: a questionnaire without a definition is offered to no one."""

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="definitions_b", birth_year=1950)
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.undefined = Questionnaire.objects.create(questionnaire_name="無定義", code="undefined")
        cls.question = Question.objects.create(
            questionnaire=cls.undefined,
            question_text="無定義的題目",
            question_number=1,
            category=Category.SOCIAL,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_catalog_and_recommendation_skip_it(self):
        response = self.client.get(reverse("questionnaire_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "無定義")
        self.assertNotContains(response, reverse("screening", args=[self.undefined.pk]))
        self.assertEqual(response.context["recommended"], self.hhie_s)

    def test_answer_page_is_404(self):
        url = reverse("screening", args=[self.undefined.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-0-score": 4,
            "form-0-question_id": str(self.question.pk),
            "wearing_hearing_aid": "False",
        }
        self.assertEqual(self.client.post(url, data).status_code, 404)

    def test_api_does_not_list_it(self):
        response = self.client.get(reverse("api:questionnaires"))
        self.assertEqual([q["code"] for q in response.json()], ["hhie-s"])
        detail = reverse("api:questionnaire", args=[self.undefined.pk])
        self.assertEqual(self.client.get(detail).status_code, 404)
