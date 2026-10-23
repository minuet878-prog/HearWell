import re

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from screening.models import AidAndSubsidy, GuideChapterView, User
from screening.tests import test_guide, test_guide_summary
from screening.tests.helpers import consented_user

ROUTE_STOP = "/guide#stop-assessment"
CHAPTER_CARD = "/guide/assessment#stop-question"
PTA_55 = test_guide_summary.PTA_55
QUESTION = "您有聽覺機能的身心障礙證明嗎？"
ANSWERS = (
    ("yes", "有"),
    ("applying", "還沒有，正在申請鑑定"),
    ("no_subsidy", "沒有，不申請身障補助"),
)


def buttons(markup):
    """Each answer button's (value, wording, filled) in order."""
    found = re.findall(
        r'<button type="submit" name="certificate" value="([^"]+)" class="btn btn-lg '
        r'(btn-primary|btn-outline-primary)">([^<]+)</button>',
        markup,
    )
    return [(value, wording, kind == "btn-primary") for value, kind, wording in found]


def offered(filled=None):
    return [(value, wording, value == filled) for value, wording in ANSWERS]


class RouteAnswerTests(TestCase):
    """#293 (spec #291 acceptance 7, 28): one POST takes a stop's answer, for request.user
    only, signed in and consented, and goes back to where it was asked."""

    def setUp(self):
        self.user = consented_user(username="answering_user")
        self.client.force_login(self.user)

    def post(self, certificate="yes", next_url=ROUTE_STOP, client=None, stop="assessment"):
        data = {"stop": stop, "certificate": certificate, "next": next_url}
        return (client or self.client).post(reverse("route_answer"), data)

    def certificate(self, user=None):
        aid = AidAndSubsidy.for_user(user or self.user)
        return aid and aid.certificate

    def test_each_answer_is_kept_and_goes_back_to_the_stop(self):
        for answer in ("yes", "applying", "no_subsidy"):
            with self.subTest(answer=answer):
                response = self.post(answer)
                self.assertRedirects(response, ROUTE_STOP, fetch_redirect_response=False)
                self.assertEqual(self.certificate(), answer)
        self.assertEqual(AidAndSubsidy.objects.count(), 1)

    def test_from_a_chapter_it_goes_back_to_the_chapter_s_question(self):
        response = self.post(next_url=CHAPTER_CARD)
        self.assertRedirects(response, CHAPTER_CARD, fetch_redirect_response=False)

    def test_another_site_s_next_goes_to_the_stop_instead(self):
        response = self.post(next_url="https://example.com/guide")
        self.assertRedirects(response, ROUTE_STOP, fetch_redirect_response=False)
        self.assertEqual(self.certificate(), "yes")

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
    """#293 (spec #291 acceptance 6, 7, 18, 20): the question opens at the 目前這一站; an
    answered stop says the answer in short with 修改, which opens the question again."""

    def setUp(self):
        self.user = consented_user(username="route_question_user")
        self.client.force_login(self.user)
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")

    make = test_guide_summary.GuideSummaryTests.make

    def page(self, query=""):
        return self.client.get(reverse("guide") + query).content.decode()

    def stop(self, slug, query=""):
        stop = r'<li class="route-stop[^"]*" data-stop="([^"]+)"[^>]*>(.*?)</li>'
        return dict(re.findall(stop, self.page(query), re.S))[slug]

    def marks(self, slug):
        return re.findall(r'<span class="route-mark">([^<]+)</span>', self.stop(slug))

    def answer(self, certificate):
        data = {"stop": "assessment", "certificate": certificate, "next": ROUTE_STOP}
        self.client.post(reverse("route_answer"), data)

    def assert_question(self, markup, filled=None):
        self.assertIn(f'<legend class="font-bold text-xl/normal">{QUESTION}</legend>', markup)
        self.assertIn("第二類 b230、s260，或舊制 02", markup)
        self.assertIn('<input type="hidden" name="stop" value="assessment">', markup)
        self.assertIn(f'<input type="hidden" name="next" value="{ROUTE_STOP}">', markup)
        self.assertEqual(buttons(markup), offered(filled))

    def test_here_at_the_assessment_it_opens_the_question(self):
        self.assertEqual(self.marks("assessment"), ["您在這裡"])
        self.assert_question(self.stop("assessment"))
        self.assertEqual(self.page().count("<fieldset"), 1)

    def test_a_stop_that_is_not_here_keeps_its_question_closed(self):
        GuideChapterView.objects.filter(user=self.user).delete()
        self.assertNotIn(QUESTION, self.page())

    def test_having_one_marks_it_done_says_so_and_offers_to_change_it(self):
        self.answer("yes")
        self.assertEqual(self.marks("assessment"), ["已完成"])
        self.assertEqual(self.marks("form-9"), ["您在這裡"])
        assessment = self.stop("assessment")
        self.assertNotIn(QUESTION, assessment)
        edit = reverse("guide") + "?edit=assessment#stop-assessment"
        self.assertRegex(
            assessment,
            rf'<p class="route-answer">有身障證明 <a href="{re.escape(edit)}"[^>]*>修改</a></p>',
        )

    def test_applying_stays_here_says_so_and_keeps_the_question_open(self):
        self.answer("applying")
        self.assertEqual(self.marks("assessment"), ["您在這裡"])
        assessment = self.stop("assessment")
        self.assertIn('<p class="route-answer">正在申請鑑定</p>', assessment)
        self.assert_question(assessment, filled="applying")

    def test_not_applying_marks_the_subsidy_s_stops_not_applicable_and_pale(self):
        self.answer("no_subsidy")
        self.assertIn('<p class="route-answer">不申請身障補助 <a', self.stop("assessment"))
        page = self.page()
        for slug in ("form-9", "notice", "form-25", "payout"):
            with self.subTest(stop=slug):
                self.assertEqual(self.marks(slug), ["不適用"])
                self.assertRegex(page, rf'<li class="route-stop is-na" data-stop="{slug}"')
        self.assertEqual(self.marks("types-and-prices"), ["您在這裡"])
        self.assertEqual(page.count("is-na"), 4)

    def test_edit_opens_the_question_again_with_the_current_answer(self):
        self.answer("yes")
        assessment = self.stop("assessment", "?edit=assessment")
        self.assertIn('<p class="route-answer">有身障證明</p>', assessment)
        self.assert_question(assessment, filled="yes")

    def test_changing_to_applying_takes_the_done_away(self):
        self.answer("yes")
        self.answer("applying")
        self.assertEqual(self.marks("assessment"), ["您在這裡"])
        self.assertEqual(self.marks("form-9"), [])

    def test_an_edit_of_a_stop_without_a_question_opens_nothing(self):
        self.answer("yes")
        for edit in ("form-9", "nonsense"):
            with self.subTest(edit=edit):
                self.assertNotIn(QUESTION, self.page(f"?edit={edit}"))

    def test_signed_out_there_is_no_question(self):
        self.client.logout()
        self.assertNotIn(QUESTION, self.page("?edit=assessment"))
        self.assertNotIn('class="route-answer"', self.page())

    def test_once_answered_the_estimate_below_the_threshold_is_left_out(self):
        self.user.audiograms.all().delete()
        self.make((30, 30, 30, 30), (20, 20, 20, 20))
        self.assertEqual(self.marks("assessment"), ["您在這裡", "估算未達門檻"])
        self.answer("applying")
        self.assertEqual(self.marks("assessment"), ["您在這裡", "估算未達門檻"])
        self.answer("no_subsidy")
        self.assertEqual(self.marks("assessment"), ["已完成"])
        self.assertNotIn("看沒有身障證明時", self.stop("assessment"))


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
        self.assertIn('<h2 id="stop-question-title" class="h4">看完了嗎？</h2>', card)
        self.assertIn(QUESTION, card)
        self.assertIn(f'<input type="hidden" name="next" value="{CHAPTER_CARD}">', card)
        self.assertEqual(buttons(card), offered())
        self.assertIn("答了之後，選配路線會往下一站走。", test_guide.text_of(response))

    def test_answering_there_goes_back_to_it_and_the_question_is_gone(self):
        data = {"stop": "assessment", "certificate": "applying", "next": CHAPTER_CARD}
        response = self.client.post(reverse("route_answer"), data)
        self.assertRedirects(response, CHAPTER_CARD, fetch_redirect_response=False)
        self.assertNotContains(self.page(), QUESTION)

    def test_an_answer_not_offered_shows_the_chapter_again_with_its_error(self):
        data = {"stop": "assessment", "certificate": "maybe", "next": CHAPTER_CARD}
        response = self.client.post(reverse("route_answer"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1 class="h3 mt-4">身障鑑定與鑑定醫院</h1>')
        self.assertContains(response, 'class="text-danger field-error')
        self.assertContains(
            response, 'aria-describedby="id_certificate_helptext id_certificate_error"'
        )
        self.assertFalse(AidAndSubsidy.objects.exists())

    def test_other_chapters_ask_nothing_yet(self):
        for slug in ("before-you-go", "form-9", "types-and-prices", "after-fitting", "form-25"):
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


class CertificateMigrationTests(TransactionTestCase):
    """#293: #284's yes / not yet becomes the three answers; 還沒有 stays at the stop."""

    before = (("screening", "0027_guide_chapter_view"),)
    after = (("screening", "0028_aid_certificate_answer"),)

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
