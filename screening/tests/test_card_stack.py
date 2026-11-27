"""#753 (spec #741 acceptance 44, 45, 56, 58; P3, P4): the questionnaires page's stacked cards,
the 推薦問卷 first, then the ones that suit this person by age and hearing aids, at most three;
below them the whole catalogue, and 幫我選 in the bird's bubble."""

import re
import uuid
from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import AidAndSubsidy, Answer, Questionnaire, Submission
from screening.tests.helpers import consented_user

CARD = re.compile(
    r'<article class="hero-card card-stack-card" role="group" aria-roledescription="卡片" '
    r'aria-label="([^"]+)"(?: inert)?>(.*?)</article>',
    re.S,
)


class StackMixin:
    def login(self, age=70):
        user = consented_user(
            username=f"stack_{uuid.uuid4().hex[:8]}", birth_year=date.today().year - age
        )
        self.client.force_login(user)
        return user

    def record(self, user, code, *, wearing=None, days_ago=1):
        # Every item answered, so a card's 上次 can show its result.
        questionnaire = Questionnaire.objects.get(code=code)
        submission = Submission.objects.create(
            user=user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=0)
            for question in questionnaire.questions.all()
        )
        Submission.objects.filter(pk=submission.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )

    def page(self):
        return self.client.get(reverse("questionnaire_list")).content.decode()

    def stack(self, html):
        start = html.index('<section class="card-stack"')
        return html[start : html.index("</section>", start)]

    def cards(self, html):
        """Each card's accessible name, in order."""
        return [name for name, _ in CARD.findall(self.stack(html))]

    def start_url(self, code):
        return reverse("screening", args=[Questionnaire.objects.get(code=code).pk])


class CardStackTests(StackMixin, TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S, IOI-HA

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())  # HHIA-S, THI, SSQ12-TW, SADL

    def test_over_65_not_wearing_recommended_hhie_s_comes_first_without_hhia_s(self):
        # Acceptance 44: 70, only a THI record, so HHIE-S is recommended; not wearing, so no
        # IOI-HA or SADL either, and the ones for anyone follow in the catalogue's order.
        user = self.login(age=70)
        self.record(user, "thi")
        html = self.page()
        self.assertEqual(
            self.cards(html),
            [
                "第 1 張，共 3 張：聽力對生活的影響（HHIE-S）",
                "第 2 張，共 3 張：日常聆聽能力（SSQ12-TW）",
                "第 3 張，共 3 張：耳鳴對生活的影響（THI）",
            ],
        )
        stack = self.stack(html)
        self.assertNotIn("HHIA-S", stack)
        first = CARD.search(stack)[2]
        self.assertIn("推薦您做這一份", first)
        self.assertIn(f'<a class="btn btn-hero btn-lg" href="{self.start_url("hhie-s")}">', first)
        # The buttons and where one is, hidden until the script runs (no JavaScript: the first
        # card and the list).
        self.assertIn('<div class="card-stack-controls" hidden>', stack)
        self.assertIn('aria-label="上一張"', stack)
        self.assertIn('aria-label="下一張"', stack)
        self.assertIn(
            '<p class="card-stack-position" aria-live="polite">第 1 張，共 3 張</p>', stack
        )
        # The page is 問卷, and the whole catalogue stays below the stack.
        self.assertIn("<title>問卷\uff5c聽伴</title>", html)
        self.assertIn('<h1 class="bird-title">問卷</h1>', html)
        below = html[html.index("</section>", html.index('<section class="card-stack"')) :]
        self.assertEqual(below.count('<a class="link-card questionnaire-card"'), 6)

    def test_someone_wearing_hearing_aids_gets_the_hearing_aid_ones_three_at_most(self):
        # Worn and unaided records without IOI-HA recommend IOI-HA (#347); HHIE-S for the age
        # and SADL for the hearing aids follow, and SSQ12-TW and THI are past the three.
        user = self.login(age=70)
        self.record(user, "hhie-s", wearing=False, days_ago=30)
        self.record(user, "sadl", wearing=True)
        self.assertEqual(
            self.cards(self.page()),
            [
                "第 1 張，共 3 張：助聽器使用成效（IOI-HA）",
                "第 2 張，共 3 張：聽力對生活的影響（HHIE-S）",
                "第 3 張，共 3 張：助聽器滿意度（SADL）",
            ],
        )

    def test_a_fitting_date_counts_as_wearing_them(self):
        user = self.login(age=40)
        self.record(user, "hhia-s", wearing=False, days_ago=200)  # due again: HHIA-S
        AidAndSubsidy.objects.create(user=user, fitted_on=date.today() - timedelta(days=10))
        names = self.cards(self.page())
        self.assertEqual(names[0], "第 1 張，共 3 張：聽力對生活的影響（HHIA-S）")
        self.assertIn("IOI-HA", names[1])

    def test_without_a_recommendation_the_suitable_ones_still_stack(self):
        # A recent unaided HHIE-S (#339 acceptance 7): nothing recommended, none says so.
        user = self.login(age=70)
        self.record(user, "hhie-s", wearing=False, days_ago=30)
        html = self.page()
        self.assertEqual(
            self.cards(html),
            [
                "第 1 張，共 3 張：聽力對生活的影響（HHIE-S）",
                "第 2 張，共 3 張：日常聆聽能力（SSQ12-TW）",
                "第 3 張，共 3 張：耳鳴對生活的影響（THI）",
            ],
        )
        self.assertNotIn("推薦您做這一份", html)

    def test_help_me_choose_is_in_the_bird_s_bubble(self):
        user = self.login()
        self.record(user, "thi")
        html = self.page()
        bubble = html[html.index('<div class="bird-bubble">') : html.index("</h1>")]
        # Its lead went in the owner's 2026-11-27 walkthrough.
        self.assertNotIn("bird-lead", bubble)
        after = html[html.index("</h1>") :]
        pick = after[: after.index("</div>")]
        self.assertIn(f'href="{reverse("questionnaire_list")}?wizard=1"', pick)
        self.assertIn("幫我選", pick)
        self.assertEqual(html.count("?wizard=1"), 1)


class OneSuitableTests(StackMixin, TestCase):
    """Acceptance 45: only HHIE-S and IOI-HA exist, and IOI-HA does not suit someone not
    wearing hearing aids."""

    fixtures = ("questions_fixture.json",)

    def test_one_card_without_buttons(self):
        user = self.login(age=70)
        self.record(user, "hhie-s", wearing=False, days_ago=200)
        html = self.page()
        self.assertEqual(self.cards(html), ["第 1 張，共 1 張：聽力對生活的影響（HHIE-S）"])
        stack = self.stack(html)
        self.assertNotIn("card-stack-controls", stack)
        self.assertNotIn("上一張", stack)
        self.assertNotIn("下一張", stack)
