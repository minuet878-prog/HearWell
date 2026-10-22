"""Rules from CODING_STANDARDS.md that a test can check, so review does not have to."""

import ast
import re
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.urls.converters import IntConverter

from screening import questionnaires
from screening import urls as screening_urls
from screening.views import health_data_page

BASE_DIR = Path(settings.BASE_DIR)


def python_sources():
    for folder in ("config", "screening"):
        for path in sorted((BASE_DIR / folder).rglob("*.py")):
            if "migrations" not in path.parts:
                yield path


class SumDefaultTests(SimpleTestCase):
    """`Sum` without `default=0` returns None instead of 0 when there are no rows."""

    def test_every_sum_has_a_default(self):
        missing = []
        for path in python_sources():
            for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if name == "Sum" and not any(k.arg == "default" for k in node.keywords):
                    missing.append(f"{path.relative_to(BASE_DIR)}:{node.lineno}")
        self.assertEqual(missing, [], "Sum() needs default=0")


class FontSizeUnitTests(SimpleTestCase):
    """Font sizes use rem, not px, so they follow the reader's browser setting."""

    PX_FONT_SIZE = re.compile(r"font-size\s*:\s*[^;\"'}]*\d+(?:\.\d+)?px")

    def test_no_px_font_sizes(self):
        sources = [
            *sorted((BASE_DIR / "screening" / "static" / "screening").rglob("*.css")),
            *sorted((BASE_DIR / "screening" / "templates").rglob("*.html")),
            *sorted((BASE_DIR / "frontend" / "src").rglob("*.css")),
        ]
        found = []
        for path in sources:
            for lineno, line in enumerate(path.read_text().splitlines(), start=1):
                if self.PX_FONT_SIZE.search(line):
                    found.append(f"{path.relative_to(BASE_DIR)}:{lineno}")
        self.assertEqual(found, [], "use rem for font-size")


class TemplateCommentTests(SimpleTestCase):
    """Django's {# #} comment ends on its own line; one split over two lines shows on the page."""

    def test_comments_close_on_the_same_line(self):
        found = []
        for path in sorted((BASE_DIR / "screening" / "templates").rglob("*.html")):
            for lineno, line in enumerate(path.read_text().splitlines(), start=1):
                if re.search(r"\{#(?!.*#\})", line):
                    found.append(f"{path.relative_to(BASE_DIR)}:{lineno}")
        self.assertEqual(found, [], "use {% comment %} for comments longer than a line")


def questionnaire_code_lines(text, codes):
    """Line numbers where a code stands alone, not inside a longer id like report-ioi-ha."""
    pattern = re.compile(rf"(?<![\w-])(?:{'|'.join(map(re.escape, codes))})(?![\w-])")
    return [n for n, line in enumerate(text.splitlines(), start=1) if pattern.search(line)]


class QuestionnaireCodeTests(SimpleTestCase):
    """Only questionnaire definitions name a questionnaire code (issue #104, ADR 0005)."""

    SKIPPED = (
        "screening/tests",
        "screening/migrations",
        "screening/fixtures",
        "screening/questionnaires",
        "screening/static/screening/frontend",  # the gitignored build of frontend/src
    )
    SUFFIXES = (".py", ".html", ".js", ".jsx", ".css")

    def _sources(self):
        for path in sorted((BASE_DIR / "screening").rglob("*")):
            if path.suffix in self.SUFFIXES and not any(
                path.is_relative_to(BASE_DIR / folder) for folder in self.SKIPPED
            ):
                yield path
        for path in sorted((BASE_DIR / "frontend" / "src").rglob("*")):
            if path.suffix in self.SUFFIXES and ".test." not in path.name:
                yield path

    def test_codes_appear_only_in_definitions(self):
        sources = list(self._sources())
        for scanned in ("screening/views.py", "frontend/src/AnswerApp.jsx"):
            self.assertIn(BASE_DIR / scanned, sources)
        found = [
            f"{path.relative_to(BASE_DIR)}:{n}"
            for path in sources
            for n in questionnaire_code_lines(path.read_text(), questionnaires.DEFINITIONS)
        ]
        self.assertEqual(found, [], "ask the questionnaire definition instead of its code")

    def test_a_hard_coded_code_is_caught(self):
        source = 'id="report-ioi-ha"\nif questionnaire.code == "ssq12-tw":\n'
        self.assertEqual(questionnaire_code_lines(source, questionnaires.DEFINITIONS), [2])


# Logged-in views that show no health data (GLOSSARY.md 健康資料頁面), each with its reason (#182).
NO_HEALTH_DATA = {
    "consent": "the privacy summary and the agree button only",
    "audiogram_new": "an empty input page; a saved audiogram opens in audiogram_edit",
    "delete_account": "how many records would go, not their answers, scores or audiograms",
    "report_share_create": "POST only, answers with a redirect",
    "report_share_cancel": "POST only, answers with a redirect",
}


def logged_in_views():
    """(URL name, view) for each page in screening's URLs that sends a logged-out visitor to log
    in, whatever form the login requirement takes (decorator, mixin, other module)."""
    client = Client()
    login = reverse("login")
    for pattern in screening_urls.urlpatterns:
        kwargs = {
            name: 1 if isinstance(converter, IntConverter) else "x"
            for name, converter in pattern.pattern.converters.items()
        }
        url = reverse(pattern.name, kwargs=kwargs)
        if any(
            client.generic(method, url).get("Location", "").startswith(login)
            for method in ("GET", "POST")
        ):
            yield pattern.name, pattern.callback


def unmarked(views, exceptions):
    """Names of views carrying neither @health_data_page nor an entry in exceptions."""
    return [
        name
        for name, view in views
        if not getattr(view, "health_data_page", False) and name not in exceptions
    ]


class HealthDataPageTests(TestCase):
    """#182: every logged-in page is a 健康資料頁面 (never cached) or says why it holds none."""

    def test_every_logged_in_view_is_marked_or_excused(self):
        views = dict(logged_in_views())
        # The scan finds logged-in pages and only those.
        self.assertIn("my_hearing", views)
        self.assertNotIn("privacy", views)
        self.assertEqual(
            unmarked(views.items(), NO_HEALTH_DATA),
            [],
            "add @health_data_page, or list the view in NO_HEALTH_DATA with its reason",
        )

    def test_an_unmarked_view_is_caught(self):
        def shown(request): ...

        @health_data_page
        def marked(request): ...

        views = [("shown", shown), ("marked", marked)]
        self.assertEqual(unmarked(views, {}), ["shown"])
        self.assertEqual(unmarked(views, {"shown": "why"}), [])


class MigrationsUpToDateTests(TestCase):
    """A model change must ship with its migration."""

    def test_no_missing_migrations(self):
        out = StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
        except SystemExit:
            self.fail(f"missing migrations:\n{out.getvalue()}")
