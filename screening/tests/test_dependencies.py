"""Security check 2026-11-19, decision 1: the packages with known vulnerabilities stay at or
above the versions that fixed them."""

from importlib.metadata import version

from django.test import SimpleTestCase

FIXED_IN = {
    "certifi": "2026.10.18",  # GHSA-6q48-6c7w-9gw2
    "brotli": "1.2.1",  # GHSA-9v8h-qqgm-4m35
    "sqlparse": "0.6.0",  # GHSA-f2ff-p2ww-7p4p and others
}


def parts(number):
    return tuple(int(part) for part in number.split("."))


class FixedVersionTests(SimpleTestCase):
    def test_installed_at_or_above_the_fix(self):
        for package, fixed in FIXED_IN.items():
            with self.subTest(package):
                self.assertGreaterEqual(parts(version(package)), parts(fixed))
