"""SSQ12-TW public answering flow (#79)."""

import uuid
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import Questionnaire
from screening.tests.helpers import consented_user


class Ssq12Tests(TestCase):
    def start(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.questionnaire = Questionnaire.objects.get(code="ssq12-tw")
        self.questions = list(self.questionnaire.questions.all())
        self.user = consented_user(username="ssq_user", password="Test-pass-12345")
        self.client.force_login(self.user)

    def post(self, scores, key=None):
        return self.client.post(
            "/api/submissions/",
            {
                "questionnaire": self.questionnaire.pk,
                "wearing_hearing_aid": False,
                "answers": [
                    {"question": q.pk, "score": score}
                    for q, score in zip(self.questions, scores, strict=True)
                ],
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key or uuid.uuid4()),
        )

    def test_twelve_numeric_answers_have_only_a_rounded_average(self):
        self.start()
        self.assertEqual(len(self.questions), 12)
        for scores in ([6] * 12, [6] * 11 + [9], [6] * 11 + [10], [0] * 12, [10] * 12):
            expected = {72: "6.0", 75: "6.3", 76: "6.3", 0: "0.0", 120: "10.0"}[sum(scores)]
            with self.subTest(expected=expected, total=sum(scores)):
                response = self.post(scores)
                self.assertEqual(response.status_code, 201, response.content)
                data = response.json()
                self.assertEqual(data["average_score"], expected)
                self.assertIsNone(data["scores"])
                self.assertIsNone(data["level"])
                self.assertIsNone(data["average_unavailable_reason"])
                page = self.client.get(reverse("result", args=[data["id"]]))
                self.assertContains(page, f"整體平均：{expected}")
                self.assertNotContains(page, "情緒分數")
                self.assertNotContains(page, "總分")
                history = self.client.get(reverse("my_hearing"), {"questionnaire": "ssq12-tw"})
                self.assertContains(history, f"整體平均：{expected}／10")
                exported = self.client.get(reverse("download_my_data")).json()["submissions"][0]
                self.assertEqual(exported["average_score"], expected)

    def test_not_applicable_is_not_zero_in_api_history_and_export(self):
        self.start()
        for scores, reason in (
            ([6] * 11 + [None], "未計算：包含不適用題目"),
            ([None] * 12, "未計算：沒有可用數值回答"),
        ):
            with self.subTest(reason=reason):
                response = self.post(scores)
                self.assertEqual(response.status_code, 201, response.content)
                data = response.json()
                self.assertIsNone(data["average_score"])
                self.assertEqual(data["average_unavailable_reason"], reason)
                self.assertIsNone(data["answers"][-1]["score"])
                self.assertEqual(data["answers"][-1]["label"], "不適用")
                retry = self.client.get(f"/api/submissions/{data['id']}/").json()
                self.assertEqual(retry, data)
                history = self.client.get(reverse("my_hearing"), {"questionnaire": "ssq12-tw"})
                self.assertContains(history, reason)
                self.assertNotContains(history, "總分")
                self.assertNotContains(history, 'id="trend-chart"')
                exported = self.client.get(reverse("download_my_data")).json()["submissions"][0]
                self.assertIsNone(exported["average_score"])
                self.assertIsNone(exported["total_score"])
                self.assertIsNone(exported["answers"][-1]["score"])
                self.assertEqual(exported["answers"][-1]["choice"], "不適用")
                self.assertEqual(exported["average_unavailable_reason"], reason)

    def test_questionnaire_has_original_anchors_and_explicit_not_applicable(self):
        self.start()
        response = self.client.get(f"/api/questionnaires/{self.questionnaire.pk}/")
        self.assertEqual(response.status_code, 200)
        questions = response.json()["questions"]
        self.assertEqual(questions[0]["choices"][-1], {"value": None, "label": "不適用"})
        for number, labels in (
            (1, ("完全不行", "輕鬆做到")),
            (9, ("混亂", "分開")),
            (11, ("不清晰", "清晰")),
            (12, ("非常專心", "輕鬆做到")),
        ):
            self.assertEqual(
                questions[number - 1]["scale"], {"min_label": labels[0], "max_label": labels[1]}
            )
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk]))
        self.assertContains(page, "完全不行選 0")
        self.assertContains(page, "經驗不足可以先不填")
        # #76 rule 7: describe current unaided experience, never recall before fitting.
        self.assertContains(page, "選「沒戴」時，依您目前不戴助聽器時的實際經驗")
        self.assertNotContains(page, "回想")

    def test_invalid_or_missing_answers_never_save_and_retries_keep_one_record(self):
        self.start()
        for value in (-1, 11, 6.5, 6.0, True, "6"):
            with self.subTest(value=value):
                self.assertEqual(self.post([value] + [6] * 11).status_code, 400)
                self.assertFalse(self.user.submissions.exists())
        payload = {
            "questionnaire": self.questionnaire.pk,
            "wearing_hearing_aid": False,
            "answers": [{"question": q.pk, "score": 6} for q in self.questions],
        }
        for problem in ("missing", "duplicate", "foreign", "missing_score"):
            import copy

            body = copy.deepcopy(payload)
            if problem == "missing":
                body["answers"].pop()
            elif problem == "duplicate":
                body["answers"][0] = body["answers"][1]
            elif problem == "foreign":
                body["answers"][0]["question"] = 999999
            else:
                del body["answers"][0]["score"]
            response = self.client.post(
                "/api/submissions/",
                body,
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            )
            self.assertEqual(response.status_code, 400)
            self.assertFalse(self.user.submissions.exists())
        key = uuid.uuid4()
        first = self.post([0] + [None] * 11, key)
        repeat = self.post([0] + [None] * 11, key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(first.json(), repeat.json())
        self.assertEqual(self.post([1] + [None] * 11, key).status_code, 409)
        self.assertEqual(self.user.submissions.count(), 1)

    def test_html_fallback_requires_each_answer_and_saves_explicit_na(self):
        self.start()
        data = {
            "form-TOTAL_FORMS": 12,
            "form-INITIAL_FORMS": 0,
            "wearing_hearing_aid": "True",
            "idempotency_key": str(uuid.uuid4()),
        }
        for index, question in enumerate(self.questions):
            data[f"form-{index}-question_id"] = question.pk
            data[f"form-{index}-score"] = "na" if index == 0 else "0"
        url = reverse("screening", args=[self.questionnaire.pk])
        missing = dict(data)
        del missing["form-1-score"]
        page = self.client.post(url, missing)
        self.assertContains(page, 'href="#question-2"')
        self.assertContains(page, 'role="alert"')
        self.assertNotContains(page, 'id="answer-app"')
        self.assertFalse(self.user.submissions.exists())
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(self.client.post(url, data), response.url)
        submission = self.user.submissions.get()
        self.assertTrue(submission.wearing_hearing_aid)
        self.assertIsNone(submission.answers.get(question=self.questions[0]).score)
        self.assertEqual(submission.answers.get(question=self.questions[1]).score, 0)
        page = self.client.get(response.url)
        self.assertContains(page, "未計算：包含不適用題目")

    def test_owner_privacy_and_deletion_include_ssq12(self):
        from screening.models import Answer, Submission, User

        self.start()
        data = self.post([6] * 12).json()
        other = consented_user(username="other")
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"/api/submissions/{data['id']}/").status_code, 404)
        self.assertEqual(self.client.get(reverse("result", args=[data["id"]])).status_code, 404)
        self.assertEqual(self.client.get("/api/submissions/").json()["results"], [])
        self.assertEqual(self.client.get(reverse("download_my_data")).json()["submissions"], [])
        self.client.force_login(self.user)
        response = self.client.post(reverse("delete_account"), {"password": "Test-pass-12345"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Submission.objects.filter(pk=data["id"]).exists())
        self.assertFalse(Answer.objects.filter(submission_id=data["id"]).exists())
        self.assertTrue(User.objects.filter(pk=other.pk).exists())

    def test_seed_is_repeatable_without_changing_existing_versions(self):
        self.start()
        before = list(self.questionnaire.questions.values_list("pk", "question_text"))
        self.post([6] * 12)
        call_command("seed_questionnaires", stdout=StringIO())
        self.assertEqual(
            list(self.questionnaire.questions.values_list("pk", "question_text")), before
        )
        self.assertEqual(self.questionnaire.questions.count(), 12)

    def test_schema_documents_nullable_numeric_answers_and_optional_scale(self):
        import yaml

        self.start()
        schema = yaml.safe_load(self.client.get("/api/schema/").content)
        components = schema["components"]["schemas"]
        score = components["Answer"]["properties"]["score"]
        self.assertEqual(score.get("type"), "integer")
        self.assertTrue(score["nullable"])
        self.assertEqual(score["maximum"], 10)
        self.assertNotIn("scale", components["Question"]["required"])
