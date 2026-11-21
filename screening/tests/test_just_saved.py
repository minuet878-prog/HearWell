"""Spec #741's 實作中本人補充 (2026-11-21): the result page's green line
「做完了，已存到我的紀錄。」 and the bird's 「做完了，辛苦了。」 only right after the answers
were sent; a result opened again later (上次結果, 我的紀錄, a reload) has no green line and the
bird says 「這是您這一次的結果。」"""

import json
import uuid
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import Questionnaire
from screening.questionnaires import hhie_s
from screening.tests.helpers import consented_user, submission_with_answers

STRIP = '<p class="result-saved" role="status">'
JUST_SENT = "做完了，辛苦了。"
LATER = "這是您這一次的結果。"


class JustSavedTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        cls.questionnaire = Questionnaire.objects.get(code=hhie_s.CODE)
        cls.questions = list(cls.questionnaire.questions.order_by("question_number"))

    def setUp(self):
        self.user = consented_user(username="just_saved_user")
        self.client.force_login(self.user)

    def assertJustSent(self, response):
        page = response.content.decode()
        self.assertIn(STRIP, page)
        self.assertIn(JUST_SENT, page)
        self.assertNotIn(LATER, page)

    def assertSeenLater(self, response):
        page = response.content.decode()
        self.assertNotIn(STRIP, page)
        self.assertIn(LATER, page)
        self.assertNotIn(JUST_SENT, page)

    def send_the_form(self):
        data = {
            "form-TOTAL_FORMS": len(self.questions),
            "form-INITIAL_FORMS": 0,
            "wearing_hearing_aid": "False",
            "idempotency_key": str(uuid.uuid4()),
        }
        for number, question in enumerate(self.questions):
            data[f"form-{number}-question_id"] = str(question.pk)
            data[f"form-{number}-score"] = "2"
        return self.client.post(reverse("screening", args=[self.questionnaire.pk]), data)

    def send_to_the_api(self, **extra):
        body = {
            "questionnaire": self.questionnaire.pk,
            "wearing_hearing_aid": False,
            "answers": [{"question": q.pk, "score": 2} for q in self.questions],
            **extra,
        }
        response = self.client.post(
            "/api/submissions/",
            json.dumps(body),
            content_type="application/json",
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 201)
        return reverse("result", args=[response.json()["id"]])

    def test_the_web_form_lands_on_the_result_just_sent(self):
        response = self.send_the_form()
        self.assertJustSent(self.client.get(response["Location"]))

    def test_the_answer_page_lands_on_the_result_just_sent(self):
        # AnswerApp sends to the API, then opens /submission/<id>.
        self.assertJustSent(self.client.get(self.send_to_the_api()))

    def test_opened_again_it_is_seen_later(self):
        for path in (self.send_to_the_api(), self.send_the_form()["Location"]):
            with self.subTest(path=path):
                self.client.get(path)
                self.assertSeenLater(self.client.get(path))

    def test_a_record_opened_from_my_records_is_seen_later(self):
        record = submission_with_answers(
            self.user, hhie_s.CODE, [2] * 10, wearing_hearing_aid=False
        )
        self.assertSeenLater(self.client.get(reverse("result", args=[record.pk])))

    def test_only_the_result_just_sent_says_so(self):
        older = submission_with_answers(self.user, hhie_s.CODE, [0] * 10, wearing_hearing_aid=False)
        self.send_to_the_api()
        self.assertSeenLater(self.client.get(reverse("result", args=[older.pk])))

    def test_a_guest_result_saved_on_the_save_page_is_seen_later(self):
        # guest_save.html says it is saved; the record opened afterwards is not just sent.
        self.assertSeenLater(self.client.get(self.send_to_the_api(from_guest=True)))
