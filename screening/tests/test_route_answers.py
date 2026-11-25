import re
from datetime import date, timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from screening.fitting_route import fitting_state
from screening.models import AidAndSubsidy, GuideChapterView, User
from screening.tests import test_guide, test_guide_summary
from screening.tests.helpers import consented_user, took_ioi_ha

CHAPTER_CARD = "/guide/assessment#stop-question"
# The card's title, a section title (T1, ADR 0043).
CARD_TITLE = '<h2 id="stop-question-title" class="h4">'
PTA_55 = test_guide_summary.PTA_55
QUESTION = "您有聽覺機能的身心障礙證明嗎？"
# #597 (spec #593 acceptance 17): no reason asked of 沒有, and room for those about to apply;
# spec #741 Q21 words them 有／正在申請／沒有.
ANSWERS = (
    ("yes", "有"),
    ("applying", "正在申請"),
    ("no_subsidy", "沒有"),
)


def buttons(markup):
    """Each answer button's (value, wording, filled) in order."""
    return answer_buttons(markup, "certificate")


def offered(filled=None):
    return [(value, wording, value == filled) for value, wording in ANSWERS]


def marks(user, slug):
    """#779: the stop's state on the 選配路線, in the words the route marked it with before my
    guide stopped drawing it (已完成, 您在這裡, 不適用, in that order)."""
    state = fitting_state(user, timezone.localdate())
    found = (
        ("已完成", slug in state.done),
        ("您在這裡", slug == state.stop),
        ("不適用", slug in state.not_applicable),
    )
    return [mark for mark, on in found if on]


def chapter_foot(client, slug, query=""):
    """A chapter's foot: its stop's question or answer, up to the sources."""
    content = client.get(reverse("guide_chapter", args=[slug]) + query).content.decode()
    return content[content.index('<section id="stop-question"') : content.index("<footer")]


class RouteAnswerTests(TestCase):
    """#293 (spec #291 acceptance 7, 28): one POST takes a stop's answer, for request.user
    only, signed in and consented, and goes back to where it was asked; #779: without a next,
    to the stop's chapter, as my guide no longer draws the route."""

    def setUp(self):
        self.user = consented_user(username="answering_user")
        self.client.force_login(self.user)

    def post(self, certificate="yes", next_url=CHAPTER_CARD, client=None, stop="assessment"):
        data = {"stop": stop, "certificate": certificate, "next": next_url}
        return (client or self.client).post(reverse("route_answer"), data)

    def certificate(self, user=None):
        aid = AidAndSubsidy.for_user(user or self.user)
        return aid and aid.certificate

    def test_each_answer_is_kept_and_goes_back_to_the_chapter_s_question(self):
        for answer in ("yes", "applying", "no_subsidy"):
            with self.subTest(answer=answer):
                response = self.post(answer)
                self.assertRedirects(response, CHAPTER_CARD, fetch_redirect_response=False)
                self.assertEqual(self.certificate(), answer)
        self.assertEqual(AidAndSubsidy.objects.count(), 1)

    def test_another_site_s_next_goes_to_the_stop_s_chapter_instead(self):
        response = self.post(next_url="https://example.com/guide")
        self.assertRedirects(response, CHAPTER_CARD, fetch_redirect_response=False)
        self.assertEqual(self.certificate(), "yes")

    def test_without_a_next_each_stop_goes_to_where_its_chapter_asks_it(self):
        # #779 (spec #774): in place of /guide#stop-<slug>; the notice is asked at form 9's.
        AidAndSubsidy.objects.create(user=self.user, certificate="yes", form_9_done=True)
        for stop, field, value, address in (
            ("assessment", "certificate", "yes", CHAPTER_CARD),
            ("form-9", "form_9_done", "True", "/guide/form-9#stop-question"),
            ("notice", "notice_received", "False", "/guide/form-9#stop-notice"),
            ("form-25", "form_25_done", "False", "/guide/form-25#stop-question"),
            ("after-fitting", "not_fitted", "1", "/guide/after-fitting#stop-question"),
        ):
            with self.subTest(stop=stop):
                data = {"stop": stop, field: value}
                response = self.client.post(reverse("route_answer"), data)
                self.assertRedirects(response, address, fetch_redirect_response=False)

    def test_only_the_signed_in_user_s_answer_changes(self):
        other = consented_user(username="other_answering_user")
        AidAndSubsidy.objects.create(user=other, certificate="applying", ear="left")
        self.post("no_subsidy")
        self.assertEqual(self.certificate(other), "applying")
        self.assertEqual(AidAndSubsidy.for_user(other).ear, "left")
        self.assertEqual(self.certificate(), "no_subsidy")

    def test_answering_keeps_the_other_answers(self):
        AidAndSubsidy.objects.create(user=self.user, ear="both", subsidy="disability", level="mid")
        self.post("yes")
        aid = AidAndSubsidy.for_user(self.user)
        self.assertEqual((aid.ear, aid.subsidy, aid.level), ("both", "disability", "mid"))

    def test_signed_out_goes_to_log_in_and_keeps_nothing(self):
        self.client.logout()
        response = self.post()
        self.assertTrue(response["Location"].startswith(reverse("login")))
        self.assertFalse(AidAndSubsidy.objects.exists())

    def test_without_consent_goes_to_the_consent_page_and_keeps_nothing(self):
        user = User.objects.create_user(username="not_consented_user")
        self.client.force_login(user)
        response = self.post()
        self.assertTrue(response["Location"].startswith(reverse("consent")))
        self.assertFalse(AidAndSubsidy.objects.exists())

    def test_without_the_csrf_token_it_is_refused(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(self.post(client=client).status_code, 403)
        self.assertFalse(AidAndSubsidy.objects.exists())

    def test_only_post(self):
        self.assertEqual(self.client.get(reverse("route_answer")).status_code, 405)

    def test_the_response_is_never_cached(self):
        self.assertIn("no-store", self.post()["Cache-Control"])

    def test_a_stop_without_a_question_is_refused(self):
        for stop in ("before-you-go", "payout", "nonsense", ""):
            with self.subTest(stop=stop):
                self.assertEqual(self.post(stop=stop).status_code, 400)
        self.assertFalse(AidAndSubsidy.objects.exists())

    def test_an_answer_not_offered_shows_the_question_again_with_its_error(self):
        AidAndSubsidy.objects.create(user=self.user, certificate="applying")
        for answer in ("maybe", ""):
            with self.subTest(answer=answer):
                response = self.post(answer)
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response["Cache-Control"])
                question = test_guide.text_of(response)
                self.assertIn("您有聽覺機能的身心障礙證明嗎？", question)
                self.assertContains(response, 'class="text-danger field-error')
                self.assertEqual(self.certificate(), "applying")


