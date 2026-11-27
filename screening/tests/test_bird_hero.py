"""#749 (spec #741 acceptance 33, 34; ADR 0076): every page's title sits in the bird's speech
bubble under a lead line, and a page has at most one blue hero card, without a solid blue button
beside it."""

import re
from datetime import date
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone

from screening.models import Audiogram, Questionnaire, ReportShare, RetestReminder
from screening.page_leads import LEADS
from screening.tests.helpers import consented_user, submission_with_answers
from screening.views.accounts import RESET_EMAIL
from screening.views.guide import GUIDE_CHAPTERS
from screening.views.qa_assistant import RESULTS_SESSION_KEY

BIRD = re.compile(
    r'<div class="bird-dialogue"[^>]*>\s*<span class="bird-avatar" aria-hidden="true"></span>\s*'
    r'<div class="bird-bubble">.*?(?:<p class="bird-lead">(.+?)</p>\s*)?'
    r'<h1 class="bird-title"[^>]*>(.+?)</h1>',
    re.S,
)
HERO = re.compile(r'<section class="hero-card\b')
SOLID = re.compile(r'class="[^"]*\bbtn-primary\b')
TEMPLATES = Path(settings.BASE_DIR) / "screening" / "templates"


def _main(response):
    content = response.content.decode()
    return content[content.index("<main") : content.index("</main>")]


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def bird(response):
    """(lead, title) of the page's bird dialogue, as text, the lead None without one; None
    without a bird dialogue."""
    found = BIRD.search(_main(response))
    return found and (found[1] and _text(found[1]), _text(found[2]))


class BirdDialogueTests(TestCase):
    def test_login_title_is_in_the_bubble_under_the_canvas_lead(self):
        self.assertEqual(bird(self.client.get(reverse("login"))), ("歡迎回來。", "登入"))

    def test_account_lead_names_the_account(self):
        # The canvas's ProAccount: 「jason，這裡可以管理您的帳號。」
        self.client.force_login(consented_user(username="jason"))
        lead, title = bird(self.client.get(reverse("account_settings")))
        self.assertEqual((lead, title), ("jason，這裡可以管理您的帳號。", "帳號設定"))

    def test_every_lead_is_a_short_line(self):
        for key, lead in LEADS.items():
            with self.subTest(key=key):
                self.assertTrue(lead.strip())
                self.assertLessEqual(len(lead), 24)

    def test_no_page_template_writes_its_own_h1(self):
        """Every page's h1 comes from bird_dialogue.html; mails and the printed clinic cards
        are not pages of the site's look."""
        outside = {
            "bird_dialogue.html",
            "password_reset_email.html",
            "email_confirmation_email.html",
            "clinic_cards.html",
        }
        for path in TEMPLATES.rglob("*.html"):
            if path.name in outside:
                continue
            with self.subTest(template=str(path.relative_to(TEMPLATES))):
                self.assertFalse("<h1" in path.read_text())


ONE_LINE = {
    "index",
    "screening",
    "result",
    "guest_result",
    "register",
    "consent",
    "my_hearing",
    "audiogram_list",
    "audiogram_new",
    "audiogram_edit",
    "audiogram_detail",
    "qa_answer",
    "questionnaire_list",
    "health_report",
    "learn",
    "hhi_comparison",
}


