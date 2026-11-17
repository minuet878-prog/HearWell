"""Reading 「健康」's Apple hearing test PDF (spec #702, ticket #707), on made-up PDFs drawn like
the real one (apple_pdf.py): the owner's own stays out of this public repo."""

from datetime import date, datetime

from django.test import SimpleTestCase

from screening.apple_hearing_test import read
from screening.tests.apple_pdf import FREQUENCIES, LEFT, RIGHT, apple_pdf


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
