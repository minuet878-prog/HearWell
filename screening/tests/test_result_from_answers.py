"""A result worked out from answers not saved (ticket #494, spec #492): no record, no account."""

from io import StringIO

from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Questionnaire, Submission
from screening.questionnaires import hhia_s, hhie_s
from screening.tests.helpers import consented_user, submission_with_answers

# Each questionnaire's answers for its three levels, item-number order (emotional items 1, 2, 4,
# 7, 9 on HHIE-S; 1, 2, 4, 7, 9 on HHIA-S): 無／極輕微 up to 8, 輕度到中度 up to 24, then 顯著.
LEVELS = {
    hhie_s.CODE: (
        ([0, 2, 0, 0, 2, 0, 0, 2, 0, 0], "normal"),
        ([4, 4, 2, 0, 0, 0, 4, 0, 0, 2], "mild_to_moderate"),
        ([4, 4, 4, 4, 4, 4, 4, 4, 2, 0], "severe"),
    ),
    hhia_s.CODE: (
        ([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "normal"),
        ([4, 4, 2, 0, 2, 2, 0, 2, 0, 0], "mild_to_moderate"),
        ([4, 4, 4, 4, 4, 4, 4, 4, 4, 4], "severe"),
    ),
}


class ResultFromAnswersTestCase(TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())  # HHIA-S
        cls.user = consented_user(username="from_answers")

    def from_answers(self, code, scores, wearing_hearing_aid=False):
        """The result of these answers, item-number order, worked out without saving them."""
        questionnaire = Questionnaire.objects.get(code=code)
        questions = list(questionnaire.questions.order_by("question_number"))
        answers = list(zip(questions, scores, strict=True))
        return questionnaire.definition.result.from_answers(
            questionnaire, answers, wearing_hearing_aid
        )


class SameAsTheRecordTests(ResultFromAnswersTestCase):
    def test_total_subscores_and_level_match_the_saved_record_at_each_level(self):
        for code, cases in LEVELS.items():
            for scores, level in cases:
                with self.subTest(code=code, level=level):
                    result = self.from_answers(code, scores)
                    record = submission_with_answers(
                        self.user, code, scores, wearing_hearing_aid=False
                    ).result
                    self.assertEqual(result.level["level"], level)
                    self.assertEqual(result.total, record.total)
                    self.assertEqual(result.subscores, record.subscores)
                    self.assertEqual(result.level, record.level)

    def test_a_worked_example(self):
        result = self.from_answers(hhie_s.CODE, [4, 4, 2, 0, 0, 0, 4, 0, 0, 2])
        self.assertEqual(result.total, 16)
        self.assertEqual(result.subscores, {"emotional": 12, "social": 4})
        self.assertEqual(result.level["text"], "輕度到中度影響")

    def test_saves_nothing(self):
        submissions, answers = Submission.objects.count(), Answer.objects.count()
        for code, cases in LEVELS.items():
            for scores, _level in cases:
                self.from_answers(code, scores)
        self.assertEqual(Submission.objects.count(), submissions)
        self.assertEqual(Answer.objects.count(), answers)


class NoAccountTests(ResultFromAnswersTestCase):
    def test_no_since_last_even_after_a_record_of_the_same_answers(self):
        # 與上次比較 (#461) is against the account's last record: without an account, none.
        for wearing in (False, True):
            with self.subTest(wearing=wearing):
                scores = [4, 4, 2, 0, 0, 0, 4, 0, 0, 2]
                submission_with_answers(
                    self.user, hhie_s.CODE, [0] * 10, wearing_hearing_aid=wearing
                )
                self.assertIsNotNone(
                    submission_with_answers(
                        self.user, hhie_s.CODE, scores, wearing_hearing_aid=wearing
                    ).result.since_last
                )
                self.assertIsNone(self.from_answers(hhie_s.CODE, scores, wearing).since_last)

    def test_worked_out_and_its_page_data_without_a_query(self):
        for code in LEVELS:
            for wearing in (False, True, None):
                with self.subTest(code=code, wearing=wearing):
                    result = self.from_answers(code, [4] * 10, wearing)
                    with self.assertNumQueries(0):
                        worked_out = (result.total, result.subscores, result.level)
                        since_last = result.since_last
                        context = result.page_context()
                    self.assertEqual(worked_out[0], 40)
                    self.assertIsNone(since_last)
                    # SSQ12-TW's link needs an account (spec #492).
                    self.assertIsNone(context["optional_ssq12"])
                    self.assertEqual(
                        [answer.get_answer_display() for answer in context["answers"]],
                        [dict(hhie_s.CHOICES if code == hhie_s.CODE else hhia_s.CHOICES)[4]] * 10,
                    )


class SectionTests(ResultFromAnswersTestCase):
    """The result page's result section drawn alone, as the guest's result page will draw it."""

    def render(self, result):
        context = {"submission": result.submission} | result.page_context()
        return render_to_string("screening/graded_result.html", context)

    def test_draws_the_whole_result_without_a_query(self):
        scores = [4, 4, 2, 0, 0, 0, 4, 0, 0, 2]
        result = self.from_answers(hhie_s.CODE, scores, False)
        with self.assertNumQueries(0):
            html = self.render(result)
        self.assertIn('總分 <span class="result-number">16</span> 分（滿分 40）', html)
        self.assertIn(
            '<h2 class="result-block-level" aria-describedby="result-score">輕度到中度影響</h2>',
            html,
        )
        self.assertIn('<div class="score-bar" aria-hidden="true">', html)
        self.assertIn("<span>輕度到中度影響</span></div>", html)  # under the bar's marker
        self.assertIn('<p class="mb-1">情緒分數：12　社交分數：4</p>', html)
        self.assertIn("助聽器：沒戴", html)
        self.assertIn(hhie_s.ADVICE["mild_to_moderate"], html)
        questionnaire = Questionnaire.objects.get(code=hhie_s.CODE)
        questions = questionnaire.questions.order_by("question_number")
        labels = dict(hhie_s.CHOICES)
        for question, score in zip(questions, scores, strict=True):
            self.assertIn(f"<li>{question.question_text}——{labels[score]}</li>", html)

    def test_no_since_last_journey_records_report_or_sharing(self):
        for code in LEVELS:
            with self.subTest(code=code):
                html = self.render(self.from_answers(code, [4] * 10, False))
                self.assertNotIn("result-since-last", html)
                # The 照顧旅程's 建議下一步 place holds the save card instead (#496).
                self.assertEqual(html.count('<div class="result-next">'), 1)
                self.assertIn('<h2 class="result-next-title">註冊保存這次結果</h2>', html)
                for name in ("share_report", "health_report", "my_hearing"):
                    self.assertNotIn(f'href="{reverse(name)}', html)
                self.assertNotIn("SSQ12-TW", html)


class RecordPageUnchangedTests(ResultFromAnswersTestCase):
    """The signed-in result page draws the same section from the record, with what an account has.
    The queries are main's before #494, measured with these records (its HTML was compared byte
    for byte with main's on HHIE-S and HHIA-S records of each level and hearing aid status)."""

    def test_queries_and_the_account_parts(self):
        self.client.force_login(self.user)
        for code in LEVELS:
            for wearing, queries in ((False, 16), (True, 16), (None, 15)):
                with self.subTest(code=code, wearing=wearing):
                    submission_with_answers(self.user, code, [0] * 10, wearing_hearing_aid=wearing)
                    record = submission_with_answers(
                        self.user, code, [4] * 10, wearing_hearing_aid=wearing
                    )
                    with self.assertNumQueries(queries):
                        response = self.client.get(reverse("result", args=[record.pk]))
                    self.assertContains(response, '<div class="result-next">')
                    self.assertContains(response, f'href="{reverse("share_report")}"')
                    self.assertContains(response, f'href="{reverse("health_report")}"')
                    if wearing is not None:
                        self.assertContains(response, '<div class="result-since-last">')