class RouteQuestionTests(TestCase):
    """#293 (spec #291 acceptance 6, 7, 18, 20): the certificate's answer moves the 選配路線 on.
    #779: my guide no longer draws the route, so its state is read where every page reads it;
    the question and 修改 are the chapter's (ChapterQuestionTests, test_chapter_in_place_edit)."""

    def setUp(self):
        self.user = consented_user(username="route_question_user")
        self.client.force_login(self.user)
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")

    make = test_guide_summary.GuideSummaryTests.make

    def marks(self, slug):
        return marks(self.user, slug)

    def answer(self, certificate):
        data = {"stop": "assessment", "certificate": certificate, "next": CHAPTER_CARD}
        self.client.post(reverse("route_answer"), data)

    def test_having_one_marks_it_done_and_moves_on_to_form_9(self):
        self.answer("yes")
        self.assertEqual(self.marks("assessment"), ["已完成"])
        self.assertEqual(self.marks("form-9"), ["您在這裡"])

    def test_applying_stays_here(self):
        self.answer("applying")
        self.assertEqual(self.marks("assessment"), ["您在這裡"])

    def test_not_applying_folds_the_subsidy_s_stops_away_none_not_applicable(self):
        # #596 (spec #593 acceptance 8, ADR 0063): in place of four pale 不適用 stops.
        self.answer("no_subsidy")
        state = fitting_state(self.user, timezone.localdate())
        for slug in ("form-9", "notice", "form-25", "payout"):
            with self.subTest(stop=slug):
                self.assertNotIn(slug, state.stops)
        self.assertEqual(self.marks("types-and-prices"), ["您在這裡"])
        self.assertEqual(state.not_applicable, frozenset())

    def test_changing_to_applying_takes_the_done_away(self):
        self.answer("yes")
        self.answer("applying")
        self.assertEqual(self.marks("assessment"), ["您在這裡"])
        self.assertEqual(self.marks("form-9"), [])


