"""Spec #478 (ADR 0047): the 待辦 under the 現在這一步 and the 您在這裡 stop. The wordings are
the owner's to change, so the to-dos are found by their key and kind, not their words."""

import json
import re
from datetime import date, datetime
from unittest.mock import patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.fitting_route import AUDIOGRAM, fitting_state
from screening.journey_todos import MANUAL_KEYS, STOP_TODOS, stop_todos
from screening.models import (
    FIRST_ROUND,
    AidAndSubsidy,
    AidLevel,
    Certificate,
    GuideChapterView,
    Questionnaire,
    Subsidy,
    TodoTick,
    User,
)
from screening.questionnaires import hhia_s, ioi_ha, ssq12_tw, thi
from screening.tests import test_account_deletion, test_care_journey, test_home_journey
from screening.tests.helpers import consented_user
from screening.views.guide import here_stop

SOLID = test_home_journey.SOLID

TODAY = test_care_journey.TODAY
PTA_55 = test_care_journey.PTA_55
NORMAL = test_care_journey.NORMAL


def kinds(todos):
    """(key, manual, done) of each to-do, in the order listed."""
    return [(todo.key, todo.manual, todo.done) for todo in todos]


class Ticket480JourneyTodosTests(test_care_journey.CareJourneyTestCase):
    def test_recording_an_audiogram_lists_two_manual_and_one_automatic_to_do(self):
        # Spec #478 acceptance 1.
        self.answer()
        card = self.journey().card
        self.assertEqual(card.button, ("記錄醫院的聽力圖", "/audiograms/new"))
        self.assertEqual(
            kinds(card.todos),
            [
                ("audiogram-test", True, False),
                ("audiogram-copy", True, False),
                ("audiogram-record", False, False),
            ],
        )

    def at_form_9(self):
        self.answer()
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        AidAndSubsidy.objects.create(user=self.user, certificate=Certificate.YES)

    def test_step_3_s_card_lists_the_here_stop_s_own_to_dos(self):
        # Spec #478 acceptance 2: the card takes the 您在這裡 stop's list, not one of its own.
        self.at_form_9()
        card = self.journey().card
        here = here_stop(fitting_state(self.user, TODAY), self.user)
        self.assertEqual(here.slug, "form-9")
        self.assertEqual(
            kinds(card.todos), [("form-9-book", True, False), ("form-9-answer", False, False)]
        )
        self.assertEqual(card.todos, here.todos)

    def test_step_1_lists_no_to_dos(self):
        # Spec #478 acceptance 3: only the button's one thing.
        self.make(PTA_55, PTA_55)
        journey = self.journey()
        self.assertEqual(journey.current, 1)
        self.assertEqual(journey.card.todos, ())

    def fit(self, fitted_on, subsidy=Subsidy.OTHER, level=""):
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=fitted_on, subsidy=subsidy, level=level
        )

    def test_step_4_without_form_25_lists_its_own_to_dos(self):
        # Spec #478 acceptance 4: fitted 40 days ago, bought paying otherwise.
        self.answer()
        self.fit(date(2026, 10, 3))
        journey = self.journey()
        self.assertEqual(journey.current, 4)
        self.assertEqual(
            kinds(journey.card.todos),
            [("step-4-adjust", True, False), ("step-4-ioi-ha", False, False)],
        )

    def test_step_4_at_the_payout_lists_its_own_to_dos_too(self):
        # 簡易型 leaves the route at 等待補助發放, which is not step 4's card (spec #453).
        self.answer()
        self.fit(date(2026, 10, 3), Subsidy.DISABILITY, AidLevel.BASIC)
        self.assertEqual(fitting_state(self.user, TODAY).stop, "payout")
        self.assertEqual(
            [todo.key for todo in self.journey().card.todos], ["step-4-adjust", "step-4-ioi-ha"]
        )

    def test_step_4_with_form_25_lists_form_25_s_to_dos(self):
        # Spec #478 acceptance 5: fitted 2026/10/01 at 中階型 with 身障補助, form 25 not done.
        self.answer()
        self.fit(date(2026, 10, 1), Subsidy.DISABILITY, AidLevel.MID)
        journey = self.journey()
        self.assertEqual(journey.current, 4)
        self.assertEqual(
            kinds(journey.card.todos),
            [("form-25-book", True, False), ("form-25-answer", False, False)],
        )
        here = here_stop(fitting_state(self.user, TODAY), self.user)
        self.assertEqual(journey.card.todos, here.todos)

    def test_step_5_lists_its_own_manual_to_do(self):
        # Within the normal range steps 3 and 4 are 目前不需要, so step 5 is current.
        self.answer(on=date(2026, 9, 12))
        self.make(NORMAL, NORMAL)
        journey = self.journey()
        self.assertEqual(journey.current, 5)
        self.assertEqual(kinds(journey.card.todos), [("step-5-calendar", True, False)])


