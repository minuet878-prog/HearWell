import re
from datetime import date, datetime, timedelta
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import QuestionLog, QuestionLogMonth, User, purge_question_log

TAIPEI = ZoneInfo("Asia/Taipei")
# A fixed present, so nothing depends on when the tests run.
NOW = datetime(2026, 11, 15, 10, 0, tzinfo=TAIPEI)


def at_now():
    return patch("django.utils.timezone.now", return_value=NOW)


def log(days_ago, faq_code="", reason="", **delta):
    entry = QuestionLog.objects.create(question="舊的問句", faq_code=faq_code, reason=reason)
    created_at = NOW - timedelta(days=days_ago, **delta)
    QuestionLog.objects.filter(pk=entry.pk).update(created_at=created_at)
    return entry


def stats():
    return list(
        QuestionLogMonth.objects.order_by("month").values_list(
            "month", "typed", "matched", "different_wording", "not_in_faq", "should_not_answer"
        )
    )


class PurgeOnNewQuestionTests(TestCase):
    """#401 acceptance 1: saving a new question purges those over 90 days into the month stats."""

    def test_typing_a_question_purges_the_old_ones_into_their_month(self):
        # 2026/08/01 is 106 days before NOW; 2026/08/10 is 97.
        log(106, faq_code="hearing-aid-subsidy")
        log(97, reason="not_in_faq")
        kept = log(10)
        with at_now():
            self.client.post(reverse("qa_search"), {"question": "耳機補助怎麼申請"})
        self.assertEqual(
            list(QuestionLog.objects.order_by("pk").values_list("question", flat=True)),
            [kept.question, "耳機補助怎麼申請"],
        )
        self.assertEqual(stats(), [(date(2026, 8, 1), 2, 1, 0, 1, 0)])


class PurgeTests(TestCase):
    """#401: what the shared purge counts, and acceptance 4, a question is counted once."""

    def purge(self):
        with at_now():
            return purge_question_log()

    def test_exactly_90_days_old_is_kept_one_second_more_is_purged(self):
        kept = log(90)
        log(90, seconds=1)
        self.assertEqual(self.purge(), 1)
        self.assertEqual(list(QuestionLog.objects.all()), [kept])

    def test_a_question_counts_in_its_taipei_month(self):
        # 2026/08/01 00:30 in Taipei is still 07/31 in UTC.
        entry = QuestionLog.objects.create(question="舊的問句")
        QuestionLog.objects.filter(pk=entry.pk).update(
            created_at=datetime(2026, 8, 1, 0, 30, tzinfo=TAIPEI)
        )
        log(120)  # 2026/07/18
        self.purge()
        self.assertEqual(
            stats(), [(date(2026, 7, 1), 1, 0, 0, 0, 0), (date(2026, 8, 1), 1, 0, 0, 0, 0)]
        )

    def test_each_reason_and_the_matched_ones_are_counted(self):
        log(100, faq_code="hearing-aid-subsidy")
        log(100, faq_code="hearing-aid-subsidy")
        log(100, reason="different_wording")
        log(100, reason="different_wording")
        log(100, reason="not_in_faq")
        log(100, reason="should_not_answer")
        log(100)  # matched nothing, no reason ticked yet
        self.purge()
        self.assertEqual(stats(), [(date(2026, 8, 1), 7, 2, 2, 1, 1)])

    def test_purging_again_counts_nothing_twice(self):
        log(100)
        self.assertEqual(self.purge(), 1)
        self.assertEqual(self.purge(), 0)
        self.assertEqual(stats(), [(date(2026, 8, 1), 1, 0, 0, 0, 0)])

    def test_a_later_purge_adds_to_the_month_already_counted(self):
        # The second question turns 90 days old after the first purge.
        log(100, reason="not_in_faq")
        self.purge()
        log(91, faq_code="hearing-aid-subsidy")
        self.purge()
        self.assertEqual(stats(), [(date(2026, 8, 1), 2, 1, 0, 1, 0)])
        self.assertFalse(QuestionLog.objects.exists())

    def test_the_month_stats_keep_no_question(self):
        fields = {field.name for field in QuestionLogMonth._meta.get_fields()}
        self.assertEqual(
            fields,
            {
                "id",
                "month",
                "typed",
                "matched",
                "different_wording",
                "not_in_faq",
                "should_not_answer",
            },
        )


