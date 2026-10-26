import json
import uuid
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import ClassVar
from unittest import mock
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.db import DatabaseError, connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.models import (
    Answer,
    Category,
    Question,
    Questionnaire,
    Submission,
    SubmissionQuerySet,
)
from screening.tests.helpers import consented_user, fake_definition, register


class ApiFoundationTests(TestCase):
    QUESTIONNAIRES = "/api/questionnaires/"
    SCHEMA = "/api/schema/"
    SCHEMA_FILE = Path(__file__).resolve().parent.parent.parent / "docs" / "api" / "schema.yaml"

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="tester")

    def test_anonymous_gets_403_json(self):
        response = self.client.get(self.QUESTIONNAIRES)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("detail", response.json())

    def test_anonymous_cannot_read_schema(self):
        # The schema view renders errors in its own OpenAPI format (YAML), not JSON.
        response = self.client.get(self.SCHEMA)
        self.assertEqual(response.status_code, 403)
        content = response.content.decode()
        self.assertIn("detail", content)
        self.assertNotIn("openapi", content)
        self.assertNotIn("/api/questionnaires/", content)

    def test_questionnaire_list_is_read_only(self):
        self.client.force_login(self.user)
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.QUESTIONNAIRES)
                self.assertEqual(response.status_code, 405)

    def test_questionnaire_list(self):
        # Lower id sorts last by code and name, so only ordering by id passes.
        first = Questionnaire.objects.create(questionnaire_name="ZZ 問卷", code="zz")
        second = Questionnaire.objects.create(questionnaire_name="AA 問卷", code="aa")
        self.client.force_login(self.user)
        with register(fake_definition("zz"), fake_definition("aa")):
            response = self.client.get(self.QUESTIONNAIRES)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {"id": first.id, "code": "zz", "name": "ZZ 問卷", "levels": []},
                {"id": second.id, "code": "aa", "name": "AA 問卷", "levels": []},
            ],
        )

    def test_questionnaire_list_empty(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.QUESTIONNAIRES).json(), [])

    def test_schema_lists_endpoints(self):
        self.client.force_login(self.user)
        response = self.client.get(self.SCHEMA)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertTrue(content.startswith("openapi:"))
        self.assertIn(self.QUESTIONNAIRES, content)

    def test_schema_is_yaml_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.SCHEMA, {"format": "json"}).status_code, 404)
        self.assertEqual(
            self.client.get(self.SCHEMA, HTTP_ACCEPT="application/json").status_code, 406
        )

    def test_committed_schema_is_up_to_date(self):
        out = StringIO()
        call_command("spectacular", stdout=out)
        self.assertEqual(
            out.getvalue(),
            self.SCHEMA_FILE.read_text(encoding="utf-8"),
            "API changed: run `python manage.py spectacular --file docs/api/schema.yaml`",
        )


