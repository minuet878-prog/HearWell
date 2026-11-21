import re
from html import unescape

from django.test import TestCase

from screening.tests.helpers import consented_user, submission_with_answers

DOOR_SCRIPT = "screening/frontend/door-count.js"


def words(html):
    """The words a screen reader reads in this piece of HTML: what is aria-hidden, tags and runs
    of spaces gone."""
    html = re.sub(r'<(span|svg)[^>]*aria-hidden="true".*?</\1>', " ", html, flags=re.S)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def doors(content):
    """The (address, kind, words) of each door under the blue hero card."""
    return [
        (href, kind, words(body))
        for href, kind, body in re.findall(
            r'<a class="link-card home-door" href="([^"]+)" data-door="([^"]+)">(.*?)</a>',
            content,
            re.S,
        )
    ]


def hero_card(content):
    return re.search(r'<section class="hero-card"[^>]*>(.*?)</section>', content, re.S).group(1)


class SignedOutHomeTests(TestCase):
    """Spec #741 acceptance 42 and 43 (#752, the canvas's ProGuest, grill P14, P15): someone not
    signed in sees the bird, the blue hero card that starts a questionnaire, and two doors under
    it; a guest result kept in the browser goes above the card."""

    def setUp(self):
        content = self.client.get("/").content.decode()
        self.main = content[content.index("<main") : content.index("</main>")]

    def test_the_bird_says_changes_in_hearing_are_easily_missed(self):
        bird = re.search(r'<div class="bird-dialogue">.*?</h1>', self.main, re.S).group(0)
        self.assertIn('<p class="bird-lead">您好，歡迎來到聽伴。</p>', bird)
        self.assertIn('<h1 class="bird-title">聽力變化常常容易被忽略</h1>', bird)

    def test_the_hero_card_asks_and_starts_a_questionnaire_without_an_account(self):
        card = hero_card(self.main)
        self.assertIn('<h2 class="hero-card-title">想了解自己的聽力？</h2>', card)
        chips = re.findall(r'<span class="hero-chip">(.*?)</span>', card, re.S)
        self.assertEqual([words(chip) for chip in chips], ["大約 3 分鐘", "不用註冊"])
        start = re.findall(
            r'<a class="btn btn-hero btn-lg" href="([^"]+)" data-door="([^"]+)">(.*?)</a>',
            card,
            re.S,
        )
        self.assertEqual(
            [(href, kind, words(body)) for href, kind, body in start],
            [("/questionnaire_list", "door_self", "開始")],
        )

    def test_two_doors_under_the_card_go_to_the_family_zone_and_the_guide(self):
        self.assertEqual(
            doors(self.main),
            [
                ("/family", "door_family", "擔心家人的聽力"),
                ("/guide", "door_aids", "想了解助聽器"),
            ],
        )
        self.assertLess(self.main.index("</section>"), self.main.index("home-door"))

    def test_no_login_link_and_none_of_the_old_doors(self):
        for gone in (
            "我已經有帳號，登入",
            "我想了解自己的聽力",
            "我擔心家人的聽力",
            "看看可以怎麼幫他",
            ">了解助聽器選配與補助<",
            "從一份問卷開始",
            "empty-preview",
        ):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, self.main)

    def test_what_stays_below_the_doors(self):
        last_door = self.main.rindex("home-door")
        for kept in (
            "data-hide-in-app><a",  # 加到手機主畫面 (P13), hidden in the home-screen app
            "內容由台灣執業聽力師設計與審定。",
        ):
            with self.subTest(kept=kept):
                self.assertIn(kept, self.main[last_door:])

    def test_the_page_counts_presses_of_the_start_button_and_both_doors(self):
        # P15: 想了解助聽器 counted with the other two (door-count.js sends data-door).
        page = self.client.get("/").content.decode()
        self.assertIn(DOOR_SCRIPT, page)
        self.assertEqual(
            re.findall(r'data-door="([^"]+)"', self.main), ["door_self", "door_family", "door_aids"]
        )

    def test_a_kept_guest_result_goes_above_the_hero_card_under_the_bird(self):
        # Acceptance 43 (P14): guest-home.js fills it from the browser (guest-home.test.js).
        place = self.main.index('<div id="guest-home"')
        self.assertLess(self.main.index('<div class="bird-dialogue">'), place)
        self.assertLess(place, self.main.index('<section class="hero-card"'))


class SignedInHomeKeepsNoDoorsTests(TestCase):
    """Acceptance 14 and 15 (grill Q3): a signed-in user's home is as it was, with no doors."""

    fixtures = ("questions_fixture.json",)  # HHIE-S

    def test_signed_in_without_a_record_still_starts_from_a_questionnaire(self):
        self.client.force_login(consented_user(username="new_user"))
        content = self.client.get("/").content.decode()
        self.assertIn("從一份問卷開始", content)
        self.assertIn(">開始篩檢<", content)
        self.assertEqual(doors(content), [])
        self.assertNotIn(DOOR_SCRIPT, content)

    def test_signed_in_with_a_record_sees_the_care_journey_without_doors(self):
        user = consented_user(username="with_a_record")
        submission_with_answers(user, "hhie-s", [4] * 10)
        self.client.force_login(user)
        content = self.client.get("/").content.decode()
        self.assertIn("照顧旅程", content)
        self.assertEqual(doors(content), [])
        self.assertNotIn(DOOR_SCRIPT, content)
