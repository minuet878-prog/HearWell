"""診間小卡 (spec #677, ADR 0066): the two card addresses printed in the QR codes, kept forever,
each landing on its card's page with the card's mark; the landing page counts the scan."""

import re
import threading
from unittest.mock import patch

import segno
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext

from screening.models import GuestMonth, User
from screening.public_pages import is_public
from screening.tests import test_guest_counts
from screening.tests.helpers import consented_user, submission_with_answers

ELDER_CARD = "/c/e"
FAMILY_CARD = "/c/f"


class CardAddressTests(TestCase):
    """Spec #677 acceptance 1: each card address lands on its card's page, with the card's mark."""

    def test_the_elder_card_lands_on_the_wizards_age_step(self):
        response = self.client.get(ELDER_CARD)
        self.assertRedirects(
            response, "/questionnaire_list?via=clinic-elder", fetch_redirect_response=False
        )

    def test_the_family_card_lands_on_the_family_zone(self):
        response = self.client.get(FAMILY_CARD)
        self.assertRedirects(response, "/family?via=clinic-family", fetch_redirect_response=False)

    def test_a_signed_in_user_lands_there_too_before_agreeing_to_the_privacy_notice(self):
        # Acceptance 2: the same address, which shows a signed-in user the catalogue; the
        # consent gate stops them on the landing page, where the mark waits for them, not here.
        self.client.force_login(User.objects.create_user(username="pat", password="x"))
        for card, landing in (
            (ELDER_CARD, "/questionnaire_list?via=clinic-elder"),
            (FAMILY_CARD, "/family?via=clinic-family"),
        ):
            with self.subTest(card=card):
                response = self.client.get(card)
                self.assertRedirects(response, landing, fetch_redirect_response=False)

    def test_a_signed_in_user_who_agreed_sees_what_the_screening_tab_shows(self):
        # Acceptance 2 (cross review): followed through, the elder card shows a signed-in user
        # the page the 篩檢 tab opens (the wizard until they have a record, ADR 0030).
        self.client.force_login(consented_user(username="pat", password="x"))
        response = self.client.get(ELDER_CARD, follow=True)
        self.assertEqual(response.redirect_chain, [("/questionnaire_list?via=clinic-elder", 302)])
        heading = re.compile(r"<h1[^>]*>([^<]+)</h1>")
        from_the_tab = self.client.get("/questionnaire_list").content.decode()
        self.assertEqual(heading.findall(response.content.decode()), heading.findall(from_the_tab))
        self.assertEqual(len(heading.findall(from_the_tab)), 1)

    def test_anything_added_to_the_address_is_dropped(self):
        # Acceptance 3: only the fixed landing, whatever comes after the address.
        for card, landing in (
            (ELDER_CARD, "/questionnaire_list?via=clinic-elder"),
            (FAMILY_CARD, "/family?via=clinic-family"),
        ):
            with self.subTest(card=card):
                added = {"next": "https://example.com/", "via": "send"}
                response = self.client.get(card, added)
                self.assertRedirects(response, landing, fetch_redirect_response=False)

    def test_opening_the_address_counts_nothing(self):
        # Acceptance 4: a link preview fetches the address too; only the landing page counts.
        self.client.get(ELDER_CARD)
        self.client.get(FAMILY_CARD)
        self.assertFalse(GuestMonth.objects.exists())

    def test_only_get_is_answered(self):
        self.assertEqual(self.client.post(ELDER_CARD).status_code, 405)

    def test_kept_out_of_search_and_the_sitemap(self):
        # Acceptance 5: noindex, not a 公開頁面, not in the sitemap; robots.txt keeps out nothing.
        for card in (ELDER_CARD, FAMILY_CARD):
            with self.subTest(card=card):
                self.assertEqual(self.client.get(card)["X-Robots-Tag"], "noindex")
                self.assertFalse(is_public(card))
                self.assertNotIn(card, self.client.get("/sitemap.xml").content.decode())
        self.assertNotIn("Disallow", self.client.get("/robots.txt").content.decode())


class ReturningUserLandingTests(TestCase):
    """Acceptance 2 (cross review, second round): a signed-in user with a record lands on the
    questionnaire catalogue, 選問卷, which the elder card's address takes them to."""

    fixtures = ("questions_fixture.json",)  # HHIE-S

    def test_a_user_with_a_record_sees_the_catalogue(self):
        user = consented_user(username="pat", password="x")
        submission_with_answers(user, "hhie-s", [4] * 10)
        self.client.force_login(user)
        response = self.client.get(ELDER_CARD, follow=True)
        self.assertEqual(response.redirect_chain, [("/questionnaire_list?via=clinic-elder", 302)])
        headings = re.findall(r"<h1[^>]*>([^<]+)</h1>", response.content.decode())
        self.assertEqual(headings, ["選問卷"])