class Ticket480AutomaticTodosTests(test_care_journey.CareJourneyTestCase):
    """A 自動待辦 ticks itself from the route's records; the stop moving on is the route's own
    rule, so a stop's list is judged here as the 您在這裡 card would show it."""

    def todos(self, slug):
        state = fitting_state(self.user, TODAY)
        return {todo.key: todo.done for todo in stop_todos(slug, state, self.user)}

    def test_reading_before_you_go_ticks_its_chapter_but_not_booking(self):
        # Spec #478 acceptance 8.
        self.answer()
        self.make(PTA_55, PTA_55)
        self.assertEqual(
            self.todos("before-you-go"),
            {"before-you-go-read": False, "before-you-go-book": False},
        )
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        self.assertEqual(
            self.todos("before-you-go"), {"before-you-go-read": True, "before-you-go-book": False}
        )

    def test_answering_form_9_done_ticks_its_answer(self):
        # Spec #478 acceptance 9; 還沒 leaves it unticked.
        aid = AidAndSubsidy.objects.create(
            user=self.user, certificate=Certificate.YES, form_9_done=False
        )
        self.assertFalse(self.todos("form-9")["form-9-answer"])
        aid.form_9_done = True
        aid.save()
        self.assertTrue(self.todos("form-9")["form-9-answer"])

    def test_an_audiogram_that_cannot_tell_leaves_recording_it_unticked(self):
        self.answer()
        audiogram = self.make(NORMAL, NORMAL)
        audiogram.points.filter(ear="left", frequency=4000).delete()
        self.assertFalse(self.todos("audiogram")["audiogram-record"])
        self.make(NORMAL, NORMAL)
        self.assertTrue(self.todos("audiogram")["audiogram-record"])

    def test_applying_for_the_certificate_leaves_its_answer_unticked(self):
        aid = AidAndSubsidy.objects.create(user=self.user, certificate=Certificate.APPLYING)
        self.assertFalse(self.todos("assessment")["assessment-answer"])
        aid.certificate = Certificate.NO_SUBSIDY
        aid.save()
        self.assertTrue(self.todos("assessment")["assessment-answer"])

    def test_the_notice_s_ears_and_level_both_tick_it(self):
        aid = AidAndSubsidy.objects.create(
            user=self.user, notice_received=True, approved_ears="both"
        )
        self.assertFalse(self.todos("notice")["notice-answer"])
        aid.level = AidLevel.MID
        aid.save()
        self.assertTrue(self.todos("notice")["notice-answer"])

    def test_the_fitting_date_ticks_itself_before_the_stop_is_done(self):
        # The stop wants the subsidy answered too (#295); the to-do is the date alone, so the
        # 您在這裡 stop shows it ticked.
        self.answer()
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 10, 3))
        state = fitting_state(self.user, TODAY)
        self.assertEqual(state.stop, "after-fitting")
        self.assertEqual(
            kinds(here_stop(state, self.user).todos),
            [("after-fitting-date", False, True), ("after-fitting-adjust", True, False)],
        )

    def test_answering_form_25_done_ticks_its_answer(self):
        aid = AidAndSubsidy.objects.create(
            user=self.user,
            fitted_on=date(2026, 10, 1),
            subsidy=Subsidy.DISABILITY,
            level=AidLevel.MID,
        )
        self.assertFalse(self.todos("form-25")["form-25-answer"])
        aid.form_25_done = True
        aid.save()
        self.assertTrue(self.todos("form-25")["form-25-answer"])


# A listed to-do: its kind, whether done, and its key.
TODO = re.compile(r'<li class="todo todo-(manual|auto)( is-done)?" data-todo="([^"]+)"[^>]*>')
TODO_ITEM = re.compile(r'<li class="todo [^"]*" data-todo="([^"]+)"[^>]*>(.*?)</li>', re.S)


def listed(html):
    """(key, manual, done) of each to-do listed in html, in order."""
    return [(key, kind == "manual", bool(done)) for kind, done, key in TODO.findall(html)]


