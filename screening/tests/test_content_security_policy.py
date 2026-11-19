"""Content-Security-Policy (security check 2026-11-19): a page runs only the site's own script
files and the inline scripts it wrote itself, each marked with that response's nonce, so a
script slipped into a page some other way does not run."""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from screening.tests.helpers import consented_user

TEMPLATES = Path(settings.BASE_DIR, "screening", "templates")
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)(?![^>]*application/json)([^>]*)>")


def policy_of(response):
    header = response["Content-Security-Policy"]
    return dict(part.strip().split(" ", 1) for part in header.split(";"))


class ContentSecurityPolicyTests(TestCase):
    def test_a_page_runs_only_the_sites_own_scripts(self):
        policy = policy_of(self.client.get(reverse("index")))
        self.assertEqual(policy["default-src"], "'self'")
        self.assertRegex(policy["script-src"], r"^'self' 'nonce-[\w-]{22,}'$")
        # ADR 0072: inline styles stay allowed (style="" attributes and Django admin's).
        self.assertEqual(policy["style-src"], "'self' 'unsafe-inline'")
        self.assertEqual(policy["object-src"], "'none'")
        self.assertEqual(policy["base-uri"], "'self'")
        self.assertEqual(policy["frame-ancestors"], "'none'")

    def test_each_inline_script_carries_the_responses_nonce(self):
        user = consented_user(username="wang_ming")
        self.client.force_login(user)
        response = self.client.get(reverse("index"))
        nonce = re.search(r"'nonce-([\w-]+)'", response["Content-Security-Policy"])[1]
        inline = INLINE_SCRIPT.findall(response.content.decode())
        self.assertTrue(inline)
        for attributes in inline:
            with self.subTest(attributes=attributes):
                self.assertIn(f'nonce="{nonce}"', attributes)

    def test_each_response_has_a_nonce_of_its_own(self):
        first = self.client.get(reverse("index"))["Content-Security-Policy"]
        second = self.client.get(reverse("index"))["Content-Security-Policy"]
        self.assertNotEqual(first, second)

    def test_the_admin_and_the_api_have_it_too(self):
        for url in (reverse("admin:login"), "/api/guest-counts/"):
            with self.subTest(url=url):
                self.assertIn("Content-Security-Policy", self.client.get(url))

    def test_every_inline_script_in_the_templates_carries_the_nonce(self):
        # A new inline script without it would not run: caught here, before a browser does.
        for template in TEMPLATES.rglob("*.html"):
            for attributes in INLINE_SCRIPT.findall(template.read_text(encoding="utf-8")):
                with self.subTest(template=template.relative_to(TEMPLATES)):
                    self.assertIn('nonce="{{ request.csp_nonce }}"', attributes)