GUEST_COUNTS = "/api/guest-counts/"


class ScanCountTests(TestCase):
    """Acceptance 10 and 12: the landing page sends the card's kind once; each card has its own
    column of the 訪客月計數, and a kind the site does not know adds nothing."""

    def send(self, kind):
        return self.client.post(GUEST_COUNTS, {"kind": kind}, content_type="application/json")

    def counts(self):
        # Every column, so one card adding to another's, or to the guests', shows.
        return list(
            GuestMonth.objects.values_list(
                "month",
                "completed",
                "saved_password",
                "saved_google",
                "saved_line",
                "clinic_elder",
                "clinic_family",
            )
        )

    def test_each_card_adds_one_to_its_own_column_this_month(self):
        self.assertEqual(self.send("clinic_elder").status_code, 204)
        self.assertEqual(self.send("clinic_family").status_code, 204)
        self.assertEqual(self.send("clinic_family").status_code, 204)
        self.assertEqual(self.counts(), [(test_guest_counts.this_month(), 0, 0, 0, 0, 1, 2)])

    def test_two_sent_at_the_same_moment_both_count(self):
        # Acceptance 11: the one is added in the database (UPDATE ... SET x = x + 1), never read
        # here and written back, so a second scan in the same moment cannot be written over.
        self.send("clinic_elder")
        with CaptureQueriesContext(connection) as queries:
            self.send("clinic_elder")
        updates = [q["sql"] for q in queries if q["sql"].startswith("UPDATE")]
        self.assertEqual(len(updates), 1, updates)
        added_in_place = r'SET "clinic_elder" = \("screening_guestmonth"\."clinic_elder" \+ '
        self.assertRegex(updates[0], added_in_place)
        self.assertEqual(GuestMonth.objects.get().clinic_elder, 2)

    def test_sixty_an_hour_from_one_address_then_nothing_is_added(self):
        # Security check 2026-11-19 (the owner's pick, over the grill's Q15): a flood would
        # only make the numbers wrong, but it also writes to the database each time.
        cache.clear()
        self.addCleanup(cache.clear)
        for _ in range(60):
            self.assertEqual(self.send("clinic_elder").status_code, 204)
        self.assertEqual(self.send("clinic_elder").status_code, 429)
        self.assertEqual(GuestMonth.objects.get().clinic_elder, 60)

    def test_a_kind_it_does_not_know_is_refused_and_adds_nothing(self):
        for kind in ("send", "completed", "", None):
            with self.subTest(kind=kind):
                self.assertEqual(self.send(kind).status_code, 400)
        self.assertFalse(GuestMonth.objects.exists())


ARRIVAL_SCRIPT = "screening/frontend/arrival-count.js"


class LandingPageTests(TestCase):
    """Acceptance 7 and 8: each landing page loads the script that counts the card's mark and
    takes it off, for a guest and for a signed-in user alike."""

    def test_the_landing_pages_load_the_counting_script(self):
        signed_in = consented_user(username="pat", password="x")
        for who in ("guest", "signed in"):
            if who == "signed in":
                self.client.force_login(signed_in)
            for landing in ("/questionnaire_list?via=clinic-elder", "/family?via=clinic-family"):
                with self.subTest(who=who, landing=landing):
                    response = self.client.get(landing)
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, ARRIVAL_SCRIPT)


PRINT_PAGE = "/clinic-cards"