class ApiSubmissionTests(TestCase):
    LIST = "/api/submissions/"
    ITEM_FIELDS: ClassVar[set[str]] = {
        "id",
        "created_at",
        "questionnaire",
        "wearing_hearing_aid",
        "scores",
        "level",
    }

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(
            username="alice_account", email="alice@example.com", birth_year=1950
        )
        cls.other = consented_user(username="bob_account")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _make_submission(self, user=None, scores=(0,) * 10, questionnaire=None, wearing=None):
        submission = Submission.objects.create(
            user=user or self.user,
            questionnaire=questionnaire or self.questionnaire,
            wearing_hearing_aid=wearing,
        )
        # Reversed so answers are stored out of question order.
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in reversed(list(zip(self.questions, scores, strict=False)))
        )
        return submission

    def _detail_url(self, submission_id):
        return f"{self.LIST}{submission_id}/"

    def test_anonymous_gets_403(self):
        submission = self._make_submission()
        self.client.logout()
        for url in (self.LIST, self._detail_url(submission.id)):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_endpoints_are_read_only(self):
        submission = self._make_submission()
        for url in (self.LIST, self._detail_url(submission.id)):
            # POST on the list is the submit endpoint (ApiSubmitTests).
            methods = (
                ("put", "patch", "delete")
                if url == self.LIST
                else ("post", "put", "patch", "delete")
            )
            for method in methods:
                with self.subTest(url=url, method=method):
                    self.assertEqual(getattr(self.client, method)(url).status_code, 405)

    def test_list_only_own_newest_first_with_exact_fields(self):
        older = self._make_submission()
        newer = self._make_submission()
        self._make_submission(user=self.other)
        results = self.client.get(self.LIST).json()["results"]
        self.assertEqual([item["id"] for item in results], [newer.id, older.id])
        for item in results:
            self.assertEqual(set(item), self.ITEM_FIELDS)
            self.assertEqual(item["questionnaire"], {"code": "hhie-s", "name": "HHIE-S"})
            self.assertEqual(set(item["scores"]), {"total", "emotional", "social"})
            self.assertEqual(set(item["level"]), {"code", "text"})

    def test_scores_match_result_page(self):
        # emotional 5 x 4 = 20, social 3 x 2 = 6 -> total 26 (severe)
        submission = self._make_submission(scores=[4, 4, 4, 4, 4, 2, 2, 2, 0, 0])
        page = self.client.get(reverse("result", args=[submission.id])).context
        for url in (self.LIST, self._detail_url(submission.id)):
            with self.subTest(url=url):
                data = self.client.get(url).json()
                item = data["results"][0] if "results" in data else data
                self.assertEqual(
                    item["scores"],
                    {
                        "total": page["total_score"],
                        "emotional": page["emotional"],
                        "social": page["social"],
                    },
                )
                self.assertEqual(item["scores"], {"total": 26, "emotional": 20, "social": 6})
                self.assertEqual(
                    item["level"], {"code": "severe", "text": page["classified_score_text"]}
                )

    def test_wearing_hearing_aid_values(self):
        expected = {}
        for wearing in (True, False, None):
            expected[self._make_submission(wearing=wearing).id] = wearing
        results = self.client.get(self.LIST).json()["results"]
        self.assertEqual({item["id"]: item["wearing_hearing_aid"] for item in results}, expected)

    def test_all_never_scores_zero_not_null(self):
        self._make_submission(scores=[0] * 10)
        item = self.client.get(self.LIST).json()["results"][0]
        self.assertEqual(item["scores"], {"total": 0, "emotional": 0, "social": 0})
        self.assertEqual(item["level"]["code"], "normal")

    def test_unknown_level_still_returns_scores(self):
        no_thresholds = Questionnaire.objects.create(
            questionnaire_name="測試問卷", code="no-thresholds"
        )
        self.enterContext(register(fake_definition("no-thresholds")))
        submission = self._make_submission(questionnaire=no_thresholds, scores=[4] * 10)
        for url in (self.LIST, self._detail_url(submission.id)):
            with self.subTest(url=url), self.assertLogs("screening.scoring", "ERROR"):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                data = response.json()
                item = data["results"][0] if "results" in data else data
                self.assertEqual(item["level"], {"code": "unknown", "text": "無法判讀"})
                self.assertEqual(item["scores"]["total"], 40)

    def test_cursor_pagination_has_no_gaps_or_duplicates(self):
        created = {self._make_submission().id for _ in range(21)}
        first = self.client.get(self.LIST).json()
        self.assertEqual(len(first["results"]), 20)
        self.assertIsNotNone(first["next"])
        second = self.client.get(first["next"]).json()
        self.assertEqual(len(second["results"]), 1)
        self.assertIsNone(second["next"])
        ids = [item["id"] for item in first["results"] + second["results"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), created)

    def test_pagination_with_identical_created_at(self):
        # Only the -id tie-breaker keeps equal timestamps from repeating or vanishing.
        created = {self._make_submission().id for _ in range(25)}
        Submission.objects.update(created_at=datetime(2026, 10, 14, 6, 30, tzinfo=ZoneInfo("UTC")))
        ids, url = [], self.LIST
        while url:
            page = self.client.get(url).json()
            ids += [item["id"] for item in page["results"]]
            url = page["next"]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), created)
        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_created_at_is_taipei_time(self):
        submission = self._make_submission()
        Submission.objects.filter(pk=submission.pk).update(
            created_at=datetime(2026, 10, 14, 6, 30, tzinfo=ZoneInfo("UTC"))
        )
        data = self.client.get(self._detail_url(submission.id)).json()
        self.assertEqual(data["created_at"], "2026-10-14T14:30:00+08:00")

    def test_empty_list(self):
        self.assertEqual(
            self.client.get(self.LIST).json(), {"next": None, "previous": None, "results": []}
        )

    def _count_list_queries(self, expected_rows):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.LIST)
        self.assertEqual(len(response.json()["results"]), expected_rows)
        return len(ctx.captured_queries)

    def test_list_query_count_does_not_grow(self):
        self._make_submission(scores=[4] * 10)
        one = self._count_list_queries(expected_rows=1)
        for _ in range(4):
            self._make_submission(scores=[2] * 10)
        five = self._count_list_queries(expected_rows=5)
        self.assertEqual(one, five)

    def test_detail_matches_result_page(self):
        submission = self._make_submission(scores=[4, 2, 0, 0, 0, 0, 0, 0, 0, 0], wearing=True)
        page = self.client.get(reverse("result", args=[submission.id])).context
        data = self.client.get(self._detail_url(submission.id)).json()
        self.assertEqual(set(data), self.ITEM_FIELDS | {"advice", "answers"})
        self.assertEqual(data["id"], submission.id)
        self.assertEqual(data["advice"], page["advice"])
        self.assertEqual([a["number"] for a in data["answers"]], list(range(1, 11)))
        self.assertEqual(
            data["answers"][0], {"number": 1, "text": "第1題", "score": 4, "label": "常常"}
        )
        self.assertEqual(data["answers"][1]["label"], "有時")
        self.assertEqual(data["answers"][2]["label"], "從未")

    def test_others_and_missing_submission_both_404_identically(self):
        others = self._make_submission(user=self.other)
        not_found = self.client.get(self._detail_url(others.id + 1000))
        forbidden = self.client.get(self._detail_url(others.id))
        self.assertEqual(forbidden.status_code, 404)
        self.assertEqual(not_found.status_code, 404)
        self.assertEqual(forbidden.content, not_found.content)

    def test_responses_have_no_personal_data(self):
        submission = self._make_submission()
        for url in (self.LIST, self._detail_url(submission.id)):
            content = self.client.get(url).content.decode()
            for secret in ("alice_account", "alice@example.com", "1950", "birth", "user"):
                with self.subTest(url=url, secret=secret):
                    self.assertNotIn(secret, content)

    def test_schema_lists_submission_endpoints(self):
        content = self.client.get("/api/schema/").content.decode()
        self.assertIn("/api/submissions/:", content)
        self.assertIn("/api/submissions/{id}/:", content)


class ApiQuestionnaireDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="tester")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        # Created out of order so the response has to sort by number.
        for number in (2, 1):
            Question.objects.create(
                questionnaire=cls.questionnaire,
                question_text=f"第{number}題的完整題目文字，超過三十個字也要完整回傳，不可以被截斷掉喔",
                question_number=number,
                category=Category.EMOTIONAL,
            )

    def setUp(self):
        self.client.force_login(self.user)

    def _url(self, pk):
        return f"/api/questionnaires/{pk}/"

    def test_anonymous_gets_403(self):
        self.client.logout()
        self.assertEqual(self.client.get(self._url(self.questionnaire.pk)).status_code, 403)

    def test_returns_questions_in_order_with_choices(self):
        response = self.client.get(self._url(self.questionnaire.pk))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            set(data), {"id", "code", "name", "levels", "wearing_question", "questions"}
        )
        self.assertEqual(data["code"], "hhie-s")
        self.assertEqual(len(data["levels"]), 3)
        self.assertEqual([q["number"] for q in data["questions"]], [1, 2])
        first = data["questions"][0]
        self.assertEqual(set(first), {"id", "number", "text", "choices"})
        self.assertEqual(first["text"], Question.objects.get(question_number=1).question_text)
        self.assertEqual(
            first["choices"],
            [
                {"value": 4, "label": "常常"},
                {"value": 2, "label": "有時"},
                {"value": 0, "label": "從未"},
            ],
        )

    def test_missing_gets_404(self):
        # IOI-HA is served too since #245 (test_ioi_ha_api).
        self.assertEqual(self.client.get(self._url(9999)).status_code, 404)


