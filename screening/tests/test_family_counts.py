from django.test import TestCase

from screening.models import GuestMonth
from screening.tests import test_guest_counts

GUEST_COUNTS = "/api/guest-counts/"


class DoorAndSendCountTests(TestCase):
    """Spec #655 (#672): the two doors and opens from 傳給他 each add one to their own column of
    the 訪客月計數, through the counting API the clinic cards made (spec #677)."""

    def send(self, kind):
        return self.client.post(GUEST_COUNTS, {"kind": kind}, content_type="application/json")

    def counts(self):
        # Every column, so one kind adding to another's, or to the guests' or the cards', shows.
        return list(
            GuestMonth.objects.values_list(
                "month",
                "completed",
                "saved_password",
                "saved_google",
                "saved_line",
                "clinic_elder",
                "clinic_family",
                "door_self",
                "door_family",
                "send_opened",
            )
        )

    def test_each_kind_adds_one_to_its_own_column_this_month(self):
        self.assertEqual(self.send("door_self").status_code, 204)
        self.assertEqual(self.send("door_family").status_code, 204)
        self.assertEqual(self.send("door_family").status_code, 204)
        for _ in range(3):
            self.assertEqual(self.send("send_opened").status_code, 204)
        self.assertEqual(
            self.counts(), [(test_guest_counts.this_month(), 0, 0, 0, 0, 0, 0, 1, 2, 3)]
        )

    def test_a_kind_it_does_not_know_is_refused_and_adds_nothing(self):
        # Spec #655 acceptance 27, with names close to the three kinds.
        for kind in ("door", "send", "door_selves", "SEND_OPENED", "via=send"):
            with self.subTest(kind=kind):
                self.assertEqual(self.send(kind).status_code, 400)
        self.assertFalse(GuestMonth.objects.exists())

    def test_opening_a_page_or_the_api_counts_nothing(self):
        # Acceptance 26: only the page's own POST adds one, so a link preview or a search engine
        # fetching the home, the family zone or the address 傳給他 sends adds nothing.
        self.assertEqual(self.client.get(GUEST_COUNTS).status_code, 405)
        for address in ("/", "/family", "/questionnaire_list?via=send"):
            with self.subTest(address=address):
                self.assertEqual(self.client.get(address, follow=True).status_code, 200)
        self.assertFalse(GuestMonth.objects.exists())
