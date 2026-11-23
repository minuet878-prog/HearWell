"""#754 (spec #741 acceptance 51, 56; P22, P23): the 了解 page's stacked cards, one for each of
its items, the one most about the 現在這一步 first (the hearing loss simulator when not logged in
or about none of them); below them the whole list."""

import re
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import Questionnaire, Submission
from screening.questionnaires import thi
from screening.tests.helpers import consented_user, read_site_css

CARD = re.compile(
    r'<article class="hero-card card-stack-card learn-card" role="group" '
    r'aria-roledescription="卡片" '
    r'aria-label="([^"]+)"[^>]*>(.*?)</article>',
    re.S,
)
ROW = re.compile(r'<li><a class="link-card action-card" href="([^"]*)">')

SIMULATOR = "第 1 張，共 5 張：聽損模擬"
GUIDE = "第 1 張，共 5 張：了解助聽器選配與補助"
QA = "第 1 張，共 5 張：問答小助手"


class LearnStackTests(TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S, IOI-HA

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())  # HHIA-S, THI

    def thi_record(self, user, wearing=None):
        Submission.objects.create(
            user=user,
            questionnaire=Questionnaire.objects.get(code=thi.CODE),
            wearing_hearing_aid=wearing,
        )

    def page(self):
        response = self.client.get(reverse("learn"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        return response, content[content.index("<main") : content.index("</main>")]

    def stack(self, main):
        start = main.index('<section class="card-stack"')
        return main[start : main.index("</section>", start)]

    def cards(self, main):
        return CARD.findall(self.stack(main))

    def first_card(self):
        _, main = self.page()
        return self.cards(main)[0][0]

    def test_not_logged_in_the_simulator_first_then_every_other_item(self):
        # Acceptance 51: not logged in, the first card is the hearing loss simulator.
        _, main = self.page()
        self.assertEqual(
            [name for name, _ in self.cards(main)],
            [
                SIMULATOR,
                "第 2 張，共 5 張：了解助聽器選配與補助",
                "第 3 張，共 5 張：家人專區",
                "第 4 張，共 5 張：問答小助手",
                "第 5 張，共 5 張：關於聽伴",
            ],
        )

    def test_each_card_has_its_title_its_line_its_drawing_and_its_white_button(self):
        _, main = self.page()
        body = self.cards(main)[0][1]
        # The canvas's ProLearn card: its sound wave plays once (ADR 0077), then the words.
        self.assertIn('class="hero-wave play-once-wave" data-play-in-view', body)
        self.assertIn('<h2 class="hero-card-title text-balance">聽損模擬</h2>', body)
        self.assertIn("<p>了解聽損者的感覺</p>", body)
        self.assertRegex(
            body,
            rf'<a class="btn btn-hero btn-lg" href="{reverse("hearing_loss_simulator")}">聽聽看',
        )
        # The owner (2026-11-21, at acceptance): the words on these cards centred.
        css = read_site_css()
        self.assertRegex(css, r"\.learn-card \{[^}]*text-align: center;")
        # Its line bigger than body text (owner, 2026-11-21): 22px at the 18px root.
        self.assertRegex(css, r"\.learn-card > p \{[^}]*font-size: 1\.2222rem;")
        # And the simulator's wave no taller than the other cards' drawings, so the words lead.
        self.assertRegex(css, r"\.learn-card \.hero-wave \{[^}]*height: 2\.6667rem;")
        # Every card its own drawing, each playing once when its card comes to the front.
        drawings = [re.search(r"<svg[^>]*>", body).group() for _, body in self.cards(main)]
        self.assertEqual(len(set(drawings)), 5)
        for drawing in drawings:
            with self.subTest(drawing=drawing):
                self.assertIn("data-play-in-view", drawing)

    def test_the_cards_behind_wait_inert_until_brought_to_the_front(self):
        # Without JavaScript the first card shows alone (site.css); the ones behind it are inert
        # from the start, so in-view.js holds their drawings until card-stack.js brings each
        # forward.
        _, main = self.page()
        cards = re.findall(r"<article [^>]*>", self.stack(main))
        self.assertNotIn(" inert", cards[0])
        for card in cards[1:]:
            with self.subTest(card=card):
                self.assertIn(" inert", card)
        self.assertIn('<div class="card-stack-controls" hidden>', main)
        self.assertIn("第 1 張，共 5 張", main)

    def test_below_the_cards_the_whole_list(self):
        # Acceptance 51: the whole list under the stack, every item, in the list's order.
        _, main = self.page()
        list_start = main.index("<ul", main.index("</section>", main.index("card-stack")))
        self.assertEqual(
            ROW.findall(main[list_start:]),
            [
                reverse("guide"),
                reverse("family_guide"),
                reverse("hearing_loss_simulator"),
                reverse("qa_home"),
                reverse("about"),
            ],
        )
        # The canvas's rows: a line under the title where it has one.
        rows = re.findall(
            r'<span class="link-card-title">([^<]*)</span>\s*(?:<span>([^<]*)</span>)?',
            main[list_start:],
        )
        self.assertEqual(
            rows,
            [
                # The owner (2026-11-21): every row a line, this one its card's.
                ("了解助聽器選配與補助", "從聽力檢查到申請補助"),
                ("家人專區", "溝通與陪伴"),
                ("聽損模擬", "聽聽看他聽到的聲音"),
                ("問答小助手", "常見問題一次查"),
                ("關於聽伴", "誰做的、內容怎麼查核"),
            ],
        )

    def test_logged_in_at_step_5_the_guide_first(self):
        # Acceptance 51: wearing hearing aids starts the 照顧旅程 at step 5 (spec #741 acceptance
        # 28), so the guide to fitting and subsidies comes first.
        user = consented_user(username="learn_step_5", birth_year=1950)
        self.thi_record(user, wearing=True)
        self.client.force_login(user)
        response, main = self.page()
        names = [name for name, _ in self.cards(main)]
        self.assertEqual(names[0], GUIDE)
        self.assertEqual(
            names[1:],
            [
                # The rest in the list's order.
                "第 2 張，共 5 張：家人專區",
                "第 3 張，共 5 張：聽損模擬",
                "第 4 張，共 5 張：問答小助手",
                "第 5 張，共 5 張：關於聽伴",
            ],
        )
        # Picked from this account's records: never cached (CODING_STANDARDS 24).
        self.assertIn("no-store", response["Cache-Control"])

    def test_logged_in_without_records_the_simulator_first(self):
        self.client.force_login(consented_user(username="learn_no_records"))
        response, main = self.page()
        self.assertEqual(self.cards(main)[0][0], SIMULATOR)
        self.assertIn("no-store", response["Cache-Control"])

    def test_not_logged_in_it_may_be_cached(self):
        response, _ = self.page()
        self.assertNotIn("no-store", response.get("Cache-Control", ""))

    def test_each_step_s_first_card(self):
        # Spec #741 P23: the item most about each 現在這一步; about none of them, the simulator.
        # Any record opens the 照顧旅程 (as on the home page); which step it stands at is stood in.
        user = consented_user(username="learn_steps")
        self.thi_record(user)
        self.client.force_login(user)
        expected = {
            1: SIMULATOR,  # 填生活影響問卷
            2: QA,  # 到醫院進行聽力檢查: the assistant answers where to have one
            3: SIMULATOR,  # 記錄聽力圖
            4: GUIDE,  # 了解助聽器選配與補助
            5: GUIDE,  # 申請補助與配戴助聽器
            6: GUIDE,  # 戴滿 3 個月做效益問卷: the guide's 配戴之後 chapter
            7: SIMULATOR,  # 半年後再篩檢
        }
        for step, first in expected.items():
            with self.subTest(step=step):
                journey = SimpleNamespace(current=step)
                with mock.patch("screening.views.home.care_journey", return_value=journey):
                    self.assertEqual(self.first_card(), first)