class ChapterQuestionTests(TestCase):
    """#293 (spec #291 acceptance 6, 20): the assessment chapter asks the same question at
    its foot while a signed-in user has not answered it."""

    def setUp(self):
        self.user = consented_user(username="chapter_question_user")
        self.client.force_login(self.user)

    def page(self, slug="assessment"):
        return self.client.get(reverse("guide_chapter", args=[slug]))

    def test_unanswered_the_chapter_ends_with_the_question(self):
        response = self.page()
        self.assertIn("no-store", response["Cache-Control"])
        content = response.content.decode()
        card = content[content.index('<section id="stop-question"') : content.index("<footer")]
        self.assertIn(f"{CARD_TITLE}看完了嗎？</h2>", card)
        self.assertIn(QUESTION, card)
        self.assertIn("第二類 b230、s260，或舊制 02", card)  # #597: the help unchanged
        self.assertIn(f'<input type="hidden" name="next" value="{CHAPTER_CARD}">', card)
        self.assertEqual(buttons(card), offered())
        # #779: the route is no longer drawn; the 照顧旅程 moves on (a draft for the owner).
        self.assertIn("答了之後，首頁的照顧旅程會跟著往下走。", test_guide.text_of(response))

    def test_answering_there_goes_back_to_it_and_the_question_is_gone(self):
        data = {"stop": "assessment", "certificate": "applying", "next": CHAPTER_CARD}
        response = self.client.post(reverse("route_answer"), data)
        self.assertRedirects(response, CHAPTER_CARD, fetch_redirect_response=False)
        self.assertNotContains(self.page(), QUESTION)

    def test_an_answer_not_offered_shows_the_chapter_again_with_its_error(self):
        data = {"stop": "assessment", "certificate": "maybe", "next": CHAPTER_CARD}
        response = self.client.post(reverse("route_answer"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1 class="bird-title">身障鑑定與鑑定醫院</h1>')
        self.assertContains(response, 'class="text-danger field-error')
        self.assertContains(
            response, 'aria-describedby="id_certificate_helptext id_certificate_error"'
        )
        self.assertFalse(AidAndSubsidy.objects.exists())

    def test_the_chapters_done_by_reading_ask_nothing(self):
        for slug in ("before-you-go", "types-and-prices"):
            with self.subTest(chapter=slug):
                self.assertNotContains(self.page(slug), 'id="stop-question"')

    def test_signed_out_or_without_consent_there_is_no_question(self):
        self.client.logout()
        self.assertNotContains(self.page(), QUESTION)
        self.client.force_login(User.objects.create_user(username="chapter_not_consented"))
        self.assertNotContains(self.page(), QUESTION)

    def test_another_user_s_answer_does_not_hide_it(self):
        other = consented_user(username="chapter_question_other")
        AidAndSubsidy.objects.create(user=other, certificate="yes")
        self.assertContains(self.page(), QUESTION)


class AnsweredCardTests(TestCase):
    """#294 (owner's decision for the chapters' questions): once answered, the chapter's
    question card says 已記下 with the answer, 修改, and a large button back to my guide (#779:
    its cards, as the route is no longer drawn)."""

    setUp = ChapterQuestionTests.setUp
    page = ChapterQuestionTests.page

    def card(self, slug):
        content = self.page(slug).content.decode()
        return content[content.index('<section id="stop-question"') : content.index("<footer")]

    def test_each_answered_chapter_says_what_was_kept(self):
        AidAndSubsidy.objects.create(user=self.user, certificate="yes", form_9_done=False)
        for slug, title, answer in (
            ("assessment", "身障鑑定與鑑定醫院", "有身障證明"),
            ("form-9", "九號表：申請助聽器補助", "九號表還沒完成"),
        ):
            with self.subTest(chapter=slug):
                card = self.card(slug)
                self.assertIn(f"{CARD_TITLE}已記下：{answer}</h2>", card)
                self.assertNotIn("<fieldset", card)
                # #777: 修改 opens it again on the chapter itself.
                edit = reverse("guide_chapter", args=[slug]) + "?edit=1#stop-question"
                self.assertIn(f'<a href="{edit}" aria-label="修改{title}的回答">修改</a>', card)
                self.assertIn(
                    f'<a class="btn btn-primary btn-lg w-full mt-2" '
                    f'href="{reverse("guide")}">回到助聽器選配與補助</a>',
                    card,
                )

    def test_answering_on_the_chapter_comes_back_to_the_card(self):
        data = {"stop": "assessment", "certificate": "yes", "next": CHAPTER_CARD}
        response = self.client.post(reverse("route_answer"), data, follow=True)
        self.assertEqual(response.redirect_chain, [(CHAPTER_CARD, 302)])
        self.assertContains(response, "已記下：有身障證明")

    def test_signed_out_or_without_consent_there_is_no_card(self):
        AidAndSubsidy.objects.create(user=self.user, certificate="yes")
        self.client.logout()
        self.assertNotContains(self.page(), 'id="stop-question"')
        self.client.force_login(User.objects.create_user(username="card_not_consented"))
        self.assertNotContains(self.page(), 'id="stop-question"')


class NotApplicableOverDoneTests(TestCase):
    """Spec #291 (#291 review): a stop both answered done and 不適用 is marked 不適用 only, and
    its chapter asks nothing at its foot, neither the question nor 已記下."""

    def setUp(self):
        self.user = consented_user(username="not_applicable_over_done_user")
        self.client.force_login(self.user)

    marks = RouteQuestionTests.marks

    def answer(self, stop, name, value):
        self.client.post(reverse("route_answer"), {"stop": stop, name: value})

    def chapter(self, slug):
        return self.client.get(reverse("guide_chapter", args=[slug]))

    def test_form_9_done_then_not_applying_folds_it_away_and_its_chapter_asks_nothing(self):
        # #596 (spec #593 acceptance 14, 19): 沒有 folds the 補助站 away, form 9 done or not.
        self.answer("assessment", "certificate", "yes")
        self.answer("form-9", "form_9_done", "True")
        self.answer("assessment", "certificate", "no_subsidy")
        self.assertNotIn("form-9", fitting_state(self.user, timezone.localdate()).stops)
        for slug in ("form-9", "form-25"):
            with self.subTest(chapter=slug):
                self.assertNotContains(self.chapter(slug), 'id="stop-question"')

    def test_the_certificate_unanswered_form_9_s_chapter_still_asks(self):
        # #596 (spec #593 acceptance 20): folded is not 沒有; answering it unfolds them.
        self.assertContains(self.chapter("form-9"), "九號表完成了嗎？")

    def test_basic_with_form_25_done_is_not_applicable_only(self):
        AidAndSubsidy.objects.create(
            user=self.user,
            fitted_on=date(2026, 5, 1),
            subsidy="disability",
            level="basic",
            form_25_done=True,
        )
        self.assertEqual(self.marks("form-25"), ["不適用"])
        self.assertNotContains(self.chapter("form-25"), 'id="stop-question"')


class ViewedStaysDoneTests(TestCase):
    """Spec #291 acceptance 19, through the pages: a chapter read stays 已完成 whatever is
    answered after it."""

    def setUp(self):
        self.user = consented_user(username="viewed_stays_done_user")
        self.client.force_login(self.user)

    marks = RouteQuestionTests.marks
    answer = NotApplicableOverDoneTests.answer

    def test_answers_sent_after_reading_leave_stops_2_and_6_done(self):
        for slug in ("before-you-go", "types-and-prices"):
            self.client.get(reverse("guide_chapter", args=[slug]))
        self.answer("assessment", "certificate", "applying")
        self.answer("after-fitting", "not_fitted", "1")
        self.answer("form-9", "form_9_done", "False")
        self.answer("notice", "notice_received", "False")
        self.answer("form-25", "form_25_done", "False")
        aid = AidAndSubsidy.for_user(self.user)
        self.assertEqual(
            (aid.certificate, aid.form_9_done, aid.notice_received, aid.form_25_done),
            ("applying", False, False, False),
        )
        self.assertEqual(self.marks("before-you-go"), ["已完成"])
        self.assertEqual(self.marks("types-and-prices"), ["已完成"])


def migrate_to(targets):
    """The models as they stood at targets, the test database migrated there."""
    executor = MigrationExecutor(connection)
    executor.migrate(list(targets))
    return executor.loader.project_state(list(targets)).apps


class CertificateRewordMigrationTests(TransactionTestCase):
    """#597 (spec #593 acceptance 25): the certificate's answers reworded, every stored value
    kept as it was."""

    before = (("screening", "0035_signinmethod_line"),)
    after = (("screening", "0036_certificate_answers_reworded"),)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_every_answer_keeps_its_value(self):
        apps = migrate_to(self.before)
        old_user, old_aid = (
            apps.get_model("screening", "User"),
            apps.get_model("screening", "AidAndSubsidy"),
        )
        stored = {"has_one": "yes", "applying": "applying", "none": "no_subsidy", "blank": ""}
        for name, answer in stored.items():
            old_aid.objects.create(user=old_user.objects.create(username=name), certificate=answer)
        new_aid = migrate_to(self.after).get_model("screening", "AidAndSubsidy")
        self.assertEqual(dict(new_aid.objects.values_list("user__username", "certificate")), stored)


class CertificateMigrationTests(TransactionTestCase):
    """#293, spec #291 Q17: in the one 0027, #284's yes / not yet becomes the three answers;
    還沒有 stays at the stop."""

    before = (("screening", "0026_aid_and_subsidy"),)
    after = (("screening", "0027_route_progress"),)

    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(list(targets))
        return executor.loader.project_state(list(targets)).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_yes_is_yes_not_yet_is_applying_and_unanswered_stays_so(self):
        apps = self._migrate(self.before)
        old_user, old_aid = (
            apps.get_model("screening", "User"),
            apps.get_model("screening", "AidAndSubsidy"),
        )
        for name, answer in (("has_one", True), ("not_yet", False), ("unanswered", None)):
            user = old_user.objects.create(username=name)
            old_aid.objects.create(user=user, has_certificate=answer)
        new_aid = self._migrate(self.after).get_model("screening", "AidAndSubsidy")
        certificates = dict(new_aid.objects.values_list("user__username", "certificate"))
        self.assertEqual(certificates, {"has_one": "yes", "not_yet": "applying", "unanswered": ""})


def answer_buttons(markup, name):
    """Each answer button for the field name: (value, wording, current) in order. #467: the
    current answer is framed with a tick (it was the filled button)."""
    found = re.findall(
        rf'<button type="submit" name="{name}" value="([^"]+)" '
        r'class="btn btn-lg btn-outline-primary( is-current" aria-pressed="true)?">'
        r'(?:<svg class="stop-answer-tick".*?</svg>)?([^<]+)</button>',
        markup,
    )
    return [(value, wording, bool(current)) for value, current, wording in found]


class Form9AndNoticeRouteTests(TestCase):
    """#294 (spec #291 acceptance 8, 9, 18): 九號表 and 等待核定公文 answered one press each, the
    notice's three questions one after another. #779: my guide no longer draws the route, so
    its state is read as every page reads it; the questions are asked at form 9's chapter
    (test_chapter_in_place_edit)."""

    FORM_9 = "九號表完成了嗎？"
    NOTICE = "收到核定公文了嗎？"
    EARS = "核定的是單耳還是雙耳？"
    LEVEL = "補助的等級是？"

    def setUp(self):
        self.user = consented_user(username="form_9_route_user")
        self.client.force_login(self.user)
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        AidAndSubsidy.objects.create(user=self.user, certificate="yes")

    make = test_guide_summary.GuideSummaryTests.make
    marks = RouteQuestionTests.marks

    def answer(self, stop, name, value, next_url=None):
        data = {"stop": stop, name: value}
        if next_url:
            data["next"] = next_url
        return self.client.post(reverse("route_answer"), data)

    def aid(self):
        return AidAndSubsidy.for_user(self.user)

    def test_done_moves_on_to_the_notice(self):
        response = self.answer("form-9", "form_9_done", "True")
        self.assertRedirects(response, "/guide/form-9#stop-question", fetch_redirect_response=False)
        self.assertIs(self.aid().form_9_done, True)
        self.assertEqual(self.marks("form-9"), ["已完成"])
        self.assertEqual(self.marks("notice"), ["您在這裡"])

    def test_form_9_not_yet_stays_here(self):
        self.answer("form-9", "form_9_done", "False")
        self.assertIs(self.aid().form_9_done, False)
        self.assertEqual(self.marks("form-9"), ["您在這裡"])

    def test_not_yet_after_done_takes_the_done_away(self):
        self.answer("form-9", "form_9_done", "True")
        self.answer("form-9", "form_9_done", "False")
        self.assertEqual(self.marks("form-9"), ["您在這裡"])

    def test_the_form_9_chapter_asks_too_and_answering_goes_back_to_it(self):
        chapter = "/guide/form-9#stop-question"
        content = self.client.get(reverse("guide_chapter", args=["form-9"])).content.decode()
        card = content[content.index('<section id="stop-question"') : content.index("<footer")]
        self.assertIn(self.FORM_9, card)
        self.assertIn(f'<input type="hidden" name="next" value="{chapter}">', card)
        response = self.answer("form-9", "form_9_done", "True", next_url=chapter)
        self.assertRedirects(response, chapter, fetch_redirect_response=False)
        self.assertIs(self.aid().form_9_done, True)

    def legends(self, markup):
        return re.findall(r'<legend class="font-bold text-xl/normal">([^<]+)</legend>', markup)

    def at_the_notice(self):
        AidAndSubsidy.objects.filter(user=self.user).update(form_9_done=True)

    def test_received_then_the_ears_then_the_level_and_only_then_is_done(self):
        self.at_the_notice()
        response = self.answer("notice", "notice_received", "True")
        self.assertRedirects(response, "/guide/form-9#stop-notice", fetch_redirect_response=False)
        self.assertEqual(self.marks("notice"), ["您在這裡"])
        self.answer("notice", "approved_ears", "both")
        self.assertEqual(self.marks("notice"), ["您在這裡"])
        self.answer("notice", "level", "mid")
        self.assertEqual(self.marks("notice"), ["已完成"])
        self.assertEqual(self.marks("types-and-prices"), ["您在這裡"])
        aid = self.aid()
        self.assertEqual((aid.notice_received, aid.approved_ears, aid.level), (True, "both", "mid"))

    def test_notice_not_yet_stays_here(self):
        self.at_the_notice()
        self.answer("notice", "notice_received", "False")
        self.assertIs(self.aid().notice_received, False)
        self.assertEqual(self.marks("notice"), ["您在這裡"])

    def test_halfway_edit_also_opens_the_questions_already_answered(self):
        self.at_the_notice()
        self.answer("notice", "notice_received", "True")
        foot = chapter_foot(self.client, "form-9", "?edit=notice")
        notice = foot[foot.index('id="stop-notice"') :]
        self.assertEqual(self.legends(notice), [self.NOTICE, self.EARS])

    def test_changing_to_not_yet_takes_the_done_away_and_clears_what_it_approved(self):
        self.at_the_notice()
        AidAndSubsidy.objects.filter(user=self.user).update(
            notice_received=True, approved_ears="both", level="mid"
        )
        self.answer("notice", "notice_received", "False")
        self.assertEqual(self.marks("notice"), ["您在這裡"])
        aid = self.aid()
        self.assertEqual((aid.notice_received, aid.approved_ears, aid.level), (False, "", ""))

    def test_an_answer_not_offered_shows_the_notice_again_with_its_error(self):
        self.at_the_notice()
        self.answer("notice", "notice_received", "True")
        response = self.answer("notice", "approved_ears", "three")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.EARS)
        self.assertContains(response, 'class="text-danger field-error')
        self.assertEqual(self.aid().approved_ears, "")

    def test_the_notice_is_asked_at_form_9_s_chapter_once_form_9_is_done(self):
        # #777 (spec #774 acceptance 22), in place of #294's none: test_chapter_in_place_edit.
        form_9 = reverse("guide_chapter", args=["form-9"])
        self.assertNotContains(self.client.get(form_9), self.NOTICE)
        self.at_the_notice()
        self.assertContains(self.client.get(form_9), self.NOTICE)

    def test_an_answer_not_offered_shows_form_9_again_with_its_error(self):
        response = self.answer("form-9", "form_9_done", "maybe")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.FORM_9)
        self.assertContains(response, 'class="text-danger field-error')
        self.assertIsNone(self.aid().form_9_done)


