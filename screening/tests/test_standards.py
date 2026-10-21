"""Rules from CODING_STANDARDS.md that a test can check, so review does not have to."""

import ast
import re
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from screening import questionnaires

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
        ]
        found = []
        for path in sources:
            for lineno, line in enumerate(path.read_text().splitlines(), start=1):
                if self.PX_FONT_SIZE.search(line):
                    found.append(f"{path.relative_to(BASE_DIR)}:{lineno}")
        self.assertEqual(found, [], "use rem for font-size")


def code_lines(text, codes):
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
        found = [
            f"{path.relative_to(BASE_DIR)}:{n}"
            for path in self._sources()
            for n in code_lines(path.read_text(), questionnaires.DEFINITIONS)
        ]
        self.assertEqual(found, [], "ask the questionnaire definition instead of its code")

    def test_a_hard_coded_code_is_caught(self):
        source = 'id="report-ioi-ha"\nif questionnaire.code == "ssq12-tw":\n'
        self.assertEqual(code_lines(source, questionnaires.DEFINITIONS), [2])


class MigrationsUpToDateTests(TestCase):
    """A model change must ship with its migration."""

    def test_no_missing_migrations(self):
        out = StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
        except SystemExit:
            self.fail(f"missing migrations:\n{out.getvalue()}")
