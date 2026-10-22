"""SSQ12-TW public answering flow (#79)."""

import re
import uuid
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Questionnaire, Submission
from screening.questionnaires import ssq12_tw
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
                self.assertContains(page, f"整體平均 <strong>{expected}</strong> 分（滿分 10）")
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
        from screening.models import User

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


class Ssq12ResultRedesignTests(TestCase):
    """The SSQ12-TW result page's layout and 「比上一次」 line (#188)."""

    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.questionnaire = Questionnaire.objects.get(code="ssq12-tw")
        self.user = consented_user(username="ssq_redesign")
        self.client.force_login(self.user)

    def record(self, day, total=None, wearing=False, scores=None):
        """An SSQ12-TW record made at noon Taipei time; scores default to summing to total."""
        if scores is None:
            scores = [total // 12 + 1] * (total % 12) + [total // 12] * (12 - total % 12)
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(self.questionnaire.questions.all(), scores, strict=True)
        )
        when = datetime(*day, 12, tzinfo=ZoneInfo("Asia/Taipei"))
        Submission.objects.filter(pk=submission.pk).update(created_at=when)
        return submission

    def main(self, submission):
        content = self.client.get(reverse("result", args=[submission.id])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def text(self, main):
        return " ".join(re.sub(r"<[^>]+>", " ", main).split())

    def bar(self, main):
        # The 0–10 position bar, hidden from assistive tech; "" when the page has none.
        found = re.search(r'<div class="ssq-bar" aria-hidden="true">(.*?)ssq-bar-ends', main, re.S)
        return found.group(1) if found else ""

    def test_since_last_names_the_previous_record_and_the_bar_marks_both(self):
        self.record((2026, 4, 20), total=70)  # 5.8
        latest = self.record((2026, 10, 15), total=78)  # 6.5
        main = self.main(latest)
        self.assertIn("比上一次（2026/04/20，5.8 分）多 0.7 分（分數越高越好）", self.text(main))
        bar = self.bar(main)
        self.assertIn("--average: 6.5", bar)
        self.assertIn("--average: 5.8", bar)

    def test_since_last_skips_records_worn_the_other_way(self):
        self.record((2026, 1, 10), total=60, wearing=True)  # 5.0
        self.record((2026, 4, 20), total=70, wearing=False)
        latest = self.record((2026, 10, 15), total=78, wearing=True)
        main = self.main(latest)
        self.assertIn("比上一次（2026/01/10，5.0 分）多 1.5 分（分數越高越好）", self.text(main))
        self.assertIn("--average: 5.0", self.bar(main))

    def test_no_since_last_without_a_comparable_previous_record(self):
        not_applicable = [6] * 11 + [None]
        cases = {
            "first record": [],
            "previous worn the other way": [dict(total=70, wearing=True)],
            "previous has not applicable": [dict(total=70), dict(scores=not_applicable)],
            "hearing aid not recorded": [dict(total=70, wearing=None)],
        }
        for case, earlier in cases.items():
            with self.subTest(case):
                Answer.objects.all().delete()
                Submission.objects.all().delete()
                for month, record in enumerate(earlier, start=1):
                    self.record((2026, month, 10), **record)
                wearing = None if case == "hearing aid not recorded" else False
                main = self.main(self.record((2026, 10, 15), total=78, wearing=wearing))
                self.assertNotIn("上一次", self.text(main))
                bar = self.bar(main)
                self.assertIn("這次", bar)
                self.assertNotIn("上次", bar)
                self.assertEqual(bar.count("--average:"), 3)  # this record's label, fill, marker

    def test_a_record_with_not_applicable_has_neither_since_last_nor_bar(self):
        self.record((2026, 4, 20), total=70)
        latest = self.record((2026, 10, 15), scores=[6] * 11 + [None])
        main = self.main(latest)
        text = self.text(main)
        self.assertIn("未計算：包含不適用題目", text)
        self.assertNotIn("上一次", text)
        self.assertNotIn("整體平均 ", text)
        self.assertEqual(self.bar(main), "")

    def test_difference_uses_unrounded_averages_and_reads_more_less_or_same(self):
        # ADR 0001: 52 and 56 show 4.3 and 4.7, yet differ by 4 / 12 = 0.33, shown as 0.3.
        for previous, latest, expected in (
            (52, 56, "比上一次（2026/04/20，4.3 分）多 0.3 分（分數越高越好）"),
            (56, 52, "比上一次（2026/04/20，4.7 分）少 0.3 分（分數越高越好）"),
            (48, 52, "比上一次（2026/04/20，4.0 分）多 0.3 分（分數越高越好）"),
            (70, 70, "和上一次一樣"),
        ):
            with self.subTest(previous=previous, latest=latest):
                Answer.objects.all().delete()
                Submission.objects.all().delete()
                self.record((2026, 4, 20), total=previous)
                main = self.main(self.record((2026, 10, 15), total=latest))
                self.assertIn(expected, self.text(main))
                self.assertIn("上次", self.bar(main))

    def test_page_reads_topic_status_average_then_folded_answers_and_disclaimer_last(self):
        latest = self.record((2026, 10, 15), total=78, wearing=True)
        main = self.main(latest)
        self.assertIn('<h1 class="h3 mt-2 mb-1">日常聆聽能力</h1>', main)
        text = self.text(main)
        order = [
            "SSQ12-TW・2026/10/15 作答・有戴助聽器",
            "整體平均 6.5 分（滿分 10）",
            "分數越高，代表您回報的聆聽能力越好。",
            "看全部 12 題的回答",
        ]
        self.assertEqual([text.index(part) for part in order], sorted(text.index(p) for p in order))
        folded = re.search(
            r"<details[^>]*>\s*<summary>看全部 12 題的回答</summary>(.*?)</details>", main, re.S
        )
        self.assertIsNotNone(folded)
        self.assertEqual(folded.group(1).count("<li"), 12)
        self.assertIn(
            self.questionnaire.questions.get(question_number=12).question_text, folded.group(1)
        )
        self.assertTrue(text.endswith("這份紀錄不能代替專業評估，也不代表助聽器效益合格與否。"))


class Ssq12LowestItemsTests(TestCase):
    """The SSQ12-TW result page's 「分數最低的 n 題」 (#189)."""

    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.questionnaire = Questionnaire.objects.get(code="ssq12-tw")
        self.user = consented_user(username="ssq_lowest")
        self.client.force_login(self.user)

    def lowest(self, scores):
        """The page's lowest-items section for a record with these 12 scores (None: 不適用)."""
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.questionnaire, wearing_hearing_aid=False
        )
        # Answers saved last item first, so their ids do not follow the item numbers.
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in reversed(
                list(zip(self.questionnaire.questions.all(), scores, strict=True))
            )
        )
        self.page = self.client.get(reverse("result", args=[submission.id])).content.decode()
        found = re.search(
            r'<section [^>]*aria-labelledby="ssq-lowest-title">(.*?)</section>', self.page, re.S
        )
        return found.group(1) if found else None

    def items(self, section):
        """(question text, score) of each listed item, in page order."""
        # Each item a card since the text-heavy pages tidy-up: the question, then its score tag.
        return re.findall(
            r'<div class="score-card-head"><span>(.*?)</span><span class="score-chip">(.*?)</span>',
            section,
            re.S,
        )

    def test_lists_the_three_lowest_scored_items_by_score_then_item_number(self):
        # Items 1 and 5 不適用; items 3 and 4 tie for third place at 4.
        scores = [None, 3, 4, 4, None, 2, 8, 8, 8, 8, 8, 8]
        section = self.lowest(scores)
        self.assertIn("分數最低的 3 題", section)
        self.assertEqual(
            self.items(section),
            [
                (ssq12_tw.QUESTIONS[5], "2 分"),
                (ssq12_tw.QUESTIONS[1], "3 分"),
                (ssq12_tw.QUESTIONS[2], "4 分"),
            ],
        )

    def test_heading_counts_the_items_listed_when_fewer_than_three_have_a_score(self):
        section = self.lowest([None] * 5 + [7] + [None] * 5 + [5])
        self.assertIn("分數最低的 2 題", section)
        self.assertEqual(
            self.items(section), [(ssq12_tw.QUESTIONS[11], "5 分"), (ssq12_tw.QUESTIONS[5], "7 分")]
        )

    def test_no_section_when_every_item_is_not_applicable(self):
        self.assertIsNone(self.lowest([None] * 12))
        self.assertNotIn("分數最低的", self.page)