class PurgeOnAdminListTests(TestCase):
    """#401 acceptance 2: opening the question log in the admin purges first."""

    def test_the_list_never_shows_a_question_over_90_days(self):
        old = QuestionLog.objects.create(question="九十天前的問句")
        QuestionLog.objects.filter(pk=old.pk).update(created_at=NOW - timedelta(days=100))
        QuestionLog.objects.create(question="上週的問句")
        with at_now():  # also when the session expires
            self.client.force_login(User.objects.create_superuser(username="owner", password="pw"))
            response = self.client.get(reverse("admin:screening_questionlog_changelist"))
        self.assertContains(response, "上週的問句")
        self.assertNotContains(response, "九十天前的問句")
        self.assertFalse(QuestionLog.objects.filter(pk=old.pk).exists())
        self.assertEqual(stats(), [(date(2026, 8, 1), 1, 0, 0, 0, 0)])


class PurgeOnDeployTests(TestCase):
    """#401 acceptance 3: the deploy runs a command that purges the same way."""

    def test_the_command_purges_into_the_month_stats(self):
        log(100, faq_code="hearing-aid-subsidy")
        kept = log(10)
        out = StringIO()
        with at_now():
            call_command("purge_question_log", stdout=out)
        self.assertEqual(list(QuestionLog.objects.all()), [kept])
        self.assertEqual(stats(), [(date(2026, 8, 1), 1, 1, 0, 0, 0)])
        self.assertEqual(out.getvalue(), "Purged 1 question(s) older than 90 days.\n")


class MonthStatsAdminTests(TestCase):
    """#401 acceptance 5: the owner reads each month's counts and cannot change them."""

    def setUp(self):
        self.client.force_login(User.objects.create_superuser(username="owner", password="pw"))
        self.august = QuestionLogMonth.objects.create(
            month=date(2026, 8, 1),
            typed=61,
            matched=37,
            different_wording=13,
            not_in_faq=8,
            should_not_answer=3,
        )
        QuestionLogMonth.objects.create(month=date(2026, 7, 1), typed=52)
        QuestionLogMonth.objects.create(month=date(2026, 9, 1), typed=48)

    def test_each_month_and_its_counts_newest_first(self):
        response = self.client.get(reverse("admin:screening_questionlogmonth_changelist"))
        page = response.content.decode()
        months = re.findall(r'<th class="field-month_label"><a [^>]*>([^<]+)</a></th>', page)
        self.assertEqual(months, ["2026/09", "2026/08", "2026/07"])
        for heading in ("月份", "打字提問數", "對到數", "問法不同", "題庫沒有", "不該回答"):
            with self.subTest(heading=heading):
                self.assertIn(heading, page)
        august = page[page.index(">2026/08<") : page.index(">2026/07<")]
        cells = re.findall(r'<td class="field-(\w+)">(\d+)</td>', august)
        self.assertEqual(
            cells,
            [
                ("typed", "61"),
                ("matched", "37"),
                ("different_wording", "13"),
                ("not_in_faq", "8"),
                ("should_not_answer", "3"),
            ],
        )

    def test_read_only(self):
        data = {"month": "2026-08-01", "typed": 0, "matched": 0}
        add = reverse("admin:screening_questionlogmonth_add")
        change = reverse("admin:screening_questionlogmonth_change", args=[self.august.pk])
        delete = reverse("admin:screening_questionlogmonth_delete", args=[self.august.pk])
        self.assertEqual(self.client.get(change).status_code, 200)
        self.assertEqual(self.client.get(add).status_code, 403)
        self.assertEqual(self.client.post(add, data).status_code, 403)
        self.assertEqual(self.client.post(change, data).status_code, 403)
        self.assertEqual(self.client.post(delete, {"post": "yes"}).status_code, 403)
        self.assertEqual(QuestionLogMonth.objects.get(pk=self.august.pk).typed, 61)
        self.assertEqual(QuestionLogMonth.objects.count(), 3)
