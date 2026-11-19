"""Reading 「健康」's Apple hearing test PDF (spec #702, ticket #707), on made-up PDFs drawn like
the real one (apple_pdf.py): the owner's own stays out of this public repo."""

import resource
import sys
from datetime import date, datetime
from unittest import mock, skipUnless

from django.test import SimpleTestCase

from screening.apple_hearing_test import MAX_BYTES, CannotRead, Unreadable, read
from screening.tests.apple_pdf import FREQUENCIES, LEFT, RIGHT, apple_pdf, unpacking_pdf


def _points(right, left):
    return [
        {"ear": ear, "frequency": f, "db": db}
        for ear, values in (("right", right), ("left", left))
        for f, db in zip(FREQUENCIES, values, strict=True)
    ]


class ReadTests(SimpleTestCase):
    def test_reads_the_test_date_and_both_ears(self):
        """Spec #702 acceptance 1, 4: the test's own date, not the export's, and each ear's eight
        values as printed, 1 dB apart."""
        test = read(apple_pdf())
        self.assertEqual(test.tested_on, date(2026, 11, 10))
        self.assertCountEqual(test.points, _points(RIGHT, LEFT))

    def test_keeps_values_below_minus_ten(self):
        """Spec #702 acceptance 3."""
        right = (3, -2, 1, -6, -4, 2, -14, -8)
        left = (6, 4, 0, -3, -1, 5, -11, -20)
        test = read(apple_pdf(right=right, left=left, tested_at=datetime(2026, 1, 5, 9, 30)))
        self.assertEqual(test.tested_on, date(2026, 1, 5))
        self.assertCountEqual(test.points, _points(right, left))

    def test_values_without_an_asterisk(self):
        self.assertCountEqual(read(apple_pdf(stars=False)).points, _points(RIGHT, LEFT))

    def test_the_export_time_is_never_taken_for_the_test_date(self):
        """Spec #702 acceptance 4, should 輸出時間 ever carry a time of day."""
        test = read(apple_pdf(exported_on="2026年11月17日 上午9:05"))
        self.assertEqual(test.tested_on, date(2026, 11, 10))


class UnreadableTests(SimpleTestCase):
    """Spec #702 acceptance 7: each way a file cannot be read, with the reason the monthly
    failure counts keep."""

    def assertReason(self, data, reason):
        with self.assertRaises(CannotRead) as caught:
            read(data)
        self.assertEqual(caught.exception.reason, reason)

    def test_too_big_or_not_a_pdf(self):
        self.assertReason(b"%PDF" + b"0" * MAX_BYTES, Unreadable.NOT_A_PDF)
        self.assertReason("聽力測試".encode(), Unreadable.NOT_A_PDF)
        self.assertReason(b"%PDF-1.4 but broken", Unreadable.NOT_A_PDF)

    def test_not_an_apple_hearing_test(self):
        self.assertReason(apple_pdf(source="來源：其他App"), Unreadable.NOT_APPLE)
        # An iPhone in English prints its own words: only the Chinese page is known.
        self.assertReason(apple_pdf(source="Source: Apple Hearing Test"), Unreadable.NOT_APPLE)

    def test_a_layout_it_does_not_know(self):
        missing = (*RIGHT[:7], None)
        self.assertReason(apple_pdf(printed={"right": missing}), Unreadable.LAYOUT)
        self.assertReason(apple_pdf(extra=("left", 2000, "7*")), Unreadable.LAYOUT)

    def test_a_value_off_the_chart(self):
        """Nothing above 120 or below -20 dB can be saved, so it cannot be read either."""
        for right in ((125, *RIGHT[1:]), (*RIGHT[:7], -25)):
            with self.subTest(right=right):
                self.assertReason(apple_pdf(right=right), Unreadable.LAYOUT)

    def test_a_scale_upside_down(self):
        """0 dB must sit above 120 dB: otherwise the heights cannot be read as dB at all."""
        self.assertReason(apple_pdf(scale={0: 120, 120: 0}), Unreadable.LAYOUT)

    def test_a_test_date_still_to_come(self):
        self.assertReason(apple_pdf(tested_at=datetime(2099, 1, 5, 9, 30)), Unreadable.LAYOUT)

    def test_a_value_its_point_disagrees_with(self):
        """Printed 10 dB off where the curve is drawn: more than the 2 dB the check allows."""
        off = (RIGHT[0] + 10, *RIGHT[1:])
        self.assertReason(apple_pdf(printed={"right": off}), Unreadable.CROSS_CHECK)


def _peak_megabytes():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux counts it in kilobytes, macOS in bytes.
    return peak // 1024 if sys.platform == "linux" else peak // 1024 // 1024


class ReadingLimitTests(SimpleTestCase):
    """A PDF a few hundred KB long can unpack to more memory than the server has, which it
    shares with the database: the page is read in a process of its own, with limits."""

    def test_a_pdf_that_unpacks_huge_does_not_grow_this_process(self):
        before = _peak_megabytes()
        with self.assertRaises(CannotRead):
            read(unpacking_pdf(300 * 1024 * 1024))
        self.assertLess(_peak_megabytes() - before, 100)

    @skipUnless(sys.platform == "linux", "macOS does not enforce RLIMIT_AS; CI runs on Linux")
    def test_reading_stops_at_its_memory_limit(self):
        with self.assertRaises(CannotRead) as caught:
            read(unpacking_pdf(400 * 1024 * 1024))
        self.assertEqual(caught.exception.reason, Unreadable.NOT_A_PDF)

    def test_reading_too_long_is_given_up(self):
        with (
            mock.patch("screening.apple_hearing_test.READ_SECONDS", 0.001),
            self.assertRaises(CannotRead) as caught,
        ):
            read(apple_pdf())
        self.assertEqual(caught.exception.reason, Unreadable.NOT_A_PDF)


class ReminderTests(SimpleTestCase):
    """Spec #702 acceptance 5: what the preview reminds of; none of it is saved."""

    def test_each_reminder_only_when_the_pdf_says_so(self):
        test = read(apple_pdf(stars=True, congested=True, loud_noise=True))
        self.assertEqual((test.noise_marked, test.congested, test.loud_noise), (True, True, True))
        test = read(apple_pdf(stars=False))
        self.assertEqual(
            (test.noise_marked, test.congested, test.loud_noise), (False, False, False)
        )
