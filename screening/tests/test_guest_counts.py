"""The guests' monthly counts (ticket #500, spec #492): how many guests finished a questionnaire
each month and how many of those results were saved, nothing else."""

import json
import re
import uuid
from datetime import UTC, date, datetime
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import GuestMonth, Questionnaire, User
from screening.questionnaires import hhie_s
from screening.tests.helpers import consented_user

GUEST_SCORE = "/api/guest-scores/"
SUBMISSIONS = "/api/submissions/"


def counts():
    # 保存 of accounts registered with a password: every one here (the others: #513's tests).
    return list(
        GuestMonth.objects.order_by("month").values_list("month", "completed", "saved_password")
    )


def this_month():
    return timezone.localdate().replace(day=1)


class GuestCountTestCase(TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S, IOI-HA

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())  # HHIA-S and the others
        cls.hhie_s = Questionnaire.objects.get(code=hhie_s.CODE)

    def setUp(self):
        # The guest scoring's rate limit counts in the cache; each test starts with none counted.
        cache.clear()
        self.addCleanup(cache.clear)

    def body(self, scores, **extra):
        questions = self.hhie_s.questions.order_by("question_number")
        return {
            "questionnaire": self.hhie_s.pk,
            "wearing_hearing_aid": False,
            "answers": [
                {"question": question.pk, "score": score}
                for question, score in zip(questions, scores, strict=True)
            ],
            **extra,
        }

    def guest_score(self, body):
        return self.client.post(GUEST_SCORE, json.dumps(body), content_type="application/json")


class CompletedTests(GuestCountTestCase):
    """#492 acceptance 30: a guest finishing one adds one; looking at it again adds none."""

    def test_finishing_one_adds_one_to_this_month(self):
        self.assertEqual(counts(), [])
        response = self.guest_score(self.body([4] * 10, just_finished=True))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(counts(), [(this_month(), 1, 0)])

    def test_the_guest_result_page_sending_it_again_adds_none(self):
        # Opening the guest result page again, or from the home page, sends just_finished false.
        self.guest_score(self.body([4] * 10, just_finished=True))
        for _ in range(2):
            response = self.guest_score(self.body([4] * 10, just_finished=False))
            self.assertEqual(response.status_code, 200)
        self.assertEqual(counts(), [(this_month(), 1, 0)])

    def test_each_finished_one_adds_one(self):
        self.guest_score(self.body([4] * 10, just_finished=True))
        self.guest_score(self.body([0] * 10, just_finished=True))
        self.assertEqual(counts(), [(this_month(), 2, 0)])

    def test_refused_answers_add_none(self):
        response = self.guest_score(self.body([9] * 10, just_finished=True))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(counts(), [])

    def test_the_month_is_taipeis(self):
        # 23:30 on 10/31 in Taipei is October; 00:30 on 11/01 in Taipei is November, though it is
        # still 10/31 in UTC.
        for moment in (
            datetime(2026, 10, 31, 15, 30, tzinfo=UTC),
            datetime(2026, 10, 31, 16, 30, tzinfo=UTC),
        ):
            with (
                self.subTest(moment=moment),
                patch("django.utils.timezone.now", return_value=moment),
            ):
                self.guest_score(self.body([4] * 10, just_finished=True))
        self.assertEqual(counts(), [(date(2026, 10, 1), 1, 0), (date(2026, 11, 1), 1, 0)])


class SavedTests(GuestCountTestCase):
    """#492 acceptance 31: a guest result newly saved adds one; sent again, or an account's own
    answers, add none."""

    def setUp(self):
        super().setUp()
        self.user = consented_user(username="guest_counts")
        self.client.force_login(self.user)

    def save(self, body, key):
        return self.client.post(
            SUBMISSIONS,
            json.dumps(body),
            content_type="application/json",
            headers={"Idempotency-Key": str(key)},
        )

    def test_newly_saved_adds_one_to_this_month(self):
        response = self.save(self.body([4] * 10, from_guest=True), uuid.uuid4())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(counts(), [(this_month(), 0, 1)])

    def test_sent_again_with_its_receipt_number_adds_none(self):
        key = uuid.uuid4()
        body = self.body([4] * 10, from_guest=True)
        self.assertEqual(self.save(body, key).status_code, 201)
        self.assertEqual(self.save(body, key).status_code, 200)
        # The same receipt number with other answers is refused and adds none either.
        other = self.body([0] * 10, from_guest=True)
        self.assertEqual(self.save(other, key).status_code, 409)
        self.assertEqual(counts(), [(this_month(), 0, 1)])

    def test_an_accounts_own_answers_add_none(self):
        # The answer page sends no guest mark; false is the same.
        for body in (self.body([4] * 10), self.body([4] * 10, from_guest=False)):
            with self.subTest(body=body):
                self.assertEqual(self.save(body, uuid.uuid4()).status_code, 201)
        self.assertEqual(counts(), [])

    def test_refused_answers_add_none(self):
        response = self.save(self.body([9] * 10, from_guest=True), uuid.uuid4())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(counts(), [])

    def test_a_guest_finishing_then_saving_counts_once_each(self):
        scores = [4] * 10
        self.client.logout()
        self.guest_score(self.body(scores, just_finished=True))
        self.client.force_login(self.user)
        self.save(self.body(scores, from_guest=True), uuid.uuid4())
        self.assertEqual(counts(), [(this_month(), 1, 1)])


