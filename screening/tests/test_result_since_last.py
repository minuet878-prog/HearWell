"""#461 (spec #453 acceptance 23-26): a graded result against the record just before it."""

import datetime
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from screening.models import Question, Submission
from screening.tests.helpers import consented_user, submission_with_answers

TAIPEI = timezone.get_fixed_timezone(8 * 60)


def hhie_s_scores(total):
    """Ten HHIE-S answers (4, 2 or 0) adding up to total."""
    scores = [4] * (total // 4) + [2] * (total % 4 // 2)
    return scores + [0] * (10 - len(scores))


class SinceLastTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())

    def setUp(self):
        self.user = consented_user(username="since_last_user")

    def record(self, code, scores, day, **fields):
        submission = submission_with_answers(self.user, code, scores, **fields)
        moment = datetime.datetime(*day, 10, 0, tzinfo=TAIPEI)
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        # Fresh from the database: the result and its scores are cached (AGENTS.md).
        return Submission.objects.get(pk=submission.pk)

    def hhie_s(self, total, day, wearing=False):
        return self.record("hhie-s", hhie_s_scores(total), day, wearing_hearing_aid=wearing)

    def test_a_lower_score_says_the_last_day_and_score_and_how_many_fewer(self):
        # Acceptance 23: numbers only, no 進步 or 退步.
        self.hhie_s(18, (2026, 3, 26))
        latest = self.hhie_s(14, (2026, 11, 12))
        self.assertEqual(
            latest.result.since_last,
            {"text": "上次 2026/03/26 是 18 分，這次少 4 分", "level_change": None},
        )

    def test_a_higher_score_says_how_many_more(self):
        self.hhie_s(10, (2026, 3, 26))
        latest = self.hhie_s(14, (2026, 11, 12))
        self.assertEqual(latest.result.since_last["text"], "上次 2026/03/26 是 10 分，這次多 4 分")

    def test_the_same_score_says_it_is_the_same(self):
        # The draft sentence of the #460 mockup.
        self.hhie_s(12, (2026, 5, 20))
        latest = self.hhie_s(12, (2026, 11, 12))
        self.assertEqual(latest.result.since_last["text"], "上次 2026/05/20 也是 12 分，這次一樣")

    def test_a_changed_level_is_written_out(self):
        # Acceptance 23-24: 10 is 輕度到中度影響, 6 is 無／極輕微影響 (the threshold is 8).
        self.hhie_s(10, (2026, 3, 26))
        latest = self.hhie_s(6, (2026, 11, 12))
        self.assertEqual(
            latest.result.since_last,
            {
                "text": "上次 2026/03/26 是 10 分，這次少 4 分",
                "level_change": "分級從「輕度到中度影響」變成「無／極輕微影響」",
            },
        )

    def test_the_first_record_has_no_comparison(self):
        # Acceptance 25.
        self.assertIsNone(self.hhie_s(14, (2026, 11, 12)).result.since_last)

    def test_only_the_same_questionnaire_is_compared(self):
        self.record("hhia-s", hhie_s_scores(18), (2026, 3, 26), wearing_hearing_aid=False)
        self.assertIsNone(self.hhie_s(14, (2026, 11, 12)).result.since_last)

    def test_another_user_s_record_is_never_compared(self):
        mine = self.user
        self.user = consented_user(username="someone_else")
        self.hhie_s(18, (2026, 3, 26))
        self.user = mine
        self.assertIsNone(self.hhie_s(14, (2026, 11, 12)).result.since_last)

    def test_an_old_record_is_compared_with_the_one_before_it_not_the_newest(self):
        # Acceptance 26.
        self.hhie_s(20, (2026, 1, 5))
        old = self.hhie_s(16, (2026, 3, 26))
        self.hhie_s(4, (2026, 11, 12))
        self.assertEqual(old.result.since_last["text"], "上次 2026/01/05 是 20 分，這次少 4 分")

    def test_records_at_the_same_moment_are_ordered_by_id(self):
        first = self.hhie_s(18, (2026, 3, 26))
        second = self.hhie_s(14, (2026, 3, 26))
        self.assertIsNone(first.result.since_last)
        self.assertEqual(second.result.since_last["text"], "上次 2026/03/26 是 18 分，這次少 4 分")

    def test_the_day_is_the_taipei_day(self):
        # 2026/03/26 00:30 in Taipei is still 03/25 in UTC.
        previous = self.hhie_s(18, (2026, 3, 26))
        moment = datetime.datetime(2026, 3, 26, 0, 30, tzinfo=TAIPEI)
        Submission.objects.filter(pk=previous.pk).update(created_at=moment)
        latest = self.hhie_s(14, (2026, 11, 12))
        self.assertEqual(latest.result.since_last["text"], "上次 2026/03/26 是 18 分，這次少 4 分")

    def test_thi_is_compared_too(self):
        # THI is graded (five levels): 48 is 中度障礙, 42 is 中度障礙 as well (39-56).
        self.record("thi", [2] * 24 + [0], (2026, 8, 10), wearing_hearing_aid=False)
        latest = self.record("thi", [2] * 21 + [0] * 4, (2026, 11, 12), wearing_hearing_aid=False)
        self.assertEqual(
            latest.result.since_last,
            {"text": "上次 2026/08/10 是 48 分，這次少 6 分", "level_change": None},
        )

    def test_questionnaires_that_are_not_graded_have_no_comparison(self):
        # Acceptance 25: SSQ12-TW, IOI-HA and SADL.
        for code, score in (("ssq12-tw", 6), ("ioi-ha", 3), ("sadl", 4)):
            with self.subTest(code=code):
                scores = [score] * Question.objects.filter(questionnaire__code=code).count()
                self.record(code, scores, (2026, 3, 26), wearing_hearing_aid=True)
                latest = self.record(code, scores, (2026, 11, 12), wearing_hearing_aid=True)
                self.assertIsNone(latest.result.since_last)

    def test_a_record_that_cannot_be_graded_has_no_comparison(self):
        # 無法判讀 (an out-of-range total) may be a data error: no numbers are compared with it.
        self.record("hhie-s", [4] * 10, (2026, 3, 26), wearing_hearing_aid=False)
        out_of_range = self.record("hhie-s", [10] * 10, (2026, 5, 20), wearing_hearing_aid=False)
        latest = self.hhie_s(14, (2026, 11, 12))
        self.assertIsNone(out_of_range.result.since_last)
        self.assertIsNone(latest.result.since_last)

    # The owner on #461 (2026-11-12): only against the last record worn the same way, as
    # 我的紀錄's 「和上一次比」; worn against not worn is the wearing comparison's.
    def test_a_record_worn_otherwise_is_not_compared(self):
        self.hhie_s(18, (2026, 3, 26), wearing=False)
        aided = self.hhie_s(8, (2026, 6, 1), wearing=True)
        self.assertIsNone(aided.result.since_last)

    def test_records_worn_otherwise_in_between_are_skipped(self):
        self.hhie_s(18, (2026, 3, 26), wearing=False)
        self.hhie_s(8, (2026, 6, 1), wearing=True)
        self.hhie_s(20, (2026, 8, 1), wearing=False)
        latest = self.hhie_s(6, (2026, 11, 12), wearing=True)
        self.assertEqual(latest.result.since_last["text"], "上次 2026/06/01 是 8 分，這次少 2 分")

    def test_an_old_record_is_compared_with_the_one_before_it_worn_the_same_way(self):
        self.hhie_s(12, (2026, 1, 5), wearing=True)
        self.hhie_s(18, (2026, 3, 26), wearing=False)
        old = self.hhie_s(8, (2026, 6, 1), wearing=True)
        self.hhie_s(6, (2026, 11, 12), wearing=True)
        self.assertEqual(old.result.since_last["text"], "上次 2026/01/05 是 12 分，這次少 4 分")

    def test_without_a_hearing_aid_status_there_is_no_comparison(self):
        # As 我的紀錄 (Submission.previous_same_wearing): a record from before the question has
        # no comparison, and is never the one compared with.
        self.hhie_s(18, (2026, 3, 26), wearing=None)
        unknown = self.hhie_s(14, (2026, 6, 1), wearing=None)
        self.assertIsNone(unknown.result.since_last)
        latest = self.hhie_s(10, (2026, 11, 12), wearing=False)
        self.assertIsNone(latest.result.since_last)
