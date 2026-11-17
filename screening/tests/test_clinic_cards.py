"""診間小卡 (spec #677, ADR 0066): the two card addresses printed in the QR codes, kept forever,
each landing on its card's page with the card's mark; the landing page counts the scan."""

from unittest.mock import patch

from django.test import TestCase

from screening.models import GuestMonth, User
from screening.public_pages import is_public
from screening.tests import test_guest_counts
from screening.tests.helpers import consented_user

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
        # Acceptance 11: a second scan arrives after the first has found this month's row and
        # before it adds its one; both must count, as two scans in the same moment would.
        find_month = GuestMonth.objects.get_or_create
        second = []

        def second_scan_arrives(**fields):
            found = find_month(**fields)
            if not second:
                second.append(None)  # before sending: the second scan finds the row as well
                second[0] = self.send("clinic_elder")
            return found

        with patch.object(GuestMonth.objects, "get_or_create", side_effect=second_scan_arrives):
            self.send("clinic_elder")
        self.assertEqual(second[0].status_code, 204)
        self.assertEqual(GuestMonth.objects.get().clinic_elder, 2)

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
