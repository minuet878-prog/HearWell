"""Spec #478 (ADR 0047): the 待辦 under the 現在這一步 and the 您在這裡 stop. The wordings are
the owner's to change, so the to-dos are found by their key and kind, not their words."""

import re
from datetime import date

from django.urls import reverse

from screening.fitting_route import fitting_state
from screening.journey_todos import stop_todos
from screening.models import AidAndSubsidy, AidLevel, Certificate, GuideChapterView, Subsidy
from screening.tests import test_care_journey, test_home_journey
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
        here = here_stop(fitting_state(self.user, TODAY))
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
        self.assertEqual(journey.card.todos, here_stop(fitting_state(self.user, TODAY)).todos)

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
        return {todo.key: todo.done for todo in stop_todos(slug, fitting_state(self.user, TODAY))}

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
            kinds(here_stop(state).todos),
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
TODO = re.compile(r'<li class="todo todo-(manual|auto)( is-done)?" data-todo="([^"]+)">')
TODO_ITEM = re.compile(r'<li class="todo [^"]*" data-todo="([^"]+)">(.*?)</li>', re.S)


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

    def words(self, html):
        """Each to-do's words as a screen reader reads them, by key."""
        return {key: self.text(body) for key, body in TODO_ITEM.findall(html)}

    def test_step_2_s_card_lists_its_to_dos_under_the_one_solid_button(self):
        # Spec #478 acceptance 1 and 27.
        self.answer()
        main = self.main()
        card = self.part(main, "journey-card")
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

    def test_each_to_do_is_read_as_done_or_not_and_none_can_be_pressed_yet(self):
        # Spec #478 acceptance 28, as far as #480 goes: the state in words; ticking a manual one
        # and saving it is #481's, so nothing in the list takes the focus or a press yet.
        self.answer()
        todos = self.part(self.part(self.main(), "journey-card"), "todos")
        self.assertEqual(
            self.words(todos),
            {
                "audiogram-test": "到醫院或診所做聽力檢查 ，未完成",
                "audiogram-copy": "跟醫院或診所要一份聽力圖 ，未完成",
                "audiogram-record": "把聽力圖記到聽伴 ，未完成。 做完會自動打勾",
            },
        )
        for control in ("<a ", "<button", "<input", "<form", "tabindex", 'role="checkbox"'):
            self.assertNotIn(control, todos)

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
        home = listed(self.part(self.main(), "journey-card"))
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
        self.assertIn('<div class="todos">', self.part(main, "journey-card"))
        self.assertEqual(guide.count('<div class="todos">'), 1)
        self.assertIn('<div class="todos">', self.here(guide))

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
