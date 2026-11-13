"""Saving a guest's results from the save card (ticket #496, spec #492): the card on the guest
result page, its way through registering or logging in and the consent, and the save page that
sends every guest result kept in the browser to the records API."""

import json
import uuid
from io import StringIO
from urllib.parse import quote

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening import models
from screening.models import Consent, Questionnaire, Submission, User
from screening.questionnaires import hhia_s, hhie_s
from screening.tests.helpers import consented_user

GUEST_SCORE = "/api/guest-scores/"
SUBMISSIONS = "/api/submissions/"
SAVE_FROM_CARD = "/guest/save?from=card"
PASSWORD = "Fake-pass-2468"
MORE = "註冊後還有耳鳴、在吵雜環境聽不聽得清楚等問卷可以做。"
REASONS = {
    "normal": "註冊保存後，半年後會提醒您再做一次，跟這次的結果比一比。",
    "mild_to_moderate": (
        "註冊保存後，看完醫師可以接著記下聽力圖，網站會一步步帶您走助聽器選配與補助。"
    ),
    "severe": "註冊保存後，就醫拿到聽力圖可以記下來，網站會一步步帶您走助聽器選配與補助申請。",
}


class GuestSaveTestCase(TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S, IOI-HA

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())  # HHIA-S and the others
        cls.hhie_s = Questionnaire.objects.get(code=hhie_s.CODE)
        cls.hhia_s = Questionnaire.objects.get(code=hhia_s.CODE)

    def body(self, questionnaire, scores, wearing=False, **extra):
        questions = questionnaire.questions.order_by("question_number")
        return {
            "questionnaire": questionnaire.pk,
            "wearing_hearing_aid": wearing,
            "answers": [
                {"question": question.pk, "score": score}
                for question, score in zip(questions, scores, strict=True)
            ],
            **extra,
        }

    def guest_html(self, scores):
        response = self.client.post(
            GUEST_SCORE,
            json.dumps(self.body(self.hhie_s, scores, just_finished=False)),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["html"]

    def save(self, body, key):
        # What the save page sends for one guest result: its receipt number and the guest mark.
        return self.client.post(
            SUBMISSIONS,
            json.dumps(body),
            content_type="application/json",
            headers={"Idempotency-Key": str(key)},
        )

    def register_from_card(self, username="saver"):
        """Registering from the card's 註冊保存: its next is the save page from the card."""
        return self.client.post(
            f"{reverse('register')}?next={quote(SAVE_FROM_CARD, safe='')}",
            {
                "username": username,
                "email": f"{username}@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "next": SAVE_FROM_CARD,
            },
        )


class SaveCardTests(GuestSaveTestCase):
    """#492 acceptance 14: the save card says what saving brings at each level."""

    def test_says_what_saving_brings_at_each_level(self):
        for level, scores in (
            ("normal", [0] * 10),
            ("mild_to_moderate", [4, 4, 2, 0, 0, 0, 4, 0, 0, 2]),
            ("severe", [4] * 10),
        ):
            with self.subTest(level=level):
                html = self.guest_html(scores)
                self.assertIn('<h2 class="result-next-title">註冊保存這次結果</h2>', html)
                self.assertIn(REASONS[level], html)
                for other in set(REASONS) - {level}:
                    self.assertNotIn(REASONS[other], html)
                self.assertIn(MORE, html)

    def test_its_two_buttons_go_to_the_save_page_from_the_card(self):
        html = self.guest_html([0] * 10)
        next_part = "?next=%2Fguest%2Fsave%3Ffrom%3Dcard"
        self.assertIn(
            f'<a class="btn btn-primary btn-lg w-full" href="{reverse("register")}{next_part}">'
            "註冊保存</a>",
            html,
        )
        self.assertIn(
            f'<a class="btn btn-outline-primary btn-lg w-full" href="{reverse("login")}'
            f'{next_part}">登入保存</a>',
            html,
        )

    def test_at_its_bottom_how_long_it_stays_and_where(self):
        # The days are the browser's to fill (it alone knows when the result was finished).
        html = self.guest_html([0] * 10)
        self.assertIn("這次結果只存在這支手機上，還留 <span data-guest-days-left></span> 天", html)
        self.assertIn("換手機或換瀏覽器就看不到這次結果。", html)
        buttons = html.index("登入保存</a>")
        self.assertLess(buttons, html.index("data-guest-days-left"))
        self.assertLess(buttons, html.index("換手機或換瀏覽器就看不到這次結果。"))

    def test_after_the_one_sentence_where_the_journey_card_is(self):
        # B1: in the 照顧旅程 card's place, after the level's one sentence and before the fold.
        html = self.guest_html([0] * 10)
        card = html.index("註冊保存這次結果")
        self.assertLess(html.index('class="result-one-line"'), card)
        self.assertLess(card, html.index('class="result-list"'))


class FromTheCardTests(GuestSaveTestCase):
    """#492 acceptance 22, 23, 28, 29: from the card through registering or logging in and the
    consent, straight to the save page."""

    def consent_url(self):
        return f"{reverse('consent')}?next={quote(SAVE_FROM_CARD, safe='')}"

    def test_registering_agreeing_then_the_save_page(self):
        response = self.register_from_card()
        self.assertRedirects(response, self.consent_url(), fetch_redirect_response=False)
        response = self.client.post(self.consent_url(), {"agree": "", "next": SAVE_FROM_CARD})
        self.assertRedirects(response, SAVE_FROM_CARD, fetch_redirect_response=False)
        response = self.client.get(SAVE_FROM_CARD)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "guest-save.js")

    def test_logging_in_goes_straight_to_the_save_page(self):
        consented_user(username="has_account", password=PASSWORD)
        response = self.client.post(
            reverse("login"),
            {"username": "has_account", "password": PASSWORD, "next": SAVE_FROM_CARD},
        )
        self.assertRedirects(response, SAVE_FROM_CARD, fetch_redirect_response=False)
        self.assertEqual(self.client.get(SAVE_FROM_CARD).status_code, 200)

    def test_not_agreed_to_the_latest_notice_the_consent_comes_first(self):
        user = User.objects.create_user(username="old_consent", password=PASSWORD)
        Consent.objects.create(user=user, version=models.CONSENT_VERSION - 1)
        self.client.post(
            reverse("login"),
            {"username": "old_consent", "password": PASSWORD, "next": SAVE_FROM_CARD},
        )
        self.assertRedirects(
            self.client.get(SAVE_FROM_CARD), self.consent_url(), fetch_redirect_response=False
        )
        # Nor can the records API save it before then.
        key = uuid.uuid4()
        body = self.body(self.hhie_s, [4] * 10, from_guest=True)
        self.assertEqual(self.save(body, key).status_code, 403)
        self.assertFalse(Submission.objects.filter(user=user).exists())
        self.client.post(self.consent_url(), {"agree": "", "next": SAVE_FROM_CARD})
        self.assertEqual(self.client.get(SAVE_FROM_CARD).status_code, 200)
        self.assertEqual(self.save(body, key).status_code, 201)
        submission = Submission.objects.get(user=user)
        latest = user.consents.get(version=models.CONSENT_VERSION)
        self.assertGreaterEqual(submission.created_at, latest.agreed_at)

    def test_declining_logs_out_home_and_saves_nothing(self):
        self.register_from_card()
        response = self.client.post(reverse("consent"), {"decline": "", "next": SAVE_FROM_CARD})
        self.assertRedirects(response, reverse("index"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(Submission.objects.exists())

    def test_without_an_account_the_save_page_asks_to_log_in(self):
        response = self.client.get(SAVE_FROM_CARD)
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={quote(SAVE_FROM_CARD, safe='/')}",
            fetch_redirect_response=False,
        )


class SavePageTests(GuestSaveTestCase):
    """The save page (spec #492): signed in, never cached, with what guest-save.js needs."""

    def setUp(self):
        self.client.force_login(consented_user(username="page"))

    def test_never_cached_with_where_to_send_and_go(self):
        response = self.client.get(SAVE_FROM_CARD)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertContains(response, f'data-submissions-url="{SUBMISSIONS}"')
        self.assertContains(response, f'data-done-url="{reverse("my_hearing")}"')
        self.assertContains(response, f'data-home-url="{reverse("index")}"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_names_each_guest_questionnaire_for_a_failure(self):
        response = self.client.get(SAVE_FROM_CARD)
        self.assertContains(response, '<script id="guest-names" type="application/json">')
        names = json.loads(
            response.content.decode()
            .split('<script id="guest-names" type="application/json">')[1]
            .split("</script>")[0]
        )
        self.assertEqual(
            names,
            {
                hhie_s.CODE: "聽力對生活的影響（HHIE-S）",
                hhia_s.CODE: f"{hhia_s.DEFINITION.topic}（HHIA-S）",
            },
        )


class SavingTests(GuestSaveTestCase):
    """#492 acceptance 22, 24, 25: what the save page sends for each guest result, the records API
    as an account's answer page uses it plus the guest mark."""

    def setUp(self):
        self.user = consented_user(username="saving")
        self.client.force_login(self.user)

    def test_the_record_has_the_guest_results_scores_and_level_dated_today(self):
        scores = [4, 4, 2, 0, 0, 0, 4, 0, 0, 2]
        guest = self.client.post(
            GUEST_SCORE,
            json.dumps(self.body(self.hhie_s, scores, just_finished=False)),
            content_type="application/json",
        ).json()
        response = self.save(self.body(self.hhie_s, scores, from_guest=True), uuid.uuid4())
        self.assertEqual(response.status_code, 201)
        submission = Submission.objects.with_scores().get(user=self.user)
        self.assertEqual(submission.result.total, guest["scores"]["total"])
        self.assertEqual(submission.result.total, 16)
        self.assertEqual(submission.result.level["text"], guest["level"]["text"])
        self.assertEqual(timezone.localdate(submission.created_at), timezone.localdate())
        # 我的紀錄 lists it.
        self.assertContains(self.client.get(reverse("my_hearing")), "總分：16")

    def test_both_questionnaires_are_saved(self):
        self.save(self.body(self.hhie_s, [4] * 10, from_guest=True), uuid.uuid4())
        self.save(self.body(self.hhia_s, [2] * 10, from_guest=True), uuid.uuid4())
        self.assertEqual(
            set(self.user.submissions.values_list("questionnaire__code", flat=True)),
            {hhie_s.CODE, hhia_s.CODE},
        )

    def test_sent_again_with_its_receipt_number_one_record(self):
        key = uuid.uuid4()
        body = self.body(self.hhie_s, [4] * 10, from_guest=True)
        self.assertEqual(self.save(body, key).status_code, 201)
        again = self.save(body, key)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(self.user.submissions.count(), 1)
        self.assertEqual(again.json()["id"], self.user.submissions.get().pk)

    def test_the_guest_mark_is_a_boolean_and_optional(self):
        for value in ("yes", 1, None):
            with self.subTest(value=value):
                body = self.body(self.hhie_s, [4] * 10, from_guest=value)
                response = self.save(body, uuid.uuid4())
                self.assertEqual(response.status_code, 400)
                self.assertIn("from_guest", response.json())
        self.assertFalse(self.user.submissions.exists())
        # An account's own answer page sends none.
        self.assertEqual(self.save(self.body(self.hhie_s, [4] * 10), uuid.uuid4()).status_code, 201)


ASK_SCRIPT = 'src="/static/screening/frontend/guest-ask.js" data-ask-url="/guest/save"'


class GuestAskRedirectTests(GuestSaveTestCase):
    """#497 (#492 acceptance 26, 27): someone signed in by another way than the save card, with
    guest results in this browser, is taken to the save page's question on opening a page;
    guest-ask.js looks in the browser, the page only carries it."""

    def test_pages_past_the_consent_and_the_home_page_carry_it(self):
        self.client.force_login(consented_user(username="asked"))
        for name in ("index", "questionnaire_list", "my_hearing"):
            with self.subTest(page=name):
                self.assertContains(self.client.get(reverse(name)), ASK_SCRIPT)

    def test_the_save_page_itself_does_not_so_it_cannot_loop(self):
        self.client.force_login(consented_user(username="saving_page"))
        for url in (reverse("guest_save"), SAVE_FROM_CARD):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), "guest-ask.js")

    def test_nor_the_consent_page_before_agreeing(self):
        # The save page needs the consent, so sending someone there from the consent would loop.
        self.client.force_login(User.objects.create_user(username="not_agreed"))
        response = self.client.get(reverse("consent"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "guest-ask.js")

    def test_nor_the_pages_open_before_agreeing(self):
        # Reading the notice or deleting the account must stay possible before agreeing.
        self.client.force_login(User.objects.create_user(username="reading"))
        for name in ("privacy", "account_settings", "delete_account", "family_guide"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "guest-ask.js")

    def test_nor_any_page_without_an_account(self):
        for name in ("index", "privacy", "login", "register"):
            with self.subTest(page=name):
                self.assertNotContains(self.client.get(reverse(name)), "guest-ask.js")


ASK_TITLE = '<h1 class="h3 mt-4">要把這次結果存到這個帳號嗎？</h1>'
YES = "要，存進這個帳號"
NO = "不要，清掉這次結果"


class GuestAskQuestionTests(GuestSaveTestCase):
    """#497 (the #493 mockup's F2): the save page not come from the card asks first; from the card
    it saves straight away (#492 acceptance 22, 23 unchanged)."""

    def setUp(self):
        self.client.force_login(consented_user(username="question"))

    def test_not_from_the_card_it_asks_with_what_each_answer_does(self):
        response = self.client.get(reverse("guest_save"))
        self.assertContains(response, ASK_TITLE)
        self.assertContains(response, "data-asking")
        self.assertContains(response, f"data-guest-ask-yes>{YES}</button>")
        self.assertContains(response, f"data-guest-ask-no>{NO}</button>")
        # Nothing is being saved until 要.
        self.assertContains(
            response,
            '<p data-guest-saving role="status" tabindex="-1" hidden>正在保存，請稍候。</p>',
        )
        self.assertIn("no-store", response["Cache-Control"])

    def test_from_the_card_it_saves_without_asking(self):
        response = self.client.get(SAVE_FROM_CARD)
        self.assertContains(response, '<h1 class="h3 mt-4">保存這次結果</h1>')
        self.assertContains(
            response, '<p data-guest-saving role="status" tabindex="-1">正在保存，請稍候。</p>'
        )
        self.assertNotContains(response, "data-asking")
        # Self-review B2: what was not saved takes focus, so it is read out.
        self.assertContains(response, 'role="alert" tabindex="-1" data-guest-failed-list')
        self.assertNotContains(response, YES)
        self.assertNotContains(response, NO)


class GuestAskOtherWaysInTests(GuestSaveTestCase):
    """#492 acceptance 26, 27: registering from the top's 註冊, or logging in to an account there
    already, ends on a page that takes a browser with guest results to the question; until 要
    the account has no new record."""

    def test_registering_from_the_top_then_agreeing_lands_where_it_is_asked(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "grandson",
                "email": "grandson@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        self.assertRedirects(response, reverse("consent"), fetch_redirect_response=False)
        response = self.client.post(reverse("consent"), {"agree": ""}, follow=True)
        self.assertEqual(response.resolver_match.url_name, "index")
        self.assertContains(response, ASK_SCRIPT)
        self.assertContains(self.client.get(reverse("guest_save")), ASK_TITLE)
        self.assertFalse(Submission.objects.exists())

    def test_logging_in_to_another_account_lands_where_it_is_asked(self):
        consented_user(username="another", password=PASSWORD)
        response = self.client.post(
            reverse("login"), {"username": "another", "password": PASSWORD}, follow=True
        )
        self.assertEqual(response.resolver_match.url_name, "index")
        self.assertContains(response, ASK_SCRIPT)
        self.assertContains(self.client.get(reverse("guest_save")), ASK_TITLE)
        self.assertFalse(Submission.objects.exists())

    def test_not_agreed_to_the_latest_notice_the_consent_comes_before_the_question(self):
        user = User.objects.create_user(username="old_notice", password=PASSWORD)
        Consent.objects.create(user=user, version=models.CONSENT_VERSION - 1)
        self.client.force_login(user)
        # The home page sends there all the same; the save page asks for the consent first.
        self.assertContains(self.client.get(reverse("index")), ASK_SCRIPT)
        save = reverse("guest_save")
        consent = f"{reverse('consent')}?next={quote(save, safe='')}"
        self.assertRedirects(self.client.get(save), consent, fetch_redirect_response=False)
        self.client.post(consent, {"agree": ""})
        self.assertContains(self.client.get(save), ASK_TITLE)
        self.assertFalse(Submission.objects.exists())