class OnlyTheCountsTests(GuestCountTestCase):
    """#492 acceptance 32 and #500: the month and the numbers (保存 in three since #513), nobody's
    IP, account or answers; the admin can look but not change; not part of anybody's data."""

    PASSWORD = "Fake-pass-1357"

    def test_the_table_has_only_the_month_and_the_counts(self):
        fields = {field.name for field in GuestMonth._meta.get_fields()}
        self.assertEqual(
            fields,
            {"id", "month", "completed", "saved_password", "saved_google", "saved_line"},
        )

    def test_the_admin_lists_each_month_newest_first(self):
        GuestMonth.objects.create(
            month=date(2026, 10, 1), completed=31, saved_password=9, saved_google=5
        )
        GuestMonth.objects.create(month=date(2026, 11, 1), completed=12, saved_password=4)
        self.client.force_login(User.objects.create_superuser(username="owner", password="pw"))
        page = self.client.get(reverse("admin:screening_guestmonth_changelist")).content.decode()
        months = re.findall(r'<th class="field-month_label"><a [^>]*>([^<]+)</a></th>', page)
        self.assertEqual(months, ["2026/11", "2026/10"])
        for heading in ("月份", "訪客完成", "保存（帳號密碼）", "保存（Google）", "保存（LINE）"):
            with self.subTest(heading=heading):
                self.assertIn(heading, page)
        october = page[page.index(">2026/10<") :]
        cells = re.findall(r'<td class="field-(\w+)">(\d+)</td>', october)
        self.assertEqual(
            cells,
            [
                ("completed", "31"),
                ("saved_password", "9"),
                ("saved_google", "5"),
                ("saved_line", "0"),
            ],
        )

    def test_two_or_many_months_take_the_same_queries(self):
        # CODING_STANDARDS 15: a month more each month.
        GuestMonth.objects.create(month=date(2026, 10, 1), completed=31, saved_password=9)
        GuestMonth.objects.create(month=date(2026, 11, 1), completed=12, saved_password=4)
        self.client.force_login(User.objects.create_superuser(username="owner", password="pw"))
        changelist = reverse("admin:screening_guestmonth_changelist")
        self.client.get(changelist)  # the first request also looks up what the admin caches
        with CaptureQueriesContext(connection) as two:
            self.assertEqual(self.client.get(changelist).status_code, 200)
        GuestMonth.objects.bulk_create(
            GuestMonth(month=date(2025, month, 1), completed=month) for month in range(1, 13)
        )
        with self.assertNumQueries(len(two)):
            self.assertEqual(self.client.get(changelist).status_code, 200)

    def test_the_admin_cannot_add_change_or_delete(self):
        october = GuestMonth.objects.create(month=date(2026, 10, 1), completed=31, saved_password=9)
        self.client.force_login(User.objects.create_superuser(username="owner", password="pw"))
        data = {"month": "2026-10-01", "completed": 0, "saved_password": 0}
        add = reverse("admin:screening_guestmonth_add")
        change = reverse("admin:screening_guestmonth_change", args=[october.pk])
        delete = reverse("admin:screening_guestmonth_delete", args=[october.pk])
        self.assertEqual(self.client.get(change).status_code, 200)
        self.assertEqual(self.client.get(add).status_code, 403)
        self.assertEqual(self.client.post(add, data).status_code, 403)
        self.assertEqual(self.client.post(change, data).status_code, 403)
        self.assertEqual(self.client.post(delete, {"post": "yes"}).status_code, 403)
        self.assertEqual(counts(), [(date(2026, 10, 1), 31, 9)])

    def test_not_in_the_download_and_kept_when_the_account_is_deleted(self):
        user = consented_user(username="guest_counts_account", password=self.PASSWORD)
        self.client.force_login(user)
        self.client.post(
            SUBMISSIONS,
            json.dumps(self.body([4] * 10, from_guest=True)),
            content_type="application/json",
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        data = json.loads(self.client.get(reverse("download_my_data")).content)
        names = {"guest_month", "guest_months", "completed", "saved_password", "saved_google"}
        self.assertFalse(names & set(data))
        self.assertNotIn("訪客", json.dumps(data, ensure_ascii=False))
        self.client.post(reverse("delete_account"), {"password": self.PASSWORD})
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertEqual(counts(), [(this_month(), 0, 1)])
