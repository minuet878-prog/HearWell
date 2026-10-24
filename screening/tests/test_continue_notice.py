"""#326 E7 (#337): what the home and screening pages give the continue notice's script.

The drafts themselves live in the browser; frontend/src/continue-notice.test.js covers which of
them show. These tests cover the page's side: logged in only, and only questionnaires the user
can open.
"""

import json
import re

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.questionnaires import hhie_s, ssq12_tw
from screening.tests.helpers import consented_user

DATA = re.compile(r'<script id="continue-notice-data" type="application/json">(.*?)</script>')
SCRIPT = "screening/frontend/continue-notice.js"


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


class ContinueNoticeDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ssq12 = _questionnaire("SSQ12-TW", ssq12_tw.CODE, 2)
        cls.hhie_s = _questionnaire("HHIE-S", hhie_s.CODE, 3)
        # No definition (ADR 0005): the answer page answers 404, so the notice leaves it out.
        cls.retired = _questionnaire("舊問卷", "retired", 2)
        cls.user = consented_user(username="notice_a")

    def _data(self, url):
        match = DATA.search(self.client.get(url).content.decode())
        return match and json.loads(match.group(1))

    def _expected(self):
        def entry(questionnaire, topic, allow_not_applicable):
            return {
                "id": questionnaire.pk,
                "name": f"{topic}（{questionnaire.questionnaire_name}）",
                "url": reverse("screening", args=[questionnaire.pk]),
                "questionIds": list(
                    questionnaire.questions.order_by("question_number").values_list("id", flat=True)
                ),
                "allowNotApplicable": allow_not_applicable,
            }

        # The catalog's order: HHIE-S before SSQ12-TW.
        return {
            "userId": self.user.pk,
            "questionnaires": [
                entry(self.hhie_s, "聽力對生活的影響", False),
                entry(self.ssq12, "日常聆聽能力", True),
            ],
        }

    def test_new_users_home_lists_the_questionnaires_they_can_open(self):
        self.client.force_login(self.user)
        self.assertEqual(self._data(reverse("index")), self._expected())

    def test_returning_users_home_lists_them_too(self):
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.hhie_s, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=4)
            for question in self.hhie_s.questions.all()
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"))
        self.assertContains(response, "welcome-band")
        self.assertEqual(self._data(reverse("index")), self._expected())

    def test_screening_pages_list_them(self):
        self.client.force_login(self.user)
        for url in (
            reverse("questionnaire_list"),
            reverse("questionnaire_list") + "?choose=self",
        ):
            with self.subTest(url=url):
                self.assertEqual(self._data(url), self._expected())

    def test_screening_pages_read_the_questionnaires_once(self):
        # The page has already read the questionnaires; the notice uses those (#326 review).
        self.client.force_login(self.user)
        wizard = reverse("questionnaire_list")
        for url in (
            wizard,
            wizard + "?age_group=older",
            wizard + "?age_group=older&hearing_aid=no",
            wizard + "?choose=self",
        ):
            with self.subTest(url=url), CaptureQueriesContext(connection) as queries:
                self.assertEqual(self._data(url), self._expected())
            reads = [q["sql"] for q in queries if 'FROM "screening_questionnaire"' in q["sql"]]
            self.assertEqual(len(reads), 1, reads)

    def test_the_page_loads_the_script_with_its_list(self):
        self.client.force_login(self.user)
        for url in (reverse("index"), reverse("questionnaire_list")):
            with self.subTest(url=url):
                content = self.client.get(url).content.decode()
                main = content[content.index("<main") : content.index("</main>")]
                self.assertIn('<div id="continue-notice"></div>', main)
                self.assertIn(SCRIPT, content)
                # The list is not page text: the head keeps its names and links out of <main>.
                self.assertNotIn("continue-notice-data", main)

    def test_nothing_without_logging_in(self):
        response = self.client.get(reverse("index"))
        self.assertIsNone(DATA.search(response.content.decode()))
        self.assertNotContains(response, 'id="continue-notice"')
        self.assertNotContains(response, SCRIPT)