class Ticket480TodoPagesTests(test_home_journey.HomeJourneyTestCase):
    """The home page's 現在這一步 card and my guide's 您在這裡 card show the same list, under
    the button (the owner's pick B on #479)."""

    def at_form_9(self):
        self.answer()
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        AidAndSubsidy.objects.create(user=self.user, certificate=Certificate.YES)

    def guide(self):
        content = self.client.get(reverse("guide")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def here(self, guide):
        """The 您在這裡 card, as far as the next stop."""
        start = guide.index('<div class="route-box route-card">')
        return guide[start : guide.index('<li class="route-stop', start)]

    def current_card(self, main):
        """The 現在這一步's card with its to-dos, as far as the next step or the list's end."""
        start = main.index('<div class="journey-card">')
        ends = (main.find('<li class="journey-step', start), main.index("</ol>", start))
        return main[start : min(end for end in ends if end != -1)]

    def words(self, html):
        """Each to-do's words as a screen reader reads them, by key."""
        return {key: self.text(body) for key, body in TODO_ITEM.findall(html)}

    def test_step_2_s_card_lists_its_to_dos_under_the_one_solid_button(self):
        # Spec #478 acceptance 1 and 27.
        self.answer()
        main = self.main()
        card = self.current_card(main)
        self.assertEqual(
            listed(card),
            [
                ("audiogram-test", True, False),
                ("audiogram-copy", True, False),
                ("audiogram-record", False, False),
            ],
        )
        self.assertEqual(len(SOLID.findall(main)), 1)
        button = card.index('href="/audiograms/new">記錄醫院的聽力圖</a>')
        self.assertLess(button, card.index('<div class="todos">'))
        self.assertIn('<p class="todos-head" id="todos-title">要做的事</p>', card)
        # A 手動待辦 a box, a 自動待辦 a ring (the mockup's look); neither drawing is read out.
        self.assertEqual(card.count('<span class="todo-box" aria-hidden="true">'), 2)
        self.assertEqual(card.count('<span class="todo-ring" aria-hidden="true">'), 1)

    def test_each_to_do_is_read_by_its_words(self):
        # Spec #478 acceptance 28: an automatic one's state in words; a manual one is named by
        # its words, its state the checkbox's (#481, Ticket481TickTests).
        self.answer()
        todos = self.part(self.current_card(self.main()), "todos")
        self.assertEqual(
            self.words(todos),
            {
                "audiogram-test": "到醫院或診所做聽力檢查",
                "audiogram-copy": "跟醫院或診所要一份聽力圖",
                "audiogram-record": "把聽力圖記到聽伴 ，未完成。 做完就會往下一站",
            },
        )

    def test_step_4_s_own_automatic_to_do_says_it_finishes_the_step(self):
        # The owner on 2026-11-13: a stop's says it moves the route on, step 4's that the step is
        # done (phase-2-grill-decisions.md); fitted 40 days ago, bought paying otherwise.
        self.answer()
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 10, 3), subsidy=Subsidy.OTHER
        )
        todos = self.part(self.current_card(self.main()), "todos")
        self.assertEqual(
            self.words(todos)["step-4-ioi-ha"], "做完助聽器效益問卷 ，未完成。 做完這一步就完成"
        )

    def test_a_done_automatic_to_do_is_a_ticked_ring_saying_so(self):
        # Spec #478 acceptance 8's look: the fitting date ticks its to-do before 配戴之後 is
        # done, which wants the subsidy too, so my guide's 您在這裡 shows it ticked.
        self.answer()
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 10, 3))
        here = self.here(self.guide())
        self.assertEqual(
            listed(here),
            [("after-fitting-date", False, True), ("after-fitting-adjust", True, False)],
        )
        self.assertEqual(
            self.words(here)["after-fitting-date"], "記下開始配戴的日期 ，已完成。 已自動打勾"
        )
        ring = re.search(r'<span class="todo-ring" aria-hidden="true">(.*?)</span>', here, re.S)
        self.assertIn("<svg", ring.group(1))

    def test_home_and_my_guide_list_the_same_to_dos_for_form_9(self):
        # Spec #478 acceptance 2; on my guide the list sits between the button and the question.
        self.at_form_9()
        home = listed(self.current_card(self.main()))
        here = self.here(self.guide())
        self.assertEqual(home, [("form-9-book", True, False), ("form-9-answer", False, False)])
        self.assertEqual(listed(here), home)
        self.assertLess(here.index("看九號表的流程</a>"), here.index('<div class="todos">'))
        self.assertLess(here.index('<div class="todos">'), here.index("<form"))

    def test_only_the_current_step_and_the_here_stop_list_to_dos(self):
        # Spec #478 acceptance 6: none under the steps done, after or not needed, nor under the
        # route's other stops.
        self.at_form_9()
        main, guide = self.main(), self.guide()
        self.assertEqual(main.count('<div class="todos">'), 1)
        self.assertIn('<div class="todos">', self.current_card(main))
        self.assertEqual(guide.count('<div class="todos">'), 1)
        self.assertIn('<div class="todos">', self.here(guide))

    def test_steps_not_needed_list_no_to_dos(self):
        # Spec #478 acceptance 6 for 目前不需要: within the normal range steps 3 and 4 open to
        # say what they are, without step 4's own to-dos; step 5's card lists its own.
        self.answer(on=date(2026, 9, 12))
        self.make(NORMAL, NORMAL)
        main = self.main()
        not_needed = re.findall(r'<li class="journey-step is-not-needed.*?</li>', main, re.S)
        self.assertEqual(len(not_needed), 2)
        for step in not_needed:
            self.assertIn("目前不需要", step)
            self.assertNotIn('class="todo', step)
        self.assertEqual(main.count('<div class="todos">'), 1)
        self.assertEqual(listed(self.current_card(main)), [("step-5-calendar", True, False)])

    def test_step_1_s_card_has_no_list(self):
        # Spec #478 acceptance 3.
        self.make(PTA_55, PTA_55)
        self.assertNotIn('class="todos', self.main())

    def test_a_result_page_s_next_step_lists_no_to_dos(self):
        # Spec #478 acceptance 7: the 建議下一步 is the card's one thing and button only.
        submission = self.answer()
        content = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        self.assertIn("記錄醫院的聽力圖", content)
        self.assertNotIn('class="todos', content)
        self.assertNotIn("要做的事", content)


