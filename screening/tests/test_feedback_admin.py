import re
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.admin.models import LogEntry
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.models import Feedback, User, purge_feedback
from screening.tests import test_layout

TAIPEI = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 11, 16, 10, 0, tzinfo=TAIPEI)


def at_now():
    return patch("django.utils.timezone.now", return_value=NOW)


def kept(text, days_ago=0, **fields):
    feedback = Feedback.objects.create(text=text, **fields)
    Feedback.objects.filter(pk=feedback.pk).update(created_at=NOW - timedelta(days=days_ago))
    return Feedback.objects.get(pk=feedback.pk)


class FeedbackAdminTests(TestCase):
    """Spec #633 (#639, acceptance 37-40): the owner reads each 意見回饋, ticks it handled and
    deletes one early; what was sent stays as it was."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(username="feedback_admin", password="pw")
        cls.oldest = kept("字太小了看不清楚", days_ago=3, page="結果頁")
        cls.handled = kept("謝謝你們", days_ago=2, handled=True)
        cls.newest = kept("報告印不出來", days_ago=1, email="wang@example.com", page="聽力報告")

    def setUp(self):
        self.client.force_login(self.admin)
        self.changelist = reverse("admin:screening_feedback_changelist")

    def change_url(self, feedback):
        return reverse("admin:screening_feedback_change", args=[feedback.pk])

    def rows(self, query=""):
        """{the words' start: the row's text}, in the order listed."""
        with at_now():
            page = self.client.get(self.changelist + query).content.decode()
        body = page[page.index("<tbody>") : page.index("</tbody>")]
        return {
            row.group(1): test_layout._text(row.group(0))
            for row in re.finditer(r"<tr>.*?<a href=\"[^\"]+\">([^<]+)</a>.*?</tr>", body, re.S)
        }

    def test_the_list_shows_when_where_handled_the_words_and_the_email(self):
        with at_now():
            response = self.client.get(self.changelist)
        self.assertEqual(response.status_code, 200)
        headers = re.findall(r'<th scope="col" class="[^"]*column-(\w+)', response.content.decode())
        self.assertEqual(headers, ["created_at", "page", "handled", "start", "email"])
        rows = self.rows()
        self.assertIn("聽力報告", rows["報告印不出來"])
        self.assertIn("wang@example.com", rows["報告印不出來"])
        self.assertIn("2026", rows["報告印不出來"])

    def test_a_long_one_shows_its_start(self):
        kept("耳" * 60)
        self.assertIn("耳" * 30 + "…", self.rows())

    def test_the_newest_come_first(self):
        self.assertEqual(list(self.rows()), ["報告印不出來", "謝謝你們", "字太小了看不清楚"])

    def test_only_those_not_handled_and_by_email(self):
        self.assertEqual(list(self.rows("?handled__exact=0")), ["報告印不出來", "字太小了看不清楚"])
        self.assertEqual(list(self.rows("?q=wang%40example.com")), ["報告印不出來"])

    def test_only_handled_can_change(self):
        with at_now():
            form = self.client.get(self.change_url(self.oldest)).content.decode()
        self.assertIn('name="handled"', form)
        for field in ("text", "email", "page", "created_at"):
            with self.subTest(field=field):
                self.assertNotIn(f'name="{field}"', form)
        self.assertIn("字太小了看不清楚", form)
        with at_now():
            response = self.client.post(
                self.change_url(self.oldest),
                {"handled": "on", "text": "改過的", "email": "x@example.com", "page": "首頁"},
            )
        self.assertRedirects(response, self.changelist)
        feedback = Feedback.objects.get(pk=self.oldest.pk)
        self.assertTrue(feedback.handled)
        self.assertEqual(
            (feedback.text, feedback.email, feedback.page), ("字太小了看不清楚", "", "結果頁")
        )

    def test_nothing_can_be_added(self):
        add = reverse("admin:screening_feedback_add")
        self.assertEqual(self.client.get(add).status_code, 403)
        self.assertEqual(self.client.post(add, {"text": "假的"}).status_code, 403)
        self.assertEqual(Feedback.objects.count(), 3)

    def test_one_or_the_selected_can_be_deleted_early(self):
        delete = reverse("admin:screening_feedback_delete", args=[self.oldest.pk])
        with at_now():
            self.assertRedirects(self.client.post(delete, {"post": "yes"}), self.changelist)
            self.client.post(
                self.changelist,
                {
                    "action": "delete_selected",
                    "_selected_action": [self.handled.pk],
                    "post": "yes",
                },
            )
        self.assertEqual(list(Feedback.objects.values_list("text", flat=True)), ["報告印不出來"])

    def test_the_history_keeps_no_words_or_email(self):
        with at_now():
            self.client.post(self.change_url(self.newest), {"handled": "on"})
            delete = reverse("admin:screening_feedback_delete", args=[self.newest.pk])
            self.client.post(delete, {"post": "yes"})
        history = " ".join(
            f"{entry.object_repr} {entry.change_message}" for entry in LogEntry.objects.all()
        )
        self.assertTrue(history.strip())
        self.assertNotIn("報告印不出來", history)
        self.assertNotIn("wang@example.com", history)


class FeedbackAdminQueryTests(TestCase):
    """CODING_STANDARDS 15: feedback grows each day, its list takes the same queries."""

    def test_two_or_many_take_the_same_queries(self):
        self.client.force_login(User.objects.create_superuser(username="feedback_owner"))
        changelist = reverse("admin:screening_feedback_changelist")
        Feedback.objects.bulk_create(Feedback(text=f"意見 {n}") for n in range(2))
        self.client.get(changelist)  # the first request also looks up what the admin caches
        with CaptureQueriesContext(connection) as two:
            self.assertEqual(self.client.get(changelist).status_code, 200)
        Feedback.objects.bulk_create(
            Feedback(text=f"多的意見 {n}", email=f"m{n}@example.com", page="結果頁", handled=n % 2)
            for n in range(20)
        )
        with self.assertNumQueries(len(two)):
            self.assertEqual(self.client.get(changelist).status_code, 200)


class FeedbackPurgeTests(TestCase):
    """Spec #633 (#639, acceptance 41-42): each 意見回饋 is kept 90 days (ADR 0064)."""

    def test_exactly_90_days_old_is_kept_one_second_more_is_purged(self):
        stays = kept("剛好 90 天", days_ago=90)
        Feedback.objects.filter(pk=kept("多一秒").pk).update(
            created_at=NOW - timedelta(days=90, seconds=1)
        )
        with at_now():
            self.assertEqual(purge_feedback(), 1)
        self.assertEqual(list(Feedback.objects.all()), [stays])

    def test_the_command_purges_and_says_how_many(self):
        kept("舊的", days_ago=100)
        stays = kept("新的", days_ago=10)
        out = StringIO()
        with at_now():
            call_command("purge_feedback", stdout=out)
        self.assertEqual(list(Feedback.objects.all()), [stays])
        self.assertEqual(out.getvalue(), "Purged 1 feedback older than 90 days.\n")

    def test_the_admin_list_never_shows_one_over_90_days(self):
        kept("舊的", days_ago=91)
        stays = kept("新的", days_ago=1)
        self.client.force_login(User.objects.create_superuser(username="feedback_purge"))
        with at_now():
            response = self.client.get(reverse("admin:screening_feedback_changelist"))
        self.assertNotContains(response, "舊的")
        self.assertEqual(list(Feedback.objects.all()), [stays])


class FeedbackPurgePermissionTests(TestCase):
    """Cross review of spec #633 (S1, CODING_STANDARDS 1): opening the list purges only for one
    who may see it; staff without the permission are refused and delete nothing."""

    def test_staff_without_the_permission_purge_nothing(self):
        old = kept("舊的", days_ago=91)
        self.client.force_login(User.objects.create_user("feedback_staff", is_staff=True))
        with at_now():
            response = self.client.get(reverse("admin:screening_feedback_changelist"))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Feedback.objects.filter(pk=old.pk).exists())
