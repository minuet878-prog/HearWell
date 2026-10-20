"""HHIA-S public answering flow, issue #78."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import Questionnaire
from screening.tests.helpers import consented_user


class HhiaSTests(TestCase):
    def test_catalog_has_an_independent_ten_question_version(self):
        original = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        call_command("seed_hhia_s", stdout=StringIO())
        call_command("seed_hhia_s", stdout=StringIO())
        user = consented_user(username="adult")
        self.client.force_login(user)
        response = self.client.get(reverse("questionnaire_list"))
        self.assertContains(response, "HHIA-S")
        self.assertContains(response, "適合 18–64 歲成人")
        questionnaire = Questionnaire.objects.get(code="hhia-s")
        self.assertNotEqual(questionnaire.pk, original.pk)
        self.assertEqual(questionnaire.questions.count(), 10)
        self.assertEqual(
            questionnaire.questions.get(question_number=3).question_text,
            "聽力問題會讓你看電影或戲劇表演時感到困難嗎？",
        )

    def test_api_level_bands_use_adult_texts(self):
        self._start()
        response = self.client.get(f"/api/questionnaires/{self.questionnaire.pk}/")
        self.assertEqual(
            response.json()["levels"],
            [
                {"code": "normal", "text": "無／極輕微影響", "max": 8},
                {"code": "mild_to_moderate", "text": "輕至中度影響", "max": 24},
                {"code": "severe", "text": "顯著影響", "max": 40},
            ],
        )

    def _start(self):
        call_command("seed_hhia_s", stdout=StringIO())
        self.questionnaire = Questionnaire.objects.get(code="hhia-s")
        self.questions = list(self.questionnaire.questions.all())
        self.user = consented_user(username="adult", password="TestingPass123!")
        self.client.force_login(self.user)

    def _submit(self, scores, key=None):
        import uuid

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

    def test_results_use_adult_levels_and_advice_at_all_boundaries(self):
        self._start()
        cases = (
            (
                0,
                "無／極輕微影響",
                "您這次回報的生活影響較少。若仍有聽不清楚的困擾，建議安排聽力評估。",
            ),
            (
                8,
                "無／極輕微影響",
                "您這次回報的生活影響較少。若仍有聽不清楚的困擾，建議安排聽力評估。",
            ),
            (
                10,
                "輕至中度影響",
                "您回報聽力困擾已影響部分日常生活。建議安排聽力評估，並帶這份結果與聽力師或耳鼻喉科醫師討論。",
            ),
            (
                24,
                "輕至中度影響",
                "您回報聽力困擾已影響部分日常生活。建議安排聽力評估，並帶這份結果與聽力師或耳鼻喉科醫師討論。",
            ),
            (
                26,
                "顯著影響",
                "您回報聽力困擾對生活有顯著影響。建議儘早安排聽力評估，與聽力師或耳鼻喉科醫師討論適合您的協助方式。",
            ),
            (
                40,
                "顯著影響",
                "您回報聽力困擾對生活有顯著影響。建議儘早安排聽力評估，與聽力師或耳鼻喉科醫師討論適合您的協助方式。",
            ),
        )
        explanation = (
            "這份問卷反映您感受到的生活影響，不能判定聽損程度，也不能單憑分數決定是否需要助聽器。"
        )
        for total, level, advice in cases:
            with self.subTest(total=total):
                scores = [4] * (total // 4) + ([2] if total % 4 else [])
                scores += [0] * (10 - len(scores))
                response = self._submit(scores)
                self.assertEqual(response.status_code, 201)
                data = response.json()
                self.assertEqual(data["scores"]["total"], total)
                self.assertEqual(data["level"]["text"], level)
                self.assertIn(advice, data["advice"])
                self.assertIn(explanation, data["advice"])
                page = self.client.get(reverse("result", args=[data["id"]]))
                self.assertContains(page, advice)
                self.assertContains(page, explanation)
                self.assertContains(page, level)

    def test_original_answer_labels_match_api_form_and_results(self):
        self._start()
        detail = self.client.get(f"/api/questionnaires/{self.questionnaire.pk}/").json()
        self.assertEqual(
            detail["questions"][0]["choices"],
            [
                {"value": 4, "label": "會"},
                {"value": 2, "label": "有時"},
                {"value": 0, "label": "不會"},
            ],
        )
        response = self._submit([2] * 10)
        data = response.json()
        self.assertEqual(data["scores"], {"total": 20, "emotional": 10, "social": 10})
        self.assertEqual([a["label"] for a in data["answers"]], ["有時"] * 10)
        data = self._submit([4] * 10).json()
        self.assertEqual([a["label"] for a in data["answers"]], ["會"] * 10)
        page = self.client.get(reverse("result", args=[data["id"]]))
        self.assertContains(page, "——會", count=10)
        page = self.client.get(reverse("screening", args=[self.questionnaire.pk]))
        self.assertContains(page, "會")
        self.assertContains(page, "不會")
        self.assertNotContains(page, "圈選常常")
        self.assertContains(page, 'id="answer-form"')
        self.assertContains(page, "<fieldset", count=11)

    def _web_data(self):
        import uuid

        data = {
            "form-TOTAL_FORMS": 10,
            "form-INITIAL_FORMS": 0,
            "wearing_hearing_aid": "True",
            "idempotency_key": str(uuid.uuid4()),
        }
        for i, question in enumerate(self.questions):
            data[f"form-{i}-question_id"] = question.pk
            data[f"form-{i}-score"] = 2
        return data

    def test_web_fallback_can_complete_retry_and_find_history_after_65(self):
        self._start()
        self.user.birth_year = 1940
        self.user.save()
        data = self._web_data()
        url = reverse("screening", args=[self.questionnaire.pk])
        first = self.client.post(url, data)
        self.assertEqual(first.status_code, 302)
        self.assertRedirects(self.client.post(url, data), first.url)
        self.assertEqual(self.user.submissions.count(), 1)
        result = self.client.get(first.url)
        self.assertContains(result, "總分 20 分")
        self.assertContains(result, "——有時", count=10)
        history = self.client.get(reverse("my_hearing"), {"questionnaire": "hhia-s"})
        self.assertContains(history, first.url)
        self.assertContains(history, "總分：20")
        self.assertContains(history, "有戴")
        self.assertContains(history, "輕至中度影響")
        submission = self.user.submissions.get()
        self.assertContains(history, submission.created_at.astimezone().strftime("%Y/%m/%d"))
        api = self.client.get(f"/api/submissions/{submission.pk}/").json()
        self.assertEqual(api["wearing_hearing_aid"], True)
        self.assertEqual(api["scores"]["total"], 20)
        self.assertEqual(len(api["answers"]), 10)
        questions = list(self.questionnaire.questions.values_list("pk", "question_text"))
        call_command("seed_hhia_s", stdout=StringIO())
        self.assertEqual(
            list(self.questionnaire.questions.values_list("pk", "question_text")), questions
        )

    def test_web_invalid_answers_are_not_saved_and_keep_accessible_errors(self):
        self._start()
        url = reverse("screening", args=[self.questionnaire.pk])
        for change in ("missing", "duplicate", "wrong", "invalid", "wearing"):
            with self.subTest(change=change):
                data = self._web_data()
                if change == "missing":
                    del data["form-0-score"]
                elif change == "duplicate":
                    data["form-0-question_id"] = self.questions[1].pk
                elif change == "wrong":
                    data["form-0-question_id"] = 999999
                elif change == "invalid":
                    data["form-0-score"] = 3
                else:
                    del data["wearing_hearing_aid"]
                response = self.client.post(url, data)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="error-summary"')
                self.assertContains(response, 'role="alert"')
                self.assertNotContains(response, 'id="answer-app"')
                if change == "missing":
                    self.assertContains(response, 'href="#question-1"')
                self.assertFalse(self.user.submissions.exists())

    def test_api_retry_validation_and_private_results(self):
        import uuid

        self._start()
        key = uuid.uuid4()
        first = self._submit([2] * 10, key)
        repeat = self._submit([2] * 10, key)
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(first.json(), repeat.json())
        self.assertEqual(self._submit([4] * 10, key).status_code, 409)
        valid = first.json()
        detail_url = f"/api/submissions/{valid['id']}/"
        self.assertEqual(self.client.get(detail_url).json(), valid)
        self.assertEqual(
            self.client.get("/api/submissions/").json()["results"][0]["scores"], valid["scores"]
        )
        for change in ("missing", "duplicate", "wrong", "invalid"):
            payload = {
                "questionnaire": self.questionnaire.pk,
                "wearing_hearing_aid": False,
                "answers": [{"question": q.pk, "score": 2} for q in self.questions],
            }
            if change == "missing":
                payload["answers"].pop()
            elif change == "duplicate":
                payload["answers"][0] = payload["answers"][1]
            elif change == "wrong":
                payload["answers"][0]["question"] = 999999
            else:
                payload["answers"][0]["score"] = 3
            with self.subTest(change=change):
                response = self.client.post(
                    "/api/submissions/",
                    payload,
                    content_type="application/json",
                    HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.user.submissions.count(), 1)
        other = consented_user(username="other")
        self.client.force_login(other)
        self.assertEqual(self.client.get(detail_url).status_code, 404)
        self.assertEqual(self.client.get(reverse("result", args=[valid["id"]])).status_code, 404)
        self.assertEqual(self.client.get("/api/submissions/").json()["results"], [])
        self.assertNotContains(
            self.client.get(reverse("my_hearing")), reverse("result", args=[valid["id"]])
        )

    def test_export_and_account_deletion_include_new_answers_only_for_owner(self):
        from screening.models import Answer, Submission, User

        self._start()
        data = self._submit([2] * 10).json()
        other = consented_user(username="other")
        unrelated = Submission.objects.create(user=other, questionnaire=self.questionnaire)
        Answer.objects.create(submission=unrelated, question=self.questions[0], score=4)
        response = self.client.get(reverse("download_my_data"))
        exported = response.json()["submissions"]
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["total_score"], 20)
        self.assertEqual(len(exported[0]["answers"]), 10)
        self.assertEqual(exported[0]["answers"][0]["choice"], "有時")
        self.assertEqual(exported[0]["level"], "輕至中度影響")
        response = self.client.post(reverse("delete_account"), {"password": "TestingPass123!"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Submission.objects.filter(pk=data["id"]).exists())
        self.assertFalse(Answer.objects.filter(submission_id=data["id"]).exists())
        self.assertTrue(Submission.objects.filter(pk=unrelated.pk).exists())
        self.assertEqual(self.questionnaire.questions.count(), 10)
