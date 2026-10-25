"""Rules from CODING_STANDARDS.md that a test can check, so review does not have to."""

import ast
import re
import string
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.forms import BaseForm, Form
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.urls.converters import IntConverter

from screening import forms as screening_forms
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


# Small print (CODING_STANDARDS.md 16, #357): the only selectors that may set text under 1rem,
# each with what it holds. Sources and the like first, then small text the owner chose to keep.
SOURCES = {
    ".q-intro-source": "a questionnaire's source on its answer page",
    ".source-note": "a source, HHIA-S's result limits, the privacy notice's version date",
    ".guide-source": "a guide chapter's sources",
    ".guide-checked": "the date a guide chapter was checked",
    ".history-tab-code": "a records tab's questionnaire code",
}
OWNER_KEPT = {
    ".since-last-date": "和上一次比's dates, under their labels (2026-10-24 comparison, A)",
    ".ioi-axis .ioi-grid": "the IOI-HA chart's axis numbers; the chart stays as drawn (#364)",
    ".ioi-name": "the IOI-HA chart's item names; the chart stays as drawn (#364)",
}
SMALL_PRINT = SOURCES | OWNER_KEPT

SIZE = re.compile(r"(\d*\.?\d+)(rem|em|%)")
SMALL_KEYWORD = re.compile(r"\b(?:smaller|small|x-small|xx-small)\b")


def is_small(value, variables):
    """True when a font-size value, or a custom property it reads, is under 1rem."""
    values = [value] + [
        defined
        for name in re.findall(r"var\((--[\w-]+)", value)
        for defined in variables.get(name, ())
    ]
    return any(
        SMALL_KEYWORD.search(v)
        or any(float(n) / (100 if unit == "%" else 1) < 1 for n, unit in SIZE.findall(v))
        for v in values
    )


def small_font_sizes(css):
    """(line, selector) for each font-size under 1rem set outside SMALL_PRINT. A rule's selector
    is its innermost style rule, inside whatever @layer, @media or @container wraps it."""
    css = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group().count("\n"), css, flags=re.S)
    variables = {}
    for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;{}]+)", css):
        variables.setdefault(name, []).append(value)
    found, preludes, text, line = [], [], "", 1
    for char in css:
        if char == "{":
            preludes.append(" ".join(text.split()))
            text = ""
        elif char == "}":
            if preludes:
                preludes.pop()
            text = ""
        elif char == ";":
            declaration = re.match(r"\s*font-size\s*:(.*)", text, flags=re.S)
            selector = next((p for p in reversed(preludes) if not p.startswith("@")), "")
            if declaration and is_small(declaration.group(1), variables):
                selectors = [s.strip() for s in selector.split(",")]
                if not all(s in SMALL_PRINT for s in selectors):
                    found.append((line, selector))
            text = ""
        else:
            text += char
        line += char == "\n"
    return found


def small_tailwind_text(line):
    """True when a template line uses Tailwind's text-xs or text-sm, or an arbitrary size
    under 1rem such as text-[0.875rem]."""
    sizes = re.findall(r"\btext-\[(\d*\.?\d+)(?:rem|em)\]", line)
    return bool(re.search(r"\btext-(?:xs|sm)\b", line)) or any(float(n) < 1 for n in sizes)


class SmallPrintTests(SimpleTestCase):
    """#357: text a reader needs is at least 1rem; only small print may be smaller."""

    def test_only_small_print_is_under_1rem(self):
        path = BASE_DIR / "frontend" / "src" / "site.css"
        found = [f"{line} {selector}" for line, selector in small_font_sizes(path.read_text())]
        self.assertEqual(found, [], "use 1rem or more, or add a source-like class to SMALL_PRINT")

    def test_no_small_tailwind_text_in_templates(self):
        sources = [
            *sorted((BASE_DIR / "screening" / "templates").rglob("*.html")),
            *sorted((BASE_DIR / "frontend" / "src").rglob("*.jsx")),
        ]
        found = [
            f"{path.relative_to(BASE_DIR)}:{lineno}"
            for path in sources
            for lineno, line in enumerate(path.read_text().splitlines(), start=1)
            if small_tailwind_text(line)
        ]
        self.assertEqual(found, [], "small print takes a SMALL_PRINT class from site.css")

    def test_small_tailwind_text_is_caught(self):
        self.assertTrue(small_tailwind_text('<p class="text-sm mb-0">'))
        self.assertTrue(small_tailwind_text('<span className="text-[0.875rem]">'))
        self.assertFalse(small_tailwind_text('<legend class="text-[calc(1.275rem+0.3vw)]">'))
        self.assertFalse(small_tailwind_text('<p class="text-body text-xl/normal">'))

    def test_a_small_size_outside_the_list_is_caught(self):
        css = """@layer components {
  .source-note { font-size: 0.875rem; }
  .guide-source,
  .guide-checked { font-size: 0.875rem; }
  @media (max-width: 47.99em) {
    .score-bar-ends { font-size: 0.875rem; } /* a label needed to read the bar */
  }
  .tag { --tag-size: 0.9em; font-size: var(--tag-size); }
  .source-note, .field-help { font-size: 90%; }
  small { font-size: smaller; }
  .lead { font-size: calc(1.3rem + 0.6vw); }
}"""
        self.assertEqual(
            small_font_sizes(css),
            [
                (6, ".score-bar-ends"),
                (8, ".tag"),
                (9, ".source-note, .field-help"),
                (10, "small"),
            ],
        )


