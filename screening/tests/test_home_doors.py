import re
from html import unescape

from django.test import TestCase

from screening.tests.helpers import consented_user, submission_with_answers

DOOR_SCRIPT = "screening/frontend/door-count.js"


def doors(content):
    """The (address, kind, title, small words) of each door on the page."""
    found = re.findall(
        r'<a class="link-card action-card home-door" href="([^"]+)" data-door="([^"]+)">(.*?)</a>',
        content,
        re.S,
    )
    return [
        (
            href,
            kind,
            *[
                " ".join(unescape(re.sub(r"<[^>]+>", " ", part)).split())
                for part in re.findall(r'<span(?: class="link-card-title")?>([^<]*)</span>', body)
            ],
        )
        for href, kind, body in found
    ]


class SignedOutDoorsTests(TestCase):
    """Spec #655 acceptance 10–13 (#673): someone not signed in sees only the two doors first,
    with the owner's words (#671), each going to its place; what stays is below them."""

    def setUp(self):
        self.content = self.client.get("/").content.decode()

    def test_the_two_doors_with_the_owners_words_go_to_the_wizard_and_the_family_zone(self):
        self.assertEqual(
            doors(self.content),
            [
                ("/questionnaire_list", "door_self", "我想了解自己的聽力", "大約 3 分鐘，不用註冊"),
                ("/family", "door_family", "我擔心家人的聽力", "看看可以怎麼幫他"),
            ],
        )

    def test_the_doors_take_the_place_of_the_heading_preview_button_and_family_link(self):
        for gone in (
            "從一份問卷開始",
            "做完第一份問卷，這裡會排出您的照顧旅程",
            ">開始篩檢<",
            ">我是家人<",
        ):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, self.content)

    def test_below_the_doors_stay_sign_in_two_links_and_the_audiologist_line(self):
        last_door = self.content.rindex("home-door")
        for kept in (
            "我已經有帳號，登入",
            ">了解助聽器選配與補助<",
            "data-hide-in-app><a",  # 加到手機主畫面, hidden in the home-screen app
            "內容由台灣執業聽力師設計與審定。",
        ):
            with self.subTest(kept=kept):
                # Searched from the doors on: the page's description in its head says the last.
                self.assertIn(kept, self.content[last_door:])

    def test_the_page_has_its_heading_in_the_bird_s_bubble(self):
        # #749 (the canvas's ProGuest): seen now, no longer for screen readers only.
        self.assertIn('<h1 class="bird-title">聽力變化常常容易被忽略</h1>', self.content)

    def test_the_door_presses_are_counted_by_the_page(self):
        # Acceptance 23: the page sends the press; the doors stay plain links without it.
        self.assertIn(DOOR_SCRIPT, self.content)

    def test_an_unsaved_guest_result_stays_on_top_of_the_doors(self):
        # Acceptance 13: guest-home.js fills it from the browser.
        self.assertLess(self.content.index('id="guest-home"'), self.content.index("home-door"))


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