class EveryPageTests(TestCase):
    """Walks the pages a GET reaches, signed in and not."""

    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        cls.user = consented_user(username="walker", birth_year=1950)
        cls.record = submission_with_answers(cls.user, "hhie-s", [2] * 10)
        cls.hhie = Questionnaire.objects.get(code="hhie-s")
        cls.audiogram = Audiogram.objects.create(user=cls.user, tested_on=date(2026, 3, 4))
        cls.share = ReportShare.objects.create(user=cls.user)
        cls.reminder = RetestReminder.objects.create(user=cls.user, enabled=True)

    def signed_in_pages(self):
        audiogram = [self.audiogram.pk]
        pages = [
            reverse("index"),
            reverse("questionnaire_list"),
            reverse("questionnaire_list") + "?wizard=1",
            reverse("questionnaire_list") + "?concern=life_impact",
            reverse("screening", args=[self.hhie.pk]),
            reverse("result", args=[self.record.pk]),
            reverse("hhi_comparison", args=[self.hhie.pk]),
            reverse("my_hearing"),
            reverse("audiogram_list"),
            reverse("audiogram_new"),
            reverse("audiogram_edit", args=audiogram),
            reverse("audiogram_import"),
            reverse("audiogram_compare"),
            reverse("audiogram_detail", args=audiogram),
            reverse("audiogram_delete", args=audiogram),
            reverse("audiogram_speech_banana", args=audiogram),
            reverse("health_report"),
            reverse("share_report"),
            reverse("learn"),
            reverse("guide"),
            *(reverse("guide_chapter", args=[chapter.slug]) for chapter in GUIDE_CHAPTERS),
            reverse("guide_subsidy"),
            reverse("family_guide"),
            reverse("family_talk"),
            reverse("family_reluctant"),
            reverse("family_signs"),
            reverse("family_hearing_aids"),
            reverse("family_visits"),
            reverse("family_subsidy_check"),
            reverse("family_deadlines"),
            reverse("hearing_loss_simulator"),
            reverse("qa_home"),
            reverse("qa_topic", args=["hearing-aids"]),
            reverse("qa_answer", args=["my-results"]),
            reverse("qa_results"),
            reverse("about"),
            reverse("privacy"),
            reverse("feedback"),
            reverse("add_to_home"),
            reverse("account_settings"),
            reverse("delete_account"),
            # 補上 email asks 確認本人 first.
            reverse("confirm_identity") + "?action=add_email",
        ]
        return pages

    def signed_out_pages(self):
        return [
            (reverse("index"), 200),
            (reverse("login"), 200),
            (reverse("register"), 200),
            (reverse("password_reset"), 200),
            (reverse("password_reset_sent"), 200),
            (reverse("password_reset_confirm", args=["MQ", "wrong-token"]), 200),
            (reverse("guest_result", args=["hhie-s"]), 200),
            (reverse("shared_cover", args=[self.share.token]), 200),
            (reverse("shared_report", args=[self.share.token]), 200),
            (reverse("shared_cover", args=["no-such-share"]), 404),
            (reverse("reminder_cancel", args=[self.reminder.cancel_token]), 200),
            (reverse("reminder_cancel", args=["no-such-reminder"]), 404),
            (reverse("reminder_cancelled"), 200),
            (reverse("email_confirm", args=["no-such-token"]), 404),
            ("/no-such-page", 404),
        ]

    def assert_page(self, response):
        found = bird(response)
        self.assertIsNotNone(found, "no bird dialogue")
        lead, title = found
        # The two home pages' bubbles are one line, as the canvas (spec #741's 實作中本人補充);
        # since the owner's 2026-11-27 walkthrough so are the wizard's, the answer page's, the
        # result pages', the register and consent pages', 我的紀錄's, the audiogram pages', a
        # Q&A answer's, the health report's, 了解's and the wearing comparison's.
        try:
            name = resolve(response.request["PATH_INFO"]).url_name
        except Resolver404:
            name = None
        # The questionnaire list's own page too (2026-11-27); its wizard's recommendation keeps
        # its lead 照您的回答，這一份最適合。
        query = response.request["QUERY_STRING"]
        recommends = name == "questionnaire_list" and "concern=" in query
        one_line = (name in ONE_LINE and not recommends) or (
            name == "questionnaire_list" and "wizard" in query
        )
        self.assertTrue(title, found)
        self.assertEqual(lead is None, one_line, found)
        main = _main(response)
        # The bubble's title is the page's one h1, and nothing above it is a heading.
        self.assertEqual(len(re.findall(r"<h1\b", main)), 1)
        self.assertLess(main.index('class="bird-dialogue"'), re.search(r"<h[1-6]\b", main).start())
        heroes = len(HERO.findall(main))
        self.assertLessEqual(heroes, 1)
        if heroes:
            self.assertIsNone(SOLID.search(main), "a solid blue button beside the hero card")

    def test_every_signed_in_page_has_the_bird_and_at_most_one_hero_card(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[RESULTS_SESSION_KEY] = []
        session.save()
        for url in self.signed_in_pages():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assert_page(response)

    def test_every_signed_out_page_has_the_bird_and_at_most_one_hero_card(self):
        session = self.client.session
        session[RESET_EMAIL] = "w@example.com"
        session.save()
        for url, status in self.signed_out_pages():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status)
                self.assert_page(response)

    def hero(self, url):
        main = _main(self.client.get(url))
        start = HERO.search(main).start()
        return main[start : main.index("</section>", start)]

    def test_each_page_s_one_thing_is_in_the_hero_card_with_a_white_button(self):
        """The 現在這一步, a result's 建議下一步 and the wizard's recommended questionnaire;
        the catalogue's is the first of its stacked cards (#753, test_card_stack)."""
        for user, url, words, button in (
            (self.user, reverse("index"), "現在這一步", None),
            (self.user, reverse("result", args=[self.record.pk]), "建議您下一步", None),
            (
                self.user,
                reverse("questionnaire_list") + "?concern=life_impact",
                "聽力對生活的影響",
                "開始作答",
            ),
        ):
            self.client.force_login(user)
            with self.subTest(url=url):
                card = self.hero(url)
                self.assertIn(words, card)
                found = re.search(
                    r'<a class="btn btn-hero btn-lg[^"]*" href="[^"]*">([^<]+)</a>', card
                )
                self.assertIsNotNone(found)
                if button:
                    self.assertEqual(found[1], button)

    def test_a_signed_in_home_without_records_and_the_consent_page(self):
        newcomer = consented_user(username="newcomer")
        self.client.force_login(newcomer)
        self.assert_page(self.client.get(reverse("index")))
        undecided = type(newcomer).objects.create_user(username="undecided")
        self.client.force_login(undecided)
        self.assert_page(self.client.get(reverse("consent")))

    def test_the_share_link_gone_past_its_day(self):
        ReportShare.objects.filter(pk=self.share.pk).update(expires_at=timezone.now())
        self.assert_page(self.client.get(reverse("shared_cover", args=[self.share.token])))
