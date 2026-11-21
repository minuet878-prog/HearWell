"""#461 (spec #453 acceptance 23-26): a graded result against the record just before it."""

import datetime
import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
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
            {
                "label": "比上次少 4 分",
                "text": "上次 2026/03/26 是 18 分",
                "level_change": None,
                # #750's two bars: 18 and 14 of 40.
                "previous_total": 18,
                "previous_width": 45.0,
                "width": 35.0,
            },
        )

    def test_a_higher_score_says_how_many_more(self):
        self.hhie_s(10, (2026, 3, 26))
        latest = self.hhie_s(14, (2026, 11, 12))
        self.assertEqual(
            (latest.result.since_last["label"], latest.result.since_last["text"]),
            ("比上次多 4 分", "上次 2026/03/26 是 10 分"),
        )

    def test_the_same_score_says_it_is_the_same(self):
        # The draft sentence of the #460 mockup.
        self.hhie_s(12, (2026, 5, 20))
        latest = self.hhie_s(12, (2026, 11, 12))
        self.assertEqual(
            (latest.result.since_last["label"], latest.result.since_last["text"]),
            ("跟上次一樣", "上次 2026/05/20 也是 12 分"),
        )

    def test_a_changed_level_is_written_out(self):
        # Acceptance 23-24: 10 is 輕度到中度影響, 6 is 無／極輕微影響 (the threshold is 8).
        self.hhie_s(10, (2026, 3, 26))
        latest = self.hhie_s(6, (2026, 11, 12))
        self.assertEqual(
            latest.result.since_last,
            {
                "label": "比上次少 4 分",
                "text": "上次 2026/03/26 是 10 分",
                "level_change": "分級從「輕度到中度影響」變成「無／極輕微影響」",
                "previous_total": 10,
                "previous_width": 25.0,
                "width": 15.0,
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
        self.assertEqual(
            (old.result.since_last["label"], old.result.since_last["text"]),
            ("比上次少 4 分", "上次 2026/01/05 是 20 分"),
        )

    def test_records_at_the_same_moment_are_ordered_by_id(self):
        first = self.hhie_s(18, (2026, 3, 26))
        second = self.hhie_s(14, (2026, 3, 26))
        self.assertIsNone(first.result.since_last)
        self.assertEqual(
            (second.result.since_last["label"], second.result.since_last["text"]),
            ("比上次少 4 分", "上次 2026/03/26 是 18 分"),
        )

    def test_the_day_is_the_taipei_day(self):
        # 2026/03/26 00:30 in Taipei is still 03/25 in UTC.
        previous = self.hhie_s(18, (2026, 3, 26))
        moment = datetime.datetime(2026, 3, 26, 0, 30, tzinfo=TAIPEI)
        Submission.objects.filter(pk=previous.pk).update(created_at=moment)
        latest = self.hhie_s(14, (2026, 11, 12))
        self.assertEqual(
            (latest.result.since_last["label"], latest.result.since_last["text"]),
            ("比上次少 4 分", "上次 2026/03/26 是 18 分"),
        )

    def test_thi_is_compared_too(self):
        # THI is graded (five levels): 48 is 中度障礙, 42 is 中度障礙 as well (39-56).
        self.record("thi", [2] * 24 + [0], (2026, 8, 10), wearing_hearing_aid=False)
        latest = self.record("thi", [2] * 21 + [0] * 4, (2026, 11, 12), wearing_hearing_aid=False)
        self.assertEqual(
            latest.result.since_last,
            {
                "label": "比上次少 6 分",
                "text": "上次 2026/08/10 是 48 分",
                "level_change": None,
                # Of THI's 100.
                "previous_total": 48,
                "previous_width": 48.0,
                "width": 42.0,
            },
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
        self.assertEqual(
            (latest.result.since_last["label"], latest.result.since_last["text"]),
            ("比上次少 2 分", "上次 2026/06/01 是 8 分"),
        )

    def test_an_old_record_is_compared_with_the_one_before_it_worn_the_same_way(self):
        self.hhie_s(12, (2026, 1, 5), wearing=True)
        self.hhie_s(18, (2026, 3, 26), wearing=False)
        old = self.hhie_s(8, (2026, 6, 1), wearing=True)
        self.hhie_s(6, (2026, 11, 12), wearing=True)
        self.assertEqual(
            (old.result.since_last["label"], old.result.since_last["text"]),
            ("比上次少 4 分", "上次 2026/01/05 是 12 分"),
        )

    def test_without_a_hearing_aid_status_there_is_no_comparison(self):
        # As 我的紀錄 (Submission.previous_same_wearing): a record from before the question has
        # no comparison, and is never the one compared with.
        self.hhie_s(18, (2026, 3, 26), wearing=None)
        unknown = self.hhie_s(14, (2026, 6, 1), wearing=None)
        self.assertIsNone(unknown.result.since_last)
        latest = self.hhie_s(10, (2026, 11, 12), wearing=False)
        self.assertIsNone(latest.result.since_last)


class ChangeLabelOnTheResultPageTests(TestCase):
    """#646 (spec #644 H2, the #645 mockup's A): the label at the top of the result box's line
    against last time, the sentence under it shortened; which record is compared is unchanged."""

    fixtures = SinceLastTests.fixtures
    setUpTestData = SinceLastTests.setUpTestData
    setUp = SinceLastTests.setUp
    record = SinceLastTests.record
    hhie_s = SinceLastTests.hhie_s

    def since_last_lines(self, submission):
        # The result box's 跟上次比 part as a screen reader reads it, paragraph by paragraph,
        # with each paragraph's own markup; None when the page has no such part.
        self.client.force_login(self.user)
        page = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        part = re.search(r'<div class="result-since-last">(.*?)</div>', page, re.S)
        if part is None:
            return None
        return re.findall(r"(<p[^>]*>)(.*?)</p>", part.group(1), re.S)

    def assert_lines(self, submission, *expected):
        lines = self.since_last_lines(submission)
        self.assertEqual([words for _, words in lines], list(expected))
        # The label is its own paragraph, first, plain words: no icon, nothing hidden from a
        # screen reader, no level colour (acceptance 7, 9).
        self.assertEqual(lines[0][0], '<p class="change-label">')
        return lines

    def test_more_says_the_label_then_the_last_day_and_score(self):
        # Acceptance 1 (and 3: 0 is 無／極輕微影響, 12 輕度到中度影響).
        self.hhie_s(0, (2026, 9, 1))
        latest = self.hhie_s(12, (2026, 9, 11))
        self.assert_lines(
            latest,
            "比上次多 12 分",
            "上次 2026/09/01 是 0 分",
            "分級從「無／極輕微影響」變成「輕度到中度影響」",
        )

    def test_fewer_and_the_same(self):
        # Acceptance 2.
        self.hhie_s(18, (2026, 3, 26))
        fewer = self.hhie_s(14, (2026, 9, 1))
        self.assert_lines(fewer, "比上次少 4 分", "上次 2026/03/26 是 18 分")
        same = self.hhie_s(14, (2026, 9, 11))
        self.assert_lines(same, "跟上次一樣", "上次 2026/09/01 也是 14 分")

    def test_a_changed_level_stays_under_the_sentence(self):
        # Acceptance 3: 10 is 輕度到中度影響, 6 is 無／極輕微影響.
        self.hhie_s(10, (2026, 3, 26))
        latest = self.hhie_s(6, (2026, 11, 12))
        self.assert_lines(
            latest,
            "比上次少 4 分",
            "上次 2026/03/26 是 10 分",
            "分級從「輕度到中度影響」變成「無／極輕微影響」",
        )

    def test_thi_has_the_label_too(self):
        self.record("thi", [2] * 24 + [0], (2026, 8, 10), wearing_hearing_aid=False)
        latest = self.record("thi", [2] * 21 + [0] * 4, (2026, 11, 12), wearing_hearing_aid=False)
        self.assert_lines(latest, "比上次少 6 分", "上次 2026/08/10 是 48 分")

    def test_nothing_to_compare_has_no_label_and_no_sentence(self):
        # Acceptance 4: the first record, one without a hearing aid status, one worn otherwise
        # and one that cannot be graded (a guest's: test_result_from_answers, NoAccountTests).
        first = self.hhie_s(18, (2026, 3, 26))
        unrecorded = self.hhie_s(14, (2026, 4, 1), wearing=None)
        worn = self.hhie_s(10, (2026, 5, 1), wearing=True)
        out_of_range = self.record("hhie-s", [10] * 10, (2026, 6, 1), wearing_hearing_aid=False)
        after_it = self.hhie_s(12, (2026, 7, 1))
        for record in (first, unrecorded, worn, out_of_range, after_it):
            with self.subTest(record=record.pk):
                self.assertIsNone(self.since_last_lines(record))
                page = self.client.get(reverse("result", args=[record.pk])).content.decode()
                self.assertNotIn("change-label", page)
                self.assertNotIn("比上次", page)

    def test_the_label_has_no_arrow_and_no_verdict(self):
        # Acceptance 7, ADR 0017: words only.
        self.hhie_s(0, (2026, 9, 1))
        latest = self.hhie_s(12, (2026, 9, 11))
        label = self.since_last_lines(latest)[0][1]
        for sign in ("↑", "↓", "▲", "▼", "⬆", "⬇", "<svg", "進步", "退步", "變好", "變差"):
            self.assertNotIn(sign, label)
