import re
import uuid
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening import questionnaires
from screening.models import (
    Answer,
    Category,
    Question,
    Questionnaire,
    ReportComparison,
    Submission,
)
from screening.questionnaires.definition import AVERAGE, LEVEL
from screening.tests import test_layout
from screening.tests.helpers import consented_user, fake_definition, register


class NextStepsCoverageTests(TestCase):
    """Ticket #157: every life-impact questionnaire has next steps for every one of its levels."""

    def test_every_level_questionnaire_has_steps_for_every_threshold_level(self):
        for definition in questionnaires.DEFINITIONS.values():
            if definition.result != LEVEL:
                continue
            for _, _, level in definition.thresholds:
                with self.subTest(questionnaire=definition.code, level=level):
                    self.assertIn(level, definition.next_steps)
                    self.assertTrue(definition.next_steps[level])


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
        content = self.client.get(reverse("questionnaire_list") + "?choose=self").content.decode()
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
        response = self.client.get(reverse("questionnaire_list") + "?choose=self")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "無定義")
        self.assertNotContains(response, reverse("screening", args=[self.undefined.pk]))
        response = self.client.get(reverse("questionnaire_list"), {"hearing_aid": "no"})
        self.assertNotContains(response, "無定義")
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
        content = self.client.get(reverse("questionnaire_list") + "?choose=self").content.decode()
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
        aided = Submission.objects.create(user=cls.user, questionnaire=undefined)
        ReportComparison.objects.create(
            user=cls.user, questionnaire=undefined, unaided=cls.submission, aided=aided
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_result_page_is_404(self):
        response = self.client.get(reverse("result", args=[self.submission.pk]))
        self.assertEqual(response.status_code, 404)

    def test_history_report_and_export_skip_it(self):
        self.assertContains(self.client.get(reverse("my_hearing")), "您還沒有做過篩檢紀錄")
        report = self.client.get(reverse("health_report"))
        self.assertEqual(report.status_code, 200)
        self.assertNotContains(report, "無定義")
        exported = self.client.get(reverse("download_my_data")).json()
        self.assertEqual(exported["submissions"], [])
        self.assertEqual(exported["report_comparisons"], [])

    def test_api_records_skip_it(self):
        self.assertEqual(self.client.get(reverse("api:submissions")).json()["results"], [])
        detail = reverse("api:submission", args=[self.submission.pk])
        self.assertEqual(self.client.get(detail).status_code, 404)


def _fake_choices(number):
    return ((1, f"假的{number}低"), (3, f"假的{number}高"), ("na", "假的不適用"))


class AnsweringFromDefinitionTests(TestCase):
    """Issue #100: choices, labels, scale and N/A come from the definition."""

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="definitions_f")
        cls.fake = Questionnaire.objects.create(questionnaire_name="假作答", code="fake-answer")
        cls.questions = Question.objects.bulk_create(
            Question(questionnaire=cls.fake, question_text=f"假題{i}", question_number=i)
            for i in range(1, 3)
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.enterContext(
            register(
                fake_definition(
                    "fake-answer",
                    result=AVERAGE,
                    choices=_fake_choices,
                    scale=lambda number: (f"假的{number}最少", f"假的{number}最多"),
                )
            )
        )

    def test_answer_page_and_api_offer_its_choices_and_scale(self):
        page = self.client.get(reverse("screening", args=[self.fake.pk]))
        self.assertContains(page, "假的2高")
        self.assertContains(page, "0：假的2最少；10：假的2最多")
        detail = self.client.get(reverse("api:questionnaire", args=[self.fake.pk])).json()
        second = detail["questions"][1]
        self.assertEqual(
            second["choices"],
            [
                {"value": 1, "label": "假的2低"},
                {"value": 3, "label": "假的2高"},
                {"value": None, "label": "假的不適用"},
            ],
        )
        self.assertEqual(second["scale"], {"min_label": "假的2最少", "max_label": "假的2最多"})

    def test_web_form_saves_not_applicable_and_shows_its_labels(self):
        data = {
            "form-TOTAL_FORMS": 2,
            "form-INITIAL_FORMS": 0,
            "form-0-question_id": str(self.questions[0].pk),
            "form-0-score": "na",
            "form-1-question_id": str(self.questions[1].pk),
            "form-1-score": "3",
            "wearing_hearing_aid": "False",
        }
        response = self.client.post(reverse("screening", args=[self.fake.pk]), data)
        submission = Submission.objects.get()
        self.assertRedirects(response, reverse("result", args=[submission.pk]))
        self.assertEqual(
            [a.score for a in submission.answers.order_by("question__question_number")],
            [None, 3],
        )
        result = self.client.get(reverse("result", args=[submission.pk]))
        self.assertContains(result, "假的不適用")
        self.assertContains(result, "假的2高")

    def test_api_saves_not_applicable(self):
        body = {
            "questionnaire": self.fake.pk,
            "wearing_hearing_aid": True,
            "answers": [
                {"question": self.questions[0].pk, "score": None},
                {"question": self.questions[1].pk, "score": 1},
            ],
        }
        response = self.client.post(
            reverse("api:submissions"),
            body,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 201, response.content)
        labels = [answer["label"] for answer in response.json()["answers"]]
        self.assertEqual(labels, ["假的不適用", "假的2低"])


class UndefinedAnsweringApiTests(TestCase):
    """Issue #100 (deferred from #105): the API refuses a questionnaire without a definition."""

    def test_api_answer_is_rejected(self):
        self.client.force_login(consented_user(username="definitions_g"))
        undefined = Questionnaire.objects.create(questionnaire_name="無定義", code="undefined")
        question = Question.objects.create(
            questionnaire=undefined, question_text="無定義題", question_number=1
        )
        response = self.client.post(
            reverse("api:submissions"),
            {
                "questionnaire": undefined.pk,
                "wearing_hearing_aid": False,
                "answers": [{"question": question.pk, "score": 4}],
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("questionnaire", response.json())
        self.assertFalse(Submission.objects.exists())


class PublishedAnsweringTests(TestCase):
    """Issue #100: the published questionnaires answer as before the move."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        cls.ssq = Questionnaire.objects.get(code="ssq12-tw")
        cls.hhie = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhie_question = Question.objects.create(
            questionnaire=cls.hhie, question_text="HHIE 題", question_number=1
        )
        cls.user = consented_user(username="definitions_h")

    def setUp(self):
        self.client.force_login(self.user)

    def test_answer_pages_show_the_same_choices_and_scale_labels(self):
        ssq = self.client.get(reverse("screening", args=[self.ssq.pk]))
        for labels in (
            "0：完全不行；10：輕鬆做到",
            "0：混亂；10：分開",
            "0：不清晰；10：清晰",
            "0：非常專心；10：輕鬆做到",
        ):
            self.assertContains(ssq, labels)
        hhie = self.client.get(reverse("screening", args=[self.hhie.pk])).content.decode()
        self.assertEqual(
            re.findall(r'value="(\d)"[^>]*>\s*([^<\s]+)', hhie)[:3],
            [("4", "常常"), ("2", "有時"), ("0", "從未")],
        )
        self.assertNotIn("不適用", hhie)

    def test_not_applicable_is_refused_without_that_choice(self):
        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-0-question_id": str(self.hhie_question.pk),
            "form-0-score": "na",
            "wearing_hearing_aid": "False",
        }
        page = self.client.post(reverse("screening", args=[self.hhie.pk]), data)
        self.assertEqual(page.status_code, 200)
        response = self.client.post(
            reverse("api:submissions"),
            {
                "questionnaire": self.hhie.pk,
                "wearing_hearing_aid": False,
                "answers": [{"question": self.hhie_question.pk, "score": None}],
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Submission.objects.exists())


class DefinitionOnlyQuestionnaireTests(TestCase):
    """Issue #104: a questionnaire added only as a definition works from catalog to history."""

    def setUp(self):
        self.enterContext(
            register(
                fake_definition(
                    "fake-flow",
                    name="假全流程",
                    questions=((Category.SOCIAL, "假流程題一"), (Category.EMOTIONAL, "假流程題二")),
                    choices=lambda number: ((5, f"假的{number}有"), (1, f"假的{number}沒有")),
                    thresholds=((4, "假的輕分級", "normal"), (10, "假的重分級", "severe")),
                    advice={"severe": "假的重分級建議"},
                )
            )
        )
        call_command("seed_questionnaires", stdout=StringIO())
        self.client.force_login(consented_user(username="definitions_i"))

    def test_catalog_answer_result_and_history(self):
        questionnaire = Questionnaire.objects.get(code="fake-flow")
        answer_url = reverse("screening", args=[questionnaire.pk])
        catalog = self.client.get(reverse("questionnaire_list") + "?choose=self")
        self.assertContains(catalog, f'href="{answer_url}"')
        self.assertContains(catalog, "假主題（假全流程）")

        page = self.client.get(answer_url)
        self.assertContains(page, "假流程題二")
        self.assertContains(page, "假的2沒有")
        first, second = questionnaire.questions.order_by("question_number")
        response = self.client.post(
            answer_url,
            {
                "form-TOTAL_FORMS": 2,
                "form-INITIAL_FORMS": 0,
                "form-0-question_id": str(first.pk),
                "form-0-score": "5",
                "form-1-question_id": str(second.pk),
                "form-1-score": "1",
                "wearing_hearing_aid": "False",
            },
        )
        result_url = reverse("result", args=[Submission.objects.get().pk])
        self.assertRedirects(response, result_url)

        result = self.client.get(result_url)
        self.assertContains(result, "總分 6 分（滿分 10）")
        self.assertContains(result, "假的重分級")
        self.assertContains(result, "假的重分級建議")
        self.assertContains(result, "假的2沒有")

        history = self.client.get(reverse("my_hearing"), {"questionnaire": "fake-flow"})
        self.assertContains(history, f'href="{result_url}"')
        self.assertContains(history, "總分：6")
        self.assertContains(history, "假的重分級")