class Ticket481TickTests(test_home_journey.HomeJourneyTestCase):
    """#481: a 手動待辦 ticked and unticked by its owner, kept, and shown alike on the home page
    and my guide; an automatic one never takes a tick."""

    at_form_9 = Ticket480TodoPagesTests.at_form_9
    guide = Ticket480TodoPagesTests.guide
    here = Ticket480TodoPagesTests.here
    current_card = Ticket480TodoPagesTests.current_card

    def tick(self, key, ticked=True, next_url="/", **headers):
        return self.client.post(
            reverse("journey_todo_tick"),
            {"todo": key, "ticked": "1" if ticked else "0", "next": next_url},
            headers=headers,
        )

    def test_a_tick_is_kept_on_the_home_page_and_my_guide(self):
        # Spec #478 acceptance 11.
        self.at_form_9()
        self.tick("form-9-book")
        ticked = [("form-9-book", True, True), ("form-9-answer", False, False)]
        self.assertEqual(listed(self.current_card(self.main())), ticked)
        self.assertEqual(listed(self.here(self.guide())), ticked)

    def test_pressing_it_again_unticks_it(self):
        # Spec #478 acceptance 12; ticking twice keeps the one tick.
        self.at_form_9()
        self.tick("form-9-book")
        self.tick("form-9-book")
        self.assertEqual(TodoTick.objects.filter(user=self.user).count(), 1)
        self.tick("form-9-book", ticked=False)
        unticked = [("form-9-book", True, False), ("form-9-answer", False, False)]
        self.assertEqual(listed(self.current_card(self.main())), unticked)
        self.assertEqual(listed(self.here(self.guide())), unticked)
        self.assertFalse(TodoTick.objects.exists())

    def test_step_4_and_5_s_own_manual_to_dos_tick_too(self):
        # Their cards are no route stop's, yet ticked the same way.
        self.answer(on=date(2026, 9, 12))
        self.make(NORMAL, NORMAL)
        self.tick("step-5-calendar")
        self.assertEqual(listed(self.current_card(self.main())), [("step-5-calendar", True, True)])

    def test_an_automatic_to_do_is_refused(self):
        # Spec #478 acceptance 10: ticked or unticked, nothing changes.
        self.at_form_9()
        for ticked in (True, False):
            with self.subTest(ticked=ticked):
                self.assertEqual(self.tick("form-9-answer", ticked).status_code, 400)
        self.assertFalse(TodoTick.objects.exists())
        self.assertEqual(
            listed(self.current_card(self.main())),
            [("form-9-book", True, False), ("form-9-answer", False, False)],
        )

    def test_an_unknown_to_do_is_404(self):
        # Spec #478 acceptance 16.
        self.at_form_9()
        for key in ("no-such-to-do", ""):
            with self.subTest(key=key):
                self.assertEqual(self.tick(key).status_code, 404)
        self.assertFalse(TodoTick.objects.exists())

    def test_signed_out_goes_to_login_writing_nothing(self):
        # Spec #478 acceptance 15.
        self.client.logout()
        url = reverse("journey_todo_tick")
        self.assertRedirects(
            self.tick("form-9-book"),
            f"{reverse('login')}?next={url}",
            fetch_redirect_response=False,
        )
        self.assertFalse(TodoTick.objects.exists())

    def test_a_tick_is_the_sender_s_own(self):
        # Spec #478 acceptance 17: 甲 ticking and unticking touches 乙's ticks of the same to-do
        # in no way.
        self.at_form_9()
        first = self.user
        self.fresh_user("todo_other")
        self.at_form_9()
        self.tick("form-9-book")
        other = self.user
        self.client.force_login(first)
        self.user = first
        self.assertEqual(
            listed(self.current_card(self.main())),
            [("form-9-book", True, False), ("form-9-answer", False, False)],
        )
        self.tick("form-9-book")
        self.tick("form-9-book", ticked=False)
        self.assertEqual(
            list(TodoTick.objects.values_list("user", "key")), [(other.pk, "form-9-book")]
        )

    def test_only_a_post_ticks(self):
        # Spec #478 acceptance 26.
        self.at_form_9()
        url = reverse("journey_todo_tick")
        for method in ("get", "put", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(url).status_code, 405)
        self.assertFalse(TodoTick.objects.exists())

    def test_without_javascript_it_goes_back_to_the_row_ticked(self):
        # Spec #478 acceptance 18: the form the row is, sent as a browser sends it, goes back to
        # the page it was on, at the row, which is ticked.
        self.at_form_9()
        for path, card in ((reverse("index"), self.main), (reverse("guide"), self.guide)):
            with self.subTest(path=path):
                row = TODO_ROW.search(card()).group(0)
                form = re.search(r'<form [^>]*action="([^"]+)"', row)
                fields = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', row))
                self.assertEqual(form.group(1), reverse("journey_todo_tick"))
                self.assertEqual(fields["todo"], "form-9-book")
                response = self.client.post(form.group(1), fields, headers={"accept": BROWSER})
                self.assertRedirects(
                    response, f"{path}#todo-form-9-book", fetch_redirect_response=False
                )
                content = self.client.get(path).content.decode()
                self.assertIn('id="todo-form-9-book"', content)
                ticked = fields["ticked"] == "1"
                self.assertEqual(listed(content)[0], ("form-9-book", True, ticked))

    def test_another_site_is_no_place_to_go_back_to(self):
        self.at_form_9()
        response = self.tick("form-9-book", next_url="https://example.com/")
        self.assertRedirects(response, "/#todo-form-9-book", fetch_redirect_response=False)

    def test_with_javascript_it_answers_in_place(self):
        # journey-todos.js asks for JSON: no page to go to, the state saved said back.
        self.at_form_9()
        response = self.tick("form-9-book", accept="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ticked": True})
        response = self.tick("form-9-book", ticked=False, accept="application/json")
        self.assertEqual(response.json(), {"ticked": False})
        self.assertFalse(TodoTick.objects.exists())

    def test_a_manual_to_do_is_a_checkbox_saying_its_state(self):
        # Spec #478 acceptance 28: each row a button read as a checkbox, ticked or not, named by
        # its words; an automatic one stays words, with nothing to press or focus.
        self.at_form_9()
        self.tick("form-9-book")
        for card in (self.current_card(self.main()), self.here(self.guide())):
            row = TODO_ROW.search(card).group(0)
            self.assertEqual(
                re.findall(r'<button [^>]*role="checkbox" aria-checked="(\w+)"', row), ["true"]
            )
            self.assertIn('value="0"', row)  # pressed again, it unticks
            button = re.search(r"<button .*?</button>", row, re.S).group(0)
            self.assertEqual(self.text(button), "預約開九號表")
            auto = re.search(r'<li class="todo todo-auto.*?</li>', card, re.S).group(0)
            for control in ("<a ", "<button", "<input", "<form", "tabindex", "role="):
                self.assertNotIn(control, auto)
        self.tick("form-9-book", ticked=False)
        row = TODO_ROW.search(self.current_card(self.main())).group(0)
        self.assertIn('role="checkbox" aria-checked="false"', row)
        self.assertIn('value="1"', row)

    def test_the_pages_stay_uncached(self):
        # Spec #478 acceptance 26: 健康資料頁面 with a tick on them, and the answer to one.
        self.at_form_9()
        self.tick("form-9-book")
        for response in (
            self.client.get(reverse("index")),
            self.client.get(reverse("guide")),
            self.tick("form-9-book"),
            self.tick("form-9-book", accept="application/json"),
        ):
            with self.subTest(url=response.request["PATH_INFO"]):
                self.assertIn("no-store", response["Cache-Control"])


