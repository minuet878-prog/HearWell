"""Screenshots of every page, for proving the Tailwind migration changes nothing (#122, #119).

Not named test_*.py and not part of e2e.main_flow, so no normal test run or CI job reaches it.
Build the frontend first, then capture into a folder of your choice (e2e-artifacts/ is ignored):

    npm run build --prefix frontend
    SHOTS_DIR=e2e-artifacts/shots/main \\
        py313/bin/python manage.py test --settings=config.test_settings e2e.screenshots

SHOTS_GROUPS limits the run to some groups, comma separated (default: all of them):
public, answering, history, report, and chrome (only the header, navigation and footer of
every page, plus the home-screen app header). Compare two captures with e2e/compare_shots.py.
Each capture also writes styles.json: the font family and root font size every page asks for,
since the screenshots themselves cannot show a lost web font.

The site's clock and the browser's clock are both fixed, and Google Fonts is blocked (the
system font stands in), so two captures of the same commit match. Font loading itself is
therefore not compared. Capture the baseline on main and the new set on your branch.
"""

import json
import os
import re
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from playwright.sync_api import sync_playwright

from e2e import main_flow
from screening.models import (
    Answer,
    Audiogram,
    AudiogramPoint,
    Category,
    NormGroup,
    Question,
    Questionnaire,
    ReportComparison,
    ReportShare,
    Submission,
    User,
)
from screening.tests.helpers import consented_user, fake_definition, register

# Playwright runs an event loop in this thread, which makes Django refuse database calls.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))
WIDTHS = (390, 1024)
GOOGLE_FONTS = re.compile(r"https://fonts\.(googleapis|gstatic)\.com/.*")
GROUPS = ("public", "answering", "history", "report", "chrome")
# Recharts and the audiogram draw with JavaScript after load; wait out their animations.
SETTLE_MS = 1600


class Shot:
    def __init__(self, group, name, url, who="user", javascript=True, media="screen"):
        self.group, self.name, self.url = group, name, url
        self.who, self.javascript, self.media = who, javascript, media

    def filename(self, width, part=None):
        flags = f"--{self.who}"
        if not self.javascript:
            flags += "--nojs"
        if self.media == "print":
            flags += "--print"
        prefix = f"chrome--{part}" if part else self.group
        return f"{prefix}--{self.name}{flags}--{width}.png"