class TemplateCommentTests(SimpleTestCase):
    """Django's {# #} comment ends on its own line; one split over two lines shows on the page."""

    def test_comments_close_on_the_same_line(self):
        found = []
        for path in sorted((BASE_DIR / "screening" / "templates").rglob("*.html")):
            for lineno, line in enumerate(path.read_text().splitlines(), start=1):
                if re.search(r"\{#(?!.*#\})", line):
                    found.append(f"{path.relative_to(BASE_DIR)}:{lineno}")
        self.assertEqual(found, [], "use {% comment %} for comments longer than a line")


# Full dates read 年/月/日 (2026/10/25), with the time 年/月/日 時:分 (#354, CODING_STANDARDS.md).
DATE_FORMATS = {"Y/m/d", "Y/m/d H:i", "H:i"}
# Y-m-d is for machines: allowed only as an attribute value, like <time datetime="…">.
MACHINE_DATE_FORMAT = "Y-m-d"
# (template, format) pairs that are still a 年/月/日 date on the page, each with its reason.
DATE_FORMAT_EXCEPTIONS = {
    ("screening/templates/screening/audiogram_compare.html", "Y/"): "Y/ <wbr> m/d lets a narrow"
    " table header wrap after the year",
    ("screening/templates/screening/audiogram_compare.html", "m/d"): "the second half of that date",
}
STRFTIME_FORMATS = {"%Y/%m/%d", "%Y/%m/%d %H:%M"}
DATE_FILTER = re.compile(r"\|date(?::\s*([\"'])(.*?)\1)?")
# A date written out in the template: 2026-10-22, 2026.10.22, 2026 年 10 月, 10 月 22 日.
LITERAL_DATE = re.compile(
    r"\b\d{4}([-.])\d{1,2}\1\d{1,2}\b|\d{4}\s*年\s*\d{1,2}\s*月|\d{1,2}\s*月\s*\d{1,2}\s*日"
)


def without_template_comments(text):
    """The template with its comments blanked out, keeping the line numbers."""

    def blank(match):
        return re.sub(r"[^\n]", " ", match.group(0))

    text = re.sub(r"\{% *comment *%\}.*?\{% *endcomment *%\}", blank, text, flags=re.S)
    return re.sub(r"\{#.*?#\}", blank, text)


def date_format_lines(text, exceptions=()):
    """Line numbers where a template shows a full date in a format other than 年/月/日."""
    found = []
    for lineno, line in enumerate(without_template_comments(text).splitlines(), start=1):
        for match in DATE_FILTER.finditer(line):
            fmt = match.group(2)
            if fmt in DATE_FORMATS or fmt in exceptions:
                continue
            if fmt == MACHINE_DATE_FORMAT and re.search(
                r"=[\"']\{\{[^{}]*$", line[: match.start()]
            ):
                continue
            found.append(lineno)
        if LITERAL_DATE.search(line):
            found.append(lineno)
    return sorted(set(found))


# A strftime directive such as %Y; a percentage's lone % (f"{x:.0%}") has none.
STRFTIME_DIRECTIVE = re.compile(r"%[A-Za-z]")


def placeholder_formats(text):
    """The format of each {name:format} placeholder in a str.format template."""
    try:
        return [spec for _, _, spec, _ in string.Formatter().parse(text) if spec]
    except ValueError:  # not a template: a lone brace
        return []


