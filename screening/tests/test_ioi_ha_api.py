"""IOI-HA answered through the API and the React answer page (#245)."""

import json
import re
import uuid

from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Submission
from screening.questionnaires.ioi_ha import ITEM_CHOICES
from screening.tests import test_answering, test_ioi_ha

NORM_ERROR = "常模依據無法確認，請重新開啟問卷。"


class IoiHaApiTests(TestCase):
    # Borrowed without inheriting (and rerunning) its tests; unwrap so `cls` is this class.
    setUpTestData = classmethod(test_ioi_ha.IoiHaTests.setUpTestData.__func__)
    _hhie_s = test_ioi_ha.IoiHaTests._hhie_s
    _web_post = test_ioi_ha.IoiHaTests._post

    URL = "/api/submissions/"

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.ioi_ha.id])

    def _token(self, client=None):
        return (client or self.client).get(self.url).context["norm_token"]

    def _body(self, scores=(3,) * 7, **extra):
        return {
            "questionnaire": self.ioi_ha.pk,
            # Reversed: each item has its own labels, so the API must not depend on answer order.
            "answers": [
                {"question": q.pk, "score": s}
                for q, s in reversed(list(zip(self.ioi_questions, scores, strict=True)))
            ],
            **extra,
        }

    def _post(self, body, key=None):
        return self.client.post(
            self.URL,
            json.dumps(body),
            content_type="application/json",
            headers={"Idempotency-Key": key or str(uuid.uuid4())},
        )

    def _ioi_records(self):
        return Submission.objects.filter(questionnaire=self.ioi_ha)

    def _assert_refused(self, response):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"norm_token": [NORM_ERROR]})
        self.assertFalse(self._ioi_records().exists())
        self.assertFalse(Answer.objects.filter(question__questionnaire=self.ioi_ha).exists())

    # 讀題目
    def test_detail_gives_each_item_its_own_choices(self):
        response = self.client.get(f"/api/questionnaires/{self.ioi_ha.pk}/")
        self.assertEqual(response.status_code, 200)
        questions = response.json()["questions"]
        self.assertEqual([q["number"] for q in questions], list(range(1, 8)))
        for question in questions:
            labels = ITEM_CHOICES[question["number"]]
            with self.subTest(number=question["number"]):
                self.assertEqual(
                    question["choices"],
                    [{"value": v, "label": label} for v, label in enumerate(labels, start=1)],
                )

    # 送出：常模依據
    def test_page_token_fixes_the_basis_shown_when_the_page_opened(self):
        basis = self._hhie_s(24, False)
        token = self._token()
        self._hhie_s(40, False)
        response = self._post(self._body(norm_token=token))
        self.assertEqual(response.status_code, 201)
        record = self._ioi_records().get()
        self.assertEqual(record.user, self.user)
        self.assertEqual(record.norm_basis_id, basis.pk)
        self.assertEqual(record.norm_group, "mild_moderate")
        self.assertIsNone(record.wearing_hearing_aid)
        # Same record the web form saves from the same token.
        self._web_post(norm_token=token)
        web = self._ioi_records().latest("pk")
        for field in ("norm_basis_id", "norm_group", "wearing_hearing_aid"):
            with self.subTest(field=field):
                self.assertEqual(getattr(record, field), getattr(web, field))

    def test_without_a_token_uses_the_latest_basis_now(self):
        basis = self._hhie_s(24, False)
        self.assertEqual(self._post(self._body()).status_code, 201)
        record = self._ioi_records().get()
        self.assertEqual(record.norm_basis_id, basis.pk)
        self.assertEqual(record.norm_group, "mild_moderate")

    def test_without_any_basis_is_saved_ungrouped(self):
        for body in (self._body(), self._body(norm_token=self._token())):
            with self.subTest(sent_token="norm_token" in body):
                self.assertEqual(self._post(body).status_code, 201)
                record = self._ioi_records().latest("pk")
                self.assertIsNone(record.norm_basis_id)
                self.assertEqual(record.norm_group, "ungrouped")

    def test_another_users_token_is_refused(self):
        self._hhie_s(24, False)
        self._hhie_s(40, False, user=self.other)
        other_client = self.client_class()
        other_client.force_login(self.other)
        response = self._post(self._body(norm_token=self._token(other_client)))
        self._assert_refused(response)

    def test_tampered_token_is_refused(self):
        self._hhie_s(24, False)
        token = self._token()
        for tampered in (token[:-1] + ("A" if token[-1] != "A" else "B"), "not-a-token"):
            with self.subTest(token=tampered):
                self._assert_refused(self._post(self._body(norm_token=tampered)))

    def test_basis_gone_since_the_page_opened_is_refused(self):
        basis = self._hhie_s(24, False)
        token = self._token()
        basis.answers.all().delete()
        basis.delete()
        self._assert_refused(self._post(self._body(norm_token=token)))

    # 送出：作答
    def test_reversed_answers_land_on_their_own_items(self):
        scores = (1, 2, 3, 4, 5, 1, 2)
        response = self._post(self._body(scores))
        self.assertEqual(response.status_code, 201)
        saved = {
            a.question.question_number: a.score
            for a in self._ioi_records().get().answers.select_related("question")
        }
        self.assertEqual(saved, dict(enumerate(scores, start=1)))
        labels = {a["number"]: a["label"] for a in response.json()["answers"]}
        self.assertEqual(labels[1], "沒使用")
        self.assertEqual(labels[2], "只有一點幫助")
        self.assertEqual(labels[7], "沒有改變")

    def test_value_an_item_does_not_take_is_refused(self):
        for bad in (0, 6):
            with self.subTest(score=bad):
                response = self._post(self._body((bad,) + (3,) * 6))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(set(response.json()), {"answers"})
                self.assertFalse(self._ioi_records().exists())

    def test_wearing_is_never_asked_and_saved_unrecorded(self):
        for sent in (True, False, "missing"):
            with self.subTest(sent=sent):
                extra = {} if sent == "missing" else {"wearing_hearing_aid": sent}
                self.assertEqual(self._post(self._body(**extra)).status_code, 201)
                self.assertIsNone(self._ioi_records().latest("pk").wearing_hearing_aid)

    def test_body_has_no_total_level_or_advice(self):
        data = self._post(self._body()).json()
        self.assertEqual(data["questionnaire"], {"code": "ioi-ha", "name": "IOI-HA"})
        self.assertIsNone(data["wearing_hearing_aid"])
        self.assertIsNone(data["scores"])
        self.assertIsNone(data["level"])
        self.assertIsNone(data["advice"])
        self.assertEqual(len(data["answers"]), 7)

    def test_same_key_same_answers_returns_the_first(self):
        self._hhie_s(24, False)
        key = str(uuid.uuid4())
        first = self._post(self._body(norm_token=self._token()), key=key)
        # The basis was fixed by the first one; a token sent again (or not) changes nothing.
        second = self._post(self._body(), key=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(self._ioi_records().count(), 1)

    def test_other_questionnaires_ignore_a_norm_token(self):
        body = {
            "questionnaire": self.hhie_s.pk,
            "wearing_hearing_aid": False,
            "answers": [{"question": q.pk, "score": 0} for q in self.hhie_questions],
            "norm_token": "not-a-token",
        }
        self.assertEqual(self._post(body).status_code, 201)
        record = Submission.objects.get(questionnaire=self.hhie_s)
        self.assertEqual(record.norm_group, "")
        self.assertIsNone(record.norm_basis_id)

    def test_schema_documents_the_norm_token(self):
        # Only the submit body has it, so finding it at all means it is documented there.
        self.assertIn("norm_token:", self.client.get("/api/schema/").content.decode())


class IoiHaReactPageTests(TestCase):
    setUpTestData = classmethod(test_ioi_ha.IoiHaTests.setUpTestData.__func__)
    _hhie_s = test_ioi_ha.IoiHaTests._hhie_s

    ANSWER_JS = test_answering.ReactAnswerPageTests.ANSWER_JS

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.ioi_ha.id])

    def test_loads_react_with_its_norm_token_and_no_wearing_step(self):
        self._hhie_s(24, False)
        response = self.client.get(self.url)
        token = response.context["norm_token"]
        self.assertContains(response, self.ANSWER_JS)
        self.assertContains(response, 'id="answer-loading"')
        app = re.search(r'<div id="answer-app"[^>]*>', response.content.decode()).group()
        self.assertIn(f'data-questionnaire-id="{self.ioi_ha.id}"', app)
        self.assertIn(f'data-norm-token="{token}"', app)
        self.assertIn("data-skip-wearing", app)
        # Skipping the step is not always-aided: that would save the record as worn.
        self.assertNotIn("data-always-aided", app)
        # The basis is told in the intro React reads, before the first item.
        self.assertContains(response, "本次常模依據")

    def test_web_form_is_still_complete_without_js(self):
        content = self.client.get(self.url).content.decode()
        form = content[content.index('<form id="answer-form"') :]
        self.assertIn('name="norm_token"', form)
        self.assertIn("IOI題7", form)
        self.assertIn('type="submit"', form)
        self.assertNotIn('name="wearing_hearing_aid"', form)

    def test_other_questionnaires_get_no_norm_token_or_skip(self):
        app = re.search(
            r'<div id="answer-app"[^>]*>',
            self.client.get(reverse("screening", args=[self.hhie_s.id])).content.decode(),
        ).group()
        self.assertNotIn("data-norm-token", app)
        self.assertNotIn("data-skip-wearing", app)