# A browser's own form post, which prefers a page (Chrome's Accept).
BROWSER = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
TODO_ROW = re.compile(r'<li class="todo todo-manual[^"]*" data-todo="form-9-book".*?</li>', re.S)


class Ticket481TicksDoNotMoveTheJourneyTests(test_care_journey.CareJourneyTestCase):
    """Spec #478 acceptance 13–14 (ADR 0047): a stop is done by its records, ticks or none."""

    at_form_9 = Ticket480JourneyTodosTests.at_form_9

    def test_every_manual_to_do_ticked_leaves_form_9_the_stop(self):
        # 13.
        self.at_form_9()
        TodoTick.objects.create(user=self.user, key="form-9-book", round_key=FIRST_ROUND)
        journey = self.journey()
        self.assertEqual(journey.current, 3)
        self.assertEqual(fitting_state(self.user, TODAY).stop, "form-9")
        self.assertEqual(kinds(journey.card.todos)[0], ("form-9-book", True, True))

    def test_none_ticked_form_9_done_moves_on(self):
        # 14.
        self.at_form_9()
        AidAndSubsidy.objects.filter(user=self.user).update(form_9_done=True)
        state = fitting_state(self.user, TODAY)
        self.assertIn("form-9", state.done)
        self.assertEqual(state.stop, "notice")


