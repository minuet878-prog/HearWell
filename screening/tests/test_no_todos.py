"""#742 (spec #741, ADR 0073): the 待辦 are gone, from the pages and from the database, with the
第幾台 they were counted by."""

import json
from datetime import date, timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import NoReverseMatch, reverse

from screening.models import AidAndSubsidy, Certificate, GuideChapterView, Subsidy, User
from screening.questionnaires import ioi_ha
from screening.tests import test_home_journey
from screening.tests.helpers import consented_user

TODAY = test_home_journey.TODAY
PTA_55 = test_home_journey.PTA_55
# What only the 待辦 put on a page: their list, its heading, a 手動待辦's checkbox, and an
# 自動待辦's 「⋯網站會知道」.
TODO_MARKS = ('class="todos"', "data-todo", 'role="checkbox"', "網站會知道")


class NoTodosOnThePagesTests(test_home_journey.HomeJourneyTestCase):
    """Spec #741 acceptance 29: whatever the state, neither the home page nor my guide lists
    「要做的事」, a box to tick or 「⋯網站會知道」."""

    def guide(self):
        content = self.client.get(reverse("guide")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def assert_no_todos(self, page):
        self.assertNotIn("要做的事", page)
        for mark in TODO_MARKS:
            self.assertNotIn(mark, page)

    def fitted(self, on):
        AidAndSubsidy.objects.update_or_create(
            user=self.user,
            defaults={"fitted_on": on, "ear": "both", "subsidy": Subsidy.OTHER},
        )

    def test_no_state_lists_to_dos(self):
        def recording_the_audiogram():
            self.answer()

        def at_form_9():
            self.answer()
            self.make(PTA_55, PTA_55)
            GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
            AidAndSubsidy.objects.create(user=self.user, certificate=Certificate.YES)

        def wearing_for_a_month():
            self.answer()
            self.make(PTA_55, PTA_55)
            self.fitted(TODAY - timedelta(days=30))

        def retesting():
            self.answer(on=date(2026, 5, 1))
            self.make(PTA_55, PTA_55, tested_on=date(2026, 4, 1))
            self.fitted(date(2026, 5, 1))
            self.answer(ioi_ha.CODE, on=date(2026, 8, 10))

        for number, state in enumerate(
            (recording_the_audiogram, at_form_9, wearing_for_a_month, retesting)
        ):
            with self.subTest(state.__name__):
                self.fresh_user(f"no_todos_{number}")
                state()
                self.assert_no_todos(self.main())
                self.assert_no_todos(self.guide())

    def test_there_is_no_page_to_tick_on(self):
        with self.assertRaises(NoReverseMatch):
            reverse("journey_todo_tick")
        self.assertEqual(self.client.post("/journey_todo_tick").status_code, 404)


class NoTodosInTheAccountTests(TestCase):
    """Spec #741 acceptance 30 and #742: the download no longer lists 待辦, and neither the
    privacy notice, its highlights nor the delete-account page name the ticks."""

    def setUp(self):
        self.user = consented_user(username="no_todo_ticks")
        self.client.force_login(self.user)

    def test_the_download_has_no_to_dos(self):
        response = self.client.get(reverse("download_my_data"))
        self.assertNotIn("journey_todos", json.loads(response.content))

    def test_no_page_names_the_ticks(self):
        for name in ("privacy", "delete_account"):
            with self.subTest(name):
                self.assertNotContains(self.client.get(reverse(name)), "待辦打勾")
        # The consent page, which shares the privacy notice's highlights, before agreeing.
        self.client.force_login(User.objects.create_user(username="no_todo_ticks_yet"))
        self.assertNotContains(self.client.get(reverse("consent")), "待辦打勾")


class DropTodoTicksMigrationTests(TransactionTestCase):
    """Spec #741 acceptance 30 (ADR 0073): the tick table and 第幾台 are dropped; every other
    answer in the 助聽器與補助資料 stays as it was."""

    before = (("screening", "0044_user_confirmed_email"),)
    after = (("screening", "0045_drop_todo_ticks_and_pair_number"),)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _apps(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(list(targets))
        return executor.loader.project_state(list(targets)).apps

    def test_the_ticks_and_the_pair_go_and_the_answers_stay(self):
        apps = self._apps(self.before)
        user = apps.get_model("screening", "User").objects.create(username="ticked_before_742")
        apps.get_model("screening", "TodoTick").objects.create(
            user=user, key="form-9-book", round_key=2
        )
        answers = {
            "certificate": "yes",
            "form_9_done": True,
            "notice_received": True,
            "approved_ears": "both",
            "fitted_on": date(2026, 10, 3),
            "ear": "both",
            "subsidy": "disability",
            "level": "mid",
            "form_25_done": False,
        }
        apps.get_model("screening", "AidAndSubsidy").objects.create(
            user=user, pair_number=2, **answers
        )

        new_aid = self._apps(self.after).get_model("screening", "AidAndSubsidy")

        self.assertNotIn("screening_todotick", connection.introspection.table_names())
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(
                cursor, "screening_aidandsubsidy"
            )
        self.assertNotIn("pair_number", [column.name for column in columns])
        self.assertEqual(list(new_aid.objects.filter(user_id=user.pk).values(*answers)), [answers])