class PrintPageTests(TestCase):
    """Acceptance 14-19 (the #678 mockup's C and P): a sheet of 10 cards of one kind, the QR
    codes pointing at the live site's card address."""

    def cards(self, response):
        return re.findall(r'<div class="clinic-card" data-card="(\w+)"', response.content.decode())

    def test_a_guest_opens_a_sheet_of_ten_elder_cards(self):
        response = self.client.get(PRINT_PAGE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.cards(response), ["elder"] * 10)

    def test_the_family_card_fills_the_sheet_when_chosen(self):
        self.assertEqual(
            self.cards(self.client.get(PRINT_PAGE, {"card": "family"})), ["family"] * 10
        )

    def test_a_card_it_does_not_know_is_the_elder_card(self):
        for card in ("other", ""):
            with self.subTest(card=card):
                response = self.client.get(PRINT_PAGE, {"card": card})
                self.assertEqual(self.cards(response), ["elder"] * 10)

    def test_the_two_choices_on_top_switch_without_javascript(self):
        # The mockup's P: two links, the one shown marked as the current choice.
        page = self.client.get(PRINT_PAGE, {"card": "family"}).content.decode()
        choices = re.findall(r'<a class="clinic-cards-choice"([^>]*)>([^<]+)</a>', page)
        self.assertEqual(
            choices,
            [
                (' href="/clinic-cards?card=elder"', "長輩卡"),
                (' href="/clinic-cards?card=family" aria-current="page"', "家屬卡"),
            ],
        )


def qr_drawing(address):
    """The squares of a QR code holding address, as the print page should draw it."""
    code = segno.make(address, error="m", micro=False)
    return re.search(r'class="qrline"[^>]* d="([^"]+)"', code.svg_inline(border=4)).group(1)


@override_settings(SITE_URL="https://tingpal.tw")
class QrCodeTests(TestCase):
    """Acceptance 16, 17 and 24: each card's QR code holds the live site's 小卡網址, drawn here."""

    def drawings(self, response):
        # The dark squares' path; the white border is a path of its own.
        return re.findall(r'class="qrline"[^>]* d="([^"]+)"', response.content.decode())

    def test_each_card_holds_its_address_on_the_live_site(self):
        for card, address in (
            ("elder", "https://tingpal.tw/c/e"),
            ("family", "https://tingpal.tw/c/f"),
        ):
            with self.subTest(card=card):
                response = self.client.get(PRINT_PAGE, {"card": card})
                self.assertEqual(self.drawings(response), [qr_drawing(address)] * 10)
                # Read out as what it opens.
                self.assertContains(response, f"<title>QR code：{address}</title>", count=10)

    def test_opened_from_another_address_it_still_holds_the_live_sites(self):
        for card, path in (("elder", "/c/e"), ("family", "/c/f")):
            with self.subTest(card=card):
                response = self.client.get(PRINT_PAGE, {"card": card}, HTTP_HOST="localhost")
                drawn = [qr_drawing(f"https://tingpal.tw{path}")] * 10
                self.assertEqual(self.drawings(response), drawn)

    def test_each_code_has_its_white_border(self):
        # Acceptance 21: version 2 is 25 squares a side; 4 white squares round it make 33.
        page = self.client.get(PRINT_PAGE).content.decode()
        self.assertEqual(page.count('viewBox="0 0 33 33"'), 10)
        self.assertEqual(page.count('<path fill="#fff" d="M0 0h33v33h-33z"/>'), 10)
        self.assertEqual(re.findall(r'class="qrline"[^>]* d="(M4 4\.5)', page), ["M4 4.5"] * 10)

    def test_drawn_here_by_segno_without_calling_out(self):
        # Acceptance 24: segno is installed with the site, and nothing leaves the server.
        requirements = (settings.BASE_DIR / "requirements.txt").read_text()
        self.assertRegex(requirements, r"(?m)^segno==")
        with patch("socket.socket.connect", side_effect=AssertionError("called out")):
            response = self.client.get(PRINT_PAGE)
        self.assertEqual(len(self.drawings(response)), 10)

    @override_settings(SITE_URL="https://staging.example.test")
    def test_the_codes_follow_the_live_sites_address_set(self):
        # Acceptance 16 (cross review): the address comes from SITE_URL, not a fixed one, for
        # both cards, opened from that site or from another address.
        for card, path in (("elder", "/c/e"), ("family", "/c/f")):
            address = f"https://staging.example.test{path}"
            for host in ("testserver", "localhost"):
                with self.subTest(card=card, host=host):
                    response = self.client.get(PRINT_PAGE, {"card": card}, HTTP_HOST=host)
                    self.assertEqual(self.drawings(response), [qr_drawing(address)] * 10)
                    self.assertContains(response, f"<title>QR code：{address}</title>", count=10)

    @override_settings(SITE_URL="")
    def test_without_the_live_sites_address_it_says_so_and_draws_none(self):
        response = self.client.get(PRINT_PAGE)
        self.assertEqual(self.drawings(response), [])
        self.assertContains(response, "沒有設定正式網址，印出來的 QR code 不能用")


