from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.questionnaires.definition import LEVEL
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


PUBLISHED = {
    # code: (card audience, minutes, icon, sentences from the answer page intro)
    "hhie-s": (
        "適合 65 歲以上的長輩。",
        3,
        "ear",
        ("適合 65 歲以上的長輩；若您持續使用原問卷追蹤", "本問卷的目的在幫助您了解自己的聽力"),
    ),
    "ioi-ha": (
        "適合已配戴助聽器的人。",
        2,
        "aid",
        ("目前沒有完整有效的未配戴 HHIA-S／HHIE-S 紀錄", "請依照最近兩週戴著現有助聽器的經驗"),
    ),
    "hhia-s": (
        "適合 18–64 歲成人；若您持續使用原問卷追蹤，也可以繼續填寫。",
        3,
        "clipboard",
        ("適合 18–64 歲成人", "題目中譯來源：林克寰《助聽器選配與驗證》，第 165 頁"),
    ),
    "ssq12-tw": (
        "了解您目前生活中的聆聽能力。",
        5,
        "clipboard",
        ("十二題都有分數才計算整體平均", "來源：婦聯聽覺健康基金會 SSQ12-TW"),
    ),
}


class RealDefinitionsTests(TestCase):
    """Issue #105: the four published questionnaires read the same after the move."""

    @classmethod
    def setUpTestData(cls):
        cls.questionnaires = {}
        # Added in the published order, so the two rank-2 questionnaires keep HHIA-S first.
        for code in ("hhie-s", "ioi-ha", "hhia-s", "ssq12-tw"):
            questionnaire = Questionnaire.objects.create(questionnaire_name=code.upper(), code=code)
            Question.objects.create(
                questionnaire=questionnaire,
                question_text=f"{code} 題目",
                question_number=1,
                category=Category.SOCIAL,
            )
            cls.questionnaires[code] = questionnaire

    def setUp(self):
        self.client.force_login(consented_user(username="definitions_c"))

    def test_catalog_cards(self):
        content = self.client.get(reverse("questionnaire_list")).content.decode()
        main = content[content.index("<main") : content.index("</main>")]
        cards = test_layout._cards(main)
        hrefs = [
            f'href="{reverse("screening", args=[self.questionnaires[code].pk])}"'
            # No birth year, so nothing is recommended ahead of the list order.
            for code in ("hhie-s", "ioi-ha", "hhia-s", "ssq12-tw")
        ]
        self.assertEqual(
            [next(i for i, c in enumerate(cards) if h in c) for h in hrefs], [0, 1, 2, 3]
        )
        for code, (audience, minutes, icon, _) in PUBLISHED.items():
            with self.subTest(code=code):
                href = f'href="{reverse("screening", args=[self.questionnaires[code].pk])}"'
                card = next(c for c in cards if href in c)
                self.assertIn(f'data-icon="{icon}"', card)
                self.assertIn(audience, test_layout._text(card))
                self.assertIn(f"約 {minutes} 分鐘", test_layout._text(card))

    def test_answer_page_intro(self):
        for code, (_, minutes, _, sentences) in PUBLISHED.items():
            with self.subTest(code=code):
                url = reverse("screening", args=[self.questionnaires[code].pk])
                content = self.client.get(url).content.decode()
                self.assertIn(f"共 1 題，大約 {minutes} 分鐘。", content)
                for sentence in sentences:
                    self.assertIn(sentence, content)


class ResultFromDefinitionTests(TestCase):
    """Issue #101: a graded questionnaire's result comes from its definition."""

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="definitions_d")
        cls.fake = Questionnaire.objects.create(questionnaire_name="假分級", code="fake-level")
        questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.fake,
                question_text=f"假題{i}",
                question_number=i,
                category=Category.SOCIAL,
            )
            for i in range(1, 4)
        )
        cls.submission = Submission.objects.create(
            user=cls.user, questionnaire=cls.fake, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=cls.submission, question=question, score=2) for question in questions
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.enterContext(
            register(
                fake_definition(
                    "fake-level",
                    result=LEVEL,
                    thresholds=((5, "假的低分級", "normal"), (12, "假的高分級", "severe")),
                    advice={"severe": "假的高分建議"},
                )
            )
        )

    def test_result_page_grades_with_its_thresholds_and_advice(self):
        response = self.client.get(reverse("result", args=[self.submission.pk]))
        self.assertContains(response, "總分 6 分（滿分 12）")
        self.assertContains(response, "假的高分級")
        self.assertContains(response, "假的高分建議")

    def test_api_reads_its_levels(self):
        detail = self.client.get(reverse("api:questionnaire", args=[self.fake.pk])).json()
        self.assertEqual(
            detail["levels"],
            [
                {"code": "normal", "text": "假的低分級", "max": 5},
                {"code": "severe", "text": "假的高分級", "max": 12},
            ],
        )
        record = self.client.get(reverse("api:submission", args=[self.submission.pk])).json()
        self.assertEqual(record["level"], {"code": "severe", "text": "假的高分級"})
        self.assertEqual(record["advice"], "假的高分建議")


class UndefinedResultTests(TestCase):
    """Issue #101 (deferred from #105): records of an undefined questionnaire are not shown."""

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="definitions_e")
        undefined = Questionnaire.objects.create(questionnaire_name="無定義", code="undefined")
        cls.submission = Submission.objects.create(user=cls.user, questionnaire=undefined)

    def setUp(self):
        self.client.force_login(self.user)

    def test_result_page_is_404(self):
        response = self.client.get(reverse("result", args=[self.submission.pk]))
        self.assertEqual(response.status_code, 404)

    def test_api_records_skip_it(self):
        self.assertEqual(self.client.get(reverse("api:submissions")).json()["results"], [])
        detail = reverse("api:submission", args=[self.submission.pk])
        self.assertEqual(self.client.get(detail).status_code, 404)