class Ticket481TickDataTests(test_home_journey.HomeJourneyTestCase):
    """Spec #478 acceptance 24–25: the ticks in 下載我的資料, and gone with the account."""

    tick = Ticket481TickTests.tick

    def test_the_download_lists_each_tick_with_its_words_and_time(self):
        # 24: an unticked one is not there; an earlier round's is Ticket482RoundDataTests'.
        other = consented_user(username="todo_export_other")
        TodoTick.objects.create(user=other, key="audiogram-copy", round_key=FIRST_ROUND)
        for key, moment in (
            ("audiogram-test", datetime(2026, 11, 12, 9, 30)),
            ("form-9-book", datetime(2026, 11, 12, 9, 31)),
            ("step-5-calendar", datetime(2026, 11, 13, 8, 5)),
        ):
            with patch("django.utils.timezone.now", return_value=timezone.make_aware(moment)):
                self.tick(key)
        self.tick("form-9-book", ticked=False)
        data = json.loads(self.client.get(reverse("download_my_data")).content)
        self.assertEqual(
            data["journey_todos"],
            [
                {
                    "todo": "到醫院或診所做聽力檢查",
                    "ticked_at": "2026-11-12T09:30:00+08:00",
                    "current_round": True,
                },
                {
                    "todo": "把下次篩檢日期記在月曆或手機上",
                    "ticked_at": "2026-11-13T08:05:00+08:00",
                    "current_round": True,
                },
            ],
        )

    def test_the_download_s_queries_do_not_grow_with_the_ticks(self):
        # CODING_STANDARDS 15: two ticks and many, the same queries.
        for key in ("audiogram-test", "audiogram-copy"):
            self.tick(key)
        url = reverse("download_my_data")
        with CaptureQueriesContext(connection) as two:
            self.client.get(url)
        # Counted now: the ticks' requests below empty the log it reads.
        queries = len(two)
        many = sorted(MANUAL_KEYS - {"audiogram-test", "audiogram-copy"})
        self.assertGreater(len(many), 5)
        for key in many:
            self.tick(key)
        self.assertEqual(TodoTick.objects.filter(user=self.user).count(), len(MANUAL_KEYS))
        with self.assertNumQueries(queries):
            self.client.get(url)

    def test_deleting_the_account_takes_its_ticks(self):
        # 25: PROTECT, so delete_with_data deletes them first; another's stay.
        other = consented_user(username="todo_delete_other")
        TodoTick.objects.create(user=other, key="audiogram-test", round_key=FIRST_ROUND)
        self.user.set_password(test_account_deletion.PASSWORD)
        self.user.save()
        self.client.force_login(self.user)
        self.tick("audiogram-test")
        self.tick("form-9-book")
        response = self.client.post(
            reverse("delete_account"), {"password": test_account_deletion.PASSWORD}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(list(TodoTick.objects.values_list("user", flat=True)), [other.pk])


class Ticket482RoundsTests(test_care_journey.CareJourneyTestCase):
    """#482 (spec #478 acceptance 19–23): a step's or a stop's 手動待辦 start over each round,
    judged on the 照顧旅程 and the 您在這裡 stop as the pages show them. Ticks go in through the
    tick page and fitting dates through 配戴之後's question, as the user sends them."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def tick(self, *keys):
        for key in keys:
            self.client.post(reverse("journey_todo_tick"), {"todo": key, "ticked": "1"})

    def fit(self, fitted_on, subsidy=Subsidy.OTHER, level=""):
        # 配戴之後's question, which a first date and a changed one both go through.
        data = {"stop": "after-fitting", "fitted_on": fitted_on.isoformat(), "ear": "both"}
        data |= {"subsidy": subsidy, "level": level}
        self.client.post(reverse("route_answer"), data)

    def ticked(self, slug):
        """Whether each 手動待辦 of a stop is ticked, as the 您在這裡 stop would show them."""
        return {
            todo.key: todo.done
            for todo in stop_todos(slug, fitting_state(self.user, TODAY), self.user)
            if todo.manual
        }

    def at_form_25(self):
        # Fitted 2026/10/01 at 中階型 with 身障補助: step 4 shows 二十五號表's to-dos.
        self.answer()
        self.make(PTA_55, PTA_55)
        self.fit(date(2026, 10, 1), Subsidy.DISABILITY, AidLevel.MID)
        self.assertEqual(kinds(self.journey().card.todos)[0], ("form-25-book", True, False))

    def test_a_later_fitting_date_starts_the_route_s_eight_stops_over(self):
        # 21: every stop's 手動待辦 ticked, the date moved later; 記錄聽力圖's stay.
        self.at_form_25()
        manual = [todo.key for todos in STOP_TODOS.values() for todo in todos if not todo.rule]
        self.tick(*manual)
        self.assertEqual(kinds(self.journey().card.todos)[0], ("form-25-book", True, True))
        self.fit(date(2026, 10, 5), Subsidy.DISABILITY, AidLevel.MID)
        self.assertEqual(kinds(self.journey().card.todos)[0], ("form-25-book", True, False))
        for slug, todos in STOP_TODOS.items():
            with self.subTest(slug):
                still = {todo.key: slug == AUDIOGRAM for todo in todos if not todo.rule}
                self.assertEqual(self.ticked(slug), still)

    def test_a_later_fitting_date_starts_step_4_s_own_over(self):
        # 21 for step 4's card without 二十五號表: fitted 40 days ago, paying otherwise.
        self.answer()
        self.fit(date(2026, 10, 3))
        self.tick("step-4-adjust")
        self.assertEqual(kinds(self.journey().card.todos)[0], ("step-4-adjust", True, True))
        self.fit(date(2026, 10, 10))
        self.assertEqual(kinds(self.journey().card.todos)[0], ("step-4-adjust", True, False))

    def test_an_earlier_fitting_date_keeps_the_ticks(self):
        # 22: a date put right, not a new pair.
        self.at_form_25()
        self.tick("form-25-book", "step-4-adjust", "before-you-go-book")
        self.fit(date(2026, 9, 25), Subsidy.DISABILITY, AidLevel.MID)
        self.assertEqual(kinds(self.journey().card.todos)[0], ("form-25-book", True, True))
        self.assertEqual(self.ticked("before-you-go"), {"before-you-go-book": True})

    def test_the_first_fitting_date_keeps_the_ticks(self):
        # 23: before any 助聽器與補助資料, and once some were answered without the date.
        self.answer()
        self.make(PTA_55, PTA_55)
        self.tick("before-you-go-book")
        self.client.post(reverse("route_answer"), {"stop": "assessment", "certificate": "yes"})
        self.tick("form-9-book")
        self.fit(date(2026, 10, 3))
        self.assertEqual(self.ticked("before-you-go"), {"before-you-go-book": True})
        self.assertEqual(self.ticked("form-9"), {"form-9-book": True})

    def test_clearing_the_fitting_date_then_filling_it_again_keeps_the_ticks(self):
        # 還沒開始戴 clears the date (spec #291 acceptance 18); neither is a later date.
        self.at_form_25()
        self.tick("before-you-go-book")
        self.client.post(reverse("route_answer"), {"stop": "after-fitting", "not_fitted": "1"})
        self.assertIsNone(AidAndSubsidy.for_user(self.user).fitted_on)
        self.fit(date(2026, 10, 20))
        self.assertEqual(self.ticked("before-you-go"), {"before-you-go-book": True})

    def test_a_later_date_saved_anywhere_is_the_next_pair(self):
        # The rule is the record's own, so a date saved apart from 配戴之後's question counts.
        self.answer()
        aid = AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 10, 3))
        self.tick("step-4-adjust")
        aid.fitted_on = date(2026, 10, 4)
        aid.save()
        self.assertEqual(kinds(self.journey().card.todos)[0], ("step-4-adjust", True, False))

    def test_another_s_rounds_are_their_own(self):
        # A new pair of one user's is no other user's (the round is read per account).
        other = consented_user(username="round_other")
        AidAndSubsidy.objects.create(user=other, fitted_on=date(2026, 10, 3))
        self.client.force_login(other)
        self.tick("step-4-adjust")
        aid = AidAndSubsidy.for_user(other)
        aid.fitted_on = date(2026, 10, 10)
        aid.save()
        self.client.force_login(self.user)
        self.answer()
        self.fit(date(2026, 10, 3))
        self.tick("step-4-adjust")
        self.assertEqual(kinds(self.journey().card.todos)[0], ("step-4-adjust", True, True))

    def at_step_5(self):
        # Within the normal range steps 3 and 4 are 目前不需要, so step 5 is current.
        self.answer(on=date(2026, 9, 12))
        self.make(NORMAL, NORMAL)
        self.tick("step-5-calendar")
        self.assertEqual(kinds(self.journey().card.todos), [("step-5-calendar", True, True)])

    def test_the_next_life_impact_record_starts_step_5_over(self):
        # 19, either life-impact questionnaire; ticked again, it is that round's.
        self.at_step_5()
        self.answer(code=hhia_s.CODE, on=date(2026, 11, 10))
        journey = self.journey()
        self.assertEqual(journey.current, 5)
        self.assertEqual(kinds(journey.card.todos), [("step-5-calendar", True, False)])
        self.tick("step-5-calendar")
        self.assertEqual(kinds(self.journey().card.todos), [("step-5-calendar", True, True)])

    def test_another_questionnaire_keeps_step_5_s_ticks(self):
        # 20: THI and SSQ12 are no life-impact questionnaire.
        self.at_step_5()
        ssq12 = Questionnaire.objects.create(questionnaire_name="SSQ12", code=ssq12_tw.CODE)
        self.questionnaires[ssq12_tw.CODE] = ssq12
        self.answer(code=thi.CODE, on=date(2026, 11, 10))
        self.answer(code=ssq12_tw.CODE, on=date(2026, 11, 11))
        self.assertEqual(kinds(self.journey().card.todos), [("step-5-calendar", True, True)])

    def test_step_5_ticked_before_any_life_impact_record_starts_over_with_the_first(self):
        # Worn and IOI-HA done, step 5 asks for one first (spec #453).
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 5, 1), subsidy=Subsidy.OTHER
        )
        self.answer(code=ioi_ha.CODE, on=date(2026, 9, 1))
        self.assertEqual(self.journey().current, 5)
        self.tick("step-5-calendar")
        self.assertEqual(kinds(self.journey().card.todos), [("step-5-calendar", True, True)])
        self.answer(on=date(2026, 11, 10))
        self.assertEqual(kinds(self.journey().card.todos), [("step-5-calendar", True, False)])

    def test_a_new_life_impact_record_keeps_the_route_s_ticks(self):
        # The two rounds apart: a retest is no new pair, a new pair no retest.
        self.at_form_25()
        self.tick("form-25-book", "step-5-calendar")
        self.answer(on=date(2026, 11, 10))
        self.assertEqual(kinds(self.journey().card.todos)[0], ("form-25-book", True, True))


class Ticket482RoundDataTests(test_home_journey.HomeJourneyTestCase):
    """Spec #478 acceptance 19 and 24: an earlier round's ticks stay in 下載我的資料, each
    saying whether it is in the current round."""

    tick = Ticket481TickTests.tick

    def tick_at(self, key, hour, minute):
        moment = timezone.make_aware(datetime(2026, 11, 12, hour, minute))
        with patch("django.utils.timezone.now", return_value=moment):
            self.tick(key)

    def test_the_download_says_which_ticks_are_in_the_current_round(self):
        aid = AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 10, 3))
        self.tick_at("audiogram-test", 9, 0)
        self.tick_at("form-9-book", 9, 1)
        self.tick_at("step-5-calendar", 9, 2)
        # A new pair and a life-impact record later, step 5 ticked anew and unticked again.
        aid.fitted_on = date(2026, 10, 10)
        aid.save()
        self.answer()
        self.tick_at("step-5-calendar", 9, 3)
        self.tick("step-5-calendar", ticked=False)
        self.tick_at("form-9-book", 9, 4)
        data = json.loads(self.client.get(reverse("download_my_data")).content)
        self.assertEqual(
            [
                (tick["todo"], tick["ticked_at"][11:16], tick["current_round"])
                for tick in data["journey_todos"]
            ],
            [
                ("到醫院或診所做聽力檢查", "09:00", True),
                ("預約開九號表", "09:01", False),
                ("把下次篩檢日期記在月曆或手機上", "09:02", False),
                ("預約開九號表", "09:04", True),
            ],
        )


class Ticket482PairMigrationTests(TransactionTestCase):
    """#482: 助聽器與補助資料 kept before it count as the first pair, the rest as they were."""

    before = (("screening", "0030_todotick"),)
    after = (("screening", "0031_aidandsubsidy_pair_number"),)

    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(list(targets))
        return executor.loader.project_state(list(targets)).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_kept_records_are_the_first_pair_and_keep_their_answers(self):
        apps = self._migrate(self.before)
        old_user, old_aid = (
            apps.get_model("screening", "User"),
            apps.get_model("screening", "AidAndSubsidy"),
        )
        user = old_user.objects.create(username="kept_aid")
        old_aid.objects.create(
            user=user, fitted_on=date(2026, 10, 3), subsidy="other", form_25_done=True
        )
        new_aid = self._migrate(self.after).get_model("screening", "AidAndSubsidy")
        self.assertEqual(
            list(
                new_aid.objects.values_list("fitted_on", "subsidy", "form_25_done", "pair_number")
            ),
            [(date(2026, 10, 3), "other", True, 1)],
        )