# Spec #677 acceptance 25: the owner's words from #679, as written, line breaks and all.
OWNERS_WORDS = {
    "elder": {
        "title": "花 3 分鐘，看看<br>聽力對生活的影響",
        "free": "不用註冊・免費",
        "sees": "回答 10 題，<br>馬上看到結果和建議",
        "camera": "用手機相機掃",
    },
    "family": {
        "title": "陪家人一起<br>面對聽力問題",
        "free": "不用註冊・免費",
        "sees": "怎麼跟他說話、陪他看診、<br>助聽器怎麼照顧",
        "camera": "用手機相機掃",
    },
}


class PrintPageReachTests(TestCase):
    """Acceptance 14, 15, 18 and 19: who opens the print page, how the owner finds it, and what a
    card never says."""

    def test_open_before_agreeing_to_the_privacy_notice(self):
        self.client.force_login(User.objects.create_user(username="pat", password="x"))
        self.assertEqual(self.client.get(PRINT_PAGE).status_code, 200)

    def test_kept_out_of_search_and_the_sitemap(self):
        self.assertEqual(self.client.get(PRINT_PAGE)["X-Robots-Tag"], "noindex")
        self.assertFalse(is_public(PRINT_PAGE))
        self.assertNotIn(PRINT_PAGE, self.client.get("/sitemap.xml").content.decode())

    def test_no_page_of_the_site_links_to_it(self):
        for page in ("/", "/learn", "/family", "/about", "/privacy", "/questionnaire_list"):
            with self.subTest(page=page):
                self.assertNotContains(self.client.get(page), PRINT_PAGE)

    def test_the_admins_home_links_to_it(self):
        self.client.force_login(User.objects.create_superuser(username="owner", password="pw"))
        self.assertContains(self.client.get("/admin/"), f'href="{PRINT_PAGE}"')

    # Its own SITE_URL: without one no QR code is drawn (acceptance 17), and CI sets none.
    @override_settings(SITE_URL="https://tingpal.tw")
    def test_every_card_says_only_its_words_with_its_own_code(self):
        # Acceptance 15 (cross review, second round): each of the 10 cards of both kinds, read
        # as its words alone, is the logo's 聽伴, the owner's words and tingpal.tw, nothing
        # more, so a name or a workplace added anywhere on it shows; each has one QR code.
        for kind, words in OWNERS_WORDS.items():
            expected = "".join(
                part.replace("<br>", "")
                for part in ("聽伴", words["title"], words["free"], words["sees"])
            ) + "".join((words["camera"], "tingpal.tw"))
            page = self.client.get(PRINT_PAGE, {"card": kind}).content.decode()
            cards = page.split('<div class="clinic-card" data-card=')[1:]
            self.assertEqual(len(cards), 10)
            for number, card in enumerate(cards, start=1):
                with self.subTest(card=kind, number=number):
                    self.assertEqual(card.count('class="qrline"'), 1)
                    self.assertIn('class="clinic-card-logo"', card)
                    shown = re.sub(r"<svg.*?</svg>", "", card, flags=re.S)
                    shown = re.sub(r"<[^>]+>|\s", "", shown.split(">", 1)[1])
                    self.assertEqual(shown, expected.replace(" ", ""))


class CardWordsTests(TestCase):
    """Spec #677 acceptance 25: each card says the owner's words."""

    def test_each_card_says_the_owners_words(self):
        for card, words in OWNERS_WORDS.items():
            page = self.client.get(PRINT_PAGE, {"card": card}).content.decode()
            for part, text in words.items():
                with self.subTest(card=card, part=part):
                    self.assertEqual(page.count(f'<p class="clinic-card-{part}">{text}</p>'), 10)


class SimultaneousScanTests(TransactionTestCase):
    """Acceptance 11 (cross review): two scans sent at the same moment, from two threads with
    their own database connections, both count, even into a month with no row yet."""

    def test_two_sent_at_once_both_count(self):
        both_ready = threading.Barrier(2)
        answers = []

        def scan():
            try:
                both_ready.wait(timeout=5)
                answers.append(
                    Client()
                    .post(GUEST_COUNTS, {"kind": "clinic_elder"}, content_type="application/json")
                    .status_code
                )
            finally:
                connection.close()

        scans = [threading.Thread(target=scan) for _ in range(2)]
        for each in scans:
            each.start()
        for each in scans:
            each.join(timeout=10)
        self.assertEqual(answers, [204, 204])
        self.assertEqual(GuestMonth.objects.get().clinic_elder, 2)
