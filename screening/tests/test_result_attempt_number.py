"""#647 (spec #644 H3, acceptance 11-17): which time this is, under every result page's header."""

import datetime
import json
import re
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import NormGroup, Questionnaire, Submission
from screening.questionnaires import hhie_s
from screening.tests.helpers import consented_user, submission_with_answers

TAIPEI = timezone.get_fixed_timezone(8 * 60)
# A valid score for every item of each questionnaire, and how many items it has.
QUESTIONNAIRES = {
    "hhie-s": (2, 10),
    "hhia-s": (2, 10),
    "thi": (2, 25),
    "ssq12-tw": (6, 12),
    "sadl": (4, 15),
    "ioi-ha": (3, 7),
}
ALWAYS_AIDED = ("ioi-ha", "sadl")
# The header: the title, the line under it (questionnaire, date, wearing), then the paragraph after
# it, the header's last.
HEADER = re.compile(r"<h1[^>]*>[^<]*</h1>\s*<p[^>]*>[^<]*</p>\s*<p[^>]*>([^<]*)</p>(?!\s*<p[\s>])")
FIRST = "這是您第 1 次做這份問卷。"


class AttemptNumberTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())

    def setUp(self):
        self.user = consented_user(username="attempt_number_user")
        self.client.force_login(self.user)

    def record(self, code, day, wearing=False):
        score, items = QUESTIONNAIRES[code]
        # IOI-HA's norm group is fixed when it is submitted; "" is only for the others.
        norm_group = NormGroup.UNGROUPED if code == "ioi-ha" else ""
        submission = submission_with_answers(
            self.user, code, [score] * items, wearing_hearing_aid=wearing, norm_group=norm_group
        )
        moment = datetime.datetime(*day, 10, 0, tzinfo=TAIPEI)
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def page(self, submission):
        return self.client.get(reverse("result", args=[submission.pk]))

    def header(self, submission):
        html = self.page(submission).content.decode()
        return HEADER.search(html[html.index("<main") : html.index("</main>")])

    def line(self, submission):
        return self.header(submission).group(1)

    def test_worn_and_not_worn_records_are_counted_together(self):
        # Acceptance 11-12; a record from before the hearing aid question (None) counts too.
        first = self.record("hhie-s", (2026, 3, 1), wearing=None)
        second = self.record("hhie-s", (2026, 6, 1), wearing=True)
        latest = self.record("hhie-s", (2026, 9, 11), wearing=False)
        self.assertEqual(self.line(latest), "這是您第 3 次做這份問卷。")
        self.assertEqual(self.line(second), "這是您第 2 次做這份問卷。")
        self.assertEqual(self.line(first), FIRST)

    def test_the_first_time_says_so_and_nothing_about_doing_it_again(self):
        # Acceptance 13: no 「半年後再做」 or the like.
        header = self.header(self.record("hhie-s", (2026, 9, 11)))
        self.assertEqual(header.group(1), FIRST)
        self.assertNotIn("再做", header.group(0))

    def test_each_questionnaire_counts_its_own(self):
        # Acceptance 14: THI between the HHIE-S records is not counted in HHIE-S, nor they in THI.
        self.record("hhie-s", (2026, 3, 1))
        thi = self.record("thi", (2026, 4, 1))
        latest = self.record("hhie-s", (2026, 9, 11))
        self.assertEqual(self.line(latest), "這是您第 2 次做這份問卷。")
        self.assertEqual(self.line(thi), FIRST)

    def test_another_user_s_records_are_not_counted(self):
        other = consented_user(username="attempt_number_other")
        submission_with_answers(other, "hhie-s", [2] * 10, wearing_hearing_aid=False)
        self.assertEqual(self.line(self.record("hhie-s", (2026, 9, 11))), FIRST)

    def test_every_result_page_has_it(self):
        # Acceptance 15: the six questionnaires' result pages share the header.
        for code in QUESTIONNAIRES:
            with self.subTest(code=code):
                wearing = code in ALWAYS_AIDED
                self.record(code, (2026, 3, 1), wearing=wearing)
                latest = self.record(code, (2026, 9, 11), wearing=wearing)
                self.assertEqual(self.line(latest), "這是您第 2 次做這份問卷。")

    def test_records_at_the_same_moment_are_ordered_by_id_as_since_last_orders_them(self):
        # Acceptance 17: the order 「跟上次比」 uses: at the same moment, the lower id first.
        first = self.record("hhie-s", (2026, 3, 26))
        second = self.record("hhie-s", (2026, 3, 26))
        self.assertEqual(self.line(first), FIRST)
        self.assertEqual(self.line(second), "這是您第 2 次做這份問卷。")
        self.assertIsNone(Submission.objects.get(pk=first.pk).result.since_last)
        self.assertIsNotNone(Submission.objects.get(pk=second.pk).result.since_last)

    def test_one_query_counts_them_however_many_there_are(self):
        # CODING_STANDARDS 15: counted in the database, so one record or three, the same queries.
        oldest = self.record("hhie-s", (2026, 1, 1))
        self.page(oldest)  # the session and the questionnaire definitions loaded once
        with CaptureQueriesContext(connection) as one:
            self.page(oldest)
        self.record("hhie-s", (2026, 2, 1))
        latest = self.record("hhie-s", (2026, 3, 1))
        with self.assertNumQueries(len(one)):
            self.assertEqual(self.line(latest), "這是您第 3 次做這份問卷。")


class GuestAttemptNumberTests(TestCase):
    fixtures = ("questions_fixture.json",)

    def test_a_guest_s_result_does_not_say_which_time(self):
        # Acceptance 16: a guest has no records, so no 「第 1 次」 to suggest one was kept.
        page = self.client.get(reverse("guest_result", args=[hhie_s.CODE]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "次做這份問卷")
        questionnaire = Questionnaire.objects.get(code=hhie_s.CODE)
        body = {
            "questionnaire": questionnaire.pk,
            "wearing_hearing_aid": False,
            "answers": [
                {"question": question.pk, "score": 2}
                for question in questionnaire.questions.order_by("question_number")
            ],
            "just_finished": True,
        }
        section = self.client.post(
            "/api/guest-scores/", json.dumps(body), content_type="application/json"
        )
        self.assertEqual(section.status_code, 200)
        self.assertNotIn("次做這份問卷", section.json()["html"])