def radios(markup, name):
    """Each radio for the field name: (value, wording, checked) in order."""
    found = re.findall(
        rf'<label[^>]*><input type="radio" name="{name}" value="([^"]+)"([^>]*)>\s*([^<]+)</label>',
        markup,
    )
    return [(value, wording.strip(), " checked" in attrs) for value, attrs, wording in found]


class FittingRouteTests(TestCase):
    """#295 (spec #291 acceptance 11, 18): 配戴之後 asks when the current pair was first worn;
    which ear only when the notice approved one ear, and for someone who did not come through
    form 9 and the notice also the ear, the subsidy and, with 用身障補助, its level. #779: asked
    at its chapter's foot, as my guide no longer draws the route."""

    DATE = "這副助聽器哪一天開始戴？"
    DATE_HELP = "可以看購買收據或保固書上的日期"
    EAR = "戴哪一耳？"
    SUBSIDY = "有沒有用身障補助買？"
    LEVEL = "補助的等級是？"

    def setUp(self):
        self.user = consented_user(username="fitting_route_user")
        self.client.force_login(self.user)
        self.make(PTA_55, PTA_55)
        for chapter in ("before-you-go", "types-and-prices"):
            GuideChapterView.objects.create(user=self.user, chapter=chapter)

    make = test_guide_summary.GuideSummaryTests.make
    marks = RouteQuestionTests.marks
    legends = Form9AndNoticeRouteTests.legends

    def stop(self, slug, query=""):
        """The stop's question or answer at its chapter's foot."""
        return chapter_foot(self.client, slug, query)

    def without_the_notice(self):
        # 沒有: 九號表 and the notice are folded away (#596), so 您在這裡 is 配戴之後.
        AidAndSubsidy.objects.create(user=self.user, certificate="no_subsidy")

    def test_without_the_notice_it_asks_the_date_the_ear_the_subsidy_and_the_level(self):
        self.without_the_notice()
        stop = self.stop("after-fitting")
        self.assertEqual(self.marks("after-fitting"), ["您在這裡"])
        self.assertIn('<input type="hidden" name="stop" value="after-fitting">', stop)
        self.assertRegex(stop, rf'<label for="id_fitted_on"[^>]*>{self.DATE}</label>')
        self.assertIn(self.DATE_HELP, stop)
        today = timezone.localdate().isoformat()
        self.assertRegex(stop, rf'<input type="date" name="fitted_on"[^>]* max="{today}"')
        self.assertEqual(self.legends(stop), [self.EAR, self.SUBSIDY, self.LEVEL])
        self.assertEqual(
            radios(stop, "ear"),
            [("left", "左耳", False), ("right", "右耳", False), ("both", "雙耳", False)],
        )
        self.assertEqual(
            radios(stop, "subsidy"),
            [("disability", "用身障補助", False), ("other", "自費或其他補助", False)],
        )
        levels = [value for value, _, _ in radios(stop, "level")]
        self.assertEqual(levels, ["basic", "mid", "advanced", "cros", "unknown"])
        self.assertIn(
            '<fieldset class="mb-4" data-fitting-level data-shown-with="disability"', stop
        )
        # At a chapter's foot the save button is the solid one (on the route it was outlined).
        self.assertIn('<button type="submit" class="btn btn-primary btn-lg">儲存</button>', stop)
        self.assertNotIn("還沒開始戴", stop)

    def with_the_notice(self, ears):
        AidAndSubsidy.objects.create(
            user=self.user,
            certificate="yes",
            form_9_done=True,
            notice_received=True,
            approved_ears=ears,
            level="mid",
        )

    def test_the_notice_s_one_ear_asks_left_or_right_and_nothing_it_answered(self):
        self.with_the_notice("one")
        stop = self.stop("after-fitting")
        self.assertEqual(self.marks("after-fitting"), ["您在這裡"])
        self.assertEqual(self.legends(stop), [self.EAR])
        self.assertEqual(radios(stop, "ear"), [("left", "左耳", False), ("right", "右耳", False)])
        self.assertNotIn('name="subsidy"', stop)
        self.assertNotIn('name="level"', stop)

    def test_the_notice_s_both_ears_asks_only_the_date(self):
        self.with_the_notice("both")
        stop = self.stop("after-fitting")
        self.assertIn(self.DATE, stop)
        self.assertEqual(self.legends(stop), [])

    def fit(self, **answers):
        data = {"stop": "after-fitting", **answers}
        return self.client.post(reverse("route_answer"), data)

    def aid(self):
        return AidAndSubsidy.for_user(self.user)

    def test_the_date_and_answers_are_kept_and_it_is_done(self):
        self.without_the_notice()
        took_ioi_ha(self.user, date(2026, 5, 1))  # 配戴之後 needs it too (ADR 0074)
        response = self.fit(fitted_on="2026-05-01", ear="left", subsidy="disability", level="mid")
        chapter = "/guide/after-fitting#stop-question"
        self.assertRedirects(response, chapter, fetch_redirect_response=False)
        aid = self.aid()
        self.assertEqual(
            (aid.fitted_on, aid.ear, aid.subsidy, aid.level),
            (date(2026, 5, 1), "left", "disability", "mid"),
        )
        self.assertEqual(self.marks("after-fitting"), ["已完成"])
        card = self.stop("after-fitting")
        self.assertIn(f"{CARD_TITLE}已記下：2026/05/01 開始戴、左耳、用身障補助、中階型</h2>", card)
        self.assertIn('<a href="/guide/after-fitting?edit=1#stop-question"', card)

    def test_paying_otherwise_keeps_no_level(self):
        self.without_the_notice()
        self.fit(fitted_on="2026-05-01", ear="both", subsidy="other", level="mid")
        aid = self.aid()
        self.assertEqual((aid.subsidy, aid.level), ("other", ""))
        self.assertIn("2026/05/01 開始戴、雙耳、自費或其他補助", self.stop("after-fitting"))

    def test_without_the_notice_the_subsidy_must_be_answered(self):
        # Spec #291 Q16: nothing is kept, and the error is beside the subsidy question.
        self.without_the_notice()
        response = self.fit(fitted_on="2026-05-01", ear="left")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        subsidy = content[content.index(self.SUBSIDY) : content.index(self.LEVEL)]
        self.assertIn("請選擇有沒有用身障補助", subsidy)
        self.assertIn('class="text-danger field-error', subsidy)
        aid = self.aid()
        self.assertEqual((aid.fitted_on, aid.ear), (None, ""))

    def test_the_date_and_the_subsidy_are_enough(self):
        self.without_the_notice()
        took_ioi_ha(self.user, date(2026, 5, 1))  # with the IOI-HA ADR 0074 asks for
        self.fit(fitted_on="2026-05-01", subsidy="other")
        self.assertEqual(self.marks("after-fitting"), ["已完成"])
        self.assertIn("已記下：2026/05/01 開始戴、自費或其他補助</h2>", self.stop("after-fitting"))

    def test_the_notice_s_both_ears_are_kept_as_both(self):
        self.with_the_notice("both")
        self.fit(fitted_on="2026-05-01")
        aid = self.aid()
        self.assertEqual((aid.fitted_on, aid.ear, aid.level), (date(2026, 5, 1), "both", "mid"))
        self.assertIn("2026/05/01 開始戴、雙耳", self.stop("after-fitting"))

    def test_the_notice_s_one_ear_keeps_the_ear_chosen_and_the_notice_s_level(self):
        self.with_the_notice("one")
        self.fit(fitted_on="2026-05-01", ear="right")
        aid = self.aid()
        self.assertEqual((aid.ear, aid.subsidy, aid.level), ("right", "", "mid"))

    def test_the_notice_s_one_ear_cannot_be_both(self):
        self.with_the_notice("one")
        response = self.fit(fitted_on="2026-05-01", ear="both")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="text-danger field-error')
        self.assertIsNone(self.aid().fitted_on)

    def test_a_date_after_today_or_none_shows_the_question_again(self):
        self.without_the_notice()
        tomorrow = timezone.localdate() + timedelta(days=1)
        for fitted_on, error in ((tomorrow.isoformat(), "開始配戴日期不能是未來"), ("", None)):
            with self.subTest(fitted_on=fitted_on):
                response = self.fit(fitted_on=fitted_on, ear="left")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.DATE)
                self.assertContains(response, 'class="text-danger field-error')
                if error:
                    self.assertContains(response, error)
                aid = self.aid()
                self.assertEqual((aid.fitted_on, aid.ear), (None, ""))

    def test_today_is_allowed(self):
        self.without_the_notice()
        self.fit(fitted_on=timezone.localdate().isoformat(), subsidy="other")
        self.assertEqual(self.aid().fitted_on, timezone.localdate())

    def test_edit_opens_it_filled_with_not_fitted_yet(self):
        self.without_the_notice()
        self.fit(fitted_on="2026-05-01", ear="left", subsidy="disability", level="mid")
        stop = self.stop("after-fitting", "?edit=1")
        self.assertRegex(stop, r'<input type="date" name="fitted_on" value="2026-05-01"')
        self.assertEqual(radios(stop, "ear")[0], ("left", "左耳", True))
        self.assertEqual(radios(stop, "subsidy")[0], ("disability", "用身障補助", True))
        self.assertEqual(radios(stop, "level")[1], ("mid", "中階型", True))
        self.assertIn(
            '<button type="submit" name="not_fitted" value="1" '
            'class="btn btn-outline-primary btn-lg">還沒開始戴</button>',
            stop,
        )

    def test_not_fitted_yet_clears_what_it_asked_and_takes_the_done_away(self):
        self.without_the_notice()
        self.fit(fitted_on="2026-05-01", ear="left", subsidy="disability", level="mid")
        self.fit(fitted_on="2026-05-01", ear="left", not_fitted="1")
        aid = self.aid()
        self.assertEqual(
            (aid.fitted_on, aid.ear, aid.subsidy, aid.level, aid.certificate),
            (None, "", "", "", "no_subsidy"),
        )
        self.assertEqual(self.marks("after-fitting"), ["您在這裡"])
        self.assertNotIn("已記下", self.stop("after-fitting"))

    def test_not_fitted_yet_keeps_the_notice_s_answers(self):
        self.with_the_notice("both")
        self.fit(fitted_on="2026-05-01")
        self.fit(not_fitted="1")
        aid = self.aid()
        self.assertEqual(
            (aid.fitted_on, aid.ear, aid.notice_received, aid.approved_ears, aid.level),
            (None, "", True, "both", "mid"),
        )

    def test_the_level_s_script_comes_with_the_level_question(self):
        self.without_the_notice()
        self.assertIn("screening/frontend/fitting-level.js", self.stop("after-fitting"))
        # The notice's level answered, the level is not asked (#779: at the chapter's foot).
        AidAndSubsidy.objects.filter(user=self.user).update(
            certificate="yes", form_9_done=True, notice_received=True, approved_ears="both"
        )
        AidAndSubsidy.objects.filter(user=self.user).update(level="mid")
        self.assertNotIn("fitting-level.js", self.stop("after-fitting"))