def python_date_formats(source):
    """Every date format in a Python source: handed to strftime or format(), or after the colon
    of an f-string's or a str.format template's placeholder."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            strftime = getattr(node.func, "attr", None) == "strftime"
            if strftime:
                args = node.args
            elif isinstance(node.func, ast.Name) and node.func.id == "format":
                args = node.args[1:]  # format(ratio, "f") is a number's
            else:
                continue
            for arg in args:
                for part in ast.walk(arg):
                    if isinstance(part, ast.Constant) and isinstance(part.value, str):
                        if strftime or STRFTIME_DIRECTIVE.search(part.value):
                            yield part.lineno, part.value
        elif isinstance(node, ast.FormattedValue) and node.format_spec is not None:
            spec = "".join(
                part.value for part in node.format_spec.values if isinstance(part, ast.Constant)
            )
            if STRFTIME_DIRECTIVE.search(spec):
                yield node.lineno, spec
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for spec in placeholder_formats(node.value):
                if STRFTIME_DIRECTIVE.search(spec):
                    yield node.lineno, spec


class DateFormatT358Tests(SimpleTestCase):
    """#354: every full date on the site reads 年/月/日 (with the time, 年/月/日 時:分)."""

    def test_templates_write_dates_as_year_month_day(self):
        found = []
        for path in sorted((BASE_DIR / "screening" / "templates").rglob("*.html")):
            name = str(path.relative_to(BASE_DIR))
            exceptions = {fmt for (where, fmt) in DATE_FORMAT_EXCEPTIONS if where == name}
            found += [f"{name}:{n}" for n in date_format_lines(path.read_text(), exceptions)]
        self.assertEqual(found, [], 'write a full date as |date:"Y/m/d" (or "Y/m/d H:i")')

    def test_python_formats_dates_as_year_month_day(self):
        found = [
            f"{path.relative_to(BASE_DIR)}:{lineno} {fmt}"
            for path in python_sources()
            if "tests" not in path.parts
            for lineno, fmt in python_date_formats(path.read_text())
            if fmt not in STRFTIME_FORMATS
        ]
        self.assertEqual(found, [], 'format a full date as "%Y/%m/%d" (or "%Y/%m/%d %H:%M")')

    def test_other_date_formats_are_caught(self):
        source = (
            '{{ a|date:"Y/m/d" }} {{ a|date:"Y/m/d H:i" }} {{ a|date:"H:i" }}\n'
            '{{ a|date:"n月j日" }}\n'
            "{{ a|date }}\n"
            '<time datetime="{{ a|date:"Y-m-d" }}">{{ a|date:"Y-m-d" }}</time>\n'
            "本頁資料查核於 2026-10-22。\n"
            "連結有效到 10 月 29 日。\n"
            "{# checked 2026-10-22 #}\n"
            '{% comment %}\n{{ a|date:"n/j" }}\n{% endcomment %}\n'
            '<th>{{ a|date:"Y/" }}<wbr>{{ a|date:"m/d" }}</th>\n'
        )
        self.assertEqual(date_format_lines(source), [2, 3, 4, 5, 6, 11])
        self.assertEqual(date_format_lines(source, {"Y/", "m/d"}), [2, 3, 4, 5, 6])
        formats = [
            fmt for _, fmt in python_date_formats('a.strftime("%Y/%m/%d" if x else "%m/%d")')
        ]
        self.assertEqual(sorted(formats), ["%Y/%m/%d", "%m/%d"])
        # Dates formatted without strftime: an f-string, format() and a str.format template,
        # each placeholder's format; a percentage's % is not a date.
        source = (
            'f"{a:%Y-%m-%d} {b:%Y/%m/%d} {c:.0%}"\n'
            'format(a, "%m/%d/%Y") + format(b, "f")\n'
            'NOTE = "要在 {deadline:%Y-%m-%d} 前做完"\n'
            '"{:%d.%m.%Y}".format(a)\n'
        )
        self.assertEqual(
            sorted(python_date_formats(source)),
            [(1, "%Y-%m-%d"), (1, "%Y/%m/%d"), (2, "%m/%d/%Y"), (3, "%Y-%m-%d"), (4, "%d.%m.%Y")],
        )


def forms_keeping_the_colon(module):
    """Form classes defined in module that still add Django's colon after each field name."""
    return [
        name
        for name, cls in vars(module).items()
        if isinstance(cls, type)
        and issubclass(cls, BaseForm)
        and cls.__module__ == module.__name__
        and not issubclass(cls, screening_forms.NoLabelSuffix)
    ]


class FormLabelSuffixT358Tests(SimpleTestCase):
    """#354: a field name never ends in a colon: every form drops the one Django adds."""

    def test_every_form_drops_the_django_colon(self):
        self.assertEqual(forms_keeping_the_colon(screening_forms), [])
        self.assertEqual(screening_forms.RegisterForm().label_suffix, "")

    def test_a_form_keeping_the_colon_is_caught(self):
        module = type(screening_forms)("fake_forms")
        module.Kept = type("Kept", (Form,), {"__module__": "fake_forms"})
        module.Dropped = type(
            "Dropped", (screening_forms.NoLabelSuffix, Form), {"__module__": "fake_forms"}
        )
        self.assertEqual(forms_keeping_the_colon(module), ["Kept"])
        self.assertEqual(module.Dropped().label_suffix, "")


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