class ApiSubmitTests(TestCase):
    URL = "/api/submissions/"

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="alice_account")
        cls.other = consented_user(username="bob_account")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        cls.ioi_questions = Question.objects.bulk_create(
            Question(questionnaire=cls.ioi_ha, question_text=f"IOI 第{i}題", question_number=i)
            for i in range(1, 8)
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _body(self, scores=(4,) * 5 + (2,) * 5, wearing=False, questions=None, questionnaire=None):
        questions = self.questions if questions is None else questions
        return {
            "questionnaire": (questionnaire or self.questionnaire).pk,
            "wearing_hearing_aid": wearing,
            # Reversed: the API must not depend on answer order.
            "answers": [
                {"question": q.pk, "score": s}
                for q, s in reversed(list(zip(questions, scores, strict=False)))
            ],
        }

    def _post(self, body, key="__new__", client=None):
        headers = {}
        if key == "__new__":
            key = str(uuid.uuid4())
        if key is not None:
            headers["Idempotency-Key"] = key
        return (client or self.client).post(
            self.URL, json.dumps(body), content_type="application/json", headers=headers
        )

    def assertNothingSaved(self):
        self.assertEqual(Submission.objects.count(), 0)
        self.assertEqual(Answer.objects.count(), 0)

    # 送出作答
    def test_anonymous_gets_403(self):
        self.client.logout()
        self.assertEqual(self._post(self._body()).status_code, 403)
        self.assertNothingSaved()

    def test_missing_csrf_token_gets_403(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(self._post(self._body(), client=client).status_code, 403)
        self.assertNothingSaved()

    def test_valid_submission_is_saved_and_scored(self):
        response = self._post(self._body(wearing=True))
        self.assertEqual(response.status_code, 201)
        submission = Submission.objects.get()
        self.assertEqual(submission.user, self.user)
        self.assertIs(submission.wearing_hearing_aid, True)
        self.assertEqual(submission.answers.count(), 10)
        data = response.json()
        self.assertEqual(data["id"], submission.pk)
        self.assertEqual(data["scores"], {"total": 30, "emotional": 20, "social": 10})
        self.assertEqual(data["level"], {"code": "severe", "text": "顯著影響"})
        # Same numbers as the history page.
        page = self.client.get(reverse("my_hearing")).content.decode()
        self.assertIn("總分：30", page)
        self.assertIn("顯著影響", page)

    def test_all_zero_is_a_real_score(self):
        response = self._post(self._body(scores=(0,) * 10))
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["scores"]["total"], 0)
        self.assertEqual(data["level"]["code"], "normal")

    def test_user_in_body_is_ignored(self):
        body = {**self._body(), "user": self.other.pk}
        self.assertEqual(self._post(body).status_code, 201)
        self.assertEqual(Submission.objects.get().user, self.user)
        self.assertFalse(self.other.submissions.exists())

    def test_invalid_answers_get_400(self):
        foreign = [*self.questions[:9], self.ioi_questions[0]]
        cases = {
            "missing": (
                self._body(scores=(0,) * 9, questions=self.questions[:9]),
                "有題目沒有作答",
            ),
            "duplicate": (
                self._body(questions=[*self.questions[:9], self.questions[0]]),
                "重複題目",
            ),
            "foreign": (self._body(questions=foreign), "有題目沒有作答"),
            "bad score": (self._body(scores=(3,) + (0,) * 9), None),
        }
        for name, (body, message) in cases.items():
            with self.subTest(name):
                response = self._post(body)
                self.assertEqual(response.status_code, 400)
                errors = response.json()
                self.assertEqual(set(errors), {"answers"})
                if message:
                    self.assertIn(message, errors["answers"])
                self.assertNothingSaved()

    def test_wearing_hearing_aid_is_required(self):
        body = self._body()
        # Only JSON true/false: DRF would otherwise read 1, "yes", "on", "true" as True.
        for value in ("missing", None, "maybe", 1, 0, "yes", "on", "true"):
            with self.subTest(value=value):
                if value == "missing":
                    body.pop("wearing_hearing_aid", None)
                else:
                    body["wearing_hearing_aid"] = value
                response = self._post(body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(), {"wearing_hearing_aid": ["請選擇這次有沒有戴助聽器"]}
                )
                self.assertNothingSaved()

    def test_unknown_questionnaire_gets_400(self):
        body = {**self._body(), "questionnaire": 9999}
        response = self._post(body)
        self.assertEqual(response.status_code, 400)
        self.assertIn("questionnaire", response.json())
        self.assertNothingSaved()

    def test_questionnaire_without_questions_gets_400(self):
        empty = Questionnaire.objects.create(questionnaire_name="空問卷", code="empty")
        self.enterContext(register(fake_definition("empty")))
        body = {"questionnaire": empty.pk, "wearing_hearing_aid": False, "answers": []}
        response = self._post(body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"questionnaire": ["這份問卷沒有題目"]})
        self.assertNothingSaved()

    def test_failure_midway_leaves_nothing(self):
        with (
            mock.patch.object(Answer.objects, "bulk_create", side_effect=DatabaseError),
            self.assertRaises(DatabaseError),
        ):
            self._post(self._body())
        self.assertNothingSaved()

    def test_schema_documents_write_endpoints(self):
        content = self.client.get("/api/schema/").content.decode()
        self.assertIn("/api/questionnaires/{id}/:", content)
        submissions = content.split("/api/submissions/:", 1)[1].split("/api/submissions/{id}/:")[0]
        self.assertIn("post:", submissions)
        self.assertIn("Idempotency-Key", submissions)

    def test_detail_stays_read_only(self):
        submission = Submission.objects.create(user=self.user, questionnaire=self.questionnaire)
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(f"{self.URL}{submission.pk}/")
                self.assertEqual(response.status_code, 405)

    # 收據編號
    def test_same_key_same_body_returns_first(self):
        key = str(uuid.uuid4())
        first = self._post(self._body(), key=key)
        second = self._post(self._body(), key=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(Submission.objects.count(), 1)

    def test_same_key_different_body_gets_409(self):
        key = str(uuid.uuid4())
        self._post(self._body(), key=key)
        # A valid HHIA-S body: only the questionnaire differs from the first request.
        hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")
        hhia_questions = Question.objects.bulk_create(
            Question(questionnaire=hhia_s, question_text=f"HHIA 第{i}題", question_number=i)
            for i in range(1, 11)
        )
        different = {
            "scores": self._body(scores=(0,) * 10),
            "wearing": self._body(wearing=True),
            "questionnaire": self._body(questions=hhia_questions, questionnaire=hhia_s),
        }
        for name, body in different.items():
            with self.subTest(name):
                response = self._post(body, key=key)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json(), {"detail": "這個收據編號已經用過"})
                self.assertEqual(Submission.objects.count(), 1)
                self.assertEqual(Submission.objects.get().total_answer_score, 30)

    def test_missing_or_invalid_key_gets_400(self):
        for key in (None, "", "not-a-uuid"):
            with self.subTest(key=key):
                response = self._post(self._body(), key=key)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"detail": "缺少或無效的收據編號"})
                self.assertNothingSaved()

    def test_key_is_scoped_to_user(self):
        key = str(uuid.uuid4())
        self.client.force_login(self.other)
        self._post(self._body(scores=(0,) * 10), key=key)
        self.client.force_login(self.user)
        response = self._post(self._body(), key=key)
        self.assertEqual(response.status_code, 201)
        mine = self.user.submissions.get()
        self.assertEqual(response.json()["id"], mine.pk)
        self.assertEqual(response.json()["scores"]["total"], 30)

    def test_concurrent_same_key_returns_first_not_500(self):
        key = str(uuid.uuid4())
        first = self._post(self._body(), key=key)
        # The second request checks before the first has saved, then hits the unique constraint.
        existing = Submission.objects.get()
        with mock.patch.object(
            SubmissionQuerySet, "find_by_key", autospec=True, side_effect=[None, existing]
        ):
            second = self._post(self._body(), key=key)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(Submission.objects.count(), 1)

    # 回傳內容
    def test_created_body_matches_detail_get(self):
        response = self._post(self._body())
        detail = self.client.get(f"{self.URL}{response.json()['id']}/")
        self.assertEqual(response.json(), detail.json())

    def test_errors_are_in_chinese_by_field(self):
        # wearing_hearing_aid is only required once the questionnaire is known (#170, SADL is
        # always-aided and needs none), so a missing questionnaire alone cannot flag it too.
        response = self._post({"answers": "not a list"})
        self.assertEqual(response.status_code, 400)
        errors = response.json()
        self.assertEqual(set(errors), {"questionnaire", "answers"})
        for messages in errors.values():
            for message in messages:
                self.assertRegex(message, r"[一-鿿]")

    # 兩支 API 接得起來
    def test_questionnaire_detail_feeds_submit(self):
        detail = self.client.get(f"/api/questionnaires/{self.questionnaire.pk}/").json()
        body = {
            "questionnaire": detail["id"],
            "wearing_hearing_aid": False,
            "answers": [
                {"question": q["id"], "score": q["choices"][-1]["value"]}
                for q in detail["questions"]
            ],
        }
        self.assertEqual(self._post(body).status_code, 201)