class Screenshots(StaticLiveServerTestCase):
    fixtures = ("questions_fixture.json",)
    # Some pages print the site's address; a random port would differ between two captures.
    port = 8765

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        # Same text rasterising on every run, so glyph edges do not differ between captures.
        cls.browser = cls.playwright.chromium.launch(
            args=["--font-render-hinting=none", "--disable-gpu", "--force-color-profile=srgb"]
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        if "SHOTS_DIR" not in os.environ:
            self.skipTest("set SHOTS_DIR to capture screenshots")
        self.out = Path(os.environ["SHOTS_DIR"])
        self.out.mkdir(parents=True, exist_ok=True)
        wanted = os.environ.get("SHOTS_GROUPS", ",".join(GROUPS)).split(",")
        self.groups = {g.strip() for g in wanted if g.strip()}
        unknown = self.groups - set(GROUPS)
        if unknown:
            raise ValueError(f"unknown SHOTS_GROUPS: {sorted(unknown)}")
        self.enterContext(mock.patch("django.utils.timezone.now", return_value=NOW))
        call_command("seed_questionnaires", verbosity=0)
        self.records = self.make_records()
        self.cookies = {
            "user": self.session(self.user),
            "new": self.session(User.objects.create_user(username="shots_new")),
            "anon": None,
        }

    def session(self, user):
        client = Client()
        client.force_login(user)
        return {
            "name": settings.SESSION_COOKIE_NAME,
            "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def answered(self, code, scores, days_ago, **fields):
        questionnaire = Questionnaire.objects.get(code=code)
        record = Submission.objects.create(
            user=self.user,
            questionnaire=questionnaire,
            wearing_hearing_aid=fields.pop("wearing", False),
            **fields,
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=question, score=score)
            for question, score in zip(questionnaire.questions.all(), scores, strict=True)
        )
        Submission.objects.filter(pk=record.pk).update(created_at=NOW - timedelta(days=days_ago))
        return record

    def make_records(self):
        self.user = consented_user(username="shots_user", birth_year=1950)
        records = {
            "hhie-s-normal": self.answered("hhie-s", [0] * 10, 30),
            "hhie-s-mild": self.answered("hhie-s", [2] * 6 + [0] * 4, 20),
            "hhie-s-severe": self.answered("hhie-s", [4] * 10, 10),
            "hhie-s-aided": self.answered("hhie-s", [2] * 3 + [0] * 7, 5, wearing=True),
            "hhia-s-normal": self.answered("hhia-s", [0] * 10, 29),
            "hhia-s-mild": self.answered("hhia-s", [2] * 6 + [0] * 4, 19),
            "hhia-s-severe": self.answered("hhia-s", [4] * 10, 9),
            "ssq12-tw": self.answered("ssq12-tw", [7, 6, 8, 5, 7, 6, 8, 7, 6, 5, 7, 8], 8),
        }
        records["ioi-ha"] = self.answered(
            "ioi-ha",
            [5, 2, 3, 4, 3, 5, 1],
            4,
            wearing=True,
            norm_group=NormGroup.MILD_MODERATE,
            norm_basis=records["hhie-s-severe"],
        )
        unconfigured = Questionnaire.objects.create(
            questionnaire_name="Unknown", code="unconfigured"
        )
        Question.objects.bulk_create(
            Question(
                questionnaire=unconfigured,
                question_text=f"題目{n}",
                question_number=n,
                category=Category.EMOTIONAL,
            )
            for n in range(1, 11)
        )
        records["unknown"] = self.answered("unconfigured", [2] * 10, 3)
        ReportComparison.objects.create(
            user=self.user,
            questionnaire=records["hhie-s-severe"].questionnaire,
            unaided=records["hhie-s-severe"],
            aided=records["hhie-s-aided"],
        )
        ReportShare.objects.create(user=self.user, token="screenshots-fixed-token")
        for key, tested_on, db in (
            ("audiogram-newer", date(2026, 9, 1), 45),
            ("audiogram-older", date(2026, 6, 1), 35),
        ):
            records[key] = Audiogram.objects.create(user=self.user, tested_on=tested_on)
            AudiogramPoint.objects.bulk_create(
                AudiogramPoint(
                    audiogram=records[key], ear=ear, conduction="air", frequency=f, db=db
                )
                for ear in ("right", "left")
                for f in (250, 500, 1000, 2000, 4000, 8000)
            )
        return records

    def shots(self):
        r = self.records
        hhie_s = r["hhie-s-severe"].questionnaire
        audiogram = r["audiogram-newer"]
        share = reverse("shared_cover", args=["screenshots-fixed-token"])
        shots = []
        for name, url in (
            ("index", reverse("index")),
            ("privacy", reverse("privacy")),
            ("family", reverse("family_guide")),
            ("add-to-home", reverse("add_to_home")),
        ):
            shots += [Shot("public", name, url, who="anon"), Shot("public", name, url)]
        shots += [
            Shot("public", "login", reverse("login"), who="anon"),
            Shot("public", "register", reverse("register"), who="anon"),
            Shot("public", "consent", reverse("consent"), who="new"),
            Shot("public", "account", reverse("account_settings")),
            Shot("public", "account-delete", reverse("delete_account")),
            Shot("answering", "questionnaire-list", reverse("questionnaire_list")),
            Shot("answering", "comparison-hhie-s", reverse("hhi_comparison", args=[hhie_s.pk])),
        ]
        for code in ("hhie-s", "hhia-s", "ssq12-tw", "ioi-ha"):
            url = reverse("screening", args=[Questionnaire.objects.get(code=code).pk])
            shots += [
                Shot("answering", f"answer-{code}", url),
                Shot("answering", f"answer-{code}", url, javascript=False),
            ]
        for key in (
            "hhie-s-normal",
            "hhie-s-mild",
            "hhie-s-severe",
            "hhia-s-normal",
            "hhia-s-mild",
            "hhia-s-severe",
            "unknown",
            "ssq12-tw",
            "ioi-ha",
        ):
            shots.append(Shot("answering", f"result-{key}", reverse("result", args=[r[key].pk])))
        for code in ("hhie-s", "hhia-s", "ssq12-tw", "ioi-ha"):
            url = f"{reverse('my_hearing')}?questionnaire={code}"
            shots.append(Shot("history", f"my-hearing-{code}", url))
        shots += [
            Shot("history", "audiograms", reverse("audiogram_list")),
            Shot("history", "audiogram-new", reverse("audiogram_new")),
            Shot("history", "audiogram-detail", reverse("audiogram_detail", args=[audiogram.pk])),
            Shot("history", "audiogram-edit", reverse("audiogram_edit", args=[audiogram.pk])),
            Shot("history", "audiogram-compare", reverse("audiogram_compare")),
            Shot("history", "audiogram-delete", reverse("audiogram_delete", args=[audiogram.pk])),
            Shot("report", "report", reverse("health_report")),
            Shot("report", "report", reverse("health_report"), media="print"),
            Shot("report", "shared-cover", share, who="anon"),
            Shot("report", "shared-report", f"{share}/report", who="anon"),
        ]
        return shots

    def open(self, shot, width, standalone=False):
        context = self.browser.new_context(
            viewport={"width": width, "height": 900}, java_script_enabled=shot.javascript
        )
        # Google Fonts loads Noto Sans TC in slices whose timing moves Latin glyphs between
        # captures; the system font keeps every capture alike (the font itself is not compared).
        context.route(GOOGLE_FONTS, lambda route: route.abort())
        if self.cookies[shot.who]:
            context.add_cookies([self.cookies[shot.who]])
        if standalone:
            context.add_init_script(main_flow.PwaNavTest.STANDALONE)
        page = context.new_page()
        page.clock.set_fixed_time(NOW)
        page.emulate_media(media=shot.media)
        page.goto(f"{self.live_server_url}{shot.url}")
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        if page.locator("#trend-chart, #audiogram-chart, #audiogram-app").count():
            page.wait_for_timeout(SETTLE_MS)
        return context, page

    @staticmethod
    def chrome(page):
        return {
            "header": page.get_by_role("banner"),
            "nav": page.get_by_role("navigation", name="主要導覽"),
            "footer": page.get_by_role("contentinfo"),
        }

    def capture(self, page, path, locator=None):
        options = {"path": self.out / path, "animations": "disabled", "caret": "hide"}
        if locator is None:
            page.screenshot(full_page=True, **options)
        else:
            locator.screenshot(**options)

    def test_capture(self):
        taken = 0
        styles = {}
        chrome = "chrome" in self.groups
        for shot in self.shots():
            page_wanted = shot.group in self.groups
            if not (page_wanted or chrome):
                continue
            # Registered only here, so the fake questionnaire shows up on no other page.
            unknown = shot.name == "result-unknown"
            with register(fake_definition("unconfigured")) if unknown else nullcontext():
                for width in WIDTHS:
                    context, page = self.open(shot, width)
                    styles[shot.filename(width)] = page.evaluate(
                        "({ font: getComputedStyle(document.body).fontFamily,"
                        " rootSize: getComputedStyle(document.documentElement).fontSize })"
                    )
                    if page_wanted:
                        self.capture(page, shot.filename(width))
                        taken += 1
                    if chrome and shot.media == "screen":
                        for part, found in self.chrome(page).items():
                            if found.count():
                                self.capture(page, shot.filename(width, part), found)
                                taken += 1
                    context.close()
        (self.out / "styles.json").write_text(
            json.dumps(styles, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
        )
        if chrome:
            app = Shot("chrome", "questionnaire-list-app", reverse("questionnaire_list"))
            for width in WIDTHS:
                context, page = self.open(app, width, standalone=True)
                self.capture(page, app.filename(width, "header"), page.get_by_role("banner"))
                taken += 1
                context.close()
        print(f"{taken} screenshots in {self.out}")