class FittingChapterTests(TestCase):
    """#295 (spec #291 Q13): the 配戴之後 chapter ends with the same question while it is
    unanswered, and 已記下 once the date is filled in."""

    def setUp(self):
        self.user = consented_user(username="fitting_chapter_user")
        self.client.force_login(self.user)
        AidAndSubsidy.objects.create(user=self.user, certificate="no_subsidy")

    def card(self):
        content = self.client.get(reverse("guide_chapter", args=["after-fitting"])).content
        content = content.decode()
        return content[content.index('<section id="stop-question"') : content.index("<footer")]

    def test_unanswered_it_asks_and_answering_goes_back_to_it(self):
        chapter = "/guide/after-fitting#stop-question"
        card = self.card()
        self.assertIn(FittingRouteTests.DATE, card)
        self.assertIn(f'<input type="hidden" name="next" value="{chapter}">', card)
        data = {
            "stop": "after-fitting",
            "fitted_on": "2026-05-01",
            "ear": "both",
            "subsidy": "other",
            "next": chapter,
        }
        response = self.client.post(reverse("route_answer"), data)
        self.assertRedirects(response, chapter, fetch_redirect_response=False)
        self.assertIn("已記下：2026/05/01 開始戴、雙耳、自費或其他補助", self.card())

    def test_a_date_after_today_shows_the_chapter_again_with_its_error(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        data = {
            "stop": "after-fitting",
            "fitted_on": tomorrow.isoformat(),
            "next": "/guide/after-fitting#stop-question",
        }
        response = self.client.post(reverse("route_answer"), data)
        self.assertContains(response, "開始配戴日期不能是未來")
        self.assertContains(response, '<h1 class="bird-title">配戴助聽器之後</h1>')


class Form25RouteTests(TestCase):
    """#296 (spec #291 acceptance 16, 18): 二十五號表 asked at the foot of its chapter; 完成了
    moves on to 等待補助發放, which is never done. #779: my guide no longer draws the route, so
    its state is read as every page reads it."""

    QUESTION = "二十五號表完成了嗎？"
    CHAPTER = "/guide/form-25#stop-question"

    def setUp(self):
        self.user = consented_user(username="form_25_route_user")
        self.client.force_login(self.user)
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 5, 1), subsidy="disability", level="mid"
        )
        took_ioi_ha(self.user, date(2026, 5, 1))  # 配戴之後 done (ADR 0074)

    marks = RouteQuestionTests.marks
    answer = Form9AndNoticeRouteTests.answer
    aid = Form9AndNoticeRouteTests.aid

    def chapter_card(self):
        return chapter_foot(self.client, "form-25")

    def test_done_moves_on_to_the_payout_which_is_never_done(self):
        response = self.answer("form-25", "form_25_done", "True")
        self.assertRedirects(response, self.CHAPTER, fetch_redirect_response=False)
        self.assertIs(self.aid().form_25_done, True)
        self.assertEqual(self.marks("form-25"), ["已完成"])
        self.assertEqual(self.marks("payout"), ["您在這裡"])

    def test_not_yet_stays_here(self):
        self.answer("form-25", "form_25_done", "False")
        self.assertIs(self.aid().form_25_done, False)
        self.assertEqual(self.marks("form-25"), ["您在這裡"])

    def test_not_yet_after_done_takes_the_done_away(self):
        self.answer("form-25", "form_25_done", "True")
        self.answer("form-25", "form_25_done", "False")
        self.assertEqual(self.marks("form-25"), ["您在這裡"])
        self.assertEqual(self.marks("payout"), [])

    def test_not_fitted_yet_takes_form_25_s_done_away_for_the_next_pair(self):
        self.answer("form-25", "form_25_done", "True")
        fit = FittingRouteTests.fit
        fit(self, not_fitted="1")
        fit(self, fitted_on="2026-05-01", ear="both", subsidy="disability", level="mid")
        self.assertIsNone(self.aid().form_25_done)
        self.assertEqual(self.marks("form-25"), ["您在這裡"])
        self.assertNotIn("已記下", self.chapter_card())

    def test_an_answer_not_offered_shows_form_25_again_with_its_error(self):
        response = self.answer("form-25", "form_25_done", "maybe")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.QUESTION)
        self.assertIsNone(self.aid().form_25_done)

    def test_the_chapter_asks_too_and_answering_comes_back_to_already_kept(self):
        card = self.chapter_card()
        self.assertIn(self.QUESTION, card)
        self.assertIn("看完了嗎？", card)
        self.assertIn(f'<input type="hidden" name="next" value="{self.CHAPTER}">', card)
        response = self.answer("form-25", "form_25_done", "True", next_url=self.CHAPTER)
        self.assertRedirects(response, self.CHAPTER, fetch_redirect_response=False)
        card = self.chapter_card()
        self.assertIn(f"{CARD_TITLE}已記下：二十五號表完成了</h2>", card)
        # #777: 修改 opens it again on the chapter itself.
        edit = reverse("guide_chapter", args=["form-25"]) + "?edit=1#stop-question"
        label = "修改二十五號表：使用效益驗證的回答"
        self.assertIn(f'<a href="{edit}" aria-label="{label}">修改</a>', card)
