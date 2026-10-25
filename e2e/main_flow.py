"""End-to-end: a real browser walks the main flow against a live test server (spec phase6_e2e.md).

Not named test_*.py, so the normal test run skips it; run it by name after building the frontend:
    python manage.py test --settings=config.test_settings e2e.main_flow --parallel 4
"""

import base64
import calendar
import os
import re
from contextlib import contextmanager, nullcontext
from datetime import date, datetime, timedelta
from itertools import combinations, pairwise
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from screening.audiogram import DB_MAX
from screening.fitting_route import add_months
from screening.models import (
    AidAndSubsidy,
    Answer,
    Audiogram,
    AudiogramPoint,
    Category,
    GuideChapterView,
    NormGroup,
    Question,
    Questionnaire,
    ReportComparison,
    ReportShare,
    Submission,
    User,
)
from screening.questionnaires.thi import SUPPORT_MESSAGE as THI_SUPPORT_MESSAGE
from screening.tests.helpers import consented_user, fake_definition, register

# Playwright runs an event loop in this thread, which makes Django refuse database calls.
# The Django docs' fix for Playwright; this module is only imported by the e2e run.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

ARTIFACTS = settings.BASE_DIR / "e2e-artifacts"
QUESTION_COUNT = 10


class SavesFailureArtifacts:
    """On failure, keep the screenshot and trace of that moment for debugging (CI uploads them)."""

    saved_context = None
    saved_count = 0

    @contextmanager
    def saving_artifacts(self):
        try:
            yield
        except BaseException:
            # Nested blocks see the same failure again; a context's trace can only stop once.
            if self.saved_context is not self.context:
                self.saved_context = self.context
                self.saved_count += 1
                # Named per test and browser context, so one failure never overwrites another.
                name = f"{'.'.join(self.id().split('.')[-2:])}-{self.saved_count}"
                ARTIFACTS.mkdir(exist_ok=True)
                self.page.screenshot(path=ARTIFACTS / f"{name}.png", full_page=True)
                self.context.tracing.stop(path=ARTIFACTS / f"{name}.zip")
            raise

    @contextmanager
    def subTest(self, *args, **params):
        # unittest records a failing subtest and carries on, so no outer block ever sees it.
        with super().subTest(*args, **params), self.saving_artifacts():
            yield

    def __getstate__(self):
        # --parallel pickles a failed subtest's test case to send it back, after the test has
        # ended, when Django no longer leaves out what cannot be pickled: the browser objects.
        state = super().__getstate__()
        browser = ("page", "context", "saved_context")
        return {key: value for key, value in state.items() if key not in browser}


AUDIOGRAM_FORWARD = re.compile("^下一步：標右耳$|換左耳$|確認存檔$")


def audiogram_step(page, live_server_url, step):
    """#199: the new-audiogram page opens on the date; walk on to step (2: 標右耳, 4: 確認存檔)."""
    page.goto(f"{live_server_url}/audiograms/new")
    for _ in range(step - 1):
        page.get_by_role("main").get_by_role("button", name=AUDIOGRAM_FORWARD).click()


# #314: each questionnaire's summary row on the report: a summary holding a level 3 heading.
REPORT_FOLDS = "details > summary:has(> h3)"


def open_report_folds(page):
    """#314: opens every questionnaire's fold on the report."""
    for fold in page.get_by_role("main").locator(REPORT_FOLDS).all():
        fold.click()


class OnAPhone:
    """Finding things on a page and answering questions, shared by the main-flow routes."""

    # Text at 200%: 2 x the site's 112.5% base, as in SharedLayoutTest.
    DOUBLE_TEXT_SIZE = "225%"

    def main(self):
        return self.page.get_by_role("main")

    def double_text(self, on=True):
        """Sets the page's text to 200%, or (on=False) back to its usual size. Not add_style_tag:
        it waits for the style's load event, which never fires without JavaScript."""
        self.page.locator("html").evaluate(
            "(html, [on, size]) => on ? html.style.setProperty('font-size', size, 'important')"
            " : html.style.removeProperty('font-size')",
            [on, self.DOUBLE_TEXT_SIZE],
        )

    def assert_fits_a_phone_at_double_text_size(self, where, width=320):
        # The page is width px wide. Wait for the stylesheet first: a click only waits until the
        # new page starts, and an unstyled page is wider than 320px (unsized SVG icons), which
        # failed CI at random.
        self.page.wait_for_load_state("load")
        self.double_text()
        scroll_width = self.page.evaluate("document.documentElement.scrollWidth")
        self.assertLessEqual(scroll_width, width, where)

    def question(self, number):
        """The one question on screen, checked to be the expected one."""
        group = self.page.get_by_role("group")
        expect(group).to_have_count(1)
        if number is not None:
            expect(group).to_contain_text(f"第 {number} 題／共 {QUESTION_COUNT} 題")
        return group

    def answer(self, label, number=None):
        self.question(number).get_by_label(label).check()

    def next(self):
        self.main().get_by_role("button", name="下一題").click()

    def answer_ioi_ha(self):
        """On IOI-HA's React page: no wearing step, the norm basis told on item 1 (ADR 0002)."""
        app = self.main().locator(".answer-app")
        expect(app.get_by_role("group")).to_contain_text("第 1 題／共 7 題")
        expect(app).to_contain_text("本次常模依據：")
        expect(app).not_to_contain_text("有沒有戴助聽器")
        for number in range(1, 8):
            group = app.get_by_role("group")
            expect(group).to_contain_text(f"第 {number} 題／共 7 題")
            group.get_by_role("radio").first.check()
            if number < 7:
                self.next()
        self.main().get_by_role("button", name="送出").click()
        expect(self.page).to_have_url(re.compile(r"/submission/\d+$"))


class NewUserScreeningTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """Spec 4.1: one method per step, so a failure's traceback names the step."""

    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.context = self.browser.new_context(**self.playwright.devices["Pixel 7"])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def test_new_user_completes_hhie_s(self):
        with self.saving_artifacts():
            self.step1_start_goes_to_register()
            self.step2_register()
            self.step3_choose_hhie_s()
            self.step4_answer_and_change_one()
            self.step5_submit()
            self.step6_history()
            self.step7_report_prints_without_site_chrome()

    def test_new_user_answers_ioi_ha_on_react_after_an_unaided_hhie_s(self):
        """#245: the unaided HHIE-S just answered is IOI-HA's norm basis, told on item 1."""
        with self.saving_artifacts():
            self.step1_start_goes_to_register()
            self.step2_register()
            self.step3_choose_hhie_s()
            self.step4_answer_and_change_one()
            self.step5_submit()
            ioi_ha = Questionnaire.objects.get(code="ioi-ha")
            self.page.goto(f"{self.live_server_url}/questionnaire/{ioi_ha.pk}")
            self.answer_ioi_ha()
            basis = self.page.get_by_text("分組依據：", exact=False)
            expect(basis).to_contain_text("HHIE-S")
            expect(basis).to_contain_text("20 分")
            expect(self.main()).to_contain_text("低於常模")

    def test_show_password_with_javascript(self):
        """#155 (ticket #151): the 顯示 button shows the password, and hides it again."""
        with self.saving_artifacts():
            self.step1_start_goes_to_register()
            password = self.page.get_by_label("密碼", exact=True)
            password.fill("Fake-pass-2468")
            toggle = self.main().locator('button.password-toggle[aria-controls="id_password1"]')
            expect(toggle).to_have_accessible_name("顯示密碼")
            toggle.click()
            expect(password).to_have_attribute("type", "text")
            expect(toggle).to_have_accessible_name("隱藏密碼")
            expect(toggle).to_have_text("隱藏")
            toggle.click()
            expect(password).to_have_attribute("type", "password")
            expect(toggle).to_have_accessible_name("顯示密碼")

    def test_first_visit_pages_fit_a_phone_at_double_text_size(self):
        """#155: home, register, consent, every wizard step and the answer page, 320px at 200%.

        The login page too, since its form moved onto a brand banner (2026-10-23).
        """
        self.context.close()
        self.context = self.browser.new_context(
            **{**self.playwright.devices["Pixel 7"], "viewport": {"width": 320, "height": 640}}
        )
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/login")
            self.assert_fits_a_phone_at_double_text_size("login")
            self.page.goto(self.live_server_url)
            self.assert_fits_a_phone_at_double_text_size("home")
            self.main().get_by_role("link", name="開始篩檢").click()
            self.assert_fits_a_phone_at_double_text_size("register")
            self.fill_register_form()
            self.main().get_by_role("button", name="註冊").click()
            self.assert_fits_a_phone_at_double_text_size("consent")
            self.main().get_by_role("button", name="我同意，開始篩檢", exact=True).click()
            expect(self.main().locator(".questionnaire-guide")).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("wizard concern")
            self.main().get_by_role("group", name="您最想了解什麼？").get_by_label(
                "聽不清楚對生活、心情的影響", exact=True
            ).check()
            self.main().get_by_role("button", name="下一步").click()
            self.assert_fits_a_phone_at_double_text_size("wizard age")
            self.main().get_by_role("group", name="您目前的實際年齡？").get_by_label(
                "65 歲以上", exact=True
            ).check()
            self.main().get_by_role("button", name="下一步").click()
            self.main().get_by_text("看其他問卷", exact=True).click()
            expect(self.main().locator("details a.link-card").first).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("wizard recommendation")
            self.main().get_by_role("link", name="開始作答").click()
            expect(self.page.get_by_role("group")).to_have_count(1)
            self.assert_fits_a_phone_at_double_text_size("answer hearing aid step")
            self.answer("沒戴")
            self.next()
            self.question(1)
            self.main().get_by_role("button", name="這份問卷在問什麼？").click()
            expect(self.page.locator("#answer-intro-text")).to_contain_text("本問卷的目的")
            self.assert_fits_a_phone_at_double_text_size("answer question 1, intro open")

    def test_adult_completes_hhia_s_with_keyboard(self):
        """Issue #78: real React flow, original labels, focus and saved results."""
        call_command("seed_questionnaires", verbosity=0)
        with self.saving_artifacts():
            self.step1_start_goes_to_register()
            self.step2_register()
            self.choose_self()
            self.main().get_by_role("link", name=re.compile("HHIA-S")).click()
            self.answer("沒戴")
            self.next()
            for number in range(1, 11):
                group = self.question(number)
                expect(group.locator("legend")).to_be_focused()
                radio = group.get_by_role("radio", name="有時", exact=True)
                radio.focus()
                radio.press("Space")
                expect(radio).to_be_checked()
                if number < 10:
                    self.next()
            self.main().get_by_role("button", name="送出").click()
            expect(self.page.get_by_text("總分 20 分")).to_be_visible()
            expect(self.page.locator(".result-banner").get_by_text("輕至中度影響")).to_be_visible()
            # Text-heavy pages tidy-up: said under the steps, outside the folded full advice.
            expect(self.main().locator(".source-note")).to_contain_text("不能判定聽損程度")
            expect(self.main().locator(".source-note")).to_be_visible()
            self.page.get_by_role("navigation", name="主要導覽").get_by_role(
                "link", name="紀錄"
            ).click()
            expect(self.main().locator("a.link-card:not(.action-card)")).to_contain_text("總分：20")

    def test_adult_completes_hhia_s_without_javascript(self):
        """Issue #78: the actual HTML fallback works when scripts never run."""
        call_command("seed_questionnaires", verbosity=0)
        self.context.close()
        self.context = self.browser.new_context(java_script_enabled=False)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.step1_start_goes_to_register()
        self.step2_register()
        self.choose_self()
        self.main().get_by_role("link", name=re.compile("HHIA-S")).click()
        self.page.get_by_role("group", name="這次填答時，您有沒有戴助聽器？").get_by_label(
            "沒戴", exact=True
        ).check()
        for number in range(1, 11):
            self.page.locator(f"#question-{number}").get_by_role(
                "radio", name="有時", exact=True
            ).check()
        self.main().get_by_role("button", name="送出").click()
        expect(self.page.get_by_text("總分 20 分")).to_be_visible()
        expect(self.page.locator(".result-banner").get_by_text("輕至中度影響")).to_be_visible()

    def test_ssq12_scale_draft_and_average(self):
        """#79: range input, N/A, zero and draft restoration in a real browser."""
        call_command("seed_questionnaires", verbosity=0)
        with self.saving_artifacts():
            self.step1_start_goes_to_register()
            self.step2_register()
            self.choose_self()
            self.main().get_by_role("link", name=re.compile("SSQ12-TW")).click()
            self.answer("沒戴")
            self.next()
            expect(self.main().get_by_text("未作答", exact=True)).to_be_visible()
            # #326 C5: nothing chosen on the scale, so 下一題 asks for a choice and stays.
            self.next()
            expect(self.main().get_by_role("alert")).to_have_text("請先選一個答案")
            expect(self.main().get_by_role("group").locator("legend")).to_be_focused()
            expect(self.main().get_by_role("group")).to_contain_text("第 1 題／共 12 題")
            self.main().get_by_role("group").get_by_label("不適用", exact=True).check()
            expect(self.main().get_by_role("alert")).to_have_count(0)
            self.next()
            slider = self.main().get_by_role("slider")
            slider.press("Home")
            expect(self.main().get_by_text("0 分", exact=True)).to_be_visible()
            self.page.reload()
            self.main().get_by_role("button", name="接著答").click()
            expect(self.main().get_by_text("0 分", exact=True)).to_be_visible()
            self.main().get_by_role("button", name="上一題").click()
            expect(
                self.main().get_by_role("group").get_by_label("不適用", exact=True)
            ).to_be_checked()
            # Replace the explicit N/A with 6, then all items 6 except the last (9).
            for number in range(1, 13):
                if number in (9, 11, 12):
                    label = {9: "0：混亂", 11: "0：不清晰", 12: "0：非常專心"}[number]
                    expect(self.main().get_by_text(label, exact=True)).to_be_visible()
                slider = self.main().get_by_role("slider")
                slider.press("Home")
                for _ in range(9 if number == 12 else 6):
                    slider.press("ArrowRight")
                if number < 12:
                    self.next()
            self.main().get_by_role("button", name="送出").click()
            expect(
                self.main().get_by_text("整體平均 6.3 分（滿分 10）", exact=True)
            ).to_be_visible()
            expect(self.main().get_by_text("情緒分數", exact=False)).to_have_count(0)
            self.page.screenshot(path="/tmp/hearwell-ssq12-result.png", full_page=True)
            self.main().locator(".result-actions").get_by_role("link", name="看我的紀錄").click()
            expect(self.main().locator("a.link-card:not(.action-card)")).to_contain_text(
                "整體平均：6.3"
            )
            expect(self.main().locator("#trend-chart")).to_have_count(0)
            # #83/#84: keep a comparison and follow it through owner/family/print.
            unaided = Submission.objects.get(questionnaire__code="ssq12-tw")
            aided = Submission.objects.create(
                user=unaided.user, questionnaire=unaided.questionnaire, wearing_hearing_aid=True
            )
            Answer.objects.bulk_create(
                Answer(submission=aided, question=q, score=8)
                for q in unaided.questionnaire.questions.all()
            )
            # #161: the comparison link only shows once both statuses exist; the page was
            # rendered before the aided record above, so reload to see it.
            self.page.reload()
            self.main().get_by_role("link", name="比較戴與不戴助聽器", exact=True).click()
            self.page.locator(f'input[name="unaided"][value="{unaided.pk}"]').check()
            self.page.locator(f'input[name="aided"][value="{aided.pk}"]').check()
            self.main().get_by_role("button", name="查看比較", exact=True).focus()
            self.page.keyboard.press("Enter")
            expect(
                self.main().get_by_text("有戴比沒戴多 1.8 分（分數越高越好）", exact=True)
            ).to_be_visible()
            self.main().get_by_role("button", name="放進聽力報告", exact=True).focus()
            self.page.keyboard.press("Enter")
            expect(self.main().get_by_text("這一組已經在聽力報告裡", exact=True)).to_be_visible()
            call_command("seed_questionnaires", verbosity=0)
            for hhi in Questionnaire.objects.filter(code__in=("hhie-s", "hhia-s")):
                pair = []
                for wearing in (False, True):
                    record = Submission.objects.create(
                        user=unaided.user, questionnaire=hhi, wearing_hearing_aid=wearing
                    )
                    Answer.objects.bulk_create(
                        Answer(submission=record, question=q, score=2) for q in hhi.questions.all()
                    )
                    pair.append(record)
                self.page.goto(f"{self.live_server_url}/comparisons/{hhi.pk}")
                self.page.locator(f'input[name="unaided"][value="{pair[0].pk}"]').check()
                self.page.locator(f'input[name="aided"][value="{pair[1].pk}"]').check()
                self.main().get_by_role("button", name="查看比較", exact=True).click()
                self.main().get_by_role("button", name="放進聽力報告", exact=True).click()
                expect(
                    self.main().get_by_text("這一組已經在聽力報告裡", exact=True)
                ).to_be_visible()
            self.page.goto(f"{self.live_server_url}/report")
            expect(self.page.locator("#report-ssq12")).to_contain_text("整體平均：8.0")
            # #314: every questionnaire folded; open them all, so their contents must fit too.
            open_report_folds(self.page)
            self.page.set_viewport_size({"width": 320, "height": 800})
            self.page.locator("html").evaluate("el => el.style.fontSize = '24px'")
            self.page.locator("body").evaluate("el => el.style.fontFamily = 'monospace'")
            self.assertFalse(
                self.page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
            )
            self.page.screenshot(path="/tmp/hearwell-adult-report-320.png", full_page=True)
            self.page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
            self.page.emulate_media(media="print")
            for section in ("report-hhia-s", "report-hhie-s", "report-ssq12"):
                expect(self.page.locator(f"#{section} .report-answers ol")).to_be_visible()
            for section in (
                "report-difference",
                "report-comparison-hhia-s",
                "report-comparison-ssq12-tw",
            ):
                expect(self.page.locator(f"#{section}")).to_be_visible()
            self.page.emulate_media(media="screen")
            self.page.evaluate("window.dispatchEvent(new Event('afterprint'))")
            self.main().get_by_role("link", name="分享報告給家人", exact=True).click()
            self.main().get_by_role("button", name="我知道了，產生連結", exact=True).click()
            expect(self.main().get_by_role("button", name="取消分享", exact=True)).to_be_visible()
            share = unaided.user.report_shares.get()
            with self.browser.new_context() as family_context:
                family_page = family_context.new_page()
                family_page.goto(f"{self.live_server_url}/shared/{share.token}/report")
                expect(family_page.locator("#report-comparison-ssq12-tw")).to_contain_text(
                    "+1.8 分"
                )
                expect(
                    family_page.get_by_role("link", name="更換或移除", exact=False)
                ).to_have_count(0)
                open_report_folds(family_page)
                family_page.set_viewport_size({"width": 320, "height": 800})
                family_page.locator("html").evaluate("el => el.style.fontSize = '24px'")
                # Wider glyphs reproduce the table's minimum-width overflow across platforms.
                family_page.locator("body").evaluate("el => el.style.fontFamily = 'monospace'")
                self.assertFalse(
                    family_page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                )
                for section in (
                    "report-difference",
                    "report-comparison-hhia-s",
                    "report-comparison-ssq12-tw",
                ):
                    expect(family_page.locator(f"#{section}")).to_be_visible()
                family_page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
                family_page.emulate_media(media="print")
                for section in ("report-hhia-s", "report-hhie-s", "report-ssq12"):
                    expect(family_page.locator(f"#{section} .report-answers ol")).to_be_visible()

    def test_ssq12_without_javascript_keeps_explicit_na(self):
        call_command("seed_questionnaires", verbosity=0)
        self.context.close()
        self.context = self.browser.new_context(java_script_enabled=False)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.step1_start_goes_to_register()
        self.step2_register()
        self.choose_self()
        self.main().get_by_role("link", name=re.compile("SSQ12-TW")).click()
        self.page.get_by_role("group", name="這次填答時，您有沒有戴助聽器？").get_by_label(
            "沒戴", exact=True
        ).check()
        for number in range(1, 13):
            self.page.locator(f"#question-{number}").get_by_role(
                "radio", name="不適用" if number == 1 else "0", exact=True
            ).check()
        self.main().get_by_role("button", name="送出").click()
        expect(self.main().get_by_text("未計算：包含不適用題目", exact=True)).to_be_visible()

    def test_age_step_and_recommendation_without_javascript(self):
        """#80, #152: server-rendered selection preserves browser back and scales at 320px."""
        call_command("seed_questionnaires", verbosity=0)
        self.context.close()
        self.context = self.browser.new_context(
            java_script_enabled=False, viewport={"width": 320, "height": 800}
        )
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.step1_start_goes_to_register()
        # #151: without JavaScript the 顯示 button could not work, so none shows.
        expect(self.main().get_by_role("button", name=re.compile("顯示"))).to_have_count(0)
        self.step2_register()
        # #345: the five answers are one named group (#339 acceptance 21).
        concern = self.main().get_by_role("group", name="您最想了解什麼？")
        expect(concern.get_by_role("radio")).to_have_count(5)
        hearing_aid_answer = concern.get_by_role("radio", name="助聽器戴得好不好", exact=True)
        hearing_aid_answer.check()
        self.main().get_by_role("button", name="下一步").click()
        # No birth year, and a life-impact questionnaire to catch up: the age comes second. Back
        # on step 1 the answer is still chosen (#339 acceptance 19).
        self.main().get_by_role("link", name="上一步").click()
        expect(hearing_aid_answer).to_be_checked()
        self.main().get_by_role("button", name="下一步").click()
        age_group = self.main().get_by_role("group", name="您目前的實際年齡？")
        age_group.get_by_role("radio", name="18–64 歲", exact=True).focus()
        self.page.keyboard.press("Space")
        self.main().get_by_role("button", name="下一步").click()
        # Wearing one with no unaided record: HHIA-S first, IOI-HA listed as also worth doing.
        recommended = self.main().locator("#recommended-title")
        expect(recommended).to_contain_text("HHIA-S")
        self.main().get_by_role("link", name=re.compile("IOI-HA")).click()
        # Answer page tidy-up: the topic is the title, the code is on the line under it.
        expect(self.page.get_by_role("heading", name="助聽器使用成效", exact=True)).to_be_visible()
        self.page.go_back()
        expect(recommended).to_contain_text("HHIA-S")
        self.page.locator("html").evaluate("element => element.style.fontSize = '200%'")
        self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 320)
        self.page.screenshot(path="/tmp/hearwell-recommendations-200.png", full_page=True)
        # #155: the wizard ends on the answer page, the server's form starting on 沒戴 (#154).
        self.main().get_by_role("link", name="開始作答").click()
        expect(self.page).to_have_url(re.compile(r"/questionnaire/\d+\?preselect=unaided$"))
        # The topic is the title; HHIA-S shares it with HHIE-S, so the code line tells them apart.
        title = self.page.get_by_role("heading", name="聽力對生活的影響", exact=True)
        expect(title).to_be_visible()
        expect(self.main().get_by_text(re.compile(r"^HHIA-S・共 \d+ 題"))).to_be_visible()
        hearing_aid = self.page.get_by_role("group", name="這次填答時，您有沒有戴助聽器？")
        expect(hearing_aid.get_by_label("沒戴", exact=True)).to_be_checked()
        expect(self.page.locator("#hearing-aid-hint")).to_have_text("請想沒戴助聽器時的情況來回答")
        self.assert_fits_a_phone_at_double_text_size("answer page without javascript")

    def test_family_guide_without_share_sheet(self):
        """Spec phase8_c1_family_guide.md acceptance 5: no button, the address is the fallback."""
        with self.saving_artifacts():
            self.page.add_init_script("delete Navigator.prototype.share;")
            self.page.goto(f"{self.live_server_url}/family")
            expect(self.page.get_by_role("button", name="傳給家人")).to_be_hidden()
            expect(self.main().get_by_text("/family")).to_be_visible()

    def test_family_guide_share_sheet(self):
        """Acceptance 6: the button hands this page's address and title to a stubbed share sheet."""
        with self.saving_artifacts():
            self.page.add_init_script(
                "navigator.share = (data) => { window.shared = data; return Promise.resolve(); };"
            )
            url = f"{self.live_server_url}/family"
            self.page.goto(url)
            self.page.get_by_role("button", name="傳給家人").click()
            shared = self.page.evaluate("window.shared")
            self.assertEqual(shared["url"], url)
            self.assertTrue(shared["title"].startswith("給家人的溝通與陪伴"))

    def test_family_guide_jumps_to_each_topic_and_marks_the_urgent_one(self):
        """#240: the jump links reach their topic; the urgent topic and 119 stand out."""
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/family")
            jumps = self.page.get_by_role("navigation", name="本頁內容").get_by_role("link")
            expect(jumps).to_have_count(3)
            topics = (
                ("talk-title", "怎麼跟聽損的家人說話"),
                ("aid-title", "陪伴配戴助聽器"),
                ("urgent-title", "什麼時候要馬上就醫"),
            )
            for anchor, name in topics:
                with self.subTest(name=name):
                    self.page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
                    link = jumps.filter(has_text=name)
                    self.assertGreaterEqual(link.bounding_box()["height"], 44)
                    link.click()
                    expect(self.page).to_have_url(re.compile(f"#{anchor}$"))
                    # The jump lands the heading at the top, not just somewhere on screen; the
                    # site scrolls smoothly, so wait for it to arrive.
                    self.page.wait_for_function(
                        "id => Math.abs(document.getElementById(id).getBoundingClientRect().top)"
                        " < 10 && window.scrollY > 0",
                        arg=anchor,
                    )
            urgent = self.main().locator("section", has=self.page.locator("#urgent-title"))
            calm = self.main().locator("section", has=self.page.locator("#talk-title"))

            def style(locator, prop):
                return locator.evaluate(f"el => getComputedStyle(el).{prop}")

            self.assertNotEqual(style(urgent, "backgroundColor"), style(calm, "backgroundColor"))
            self.assertNotEqual(style(urgent, "borderTopColor"), style(calm, "borderTopColor"))
            number = urgent.get_by_text("119", exact=True)
            body = urgent.get_by_text("如果同時出現", exact=False)
            self.assertGreater(
                float(style(number, "fontSize")[:-2]), float(style(body, "fontSize")[:-2])
            )

    def step1_start_goes_to_register(self):
        # Spec #148 (ticket #150): first-time visitors register straight away.
        self.page.goto(self.live_server_url)
        self.main().get_by_role("link", name="開始篩檢").click()
        expect(self.page).to_have_url(re.compile(r"/register\?next=/questionnaire_list$"))

    def assert_step_bar(self, done, total):
        segments = self.main().locator(".step-progress-bar > .step-progress-segment")
        expect(segments).to_have_count(total)
        expect(segments.and_(self.page.locator(".is-done"))).to_have_count(done)

    def step2_register(self):
        # #151: two numbered steps, register then consent.
        expect(self.main().locator(".step-progress-text")).to_have_text(
            "第 1 步／共 2 步：建立帳號"
        )
        self.assert_step_bar(1, 2)
        self.fill_register_form()
        self.main().get_by_role("button", name="註冊").click()
        # New accounts agree to the privacy notice first (spec phase7_consent_privacy.md).
        expect(self.main().locator(".step-progress-text")).to_have_text(
            "第 2 步／共 2 步：同意隱私權"
        )
        self.assert_step_bar(2, 2)
        self.main().get_by_role("button", name="我同意，開始篩檢", exact=True).click()
        expect(self.page.get_by_text("目前登入：e2e_user")).to_be_visible()
        expect(self.page).to_have_url(re.compile(r"/questionnaire_list\?from=consent$"))

    def fill_register_form(self):
        self.page.get_by_label("使用者名稱").fill("e2e_user")
        self.page.get_by_label("電子郵件").fill("e2e_user@example.com")
        self.page.get_by_label("密碼", exact=True).fill("Fake-pass-2468")
        # Exact: the "顯示密碼確認" toggle button (#151) also has 密碼確認 in its label.
        self.page.get_by_label("密碼確認", exact=True).fill("Fake-pass-2468")

    def choose_self(self):
        # #152: the wizard's way out to every questionnaire's card.
        self.main().get_by_role("link", name="自己選問卷").click()

    def step3_choose_hhie_s(self):
        # #345 wizard: what the user most wants to know, then the age (no birth year), then the
        # recommendation.
        guide = self.main().locator(".questionnaire-guide")
        steps = self.main().locator(".step-progress-text")
        # Coming from consent: the first screen says the account is done, so 第 1 步 is new.
        expect(guide).to_have_text("帳號建好了\N{FULLWIDTH EXCLAMATION MARK}接下來幫您找適合的問卷")
        expect(steps).to_have_text("第 1 步／共 3 步")
        self.assert_step_bar(1, 3)
        self.main().get_by_role("group", name="您最想了解什麼？").get_by_label(
            "聽不清楚對生活、心情的影響", exact=True
        ).check()
        self.main().get_by_role("button", name="下一步").click()
        expect(guide).to_have_count(0)
        expect(steps).to_have_text("第 2 步／共 3 步")
        self.assert_step_bar(2, 3)
        self.main().get_by_role("group", name="您目前的實際年齡？").get_by_label(
            "65 歲以上", exact=True
        ).check()
        self.main().get_by_role("button", name="下一步").click()
        expect(steps).to_have_text("第 3 步／共 3 步")
        self.assert_step_bar(3, 3)
        expect(self.main().get_by_role("heading", name="推薦您做這一份")).to_be_visible()
        expect(self.main().locator("#recommended-title")).to_contain_text("HHIE-S")
        expect(self.main()).to_contain_text(
            "為什麼推薦：這份問卷幫您了解聽力對日常生活和心情的影響。"
        )
        # Only the hearing-aid answer has more worth doing.
        expect(self.main().get_by_role("heading", name="也可以做")).to_have_count(0)
        self.main().get_by_role("link", name="開始作答").click()
        # Unaided: no 沒戴 preselection (#154).
        expect(self.page).to_have_url(re.compile(r"/questionnaire/\d+$"))
        # React took over: only its hearing aid question shows, the Django form is hidden.
        hearing_aid = self.page.get_by_role("group", name="這次填答時，您有沒有戴助聽器？")
        expect(hearing_aid).to_be_visible()
        expect(self.page.get_by_role("group")).to_have_count(1)

    def step4_answer_and_change_one(self):
        app = self.main().locator(".answer-app")
        about = self.main().get_by_role("button", name="這份問卷在問什麼？")
        progress = self.main().locator(".answer-app .question-progress")
        # #153: the hearing aid step shows the whole intro and no question count.
        expect(app).to_contain_text("本問卷的目的在幫助您了解自己的聽力")
        expect(app).to_contain_text("答案會自動存在這支手機，中途離開也沒關係")
        expect(about).to_have_count(0)
        self.assert_step_bar(0, 0)
        self.answer("沒戴")
        self.next()
        # From question 1 the intro folds away until asked for.
        expect(app.get_by_text("本問卷的目的", exact=False)).to_have_count(0)
        expect(about).to_have_attribute("aria-expanded", "false")
        self.assert_step_bar(0, QUESTION_COUNT)
        expect(progress).to_have_text("第 1 題／共 10 題・還剩大約 3 分鐘")
        about.click()
        expect(about).to_have_attribute("aria-expanded", "true")
        expect(self.page.locator("#answer-intro-text")).to_contain_text("本問卷的目的")
        self.answer("常常", number=1)
        self.next()
        self.answer("有時", number=2)
        # Back to question 1: its first answer is still there; change it.
        self.main().get_by_role("button", name="上一題").click()
        expect(self.question(1).get_by_label("常常")).to_be_checked()
        self.answer("有時", number=1)
        self.next()
        expect(self.question(2).get_by_label("有時")).to_be_checked()
        for number in range(3, QUESTION_COUNT + 1):
            self.next()
            self.answer("有時", number=number)
            if number == 3:
                # #153 acceptance 1: 3 of 10 segments answered; 3 minutes x 8/10 left, rounded.
                self.assert_step_bar(3, QUESTION_COUNT)
                expect(progress).to_have_text("第 3 題／共 10 題・還剩大約 2 分鐘")
        # Rounded down to none on the last question, but never less than a minute.
        expect(progress).to_have_text("第 10 題／共 10 題・還剩大約 1 分鐘")

    def step5_submit(self):
        self.main().get_by_role("button", name="送出").click()
        expect(self.page).to_have_url(re.compile(r"/submission/\d+$"))
        # Every answer 有時 (2 points) x 10, question 1 counted with its changed answer.
        expect(self.page.get_by_text("總分 20 分")).to_be_visible()
        # The banner only: the score bar below it repeats the level name (ticket #158).
        expect(self.page.locator(".result-banner").get_by_text("輕度到中度影響")).to_be_visible()

    def step6_history(self):
        nav = self.page.get_by_role("navigation", name="主要導覽")
        nav.get_by_role("link", name="紀錄").click()
        # Each record is one card link (spec phase9_ui_refresh_1_shared.md 4.5).
        card = self.main().locator("a.link-card:not(.action-card)")
        expect(card).to_have_count(1)
        expect(card).to_contain_text("總分：20")
        # The record card only: the trend summary above it repeats the level text.
        expect(card.get_by_text("輕度到中度影響")).to_be_visible()

    def step7_report_prints_without_site_chrome(self):
        # Spec phase8_c3_report.md acceptance 8: only a real browser applies the print styles.
        self.main().get_by_role("link", name="聽力報告").click()
        expect(self.page.get_by_role("heading", name="HearWell 聽力報告")).to_be_visible()
        nav = self.page.get_by_role("navigation", name="主要導覽")
        print_button = self.page.get_by_role("button", name="列印或存成 PDF")
        header = self.page.locator(".site-header")
        footer = self.page.get_by_role("link", name="隱私權說明")
        for part in (nav, print_button, header, footer):
            expect(part).to_be_visible()
        self.page.emulate_media(media="print")
        for part in (nav, print_button, header, footer):
            expect(part).to_be_hidden()
        expect(self.page.get_by_role("heading", name="重點摘要")).to_be_visible()
        self.page.emulate_media(media="screen")


class AnswerIconsHintTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#329 (spec #326 A6, C5): the answer page's direction icons, and the hint when 下一題 or
    送出 is pressed with nothing chosen."""

    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        hhie_s = Questionnaire.objects.get(code="hhie-s")
        self.client.force_login(consented_user(username="answer_hint_e2e"))
        self.context = self.browser.new_context(**self.playwright.devices["Pixel 7"])
        self.context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
                    "url": self.live_server_url,
                }
            ]
        )
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)
        self.page.goto(f"{self.live_server_url}/questionnaire/{hhie_s.pk}")

    def assert_icon(self, name, side):
        """The button keeps its name; a drawn icon sits on that side of the words."""
        button = self.main().get_by_role("button", name=name, exact=True)
        icon = button.locator(f"svg:{side}-child")
        expect(icon).to_be_visible()
        expect(icon).to_have_attribute("aria-hidden", "true")
        self.assertGreater(icon.bounding_box()["width"], 10, name)
        return icon

    def arrow_points(self, icon):
        """Which way a drawn arrow points: the side its head's two wings sit on."""
        return icon.locator("path").evaluate(
            """path => {
                const length = path.getTotalLength();
                const box = path.getBBox();
                const middle = box.y + box.height / 2;
                const wings = [];
                for (let at = 0; at <= length; at += length / 200) {
                    const point = path.getPointAtLength(at);
                    // Only the head reaches far above and below the shaft.
                    if (Math.abs(point.y - middle) > box.height / 3) wings.push(point.x);
                }
                const x = wings.reduce((sum, value) => sum + value, 0) / wings.length;
                return x < box.x + box.width / 2 ? "left" : "right";
            }"""
        )

    def assert_asks_for_a_choice(self, number):
        expect(self.main().get_by_role("alert")).to_have_text("請先選一個答案")
        expect(self.question(number).locator("legend")).to_be_focused()

    def test_icons_and_the_choose_first_hint(self):
        with self.saving_artifacts():
            # Nothing chosen: 下一題 is not greyed out; pressing it says what is missing.
            expect(self.main().get_by_role("button", name="下一題")).to_be_enabled()
            self.assertEqual(self.arrow_points(self.assert_icon("下一題", "last")), "right")
            self.next()
            self.assert_asks_for_a_choice(None)
            expect(self.main().get_by_role("group")).to_contain_text("有沒有戴助聽器")
            self.answer("沒戴")
            expect(self.main().get_by_role("alert")).to_have_count(0)
            self.next()
            self.assertEqual(self.arrow_points(self.assert_icon("上一題", "first")), "left")
            for number in range(1, QUESTION_COUNT):
                self.answer("有時", number)
                self.next()
            self.assert_icon("送出", "first")
            self.main().get_by_role("button", name="送出").click()
            self.assert_asks_for_a_choice(QUESTION_COUNT)
            self.assert_fits_a_phone_at_double_text_size("answer page hint", width=412)
            self.answer("有時", QUESTION_COUNT)
            expect(self.main().get_by_role("alert")).to_have_count(0)
            self.main().get_by_role("button", name="送出").click()
            expect(self.page).to_have_url(re.compile(r"/submission/\d+$"))


class SentMomentTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#330 (spec #326 B1): sending the answers shows a green ✓ 已送出, says 已送出, and only
    then opens the result page."""

    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.hhie_s = Questionnaire.objects.get(code="hhie-s")
        self.client.force_login(consented_user(username="sent_moment_e2e"))
        self.context = self.browser.new_context(**self.playwright.devices["Pixel 7"])
        self.context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
                    "url": self.live_server_url,
                }
            ]
        )
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def test_answering_shows_sent_then_opens_the_result(self):
        with self.saving_artifacts():
            answer_page = f"{self.live_server_url}/questionnaire/{self.hhie_s.pk}"
            self.page.goto(answer_page)
            self.answer("沒戴")
            self.next()
            for number in range(1, QUESTION_COUNT + 1):
                self.answer("有時", number)
                if number < QUESTION_COUNT:
                    self.next()
            self.main().get_by_role("button", name="送出").click()
            sent = self.main().get_by_role("button", name="已送出")
            expect(sent).to_be_visible()
            # The success green (--color-normal, ADR 0007), white words.
            expect(sent).to_have_css("background-color", "rgb(20, 87, 60)")
            expect(sent).to_have_css("color", "rgb(255, 255, 255)")
            expect(self.main().locator(".answer-app").get_by_role("status")).to_have_text("已送出")
            self.assertEqual(self.page.url, answer_page)
            expect(self.page).to_have_url(re.compile(r"/submission/\d+$"))
            submission = Submission.objects.get(user__username="sent_moment_e2e")
            self.assertEqual(self.page.url, f"{self.live_server_url}/submission/{submission.pk}")


class ProgressSavedTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#331 (spec #326 B4, C3, C4, ADR 0028): on the answer page the segment a choice just answered
    fills, another question's text fades in, and ✓ 已儲存 shows when the draft was kept."""

    fixtures = ("questions_fixture.json",)
    BLUE = "rgb(31, 78, 140)"  # --color-primary
    SAVED = "✓ 已儲存"
    ANIMATIONS = """el => el.getAnimations({subtree: true})
        .map(a => [a.animationName, a.effect.getTiming().duration])"""
    # The progress line's size and where the choices start below it, whatever the scroll.
    LAYOUT = """line => {
        const box = line.getBoundingClientRect();
        const choices = line.closest("fieldset").querySelector(".choice-group");
        return [box.width, box.height, choices.getBoundingClientRect().top - box.top];
    }"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.client.force_login(consented_user(username="progress_saved_e2e"))
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, reduced_motion="no-preference", refuse_storage=False):
        """Question 1 of HHIE-S, reached from the hearing aid question."""
        self.context = self.browser.new_context(
            **self.playwright.devices["Pixel 7"], reduced_motion=reduced_motion
        )
        self.context.add_cookies([self.cookie])
        if refuse_storage:
            self.context.add_init_script(
                "Storage.prototype.setItem = () => {"
                " throw new DOMException('denied', 'SecurityError'); };"
            )
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)
        hhie_s = Questionnaire.objects.get(code="hhie-s")
        self.page.goto(f"{self.live_server_url}/questionnaire/{hhie_s.pk}")
        self.answer("沒戴")
        self.next()
        self.question(1)

    def bar(self):
        return self.main().locator(".step-progress-bar")

    def segment(self, number):
        return self.bar().locator(".step-progress-segment").nth(number - 1)

    def question_text(self):
        return self.main().get_by_role("group").locator("legend > span:last-child")

    def back(self, number):
        self.main().get_by_role("button", name="上一題").click()
        self.question(number)

    def assert_on_question(self, number, faded):
        """Focus on the question as before; its text faded in (0.35 s) or is simply there."""
        expect(self.question(number).locator("legend")).to_be_focused()
        expect(self.question_text()).to_have_text(re.compile(r"\S"))
        animations = [["question-fade", 350]] if faded else []
        self.assertEqual(self.question_text().evaluate(self.ANIMATIONS), animations)

    def assert_fills(self, number):
        """Only that segment fills, over 0.35 s; with number None, nothing on the bar moves."""
        fill = [["progress-fill", 350]]
        self.assertEqual(self.bar().evaluate(self.ANIMATIONS), fill if number else [])
        if number:
            self.assertEqual(self.segment(number).evaluate(self.ANIMATIONS), fill)

    # #326 acceptance 12 and 13: answering fills only the new segment, going back fills nothing;
    # each question shown after moving fades in, with focus on it.
    def test_new_segment_fills_and_another_question_fades_in(self):
        self.open()
        with self.saving_artifacts():
            self.assert_on_question(1, faded=True)
            self.assert_fills(None)
            self.answer("有時", 1)
            self.assert_fills(1)
            self.next()
            self.assert_on_question(2, faded=True)
            self.assert_fills(None)
            expect(self.segment(1)).to_have_css("background-color", self.BLUE)
            self.answer("有時", 2)
            self.assert_fills(2)
            self.back(1)
            self.assert_on_question(1, faded=True)
            self.assert_fills(None)
            # Changing an answer fills nothing: the segment already was answered.
            self.answer("常常", 1)
            self.assert_fills(None)

    # #326 acceptance 23: with reduced motion nothing fills or fades; it is simply there.
    def test_reduced_motion_neither_fills_nor_fades(self):
        self.open(reduced_motion="reduce")
        with self.saving_artifacts():
            self.assert_on_question(1, faded=False)
            expect(self.question_text()).to_have_css("opacity", "1")
            self.answer("有時", 1)
            self.assert_fills(None)
            expect(self.segment(1)).to_have_css("background-color", self.BLUE)
            self.next()
            self.assert_on_question(2, faded=False)

    # #326 acceptance 9: ✓ 已儲存 shows beside the progress for about 1.5 s once the draft was
    # kept, without moving anything, at the usual and at double text size; not read aloud; the
    # footer's autosave note stays.
    def test_saved_shows_beside_the_progress_for_a_moment(self):
        self.open()
        with self.saving_artifacts():
            for number, double in ((1, False), (2, True)):
                with self.subTest(double_text_size=double):
                    if double:
                        self.page.locator("html").evaluate(
                            "html => html.style.setProperty('font-size', '225%', 'important')"
                        )
                    line = self.main().locator(".question-progress-line")
                    before = line.evaluate(self.LAYOUT)
                    self.answer("有時", number)
                    saved = line.get_by_text(self.SAVED)
                    expect(saved).to_be_visible()
                    self.assertEqual(line.evaluate(self.LAYOUT), before)
                    expect(self.question(number)).not_to_have_accessible_name(re.compile("已儲存"))
                    expect(saved).to_have_count(0, timeout=2500)
                    self.assertEqual(line.evaluate(self.LAYOUT), before)
                    expect(self.main()).to_contain_text(
                        "答案會自動存在這支手機，中途離開也沒關係。"
                    )
                    self.next()

    # #326 acceptance 9: storage refused (private mode, blocked): the answer counts, no 已儲存.
    def test_no_saved_when_the_draft_cannot_be_kept(self):
        self.open(refuse_storage=True)
        with self.saving_artifacts():
            self.answer("有時", 1)
            self.assert_fills(1)
            self.page.wait_for_timeout(500)
            expect(self.main().get_by_text(self.SAVED)).to_have_count(0)


class CopyPasswordRegisterFeedbackTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#332 (spec #326 B3, D5, D6): copy, show-password and register field feedback."""

    GREEN = "rgb(20, 87, 60)"  # --color-normal, the site's success green
    SLASH = "M3 3l18 18"  # the line across the 隱藏 eye

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def open(self, width=412, height=900, signed_in=False):
        self.context = self.browser.new_context(viewport={"width": width, "height": height})
        if signed_in:
            user = consented_user(username="feedback_e2e")
            ReportShare.objects.create(user=user)
            self.client.force_login(user)
            self.context.add_cookies(
                [
                    {
                        "name": settings.SESSION_COOKIE_NAME,
                        "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
                        "url": self.live_server_url,
                    }
                ]
            )
            self.context.grant_permissions(
                ["clipboard-read", "clipboard-write"], origin=self.live_server_url
            )
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    # Spec #326 acceptance 8 (B3); every press saying it again is in copy-link.test.js.
    def test_copy_button_turns_green_with_a_tick_then_back(self):
        self.open(signed_in=True)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/share")
            button = self.main().locator("#copy-link")
            expect(button).to_have_accessible_name("複製連結")
            expect(button).not_to_have_css("background-color", self.GREEN)
            button.click()
            expect(button).to_have_accessible_name("已複製")
            expect(button).to_have_text("已複製")
            expect(button.locator("svg")).to_be_visible()
            expect(button).to_have_css("background-color", self.GREEN)
            expect(button).to_have_css("color", "rgb(255, 255, 255)")
            # The words under the button are for screen readers only now.
            status = self.page.locator("#copy-status")
            expect(status).to_have_text("已複製")
            self.assertLessEqual(status.bounding_box()["width"], 1)
            expect(button).to_have_accessible_name("複製連結", timeout=3000)
            expect(button.locator("svg")).to_have_count(0)
            expect(button).not_to_have_css("background-color", self.GREEN)

    # Spec #326 acceptance 18 (D5).
    def test_show_password_has_an_open_then_a_slashed_eye(self):
        for page in ("login", "register"):
            with self.subTest(page=page):
                self.open()
                self.page.goto(f"{self.live_server_url}/{page}")
                toggle = self.main().locator("button.password-toggle").first
                eye = toggle.locator("svg")
                expect(eye).to_be_visible()
                name = toggle.get_attribute("aria-label")
                self.assertTrue(name.startswith("顯示"), name)
                self.assertNotIn(self.SLASH, eye.inner_html())
                # The eye sits on the words' line, about the words' size.
                size = float(toggle.evaluate("b => getComputedStyle(b).fontSize")[:-2])
                self.assertLessEqual(eye.bounding_box()["height"], 1.5 * size)
                toggle.click()
                expect(toggle).to_have_text("隱藏")
                expect(toggle).to_have_accessible_name(name.replace("顯示", "隱藏", 1))
                self.assertIn(self.SLASH, eye.inner_html())
                toggle.click()
                expect(toggle).to_have_text("顯示")
                expect(toggle).to_have_accessible_name(name)
                self.assertNotIn(self.SLASH, eye.inner_html())

    TICK = "M5 12.5l4.5 4.5L19 7.5"  # the tick's path, drawn in the field

    def tick(self, field):
        """The tick drawn in the field, or None: its picture, size and room, in px."""
        drawn = field.evaluate(
            """input => {
                const style = getComputedStyle(input);
                return {
                    image: style.backgroundImage,
                    size: parseFloat(style.backgroundSize),
                    position: style.backgroundPosition,
                    room: parseFloat(style.paddingRight),
                    height: input.clientHeight,
                };
            }"""
        )
        return drawn if self.TICK in drawn["image"] else None

    def assert_tick_inside(self, field, label):
        """The field shows the green tick at its right end, in room the typing never reaches."""
        tick = self.tick(field)
        self.assertIsNotNone(tick, label)
        self.assertIn("%2314573c", tick["image"], label)  # --color-normal, the success green
        # Centred down the field, its right side this far in from the field's right edge.
        gap = re.fullmatch(r"calc\(100% - ([\d.]+)px\) 50%", tick["position"])
        self.assertIsNotNone(gap, tick["position"])
        self.assertLessEqual(tick["size"] + float(gap.group(1)), tick["room"], label)
        self.assertLessEqual(tick["size"], tick["height"], label)

    # Spec #326 acceptance 19 (D6); the year rule's edges are in register-checks.test.js.
    def test_register_ticks_birth_year_and_confirmation_but_not_password(self):
        for width, size in ((412, None), (320, "225%")):
            with self.subTest(width=width, text_size=size):
                self.open(width=width, height=640)
                self.page.goto(f"{self.live_server_url}/register")
                self.page.wait_for_load_state("load")
                if size:
                    self.page.locator("html").evaluate(
                        f"html => html.style.setProperty('font-size', '{size}', 'important')"
                    )
                year = self.page.get_by_label("出生年", exact=True)
                password = self.page.get_by_label("密碼", exact=True)
                confirmation = self.page.get_by_label("密碼確認", exact=True)
                for field in (year, password, confirmation):
                    self.assertIsNone(self.tick(field))
                year.fill("200")
                self.assertIsNone(self.tick(year))
                year.fill("44")
                # The room for the tick must not squeeze out the typing at double text size:
                # a field with no room left takes no typing at all.
                expect(year).to_have_value("44")
                self.assert_tick_inside(year, "出生年")
                expect(self.main().get_by_role("status").filter(has_text="格式正確")).to_have_count(
                    1
                )
                year.fill("")
                self.assertIsNone(self.tick(year))
                password.fill("Fake-pass-2468")
                confirmation.fill("Fake-pass-246")
                self.assertIsNone(self.tick(confirmation))
                confirmation.fill("Fake-pass-2468")
                self.assert_tick_inside(confirmation, "密碼確認")
                expect(
                    self.main().get_by_role("status").filter(has_text="兩次密碼相同")
                ).to_have_count(1)
                # 密碼 itself never gets one.
                self.assertIsNone(self.tick(password))
                year.fill("44")
                if size:
                    self.assert_fits_a_phone_at_double_text_size("register with ticks", width)

    RED_BG = "rgb(254, 236, 231)"  # --color-severe-bg, the wrong field's fill

    # Owner's call (2026-10-24, #326 self-review): the tick takes the server's red frame and
    # words for that field away with it; going wrong again does not bring them back.
    def test_register_tick_takes_the_servers_red_frame_away(self):
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/register")
            self.page.get_by_label("使用者名稱").fill("tick_e2e")
            self.page.get_by_label("電子郵件").fill("tick_e2e@example.com")
            self.page.get_by_label("密碼", exact=True).fill("Fake-pass-2468")
            self.page.get_by_label("密碼確認", exact=True).fill("Fake-pass-246")
            self.page.get_by_label("出生年", exact=True).fill("200")
            self.main().get_by_role("button", name="註冊", exact=True).click()
            self.page.wait_for_load_state("load")
            fields = (
                (self.page.get_by_label("出生年", exact=True), "44", "200"),
                (self.page.get_by_label("密碼確認", exact=True), "Fake-pass-2468", "x"),
            )
            for field, _, _ in fields:
                expect(field).to_have_attribute("aria-invalid", "true")
                expect(field).to_have_css("background-color", self.RED_BG)
                field_id = field.get_attribute("id")
                expect(self.page.locator(f"#{field_id}_error")).to_be_visible()
            self.page.get_by_label("密碼", exact=True).fill("Fake-pass-2468")
            for field, right, wrong in fields:
                field_id = field.get_attribute("id")
                field.fill(right)
                expect(field).not_to_have_attribute("aria-invalid", "true")
                expect(field).not_to_have_css("background-color", self.RED_BG)
                expect(self.page.locator(f"#{field_id}_error")).to_have_count(0)
                self.assertIsNotNone(self.tick(field), field_id)
                field.fill(wrong)
                expect(field).not_to_have_attribute("aria-invalid", "true")
                expect(self.page.locator(f"#{field_id}_error")).to_have_count(0)

    def send_register(self, password, confirmation):
        self.page.goto(f"{self.live_server_url}/register")
        self.page.get_by_label("使用者名稱").fill("weak_e2e")
        self.page.get_by_label("電子郵件").fill("weak_e2e@example.com")
        self.page.get_by_label("密碼", exact=True).fill(password)
        self.page.get_by_label("密碼確認", exact=True).fill(confirmation)
        self.main().get_by_role("button", name="註冊", exact=True).click()
        self.page.wait_for_load_state("load")

    # Owner's call (2026-10-24): the tick on 密碼確認 answers only 「兩次密碼不一致」; what the
    # server said about the password itself stays, red frame and all.
    def test_confirmation_tick_keeps_the_servers_word_on_a_weak_password(self):
        self.open()
        with self.saving_artifacts():
            confirmation = self.page.get_by_label("密碼確認", exact=True)
            errors = self.page.locator("#id_password2_error .field-error")
            # A weak password typed twice differently: the server only says they differ.
            self.send_register("12345678", "1234567")
            expect(errors).to_have_count(1)
            expect(errors).to_have_attribute("data-code", "password_mismatch")
            self.page.get_by_label("密碼", exact=True).fill("12345678")
            confirmation.fill("12345678")
            self.assertIsNotNone(self.tick(confirmation))
            expect(errors).to_have_count(0)
            expect(confirmation).not_to_have_attribute("aria-invalid", "true")
            expect(confirmation).not_to_have_css("background-color", self.RED_BG)
            # The same weak password twice: the server's words are about the password itself.
            self.send_register("12345678", "12345678")
            said = errors.all_inner_texts()
            self.assertGreaterEqual(len(said), 1)
            self.page.get_by_label("密碼", exact=True).fill("12345678")
            confirmation.fill("12345678")
            self.assertIsNotNone(self.tick(confirmation))
            expect(errors).to_have_text(said)
            expect(confirmation).to_have_attribute("aria-invalid", "true")
            expect(confirmation).to_have_css("background-color", self.RED_BG)
            expect(confirmation).to_have_attribute(
                "aria-describedby", re.compile(r"\bid_password2_error\b")
            )


class ReturningUserRetestTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#163: a returning user whose last HHIE-S is over 6 months old takes it again."""

    fixtures = ("questions_fixture.json",)
    TAIPEI = ZoneInfo("Asia/Taipei")
    REMINDER = "距離上次的生活影響評估已經滿 6 個月，建議再做一次追蹤。"
    RETEST_BUTTON = "再做一次（大約 3 分鐘）"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        # 200 days ago is past 6 months whatever today is. Unaided, like the retest below, so
        # 我的紀錄 compares the two (the comparison only pairs records worn the same way).
        user = consented_user(username="returning_e2e")
        self.hhie_s = Questionnaire.objects.get(code="hhie-s")
        old = Submission.objects.create(
            user=user, questionnaire=self.hhie_s, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=old, question=question, score=4)
            for question in self.hhie_s.questions.all()
        )
        old_moment = datetime.now(self.TAIPEI) - timedelta(days=200)
        Submission.objects.filter(pk=old.pk).update(created_at=old_moment)
        self.old_date = f"{old_moment:%Y/%m/%d}"
        self.client.force_login(user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, **device):
        self.context = self.browser.new_context(**{**self.playwright.devices["Pixel 7"], **device})
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def test_returning_user_retests_hhie_s(self):
        self.open()
        with self.saving_artifacts():
            self.step1_history_shows_the_reminder()
            self.step2_home_shows_the_reminder()
            self.step3_retest()
            self.step4_result_steps_and_score_bar()
            self.step5_home_shows_the_next_date()
            self.step6_history_compares_with_last_time()

    def test_home_and_result_fit_a_phone_at_double_text_size(self):
        """#163 acceptance 3: the returning user's home before and after, and the result."""
        self.open(viewport={"width": 320, "height": 640})
        with self.saving_artifacts():
            self.page.goto(self.live_server_url)
            self.assert_fits_a_phone_at_double_text_size("home, retest due")
            self.page.goto(self.live_server_url)
            self.step3_retest()
            self.assert_fits_a_phone_at_double_text_size("result")
            self.page.goto(self.live_server_url)
            expect(self.main()).to_contain_text("下次建議")
            self.assert_fits_a_phone_at_double_text_size("home, next date")

    def test_screening_tab_shows_the_catalogue_with_last_dates(self):
        """#346 (#339 acceptance 1, 2, 8, 22): 篩檢 opens the catalogue, not the wizard."""
        call_command("seed_questionnaires", verbosity=0)
        self.open(viewport={"width": 320, "height": 640})
        with self.saving_artifacts():
            self.page.goto(self.live_server_url)
            nav = self.page.get_by_role("navigation", name="主要導覽")
            nav.get_by_role("link", name="篩檢").click()
            expect(nav.locator('a[aria-current="page"]')).to_have_text("篩檢")
            expect(self.main().get_by_role("group", name="您最想了解什麼？")).to_have_count(0)
            cards = self.main().locator("a.questionnaire-card")
            expect(cards).to_have_count(6)
            expect(cards.first).to_contain_text("HHIE-S")
            last = cards.locator(".card-tag", has_text="上次")
            expect(last).to_have_count(1)
            expect(cards.first.locator(".card-tag").last).to_have_text(f"上次 {self.old_date}")
            # #347: the retest is due, so HHIE-S is recommended on top, and still a card below.
            recommended = self.main().get_by_role("region", name="推薦您做這一份")
            expect(recommended).to_contain_text("HHIE-S")
            expect(recommended).to_contain_text(self.REMINDER)
            self.assert_fits_a_phone_at_double_text_size("catalogue")
            tag = cards.first.locator(".card-tag").last
            self.assertEqual(tag.evaluate("e => e.getClientRects().length"), 1)
            self.assertLessEqual(tag.evaluate("e => e.getBoundingClientRect().right"), 320)
            self.main().get_by_role("link", name="回答幾個問題，幫您挑").click()
            expect(self.main().get_by_role("group", name="您最想了解什麼？")).to_be_visible()
            self.main().get_by_role("link", name="上一步").click()
            expect(self.page).to_have_url(f"{self.live_server_url}/questionnaire_list")
            expect(cards).to_have_count(6)

    def test_both_recommended_life_impact_questionnaires_fit_a_phone(self):
        """#347 (#339 acceptance 5, 22): only THI and no birth year, so the recommendation lists
        HHIE-S and HHIA-S, each with its ages and button; 320px at 200% text."""
        call_command("seed_questionnaires", verbosity=0)
        user = consented_user(username="thi_only_e2e")
        Submission.objects.create(user=user, questionnaire=Questionnaire.objects.get(code="thi"))
        self.client.force_login(user)
        self.cookie["value"] = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.open(viewport={"width": 320, "height": 640})
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire_list")
            recommended = self.main().get_by_role("region", name="推薦您做這一份")
            starts = recommended.get_by_role("link", name="開始作答")
            expect(starts).to_have_count(2)
            expect(starts.first).to_have_accessible_name(re.compile(r"^開始作答\s*：HHIE-S\s*$"))
            expect(recommended).to_contain_text("適合 65 歲以上的長輩。")
            expect(recommended).to_contain_text("適合 18–64 歲成人")
            self.assert_fits_a_phone_at_double_text_size("catalogue, both recommended")
            content_width, box_width = recommended.evaluate("e => [e.scrollWidth, e.clientWidth]")
            self.assertLessEqual(content_width, box_width, "推薦您做這一份")

    def test_history_fits_a_phone_at_double_text_size(self):
        """#163 acceptance 3: 我的紀錄 due, with the reminder and its button, and after the
        retest, with 和上一次比 and the trend chart."""
        self.open(viewport={"width": 320, "height": 640})
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing")
            reminder = self.page.locator("#retest-reminder")
            expect(reminder).to_contain_text(self.REMINDER)
            expect(
                reminder.get_by_role("link", name=self.RETEST_BUTTON, exact=True)
            ).to_be_visible()
            expect(self.page.locator(".recharts-wrapper")).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("my_hearing, retest due")
            self.page.goto(self.live_server_url)
            self.step3_retest()
            self.page.goto(f"{self.live_server_url}/my_hearing")
            expect(self.main().get_by_role("region", name="和上一次比")).to_be_visible()
            # The trend chart arrives after the page loads; measure the page with it.
            expect(self.page.locator(".recharts-wrapper")).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("my_hearing")
            # Its dates stay inside its own box, not only inside the page.
            since_last = self.main().get_by_role("region", name="和上一次比")
            content_width, box_width = since_last.evaluate("e => [e.scrollWidth, e.clientWidth]")
            self.assertLessEqual(content_width, box_width, "和上一次比")

    def step1_history_shows_the_reminder(self):
        # Before the retest: the reminder is there and one record has nothing to compare with.
        self.page.goto(f"{self.live_server_url}/my_hearing")
        expect(self.page.locator("#retest-reminder")).to_contain_text(self.REMINDER)
        expect(self.main().get_by_role("region", name="和上一次比")).to_have_count(0)

    def step2_home_shows_the_reminder(self):
        self.page.goto(self.live_server_url)
        expect(self.main().get_by_role("heading", name="歡迎回來")).to_be_visible()
        expect(self.main()).to_contain_text(f"上次是 {self.old_date} 做的")
        expect(self.main().locator(".result-banner")).to_contain_text("HHIE-S 總分 40 分")
        expect(self.main()).to_contain_text(self.REMINDER)

    def step3_retest(self):
        self.main().get_by_role("link", name=self.RETEST_BUTTON, exact=True).click()
        expect(self.page).to_have_url(re.compile(rf"/questionnaire/{self.hhie_s.pk}$"))
        self.answer("沒戴")
        self.next()
        for number in range(1, QUESTION_COUNT + 1):
            self.answer("有時", number=number)
            if number < QUESTION_COUNT:
                self.next()
        self.main().get_by_role("button", name="送出").click()
        expect(self.page).to_have_url(re.compile(r"/submission/\d+$"))

    def step4_result_steps_and_score_bar(self):
        # Every answer 有時 (2 points) x 10.
        expect(self.main().locator("#result-score")).to_contain_text("總分 20 分")
        expect(self.main().locator(".result-banner")).to_contain_text("輕度到中度影響")
        # HHIE-S 輕度到中度影響's steps (ticket #157): the guide link, then the retest. The report
        # is left to the closing row, as this step's words do not mention it (result page tidy-up).
        expect(self.main().get_by_role("heading", name="接下來建議您")).to_be_visible()
        steps = self.main().locator("ol.next-steps > li")
        expect(steps).to_have_count(3)
        expect(steps.nth(0)).to_contain_text("聽力問題已經慢慢影響您的社交活動與情緒")
        expect(steps.nth(1)).to_contain_text("建議前往醫院耳鼻喉科進行聽力相關檢查")
        expect(steps.nth(1).get_by_role("link", name="看助聽器選配指引")).to_be_visible()
        expect(steps.nth(1).get_by_role("link", name="看／印聽力報告")).to_have_count(0)
        expect(steps.nth(2)).to_have_text("半年後再做一次，時間到了首頁會提醒您。")
        # Ticket #158: 20 of 40 sits halfway along the bar, inside the 輕度到中度 segment
        # (9-24 of 0-40).
        bar = self.page.locator(".score-bar-segments").bounding_box()
        marker = self.page.locator(".score-bar-marker").bounding_box()
        self.assertAlmostEqual(
            marker["x"], bar["x"] + (bar["width"] - marker["width"]) / 2, delta=0.5
        )
        mild = self.page.locator(".score-bar-segment-mild_to_moderate").bounding_box()
        centre = marker["x"] + marker["width"] / 2
        self.assertTrue(mild["x"] < centre < mild["x"] + mild["width"])
        # Text-heavy pages tidy-up: only this score's level, in bold under the marker, and the
        # two ends, 0 and 40.
        current = self.page.locator(".score-bar-current span")
        expect(current).to_have_text("輕度到中度影響")
        self.assertEqual(current.evaluate("el => getComputedStyle(el).fontWeight"), "700")
        label = current.bounding_box()
        self.assertTrue(label["x"] < centre < label["x"] + label["width"])
        expect(self.page.locator(".score-bar-ends > span")).to_have_text(["0", "40"])

    def step5_home_shows_the_next_date(self):
        self.main().get_by_role("link", name="回首頁").click()
        today = datetime.now(self.TAIPEI).date()
        expect(self.main()).to_contain_text(f"上次是 {today:%Y/%m/%d} 做的")
        expect(self.main().locator(".result-banner")).to_contain_text("HHIE-S 總分 20 分")
        expect(self.main()).to_contain_text(f"下次建議 {six_months_after(today):%Y/%m/%d} 再做")
        expect(self.main()).not_to_contain_text(self.REMINDER)

    def step6_history_compares_with_last_time(self):
        today = f"{datetime.now(self.TAIPEI):%Y/%m/%d}"
        self.page.get_by_role("navigation", name="主要導覽").get_by_role(
            "link", name="紀錄"
        ).click()
        expect(self.page.locator("#retest-reminder")).to_have_count(0)
        since_last = self.main().get_by_role("region", name="和上一次比")
        expect(since_last).to_contain_text(f"上一次（{self.old_date}）：40 分")
        expect(since_last).to_contain_text(f"最近一次（{today}）：20 分")
        # 40 then 20 points, both 沒戴.
        expect(since_last).to_contain_text("比上一次少 20 分（分數越低越好）")


class ContinueNoticeTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#326 E7 (#337): an unfinished draft is offered on the home and screening pages."""

    fixtures = ("questions_fixture.json",)
    NOTICE = "您上次的「聽力對生活的影響（HHIE-S）」答到第 2 題，答案都還在。"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.hhie_s = Questionnaire.objects.get(code="hhie-s")
        self.context = self.browser.new_context(**self.playwright.devices["Pixel 7"])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def log_in(self, username):
        client = Client()
        client.force_login(consented_user(username=username))
        self.context.clear_cookies()
        self.context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
                    "url": self.live_server_url,
                }
            ]
        )

    def test_draft_is_offered_on_home_and_screening_pages_to_its_account_only(self):
        with self.saving_artifacts():
            self.log_in("notice_a")
            self.page.goto(f"{self.live_server_url}/questionnaire/{self.hhie_s.pk}")
            self.answer("沒戴")
            self.next()
            self.answer("有時", 1)
            self.next()
            self.question(2)
            for path in ("/", "/questionnaire_list"):
                self.page.goto(f"{self.live_server_url}{path}")
                notice = self.main().locator("#continue-notice p")
                expect(notice).to_have_count(1)
                expect(notice).to_have_text(f"{self.NOTICE}接著答")
                self.assert_fits_a_phone_at_double_text_size(path, width=412)
            notice.get_by_role("link", name="接著答").click()
            expect(self.page).to_have_url(f"{self.live_server_url}/questionnaire/{self.hhie_s.pk}")
            expect(self.main()).to_contain_text("您上次答到第 2 題，要接著答嗎？")
            # Another account on the same phone sees nothing of it (#326 user story 49).
            self.log_in("notice_b")
            self.page.goto(self.live_server_url)
            expect(self.main().locator("h1")).to_be_visible()
            expect(self.main().locator("#continue-notice p")).to_have_count(0)
            expect(self.main()).not_to_contain_text("您上次的")


def six_months_after(day):
    """The same day six calendar months on, or that month's last day (ADR 0010)."""
    month_index = day.month + 5  # 0-based month, six months on
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


class SharedLayoutTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """Spec phase9_ui_refresh_1_shared.md acceptance 1, 2 and 11: only a browser lays pages out."""

    fixtures = ("questions_fixture.json",)
    CONTENT_MAX = 40 * 18  # 40rem at the 18px base
    AXIS_DATES = ".recharts-xAxis-tick-labels .recharts-cartesian-axis-tick-value"
    PREVIOUS_IOI = (4, 3, 2, 3, 4, 4, 2)
    LATEST_IOI = (5, 2, 3, 4, 3, 5, 1)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        # Fake records straight in the test database, then the session cookie in the browser.
        user = self.user = consented_user(username="layout_e2e")
        hhie_s = Questionnaire.objects.get(code="hhie-s")
        submission = Submission.objects.create(
            user=user, questionnaire=hhie_s, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=2)
            for question in hhie_s.questions.all()
        )
        audiogram = Audiogram.objects.create(user=user, tested_on=date(2026, 9, 28))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=40)
            for ear in ("right", "left")
            for f in (500, 1000, 2000, 4000)
        )
        ioi_ha = Questionnaire.objects.get(code="ioi-ha")
        # An earlier answer in the same norm group first, so the chart also draws its diamonds.
        for scores in (self.PREVIOUS_IOI, self.LATEST_IOI):
            ioi = Submission.objects.create(
                user=user,
                questionnaire=ioi_ha,
                norm_group=NormGroup.MILD_MODERATE,
                norm_basis=submission,
                wearing_hearing_aid=True,
            )
            Answer.objects.bulk_create(
                Answer(submission=ioi, question=question, score=score)
                for question, score in zip(ioi_ha.questions.all(), scores, strict=True)
            )
        self.client.force_login(user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }
        self.pages = [
            "/",
            "/my_hearing?questionnaire=hhie-s",
            "/my_hearing?questionnaire=ioi-ha",
            "/audiograms",
            "/questionnaire_list",
            "/report",
        ]

    def open(self, width, height=900, signed_in=True):
        self.context = self.browser.new_context(viewport={"width": width, "height": height})
        if signed_in:
            self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def record(self, code, score, wearing, when):
        """A record of code with every item scored score, made at when (Taipei) for a fixed date."""
        questionnaire = Questionnaire.objects.get(code=code)
        record = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=question, score=score)
            for question in questionnaire.questions.all()
        )
        Submission.objects.filter(pk=record.pk).update(
            created_at=datetime(*when, tzinfo=ZoneInfo("Asia/Taipei"))
        )
        return record

    def test_result_level_is_exposed_as_a_heading(self):
        self.open(390)
        record = self.user.submissions.get(questionnaire__code="hhie-s")
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/submission/{record.pk}")
            expect(self.page.get_by_role("heading", level=1)).to_have_count(1)
            level = self.page.get_by_role("heading", level=2, name="輕度到中度影響", exact=True)
            expect(level).to_be_visible()
            expect(level).to_have_attribute("aria-describedby", "result-score")
            expect(self.page.locator("#result-score")).to_contain_text("總分 20 分")

    def test_history_exposes_older_records_outside_the_chart_summary(self):
        self.open(390)
        questionnaire = Questionnaire.objects.get(code="hhie-s")
        expected = [(datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y/%m/%d"), 20)]
        for days_ago, score in ((2, 4), (5, 0)):
            record = Submission.objects.create(
                user=self.user, questionnaire=questionnaire, wearing_hearing_aid=False
            )
            Answer.objects.bulk_create(
                Answer(submission=record, question=q, score=score)
                for q in questionnaire.questions.all()
            )
            when = datetime.now(ZoneInfo("Asia/Taipei")) - timedelta(days=days_ago)
            Submission.objects.filter(pk=record.pk).update(created_at=when)
            expected.append((when.strftime("%Y/%m/%d"), score * 10))
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=hhie-s")
            expect(self.page.locator(".recharts-wrapper")).to_be_visible()
            for date_text, score in expected:
                accessible_date = date_text.replace("/", r"\/")
                accessible_name = re.compile(rf"{accessible_date}.*總分：{score}")
                expect(self.page.get_by_role("link", name=accessible_name)).to_have_count(1)

    def hold(self, url):
        """Requests to url wait in the returned list until release() lets them through."""
        held = []
        self.page.route(url, lambda route: held.append(route))
        return held

    def release(self, held):
        for _ in range(100):  # 5 seconds for the request to arrive
            if held:
                held[0].continue_()
                return
            self.page.wait_for_timeout(50)
        self.fail("The held request never came")

    # The trend chart draws after its data arrives; the record cards below must not move then.
    def test_trend_chart_does_not_push_the_records_down(self):
        sizes = ((320, False), (390, False), (1280, False), (320, True), (390, True))
        for width, large_text in sizes:
            with self.subTest(width=width, large_text=large_text):
                self.open(width)
                # Hold the records' API answer, so the page is measured before the chart draws.
                held = self.hold("**/api/submissions/")
                with self.saving_artifacts():
                    self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=hhie-s")
                    if large_text:
                        self.page.add_style_tag(content="html { font-size: 225% !important; }")
                    card = self.page.locator("a.link-card").first
                    before = card.bounding_box()["y"]
                    loading = self.page.get_by_text("趨勢圖載入中…")
                    expect(loading).to_be_visible()
                    self.release(held)
                    expect(self.page.locator(".recharts-wrapper")).to_be_visible()
                    expect(loading).to_have_count(0)
                    self.assertAlmostEqual(card.bounding_box()["y"], before, delta=1)

    def test_skip_link_moves_keyboard_focus_on_public_and_signed_in_pages(self):
        self.open(320)
        with self.saving_artifacts():
            for path in self.pages:
                self.page.goto(f"{self.live_server_url}{path}")
                skip = self.page.get_by_role("link", name="跳到主要內容", exact=True)
                self.page.keyboard.press("Tab")
                expect(skip).to_be_focused()
                expect(skip).to_be_visible()
                self.page.keyboard.press("Enter")
                expect(self.page.get_by_role("main")).to_be_focused()
            with self.browser.new_context(viewport={"width": 320, "height": 800}) as anonymous:
                page = anonymous.new_page()
                for path in ("/", "/login", "/register", "/privacy", "/family"):
                    with self.subTest(path=path):
                        page.goto(f"{self.live_server_url}{path}")
                        page.keyboard.press("Tab")
                        expect(page.get_by_role("link", name="跳到主要內容")).to_be_focused()
                        page.keyboard.press("Enter")
                        expect(page.get_by_role("main")).to_be_focused()

    def test_hhi_comparison_keyboard_errors_and_narrow_layout_without_js(self):
        """#82: explicit preview/save/remove works with keyboard and no scripts."""
        questionnaire = Questionnaire.objects.get(code="hhie-s")
        unaided = self.user.submissions.get(questionnaire=questionnaire)
        aided = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=True
        )
        Answer.objects.bulk_create(
            Answer(submission=aided, question=q, score=0) for q in questionnaire.questions.all()
        )
        self.context = self.browser.new_context(
            java_script_enabled=False, viewport={"width": 320, "height": 640}
        )
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/comparisons/{questionnaire.pk}")
            self.page.locator("html").evaluate("element => element.style.fontSize = '200%'")
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 320)
            # #190: radio cards, chosen with the keyboard.
            first = self.page.locator(f'input[name="unaided"][value="{unaided.pk}"]')
            first.focus()
            self.page.keyboard.press("Space")
            self.page.locator(f'input[name="aided"][value="{aided.pk}"]').check()
            expect(first).to_be_checked()
            self.page.get_by_role("button", name="查看比較", exact=True).click()
            expect(self.page.get_by_role("heading", name="目前查看的兩筆")).to_be_visible()
            expect(
                self.page.get_by_text("有戴比沒戴少 20 分（分數越低越好）", exact=True)
            ).to_be_visible()
            # Submit a stale/foreign id through the actual form to check server-side errors.
            self.page.locator('input[type="hidden"][name="aided"]').evaluate(
                "el => el.value = '999999'"
            )
            self.page.get_by_role("button", name="放進聽力報告", exact=True).click()
            expect(self.page.locator("#comparison-errors")).to_be_focused()
            expect(self.page.get_by_role("heading", name="聽力報告裡的組合")).to_have_count(0)
            self.page.locator(f'input[name="aided"][value="{aided.pk}"]').check()
            self.page.get_by_role("button", name="查看比較", exact=True).click()
            self.page.get_by_role("button", name="放進聽力報告", exact=True).focus()
            self.page.keyboard.press("Enter")
            expect(self.page.get_by_text("這一組已經在聽力報告裡", exact=True)).to_be_visible()
            self.page.get_by_role("button", name="從報告移除", exact=True).click()
            expect(self.page.get_by_role("heading", name="聽力報告裡的組合")).to_have_count(0)
            expect(self.page.get_by_role("button", name="從報告移除")).to_have_count(0)

    def test_ioi_discloses_hhia_basis_before_saving(self):
        """#81: IOI-HA reveals and keeps the chosen adult HHI source."""
        call_command("seed_questionnaires", verbosity=0)
        questionnaire = Questionnaire.objects.get(code="hhia-s")
        basis = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=basis, question=q, score=4) for q in questionnaire.questions.all()
        )
        self.open(320)
        ioi = Questionnaire.objects.get(code="ioi-ha")
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire/{ioi.pk}")
            # #245: on React; only its copy of the intro shows, the page's own is hidden.
            told = self.main().locator(".answer-app").get_by_text("本次常模依據：", exact=False)
            expect(told).to_contain_text("HHIA-S")
            expect(told).to_contain_text("40 分")
            self.assert_fits_a_phone_at_double_text_size("IOI-HA answer item 1")
            self.answer_ioi_ha()
            expect(self.page.get_by_text("分組依據：", exact=False)).to_contain_text("HHIA-S")
            expect(self.page.get_by_text("分組依據：", exact=False)).to_contain_text("40 分")

    # 1
    def test_wide_screen_content_is_centred_and_narrow(self):
        self.open(1920)
        with self.saving_artifacts():
            for path in self.pages:
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    main = self.page.locator("main").bounding_box()
                    self.assertLessEqual(main["width"], self.CONTENT_MAX)
                    self.assertAlmostEqual(main["x"], (1920 - main["width"]) / 2, delta=1)
                    for band in (".site-header", ".site-footer"):
                        self.assertEqual(self.page.locator(band).bounding_box()["width"], 1920)

    # 2
    def test_phone_width_needs_no_sideways_scrolling(self):
        self.open(320, 640)
        with self.saving_artifacts():
            for path in self.pages:
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    # Not networkidle, which Playwright discourages and which once never came in
                    # CI: wait for the charts React draws (/report has an audiogram), then their
                    # fonts.
                    expect(self.page.get_by_text("趨勢圖載入中…")).to_have_count(0)
                    if self.page.locator("#audiogram-chart").count():
                        expect(self.page.locator("#audiogram-chart svg").first).to_be_visible()
                    self.page.evaluate("document.fonts.ready")
                    scroll_width = self.page.evaluate("document.documentElement.scrollWidth")
                    self.assertLessEqual(scroll_width, 320)
                    # Spec 4.3: at the very bottom the footer's last line clears the tab bar.
                    self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    last = self.page.locator(".site-footer p").last.bounding_box()
                    tab_bar = self.page.locator(".site-nav").bounding_box()
                    self.assertLessEqual(last["y"] + last["height"], tab_bar["y"])

    # 11
    def test_report_print_hides_footer_nav_and_sharing(self):
        self.open(1280)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/report")
            parts = [
                self.page.locator(".site-footer"),
                self.page.get_by_role("navigation", name="主要導覽"),
                self.page.locator("#report-share"),
            ]
            for part in parts:
                expect(part).to_be_visible()
            self.page.emulate_media(media="print")
            for part in parts:
                expect(part).to_be_hidden()

    # Pages tidy-up: the report on screen is cards with coloured level labels and no handwriting
    # line; on paper the line is back and the level is the plain bordered word, as before. The
    # family's copy shows its 「先看重點」 card on screen and the summary only on paper.
    def test_report_screen_and_paper_differ_only_where_meant(self):
        share = ReportShare.objects.create(user=self.user)
        self.open(390)
        clear = "rgba(0, 0, 0, 0)"
        background = "el => getComputedStyle(el).backgroundColor"
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/report")
            handwrite = self.page.locator(".report-handwrite")
            level = self.page.locator(".report-summary .report-level").first
            expect(handwrite).to_be_hidden()
            self.assertNotEqual(level.evaluate(background), clear)
            self.page.emulate_media(media="print")
            expect(handwrite).to_be_visible()
            self.assertEqual(level.evaluate(background), clear)
            self.page.emulate_media(media="screen")
            self.page.goto(f"{self.live_server_url}/shared/{share.token}/report")
            expect(self.page.locator("#family-highlights")).to_be_visible()
            expect(self.page.locator(".report-summary")).to_be_hidden()
            self.page.emulate_media(media="print")
            expect(self.page.locator(".report-summary")).to_be_visible()

    # phase9_ui_refresh_2_data.md acceptance 12
    def test_ioi_ha_numbers_points_and_lines_line_up(self):
        self.open(1280)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=ioi-ha")

            def centre(locator):
                box = locator.bounding_box()
                return box["y"] + box["height"] / 2

            axis = self.page.locator(".ioi-axis")
            numbers = {
                int(span.text_content()): centre(span)
                for span in axis.locator(".ioi-grid > span").all()
            }
            self.assertEqual(sorted(numbers), [1, 2, 3, 4, 5])
            for row, score in enumerate((5, 4, 3, 2, 1), start=1):
                line = centre(axis.locator(f'.ioi-line[style="grid-row: {row}"]'))
                self.assertAlmostEqual(numbers[score], line, delta=1)
            columns = self.page.locator(".ioi-columns > li:not(.ioi-axis)")
            marks = ((".ioi-dot-latest", self.LATEST_IOI), (".ioi-dot-previous", self.PREVIOUS_IOI))
            for mark, scores in marks:
                for index, score in enumerate(scores):
                    with self.subTest(mark=mark, item=index + 1):
                        column = columns.nth(index)
                        dot = centre(column.locator(mark))
                        line = centre(column.locator(f'.ioi-line[style="grid-row: {6 - score}"]'))
                        self.assertAlmostEqual(dot, numbers[score], delta=1)
                        self.assertAlmostEqual(dot, line, delta=1)

    # phase9_ui_refresh_2_data.md 4.3 and acceptance 15: dates inside the chart, never crowded
    def test_trend_dates_stay_inside_and_apart(self):
        hhie_s = Questionnaire.objects.get(code="hhie-s")
        taipei = ZoneInfo("Asia/Taipei")
        for when, wearing in (
            ((2026, 9, 1, 10, 0), False),
            ((2026, 9, 20, 10, 0), False),
            ((2026, 10, 1, 10, 0), True),
            ((2026, 10, 15, 14, 30), False),
            ((2026, 10, 15, 16, 10), True),
        ):
            record = Submission.objects.create(
                user=self.user, questionnaire=hhie_s, wearing_hearing_aid=wearing
            )
            Answer.objects.bulk_create(
                Answer(submission=record, question=question, score=2)
                for question in hhie_s.questions.all()
            )
            Submission.objects.filter(pk=record.pk).update(
                created_at=datetime(*when, tzinfo=taipei)
            )
        for width in (320, 1280):
            with self.subTest(width=width):
                self.open(width)
                with self.saving_artifacts():
                    self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=hhie-s")
                    dates = self.page.locator(f"#trend-chart {self.AXIS_DATES}")
                    expect(dates.first).to_be_visible()
                    chart = self.page.locator("#trend-chart svg.recharts-surface").first
                    edge = chart.bounding_box()
                    boxes = sorted((d.bounding_box() for d in dates.all()), key=lambda b: b["x"])
                    for box in boxes:
                        self.assertGreaterEqual(box["x"], edge["x"])
                        self.assertLessEqual(box["x"] + box["width"], edge["x"] + edge["width"])
                    # At least 1.5rem (27px) between dates; a pixel of slack for text measuring.
                    for left, right in pairwise(boxes):
                        self.assertGreaterEqual(right["x"] - (left["x"] + left["width"]), 26)

    def test_ssq12_bar_fits_a_phone_at_double_text_size(self):
        # #188: the 0–10 bar's 「這次」 and 「上次」 sit at its two ends here, at 1rem.
        call_command("seed_questionnaires", verbosity=0)
        ssq12 = Questionnaire.objects.get(code="ssq12-tw")
        for score in (10, 0):  # the previous record averages 10, this one 0
            record = Submission.objects.create(
                user=self.user, questionnaire=ssq12, wearing_hearing_aid=False
            )
            Answer.objects.bulk_create(
                Answer(submission=record, question=question, score=score)
                for question in ssq12.questions.all()
            )
        self.open(320, 640)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/submission/{record.pk}")
            labels = self.page.locator(".ssq-bar-label")
            expect(labels).to_have_text(["這次", "上次"])
            self.assertEqual(labels.first.evaluate("e => getComputedStyle(e).fontSize"), "18px")
            # 2 x the site's 112.5% base, as OnAPhone.assert_fits_a_phone_at_double_text_size.
            self.page.wait_for_load_state("load")
            self.page.locator("html").evaluate(
                "html => html.style.setProperty('font-size', '225%', 'important')"
            )
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 320)

    # #192 (#183 接縫 3): batch 1's route, 結果頁 → 比較 → 放進聽力報告 → 聽力報告, for HHIE-S
    # and SSQ12-TW, each with two unaided records to choose from and one aided.
    def test_wearing_comparison_route_from_result_page_to_report(self):
        call_command("seed_questionnaires", verbosity=0)
        # setUp's unaided HHIE-S (20 points) gets a fixed date like the others.
        self.user.submissions.filter(questionnaire__code="hhie-s").update(
            created_at=datetime(2026, 9, 1, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        )
        self.record("hhie-s", 4, False, (2026, 8, 1, 10, 0))
        self.record("ssq12-tw", 3, False, (2026, 8, 2, 10, 0))
        self.record("ssq12-tw", 5, False, (2026, 9, 2, 10, 0))
        routes = (
            (
                self.record("hhie-s", 0, True, (2026, 10, 1, 10, 0)),
                ("2026/09/01・20 分", "2026/10/01・0 分"),
                ("20 分", "0 分", "有戴比沒戴少 20 分（分數越低越好）"),
                "report-difference",
                ("未配戴：2026/09/01 10:00，20 分", "配戴：2026/10/01 10:00，0 分"),
            ),
            (
                self.record("ssq12-tw", 7, True, (2026, 10, 2, 10, 0)),
                ("2026/09/02・平均 5.0 分", "2026/10/02・平均 7.0 分"),
                ("平均 5.0 分", "平均 7.0 分", "有戴比沒戴多 2.0 分（分數越高越好）"),
                "report-comparison-ssq12-tw",
                ("未配戴：2026/09/02 10:00，平均 5.0 分", "配戴：2026/10/02 10:00，平均 7.0 分"),
            ),
        )
        self.open(390)
        with self.saving_artifacts():
            for aided, (unaided_card, aided_card), card_texts, section, report_texts in routes:
                with self.subTest(questionnaire=aided.questionnaire.code):
                    self.page.goto(f"{self.live_server_url}/submission/{aided.pk}")
                    self.main().get_by_role("link", name="比較戴與不戴助聽器", exact=True).click()
                    expect(self.page).to_have_url(
                        re.compile(rf"/comparisons/{aided.questionnaire_id}$")
                    )
                    # Nothing kept yet (ADR 0003): only the lone aided record is chosen (F2); the
                    # two unaided ones wait for the user.
                    checked = self.main().get_by_role("radio", checked=True)
                    expect(checked).to_have_count(1)
                    expect(
                        self.main()
                        .get_by_role("group", name="戴助聽器時", exact=True)
                        .get_by_label(aided_card, exact=True)
                    ).to_be_checked()
                    choices = (("沒戴助聽器時", unaided_card), ("戴助聽器時", aided_card))
                    for legend, card in choices:
                        self.main().get_by_role("group", name=legend, exact=True).get_by_label(
                            card, exact=True
                        ).check()
                    self.main().get_by_role("button", name="查看比較", exact=True).click()
                    result = self.main().get_by_role("region", name="目前查看的兩筆")
                    for text in card_texts:
                        expect(result.get_by_text(text, exact=True)).to_be_visible()
                    expect(
                        result.get_by_text("差值不能單獨判定助聽器效益。", exact=True)
                    ).to_be_visible()
                    result.get_by_role("button", name="放進聽力報告", exact=True).click()
                    expect(self.main()).to_contain_text(
                        "已放進聽力報告，新增紀錄不會自動換掉這一組。"
                    )
                    # Pages tidy-up: the pair on screen is the saved one, so it shows once.
                    preview = self.main().get_by_role("region", name="目前查看的兩筆")
                    expect(preview).to_have_count(0)
                    saved = self.main().get_by_role("region", name="聽力報告裡的組合")
                    expect(saved.get_by_text("這一組已經在聽力報告裡", exact=True)).to_be_visible()
                    expect(saved.get_by_text(card_texts[2], exact=True)).to_be_visible()
                    self.page.goto(f"{self.live_server_url}/report")
                    for text in report_texts:
                        expect(self.page.locator(f"#{section}")).to_contain_text(text)

    # #192 (#183 acceptance 31): batch 1's new and redesigned pages, 320px wide at 200% text,
    # with every fold open: the IOI-HA and SSQ12-TW results, the HHIE-S result's comparison
    # entry, and the comparison page with its result card and the card of the kept pair.
    def test_batch1_pages_fit_a_phone_at_double_text_size(self):
        call_command("seed_questionnaires", verbosity=0)
        hhie_s = self.user.submissions.get(questionnaire__code="hhie-s")
        hhie_aided = self.record("hhie-s", 0, True, (2026, 10, 1, 10, 0))
        ssq_unaided = self.record("ssq12-tw", 5, False, (2026, 9, 2, 10, 0))
        self.record("ssq12-tw", 7, True, (2026, 10, 2, 10, 0))
        ssq_latest = self.record("ssq12-tw", 6, True, (2026, 10, 12, 10, 0))
        ReportComparison.objects.create(
            user=self.user, questionnaire=hhie_s.questionnaire, unaided=hhie_s, aided=hhie_aided
        )
        hhie_other = self.record("hhie-s", 2, True, (2026, 10, 5, 10, 0))
        ioi = self.user.submissions.filter(questionnaire__code="ioi-ha").latest("pk")
        self.open(320, 640)
        with self.saving_artifacts():
            with self.subTest(page="IOI-HA result"):
                self.page.goto(f"{self.live_server_url}/submission/{ioi.pk}")
                self.main().get_by_text(re.compile(r"^其他 \d+ 項$")).click()
                expect(self.main().locator(".ioi-others .ioi-item").first).to_be_visible()
                self.assert_fits_a_phone_at_double_text_size("IOI-HA result")
            with self.subTest(page="SSQ12-TW result"):
                self.page.goto(f"{self.live_server_url}/submission/{ssq_latest.pk}")
                expect(self.main()).to_contain_text("比上一次（2026/10/02，7.0 分）少 1.0 分")
                expect(self.main().get_by_role("heading", name="分數最低的 3 題")).to_be_visible()
                self.main().get_by_text("看全部 12 題的回答", exact=True).click()
                expect(
                    self.main().get_by_role("link", name="比較戴與不戴助聽器", exact=True)
                ).to_be_visible()
                self.assert_fits_a_phone_at_double_text_size("SSQ12-TW result")
            with self.subTest(page="HHIE-S result"):
                self.page.goto(f"{self.live_server_url}/submission/{hhie_aided.pk}")
                expect(
                    self.main().get_by_role("link", name="比較戴與不戴助聽器", exact=True)
                ).to_be_visible()
                self.assert_fits_a_phone_at_double_text_size("HHIE-S result")
            with self.subTest(page="HHIE-S comparison"):
                self.page.goto(
                    f"{self.live_server_url}/comparisons/{hhie_s.questionnaire_id}"
                    f"?unaided={hhie_s.pk}&aided={hhie_other.pk}&action=preview"
                )
                expect(
                    self.main().get_by_role("button", name="改放這一組到報告", exact=True)
                ).to_be_visible()
                expect(self.main().get_by_role("region", name="聽力報告裡的組合")).to_be_visible()
                self.assert_fits_a_phone_at_double_text_size("HHIE-S comparison")
            with self.subTest(page="SSQ12-TW comparison"):
                self.page.goto(
                    f"{self.live_server_url}/comparisons/{ssq_latest.questionnaire_id}"
                    f"?unaided={ssq_unaided.pk}&aided={ssq_latest.pk}&action=preview"
                )
                self.main().get_by_text("看每一題的回答", exact=True).click()
                expect(self.main().locator(".comparison-items li").first).to_be_visible()
                self.assert_fits_a_phone_at_double_text_size("SSQ12-TW comparison")

    # #198 (#183 batch 2 route): report -> share page -> make the link -> copy it -> the
    # family's cover -> the family's report, then the account page says the link is live.
    def test_share_route_from_report_to_family_report(self):
        self.open(390)
        self.context.grant_permissions(
            ["clipboard-read", "clipboard-write"], origin=self.live_server_url
        )
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/report")
            self.main().get_by_role("link", name="分享報告給家人", exact=True).click()
            expect(self.page).to_have_url(f"{self.live_server_url}/share")
            self.main().get_by_role("button", name="我知道了，產生連結", exact=True).click()
            expect(self.page).to_have_url(f"{self.live_server_url}/share")
            share = self.user.report_shares.get()
            self.main().get_by_role("button", name="複製連結", exact=True).click()
            # #332: the button itself says it now.
            expect(self.main().get_by_role("button", name="已複製", exact=True)).to_be_visible()
            copied = self.page.evaluate("navigator.clipboard.readText()")
            # The site always serves HTTPS; the test server only speaks HTTP, so the family
            # opens the copied path on it.
            host = self.page.evaluate("location.host")
            self.assertEqual(copied, f"https://{host}/shared/{share.token}")
            # The copy button takes the address's place; it comes back only if copying fails.
            expect(self.page.locator("#share-url")).to_be_hidden()

            family = self.browser.new_context(viewport={"width": 390, "height": 900})
            self.addCleanup(family.close)
            family_page = family.new_page()
            family_page.goto(copied.replace(f"https://{host}", self.live_server_url))
            expect(
                family_page.get_by_role("heading", name="家人分享了一份 HearWell 聽力報告給您")
            ).to_be_visible()
            family_page.get_by_role("link", name="打開報告", exact=True).click()
            expect(family_page).to_have_url(f"{self.live_server_url}/shared/{share.token}/report")
            highlights = family_page.get_by_role("region", name="先看重點")
            expect(highlights).to_contain_text("2026/09/28")
            expect(family_page.get_by_role("region", name="您可以怎麼幫忙")).to_be_visible()

            self.page.goto(f"{self.live_server_url}/account")
            expires = timezone.localtime(share.expires_at)
            expect(
                self.main().get_by_role("link", name=re.compile("^分享報告給家人"))
            ).to_contain_text(f"分享中，{expires:%Y/%m/%d} 到期")

    # #204 (#183 batch 3 route): a new audiogram in four steps -> its result -> compared with the
    # one from setUp (2026/09/28, 40 dB at the four average frequencies in both ears).
    def test_audiogram_route_in_four_steps_to_result_and_compare(self):
        self.open(390)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/audiograms/new")
            main = self.main()
            expect(main.get_by_text("第 1 步／共 4 步：檢查日期", exact=True)).to_be_visible()
            main.get_by_label("檢查日期").fill("2026-10-01")
            main.get_by_role("button", name="下一步：標右耳", exact=True).click()
            for ear, button in (("右耳", "右耳標完了，換左耳"), ("左耳", "左耳標完了，確認存檔")):
                expect(main.get_by_role("button", name=re.compile(f"^{ear}氣導"))).to_be_visible()
                # Opened on the right ear's step, the table stays open on the left ear's.
                if ear == "右耳":
                    main.get_by_text("用數值輸入（鍵盤或螢幕閱讀器）").click()
                for frequency in (500, 1000, 2000, 4000):
                    main.get_by_label(f"{ear}氣導 {frequency} Hz", exact=True).select_option("50")
                count = f"{ear}已標：氣導 4 個、骨導 0 個"
                expect(main.locator(".audiogram-count")).to_have_text(count)
                main.get_by_role("button", name=button, exact=True).click()
            expect(main.get_by_text("檢查日期：2026/10/01", exact=True)).to_be_visible()
            expect(main.get_by_text("右耳：氣導 4 個、骨導 0 個", exact=True)).to_be_visible()
            expect(main.get_by_text("中度")).to_have_count(0)
            main.get_by_role("button", name="存檔", exact=True).click()
            expect(self.page).to_have_url(re.compile(r"/audiograms/\d+$"))

            summary = main.get_by_role("region", name="兩耳程度")
            expect(summary).to_have_text(re.compile(r"右耳：\s*中度\s*左耳：\s*中度"))
            expect(main.locator(".audiogram-plot svg")).to_be_visible()
            main.get_by_role("link", name="和以前的聽力圖比較").click()

            expect(main.locator(".compare-pick summary").nth(0)).to_have_text(
                re.compile(r"舊\s*2026/09/28\s*換一張")
            )
            expect(main.locator(".compare-pick summary").nth(1)).to_have_text(
                re.compile(r"新\s*2026/10/01\s*換一張")
            )
            card = main.get_by_role("region", name="右耳的比較")
            expect(card).to_contain_text("右耳四頻平均：舊 40 → 新 50 dB HL，多 10 dB")
            expect(card).to_contain_text("程度：舊 輕度，新 中度")
            expect(card).to_contain_text("差最多的頻率：500、1000、2000、4000 Hz，各多 10 dB")
            expect(card.locator(".audiogram-plot svg")).to_be_visible()
            main.get_by_role("link", name="左耳", exact=True).click()
            expect(main.get_by_role("region", name="左耳的比較")).to_contain_text(
                "左耳四頻平均：舊 40 → 新 50 dB HL"
            )

    # #204: without JavaScript the compare page still changes an audiogram.
    def test_audiogram_compare_changes_one_without_javascript(self):
        older = Audiogram.objects.create(user=self.user, tested_on=date(2026, 6, 1))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=older, ear="right", conduction="air", frequency=f, db=20)
            for f in (500, 1000, 2000, 4000)
        )
        newest = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 1))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=newest, ear="right", conduction="air", frequency=f, db=50)
            for f in (500, 1000, 2000, 4000)
        )
        self.context = self.browser.new_context(
            viewport={"width": 390, "height": 900}, java_script_enabled=False
        )
        self.addCleanup(self.context.close)
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/audiograms/compare")
            rows = self.main().locator(".compare-pick")
            expect(rows.nth(0).locator("summary")).to_contain_text("2026/09/28")
            rows.nth(0).locator("summary").click()
            rows.nth(0).get_by_label("2026/06/01", exact=True).check()
            rows.nth(0).get_by_role("button", name="比較", exact=True).click()
            expect(rows.nth(0).locator("summary")).to_contain_text("2026/06/01")
            expect(rows.nth(1).locator("summary")).to_contain_text("2026/10/01")
            expect(self.main()).to_contain_text("右耳四頻平均：舊 20 → 新 50 dB HL，多 30 dB")

    # #204 (#183 acceptance 31): batch 3's pages, 320px wide at 200% text, every fold open.
    def test_batch3_pages_fit_a_phone_at_double_text_size(self):
        newer = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 1))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=newer, ear=ear, conduction="air", frequency=f, db=55)
            for ear in ("right", "left")
            for f in (500, 1000, 2000, 4000, 8000)
        )
        self.open(320, 640)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/audiograms/new")
            for step in ("檢查日期", "標右耳", "標左耳", "確認存檔"):
                with self.subTest(step=step):
                    expect(self.main()).to_contain_text(f"共 4 步：{step}")
                    for summary in self.main().locator("details > summary").all():
                        summary.click()
                    self.assert_fits_a_phone_at_double_text_size(f"new audiogram, {step}")
                    forward = self.main().get_by_role(
                        "button", name=re.compile("^下一步：標右耳$|換左耳$|確認存檔$")
                    )
                    if forward.count():
                        forward.click()
            for path in (f"/audiograms/{newer.pk}", "/audiograms/compare"):
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    self.page.locator(".audiogram-plot svg").wait_for()
                    for summary in self.main().locator("details > summary").all():
                        summary.click()
                    self.assert_fits_a_phone_at_double_text_size(path)

    # #198: without JavaScript the address is there to copy by hand and the phone blocks open.
    def test_share_page_and_add_to_home_without_javascript(self):
        ReportShare.objects.create(user=self.user)
        self.context = self.browser.new_context(
            viewport={"width": 390, "height": 900}, java_script_enabled=False
        )
        self.addCleanup(self.context.close)
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/share")
            expect(self.page.locator("#share-url")).to_be_visible()
            expect(self.page.locator("#share-url")).to_contain_text("/shared/")
            for name in ("複製連結", "再傳一次給家人"):
                expect(self.main().get_by_role("button", name=name, exact=True)).to_be_hidden()
            self.page.goto(f"{self.live_server_url}/add_to_home")
            for phone, step in (("我用 iPhone", "分享"), ("我用 Android", "⋮")):
                block = self.main().locator("details", has_text=phone)
                expect(block.locator("ol")).to_be_hidden()
                block.get_by_text(phone, exact=True).click()
                expect(block.locator("ol")).to_be_visible()
                expect(block.locator("ol")).to_contain_text(step)

    # #198 (#183 acceptance 31): batch 2's pages, 320px wide at 200% text, folds open.
    def test_batch2_pages_fit_a_phone_at_double_text_size(self):
        share = ReportShare.objects.create(user=self.user)
        self.open(320, 640)
        with self.saving_artifacts():
            for path in ("/share", "/account", "/privacy", "/add_to_home"):
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    for block in self.main().locator("details").all():
                        block.locator("summary").click()
                    self.assert_fits_a_phone_at_double_text_size(path)
            for path in (f"/shared/{share.token}", f"/shared/{share.token}/report"):
                with self.subTest(path="family " + path.rsplit("/", 1)[-1]):
                    family = self.browser.new_context(viewport={"width": 320, "height": 640})
                    self.addCleanup(family.close)
                    self.page = family.new_page()
                    self.page.goto(f"{self.live_server_url}{path}")
                    self.assert_fits_a_phone_at_double_text_size(path)

    # #198 (#183 story 121, ADR 0006): the phone blocks change colour when hovered and pressed,
    # and never move. #303: the account's link rows are link cards now, which move like any other.
    def test_account_rows_and_phone_blocks_only_change_colour(self):
        self.open(1024)
        background = "el => getComputedStyle(el).backgroundColor"
        with self.saving_artifacts():
            for path, selector in (("/add_to_home", ".dropdown-box > summary"),):
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    target = self.page.locator(selector).first
                    before = target.bounding_box()
                    rest = target.evaluate(background)
                    target.hover()
                    hovered = target.evaluate(background)
                    self.assertNotEqual(hovered, rest)
                    self.assertEqual(target.bounding_box(), before)
                    self.page.mouse.down()
                    self.assertNotEqual(target.evaluate(background), rest)
                    self.assertEqual(target.bounding_box(), before)
                    self.page.mouse.up()
            with self.subTest(rows="account details"):
                # Not links, so hovering or pressing them changes nothing at all.
                self.page.goto(f"{self.live_server_url}/account")
                for row in self.page.locator(".settings-row").all():
                    before = (row.bounding_box(), row.evaluate(background))
                    row.hover()
                    self.assertEqual((row.bounding_box(), row.evaluate(background)), before)
                    self.page.mouse.down()
                    self.assertEqual((row.bounding_box(), row.evaluate(background)), before)
                    self.page.mouse.up()

    # phase9_ui_refresh_3_structure.md acceptance 11: more questionnaires wrap, nothing off screen
    def test_many_questionnaires_wrap_on_a_phone(self):
        self.enterContext(register(*(fake_definition(f"extra-{n}") for n in (4, 5, 6))))
        for number in (4, 5, 6):
            extra = Questionnaire.objects.create(
                questionnaire_name=f"問卷{number}", code=f"extra-{number}"
            )
            Submission.objects.create(user=self.user, questionnaire=extra)
        self.open(320, 640)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=hhie-s")
            tabs = self.page.locator(".history-tabs a")
            expect(tabs).to_have_count(5)
            boxes = [tab.bounding_box() for tab in tabs.all()]
            for box in boxes:
                self.assertGreaterEqual(box["x"], 0)
                self.assertLessEqual(box["x"] + box["width"], 320)
                self.assertGreaterEqual(box["height"], 2.75 * 18 - 1)
            self.assertGreater(len({round(box["y"]) for box in boxes}), 1)  # more than one row
            scroll_width = self.page.evaluate("document.documentElement.scrollWidth")
            self.assertLessEqual(scroll_width, 320)
            # Text-heavy pages tidy-up: on a common phone the five tabs share two columns.
            self.page.set_viewport_size({"width": 390, "height": 800})
            columns = {round(tab.bounding_box()["x"]) for tab in tabs.all()}
            self.assertEqual(len(columns), 2)

    # phase9_ui_refresh_4b_questionnaire_cards.md review A: the icon's circle stays visible on hover
    def test_icon_circle_stays_visible_on_hover(self):
        self.open(1280)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire_list?choose=self")
            card = self.page.locator("a.link-card").first
            card.hover()
            colour = "el => getComputedStyle(el).backgroundColor"
            card_bg = card.evaluate(colour)
            icon_bg = card.locator(".questionnaire-icon").evaluate(colour)
            self.assertNotEqual(icon_bg, card_bg)

    # phase9_ui_refresh_4c_audiogram_thumbnails.md acceptance 9: no badge split over two lines
    def test_audiogram_cards_fit_a_phone(self):
        self.open(320, 640)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/audiograms")
            expect(self.page.locator(".audiogram-thumbnail").first).to_be_visible()
            badges = self.page.locator("main .level-badge")
            self.assertGreater(badges.count(), 0)
            for badge in badges.all():
                lines = badge.evaluate(
                    "el => el.getClientRects().length"
                )  # a badge broken over two lines has two boxes
                self.assertEqual(lines, 1)
            scroll_width = self.page.evaluate("document.documentElement.scrollWidth")
            self.assertLessEqual(scroll_width, 320)

    # #129: The legacy w-100 was 100%, Tailwind's is 25rem; the buttons fill their column again.
    def test_audiogram_entry_buttons_fill_their_column(self):
        for width in (390, 1024):
            self.open(width)
            with self.saving_artifacts():
                main = self.page.get_by_role("main")
                # #199: the ear steps hold masking and clear; saving is on the confirm step.
                # #333: masking is a switch now.
                for step, role, name in (
                    (2, "switch", "遮蔽"),
                    (2, "button", "清除剛標的點"),
                    (4, "button", "存檔"),
                ):
                    audiogram_step(self.page, self.live_server_url, step)
                    with self.subTest(width=width, button=name):
                        widths = main.get_by_role(role, name=name).evaluate(
                            """el => {
                                const column = el.parentElement;
                                const style = getComputedStyle(column);
                                const padding = parseFloat(style.paddingLeft)
                                    + parseFloat(style.paddingRight);
                                return [el.getBoundingClientRect().width,
                                        column.clientWidth - padding];
                            }"""
                        )
                        self.assertAlmostEqual(widths[0], widths[1], delta=0.5)

    # phase9_ui_refresh_4a_home.md acceptance 8: step cards stack on a phone
    def test_home_step_cards_stack_on_a_phone(self):
        # #159: the step cards are the new-user home's own elements; this fixture user has
        # records, so check signed out.
        self.open(320, 640, signed_in=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            boxes = [card.bounding_box() for card in self.page.locator(".step-cards > li").all()]
            # Spec #148 (ticket #150) adds the account step.
            self.assertEqual(len(boxes), 4)
            self.assertEqual({box["x"] for box in boxes}, {boxes[0]["x"]})
            for upper, lower in pairwise(boxes):
                self.assertGreaterEqual(lower["y"], upper["y"] + upper["height"])
            scroll_width = self.page.evaluate("document.documentElement.scrollWidth")
            self.assertLessEqual(scroll_width, 320)

    # Spec #148 (ticket #150): four steps sit two by two on a wide screen, never three and one.
    def test_home_step_cards_two_by_two_on_a_wide_screen(self):
        self.open(1280, signed_in=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            boxes = [card.bounding_box() for card in self.page.locator(".step-cards > li").all()]
            self.assertEqual(len(boxes), 4)
            self.assertEqual(boxes[0]["y"], boxes[1]["y"])
            self.assertEqual(boxes[2]["y"], boxes[3]["y"])
            self.assertGreater(boxes[2]["y"], boxes[0]["y"])

    # phase9_ui_refresh_4a_home.md review 1: at 200% text the step cards still fit a phone
    def test_home_step_cards_fit_a_phone_at_double_text_size(self):
        self.open(320, 640, signed_in=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            self.page.add_style_tag(content="html { font-size: 225% !important; }")  # 2 x 112.5%
            for card in self.page.locator(".step-cards > li").all():
                box = card.bounding_box()
                self.assertLessEqual(box["x"] + box["width"], 320)

    # #127 acceptance 3: public and account pages at 200% text on a phone
    def test_public_and_account_pages_fit_a_phone_at_double_text_size(self):
        undecided = Client()
        undecided.force_login(User.objects.create_user(username="layout_undecided"))
        cookies = {
            "anonymous": None,
            "signed in": self.cookie["value"],
            "undecided": undecided.cookies[settings.SESSION_COOKIE_NAME].value,
        }
        pages = [
            *(("anonymous", path) for path in ("/", "/login", "/register")),
            *(
                (who, path)
                for who in ("anonymous", "signed in")
                for path in ("/privacy", "/family", "/add_to_home")
            ),
            *(("signed in", path) for path in ("/", "/account", "/account/delete")),
            ("undecided", "/consent"),
        ]
        for who, path in pages:
            with self.subTest(who=who, path=path):
                self.context = self.browser.new_context(viewport={"width": 320, "height": 640})
                self.addCleanup(self.context.close)
                if cookies[who]:
                    self.context.add_cookies([{**self.cookie, "value": cookies[who]}])
                self.context.tracing.start(screenshots=True, snapshots=True)
                self.page = self.context.new_page()
                with self.saving_artifacts():
                    self.page.goto(f"{self.live_server_url}{path}")
                    self.page.add_style_tag(content="html { font-size: 225% !important; }")
                    scroll_width = self.page.evaluate("document.documentElement.scrollWidth")
                    self.assertLessEqual(scroll_width, 320)
                    controls = self.page.locator(
                        "main :is(.btn, .form-control, .input-group-text):visible"
                    ).all()
                    boxes = [control.bounding_box() for control in controls]
                    # 1px: an input group's parts share their border on purpose.
                    for a, b in combinations(boxes, 2):
                        apart = (
                            a["x"] + a["width"] <= b["x"] + 1
                            or b["x"] + b["width"] <= a["x"] + 1
                            or a["y"] + a["height"] <= b["y"] + 1
                            or b["y"] + b["height"] <= a["y"] + 1
                        )
                        self.assertTrue(apart, f"controls overlap: {a} {b}")


class MaskingSwitchTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#333 (spec #326 D4, ADR 0028): masking on the new-audiogram page is a real switch."""

    ORANGE = "rgb(179, 89, 0)"
    KNOB_X = "el => el.getBoundingClientRect().x"
    KNOB_ANIMATIONS = """el => el.getAnimations().map(a => ({
        property: a.transitionProperty, duration: a.effect.getComputedTiming().duration }))"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.client.force_login(consented_user(username="masking_switch_e2e"))
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, width=390, reduced_motion="no-preference"):
        self.context = self.browser.new_context(
            viewport={"width": width, "height": 900}, reduced_motion=reduced_motion
        )
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)
        audiogram_step(self.page, self.live_server_url, 2)

    def switch(self):
        return self.main().get_by_role("switch", name="遮蔽", exact=True)

    def style(self, locator, prop):
        return locator.evaluate("(el, prop) => getComputedStyle(el)[prop]", prop)

    def assert_state(self, on):
        switch = self.switch()
        expect(switch).to_have_attribute("aria-checked", "true" if on else "false")
        expect(switch).to_have_text("遮蔽開" if on else "遮蔽關")
        track = switch.locator(".audiogram-mask-track")
        self.assertEqual(self.style(track, "backgroundColor") == self.ORANGE, on)
        frame = self.main().locator(".audiogram-chart")
        self.assertEqual(self.style(frame, "outlineStyle"), "dashed" if on else "none")
        if on:
            self.assertEqual(self.style(frame, "outlineColor"), self.ORANGE)

    # #326 acceptance 17: the mouse and the space bar change the switch, its 開／關 and the frame.
    def test_mouse_and_space_bar_switch_masking(self):
        self.open()
        with self.saving_artifacts():
            expect(self.switch()).to_have_accessible_name("遮蔽")
            self.assert_state(on=False)
            self.switch().click()
            self.assert_state(on=True)
            self.switch().focus()
            self.page.keyboard.press("Space")
            self.assert_state(on=False)
            self.page.keyboard.press("Space")
            self.assert_state(on=True)
            box = self.switch().bounding_box()
            self.assertGreaterEqual(min(box["width"], box["height"]), 44)

    # ADR 0028: hovering, pressing and keyboard focus only change colours; the switch keeps its
    # border and the keyboard sees a ring.
    def test_hover_press_and_focus_change_colour_only(self):
        # Reduced motion, so the buttons' colour transitions are read at their final value.
        self.open(reduced_motion="reduce")
        with self.saving_artifacts():
            switch = self.switch()
            border = "rgb(108, 117, 125)"
            self.assertEqual(self.style(switch, "backgroundColor"), "rgb(255, 255, 255)")
            box = switch.bounding_box()
            switch.hover()
            self.assertEqual(self.style(switch, "backgroundColor"), "rgb(238, 243, 250)")
            self.assertEqual(self.style(switch, "borderTopColor"), border)
            self.page.mouse.down()
            self.assertEqual(self.style(switch, "backgroundColor"), "rgb(214, 226, 242)")
            self.assertEqual(self.style(switch, "borderTopColor"), border)
            self.assertEqual(switch.bounding_box(), box)
            self.page.mouse.up()
            self.page.mouse.move(0, 0)
            self.page.keyboard.press("Shift+Tab")
            self.page.keyboard.press("Tab")
            expect(switch).to_be_focused()
            self.assertEqual(self.style(switch, "borderTopColor"), border)
            self.assertNotEqual(self.style(switch, "boxShadow"), "none")

    # #326 acceptance 17 and 23 (ADR 0028): the knob slides over 0.2 s; with reduced motion it
    # is already in place.
    def test_knob_slides_only_without_reduced_motion(self):
        for motion in ("no-preference", "reduce"):
            with self.subTest(motion=motion):
                self.open(reduced_motion=motion)
                knob = self.switch().locator(".audiogram-mask-knob")
                off = knob.evaluate(self.KNOB_X)
                self.switch().click()
                animations = knob.evaluate(self.KNOB_ANIMATIONS)
                if motion == "reduce":
                    self.assertEqual(animations, [])
                    self.assertGreater(knob.evaluate(self.KNOB_X), off)
                else:
                    self.assertEqual(animations, [{"property": "transform", "duration": 200}])
                    knob.evaluate("el => Promise.all(el.getAnimations().map(a => a.finished))")
                    self.assertGreater(knob.evaluate(self.KNOB_X), off)

    # #326 (C1's 200% rule, kept for D4): the switch fits a phone at double text size.
    def test_switch_fits_a_phone_at_double_text_size(self):
        self.open(width=320)
        with self.saving_artifacts():
            self.page.locator("html").evaluate(
                "html => html.style.setProperty('font-size', '225%', 'important')"
            )
            self.switch().click()
            widths = self.switch().evaluate("el => [el.scrollWidth, el.clientWidth]")
            self.assertLessEqual(widths[0], widths[1])
            for part in self.switch().locator("span:not(.audiogram-mask-knob)").all():
                box = part.bounding_box()
                self.assertGreaterEqual(box["x"], 0)
                self.assertLessEqual(box["x"] + box["width"], 320)
            # 遮蔽 is never broken over two lines, and 開 stays beside its track.
            lines = self.switch().evaluate(
                """el => {
                    const range = document.createRange();
                    range.selectNodeContents(el.firstChild);
                    return range.getClientRects().length;
                }"""
            )
            self.assertEqual(lines, 1)
            track = self.switch().locator(".audiogram-mask-track").bounding_box()
            state = self.switch().locator(".audiogram-mask-state").bounding_box()
            self.assertLess(state["y"], track["y"] + track["height"])
            self.assertLess(track["y"], state["y"] + state["height"])


class RecordsSwitchTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#270 (spec #268, ADR 0019): 我的紀錄's questionnaires or audiograms switch in a browser."""

    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        user = consented_user(username="records_switch_e2e")
        hhie_s = Questionnaire.objects.get(code="hhie-s")
        submission = Submission.objects.create(
            user=user, questionnaire=hhie_s, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=2)
            for question in hhie_s.questions.all()
        )
        audiogram = Audiogram.objects.create(user=user, tested_on=date(2026, 9, 28))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=40)
            for ear in ("right", "left")
            for f in (500, 1000, 2000, 4000)
        )
        self.client.force_login(user)
        self.context = self.browser.new_context(viewport={"width": 390, "height": 800})
        self.context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
                    "url": self.live_server_url,
                }
            ]
        )
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def switch(self):
        return self.main().get_by_role("navigation", name="紀錄種類")

    def assert_on(self, side):
        expect(self.main().get_by_role("heading", level=1)).to_have_text("我的紀錄")
        expect(self.switch().locator('a[aria-current="page"]')).to_have_text(side)

    def test_switch_to_audiograms_and_back(self):
        with self.saving_artifacts():
            self.page.goto(self.live_server_url)
            nav = self.page.get_by_role("navigation", name="主要導覽")
            nav.get_by_role("link", name="紀錄").click()
            self.assert_on("問卷")
            self.switch().get_by_role("link", name="聽力圖").click()
            expect(self.page).to_have_url(f"{self.live_server_url}/audiograms")
            self.assert_on("聽力圖")
            expect(self.main().get_by_role("link", name="新增聽力圖")).to_be_visible()
            self.switch().get_by_role("link", name="問卷").click()
            expect(self.page).to_have_url(f"{self.live_server_url}/my_hearing?view=questionnaires")
            self.assert_on("問卷")
            expect(self.main().locator("a.link-card:not(.action-card)")).to_contain_text("總分：20")
            # Each side is its own address: the back button returns to the audiograms.
            self.page.go_back()
            self.assert_on("聽力圖")

    def test_switch_fits_a_phone_at_double_text_size(self):
        for path in ("/my_hearing", "/audiograms"):
            with self.subTest(path=path):
                self.page.goto(f"{self.live_server_url}{path}")
                self.page.wait_for_load_state("load")
                # 2 x the site's 112.5% base, as in assert_fits_a_phone_at_double_text_size.
                self.page.locator("html").evaluate(
                    "html => html.style.setProperty('font-size', '225%', 'important')"
                )
                # The audiogram list's cards were already wider than a phone at 200% before the
                # switch (their 6rem thumbnail), so only 我的紀錄 is checked as a whole page.
                if path == "/my_hearing":
                    scroll_width = self.page.evaluate("document.documentElement.scrollWidth")
                    self.assertLessEqual(scroll_width, 390)
                widths = self.switch().evaluate("nav => [nav.scrollWidth, nav.clientWidth]")
                self.assertLessEqual(widths[0], widths[1])
                for link in self.switch().get_by_role("link").all():
                    box = link.bounding_box()
                    self.assertGreaterEqual(box["x"], 0)
                    self.assertLessEqual(box["x"] + box["width"], 390)


# Runs before the site's own scripts on every page: notes whether the page arrived with a view
# transition, which parts of the page it animates, where the pill starts (its group's first
# keyframe) and where the pill is on the new page, both [left, top] in the viewport.
REVEAL_WATCH = """
addEventListener("pagereveal", async (event) => {
    if (!event.viewTransition) {
        window.revealed = "none";
        return;
    }
    try {
        await event.viewTransition.ready;
    } catch {
        // switch-reveal.js skipped it: the page painted before its switch was parsed.
        window.revealed = "skipped";
        return;
    }
    window.revealed = "transition";
    const html = document.documentElement;
    const animations = document.getAnimations().filter((a) => a.effect.target === html);
    window.moving = [...new Set(animations.map((a) => a.effect.pseudoElement))].sort();
    // Without the new pill (a page painted before its switch was parsed) there is no group to
    // slide; window.moving then says so and the test fails at once rather than time out.
    const group = animations.find((a) => a.effect.pseudoElement.includes("-group("));
    if (group) {
        const start = new DOMMatrix(group.effect.getKeyframes()[0].transform);
        const end = document.querySelector("main [aria-current]").getBoundingClientRect();
        window.pill = [[start.e, start.f], [end.left, end.top]].map((at) => at.map(Math.round));
    }
    await event.viewTransition.finished;
    window.settled = true;
});
"""
PILL_PARTS = [f"::view-transition-{part}(switch-pill)" for part in ("group", "new", "old")]
# Chromium made into a browser without cross-document view transitions: it never fires pageswap
# or pagereveal, and it does not know @view-transition, so site.css cannot opt a page in.
NO_VIEW_TRANSITIONS = """
const listen = EventTarget.prototype.addEventListener;
EventTarget.prototype.addEventListener = function (type, ...rest) {
    if (type === "pageswap" || type === "pagereveal") return;
    return listen.call(this, type, ...rest);
};
const drop = (rules) => {
    for (let i = rules.cssRules.length - 1; i >= 0; i--) {
        const rule = rules.cssRules[i];
        if (rule.cssText.startsWith("@view-transition")) {
            rules.deleteRule(i);
            window.droppedRules = (window.droppedRules || 0) + 1;
        } else if (rule.cssRules) {
            drop(rule);
        }
    }
};
addEventListener("load", () => [...document.styleSheets].forEach(drop));
"""


class SlidingPillTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#334 (spec #326 D3, ADR 0028): the blue pill of the 問卷 or 聽力圖 and 右耳 or 左耳
    switches slides to the side pressed, by a cross-document view transition; nothing else on
    the page fades."""

    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        user = consented_user(username="sliding_pill_e2e")
        for tested_on in (date(2026, 6, 1), date(2026, 9, 28)):
            audiogram = Audiogram.objects.create(user=user, tested_on=tested_on)
            AudiogramPoint.objects.bulk_create(
                AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=40)
                for ear in ("right", "left")
                for f in (500, 1000, 2000, 4000)
            )
        self.client.force_login(user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, reduced_motion="no-preference", view_transitions=True):
        self.context = self.browser.new_context(
            viewport={"width": 390, "height": 844}, reduced_motion=reduced_motion
        )
        self.addCleanup(self.context.close)
        self.context.add_cookies([self.cookie])
        self.context.add_init_script(REVEAL_WATCH if view_transitions else NO_VIEW_TRANSITIONS)
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()

    def arrived(self, current):
        """Waits for the new page's current pill, then says how the page arrived."""
        expect(self.main().locator("[aria-current]")).to_have_text(current)
        self.page.wait_for_function("window.revealed")
        return self.page.evaluate("window.revealed")

    def assert_pill_slid(self):
        self.page.wait_for_function("window.settled")
        self.assertEqual(self.page.evaluate("window.moving"), PILL_PARTS)
        start, end = self.page.evaluate("window.pill")
        self.assertNotEqual(start, end)

    def assert_slid_unless_too_slow(self, current):
        """The pill slides; a machine too slow to parse the switch before the first paint (as CI
        can be) changes page without the transition instead, never fading the pill out."""
        arrived = self.arrived(current)
        self.assertIn(arrived, ("transition", "skipped"))
        if arrived == "transition":
            self.assert_pill_slid()

    # #334: on a slow phone the next page paints before its switch is parsed; it changes page
    # without the transition (switch-reveal.js) rather than fade the old pill out.
    def test_slow_page_changes_page_without_fading_the_pill(self):
        self.open()
        cdp = self.context.new_cdp_session(self.page)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 6})
        with self.saving_artifacts():
            for start, switch, side in (
                ("/my_hearing?view=questionnaires", "紀錄種類", "聽力圖"),
                ("/audiograms/compare", "選耳朵", "左耳"),
            ):
                with self.subTest(switch=switch):
                    self.page.goto(f"{self.live_server_url}{start}")
                    nav = self.main().get_by_role("navigation", name=switch)
                    nav.get_by_role("link", name=side).click()
                    self.assert_slid_unless_too_slow(side)

    def test_pill_slides_between_questionnaires_and_audiograms(self):
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing?view=questionnaires")
            records = self.main().get_by_role("navigation", name="紀錄種類")
            records.get_by_role("link", name="聽力圖").click()
            self.assert_slid_unless_too_slow("聽力圖")
            records.get_by_role("link", name="問卷").click()
            self.assert_slid_unless_too_slow("問卷")

    def test_pill_slides_between_ears(self):
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/audiograms/compare")
            ears = self.main().get_by_role("navigation", name="選耳朵")
            ears.get_by_role("link", name="左耳").click()
            self.assert_slid_unless_too_slow("左耳")
            ears.get_by_role("link", name="右耳").click()
            self.assert_slid_unless_too_slow("右耳")

    def test_reduced_motion_changes_page_without_sliding(self):
        self.open(reduced_motion="reduce")
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing?view=questionnaires")
            records = self.main().get_by_role("navigation", name="紀錄種類")
            records.get_by_role("link", name="聽力圖").click()
            self.assertEqual(self.arrived("聽力圖"), "none")
            self.page.goto(f"{self.live_server_url}/audiograms/compare")
            self.main().get_by_role("navigation", name="選耳朵").get_by_text("左耳").click()
            self.assertEqual(self.arrived("左耳"), "none")

    # Spec #326 acceptance 16 (D3): a browser without the transition just changes page.
    def test_browser_without_view_transitions_just_changes_page(self):
        self.open(view_transitions=False)
        with self.saving_artifacts():
            for start, switch, side, url in (
                ("/my_hearing?view=questionnaires", "紀錄種類", "聽力圖", r"/audiograms$"),
                ("/audiograms/compare", "選耳朵", "左耳", r"/audiograms/compare\?.*ear=left$"),
            ):
                self.page.goto(f"{self.live_server_url}{start}")
                # The page really has no @view-transition left, so nothing can opt it in.
                self.page.wait_for_function("window.droppedRules > 0")
                main = self.main()
                main.get_by_role("navigation", name=switch).get_by_role("link", name=side).click()
                expect(self.page).to_have_url(re.compile(url))
                expect(main.locator("[aria-current]")).to_have_text(side)
                self.page.wait_for_function("window.droppedRules > 0")

    def test_loading_bar_shows_while_the_next_side_takes_a_while(self):
        # ADR 0027: the old page still shows the moving bar and 載入中… until the new side
        # arrives. A page being left cannot be read, so it notes what it showed for the next one.
        self.open()
        held = []
        self.page.route(f"{self.live_server_url}/audiograms", lambda route: held.append(route))
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing?view=questionnaires")
            self.page.evaluate(
                """() => {
                    const html = document.documentElement;
                    const bar = document.querySelector(".page-loading-bar");
                    const status = document.getElementById("page-loading-status");
                    new MutationObserver(() => {
                        if (!html.classList.contains("page-loading")) return;
                        const shown = [getComputedStyle(bar).animationName, status.textContent];
                        sessionStorage.setItem("waiting", shown.join(" "));
                    }).observe(html, { attributes: true });
                }"""
            )
            records = self.main().get_by_role("navigation", name="紀錄種類")
            # Without no_wait_after the click would wait for the held page.
            records.get_by_role("link", name="聽力圖").click(no_wait_after=True)
            self.page.wait_for_timeout(1000)
            held[0].continue_()
            self.assert_slid_unless_too_slow("聽力圖")
            waiting = self.page.evaluate("sessionStorage.getItem('waiting')")
            self.assertEqual(waiting, "loading-slide 載入中…")

    def changes_page(self, action):
        """Does action, then says how the page it leads to arrived."""
        with self.page.expect_navigation():
            action()
        self.page.wait_for_function("window.revealed")
        return self.page.evaluate("window.revealed")

    def test_no_other_change_of_page_transitions(self):
        self.open()
        tabs = self.page.get_by_role("navigation", name="主要導覽")
        with self.saving_artifacts():
            # 紀錄 comes back to this same list (a redirect), the pill in the same place.
            for tab in ("紀錄", "首頁"):
                with self.subTest(tab=tab):
                    self.page.goto(f"{self.live_server_url}/audiograms")
                    link = tabs.get_by_role("link", name=tab)
                    self.assertEqual(self.changes_page(link.click), "none")
            with self.subTest("an audiogram's card"):
                self.page.goto(f"{self.live_server_url}/audiograms")
                card = self.main().locator("a.audiogram-card").first
                self.assertEqual(self.changes_page(card.click), "none")
            with self.subTest("比較 with another audiogram"):
                self.page.goto(f"{self.live_server_url}/audiograms/compare?ear=left")
                row = self.main().locator(".compare-pick").nth(0)
                row.locator("summary").click()
                button = row.get_by_role("button", name="比較", exact=True)
                self.assertEqual(self.changes_page(button.click), "none")
                expect(self.main().locator("[aria-current]")).to_have_text("左耳")
            with self.subTest("the back button after switching"):
                self.page.goto(f"{self.live_server_url}/my_hearing?view=questionnaires")
                records = self.main().get_by_role("navigation", name="紀錄種類")
                records.get_by_role("link", name="聽力圖").click()
                self.assert_slid_unless_too_slow("聽力圖")
                self.assertEqual(self.changes_page(self.page.go_back), "none")
                expect(self.main().locator("[aria-current]")).to_have_text("問卷")


class HearingAidGuideTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """Spec #218 (ticket #231): the guide's route, and its pages at 200% text on a phone."""

    fixtures = ("questions_fixture.json",)
    COUNTY = "花蓮縣"
    # The 1150717 roster's hearing assessment hospitals in 花蓮縣, as the snapshot lists them.
    HOSPITALS = (
        "佛教慈濟醫療財團法人花蓮慈濟醫院",
        "臺灣基督教門諾會醫療財團法人門諾醫院",
        "臺中市立老人復健綜合醫院（委託財團法人中國醫藥大學興建經營）",
    )
    CHAPTERS = (
        "before-you-go",
        "assessment",
        "form-9",
        "types-and-prices",
        "after-fitting",
        "form-25",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        # A returning user without hearing aids; 55 dB in both ears is a 45.0% ratio, just
        # reaching the assessment threshold.
        user = consented_user(username="guide_e2e")
        hhie_s = Questionnaire.objects.get(code="hhie-s")
        submission = Submission.objects.create(
            user=user, questionnaire=hhie_s, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=2)
            for question in hhie_s.questions.all()
        )
        audiogram = Audiogram.objects.create(user=user, tested_on=date(2026, 10, 1))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=55)
            for ear in ("right", "left")
            for f in (500, 1000, 2000, 4000)
        )
        self.client.force_login(user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, width, height=900):
        self.context = self.browser.new_context(viewport={"width": width, "height": height})
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    # #231: home card -> my guide (an audiogram reaching the threshold) -> the assessment
    # chapter with a county chosen -> the form 9 chapter. #261: reaching the threshold makes
    # the guide the 建議您下一步, so its button is the way in.
    def test_route_from_home_card_to_form_9(self):
        self.open(390)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            more = self.page.get_by_role("region", name="您還可以")
            expect(more.get_by_role("heading", level=3).first).to_have_text("了解助聽器選配與補助")
            more.get_by_role("link", name="看我的選配指引").click()

            expect(self.page).to_have_url(f"{self.live_server_url}/guide")
            expect(self.main().get_by_role("heading", level=1)).to_have_text("我的選配指引")
            # #260: the audiogram's date and numbers open the 選配 meter.
            fitting = self.main().get_by_role("region", name="要不要找聽力師評估")
            expect(fitting).to_contain_text("依您 2026/10/01 的聽力圖：")
            expect(fitting).to_contain_text("右耳四頻平均 55 dB HL")
            expect(fitting).to_contain_text("左耳四頻平均 55 dB HL")
            threshold = self.main().get_by_role("region", name="身障鑑定門檻")
            expect(threshold).to_contain_text(
                "雙耳障礙比率約 45.0%，達到身障鑑定門檻（45%）。實際以鑑定醫院為準。"
            )
            threshold.get_by_role("link", name="找鑑定醫院").click()

            expect(self.main().get_by_role("heading", level=1)).to_have_text("身障鑑定與鑑定醫院")
            self.main().get_by_label("選擇您的縣市").select_option(self.COUNTY)
            self.main().get_by_role("button", name="查詢").click()
            expect(self.page).to_have_url(
                re.compile(r"/guide/assessment\?county=.+#hospital-results$")
            )
            hospitals = self.main().get_by_role("list", name=self.COUNTY).get_by_role("listitem")
            expect(hospitals).to_have_text(list(self.HOSPITALS))
            # Guide chapters tidy-up: the search lands on its results, not the top of the page.
            expect(
                self.main().get_by_text(f"{self.COUNTY}：{len(self.HOSPITALS)} 家醫院")
            ).to_be_in_viewport()
            expect(hospitals.first).to_be_in_viewport()

            # #367: the chapter's end leads back too; this is the one at its top.
            self.main().get_by_role("link", name="回到我的選配指引").first.click()
            self.main().get_by_role("link", name="看九號表的流程").click()
            expect(self.page).to_have_url(f"{self.live_server_url}/guide/form-9")
            expect(self.main().get_by_role("heading", level=1)).to_have_text(
                "九號表：申請助聽器補助"
            )
            expect(self.main()).to_contain_text("沒核定就先買的不補助")

    # #292 (spec #291 e2e, acceptance 2, 4, 5, 27): the setUp user reaches the threshold but
    # has read nothing, so 您在這裡 is 去找聽力師之前. Reading it from the button, and 種類與價格
    # out of order from its title, marks both 已完成 and moves 您在這裡 on to the assessment.
    # The nine stops fit 320px at 200% text.
    def test_reading_chapters_moves_the_route_on(self):
        self.open(320, 640)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/guide")
            stops = self.main().locator(".route-stop")
            expect(stops).to_have_count(9)
            expect(stops.nth(4)).to_contain_text("等待核定公文")
            expect(stops.nth(8)).to_contain_text("等待補助發放")
            here = self.main().locator('[aria-current="step"]')
            expect(here).to_contain_text("去找聽力師之前")
            here.get_by_role("link", name="去之前要準備什麼").click()
            expect(self.main().get_by_role("heading", level=1)).to_have_text("去找聽力師之前")

            self.page.goto(f"{self.live_server_url}/guide")
            types = self.main().locator('[data-stop="types-and-prices"]')
            expect(types.locator(".route-mark")).to_have_count(0)
            types.get_by_role("link", name="助聽器的種類與價格").click()
            expect(self.main().get_by_role("heading", level=1)).to_have_text("助聽器的種類與價格")

            self.page.goto(f"{self.live_server_url}/guide")
            for slug in ("before-you-go", "types-and-prices"):
                stop = self.main().locator(f'[data-stop="{slug}"]')
                expect(stop.locator(".route-mark")).to_have_text(["已完成"])
            here = self.main().locator('[aria-current="step"]')
            expect(here).to_contain_text("身障鑑定與鑑定醫院")
            expect(here.get_by_role("link", name="找鑑定醫院")).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("/guide with chapters read")

    # #293 (spec #291 e2e, acceptance 6, 7, 18, 27; no JavaScript, story 40): answer the
    # certificate at the foot of its chapter, again on the route, then change it with 修改.
    # The chapter's question card and the route's open question fit 320px at 200% text.
    def test_answering_the_certificate_moves_the_route_on(self):
        user = User.objects.get(username="guide_e2e")
        GuideChapterView.objects.create(user=user, chapter="before-you-go")
        self.context = self.browser.new_context(
            java_script_enabled=False, viewport={"width": 320, "height": 640}
        )
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        question = "您有聽覺機能的身心障礙證明嗎？"
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/guide/assessment")
            card = self.main().get_by_role("region", name="看完了嗎？")
            expect(card.get_by_role("group", name=question)).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("/guide/assessment question card")
            card.get_by_role("button", name="還沒有，正在申請鑑定").click()
            expect(self.page).to_have_url(f"{self.live_server_url}/guide/assessment#stop-question")
            expect(self.main().get_by_role("region", name="看完了嗎？")).to_have_count(0)
            # #294: the card says what was kept, and its button goes back to the route.
            kept = self.main().get_by_role("region", name="已記下：正在申請鑑定")
            expect(kept).to_be_in_viewport()
            expect(kept.get_by_role("link", name="修改身障鑑定與鑑定醫院的回答")).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("/guide/assessment answered card")
            kept.get_by_role("link", name="回選配路線看下一站").click()

            expect(self.page).to_have_url(f"{self.live_server_url}/guide#contents-title")
            here = self.main().locator('[aria-current="step"]')
            expect(here).to_contain_text("身障鑑定與鑑定醫院")
            expect(here.locator(".route-answer")).to_have_text("正在申請鑑定")
            expect(here.get_by_role("group", name=question)).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("/guide open question")
            here.get_by_role("button", name="有", exact=True).click()

            expect(self.page).to_have_url(f"{self.live_server_url}/guide#stop-assessment")
            assessment = self.main().locator('[data-stop="assessment"]')
            expect(assessment.locator(".route-mark")).to_have_text(["已完成"])
            expect(assessment.locator(".route-answer")).to_have_text("有身障證明 修改")
            expect(self.main().locator('[aria-current="step"]')).to_contain_text("九號表")
            assessment.get_by_role("link", name="修改身障鑑定與鑑定醫院的回答").click()

            expect(self.page).to_have_url(
                f"{self.live_server_url}/guide?edit=assessment#stop-assessment"
            )
            assessment = self.main().locator('[data-stop="assessment"]')
            expect(assessment.get_by_role("group", name=question)).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("/guide editing the question")
            assessment.get_by_role("button", name="沒有，不申請身障補助").click()

            for slug in ("form-9", "notice", "form-25", "payout"):
                stop = self.main().locator(f'[data-stop="{slug}"]')
                expect(stop.locator(".route-mark")).to_have_text(["不適用"])
            here = self.main().locator('[aria-current="step"]')
            expect(here).to_contain_text("助聽器的種類與價格")

    # #294 (spec #291 e2e, acceptance 8, 9, 10, 27; no JavaScript, story 40): with a
    # certificate, answer 九號表 on the route, then 等待核定公文 one question at a time.
    def test_answering_form_9_and_the_notice_moves_the_route_on(self):
        user = User.objects.get(username="guide_e2e")
        GuideChapterView.objects.create(user=user, chapter="before-you-go")
        AidAndSubsidy.objects.create(user=user, certificate="yes")
        self.context = self.browser.new_context(
            java_script_enabled=False, viewport={"width": 320, "height": 640}
        )
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/guide")
            here = self.main().locator('[aria-current="step"]')
            expect(here).to_contain_text("九號表")
            expect(here.get_by_role("link", name="看九號表的流程")).to_be_visible()
            expect(here.get_by_role("group", name="九號表完成了嗎？")).to_be_visible()
            here.get_by_role("button", name="完成了").click()

            expect(self.page).to_have_url(f"{self.live_server_url}/guide#stop-form-9")
            form_9 = self.main().locator('[data-stop="form-9"]')
            expect(form_9.locator(".route-mark")).to_have_text(["已完成"])
            expect(form_9.locator(".route-answer")).to_have_text("九號表完成了 修改")
            here = self.main().locator('[aria-current="step"]')
            expect(here).to_contain_text("等待核定公文")
            here.get_by_role("button", name="收到了").click()

            expect(self.page).to_have_url(f"{self.live_server_url}/guide#stop-notice")
            here = self.main().locator('[aria-current="step"]')
            expect(here).to_contain_text("等待核定公文")
            expect(here.get_by_role("group", name="核定的是單耳還是雙耳？")).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("/guide the notice's ears")
            here.get_by_role("button", name="雙耳").click()

            here = self.main().locator('[aria-current="step"]')
            expect(here.get_by_role("group", name="補助的等級是？")).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("/guide the notice's level")
            here.get_by_role("button", name="中階型").click()

            notice = self.main().locator('[data-stop="notice"]')
            expect(notice.locator(".route-mark")).to_have_text(["已完成"])
            expect(notice.locator(".route-answer")).to_have_text("雙耳、中階型 修改")
            here = self.main().locator('[aria-current="step"]')
            expect(here).to_contain_text("助聽器的種類與價格")
            expect(here).to_contain_text("收到核定通知後 6 個月內要買。")

    # #295 (spec #291 e2e, acceptance 11, 12, 18, 27): the latest questionnaire answered
    # wearing hearing aids, so 您在這裡 is 配戴之後 and it asks the ear and the subsidy too; the
    # level appears only once 用身障補助 is chosen. Then 修改 and 還沒開始戴 take it back.
    def test_answering_the_fitting_date_moves_the_route_on(self):
        Submission.objects.filter(user__username="guide_e2e").update(wearing_hearing_aid=True)
        self.open(320, 640)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/guide/after-fitting")
            card = self.main().get_by_role("region", name="看完了嗎？")
            expect(card.get_by_label("這副助聽器哪一天開始戴？")).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("/guide/after-fitting question card")

            self.page.goto(f"{self.live_server_url}/guide")
            here = self.main().locator('[aria-current="step"]')
            expect(here).to_contain_text("配戴助聽器之後")
            expect(here.get_by_role("group", name="有沒有用身障補助買？")).to_be_visible()
            level = here.get_by_role("group", name="補助的等級是？")
            expect(level).to_be_hidden()
            here.get_by_label("這副助聽器哪一天開始戴？").fill("2026-05-01")
            here.get_by_role("radio", name="雙耳").check()
            here.get_by_role("radio", name="自費或其他補助").check()
            expect(level).to_be_hidden()
            here.get_by_role("radio", name="用身障補助").check()
            expect(level).to_be_visible()
            level.get_by_role("radio", name="中階型").check()
            self.assert_fits_a_phone_at_double_text_size("/guide the fitting question")
            here.get_by_role("button", name="儲存").click()

            expect(self.page).to_have_url(f"{self.live_server_url}/guide#stop-after-fitting")
            fitting = self.main().locator('[data-stop="after-fitting"]')
            expect(fitting.locator(".route-mark")).to_have_text(["已完成"])
            expect(fitting.locator(".route-answer")).to_have_text(
                "2026/05/01 開始戴、雙耳、用身障補助、中階型 修改"
            )
            expect(self.main().locator('[aria-current="step"]')).to_contain_text("二十五號表")
            fitting.get_by_role("link", name="修改配戴助聽器之後的回答").click()

            fitting = self.main().locator('[data-stop="after-fitting"]')
            expect(fitting.get_by_label("這副助聽器哪一天開始戴？")).to_have_value("2026-05-01")
            expect(fitting.get_by_role("group", name="補助的等級是？")).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("/guide editing the fitting")
            fitting.get_by_role("button", name="還沒開始戴").click()

            here = self.main().locator('[aria-current="step"]')
            expect(here).to_contain_text("配戴助聽器之後")
            expect(here.locator(".route-answer")).to_have_count(0)
            expect(here.get_by_label("這副助聽器哪一天開始戴？")).to_have_value("")

    def here(self):
        return self.main().locator('[aria-current="step"]')

    # #296 (spec #291 e2e, acceptance 1-2, 4, 6-9, 11, 14, 16, 18, 27): the whole route
    # from recording the audiogram to 等待補助發放, reading chapters, answering on the route and
    # at a chapter's foot, and 修改 once. 320px at 200% text where questions open.
    def test_walking_the_route_from_the_audiogram_to_the_payout(self):
        Audiogram.objects.filter(user__username="guide_e2e").delete()
        fitted_on = timezone.localdate() - timedelta(days=10)
        opens = add_months(fitted_on, 1)
        self.open(320, 640)
        with self.saving_artifacts():
            # 1 記錄聽力圖, in its four steps.
            self.page.goto(f"{self.live_server_url}/guide")
            expect(self.here()).to_contain_text("記錄聽力圖")
            self.here().get_by_role("link", name="記錄醫院的聽力圖").click()
            main = self.main()
            main.get_by_label("檢查日期").fill("2026-10-01")
            main.get_by_role("button", name="下一步：標右耳", exact=True).click()
            for ear, button in (("右耳", "右耳標完了，換左耳"), ("左耳", "左耳標完了，確認存檔")):
                if ear == "右耳":
                    main.get_by_text("用數值輸入（鍵盤或螢幕閱讀器）").click()
                for frequency in (500, 1000, 2000, 4000):
                    main.get_by_label(f"{ear}氣導 {frequency} Hz", exact=True).select_option("55")
                main.get_by_role("button", name=button, exact=True).click()
            main.get_by_role("button", name="存檔", exact=True).click()
            expect(self.page).to_have_url(re.compile(r"/audiograms/\d+$"))

            # 2 去找聽力師之前, read from its button.
            self.page.goto(f"{self.live_server_url}/guide")
            audiogram = self.main().locator('[data-stop="audiogram"]')
            expect(audiogram.locator(".route-mark")).to_have_text(["已完成"])
            expect(self.here()).to_contain_text("去找聽力師之前")
            self.here().get_by_role("link", name="去之前要準備什麼").click()
            expect(self.main().get_by_role("heading", level=1)).to_have_text("去找聽力師之前")

            # 3 身障鑑定, answered on the route.
            self.page.goto(f"{self.live_server_url}/guide")
            expect(self.here()).to_contain_text("身障鑑定與鑑定醫院")
            self.here().get_by_role("button", name="有", exact=True).click()

            # 4 九號表, answered at the foot of its chapter, then back to the route.
            expect(self.here()).to_contain_text("九號表")
            self.here().get_by_role("link", name="看九號表的流程").click()
            card = self.main().get_by_role("region", name="看完了嗎？")
            card.get_by_role("button", name="完成了").click()
            kept = self.main().get_by_role("region", name="已記下：九號表完成了")
            kept.get_by_role("link", name="回選配路線看下一站").click()

            # 5 等待核定公文, one question at a time.
            expect(self.here()).to_contain_text("等待核定公文")
            self.here().get_by_role("button", name="收到了").click()
            self.here().get_by_role("button", name="雙耳").click()
            self.here().get_by_role("button", name="中階型").click()

            # 6 種類與價格, read from its title.
            expect(self.here()).to_contain_text("助聽器的種類與價格")
            self.here().get_by_role("link", name="助聽器的種類與價格").click()
            expect(self.main().get_by_role("heading", level=1)).to_have_text("助聽器的種類與價格")

            # 7 配戴之後: the notice's 雙耳 leaves only the date.
            self.page.goto(f"{self.live_server_url}/guide")
            expect(self.here()).to_contain_text("配戴助聽器之後")
            self.here().get_by_label("這副助聽器哪一天開始戴？").fill(fitted_on.isoformat())
            self.here().get_by_role("button", name="儲存").click()

            # 8 二十五號表: at least a month on, dated. Answered 完成了 at the foot of its
            # chapter, then on the route 修改 to 還沒 and 完成了 again.
            fitting = self.main().locator('[data-stop="after-fitting"]')
            expect(fitting.locator(".route-gap")).to_have_text("至少 1 個月")
            expect(self.here()).to_contain_text("二十五號表")
            expect(self.here()).to_contain_text(f"{opens:%Y/%m/%d} 起可以做")
            expect(self.here().get_by_role("group", name="二十五號表完成了嗎？")).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("/guide form 25's question")
            # Back to the usual size: at 200% on 320px the link is one character wide and taller
            # than the screen, its middle behind the back-to-top button since the 1rem tab
            # labels (#357) raised the button.
            self.double_text(False)
            self.here().get_by_role("link", name="看二十五號表要帶什麼").click()
            card = self.main().get_by_role("region", name="看完了嗎？")
            expect(card.get_by_role("group", name="二十五號表完成了嗎？")).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("/guide/form-25 question card")
            card.get_by_role("button", name="完成了").click()
            kept = self.main().get_by_role("region", name="已記下：二十五號表完成了")
            kept.get_by_role("link", name="回選配路線看下一站").click()

            expect(self.here()).to_contain_text("等待補助發放")
            form_25 = self.main().locator('[data-stop="form-25"]')
            expect(form_25.locator(".route-answer")).to_have_text("二十五號表完成了 修改")
            form_25.get_by_role("link", name="修改二十五號表：使用效益驗證的回答").click()
            form_25 = self.main().locator('[data-stop="form-25"]')
            form_25.get_by_role("button", name="還沒").click()
            expect(self.here()).to_contain_text("二十五號表")
            expect(self.here().locator(".route-answer")).to_have_text("二十五號表還沒完成")
            self.here().get_by_role("button", name="完成了").click()

            # 9 等待補助發放: here, asking nothing and never 已完成; the eight before it done.
            expect(self.here()).to_contain_text("等待補助發放")
            expect(self.here().locator(".route-mark")).to_have_text(["您在這裡"])
            expect(self.here().locator("form")).to_have_count(0)
            done = self.main().locator(".route-stop").filter(has_text="已完成")
            expect(done).to_have_count(8)
            self.assert_fits_a_phone_at_double_text_size("/guide at the payout")

    # #296 (spec #291 e2e, acceptance 7, 15): not applying for the 身障補助 and paying for the
    # pair, form 25 and the payout are 不適用, and once fitted no stop is 您在這裡.
    def test_not_applying_for_the_subsidy_shows_its_stops_not_applicable(self):
        user = User.objects.get(username="guide_e2e")
        Submission.objects.filter(user=user).update(wearing_hearing_aid=True)
        AidAndSubsidy.objects.create(user=user, certificate="no_subsidy")
        self.open(320, 640)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/guide")
            for slug in ("form-9", "notice", "form-25", "payout"):
                stop = self.main().locator(f'[data-stop="{slug}"]')
                expect(stop.locator(".route-mark")).to_have_text(["不適用"])
            expect(self.here()).to_contain_text("配戴助聽器之後")
            fitted_on = timezone.localdate() - timedelta(days=10)
            self.here().get_by_label("這副助聽器哪一天開始戴？").fill(fitted_on.isoformat())
            self.here().get_by_role("radio", name="雙耳").check()
            self.here().get_by_role("radio", name="自費或其他補助").check()
            self.here().get_by_role("button", name="儲存").click()

            expect(self.page).to_have_url(f"{self.live_server_url}/guide#stop-after-fitting")
            fitting = self.main().locator('[data-stop="after-fitting"]')
            expect(fitting.locator(".route-mark")).to_have_text(["已完成"])
            for slug in ("form-25", "payout"):
                stop = self.main().locator(f'[data-stop="{slug}"]')
                expect(stop.locator(".route-mark")).to_have_text(["不適用"])
            expect(self.here()).to_have_count(0)
            expect(self.main().locator(".route-gap")).to_have_count(0)
            self.assert_fits_a_phone_at_double_text_size("/guide without the subsidy")

    # #231 (#218 acceptance 共通): my guide and the six chapters, 320px wide at 200% text,
    # with the worked steps open and a county's hospitals listed.
    def test_pages_fit_a_phone_at_double_text_size(self):
        self.open(320, 640)
        paths = [
            "/guide",
            *(f"/guide/{slug}" for slug in self.CHAPTERS),
            f"/guide/assessment?county={self.COUNTY}",
        ]
        with self.saving_artifacts():
            for path in paths:
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    for summary in self.main().locator("details > summary").all():
                        summary.click()
                    expect(self.main().locator("details:not([open])")).to_have_count(0)
                    self.assert_fits_a_phone_at_double_text_size(path)
            with self.subTest(path="/guide signed out"):
                self.context.clear_cookies()
                self.page.goto(f"{self.live_server_url}/guide")
                expect(self.main().get_by_role("link", name="登入", exact=True)).to_be_visible()
                self.assert_fits_a_phone_at_double_text_size("/guide signed out")

    # #258: the route's longest stops at 200% text: 您在這裡 with 資料不足 and its button, then
    # 估算未達門檻 with its link (the setUp audiogram reaches the threshold, so it is changed).
    # #260: then a no-response point, so the ratio's meter says 至少約 and hatches on to 100%.
    def test_route_marks_fit_a_phone_at_double_text_size(self):
        self.open(320, 640)
        points = AudiogramPoint.objects.filter(audiogram__user__username="guide_e2e")
        with self.saving_artifacts():
            with self.subTest(state="too little data"):
                # Both ears within 25 and one unknown: the audiogram cannot tell.
                points.update(db=20)
                points.filter(ear="left", frequency=4000).delete()
                self.page.goto(f"{self.live_server_url}/guide")
                expect(self.main().get_by_role("link", name="修改這張聽力圖")).to_have_count(2)
                self.assert_fits_a_phone_at_double_text_size("/guide too little data")
            with self.subTest(state="not reached"):
                points.filter(ear="right").update(db=30)
                AudiogramPoint.objects.create(
                    audiogram=points.first().audiogram, ear="left", conduction="air",
                    frequency=4000, db=20,
                )  # fmt: skip
                self.page.goto(f"{self.live_server_url}/guide")
                expect(self.main().get_by_role("link", name="看沒有身障證明時")).to_have_count(2)
                self.assert_fits_a_phone_at_double_text_size("/guide not reached")
            with self.subTest(state="no response"):
                # 40 and 80 dB HL, the left unheard at 4000 Hz: at least about 35.0%.
                points.filter(ear="right").update(db=40)
                points.filter(ear="left").update(db=80)
                points.filter(ear="left", frequency=4000).update(db=DB_MAX["air"], no_response=True)
                self.page.goto(f"{self.live_server_url}/guide")
                threshold = self.main().get_by_role("region", name="身障鑑定門檻")
                expect(threshold).to_contain_text("雙耳障礙比率（估算） 至少約 35.0%")
                expect(threshold.locator(".meter-beyond")).to_have_count(1)
                self.assert_fits_a_phone_at_double_text_size("/guide no response")

    # The meters' lines (25 dB HL, 45%) without a white edge: a bar stopping on the line meets it
    # with no gap, and the line sticks out 0.3rem above and below its track onto the page, where
    # it shows even over the dark blue bar. The last line in a meter runs into its label's.
    # #342: the bars are measured where they end, so with reduced motion, which draws them full
    # at once (GuideMeterFillTest watches them grow).
    def test_meter_lines_stick_out_of_their_tracks_without_a_gap(self):
        self.open(390)
        self.page.emulate_media(reduced_motion="reduce")
        points = AudiogramPoint.objects.filter(audiogram__user__username="guide_e2e")
        measure = """el => {
            const box = selector => {
                const r = el.querySelector(selector).getBoundingClientRect();
                return {left: r.left, right: r.right, top: r.top, bottom: r.bottom};
            };
            return {
                track: box(".meter-track"),
                bar: box(".meter-bar"),
                line: box(".meter-line"),
                shadow: getComputedStyle(el.querySelector(".meter-line")).boxShadow,
                rem: parseFloat(getComputedStyle(document.documentElement).fontSize),
            };
        }"""  # fmt: skip
        # Right and left ear in dB HL, whether the left is unheard at 4000 Hz, the ratio's text,
        # and where the right, left and ratio bars end against their lines.
        states = {
            "25 dB": (25, 25, False, "約 0.0%", ("under", "under", "none")),
            "60 dB": (60, 60, False, "約 52.5%", ("past", "past", "past")),
            "no response": (40, 80, True, "至少約 35.0%", ("past", "past", "short")),
        }
        with self.saving_artifacts():
            for state, (right, left, no_response, ratio, ends) in states.items():
                with self.subTest(state=state):
                    points.filter(ear="right").update(db=right)
                    points.filter(ear="left").update(db=left)
                    if no_response:
                        points.filter(ear="left", frequency=4000).update(
                            db=DB_MAX["air"], no_response=True
                        )
                    self.page.goto(f"{self.live_server_url}/guide")
                    threshold = self.main().get_by_role("region", name="身障鑑定門檻")
                    expect(threshold).to_contain_text(f"雙耳障礙比率（估算） {ratio}")
                    expect(threshold.locator(".meter-beyond")).to_have_count(int(no_response))
                    drawings = self.main().locator(".meter-drawing")
                    expect(drawings).to_have_count(3)
                    for drawing, end in zip(drawings.all(), ends, strict=True):
                        found = drawing.evaluate(measure)
                        bar, line, track = found["bar"], found["line"], found["track"]
                        self.assertEqual(found["shadow"], "none")
                        for out in (track["top"] - line["top"], line["bottom"] - track["bottom"]):
                            self.assertAlmostEqual(out, 0.3 * found["rem"], delta=0.5)
                        if end == "under":
                            self.assertGreater(bar["right"], bar["left"])
                            self.assertGreaterEqual(bar["right"], line["left"])
                            self.assertLessEqual(bar["right"], line["right"])
                        elif end == "none":
                            self.assertEqual(bar["right"], bar["left"])
                        elif end == "past":
                            self.assertGreater(bar["right"], line["right"])
                        else:
                            self.assertLess(bar["right"], line["left"])
                    for meter in self.main().locator(".meter").all():
                        line = meter.locator(".meter-line").last.bounding_box()
                        scale = meter.locator(".meter-scale").bounding_box()
                        self.assertGreaterEqual(line["y"] + line["height"], scale["y"])
                        self.assertAlmostEqual(line["x"], scale["x"], delta=0.5)

    # #261 acceptance 8: the home page's 建議您下一步 with its longest 「因為」 sentences, 390px
    # wide at 200% text. The setUp user has read nothing, so it is 去找聽力師之前; read, the
    # assessment (spec #291's reasons); within 25 and missing a frequency, nothing can tell.
    def test_home_next_step_fits_a_phone_at_double_text_size(self):
        self.open(390, 640)
        points = AudiogramPoint.objects.filter(audiogram__user__username="guide_e2e")
        with self.saving_artifacts():
            for state, button in (
                ("before you go", "看我的選配指引"),
                ("assessment", "看我的選配指引"),
                ("too little data", "修改這張聽力圖"),
            ):
                with self.subTest(state=state):
                    if state == "assessment":
                        user = User.objects.get(username="guide_e2e")
                        GuideChapterView.objects.create(user=user, chapter="before-you-go")
                    if state == "too little data":
                        points.update(db=20)
                        points.filter(ear="left", frequency=4000).delete()
                    self.page.goto(f"{self.live_server_url}/")
                    more = self.page.get_by_role("region", name="您還可以")
                    expect(more.get_by_role("link", name=button)).to_be_visible()
                    self.page.wait_for_load_state("load")
                    self.page.locator("html").evaluate(
                        "html => html.style.setProperty('font-size', '225%', 'important')"
                    )
                    scroll_width = self.page.evaluate("document.documentElement.scrollWidth")
                    self.assertLessEqual(scroll_width, 390, state)

    # #261 self-review: the action cards (#256) shared by the home page's 您還可以 and the result
    # pages, 320px wide at 200% text, keep room for four characters a line in their titles.
    def test_action_card_titles_keep_four_characters_a_line_at_double_text_size(self):
        self.open(320, 640)
        submission = Submission.objects.get(user__username="guide_e2e")
        with self.saving_artifacts():
            for path in ("/", f"/submission/{submission.pk}"):
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    titles = self.main().locator(".action-card .link-card-title")
                    expect(titles.first).to_be_visible()
                    self.assert_fits_a_phone_at_double_text_size(path)
                    narrow = titles.evaluate_all(
                        "titles => titles.filter(t => t.getBoundingClientRect().width"
                        " < 4 * parseFloat(getComputedStyle(t).fontSize)).map(t => t.textContent)"
                    )
                    self.assertEqual(narrow, [], path)

    # #261 self-review: the 建議您下一步 box at the same size; a reason ending in 「（45%）。」
    # once ran past its white box. This user is at 去找聽力師之前 (spec #291's reason). #304:
    # the result page shows the same box (spec #297 acceptance 12).
    def test_next_step_reason_keeps_four_characters_a_line_at_double_text_size(self):
        self.open(320, 640)
        submission = Submission.objects.get(user__username="guide_e2e")
        with self.saving_artifacts():
            for path in ("/", f"/submission/{submission.pk}"):
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    reason = self.main().locator(".next-step-because")
                    expect(reason).to_contain_text("先看看第一次去找聽力師要準備什麼。")
                    self.assert_fits_a_phone_at_double_text_size(f"{path} next step")
                    room = reason.evaluate(
                        "p => ({chars: p.clientWidth / parseFloat(getComputedStyle(p).fontSize),"
                        " overflow: p.scrollWidth - p.clientWidth})"
                    )
                    self.assertGreaterEqual(room["chars"], 4, path)
                    self.assertLessEqual(room["overflow"], 0, path)

    # #258: the 目前這一站's ring breathes only when motion is welcome. This user has read
    # nothing, so the stop is 去找聽力師之前 (spec #291). #341 (ADR 0029): it plays once the
    # stop is in view, so the route is scrolled to first.
    def test_current_stop_ring_moves_only_without_reduced_motion(self):
        self.open(390)
        with self.saving_artifacts():
            for motion, animation in (("reduce", "none"), ("no-preference", "route-ring")):
                with self.subTest(motion=motion):
                    self.page.emulate_media(reduced_motion=motion)
                    self.page.goto(f"{self.live_server_url}/guide")
                    here = self.main().locator('[aria-current="step"]')
                    expect(here).to_have_count(1)
                    expect(here).to_contain_text("去找聽力師之前")
                    here.evaluate("el => el.scrollIntoView({block: 'center', behavior: 'instant'})")
                    number = here.locator(".route-number")
                    expect(number).to_have_css("animation-name", animation)
                    expect(number).to_have_css("animation-play-state", "running")

    # #260: 看我的路線 jumps down to the route's heading and gives it the focus, so a screen
    # reader goes on from there; smoothly, or straight there with reduced motion. #321 (#318
    # acceptance 5): in the 段落框's title bar, the focus ring still shows: a solid line at least
    # 2px wide, 3:1 or more on the bar, drawn inside the bar so nothing around it hides it.
    OUTLINE_AND_BAR = """(el) => {
        const style = getComputedStyle(el);
        return [style.outlineStyle, parseFloat(style.outlineWidth), style.outlineColor,
            parseFloat(style.outlineOffset), style.backgroundColor];
    }"""

    def test_jump_to_the_route_lands_on_its_heading_with_focus(self):
        self.open(390, 844)
        with self.saving_artifacts():
            for motion in ("no-preference", "reduce"):
                with self.subTest(motion=motion):
                    self.page.emulate_media(reduced_motion=motion)
                    self.page.goto(f"{self.live_server_url}/guide")
                    heading = self.main().get_by_role("heading", name="選配與補助，一步一步看")
                    expect(heading).not_to_be_in_viewport()
                    self.main().get_by_role("link", name="看我的路線").click()
                    expect(heading).to_be_focused()
                    expect(heading).to_be_in_viewport()
                    style, width, colour, offset, bar = heading.evaluate(self.OUTLINE_AND_BAR)
                    self.assertEqual(bar, WhiteCardRuleTest.SECTION_TITLE)
                    self.assertEqual(style, "solid")
                    self.assertGreaterEqual(width, 2)
                    self.assertLessEqual(offset, -width)
                    self.assertGreaterEqual(StyleInBrowserTest.lowest_contrast(colour, bar), 3)

    # #218 acceptance 章節頁 5: my guide's links into form 9 land on their sections.
    def test_form_9_anchors_jump_to_their_sections(self):
        self.open(390, 640)
        with self.saving_artifacts():
            for anchor, heading in (
                ("reapply", "再次申請（換新機）"),
                ("without-certificate", "沒有身障證明時"),
            ):
                with self.subTest(anchor=anchor):
                    self.page.goto(f"{self.live_server_url}/guide/form-9#{anchor}")
                    expect(self.main().get_by_role("heading", name=heading)).to_be_in_viewport()

    def test_form_9_anchor_lands_when_fonts_arrive_after_the_jump(self):
        """On a slow phone the fonts arrive after the jump and rewrap the lines above."""
        self.open(390, 640)
        held = []
        self.context.route(re.compile(r"\.woff2?$"), lambda route: held.append(route))
        with self.saving_artifacts():
            self.page.goto(
                f"{self.live_server_url}/guide/form-9#reapply", wait_until="domcontentloaded"
            )
            self.page.wait_for_function("window.scrollY > 0")
            for route in held:
                route.continue_()
            self.page.wait_for_function("document.fonts.status === 'loaded'")
            # The heading is on screen for a moment as the scroll passes it; wait until it stops.
            self.page.wait_for_function(
                "() => { const still = scrollY === window.lastY; window.lastY = scrollY; "
                "return still; }",
                polling=200,
            )
            # At the top, where the jump puts it, not just somewhere on screen.
            heading = self.main().get_by_role("heading", name="再次申請（換新機）")
            self.assertLess(abs(heading.bounding_box()["y"]), 10)
            # Jumps within the page, once loaded, still scroll smoothly.
            expect(self.page.locator("html")).to_have_css("scroll-behavior", "smooth")

    def test_reduced_motion_keeps_jumps_instant_after_loading(self):
        self.open(390, 640)
        with self.saving_artifacts():
            self.page.emulate_media(reduced_motion="reduce")
            self.page.goto(f"{self.live_server_url}/guide/form-9#reapply")
            html = self.page.locator("html")
            expect(html).to_have_class(re.compile(r"\bsmooth-scroll\b"))
            expect(html).to_have_css("scroll-behavior", "auto")


class RouteCheckmarkTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#336 (spec #326 E5, acceptance 21 and 23): answering the 您在這裡 stop on the route so that
    it is 已完成 turns its circle green with a white tick drawn once; a refresh shows the number."""

    GREEN = "rgb(20, 87, 60)"  # --color-normal
    TICK_ANIMATIONS = (
        "p => p.getAnimations().map(a => [a.animationName, a.effect.getTiming().duration])"
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        # 您在這裡 is 身障鑑定與鑑定醫院: 55 dB in both ears reaches the threshold, and
        # 去找聽力師之前 has been read.
        self.user = consented_user(username="route_tick_e2e")
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 1))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=55)
            for ear in ("right", "left")
            for f in (500, 1000, 2000, 4000)
        )
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        self.client.force_login(self.user)
        cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }
        self.context = self.browser.new_context(viewport={"width": 390, "height": 844})
        self.context.add_cookies([cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def test_the_tick_draws_once_or_is_simply_there_with_reduced_motion(self):
        with self.saving_artifacts():
            for motion, animations in (
                ("no-preference", [["gauge-draw", 450]]),
                ("reduce", []),
            ):
                with self.subTest(motion=motion):
                    AidAndSubsidy.objects.filter(user=self.user).delete()
                    self.page.emulate_media(reduced_motion=motion)
                    self.page.goto(f"{self.live_server_url}/guide")
                    here = self.main().locator('[aria-current="step"]')
                    expect(here).to_contain_text("身障鑑定與鑑定醫院")
                    here.get_by_role("button", name="有", exact=True).click()

                    expect(self.page).to_have_url(f"{self.live_server_url}/guide#stop-assessment")
                    number = self.main().locator('[data-stop="assessment"] .route-number')
                    expect(number).to_have_css("background-color", self.GREEN)
                    tick = number.locator("svg path")
                    expect(tick).to_be_visible()
                    self.assertEqual(tick.evaluate(self.TICK_ANIMATIONS), animations)
                    if motion == "reduce":
                        expect(tick).to_have_css("stroke-dashoffset", "0px")
                    # Only the stop just done: the new 您在這裡 keeps its blue number.
                    here = self.main().locator('[aria-current="step"]')
                    expect(here).to_contain_text("九號表")
                    expect(here.locator(".route-number svg")).to_have_count(0)
                    self.assertEqual(self.main().locator(".route-number svg").count(), 1)

                    self.page.reload()
                    expect(number.locator("svg")).to_have_count(0)
                    expect(number).to_have_text("3")
                    expect(number).to_have_css("background-color", WhiteCardRuleTest.BLUE_SOFT)


class LearnPageTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#269 (spec #268): the 了解 page, signed out, at 200% text and without JavaScript."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def open(self, width, height=900, javascript=True):
        self.context = self.browser.new_context(
            viewport={"width": width, "height": height}, java_script_enabled=javascript
        )
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    # Acceptance: 390px at 200% text has no sideways scroll; checked at 320px, the narrower
    # phone the other 200% tests use.
    def test_fits_a_phone_at_double_text_size(self):
        self.open(320, 640)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            self.page.get_by_role("navigation", name="主要導覽").get_by_role(
                "link", name="了解"
            ).click()
            expect(self.main().get_by_role("heading", level=1)).to_have_text("了解")
            self.assert_fits_a_phone_at_double_text_size("/learn")

    def test_cards_change_page_without_javascript(self):
        cards = (
            ("了解助聽器選配與補助", "/guide", "我的選配指引"),
            ("給家人看：怎麼跟聽損的家人溝通", "/family", "給家人的溝通與陪伴"),
        )
        self.open(390, javascript=False)
        with self.saving_artifacts():
            for name, path, heading in cards:
                with self.subTest(card=name):
                    self.page.goto(f"{self.live_server_url}/learn")
                    self.main().get_by_role("link", name=name).click()
                    expect(self.page).to_have_url(f"{self.live_server_url}{path}")
                    expect(self.main().get_by_role("heading", level=1)).to_have_text(heading)


class LoadingIndicatorTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """ADR 0027 (A3 and C1 on the loading comparison page) in a real browser, with the site's
    script and styles (timings and exceptions: page-loading.test.js)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def open(self, reduced_motion="no-preference"):
        self.context = self.browser.new_context(
            viewport={"width": 390, "height": 844}, reduced_motion=reduced_motion
        )
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def stay_on_this_page(self):
        # Listeners on window run after page-loading.js's on document: the wait starts, but the
        # browser never leaves, so this page can still be read (a page being left cannot).
        self.page.evaluate(
            """() => {
                addEventListener("click", (event) => {
                    if (event.target.closest("a")) event.preventDefault();
                });
                addEventListener("submit", (event) => event.preventDefault());
            }"""
        )

    def wait_for_learn(self):
        self.page.goto(f"{self.live_server_url}/")
        self.stay_on_this_page()
        nav = self.page.get_by_role("navigation", name="主要導覽")
        nav.get_by_role("link", name="了解").click()
        expect(self.page.locator("html")).to_have_class(re.compile(r"\bpage-loading\b"))
        expect(self.page.get_by_role("status").filter(has_text="載入中…")).to_be_visible()

    def send_login(self):
        self.page.goto(f"{self.live_server_url}/login")
        self.stay_on_this_page()
        self.main().get_by_label("使用者名稱").fill("someone")
        self.main().get_by_label("密碼", exact=True).fill("secret")
        self.main().get_by_role("button", name="登入").click()
        button = self.main().get_by_role("button", name="送出中…")
        expect(button).to_be_disabled()
        return button.locator(".spinner")

    def test_bar_and_spinner_move_while_waiting(self):
        self.open()
        with self.saving_artifacts():
            self.wait_for_learn()
            bar = self.page.locator(".page-loading-bar")
            expect(bar).to_have_css("animation-name", "loading-slide")
            expect(bar).to_have_css("animation-iteration-count", "8")
            spinner = self.send_login()
            expect(spinner).to_be_visible()
            expect(spinner).to_have_css("animation-name", "loading-appear, loading-spin")

    def test_reduced_motion_keeps_the_bar_still_and_drops_the_spinner(self):
        self.open(reduced_motion="reduce")
        with self.saving_artifacts():
            self.wait_for_learn()
            bar = self.page.locator(".page-loading-bar")
            expect(bar).to_be_visible()
            expect(bar).to_have_css("animation-name", "none")
            expect(self.send_login()).to_be_hidden()


class PwaNavTest(SavesFailureArtifacts, StaticLiveServerTestCase):
    """Spec phase10_pwa_back_refresh.md acceptance 1-4, 12 and 13 (gestures are in Vitest)."""

    # Pretends to be the iPhone home-screen app; Chromium cannot emulate display-mode.
    STANDALONE = "Object.defineProperty(Navigator.prototype, 'standalone', { get: () => true });"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.client.force_login(consented_user(username="pwa_nav_e2e"))
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, standalone=True, width=412, height=900):
        self.context = self.browser.new_context(viewport={"width": width, "height": height})
        self.context.add_cookies([self.cookie])
        if standalone:
            self.context.add_init_script(self.STANDALONE)
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def back(self):
        return self.page.get_by_role("button", name="上一頁")

    # 1
    def test_browser_tab_shows_no_back_button(self):
        self.open(standalone=False)
        with self.saving_artifacts():
            # goto waits for the load event, and pwa-nav.js, a module script, has run before it.
            self.page.goto(f"{self.live_server_url}/questionnaire_list")
            expect(self.page.locator("#pwa-back")).to_be_hidden()

    # 2, 3, 4
    def test_back_button_returns_to_the_previous_page(self):
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            expect(self.page.locator("#pwa-back")).to_have_count(0)
            self.page.get_by_role("navigation", name="主要導覽").get_by_role(
                "link", name="篩檢"
            ).click()
            expect(self.back()).to_be_visible()
            box = self.back().bounding_box()
            self.assertGreaterEqual(box["width"], 44)
            self.assertGreaterEqual(box["height"], 44)
            self.back().click()
            expect(self.page).to_have_url(f"{self.live_server_url}/")

    # 12, 13
    def test_back_button_fits_a_phone_at_double_text_size(self):
        self.open(width=320, height=640)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing")
            self.page.add_style_tag(content="html { font-size: 225% !important; }")  # 2 x 112.5%
            expect(self.back()).to_be_visible()
            back = self.back().bounding_box()
            self.assertGreaterEqual(back["x"], 0)
            self.assertLessEqual(back["x"] + back["width"], 320)
            clipped = self.back().evaluate("b => b.scrollWidth > b.clientWidth")
            self.assertFalse(clipped)
            logout = self.page.get_by_role("button", name="登出").bounding_box()
            brand = self.page.locator(".site-brand").bounding_box()
            back_bottom, logout_bottom = back["y"] + back["height"], logout["y"] + logout["height"]
            same_line = logout["y"] < back_bottom and back["y"] < logout_bottom
            if same_line:
                self.assertGreaterEqual(brand["x"], back["x"] + back["width"])
                self.assertLessEqual(brand["x"] + brand["width"], logout["x"])

    def sign_in_as(self, username):
        self.client.force_login(consented_user(username=username))
        self.cookie["value"] = self.client.cookies[settings.SESSION_COOKIE_NAME].value

    def header_boxes(self, username):
        self.page.goto(f"{self.live_server_url}/my_hearing")
        self.page.evaluate("document.fonts.ready")
        return (
            self.page.locator(".site-brand").bounding_box(),
            self.page.get_by_role("button", name="登出").bounding_box(),
            self.page.get_by_role("link", name=f"目前登入：{username}，帳號設定").bounding_box(),
        )

    @staticmethod
    def on_same_line(a, b):
        return a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"]

    LONG_NAME = "family_shared_phone_account_for_grandma_and_grandpa_lin"

    def test_logout_shares_the_first_header_line_on_phones(self):
        """Logout stays beside the brand however long the name is; the name gets its own line."""
        self.sign_in_as(self.LONG_NAME)
        for width, standalone in ((360, True), (390, True), (390, False)):
            with self.subTest(width=width, standalone=standalone):
                self.open(standalone=standalone, width=width)
                with self.saving_artifacts():
                    brand, logout, account = self.header_boxes(self.LONG_NAME)
                    if standalone:
                        expect(self.back()).to_be_visible()
                    self.assertTrue(self.on_same_line(brand, logout))
                    self.assertLessEqual(logout["x"] + logout["width"], width)
                    self.assertGreaterEqual(logout["width"], 44)
                    self.assertGreaterEqual(logout["height"], 44)
                    self.assertGreaterEqual(account["y"], logout["y"] + logout["height"])
                    # Screen readers and Tab still reach the name before logout.
                    name_first = self.page.evaluate(
                        "document.querySelector('.site-account').compareDocumentPosition("
                        "document.getElementById('logout-form')) & Node.DOCUMENT_POSITION_FOLLOWING"
                    )
                    self.assertTrue(name_first)

    def test_header_is_one_line_on_wide_screens(self):
        """Just past the 48em breakpoint, a long name wraps in its own space beside logout."""
        self.sign_in_as(self.LONG_NAME)
        self.open(standalone=False, width=800)
        with self.saving_artifacts():
            brand, logout, account = self.header_boxes(self.LONG_NAME)
            self.assertTrue(self.on_same_line(brand, logout))
            self.assertTrue(self.on_same_line(account, logout))
            self.assertLessEqual(account["x"] + account["width"], logout["x"])


class BottomTabsTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#271 (spec #268): the four signed-in tabs, at 200% text and without JavaScript."""

    TABS = ("首頁", "篩檢", "紀錄", "了解")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.user = consented_user(username="bottom_tabs_e2e")
        self.client.force_login(self.user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, width, height=900, javascript=True, signed_in=True):
        self.context = self.browser.new_context(
            viewport={"width": width, "height": height}, java_script_enabled=javascript
        )
        if signed_in:
            self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def nav(self):
        return self.page.get_by_role("navigation", name="主要導覽")

    def click_through(self, nav, links):
        for name, path in links:
            with self.subTest(link=name):
                nav.get_by_role("link", name=name, exact=True).click()
                expect(self.page).to_have_url(f"{self.live_server_url}{path}")

    def add_audiogram(self):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 1))
        # Right ear 中重度, left ear 資料不足: the longest level label.
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear="right", conduction="air", frequency=f, db=60)
            for f in (500, 1000, 2000, 4000)
        )

    # Acceptance: no sideways scroll at 200% text on 我的紀錄 and 了解, checked at 320px, the
    # narrower phone assert_fits_a_phone_at_double_text_size uses.
    def test_records_and_learn_fit_a_phone_at_double_text_size(self):
        self.add_audiogram()
        self.open(320, 640)
        with self.saving_artifacts():
            # With only an audiogram, /my_hearing opens the audiogram list (#270).
            for path in ("/my_hearing?view=questionnaires", "/audiograms", "/learn"):
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    self.assert_fits_a_phone_at_double_text_size(path)

    # The audiogram card (owner's pick A): at normal text the date sits beside the thumbnail as
    # before; at 200% text it drops under the thumbnail, and the date and levels stay inside the
    # card on both phones.
    def test_audiogram_card_moves_its_thumbnail_up_at_double_text_size(self):
        self.add_audiogram()
        box = (
            "e => { const r = e.getBoundingClientRect(); "
            "return [r.left, r.right, r.top, r.bottom]; }"
        )
        for width in (320, 390):
            self.open(width, 640)
            with self.saving_artifacts():
                self.page.goto(f"{self.live_server_url}/audiograms")
                self.page.wait_for_load_state("load")
                card = self.main().locator(".link-card")
                thumbnail = card.locator(".audiogram-thumbnail")
                date_text = card.locator(".link-card-body strong")
                with self.subTest(width=width, text="normal"):
                    self.assertLessEqual(thumbnail.evaluate(box)[1], date_text.evaluate(box)[0])
                # 2 x the site's 112.5% base, as in assert_fits_a_phone_at_double_text_size.
                self.page.locator("html").evaluate(
                    "html => html.style.setProperty('font-size', '225%', 'important')"
                )
                with self.subTest(width=width, text="200%"):
                    self.assertLessEqual(
                        self.page.evaluate("document.documentElement.scrollWidth"), width
                    )
                    self.assertLessEqual(thumbnail.evaluate(box)[3], date_text.evaluate(box)[2])
                    left, right, _, _ = card.evaluate(box)
                    for part in (date_text, *card.locator(".level-badge").all()):
                        part_left, part_right, _, _ = part.evaluate(box)
                        self.assertGreaterEqual(part_left, left, part.inner_text())
                        self.assertLessEqual(part_right, right, part.inner_text())

    # Acceptance: at 390px and 200% text each tab's words take one line and stay on the screen.
    # Not 320px: there a tab is about 62px wide and two characters at 200% need about 63px.
    def test_tabs_stay_on_one_line_at_double_text_size(self):
        self.open(390)
        with self.saving_artifacts():
            for path in ("/my_hearing", "/audiograms", "/learn"):
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    self.page.wait_for_load_state("load")
                    # 2 x the site's 112.5% base, as in assert_fits_a_phone_at_double_text_size.
                    self.page.locator("html").evaluate(
                        "html => html.style.setProperty('font-size', '225%', 'important')"
                    )
                    # A range has one client rect per line its words take.
                    labels = (
                        self.nav()
                        .locator("a span")
                        .evaluate_all(
                            """spans => spans.map(span => {
                            const range = document.createRange();
                            range.selectNodeContents(span);
                            const box = span.getBoundingClientRect();
                            return [span.textContent, range.getClientRects().length,
                                    box.left >= 0 && box.right <= innerWidth];
                        })"""
                        )
                    )
                    self.assertEqual(labels, [[tab, 1, True] for tab in self.TABS])

    def test_tabs_change_page_without_javascript(self):
        tabs = (
            ("篩檢", "/questionnaire_list", None),
            ("紀錄", "/my_hearing", "我的紀錄"),
            ("了解", "/learn", "了解"),
            ("首頁", "/", None),
        )
        self.open(390, javascript=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/learn")
            for name, path, heading in tabs:
                with self.subTest(tab=name):
                    self.nav().get_by_role("link", name=name, exact=True).click()
                    expect(self.page).to_have_url(f"{self.live_server_url}{path}")
                    if heading:
                        expect(self.main().get_by_role("heading", level=1)).to_have_text(heading)

    # Spec #268 acceptance 20: the records switch and the signed-out tabs are plain links too.
    def test_records_switch_changes_page_without_javascript(self):
        self.open(390, javascript=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing")
            switch = self.page.get_by_role("navigation", name="紀錄種類")
            self.click_through(
                switch, (("聽力圖", "/audiograms"), ("問卷", "/my_hearing?view=questionnaires"))
            )

    def test_signed_out_tabs_change_page_without_javascript(self):
        self.open(390, javascript=False, signed_in=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            self.click_through(
                self.nav(),
                (("了解", "/learn"), ("登入", "/login"), ("註冊", "/register"), ("首頁", "/")),
            )


class MoreYouCanDoTest(SavesFailureArtifacts, StaticLiveServerTestCase):
    """Ticket #160 acceptance 2 and 3: the home page's "您還可以" in and out of the app."""

    fixtures = ("questions_fixture.json",)
    # #228 put the hearing-aid guide card before the one the app hides. #261: this user has no
    # audiogram, so recording one is the 建議您下一步, not a card, and the cards are grouped.
    CARDS = (
        "印聽力報告給醫師看",
        "分享報告給家人",
        "了解助聽器選配與補助",
        "加到手機主畫面",
    )
    GROUPS = ("給別人看", "了解", "方便使用")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        user = consented_user(username="more_e2e")
        hhie_s = Questionnaire.objects.get(code="hhie-s")
        submission = Submission.objects.create(
            user=user, questionnaire=hhie_s, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=2)
            for question in hhie_s.questions.all()
        )
        self.client.force_login(user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open_home(self, standalone, javascript=True):
        self.context = self.browser.new_context(
            viewport={"width": 412, "height": 900}, java_script_enabled=javascript
        )
        self.context.add_cookies([self.cookie])
        if standalone:
            self.context.add_init_script(PwaNavTest.STANDALONE)
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)
        self.page.goto(f"{self.live_server_url}/")
        return self.page.get_by_role("region", name="您還可以").get_by_role("link")

    def group_titles(self):
        return self.page.get_by_role("region", name="您還可以").locator(".more-group-title")

    def test_home_screen_app_hides_add_to_home(self):
        cards = self.open_home(standalone=True)
        with self.saving_artifacts():
            # Role locators skip hidden elements, so the last card is gone. #261: its whole
            # group goes, the 方便使用 title too.
            expect(cards.locator(".link-card-title")).to_have_text(list(self.CARDS[:-1]))
            expect(self.page.locator("main [data-hide-in-app]")).to_be_hidden()
            expect(self.group_titles().filter(visible=True)).to_have_text(list(self.GROUPS[:-1]))

    # #195: the account page's "加到手機主畫面" row hides in the app the same way.
    def test_home_screen_app_hides_add_to_home_on_account_settings(self):
        self.open_home(standalone=True)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/account")
            rows = self.page.get_by_role("region", name="家人與手機").get_by_role("link")
            expect(rows.locator(".link-card-title")).to_have_text(
                ["分享報告給家人", "給家人看：怎麼跟聽損的家人溝通"]
            )

    def test_browser_tab_and_no_javascript_show_every_card(self):
        for standalone, javascript in ((False, True), (True, False)):
            with self.subTest(standalone=standalone, javascript=javascript):
                cards = self.open_home(standalone=standalone, javascript=javascript)
                with self.saving_artifacts():
                    expect(cards.locator(".link-card-title")).to_have_text(list(self.CARDS))
                    expect(self.group_titles().filter(visible=True)).to_have_text(list(self.GROUPS))


class StyleInBrowserTest(SavesFailureArtifacts, StaticLiveServerTestCase):
    """#123: style rules measured as the browser computes them, whatever produced the CSS."""

    fixtures = ("questions_fixture.json",)
    TEXT = "rgb(73, 80, 87)"
    PRIMARY = "rgb(31, 78, 140)"
    ERROR = "rgb(143, 42, 18)"  # #149: the severe level colour, darkened to 7:1
    # #137 (2a): a warm page and footer, white surfaces, warm borders on large blocks.
    WARM_PAGE = "rgb(250, 247, 242)"
    WARM_FOOTER = "rgb(243, 237, 227)"
    WARM_BORDER = "rgb(239, 230, 216)"
    WHITE = "rgb(255, 255, 255)"
    # #138-#140 (2a): the brand gradient, its lighter end a blue teal since the brand refresh
    # (ADR 0007 keeps it blue); #139: the primary button's states (choice C in #136, with a soft
    # glow so it never looks like the keyboard ring).
    GRADIENT = "linear-gradient(rgb(31, 78, 140), rgb(29, 111, 153))"
    PRESSED_GRADIENT = "linear-gradient(rgb(23, 59, 106), rgb(24, 95, 131))"
    GLOW = "rgba(29, 111, 153, 0.45) 0px 0px 16.2px 3.6px"
    FOCUS_RING = "rgba(31, 78, 140, 0.5) 0px 0px 0px 4.5px"
    # (level, scores, background, text colour)
    BANNERS = (
        ("normal", (0,) * 10, "rgb(227, 244, 236)", "rgb(20, 87, 60)"),
        ("mild_to_moderate", (2,) * 6 + (0,) * 4, "rgb(255, 244, 214)", "rgb(112, 72, 0)"),
        ("severe", (4,) * 10, "rgb(254, 236, 231)", ERROR),
        ("unknown", (2,) * 10, "rgb(241, 243, 245)", TEXT),
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.user = consented_user(username="style_e2e")
        self.hhie_s = Questionnaire.objects.get(code="hhie-s")
        self.client.force_login(self.user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, signed_in=True, width=1024, javascript=True, motion=False, touch=False):
        # Reduced motion turns off colour transitions, so a style is read at its final value; the
        # header wave tests turn motion back on. Touch is a phone without a mouse.
        self.context = self.browser.new_context(
            viewport={"width": width, "height": 900},
            java_script_enabled=javascript,
            reduced_motion="no-preference" if motion else "reduce",
            has_touch=touch,
            is_mobile=touch,
        )
        if signed_in:
            self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def style(self, locator, prop):
        return locator.evaluate("(el, prop) => getComputedStyle(el)[prop]", prop)

    def submission(self, questionnaire, scores, wearing=False):
        record = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=question, score=score)
            for question, score in zip(questionnaire.questions.all(), scores, strict=True)
        )
        return record

    LOAD_FONT_WEIGHTS = """async () => {
        const loads = [400, 500, 600, 700].map(
            (weight) => document.fonts.load(`${weight} 18px "Noto Sans TC"`, "聽力"),
        );
        // A missing weight would load the nearest one instead, so each face's weight is checked.
        const faces = await Promise.all(loads);
        return faces.map((list) => list.map((face) => face.weight));
    }"""

    def test_body_font_comes_from_our_own_host(self):
        # #181, ADR 0014: Noto Sans TC in all four weights, and no request leaves for Google
        # Fonts or cdnjs (the privacy notice lists neither).
        own_host = urlparse(self.live_server_url).netloc
        for signed_in, path in ((False, "/"), (False, "/register"), (True, "/my_hearing")):
            with self.subTest(path=path):
                self.open(signed_in=signed_in)
                requests = []
                self.page.on("request", lambda request, seen=requests: seen.append(request))
                self.page.goto(f"{self.live_server_url}{path}")
                loaded = self.page.evaluate(self.LOAD_FONT_WEIGHTS)
                for weight, faces in zip(("400", "500", "600", "700"), loaded, strict=True):
                    self.assertTrue(faces)
                    self.assertEqual(set(faces), {weight})
                self.assertTrue(
                    self.style(self.page.locator("body"), "fontFamily").startswith('"Noto Sans TC"')
                )
                hosts = {urlparse(r.url).netloc for r in requests if r.url.startswith("http")}
                self.assertEqual(hosts, {own_host})
                font_files = [r for r in requests if r.url.endswith(".woff2")]
                self.assertTrue(font_files)
                for request in font_files:
                    self.assertEqual(request.response().status, 200)

    def test_tailwind_theme_preserves_original_design_values(self):
        # Independent values from pre-migration styles.css (#124); inspect built CSS in a browser.
        self.open(signed_in=False)
        self.page.goto(f"{self.live_server_url}/privacy")
        expected = {
            "--color-primary": "#1f4e8c",
            "--color-primary-hover": "#173b6a",
            "--color-primary-active": "#122f55",
            "--color-body": "#495057",
            "--color-heading": "#212529",
            "--color-footer": "#343a40",
            # #149: the three level colours darkened to 7:1; their backgrounds unchanged.
            "--color-normal": "#14573c",
            "--color-normal-bg": "#e3f4ec",
            "--color-mild": "#704800",
            "--color-mild-bg": "#fff4d6",
            "--color-severe": "#8f2a12",
            "--color-severe-bg": "#feece7",
            "--color-surface": "#f1f3f5",
            "--color-brand-soft": "#eef3fa",
            "--color-brand-selected": "#e8eef7",
            "--color-pull": "#e7eef8",
            "--color-border": "#ced4da",
            "--color-border-subtle": "#dee2e6",
            "--color-border-strong": "#adb5bd",
            "--color-input-border": "#6c757d",
            "--container-content": "40rem",
            "--container-form": "30rem",
            "--root-font-size": "112.5%",
            "--spacing-touch": "2.75rem",
            "--radius-button": "0.5rem",
            "--radius-badge": "1rem",
            "--radius-tab": "1.5rem",
            "--shadow-input-focus": "0 0 0 0.25rem rgba(31, 78, 140, 0.25)",
            "--color-focus-ring": "rgba(31, 78, 140, 0.5)",
            # 2a shared shell (#137): replaced the card and band radii and the card shadow.
            "--color-page": "#faf7f2",
            "--color-footer-bg": "#f3ede3",
            "--color-border-warm": "#efe6d8",
            "--shadow-warm": "0 0.25rem 0.75rem rgba(120, 90, 50, 0.08)",
            "--radius-large": "1.5rem",
            "--radius-medium": "0.75rem",
            "--radius-pill": "999px",
            "--color-gradient-start": "#1f4e8c",
            "--color-gradient-end": "#1d6f99",
        }
        # The CSS minifier rewrites .5rem and rgba() to shorter equivalent values. Let the
        # browser resolve both independent literals and tokens through the same CSS property.
        pairs = self.page.evaluate(
            """expected => Object.entries(expected).map(([name, value]) => {
                const property = name.startsWith('--color-') ? 'color'
                    : name.startsWith('--shadow-') ? 'boxShadow'
                    : name.startsWith('--radius-') ? 'borderTopLeftRadius'
                    : name === '--root-font-size' ? 'fontSize' : 'maxWidth';
                const el = document.createElement('div');
                document.body.append(el);
                el.style[property] = value;
                const literal = getComputedStyle(el)[property];
                el.style[property] = `var(${name})`;
                const token = getComputedStyle(el)[property];
                el.remove();
                return [name, literal, token];
            })""",
            expected,
        )
        for name, literal, token in pairs:
            with self.subTest(token=name):
                self.assertEqual(token, literal)
        self.assertEqual(self.style(self.page.locator("html"), "fontSize"), "18px")
        self.assertEqual(self.style(self.page.locator("main"), "maxWidth"), "720px")

    def test_heading_classes_and_muted_text_look_as_before(self):
        # #124: The pre-migration .h3 at 1024px is calc(1.3rem + .6vw) on an 18px root, line
        # height 1.2 and a .5rem bottom margin; its .text-muted (now .text-body) was the body text
        # colour. Since the heading refresh a page title (h1.h3) is bold and dark with a blue bar.
        self.open(javascript=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire_list")
            title = self.page.locator("h1.h3")
            self.assertEqual(
                self.styles(title, "fontSize", "lineHeight", "marginBottom"),
                {"fontSize": "29.544px", "lineHeight": "35.4528px", "marginBottom": "9px"},
            )
            self.assertEqual(
                self.styles(title, "fontWeight", "color", "borderLeftColor", "paddingLeft"),
                {
                    "fontWeight": "700",
                    "color": "rgb(33, 37, 41)",
                    "borderLeftColor": self.PRIMARY,
                    "paddingLeft": "13.5px",
                },
            )
            self.page.goto(f"{self.live_server_url}/privacy")
            self.assertEqual(self.style(self.page.locator("p.text-body"), "color"), self.TEXT)
            # A section title on the page has the bar; one inside a card does not.
            self.assertEqual(
                self.style(self.page.locator("h2.h4", has_text="誰在蒐集"), "borderLeftWidth"),
                "5px",  # 0.3rem, drawn in whole pixels
            )
            # #302: the highlights are a flat block now; the family guide's urgent topic is still
            # in its blue box.
            self.page.goto(f"{self.live_server_url}/family")
            self.assertEqual(
                self.style(
                    self.page.locator(".card h2.h4", has_text="什麼時候要馬上就醫"),
                    "borderLeftWidth",
                ),
                "0px",
            )

    def styles(self, locator, *props):
        return {prop: self.style(locator, prop) for prop in props}

    def size(self, locator):
        box = locator.bounding_box()
        return box["width"], box["height"]

    def audiogram(self, tested_on):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=tested_on)
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=40)
            for ear in ("right", "left")
            for f in (500, 1000, 2000, 4000)
        )
        return audiogram

    def test_buttons_keep_their_colours_size_and_focus_ring(self):
        # #125: The pre-migration values with the site's overrides, on the 18px root; since #139
        # every button is a pill, and the primary button's gradient covers its border.
        large = {"padding": "9px 18px", "fontSize": "22.5px", "borderTopLeftRadius": "999px"}
        regular = {"padding": "6.75px 13.5px", "fontSize": "18px", "borderTopLeftRadius": "999px"}
        clear = "rgba(0, 0, 0, 0)"
        white = "rgb(255, 255, 255)"
        cases = (
            # (path, signed in, button role, name, expected styles, focus ring colour)
            (
                "/login",
                False,
                "button",
                "登入",
                {
                    **large,
                    "backgroundColor": self.PRIMARY,
                    "color": white,
                    "borderTopColor": clear,
                },
                "rgba(31, 78, 140, 0.5)",
            ),
            (
                "/login",
                False,
                "link",
                "註冊新帳號",
                {
                    **large,
                    "backgroundColor": clear,
                    "color": self.PRIMARY,
                    "borderTopColor": self.PRIMARY,
                },
                "rgba(31, 78, 140, 0.5)",
            ),
            (
                "/account",
                True,
                "button",
                "登出",
                # A blue outline on the white header since the brand refresh.
                {
                    **regular,
                    "backgroundColor": clear,
                    "color": self.PRIMARY,
                    "borderTopColor": self.PRIMARY,
                },
                "rgba(31, 78, 140, 0.5)",
            ),
            (
                "/account/delete",
                True,
                "button",
                "刪除帳號",
                {
                    **large,
                    "backgroundColor": "rgb(220, 53, 69)",
                    "color": white,
                    "borderTopColor": "rgb(220, 53, 69)",
                },
                "rgba(225, 83, 97, 0.5)",
            ),
            (
                "/audiograms/new",
                True,
                "button",
                "清除剛標的點",
                {
                    **large,
                    "backgroundColor": clear,
                    "color": "rgb(108, 117, 125)",
                    "borderTopColor": "rgb(108, 117, 125)",
                    "opacity": "0.65",
                    "pointerEvents": "none",
                },
                None,
            ),
        )
        with self.saving_artifacts():
            for path, signed_in, role, name, expected, ring in cases:
                with self.subTest(button=name):
                    self.open(signed_in=signed_in)
                    if path == "/audiograms/new":
                        audiogram_step(self.page, self.live_server_url, 2)
                    else:
                        self.page.goto(f"{self.live_server_url}{path}")
                    area = self.page if name == "登出" else self.page.get_by_role("main")
                    button = area.get_by_role(role, name=name, exact=True)
                    self.assertEqual(self.styles(button, *expected), expected)
                    width, height = self.size(button)
                    self.assertGreaterEqual(min(width, height), 44)
                    if ring:
                        button.focus()
                        self.assertTrue(button.evaluate("el => el.matches(':focus-visible')"))
                        self.assertEqual(
                            self.style(button, "boxShadow"), f"{ring} 0px 0px 0px 4.5px"
                        )
            # Pages tidy-up: a link inside a sentence reads as plain text, yet its tap area is
            # still 44px tall and its line no taller than the paragraph's other lines.
            with self.subTest(link="下載我的資料"):
                self.open(signed_in=True)
                self.page.goto(f"{self.live_server_url}/account/delete")
                link = self.page.get_by_role("main").get_by_role(
                    "link", name="下載我的資料", exact=True
                )
                self.assertEqual(
                    self.styles(link, "color", "textDecorationLine", "backgroundColor"),
                    {
                        "color": self.PRIMARY,
                        "textDecorationLine": "underline",
                        "backgroundColor": clear,
                    },
                )
                self.assertGreaterEqual(self.size(link)[1], 44)
                # A stretched line would make the paragraph no whole number of lines tall.
                lines = link.locator("..").evaluate(
                    "p => p.getBoundingClientRect().height"
                    " / parseFloat(getComputedStyle(p).lineHeight)"
                )
                self.assertAlmostEqual(lines, round(lines), delta=0.05)

    def test_button_hover_and_press_colours(self):
        # The outline variant whose hover and press colours the site set itself; the primary
        # button's states are in test_primary_button_states_follow_choice_c (#139).
        cases = (("link", "註冊新帳號", self.PRIMARY, "rgb(23, 59, 106)"),)
        self.open(signed_in=False)
        with self.saving_artifacts():
            for role, name, hover, pressed in cases:
                with self.subTest(button=name):
                    self.page.goto(f"{self.live_server_url}/login")
                    button = self.page.get_by_role("main").get_by_role(role, name=name)
                    button.hover()
                    self.assertEqual(self.style(button, "backgroundColor"), hover)
                    self.assertEqual(self.style(button, "color"), "rgb(255, 255, 255)")
                    self.page.mouse.down()
                    self.assertEqual(self.style(button, "backgroundColor"), pressed)
                    self.assertEqual(self.style(button, "borderTopColor"), pressed)
                    self.page.mouse.up()

    def test_form_fields_keep_their_size_and_focus_ring(self):
        # #125: form fields keep their pre-migration size (owner's decision, 2026-10-21):
        # regular fields are 42.5px tall, above WCAG AA's 24px, and checkboxes sit in a
        # clickable 27px-tall label. Buttons are the ones held to 44 x 44.
        # The login and register pages chose thicker, taller fields (2026-10-23), so the regular
        # field is measured on the delete-account page.
        primary_ring = "rgba(31, 78, 140, 0.25) 0px 0px 0px 4.5px"
        field_focus_ring = "rgba(13, 110, 253, 0.25) 0px 0px 0px 4.5px"
        # #272: every field edge is --color-input-border (4.7:1 on white); the old
        # rgb(222, 226, 230) was 1.3:1, under WCAG 1.4.11's 3:1. Sizes stay as they were.
        border = "rgb(108, 117, 125)"
        self.audiogram(date(2026, 9, 28))
        with self.saving_artifacts():
            self.open()
            self.page.goto(f"{self.live_server_url}/account/delete")
            password = self.page.get_by_label("請輸入密碼確認")
            self.assertEqual(self.size(password)[1], 42.5)
            self.assertEqual(
                self.styles(
                    password,
                    "padding",
                    "borderTopWidth",
                    "borderTopColor",
                    "borderTopLeftRadius",
                    "color",
                ),
                {
                    "padding": "6.75px 13.5px",
                    "borderTopWidth": "1px",
                    "borderTopColor": border,
                    "borderTopLeftRadius": "13.5px",  # 0.75rem since #137
                    "color": self.TEXT,
                },
            )
            self.assertEqual(
                self.style(self.page.locator("label.form-label").first, "marginBottom"), "9px"
            )
            password.focus()
            self.assertEqual(self.style(password, "borderTopColor"), self.PRIMARY)
            self.assertEqual(self.style(password, "boxShadow"), primary_ring)

            # Login and register: 3.25rem tall, a 2px dark edge, room on the left for the icon.
            self.open(signed_in=False)
            self.page.goto(f"{self.live_server_url}/login")
            username = self.page.get_by_label("使用者名稱")
            self.assertEqual(self.size(username)[1], 58.5)
            self.assertEqual(
                self.styles(
                    username,
                    "padding",
                    "borderTopWidth",
                    "borderTopColor",
                    "borderTopLeftRadius",
                    "fontSize",
                    "color",
                ),
                {
                    "padding": "6.75px 13.5px 6.75px 54px",
                    "borderTopWidth": "2px",
                    "borderTopColor": border,
                    "borderTopLeftRadius": "13.5px",
                    "fontSize": "22.5px",
                    "color": self.TEXT,
                },
            )
            username.focus()
            self.assertEqual(self.style(username, "borderTopColor"), self.PRIMARY)
            self.assertEqual(self.style(username, "boxShadow"), primary_ring)

            self.page.goto(f"{self.live_server_url}/register")
            group = self.page.locator(".input-group")
            year, field, unit = group.locator("> *").all()
            self.assertEqual(self.style(group, "display"), "flex")
            self.assertEqual(
                self.styles(
                    year,
                    "backgroundColor",
                    "borderTopColor",
                    "padding",
                    "borderTopLeftRadius",
                    "borderTopRightRadius",
                ),
                {
                    "backgroundColor": "rgb(248, 249, 250)",
                    "borderTopColor": border,
                    "padding": "6.75px 13.5px",
                    "borderTopLeftRadius": "13.5px",
                    "borderTopRightRadius": "0px",
                },
            )
            # The 2px edges overlap by 2px, so the joins are no thicker than the outside.
            self.assertEqual(
                self.styles(field, "borderTopLeftRadius", "borderTopRightRadius", "marginLeft"),
                {"borderTopLeftRadius": "0px", "borderTopRightRadius": "0px", "marginLeft": "-2px"},
            )
            self.assertEqual(
                self.styles(unit, "borderTopLeftRadius", "borderTopRightRadius", "marginLeft"),
                {
                    "borderTopLeftRadius": "0px",
                    "borderTopRightRadius": "13.5px",
                    "marginLeft": "-2px",
                },
            )
            self.assertEqual({self.size(part)[1] for part in (year, field, unit)}, {58.5})

            self.open()
            audiogram_step(self.page, self.live_server_url, 2)
            self.page.get_by_text("用數值輸入").click()
            select = self.page.get_by_label("右耳氣導 500 Hz", exact=True)
            self.assertEqual(self.size(select)[1], 42.5)
            self.assertEqual(
                self.styles(select, "borderTopWidth", "borderTopColor"),
                {
                    "borderTopWidth": "1px",
                    "borderTopColor": border,
                },
            )
            self.assertEqual(self.style(select, "padding"), "6.75px 40.5px 6.75px 13.5px")
            self.assertIn("svg", self.style(select, "backgroundImage"))
            select.focus()
            self.assertEqual(self.style(select, "borderTopColor"), "rgb(134, 183, 254)")
            self.assertEqual(self.style(select, "boxShadow"), field_focus_ring)
            mask = self.page.get_by_label("右耳氣導 500 Hz 遮蔽")
            self.assertEqual(self.size(mask), (18, 18))
            self.assertEqual(self.style(mask, "opacity"), "0.5")
            self.assertEqual(self.style(mask, "borderTopColor"), border)
            self.assertEqual(
                self.styles(mask.locator(".."), "minHeight", "paddingLeft"),
                {"minHeight": "27px", "paddingLeft": "27px"},
            )
            select.select_option("20")
            mask.focus()
            self.assertEqual(self.style(mask, "borderTopColor"), "rgb(134, 183, 254)")
            self.assertEqual(self.style(mask, "boxShadow"), field_focus_ring)
            mask.check()
            self.assertEqual(self.style(mask, "backgroundColor"), "rgb(13, 110, 253)")
            # #199: the date is step 1.
            self.page.get_by_role("button", name="上一步").click()
            date_field = self.page.get_by_label("檢查日期")
            self.assertEqual(
                self.styles(
                    date_field,
                    "padding",
                    "fontSize",
                    "borderTopLeftRadius",
                    "borderTopWidth",
                    "borderTopColor",
                ),
                {
                    "padding": "9px 18px",
                    "fontSize": "22.5px",
                    "borderTopLeftRadius": "13.5px",
                    "borderTopWidth": "1px",
                    "borderTopColor": border,
                },
            )
            self.assertGreaterEqual(self.size(date_field)[1], 44)

            # #272: the guide's county picker, the one large select.
            self.page.goto(f"{self.live_server_url}/guide/assessment")
            self.assertEqual(
                self.styles(self.page.locator("#county"), "borderTopWidth", "borderTopColor"),
                {"borderTopWidth": "1px", "borderTopColor": border},
            )

            # #202: the compare page picks with radio cards in 舊 and 新 rows, not selects; each
            # row is a full touch target.
            self.audiogram(date(2026, 10, 5))
            self.page.goto(f"{self.live_server_url}/audiograms/compare")
            for row in self.page.locator(".compare-pick > summary").all():
                self.assertGreaterEqual(self.size(row)[1], 44)

    def test_cards_tables_alerts_and_lists_look_as_before(self):
        first = self.audiogram(date(2026, 9, 28))
        self.audiogram(date(2026, 10, 5))
        with self.saving_artifacts():
            self.open()
            self.page.goto(f"{self.live_server_url}/audiograms/{first.pk}")
            table = self.page.locator("table.table").first
            self.assertEqual(self.style(table, "marginBottom"), "18px")
            # Inside the dropdown box since the pages tidy-up: as wide as the box inside its border.
            inner = table.locator("..").evaluate("el => el.clientWidth")
            self.assertEqual(self.size(table)[0], inner)
            cell = table.locator("th").first
            self.assertEqual(
                self.styles(cell, "padding", "borderBottomWidth", "borderBottomColor", "color"),
                {
                    "padding": "9px",
                    "borderBottomWidth": "1px",
                    "borderBottomColor": "rgb(222, 226, 230)",
                    "color": "rgb(0, 0, 0)",
                },
            )

            self.page.goto(f"{self.live_server_url}/audiograms/compare?a={first.pk}&b={first.pk}")
            warning = self.page.get_by_role("alert").filter(has_text="請選兩張不同的聽力圖")
            self.assertEqual(
                self.styles(
                    warning,
                    "color",
                    "backgroundColor",
                    "borderTopColor",
                    "padding",
                    "borderTopLeftRadius",
                    "marginBottom",
                ),
                {
                    "color": "rgb(102, 77, 3)",
                    "backgroundColor": "rgb(255, 243, 205)",
                    "borderTopColor": "rgb(255, 230, 156)",
                    "padding": "18px",
                    "borderTopLeftRadius": "6.75px",
                    "marginBottom": "18px",
                },
            )

            audiogram_step(self.page, self.live_server_url, 4)
            self.page.get_by_role("button", name="存檔").click()
            danger = self.page.get_by_role("alert").filter(has_text="請至少標記一個點")
            self.assertEqual(
                self.styles(danger, "color", "backgroundColor", "borderTopColor"),
                {
                    "color": "rgb(88, 21, 28)",
                    "backgroundColor": "rgb(248, 215, 218)",
                    "borderTopColor": "rgb(241, 174, 181)",
                },
            )

            self.open(javascript=False)
            self.page.goto(f"{self.live_server_url}/questionnaire/{self.hhie_s.pk}")
            # Skip the browser's required check to reach the server's list of unanswered questions.
            self.page.evaluate("document.getElementById('answer-form').noValidate = true")
            self.page.get_by_role("button", name="送出").click()
            unanswered = self.page.locator("#error-summary ul")
            self.assertEqual(
                self.styles(unanswered, "paddingLeft", "listStyleType"),
                {"paddingLeft": "0px", "listStyleType": "none"},
            )
            # #272: each question's own error has the warning mark too, not the red alone.
            question_error = self.page.locator(".field-error").first
            self.assertEqual(self.style(question_error, "fontWeight"), "700")
            self.assertIn(
                "data:image/svg+xml",
                question_error.evaluate("el => getComputedStyle(el, '::before').maskImage"),
            )

    def test_screen_reader_only_text_is_hidden_but_read(self):
        self.open(signed_in=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/login")
            skip = self.page.get_by_role("link", name="跳到主要內容")
            self.assertEqual(self.size(skip), (1, 1))
            self.assertEqual(self.style(skip, "clip"), "rect(0px, 0px, 0px, 0px)")
            self.page.keyboard.press("Tab")
            expect(skip).to_be_focused()
            width, height = self.size(skip)
            self.assertGreater(width, 44)
            self.assertGreater(height, 44)
            self.assertEqual(self.style(skip, "clip"), "auto")

            self.open()
            self.page.goto(f"{self.live_server_url}/questionnaire_list?choose=self")
            pause = self.page.locator(".card-tags .visually-hidden").first
            self.assertEqual(self.size(pause), (1, 1))
            self.assertEqual(
                self.styles(pause, "position", "overflow", "clip", "whiteSpace"),
                {
                    "position": "absolute",
                    "overflow": "hidden",
                    "clip": "rect(0px, 0px, 0px, 0px)",
                    "whiteSpace": "nowrap",
                },
            )
            # Still in the accessibility tree: the link's name includes the hidden pause.
            expect(
                self.page.get_by_role("link", name=re.compile(r"題\s*，\s*約"))
            ).not_to_have_count(0)

    def test_text_primary_and_error_colours(self):
        self.open(signed_in=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/privacy")
            self.assertEqual(self.style(self.page.locator("body"), "color"), self.TEXT)
            muted = self.page.get_by_text(re.compile(r"^第 \d+ 版，.*更新$"))
            self.assertEqual(self.style(muted, "color"), self.TEXT)
            self.page.goto(f"{self.live_server_url}/login")
            submit = self.page.get_by_role("button", name="登入")
            self.assertEqual(self.style(submit, "backgroundColor"), self.PRIMARY)
            self.page.get_by_label("使用者名稱").fill("nobody")
            # exact: the 顯示 button's name, 顯示密碼, holds 密碼 as well.
            self.page.get_by_label("密碼", exact=True).fill("not-the-password")
            submit.click()
            error = self.page.locator("#login_error")
            expect(error).to_be_visible()
            self.assertEqual(self.style(error, "color"), self.ERROR)

    def test_a_wrong_entry_turns_the_field_red_and_marks_the_message(self):
        # #272: the field shows the error too, and the message has a warning mark, so neither
        # rests on the red alone. The field keeps its size.
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/account/delete")
            self.page.get_by_label("請輸入密碼確認").fill("not-the-password")
            self.page.get_by_role("main").get_by_role("button", name="刪除帳號").click()
            error = self.page.locator("#id_password_error p")
            expect(error).to_have_text("密碼不正確")
            # Focused again by autofocus; the red stays while the person types.
            password = self.page.get_by_label("請輸入密碼確認")
            self.assertEqual(
                self.styles(password, "borderTopColor", "backgroundColor"),
                {"borderTopColor": self.ERROR, "backgroundColor": "rgb(254, 236, 231)"},
            )
            self.assertEqual(self.size(password)[1], 42.5)
            self.assertEqual(self.style(error, "fontWeight"), "700")
            self.assertIn(
                "data:image/svg+xml",
                error.evaluate("el => getComputedStyle(el, '::before').maskImage"),
            )

    def test_result_banner_colours(self):
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
        self.enterContext(register(fake_definition("unconfigured")))
        self.open()
        with self.saving_artifacts():
            for level, scores, background, colour in self.BANNERS:
                with self.subTest(level=level):
                    unknown = level == "unknown"
                    record = self.submission(unconfigured if unknown else self.hhie_s, scores)
                    logs = (
                        self.assertLogs("screening.scoring", "ERROR") if unknown else nullcontext()
                    )
                    with logs:
                        self.page.goto(f"{self.live_server_url}/submission/{record.pk}")
                    banner = self.page.locator(f".result-banner-{level}")
                    expect(banner).to_be_visible()
                    self.assertEqual(self.style(banner, "color"), colour)
                    self.assertEqual(self.style(banner, "backgroundColor"), background)

    # The trend chart's level names, written by Django, keep their band colours.
    def test_trend_level_names_keep_their_colours(self):
        self.submission(self.hhie_s, (2,) * 10)
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=hhie-s")
            for level, _, background, colour in self.BANNERS[:3]:
                with self.subTest(level=level):
                    item = self.page.locator(f".trend-band-{level}")
                    swatch = item.locator(".trend-band-swatch")
                    self.assertEqual(self.style(item.locator("span").last, "color"), colour)
                    self.assertEqual(self.style(swatch, "backgroundColor"), background)

    # Without JavaScript the trend summary stays and the chart's box, which would stay empty, hides.
    def test_trend_summary_shows_without_javascript(self):
        self.submission(self.hhie_s, (2,) * 10)
        self.open(javascript=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=hhie-s")
            expect(self.page.locator(".trend-summary")).to_be_visible()
            expect(self.page.locator("#trend-plot")).to_be_hidden()

    # #126: the badge's class is built from the level code, as the banner's is.
    def test_level_badge_colours(self):
        for _, scores, _, _ in self.BANNERS[:3]:
            self.submission(self.hhie_s, scores)
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 9, 28))
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=hhie-s")
            for level, _, background, colour in self.BANNERS:
                if level == "unknown":
                    # An audiogram with no points has no degree on either ear.
                    self.page.goto(f"{self.live_server_url}/audiograms/{audiogram.pk}")
                with self.subTest(level=level):
                    badge = self.page.locator(f".level-badge-{level}").first
                    expect(badge).to_be_visible()
                    self.assertEqual(self.style(badge, "color"), colour)
                    self.assertEqual(self.style(badge, "backgroundColor"), background)

    # #149: each level's text reaches 7:1 on its soft background and on white.
    def test_level_text_reaches_7_to_1_on_its_soft_background_and_on_white(self):
        records = {
            level: self.submission(self.hhie_s, scores) for level, scores, _, _ in self.BANNERS[:3]
        }
        self.open()
        with self.saving_artifacts():
            for level, record in records.items():
                self.page.goto(f"{self.live_server_url}/submission/{record.pk}")
                banner = self.page.locator(f".result-banner-{level}")
                expect(banner).to_be_visible()
                with self.subTest(page="result", level=level):
                    text = self.style(banner.locator(".result-level"), "color")
                    self.assertGreaterEqual(
                        self.lowest_contrast(text, self.style(banner, "backgroundColor")), 7
                    )
                    self.assertGreaterEqual(self.lowest_contrast(text, self.WHITE), 7)
            self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=hhie-s")
            bands = self.page.locator("#trend-chart .trend-bands li")
            expect(bands).to_have_count(3)
            for level, record in records.items():
                badge = self.page.locator(f".level-badge-{level}").first
                expect(badge).to_be_visible()
                with self.subTest(page="my_hearing badge", level=level):
                    text = self.style(badge, "color")
                    self.assertGreaterEqual(
                        self.lowest_contrast(text, self.style(badge, "backgroundColor")), 7
                    )
                    self.assertGreaterEqual(self.lowest_contrast(text, self.WHITE), 7)
                # The chart's level names sit on white beside a swatch of their band.
                band = bands.filter(has_text=record.classified["text"])
                with self.subTest(page="my_hearing chart", level=level):
                    text = self.style(band.locator("span").last, "color")
                    swatch = self.style(band.locator(".trend-band-swatch"), "backgroundColor")
                    self.assertGreaterEqual(self.lowest_contrast(text, swatch), 7)
                    self.assertGreaterEqual(self.lowest_contrast(text, self.WHITE), 7)

    def assert_framed_in_its_text_colour(self, element):
        colour = self.style(element, "color")
        for side in ("Top", "Right", "Bottom", "Left"):
            with self.subTest(side=side):
                self.assertEqual(self.style(element, f"border{side}Style"), "solid")
                self.assertEqual(self.style(element, f"border{side}Width"), "2px")
                self.assertEqual(self.style(element, f"border{side}Color"), colour)

    # #149: a frame in the level's own colour, so the soft background has an edge on the page.
    def test_result_banner_and_level_badges_are_framed_in_the_level_colour(self):
        records = {
            level: self.submission(self.hhie_s, scores) for level, scores, _, _ in self.BANNERS[:3]
        }
        self.open()
        with self.saving_artifacts():
            for level, record in records.items():
                self.page.goto(f"{self.live_server_url}/submission/{record.pk}")
                banner = self.page.locator(f".result-banner-{level}")
                expect(banner).to_be_visible()
                with self.subTest(page="result", level=level):
                    self.assert_framed_in_its_text_colour(banner)
            self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=hhie-s")
            for level in records:
                badge = self.page.locator(f".level-badge-{level}").first
                expect(badge).to_be_visible()
                with self.subTest(page="my_hearing", level=level):
                    self.assert_framed_in_its_text_colour(badge)

    # #149: on paper, often black and white, the level stays written out in a frame.
    def test_printed_report_writes_the_level_in_a_frame(self):
        self.submission(self.hhie_s, (4,) * 10)
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/report")
            self.page.emulate_media(media="print")
            levels = self.page.locator(f"#report-{self.hhie_s.code} .report-level")
            expect(levels).to_have_count(1)
            expect(levels).to_be_visible()
            expect(levels).to_have_text("顯著影響")
            self.assert_framed_in_its_text_colour(levels)

    # Answer page tidy-up: one option per row, each as wide as the others.
    def test_answer_choices_are_large_buttons_one_per_row(self):
        self.open(javascript=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire/{self.hhie_s.pk}")
            labels = self.page.locator("#id_form-0-score label")
            first, second = labels.nth(0).bounding_box(), labels.nth(1).bounding_box()
            self.assertGreaterEqual(first["height"], 3 * 18)  # 3rem at the 18px base
            self.assertGreaterEqual(first["width"], 44)  # #119 acceptance 6
            self.assertEqual(first["x"], second["x"])
            self.assertEqual(first["width"], second["width"])
            self.assertGreater(second["y"], first["y"])

    # #119 acceptance 6: link cards and navigation items, like buttons, are at least 44 x 44.
    def test_link_cards_and_navigation_items_are_large_enough_to_tap(self):
        self.submission(self.hhie_s, [2] * 10)
        for width in (390, 1024):
            self.open(width=width)
            with self.saving_artifacts():
                for path in ("/questionnaire_list?choose=self", "/my_hearing"):
                    self.page.goto(f"{self.live_server_url}{path}")
                    cards = self.page.get_by_role("main").locator("a.link-card")
                    items = self.page.get_by_role("navigation", name="主要導覽").locator("a")
                    self.assertGreater(cards.count(), 0)
                    self.assertGreater(items.count(), 1)
                    for target in cards.all() + items.all():
                        href = target.get_attribute("href")
                        with self.subTest(width=width, path=path, target=href):
                            self.assertGreaterEqual(min(self.size(target)), 44)

    def test_answer_form_hides_only_while_loading(self):
        self.open(javascript=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire/{self.hhie_s.pk}")
            form = self.page.locator("#answer-form")
            expect(form).to_be_visible()
            self.assertEqual(self.style(self.page.locator("#answer-loading"), "display"), "none")
            self.page.evaluate("document.documentElement.classList.add('answer-loading')")
            self.assertEqual(self.style(form, "display"), "none")

    def test_printed_report_has_no_site_chrome_or_shadows(self):
        self.submission(self.hhie_s, [2] * 10)
        self.audiogram(date(2026, 9, 28))
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/report")
            chrome = (
                self.page.get_by_role("banner"),
                self.page.get_by_role("navigation", name="主要導覽"),
                self.page.get_by_role("contentinfo"),
                self.page.get_by_role("button", name="列印或存成 PDF"),
            )
            # Seen on screen first, so a renamed or missing part cannot pass as hidden.
            for part in chrome:
                expect(part).to_be_visible()
            expect(self.page.locator(".health-report")).to_have_count(1)
            self.page.emulate_media(media="print")
            for part in chrome:
                expect(part).to_be_hidden()
            shadows = self.page.evaluate(
                "[...document.querySelectorAll('.health-report, .health-report *')]"
                ".map(el => getComputedStyle(el).boxShadow).filter(s => s !== 'none')"
            )
            self.assertEqual(shadows, [])
            # White paper behind the whole report, with no gradient anywhere in it (#137).
            self.assertEqual(self.style(self.page.locator("body"), "backgroundColor"), self.WHITE)
            # Only what prints: a hidden print button may carry a gradient on screen.
            gradients = self.page.evaluate(
                """() => [document.documentElement, document.body,
                    ...document.querySelectorAll('.health-report, .health-report *')]
                    .filter(el => el.checkVisibility())
                    .flatMap(el => [null, '::before', '::after']
                        .map(part => getComputedStyle(el, part).backgroundImage))
                    .filter(image => image !== 'none')"""
            )
            self.assertEqual(gradients, [])
            # A section, and the table in it, stays on one page; a part holding several
            # sections may break between them, but not right after its heading (#130).
            section = self.page.locator(f"#report-{self.hhie_s.code}")
            expect(section.locator("table")).to_have_count(1)
            for whole in (self.page.locator("#report-summary"), section):
                self.assertEqual(self.style(whole, "breakInside"), "avoid")
            part = self.page.locator("#report-life-impact")
            self.assertEqual(self.style(part, "breakInside"), "auto")
            self.assertEqual(self.style(part.locator("> h2"), "breakAfter"), "avoid")

    # #137 (2a): a warm page with white surfaces, and three radius levels.
    def warm_shell_records(self):
        """A history, an IOI-HA answer below the norm and an audiogram: every surface shows."""
        basis = self.submission(self.hhie_s, [2] * 10)
        # #161: the comparison card only shows with both an aided and an unaided record.
        self.submission(self.hhie_s, [0] * 10, wearing=True)
        ioi_ha = Questionnaire.objects.get(code="ioi-ha")
        ioi = Submission.objects.create(
            user=self.user,
            questionnaire=ioi_ha,
            norm_group=NormGroup.MILD_MODERATE,
            norm_basis=basis,
            wearing_hearing_aid=True,
        )
        Answer.objects.bulk_create(
            Answer(submission=ioi, question=question, score=1)
            for question in ioi_ha.questions.all()
        )
        return basis, ioi, self.audiogram(date(2026, 9, 28))

    def test_page_is_warm_and_surfaces_are_white(self):
        audiogram = self.warm_shell_records()[2]
        # #159: these are the new-user home's own elements, so check them signed out.
        home_cases = (
            ("/", "body", self.WARM_PAGE),
            ("/", ".site-footer", self.WARM_FOOTER),
        )
        cases = (
            ("/questionnaire_list?choose=self", "main a.link-card", self.WHITE),
            ("/my_hearing?questionnaire=hhie-s", "#trend-chart .chart-canvas", self.WHITE),
            ("/my_hearing?questionnaire=ioi-ha", ".ioi-chart", self.WHITE),
            (f"/audiograms/{audiogram.pk}", ".audiogram-chart", self.WHITE),
            ("/audiograms/new", "#tested-on", self.WHITE),
            ("/audiograms/new", ".audiogram-table .form-select", self.WHITE),
            ("/audiograms/new", ".audiogram-chart", self.WHITE),
            (f"/questionnaire/{self.hhie_s.pk}", "#id_form-0-score label", self.WHITE),
        )
        with self.saving_artifacts():
            for path, selector, colour in home_cases:
                with self.subTest(path=path, selector=selector):
                    self.open(signed_in=False)
                    self.page.goto(f"{self.live_server_url}{path}")
                    found = self.page.locator(selector).first
                    expect(found).to_be_attached()
                    self.assertEqual(self.style(found, "backgroundColor"), colour)
            for path, selector, colour in cases:
                with self.subTest(path=path, selector=selector):
                    self.open(javascript=not path.startswith("/questionnaire/"))
                    if path == "/audiograms/new" and selector != "#tested-on":
                        audiogram_step(self.page, self.live_server_url, 2)
                    else:
                        self.page.goto(f"{self.live_server_url}{path}")
                    found = self.page.locator(selector).first
                    expect(found).to_be_attached()
                    self.assertEqual(self.style(found, "backgroundColor"), colour)

    def test_text_on_the_warm_page_keeps_its_contrast(self):
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            # Colours as the browser resolves them, against the page and footer backgrounds.
            ratios = self.page.evaluate(
                """() => {
                    const rgb = (colour) => {
                        const probe = document.createElement("span");
                        probe.style.color = colour;
                        document.body.append(probe);
                        const [r, g, b] = getComputedStyle(probe).color.match(/\\d+/g).map(Number);
                        probe.remove();
                        return [r, g, b];
                    };
                    const lum = (c) => c.map((v) => v / 255)
                        .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
                        .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
                    const ratio = (a, b) => {
                        const [hi, lo] = [lum(rgb(a)), lum(rgb(b))].sort((x, y) => y - x);
                        return (hi + 0.05) / (lo + 0.05);
                    };
                    const root = getComputedStyle(document.documentElement);
                    const token = (name) => root.getPropertyValue(name).trim();
                    const page = getComputedStyle(document.body).backgroundColor;
                    const footer = document.querySelector(".site-footer");
                    const out = {};
                    for (const name of ["--color-body", "--color-heading", "--color-primary",
                        "--color-normal", "--color-mild", "--color-severe"]) {
                        out[name] = ratio(token(name), page);
                    }
                    out.body = ratio(getComputedStyle(document.body).color, page);
                    out.footer = ratio(getComputedStyle(footer).color,
                        getComputedStyle(footer).backgroundColor);
                    return out;
                }"""
            )
            self.assertEqual(len(ratios), 8)
            for name, value in ratios.items():
                with self.subTest(text=name):
                    self.assertGreaterEqual(value, 4.5)

    def test_three_radius_levels(self):
        basis, ioi, audiogram = self.warm_shell_records()
        large, medium = "27px", "13.5px"  # 1.5rem and 0.75rem at the 18px base
        cases = (
            ("/questionnaire_list?choose=self", "main a.link-card", large),
            # A returning user: the wizard only by 「幫您挑」 (#346).
            ("/questionnaire_list?wizard=1&from=consent", ".questionnaire-guide", large),
            ("/my_hearing?questionnaire=hhie-s", ".trend-summary", large),
            ("/my_hearing?questionnaire=hhie-s", ".aided-difference", large),
            (f"/submission/{basis.pk}", ".result-banner", medium),
            (f"/submission/{ioi.pk}", ".ioi-note", medium),
            ("/audiograms/new", "#tested-on", medium),
            ("/audiograms/new", ".audiogram-table .form-select", medium),
            ("/audiograms/new", ".audiogram-symbol", medium),
            # #301 (ADR 0022): a chart's drawing area has a small radius, like a sheet of paper.
            ("/my_hearing?questionnaire=hhie-s", "#trend-chart .chart-canvas", "4.5px"),
            ("/my_hearing?questionnaire=ioi-ha", ".ioi-chart", "4.5px"),
            (f"/audiograms/{audiogram.pk}", ".audiogram-chart", "4.5px"),
            # Left as they were: badges, thumbnails and the charts themselves.
            ("/my_hearing?questionnaire=hhie-s", ".level-badge", "18px"),
            ("/audiograms", ".audiogram-thumbnail", "4.5px"),
            (f"/audiograms/{audiogram.pk}", ".audiogram-svg", "0px"),
        )
        with self.saving_artifacts():
            self.open()
            for path, selector, radius in cases:
                with self.subTest(path=path, selector=selector):
                    if path == "/audiograms/new" and selector != "#tested-on":
                        audiogram_step(self.page, self.live_server_url, 2)
                    else:
                        self.page.goto(f"{self.live_server_url}{path}")
                    found = self.page.locator(selector).first
                    expect(found).to_be_attached()
                    # The top right: a blue summary box's left corners are square (#357).
                    self.assertEqual(self.style(found, "borderTopRightRadius"), radius)

    def test_large_white_blocks_have_warm_borders_and_shadows(self):
        cases = (("/questionnaire_list?choose=self", "main a.link-card"),)
        with self.saving_artifacts():
            self.open()
            for path, selector in cases:
                with self.subTest(path=path, selector=selector):
                    self.page.goto(f"{self.live_server_url}{path}")
                    found = self.page.locator(selector).first
                    expect(found).to_be_attached()
                    self.assertEqual(self.style(found, "borderTopColor"), self.WARM_BORDER)
                    self.assertEqual(
                        self.style(found, "boxShadow"),
                        "rgba(120, 90, 50, 0.08) 0px 4.5px 13.5px 0px",
                    )

    def test_masking_switch_keeps_its_orange(self):
        # ADR 0007: the masking switch is one of the few non-level colours kept (#137 acceptance 4).
        self.open()
        with self.saving_artifacts():
            audiogram_step(self.page, self.live_server_url, 2)
            # #333 (D4): on a switch, the orange is the track's.
            switch = self.page.get_by_role("switch", name="遮蔽", exact=True)
            switch.click()
            track = switch.locator(".audiogram-mask-track")
            self.assertEqual(self.style(track, "backgroundColor"), "rgb(179, 89, 0)")

    # #138 (2a): the header gradient and its wave, which plays once per tab (ADR 0006).
    WAVE_ANIMATIONS = """() => document.getAnimations()
        .filter(a => a.effect.target.closest('.site-wave'))
        .map(a => ({ state: a.playState, end: a.effect.getComputedTiming().endTime }))"""

    def assert_wave_plays_and_settles(self, page):
        animations = page.evaluate(self.WAVE_ANIMATIONS)
        self.assertGreater(len(animations), 0)
        self.assertLessEqual(max(a["end"] for a in animations), 4000)
        page.wait_for_timeout(4200)
        self.assertEqual(
            [a for a in page.evaluate(self.WAVE_ANIMATIONS) if a["state"] == "running"], []
        )
        heights = page.locator(".site-wave span").evaluate_all(
            "bars => bars.map(bar => bar.getBoundingClientRect().height)"
        )
        self.assertEqual(len(heights), 28)
        self.assertEqual(len(set(heights)), 1)

    # Brand refresh: a white header with the wave-W logo on a gradient; the wave stays, pale blue.
    LOGO_GRADIENT = "linear-gradient(135deg, rgb(31, 78, 140), rgb(29, 111, 153))"

    def mask(self, locator, pseudo):
        return locator.evaluate(f"el => getComputedStyle(el, '{pseudo}').maskImage")

    def test_header_is_white_with_the_logo_and_a_hidden_wave(self):
        self.open()
        with self.saving_artifacts():
            for path in ("/", "/questionnaire_list"):
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    header = self.page.locator(".site-header")
                    self.assertEqual(self.style(header, "backgroundColor"), self.WHITE)
                    self.assertEqual(self.style(header, "backgroundImage"), "none")
                    brand = header.locator(".site-brand a")
                    self.assertEqual(self.style(brand, "color"), self.PRIMARY)
                    tint = brand.locator(".site-wordmark-tint")
                    self.assertEqual(self.style(tint, "color"), "rgb(29, 111, 153)")
                    logo = brand.locator(".site-logo")
                    self.assertEqual(self.style(logo, "backgroundImage"), self.LOGO_GRADIENT)
                    # The pebble: uneven corners, not a circle.
                    self.assertEqual(self.style(logo, "borderTopLeftRadius"), "42% 48%")
                    self.assertIn("data:image/svg+xml", self.mask(logo, "::after"))
                    texts = (
                        brand.locator(".site-wordmark-tint"),
                        header.get_by_role("link", name="目前登入：style_e2e，帳號設定"),
                        header.get_by_role("button", name="登出"),
                    )
                    for text in texts:
                        colour = self.style(text, "color")
                        self.assertGreaterEqual(self.lowest_contrast(colour, self.WHITE), 4.5)
                    wave = header.locator(".site-wave")
                    self.assertEqual(wave.get_attribute("aria-hidden"), "true")
                    expect(wave.locator("span")).to_have_count(28)

    # Brand refresh: the first-visit home is a white card; its illustration sways once and the
    # start button sends out one ring, inside ADR 0006's four seconds. Reduced motion keeps both
    # still (test_reduced_motion_keeps_the_header_still counts every animation on "/").
    def test_first_visit_home_card_plays_two_animations_once(self):
        self.open(signed_in=False, motion=True)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            hero = self.page.locator(".home-hero")
            # Design picker round 2: the result example has the score bar.
            preview = self.page.locator(".result-preview")
            expect(preview.locator(".score-bar-marker")).to_be_visible()
            animations = self.page.evaluate(
                """() => document.getAnimations()
                    .filter(a => a.effect.target.closest('.home-hero'))
                    .map(a => ({ name: a.animationName, pseudo: a.effect.pseudoElement,
                                 iterations: a.effect.getComputedTiming().iterations,
                                 end: a.effect.getComputedTiming().endTime }))"""
            )
            self.assertEqual(
                sorted((a["name"], a["pseudo"]) for a in animations),
                [("home-sway", None), ("start-ring", "::after")],
            )
            for animation in animations:
                with self.subTest(animation=animation["name"]):
                    self.assertEqual(animation["iterations"], 1)
                    self.assertLessEqual(animation["end"], 4000)

            start = hero.get_by_role("link", name="開始篩檢")
            self.assertEqual(self.style(start, "borderTopLeftRadius"), "999px")
            self.assertIn("data:image/svg+xml", self.mask(start, "::before"))
            self.assertGreaterEqual(self.text_contrast(start), 4.5)
            login = hero.get_by_role("link", name="我已經有帳號，登入")
            self.assertEqual(self.style(login, "backgroundImage"), "none")
            self.assertEqual(self.style(login, "textDecorationLine"), "underline")
            self.assertGreaterEqual(login.bounding_box()["height"], 44)

    def test_header_wave_plays_on_a_tabs_first_page_only(self):
        self.open(motion=True)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            self.assert_wave_plays_and_settles(self.page)
            self.page.goto(f"{self.live_server_url}/questionnaire_list")
            self.assertEqual(self.page.evaluate(self.WAVE_ANIMATIONS), [])
            # A new tab starts again.
            self.page = self.context.new_page()
            self.page.goto(f"{self.live_server_url}/questionnaire_list")
            self.assert_wave_plays_and_settles(self.page)
            # Nothing anywhere on the page loops for ever.
            loops = self.page.evaluate(
                "document.getAnimations()"
                ".filter(a => a.effect.getTiming().iterations === Infinity).length"
            )
            self.assertEqual(loops, 0)

    def test_header_wave_plays_on_every_page_without_javascript(self):
        self.open(javascript=False, motion=True)
        with self.saving_artifacts():
            for path in ("/", "/questionnaire_list"):
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    self.assert_wave_plays_and_settles(self.page)

    # Welcome back option D (ADR 0026): the elder sways, its sound lights up, the gauge draws and
    # the needle swings to the score, each once inside ADR 0006's four seconds; then the needle
    # rests at the score. Reduced motion: nothing moves and the needle is already there.
    WELCOME_ANIMATIONS = """() => document.getAnimations()
        .filter(a => a.effect.target.closest('.welcome'))
        .map(a => ({ name: a.animationName, state: a.playState,
                     iterations: a.effect.getComputedTiming().iterations,
                     end: a.effect.getComputedTiming().endTime }))"""

    def test_welcome_back_plays_once_and_rests_at_the_score(self):
        self.submission(self.hhie_s, (2,) * 10)  # 20 of 40: the needle at 90 degrees
        for motion in (True, False):
            with self.subTest(motion=motion):
                self.open(motion=motion)
                with self.saving_artifacts():
                    self.page.goto(f"{self.live_server_url}/")
                    needle = self.page.locator(".score-gauge-needle")
                    expect(needle).to_be_attached()
                    animations = self.page.evaluate(self.WELCOME_ANIMATIONS)
                    if not motion:
                        self.assertEqual(animations, [])
                    else:
                        self.assertEqual(
                            {a["name"] for a in animations},
                            {"home-sway", "welcome-sound", "gauge-draw", "gauge-needle"},
                        )
                        for animation in animations:
                            self.assertEqual(animation["iterations"], 1, animation)
                            self.assertLessEqual(animation["end"], 4000, animation)
                        self.page.wait_for_timeout(4200)
                        running = self.page.evaluate(self.WELCOME_ANIMATIONS)
                        self.assertEqual([a for a in running if a["state"] == "running"], [])
                    # rotate(90deg) as a matrix: cos 90 = 0, sin 90 = 1.
                    self.assertEqual(self.style(needle, "transform"), "matrix(0, 1, -1, 0, 0, 0)")

    def test_reduced_motion_keeps_the_header_still(self):
        self.open()  # reduced motion
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            expect(self.page.locator(".site-wave span")).to_have_count(28)
            self.assertEqual(self.page.evaluate("document.getAnimations().length"), 0)

    # #139 (2a): primary buttons follow choice C in #136 (docs/verification/issue-136.md); every
    # button is a pill and only changes colour.
    @staticmethod
    def lowest_contrast(text, background):
        """Lowest WCAG ratio of a text colour against every colour in a background value."""

        def luminance(rgb):
            channels = [c / 255 for c in rgb]
            linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        def colours(value):
            return [tuple(map(int, m)) for m in re.findall(r"rgb\((\d+), (\d+), (\d+)\)", value)]

        light = luminance(colours(text)[0])
        ratios = []
        for colour in colours(background):
            pair = sorted((light, luminance(colour)), reverse=True)
            ratios.append((pair[0] + 0.05) / (pair[1] + 0.05))
        return min(ratios)

    def text_contrast(self, element, text="color"):
        """Lowest contrast of an element's text (or icon stroke) against its own background."""
        background = self.style(element, "backgroundImage")
        if background == "none":
            background = self.style(element, "backgroundColor")
        return self.lowest_contrast(self.style(element, text), background)

    def test_primary_button_states_follow_choice_c(self):
        self.open(signed_in=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/login")
            button = self.page.get_by_role("main").get_by_role("button", name="登入")
            self.assertEqual(self.style(button, "backgroundImage"), self.GRADIENT)
            self.assertEqual(self.style(button, "color"), self.WHITE)
            self.assertGreaterEqual(self.text_contrast(button), 4.5)
            button.hover()
            self.assertEqual(self.style(button, "backgroundImage"), self.GRADIENT)
            self.assertEqual(self.style(button, "boxShadow"), self.GLOW)
            self.page.mouse.down()
            self.assertEqual(self.style(button, "backgroundImage"), self.PRESSED_GRADIENT)
            self.assertEqual(self.style(button, "boxShadow"), "none")
            self.assertGreaterEqual(self.text_contrast(button), 4.5)
            self.page.mouse.up()
            self.page.mouse.move(0, 0)
            button.evaluate("el => { el.disabled = true; }")
            disabled = self.styles(
                button,
                "backgroundImage",
                "backgroundColor",
                "color",
                "borderTopColor",
                "boxShadow",
                "opacity",
            )
            self.assertEqual(
                disabled,
                {
                    "backgroundImage": "none",
                    "backgroundColor": self.WHITE,
                    "color": "rgb(77, 95, 120)",
                    "borderTopColor": "rgb(141, 162, 191)",
                    "boxShadow": "rgb(141, 162, 191) 0px 0px 0px 1px inset",  # a 2px edge in all
                    "opacity": "1",
                },
            )
            self.assertGreaterEqual(self.lowest_contrast(disabled["color"], self.WHITE), 4.5)

    def test_buttons_are_pills_and_only_change_colour(self):
        # Except the audiogram symbol buttons, which #120 lists at the medium radius
        # (test_three_radius_levels).
        cases = (
            (False, "/login", "button", "登入"),
            (False, "/login", "link", "註冊新帳號"),
            (True, "/", "button", "登出"),
            (True, "/account/delete", "button", "刪除帳號"),
        )
        with self.saving_artifacts():
            for signed_in, path, role, name in cases:
                with self.subTest(button=name):
                    self.open(signed_in=signed_in)
                    self.page.goto(f"{self.live_server_url}{path}")
                    area = self.page if name == "登出" else self.page.get_by_role("main")
                    button = area.get_by_role(role, name=name, exact=True)
                    self.assertEqual(self.style(button, "borderTopLeftRadius"), "999px")
                    button.scroll_into_view_if_needed()
                    before = button.bounding_box()
                    button.hover()
                    self.assertEqual(button.bounding_box(), before)
                    self.page.mouse.down()
                    self.assertEqual(button.bounding_box(), before)
                    self.assertEqual(self.style(button, "transform"), "none")
                    # Let go elsewhere, so logout and delete are never actually clicked.
                    self.page.mouse.move(0, 0)
                    self.page.mouse.up()

    def test_delete_buttons_stay_red(self):
        audiogram = self.audiogram(date(2026, 9, 28))
        self.submission(self.hhie_s, [2] * 10)
        ReportShare.objects.create(user=self.user, token="red-button-share")
        red = "rgb(220, 53, 69)"
        cases = (
            ("/account/delete", "button", "刪除帳號", "backgroundColor"),
            (f"/audiograms/{audiogram.pk}/delete", "button", "確定刪除", "backgroundColor"),
            ("/share", "button", "取消分享", "color"),
        )
        self.open()
        with self.saving_artifacts():
            for path, role, name, prop in cases:
                with self.subTest(button=name):
                    self.page.goto(f"{self.live_server_url}{path}")
                    button = self.page.get_by_role(role, name=name, exact=True)
                    self.assertEqual(self.style(button, prop), red)
                    self.assertEqual(self.style(button, "borderTopColor"), red)
            # #201: the result page's delete is a red text link on the warm page, darker than
            # the button red (4.24:1 there) to keep 4.5:1, and still a full touch target.
            with self.subTest(button="刪除這張"):
                self.page.goto(f"{self.live_server_url}/audiograms/{audiogram.pk}")
                link = self.page.get_by_role("link", name="刪除這張", exact=True)
                self.assertEqual(self.style(link, "color"), self.ERROR)
                self.assertGreaterEqual(self.lowest_contrast(self.ERROR, self.WARM_PAGE), 4.5)
                self.assertGreaterEqual(self.size(link)[1], 44)
                edit = self.page.get_by_role("link", name="修改這張", exact=True)
                self.assertGreaterEqual(self.size(edit)[1], 44)

    def test_keyboard_focus_ring_stays_beside_the_glow(self):
        self.open(signed_in=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/login")
            button = self.page.get_by_role("main").get_by_role("button", name="登入")
            button.hover()
            hover_only = self.style(button, "boxShadow")
            self.page.mouse.move(0, 0)
            button.focus()
            self.assertTrue(button.evaluate("el => el.matches(':focus-visible')"))
            focus_only = self.style(button, "boxShadow")
            # A blurred glow against a crisp ring: never the same look.
            self.assertEqual(hover_only, self.GLOW)
            self.assertEqual(focus_only, self.FOCUS_RING)
            self.assertNotIn(" 0px 0px 0px ", hover_only)
            # Hovered as well: the ring stays next to the button, the glow goes outside it.
            button.hover()
            self.assertEqual(
                self.style(button, "boxShadow"),
                f"{self.FOCUS_RING}, rgba(29, 111, 153, 0.45) 0px 0px 16.2px 8.1px",
            )
            # Pressed from the keyboard: no glow, the ring stays.
            self.page.keyboard.down("Space")
            self.assertTrue(button.evaluate("el => el.matches(':active')"))
            self.assertEqual(self.style(button, "boxShadow"), self.FOCUS_RING)

    # #140 (2a): the gradient marks where you are, and the questionnaire icons.
    def test_current_place_and_icons_use_the_gradient(self):
        # Two questionnaires answered, so my hearing shows its tabs.
        self.submission(self.hhie_s, [2] * 10)
        self.submission(Questionnaire.objects.get(code="ioi-ha"), [3] * 7)
        self.open()  # 1024 wide: the top navigation bar
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=hhie-s")
            nav = self.page.get_by_role("navigation", name="主要導覽")
            current = nav.locator('a[aria-current="page"]')
            others = nav.locator("a:not([aria-current])")
            self.assertGreater(others.count(), 0)
            for element in (current, self.page.locator('.history-tabs a[aria-current="page"]')):
                self.assertEqual(self.style(element, "backgroundImage"), self.GRADIENT)
                self.assertEqual(self.style(element, "color"), self.WHITE)
                self.assertGreaterEqual(self.text_contrast(element), 4.5)
            # Shape as well as colour: only the current page is a pill.
            self.assertEqual(self.style(current, "borderTopLeftRadius"), "999px")
            self.assertEqual(self.style(current, "boxShadow"), "none")
            # Design picker round 2: a shadow along the top parts the white bar from the white
            # header, and the pill sits inside the bar instead of filling its height.
            self.assertIn("inset", self.style(nav, "boxShadow"))
            bar, pill = nav.bounding_box(), current.bounding_box()
            self.assertGreaterEqual(pill["y"] - bar["y"], 4)
            self.assertGreaterEqual(bar["y"] + bar["height"] - pill["y"] - pill["height"], 4)
            self.assertGreaterEqual(pill["height"], 44)
            for other in others.all():
                self.assertEqual(self.style(other, "backgroundImage"), "none")

            # #159: the step numbers are the new-user home's own elements, so check them signed out.
            self.open(signed_in=False)
            self.page.goto(f"{self.live_server_url}/")
            number = self.page.locator(".step-number").first
            self.assertEqual(self.style(number, "backgroundImage"), self.GRADIENT)
            self.assertEqual(self.style(number, "color"), self.WHITE)

            self.open()
            self.page.goto(f"{self.live_server_url}/questionnaire_list?choose=self")
            icon = self.page.locator(".questionnaire-icon").first
            self.assertEqual(self.style(icon, "backgroundImage"), self.GRADIENT)
            stroke = self.style(icon.locator("svg"), "stroke")
            self.assertEqual(stroke, self.WHITE)
            self.assertGreaterEqual(
                self.lowest_contrast(stroke, self.style(icon, "backgroundImage")), 3
            )

    def test_phone_tab_bar_puts_the_current_icon_in_a_pill(self):
        self.open(width=390)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire_list")
            nav = self.page.get_by_role("navigation", name="主要導覽")
            current = nav.locator('a[aria-current="page"]')
            self.assertEqual(self.style(current, "boxShadow"), "none")  # no line along the top
            self.assertEqual(self.style(current.locator("svg"), "backgroundImage"), self.GRADIENT)
            self.assertEqual(self.style(current.locator("svg"), "stroke"), self.WHITE)
            self.assertEqual(
                self.styles(current.locator("span"), "color", "fontWeight"),
                {"color": self.PRIMARY, "fontWeight": "700"},
            )
            self.assertGreaterEqual(min(self.size(current)), 44)
            for other in nav.locator("a:not([aria-current])").all():
                self.assertEqual(self.style(other.locator("svg"), "backgroundImage"), "none")

    def test_navigation_items_only_change_colour(self):
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire_list")
            item = self.page.get_by_role("navigation", name="主要導覽").get_by_role(
                "link", name="紀錄"
            )
            before = (item.bounding_box(), self.style(item, "color"))
            item.hover()
            self.assertEqual(item.bounding_box(), before[0])
            self.assertNotEqual(self.style(item, "color"), before[1])
            self.page.mouse.down()
            self.assertEqual(item.bounding_box(), before[0])
            self.assertEqual(self.style(item, "transform"), "none")
            self.page.mouse.move(0, 0)
            self.page.mouse.up()

    def test_answer_choices_only_change_colour(self):
        # #120 acceptance 11: like buttons and navigation items, answer choices turn blue on
        # hover and never move.
        self.open(motion=True)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire/{self.hhie_s.pk}")
            # The React page's own choice: the hidden Django form below it has the same markup,
            # and is all there is until React has loaded the questions.
            choice = self.page.locator("#answer-app div.choice-group label").first
            choice.scroll_into_view_if_needed()
            before = choice.bounding_box()
            self.assertEqual(self.style(choice, "borderTopColor"), "rgb(206, 212, 218)")
            choice.hover()
            self.assertEqual(self.settled(choice).bounding_box(), before)
            self.assertEqual(self.style(choice, "borderTopColor"), self.PRIMARY)
            self.page.mouse.down()
            self.assertEqual(self.settled(choice).bounding_box(), before)
            self.assertEqual(self.style(choice, "transform"), "none")
            self.page.mouse.move(0, 0)
            self.page.mouse.up()

    def test_comparison_radio_cards_only_change_colour(self):
        # #190 (ADR 0006): the comparison page's radio cards turn blue on hover and when chosen,
        # and never move.
        # Two unaided records, so that side starts with none chosen (a lone one is, F2).
        self.submission(self.hhie_s, [2] * 10)
        self.submission(self.hhie_s, [4] * 10)
        self.submission(self.hhie_s, [0] * 10, wearing=True)
        self.open(motion=True)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/comparisons/{self.hhie_s.pk}")
            card = self.page.locator("div.choice-group label").first
            card.scroll_into_view_if_needed()
            before = card.bounding_box()
            self.assertEqual(self.style(card, "borderTopColor"), "rgb(206, 212, 218)")
            card.hover()
            self.assertEqual(self.settled(card).bounding_box(), before)
            self.assertEqual(self.style(card, "borderTopColor"), self.PRIMARY)
            self.page.mouse.down()
            self.assertEqual(self.settled(card).bounding_box(), before)
            self.assertEqual(self.style(card, "transform"), "none")
            self.page.mouse.up()
            self.page.mouse.move(0, 0)
            # Chosen: dark blue fill (#328, C1), same place and size.
            self.assertEqual(self.settled(card).bounding_box(), before)
            self.assertEqual(self.style(card, "backgroundColor"), self.PRIMARY)
            self.assertEqual(self.style(card, "transform"), "none")

    # #141 (2a): only clickable cards move (ADR 0006); boxes that cannot be clicked stay still.
    CARD_PAGES = ("/questionnaire_list?choose=self", "/my_hearing", "/audiograms")
    LIFTED = "matrix(1, 0, 0, 1, 0, -4.5)"
    LIFTED_SHADOW = "rgba(120, 90, 50, 0.16) 0px 9px 22.5px 0px"
    REST_SHADOW = "rgba(120, 90, 50, 0.08) 0px 4.5px 13.5px 0px"
    PRESSED_CARD = "rgb(232, 238, 247)"  # darker than the hover colour

    @staticmethod
    def settled(locator):
        """Wait for the element's own transitions to finish, then hand it back."""
        locator.evaluate("el => Promise.all(el.getAnimations().map(a => a.finished))")
        return locator

    def first_card(self, path):
        """The page's first clickable card."""
        self.page.goto(f"{self.live_server_url}{path}")
        # No wait for my hearing's trend chart: its box keeps its height, so the cards stay put.
        card = self.page.locator("a.link-card").first
        card.scroll_into_view_if_needed()
        return card

    def test_clickable_cards_lift_on_hover(self):
        self.submission(self.hhie_s, [2] * 10)
        self.audiogram(date(2026, 9, 28))
        self.open(motion=True)
        with self.saving_artifacts():
            for path in self.CARD_PAGES:
                with self.subTest(path=path):
                    card = self.first_card(path)
                    before = card.bounding_box()
                    card.hover()
                    self.settled(card)
                    self.assertEqual(
                        self.styles(card, "transform", "boxShadow", "borderTopColor"),
                        {
                            "transform": self.LIFTED,
                            "boxShadow": self.LIFTED_SHADOW,
                            "borderTopColor": self.PRIMARY,
                        },
                    )
                    self.assertAlmostEqual(card.bounding_box()["y"], before["y"] - 4.5)
                    self.page.mouse.move(0, 0)

            # The questionnaire card's icon sends out one ripple.
            self.page.goto(f"{self.live_server_url}/questionnaire_list?choose=self")
            card = self.page.locator("a.link-card").first
            card.hover()
            ripples = card.locator(".questionnaire-icon").evaluate(
                """icon => document.getAnimations()
                    .filter(a => a.effect.target === icon && a.effect.pseudoElement === '::after')
                    .map(a => a.effect.getComputedTiming())"""
            )
            self.assertEqual(len(ripples), 1)
            self.assertEqual(ripples[0]["iterations"], 1)
            self.assertLessEqual(ripples[0]["endTime"], 1000)

    def test_pressed_cards_sink_on_a_touch_screen(self):
        # Headless Chromium on Linux never sets :active from simulated touch (CI probe,
        # 2026-10-22), so the states are forced the way DevTools does. Whether a finger sets
        # them is the phone browser's job, checked by hand on a real phone.
        self.submission(self.hhie_s, [2] * 10)
        self.audiogram(date(2026, 9, 28))
        sunk = {
            "transform": "matrix(1, 0, 0, 1, 0, 2.25)",
            "borderTopColor": self.PRIMARY,
            "backgroundColor": self.PRESSED_CARD,
        }
        rest = {
            "transform": "none",
            "boxShadow": self.REST_SHADOW,
            "borderTopColor": self.WARM_BORDER,
            "backgroundColor": self.WHITE,
        }
        self.open(width=390, motion=True, touch=True)
        self.assertFalse(self.page.evaluate("matchMedia('(hover: hover)').matches"))
        devtools = self.context.new_cdp_session(self.page)
        with self.saving_artifacts():
            for path in self.CARD_PAGES:
                with self.subTest(path=path):
                    card = self.first_card(path)
                    devtools.send("DOM.enable")
                    devtools.send("CSS.enable")
                    root = devtools.send("DOM.getDocument")["root"]["nodeId"]
                    node = devtools.send(
                        "DOM.querySelector", {"nodeId": root, "selector": "a.link-card"}
                    )["nodeId"]

                    def force(*states, node=node):
                        devtools.send(
                            "CSS.forcePseudoState", {"nodeId": node, "forcedPseudoClasses": states}
                        )

                    # Pressed: sunk and darker.
                    force("active", "hover")
                    self.assertEqual(self.styles(self.settled(card), *sunk), sunk)
                    # Let go: a phone still counts the tapped card as hovered; it looks at rest.
                    force("hover")
                    self.assertEqual(self.styles(self.settled(card), *rest), rest)

    def test_reduced_motion_cards_only_change_colour(self):
        self.open()  # reduced motion
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire_list?choose=self")
            card = self.page.locator("a.link-card").first
            before = card.bounding_box()
            card.hover()
            self.assertEqual(card.bounding_box(), before)
            self.assertEqual(
                self.styles(card, "transform", "boxShadow", "borderTopColor"),
                {
                    "transform": "none",
                    "boxShadow": self.REST_SHADOW,
                    "borderTopColor": self.PRIMARY,
                },
            )
            self.page.mouse.down()
            self.assertEqual(card.bounding_box(), before)
            self.assertEqual(
                self.styles(card, "transform", "boxShadow", "backgroundColor"),
                {
                    "transform": "none",
                    "boxShadow": self.REST_SHADOW,
                    "backgroundColor": self.PRESSED_CARD,
                },
            )
            # No ripple, and nothing else animates either.
            self.assertEqual(self.page.evaluate("document.getAnimations().length"), 0)
            self.page.mouse.move(0, 0)
            self.page.mouse.up()

    def test_boxes_that_cannot_be_clicked_stay_still(self):
        record = self.submission(self.hhie_s, [2] * 10)
        aided = self.submission(self.hhie_s, [0] * 10, wearing=True)
        ioi = self.submission(Questionnaire.objects.get(code="ioi-ha"), [3] * 7, wearing=True)
        Submission.objects.filter(pk=ioi.pk).update(norm_group=NormGroup.UNGROUPED)
        # #159: the step cards are the new-user home's own elements, so check them signed out.
        home_cases = (("/", ".step-cards li"),)
        cases = (
            ("/my_hearing?questionnaire=hhie-s", ".trend-summary"),
            (f"/submission/{record.pk}", ".result-banner"),
            # #192: batch 1's new boxes, an IOI-HA item and the comparison page's result card.
            (f"/submission/{ioi.pk}", ".ioi-item"),
            (
                f"/comparisons/{self.hhie_s.pk}?unaided={record.pk}&aided={aided.pk}"
                "&action=preview",
                '[aria-labelledby="preview-title"]',
            ),
        )
        every_style = """el => Object.fromEntries(
            [...getComputedStyle(el)].map(p => [p, getComputedStyle(el).getPropertyValue(p)])
        )"""

        def check(path, selector):
            self.page.goto(f"{self.live_server_url}{path}")
            box = self.page.locator(selector).first
            box.scroll_into_view_if_needed()
            before = (box.bounding_box(), box.evaluate(every_style))
            box.hover()
            self.settled(box)
            self.assertEqual((box.bounding_box(), box.evaluate(every_style)), before)
            self.page.mouse.down()
            self.settled(box)
            self.assertEqual((box.bounding_box(), box.evaluate(every_style)), before)
            self.page.mouse.up()

        with self.saving_artifacts():
            self.open(motion=True, signed_in=False)
            for path, selector in home_cases:
                with self.subTest(box=selector):
                    check(path, selector)
            self.open(motion=True)
            for path, selector in cases:
                with self.subTest(box=selector):
                    check(path, selector)

    # #158 acceptance 2 and 6: at 0 and full marks the marker sits flush inside the bar, is not
    # cut off, and nothing on the bar moves, with or without reduced motion.
    def test_score_bar_marker_stays_inside_and_still(self):
        records = {
            0: self.submission(self.hhie_s, [0] * 10),
            40: self.submission(self.hhie_s, [4] * 10),
        }
        for motion in (False, True):
            self.open(motion=motion)
            with self.saving_artifacts():
                for total, record in records.items():
                    with self.subTest(total=total, motion=motion):
                        self.page.goto(f"{self.live_server_url}/submission/{record.pk}")
                        bar = self.page.locator(".score-bar-segments").bounding_box()
                        marker = self.page.locator(".score-bar-marker").bounding_box()
                        flush = (
                            bar["x"] if total == 0 else bar["x"] + bar["width"] - marker["width"]
                        )
                        self.assertAlmostEqual(marker["x"], flush, delta=0.5)
                        track = self.page.locator(".score-bar-track")
                        self.assertEqual(self.style(track, "overflow"), "visible")
                        # The bar only: the header wave plays on a tab's first page (ADR 0006).
                        animations = self.page.locator(".score-bar").evaluate(
                            "el => el.getAnimations({subtree: true}).length"
                        )
                        self.assertEqual(animations, 0)
                        for selector in (".score-bar-segment", ".score-bar-marker"):
                            found = self.page.locator(selector).first
                            self.assertEqual(self.style(found, "transitionDuration"), "0s")
                            self.assertEqual(self.style(found, "animationName"), "none")

    # Result pages tidy-up: THI's five levels in three colours draw five score bar segments and
    # five legend swatches, the higher of two in one colour deeper, a white line between segments;
    # every dropdown on the page is a full touch target.
    def test_thi_bar_and_legend_shade_levels_sharing_a_colour(self):
        call_command("seed_questionnaires", verbosity=0)
        thi = Questionnaire.objects.get(code="thi")
        record = self.submission(thi, [4] * 12 + [0] * 13)  # 48: 中度障礙
        fills = [
            "rgb(227, 244, 236)",
            "rgb(255, 244, 214)",
            "rgb(249, 221, 150)",
            "rgb(254, 236, 231)",
            "rgb(246, 195, 179)",
        ]
        self.open(width=390)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/submission/{record.pk}")
            segments = self.page.locator(".score-bar-segment").all()
            self.assertEqual([self.style(s, "backgroundColor") for s in segments], fills)
            self.assertEqual(
                [self.styles(s, "borderLeftWidth", "borderLeftColor") for s in segments[1:]],
                [{"borderLeftWidth": "2px", "borderLeftColor": self.WHITE}] * 4,
            )
            self.assertEqual(self.style(segments[0], "borderLeftWidth"), "0px")
            summaries = self.page.locator("main details > summary").all()
            self.assertEqual(len(summaries), 2)
            for summary in summaries:
                self.assertGreaterEqual(summary.bounding_box()["height"], 44)
            self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=thi")
            swatches = self.page.locator(".trend-band-swatch").all()
            # Top band first, as stacked in the chart.
            self.assertEqual(
                [self.style(s, "backgroundColor") for s in swatches], list(reversed(fills))
            )

    def test_keyboard_focus_keeps_cards_still_with_a_ring(self):
        self.open(motion=True)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire_list?choose=self")
            card = self.page.locator("a.link-card").first
            before = card.bounding_box()
            for _ in range(30):
                self.page.keyboard.press("Tab")
                if card.evaluate("el => el === document.activeElement"):
                    break
            else:
                self.fail("Tab never reached the first questionnaire card")
            self.assertTrue(card.evaluate("el => el.matches(':focus-visible')"))
            self.settled(card)
            self.assertEqual(card.bounding_box(), before)
            self.assertEqual(
                self.styles(card, "transform", "outline", "outlineOffset", "borderTopColor"),
                {
                    "transform": "none",
                    "outline": f"{self.PRIMARY} solid 4px",  # 0.25rem, drawn in whole pixels
                    "outlineOffset": "4px",
                    "borderTopColor": self.PRIMARY,
                },
            )


class ColourOnlyFeedbackTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#328 (spec #326 A2, A3, A4, C1, C2, D1; ADR 0028): pressing, and hovering with a mouse,
    changes colour only; nothing moves or changes size. Presses are forced the way DevTools does:
    headless Chromium on Linux never sets :active from simulated touch (CI probe, 2026-10-22)."""

    fixtures = ("questions_fixture.json",)
    PRIMARY = "rgb(31, 78, 140)"
    WHITE = "rgb(255, 255, 255)"
    CLEAR = "rgba(0, 0, 0, 0)"
    GREY_EDGE = "rgb(206, 212, 218)"
    # The light blues the dropdowns' title bars already use, and the deeper one beside them.
    BRAND_SOFT = "rgb(238, 243, 250)"
    BRAND_SELECTED = "rgb(232, 238, 247)"
    BRAND_SOFT_DEEP = "rgb(214, 226, 242)"
    GRADIENT = "linear-gradient(rgb(31, 78, 140), rgb(29, 111, 153))"
    PRESSED_GRADIENT = "linear-gradient(rgb(23, 59, 106), rgb(24, 95, 131))"
    # D1: the thick blue edge on an open dropdown's left, 0.3rem at the 18px base, painted on its
    # background (a 並列區塊 keeps no shadow, ADR 0024).
    OPEN_EDGE = "linear-gradient(to right, rgb(31, 78, 140) 5.4px, rgba(0, 0, 0, 0) 5.4px)"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.user = consented_user(username="colour_feedback_e2e")
        self.hhie_s = Questionnaire.objects.get(code="hhie-s")
        self.client.force_login(self.user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, width=1024, javascript=True, touch=False):
        # Reduced motion, so a colour is read at its final value; touch is a phone without a mouse.
        self.context = self.browser.new_context(
            viewport={"width": width, "height": 900},
            java_script_enabled=javascript,
            reduced_motion="reduce",
            has_touch=touch,
            is_mobile=touch,
        )
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def style(self, locator, prop, pseudo=None):
        return locator.evaluate(
            "(el, [prop, pseudo]) => getComputedStyle(el, pseudo)[prop]", [prop, pseudo]
        )

    def submission(self, questionnaire, scores, wearing=False):
        record = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=question, score=score)
            for question, score in zip(questionnaire.questions.all(), scores, strict=True)
        )
        return record

    def audiogram(self, tested_on):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=tested_on)
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=40)
            for ear in ("right", "left")
            for f in (500, 1000, 2000, 4000)
        )
        return audiogram

    def under(self, target, *states, props=("backgroundColor",), of=None):
        """The props of `of` (the target itself by default) while `states` are forced on the
        target; neither moves nor changes size meanwhile."""
        of = of or target
        before = (target.bounding_box(), of.bounding_box())
        devtools = self.context.new_cdp_session(self.page)
        devtools.send("DOM.enable")
        devtools.send("CSS.enable")
        target.evaluate("el => el.setAttribute('data-e2e-forced', '')")
        root = devtools.send("DOM.getDocument")["root"]["nodeId"]
        node = devtools.send("DOM.querySelector", {"nodeId": root, "selector": "[data-e2e-forced]"})
        target.evaluate("el => el.removeAttribute('data-e2e-forced')")
        devtools.send(
            "CSS.forcePseudoState", {"nodeId": node["nodeId"], "forcedPseudoClasses": list(states)}
        )
        try:
            values = {prop: self.style(of, prop) for prop in props}
            self.assertEqual((target.bounding_box(), of.bounding_box()), before)
            self.assertEqual(self.style(target, "transform"), "none")
        finally:
            devtools.send(
                "CSS.forcePseudoState", {"nodeId": node["nodeId"], "forcedPseudoClasses": []}
            )
            devtools.detach()
        return values if len(props) > 1 else values[props[0]]

    # A2: the tab or half not chosen turns light blue under a mouse and a step deeper pressed;
    # the chosen one stays as it is.
    def test_tabs_and_switches_change_colour_when_hovered_or_pressed(self):
        self.submission(self.hhie_s, [2] * 10)
        self.submission(Questionnaire.objects.get(code="ioi-ha"), [3] * 7)
        self.audiogram(date(2026, 9, 1))
        self.audiogram(date(2026, 9, 28))
        cases = (
            # (name, page, navigation, the other one at rest, hovered, pressed)
            (
                "questionnaire tabs",
                "/my_hearing?questionnaire=hhie-s",
                "問卷",
                self.WHITE,
                self.BRAND_SOFT,
                self.BRAND_SELECTED,
            ),
            # The two halves sit on a light blue track: hovered lighter, pressed deeper.
            (
                "records switch",
                "/audiograms",
                "紀錄種類",
                self.CLEAR,
                self.BRAND_SOFT,
                self.BRAND_SOFT_DEEP,
            ),
            (
                "ear switch",
                "/audiograms/compare",
                "選耳朵",
                self.CLEAR,
                self.BRAND_SOFT,
                self.BRAND_SOFT_DEEP,
            ),
        )
        self.open()
        with self.saving_artifacts():
            for name, path, label, rest, hovered, pressed in cases:
                with self.subTest(name):
                    self.page.goto(f"{self.live_server_url}{path}")
                    nav = self.main().get_by_role("navigation", name=label)
                    other = nav.locator("a:not([aria-current])").first
                    track = self.style(nav, "backgroundColor")
                    self.assertEqual(self.style(other, "backgroundColor"), rest)
                    self.assertEqual(self.under(other, "hover"), hovered)
                    self.assertEqual(self.under(other, "hover", "active"), pressed)
                    for colour in (hovered, pressed):
                        self.assertNotIn(colour, (rest, track))
                    current = nav.locator("[aria-current]")
                    props = ("backgroundColor", "backgroundImage", "color")
                    at_rest = {prop: self.style(current, prop) for prop in props}
                    self.assertEqual(at_rest["backgroundImage"], self.GRADIENT)
                    for states in (("hover",), ("hover", "active")):
                        self.assertEqual(self.under(current, *states, props=props), at_rest)

    # A3: on a phone the pill behind a tab's icon lights up under the finger; wide screens' top
    # bar does the same to the whole item.
    def test_navigation_items_change_colour_when_pressed(self):
        self.open(width=390, touch=True)
        self.assertFalse(self.page.evaluate("matchMedia('(hover: hover)').matches"))
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire_list")
            nav = self.page.get_by_role("navigation", name="主要導覽")
            other = nav.get_by_role("link", name="紀錄")
            pill = other.locator("svg")
            self.assertEqual(self.style(pill, "backgroundColor"), self.CLEAR)
            self.assertEqual(self.under(other, "active", of=pill), self.BRAND_SELECTED)
            current = nav.locator('a[aria-current="page"]')
            pill = current.locator("svg")
            self.assertEqual(self.style(pill, "backgroundImage"), self.GRADIENT)
            self.assertEqual(
                self.under(current, "active", props=("backgroundImage",), of=pill),
                self.PRESSED_GRADIENT,
            )

            self.open()
            self.page.goto(f"{self.live_server_url}/questionnaire_list")
            nav = self.page.get_by_role("navigation", name="主要導覽")
            other = nav.get_by_role("link", name="紀錄")
            self.assertEqual(self.style(other, "backgroundColor"), self.CLEAR)
            self.assertEqual(self.under(other, "hover", "active"), self.BRAND_SELECTED)
            current = nav.locator('a[aria-current="page"]')
            self.assertEqual(
                self.under(current, "hover", "active", props=("backgroundImage",)),
                self.PRESSED_GRADIENT,
            )

    # A4: a text link's underline thickens under a mouse, and a light blue shows behind its
    # words while it is pressed.
    def test_text_links_thicken_when_hovered_and_tint_when_pressed(self):
        record = self.submission(self.hhie_s, [2] * 10)
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/submission/{record.pk}")
            steps = self.main().get_by_role("heading", name="接下來建議您")
            step_link = steps.locator("xpath=following-sibling::ol[1]").get_by_role("link").first
            footer_link = self.page.get_by_role("contentinfo").get_by_role(
                "link", name="隱私權說明"
            )
            for name, link in (("next step", step_link), ("footer", footer_link)):
                with self.subTest(name):
                    link.scroll_into_view_if_needed()
                    rest = self.style(link, "textDecorationThickness")
                    self.assertNotEqual(rest, "3px")
                    self.assertEqual(self.style(link, "backgroundColor"), self.CLEAR)
                    hovered = self.under(
                        link, "hover", props=("textDecorationLine", "textDecorationThickness")
                    )
                    self.assertEqual(
                        hovered,
                        {"textDecorationLine": "underline", "textDecorationThickness": "3px"},
                    )
                    self.assertEqual(self.under(link, "hover", "active"), self.BRAND_SELECTED)

    def choices(self, scope):
        return scope.locator("div.choice-group label")

    def choose_one(self, scope):
        """Chooses the first answer not yet chosen and gives back its label."""
        choices = self.choices(scope)
        expect(choices.first).to_be_visible()
        checked = choices.evaluate_all("labels => labels.map((l) => l.control.checked)")
        choice = choices.nth(checked.index(False))
        # Where each answer is on the page, whatever the click scrolls.
        on_page = """labels => labels.map((label) => {
            const box = label.getBoundingClientRect();
            return [box.x + scrollX, box.y + scrollY, box.width, box.height];
        })"""
        boxes = choices.evaluate_all(on_page)
        choice.click()
        self.page.mouse.move(0, 0)
        expect(choice.get_by_role("radio")).to_be_checked()
        # Every answer keeps the tick's room, so choosing one moves nothing.
        self.assertEqual(choices.evaluate_all(on_page), boxes)
        return choice

    def answer_pages(self):
        """Each kind of answer choice: the React page, the web form without JavaScript, and the
        comparison pages' cards. (name, JavaScript, path, where the choices are, an opener)."""
        self.submission(self.hhie_s, [2] * 10)
        self.submission(self.hhie_s, [4] * 10)
        self.submission(self.hhie_s, [0] * 10, wearing=True)
        self.audiogram(date(2026, 9, 1))
        self.audiogram(date(2026, 9, 28))

        def open_first_pick(page):
            page.get_by_role("main").locator("details summary").first.click()

        return (
            ("React answer page", True, f"/questionnaire/{self.hhie_s.pk}", "#answer-app", None),
            ("web form", False, f"/questionnaire/{self.hhie_s.pk}", "#answer-form", None),
            ("comparison page", True, f"/comparisons/{self.hhie_s.pk}", "main", None),
            ("audiogram comparison", True, "/audiograms/compare", "main", open_first_pick),
        )

    # C1: the chosen answer is dark blue with white words and a white tick on its right; the
    # others stay white.
    def test_chosen_answers_turn_dark_blue_with_a_tick(self):
        with self.saving_artifacts():
            for name, javascript, path, where, opener in self.answer_pages():
                with self.subTest(name):
                    self.open(javascript=javascript)
                    self.page.goto(f"{self.live_server_url}{path}")
                    if opener:
                        opener(self.page)
                    scope = self.page.locator(where)
                    choice = self.choose_one(scope)
                    self.assertEqual(
                        {prop: self.style(choice, prop) for prop in ("backgroundColor", "color")},
                        {"backgroundColor": self.PRIMARY, "color": self.WHITE},
                    )
                    tick = {
                        prop: self.style(choice, prop, "::after")
                        for prop in ("content", "backgroundColor", "backgroundImage", "width")
                    }
                    self.assertNotEqual(tick["content"], "none")
                    self.assertEqual(tick["backgroundColor"], self.WHITE)
                    self.assertIn("svg", tick["backgroundImage"])
                    self.assertGreater(float(tick["width"].removesuffix("px")), 0)
                    group = choice.locator(
                        "xpath=ancestor::div[contains(@class, 'choice-group')][1]"
                    )
                    others = group.locator("label").filter(
                        has=self.page.locator("input:not(:checked)")
                    )
                    self.assertGreater(others.count(), 0)
                    for other in others.all():
                        self.assertEqual(self.style(other, "backgroundColor"), self.WHITE)
                        # Only the tick's empty room: no colour, no tick.
                        room = [
                            self.style(other, prop, "::after")
                            for prop in ("backgroundColor", "backgroundImage")
                        ]
                        self.assertEqual(room, [self.CLEAR, "none"])

    # C1: at 200% text on a 320px phone the chosen answer, tick and all, stays on the screen.
    def test_chosen_answer_fits_a_phone_at_double_text_size(self):
        with self.saving_artifacts():
            for name, javascript, path, where, opener in self.answer_pages():
                with self.subTest(name):
                    self.open(width=320, javascript=javascript)
                    self.page.goto(f"{self.live_server_url}{path}")
                    if opener:
                        opener(self.page)
                    choice = self.choose_one(self.page.locator(where))
                    self.assert_fits_a_phone_at_double_text_size(name)
                    widths = choice.evaluate("el => [el.scrollWidth, el.clientWidth]")
                    self.assertLessEqual(widths[0], widths[1])
                    box = choice.bounding_box()
                    self.assertLessEqual(box["x"] + box["width"], 320)

    # C2: an answer under the finger turns light blue with a blue edge before it is let go.
    def test_answers_turn_light_blue_while_pressed(self):
        self.open(width=390, touch=True)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire/{self.hhie_s.pk}")
            choice = self.choices(self.page.locator("#answer-app")).first
            expect(choice).to_be_visible()
            props = ("backgroundColor", "borderTopColor")
            self.assertEqual(
                {prop: self.style(choice, prop) for prop in props},
                {"backgroundColor": self.WHITE, "borderTopColor": self.GREY_EDGE},
            )
            self.assertEqual(
                self.under(choice, "active", props=props),
                {"backgroundColor": self.BRAND_SOFT, "borderTopColor": self.PRIMARY},
            )

    # D1: an open box dropdown or report fold has a thick blue edge on its left and its title bar
    # stays light blue; closed again, it is as before. A line dropdown gets neither.
    def test_open_dropdowns_get_a_blue_edge_and_keep_their_bar_tinted(self):
        self.submission(self.hhie_s, [2] * 10)
        self.open()

        def check(name, path, fold, edges):
            with self.subTest(name):
                self.page.goto(f"{self.live_server_url}{path}")
                details = self.main().locator(fold).first
                summary = details.locator("> summary")
                parts = [details.locator(edge) for edge in edges]
                closed = [self.style(part, "backgroundImage") for part in parts]
                bar = self.style(summary, "backgroundColor")
                self.assertNotIn(self.OPEN_EDGE, closed)
                place = summary.bounding_box()
                summary.click()
                self.page.mouse.move(0, 0)
                expect(details).to_have_attribute("open", "")
                self.assertEqual(summary.bounding_box(), place)
                self.assertEqual(self.style(summary, "backgroundColor"), self.BRAND_SOFT)
                for part in parts:
                    self.assertEqual(self.style(part, "backgroundImage"), self.OPEN_EDGE)
                summary.click()
                self.page.mouse.move(0, 0)
                expect(details).not_to_have_attribute("open", "")
                self.assertEqual([self.style(part, "backgroundImage") for part in parts], closed)
                self.assertEqual(self.style(summary, "backgroundColor"), bar)

        with self.saving_artifacts():
            check("box dropdown", "/add_to_home", "details", ("xpath=.", "> summary"))
            check(
                "report fold",
                "/report",
                "details:has(> summary > h3)",
                ("> summary", "> summary + *"),
            )
            with self.subTest("answer page's box"):
                # "這份問卷在問什麼？" is the box dropdown with a button, after the first page.
                self.page.goto(f"{self.live_server_url}/questionnaire/{self.hhie_s.pk}")
                self.main().get_by_role("group").get_by_role("radio").first.check()
                self.next()
                about = self.main().get_by_role("button", name="這份問卷在問什麼？")
                place = about.bounding_box()
                about.click()
                self.page.mouse.move(0, 0)
                expect(about).to_have_attribute("aria-expanded", "true")
                self.assertEqual(about.bounding_box(), place)
                self.assertEqual(self.style(about, "backgroundColor"), self.BRAND_SOFT)
                for part in (about.locator(".."), about):
                    self.assertEqual(self.style(part, "backgroundImage"), self.OPEN_EDGE)
            with self.subTest("line dropdown"):
                self.page.goto(f"{self.live_server_url}/guide/assessment")
                details = self.main().locator("details").first
                summary = details.locator("> summary")
                summary.click()
                self.page.mouse.move(0, 0)
                expect(details).to_have_attribute("open", "")
                self.assertEqual(self.style(summary, "backgroundColor"), self.CLEAR)
                for part in (details, summary):
                    self.assertEqual(self.style(part, "backgroundImage"), "none")

    # D1: what runs to the box's edges (a table here) starts clear of the blue edge, which would
    # otherwise be hidden behind a white table on screen and show through it on paper.
    def test_open_dropdown_contents_start_clear_of_the_blue_edge(self):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 9, 28))
        AudiogramPoint.objects.create(
            audiogram=audiogram, ear="right", conduction="air", frequency=1000, db=40
        )
        self.open(390)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/audiograms/{audiogram.pk}")
            details = self.main().locator("details", has_text="標記的數值")
            details.locator("> summary").click()
            expect(details).to_have_attribute("open", "")
            box, table = details.bounding_box(), details.locator("> table").bounding_box()
            edge = float(self.style(details, "borderLeftWidth").removesuffix("px")) + 5.4
            self.assertGreaterEqual(table["x"], box["x"] + edge - 0.5)


# White card rule (ADR 0022, spec #297): the pages WhiteCardRuleTest walks, one tuple per ticket
# so each ticket adds only its own pages. Each entry: (name, signed in, path, or a function that
# takes the test, makes the records the page needs and returns its path).
WHITE_CARD_PAGES_HOME_RESULT = (
    ("home, signed out", False, "/"),
    ("home, returning", True, lambda test: test.returning_home()),
    ("HHIE-S result", True, lambda test: test.result("hhie-s", 2)),
    ("HHIA-S result", True, lambda test: test.result("hhia-s", 2)),
    ("THI result", True, lambda test: test.result("thi", 4)),
)

# #300: the answering pages, and login and register, whose form card is the rule's one exception.
WHITE_CARD_PAGES_ANSWERING = (
    ("answering", True, lambda test: test.answering("hhie-s")),
    (
        "questionnaire list, suggested",
        True,
        "/questionnaire_list?concern=hearing_aid&age_group=older",
    ),
    ("questionnaire list, choose yourself", True, "/questionnaire_list?choose=self"),
    ("login", False, "/login"),
    ("register", False, "/register"),
)

# #301: the records pages, and the IOI-HA, SADL and SSQ12-TW result pages (their item cards
# are #301's).
WHITE_CARD_PAGES_RECORDS = (
    ("my records, questionnaires", True, lambda test: test.trend_records()),
    ("my records, IOI-HA", True, lambda test: test.ioi_ha_records()),
    ("my records, audiograms", True, lambda test: test.audiogram_records()),
    ("audiogram", True, lambda test: test.audiogram_detail()),
    ("new audiogram", True, "/audiograms/new"),
    ("aided and unaided comparison", True, lambda test: test.hhi_comparison()),
    ("IOI-HA result", True, lambda test: test.ioi_ha_result()),
    ("SADL result", True, lambda test: test.result("sadl", 4)),
    ("SSQ12-TW result", True, lambda test: test.result("ssq12-tw", 5)),
)

# #302: the learn pages. Signed in, each chapter that asks its stop's question ends with it.
WHITE_CARD_PAGES_LEARN = (
    ("guide, signed out", False, "/guide"),
    ("guide, with records", True, lambda test: test.guide_with_records()),
    ("guide, without an audiogram", True, lambda test: test.guide_without_audiogram()),
    *((f"guide chapter {slug}", True, f"/guide/{slug}") for slug in HearingAidGuideTest.CHAPTERS),
    *(
        (f"guide chapter {slug}, signed out", False, f"/guide/{slug}")
        for slug in HearingAidGuideTest.CHAPTERS
    ),
    ("guide chapter answered", True, lambda test: test.answered_chapter()),
    ("guide, below the threshold", True, lambda test: test.guide_below_and_not_applicable()),
    ("family guide", False, "/family"),
    ("learn", False, "/learn"),
    ("privacy", False, "/privacy"),
    ("consent", True, lambda test: test.undecided()),
)

# #303: the sharing and account pages.
WHITE_CARD_PAGES_SHARING = (
    ("health report", True, lambda test: test.report()),
    ("share settings", True, lambda test: test.share_settings()),
    ("family's shared report", False, lambda test: test.shared_report()),
    ("account settings", True, "/account"),
)


class WhiteCardRuleTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """ADR 0022: only a tappable card is a white card; everything else is a flat block."""

    fixtures = ("questions_fixture.json",)
    PAGES = (
        WHITE_CARD_PAGES_HOME_RESULT
        + WHITE_CARD_PAGES_ANSWERING
        + WHITE_CARD_PAGES_RECORDS
        + WHITE_CARD_PAGES_LEARN
        + WHITE_CARD_PAGES_SHARING
    )
    WHITE = "rgb(255, 255, 255)"
    WARM_SHADOW = "rgba(120, 90, 50, 0.08) 0px 4.5px 13.5px 0px"
    LINE = "rgb(217, 205, 185)"  # #298's pick: a thin warm line on the left
    # ADR 0024: a 並列區塊 sits on a pale beige a little deeper than the page, with deeper beige
    # lines between the parts inside it; its radius is the medium one (0.75rem at 18px).
    TINT = "rgb(236, 227, 212)"
    TINT_LINE = "rgb(201, 187, 163)"
    TINT_RADIUS = "13.5px"
    HEADING = "rgb(33, 37, 41)"
    # ADR 0025: a 段落框 is a paler beige than a 並列區塊, its title in a deeper beige bar on top.
    SECTION = "rgb(245, 239, 229)"
    SECTION_TITLE = "rgb(224, 210, 184)"
    WARM_BORDER = "rgb(239, 230, 216)"  # the pale line a 段落框 would hide
    WARM_BORDER_ON_SECTION = StyleInBrowserTest.lowest_contrast(WARM_BORDER, SECTION)
    PRINT_GREY = "rgb(173, 181, 189)"
    # #316: what is not white inside a pale blue box (119's line, 建議您下一步's icon tile and
    # reason) is this deeper light blue, so it still stands out.
    BLUE_DEEP = "rgb(214, 226, 242)"
    BLUE_SOFT = "rgb(238, 243, 250)"
    # Every colour of text in an element: its own and its descendants' that hold words directly.
    # Given true, text on a colour of its own inside the element (a filled button, a level badge,
    # a step's number circle) is left out: only what sits on the element's own background.
    TEXT_COLOURS = """(el, skipOwnBackgrounds) => [el, ...el.querySelectorAll("*")]
        .filter((node) => [...node.childNodes]
            .some((child) => child.nodeType === Node.TEXT_NODE && child.textContent.trim()))
        .filter((node) => {
            if (!skipOwnBackgrounds) return true;
            for (let at = node; at !== el; at = at.parentElement) {
                const style = getComputedStyle(at);
                if (style.backgroundColor !== "rgba(0, 0, 0, 0)"
                    || style.backgroundImage !== "none") return false;
            }
            return true;
        })
        .map((node) => getComputedStyle(node).color)"""
    PRIMARY = "rgb(31, 78, 140)"
    GRADIENT = "linear-gradient(rgb(31, 78, 140), rgb(29, 111, 153))"
    # White under a warm shadow (resting or lifted), and neither a link, inside one, nor inside
    # the login and register form card: what the rule forbids.
    WHITE_CARDS_THAT_ARE_NOT_LINKS = """() => [...document.querySelectorAll("body *")]
        .filter((el) => {
            const style = getComputedStyle(el);
            return style.backgroundColor === "rgb(255, 255, 255)"
                && style.boxShadow.includes("rgba(120, 90, 50,");
        })
        .filter((el) => !el.closest("a, .auth-card"))
        .map((el) => el.outerHTML.slice(0, 120))"""
    # Spec #297 acceptance 12: a block in main that runs past the screen's right edge, or hides
    # part of what it holds sideways. The page's own width misses both when a block clips.
    # Visually hidden text (1px wide on purpose) is left out.
    CUT_OFF = """() => [...document.querySelectorAll("main *")]
        .filter((el) => el.clientWidth > 1 || getComputedStyle(el).display === "inline")
        .filter((el) => el.getBoundingClientRect().right > document.documentElement.clientWidth
            || (getComputedStyle(el).overflowX !== "visible" && el.scrollWidth > el.clientWidth))
        .map((el) => el.outerHTML.slice(0, 120))"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        call_command("seed_questionnaires", verbosity=0)
        self.user = consented_user(username="white_card_e2e")
        self.client.force_login(self.user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, signed_in, width=1024, javascript=True):
        self.context = self.browser.new_context(
            viewport={"width": width, "height": 900},
            reduced_motion="reduce",
            java_script_enabled=javascript,
        )
        if signed_in:
            self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def answered(self, code, score):
        """A record of code with every item scored score."""
        questionnaire = Questionnaire.objects.get(code=code)
        record = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=question, score=score)
            for question in questionnaire.questions.all()
        )
        return record

    def result(self, code, score):
        return f"/submission/{self.answered(code, score).pk}"

    def returning_home(self):
        self.answered("hhie-s", 2)
        return "/"

    # #302: the learn pages' records.
    def guide_with_records(self):
        """My guide with all its parts: a life impact result and 55 dB in both ears (45.0%),
        so 記錄聽力圖 is a done stop above 您在這裡."""
        self.answered("hhie-s", 2)
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 1))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=55)
            for ear in ("right", "left")
            for f in (500, 1000, 2000, 4000)
        )
        return "/guide"

    def guide_without_audiogram(self):
        """My guide with a life impact result and no audiogram: 聽力圖 asks for one."""
        self.answered("hhie-s", 2)
        return "/guide"

    def guide_below_and_not_applicable(self):
        """My guide whose route has every kind of stop (#321): 已完成 (記錄聽力圖), 您在這裡,
        估算未達門檻 (30 and 20 dB, about 0%) and 不適用 (bought paying otherwise: form 25 and
        the payout). After the chapter answered (in the white card rule's pages), its answer is
        cleared and this audiogram is the newer one."""
        self.answered("hhie-s", 2)
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 2))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=db)
            for ear, db in (("right", 30), ("left", 20))
            for f in (500, 1000, 2000, 4000)
        )
        AidAndSubsidy.objects.update_or_create(
            user=self.user, defaults={"certificate": "", "subsidy": "other"}
        )
        return "/guide"

    def answered_chapter(self):
        """The assessment chapter after its question: 已記下 and the button back to the route."""
        AidAndSubsidy.objects.create(user=self.user, certificate="yes")
        return "/guide/assessment"

    def undecided(self):
        """The consent page, shown only to someone who has not agreed yet."""
        self.user.consents.all().delete()
        return "/consent"

    def assert_titled(self, heading):
        """#298's pick for an article's parts: framed by the title's brand-blue bar only."""
        self.assertEqual(self.style(heading, "borderLeftColor"), self.PRIMARY)
        self.assertEqual(self.style(heading, "borderLeftStyle"), "solid")

    # #303: the report with a questionnaire's part and the audiogram, the share page with a live
    # link (all three steps filled in), and the family's copy through that link.
    def report(self):
        self.answered("hhie-s", 2)
        self.audiogram()
        return "/report"

    def share_settings(self):
        self.report()
        ReportShare.objects.create(user=self.user)
        return "/share"

    def shared_report(self):
        self.report()
        return f"/shared/{ReportShare.objects.create(user=self.user).token}/report"

    # #300's helpers.
    def answering(self, code):
        return f"/questionnaire/{Questionnaire.objects.get(code=code).pk}"

    # #301: the records the records pages show.
    def trend_records(self):
        self.answered("hhie-s", 2)
        self.answered("hhie-s", 4)
        return "/my_hearing?questionnaire=hhie-s"

    def ioi_ha(self):
        """An IOI-HA record below the norm on every item, grouped by an unaided HHIE-S."""
        questionnaire = Questionnaire.objects.get(code="ioi-ha")
        record = Submission.objects.create(
            user=self.user,
            questionnaire=questionnaire,
            norm_group=NormGroup.MILD_MODERATE,
            norm_basis=self.answered("hhie-s", 2),
            wearing_hearing_aid=True,
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=question, score=1)
            for question in questionnaire.questions.all()
        )
        return record

    def ioi_ha_result(self):
        return f"/submission/{self.ioi_ha().pk}"

    def ioi_ha_records(self):
        self.ioi_ha()
        return "/my_hearing?questionnaire=ioi-ha"

    def audiogram(self):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 9, 28))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=40)
            for ear in ("right", "left")
            for f in (500, 1000, 2000, 4000)
        )
        return audiogram

    def audiogram_records(self):
        self.audiogram()
        return "/audiograms"

    def audiogram_detail(self):
        return f"/audiograms/{self.audiogram().pk}"

    def hhi_comparison(self):
        """The comparison page with a pair on screen and another kept in the report."""
        kept, shown = self.answered("hhie-s", 2), self.answered("hhie-s", 4)
        aided = self.answered("hhie-s", 0)
        Submission.objects.filter(pk=aided.pk).update(wearing_hearing_aid=True)
        ReportComparison.objects.create(
            user=self.user, questionnaire=kept.questionnaire, unaided=kept, aided=aided
        )
        return (
            f"/comparisons/{kept.questionnaire_id}"
            f"?unaided={shown.pk}&aided={aided.pk}&action=preview"
        )

    def visit(self, signed_in, path, width=1024, javascript=True):
        self.open(signed_in, width, javascript)
        self.page.goto(f"{self.live_server_url}{path(self) if callable(path) else path}")

    def style(self, locator, prop):
        return locator.evaluate("(el, prop) => getComputedStyle(el)[prop]", prop)

    def assert_flat(self, block):
        expect(block).to_be_visible()
        self.assertEqual(self.style(block, "backgroundColor"), "rgba(0, 0, 0, 0)")
        self.assertEqual(self.style(block, "boxShadow"), "none")

    def assert_every_side(self, element, **expected):
        """All four of an element's borders have each value given, as border{Side}{name}."""
        for side in ("Top", "Right", "Bottom", "Left"):
            for name, value in expected.items():
                self.assertEqual(self.style(element, f"border{side}{name}"), value, side)

    def assert_fits_uncut(self, where, width=320):
        """Spec #297 acceptance 12: at 200% on a phone, no sideways scrolling and nothing cut."""
        self.assert_fits_a_phone_at_double_text_size(where, width)
        self.assertEqual(self.page.evaluate(self.CUT_OFF), [], where)

    def assert_white_card(self, card):
        """A tappable card (ADR 0022): white under the warm shadow."""
        self.assertEqual(self.style(card, "backgroundColor"), self.WHITE)
        self.assertEqual(self.style(card, "boxShadow"), self.WARM_SHADOW)

    def assert_lined(self, block):
        """#298's pick for a list of explanations: flat, with only a thin warm line on the left."""
        self.assert_flat(block)
        self.assertEqual(self.style(block, "borderLeftColor"), self.LINE)
        self.assertEqual(self.style(block, "borderTopWidth"), "0px")

    def assert_tinted(self, block, top_line=None):
        """A 並列區塊 (ADR 0024): pale beige, no shadow, no border, the medium radius. Given a
        top_line colour (#311: an ear's result), a line in that colour on top and no other border,
        its lower corners rounded."""
        expect(block).to_be_visible()
        self.assertEqual(self.style(block, "backgroundColor"), self.TINT)
        self.assertEqual(self.style(block, "boxShadow"), "none")
        if top_line is None:
            self.assertEqual(self.style(block, "borderWidth"), "0px")
            self.assertEqual(self.style(block, "borderRadius"), self.TINT_RADIUS)
            return
        self.assertEqual(self.style(block, "borderTopColor"), top_line)
        self.assertEqual(self.style(block, "borderTopStyle"), "solid")
        self.assertNotEqual(self.style(block, "borderTopWidth"), "0px")
        for side in ("Right", "Bottom", "Left"):
            self.assertEqual(self.style(block, f"border{side}Width"), "0px")
        self.assertEqual(self.style(block, "borderBottomLeftRadius"), self.TINT_RADIUS)

    def assert_block_title(self, title, ratio=1.35):
        """ADR 0024: a 並列區塊's title is 1.35 times the body text and a bold subhead in it 1.2
        times, both bold in the heading colour (not link blue), without the brand-blue bar of a
        page's section titles. Returns its size in px."""
        body = float(self.style(self.page.locator("body"), "fontSize").removesuffix("px"))
        size = float(self.style(title, "fontSize").removesuffix("px"))
        self.assertAlmostEqual(size / body, ratio, places=2)
        self.assertEqual(self.style(title, "color"), self.HEADING)
        self.assertEqual(self.style(title, "fontWeight"), "700")
        self.assertEqual(self.style(title, "borderLeftWidth"), "0px")
        return size

    def assert_lines_between(self, parts):
        """Parts inside a 並列區塊 (ADR 0024): a deeper beige line between each two, none on
        their left."""
        parts = parts.all()
        self.assertGreater(len(parts), 1)
        self.assertEqual(self.style(parts[0], "borderTopWidth"), "0px")
        # Spec #308 acceptance 2: easier to see on the beige than #298's thin warm line would be.
        old_line = StyleInBrowserTest.lowest_contrast(self.LINE, self.TINT)
        for part in parts[1:]:
            with self.subTest(part=part.inner_text()[:10]):
                line = self.style(part, "borderTopColor")
                self.assertGreater(StyleInBrowserTest.lowest_contrast(line, self.TINT), old_line)
                self.assertEqual(line, self.TINT_LINE)
                self.assertEqual(self.style(part, "borderTopStyle"), "solid")
                self.assertNotEqual(self.style(part, "borderTopWidth"), "0px")
        for part in parts:
            self.assertEqual(self.style(part, "borderLeftWidth"), "0px")

    def assert_readable_on_tint(self, block, skip_own_backgrounds=False):
        """Spec #308 acceptance 2: every text and link colour in a 並列區塊 at least 4.5:1 on the
        beige. With skip_own_backgrounds (a block holding buttons or badges), text on a colour of
        its own inside the block is left out: only what sits on the beige is measured."""
        colours = set(block.evaluate(self.TEXT_COLOURS, skip_own_backgrounds))
        self.assertTrue(colours)
        for colour in colours:
            with self.subTest(colour=colour):
                self.assertGreaterEqual(StyleInBrowserTest.lowest_contrast(colour, self.TINT), 4.5)

    def assert_section_box(self, part, words_on_box=True):
        """A 段落框 (ADR 0025): the pale beige, no shadow and no border; its title in the deeper
        beige bar across its top, a block title (1.35 times the body text, bold, the heading
        colour, no brand-blue bar). The words on each beige keep 4.5:1 or more. Without
        words_on_box (the route, its words all on its stops' 並列區塊) none need sit on the box
        itself. Returns the title."""
        expect(part).to_be_visible()
        self.assertEqual(self.style(part, "backgroundColor"), self.SECTION)
        self.assertEqual(self.style(part, "boxShadow"), "none")
        self.assertEqual(self.style(part, "borderWidth"), "0px")
        title = part.get_by_role("heading").first
        self.assertEqual(self.style(title, "backgroundColor"), self.SECTION_TITLE)
        self.assert_block_title(title)
        box, bar = part.bounding_box(), title.bounding_box()
        for edge in ("x", "y", "width"):
            self.assertAlmostEqual(bar[edge], box[edge], delta=0.5, msg=edge)
        self.assertGreaterEqual(
            StyleInBrowserTest.lowest_contrast(self.style(title, "color"), self.SECTION_TITLE), 4.5
        )
        colours = set(part.evaluate(self.TEXT_COLOURS, True))
        if words_on_box:
            self.assertTrue(colours)
        for colour in colours:
            with self.subTest(colour=colour):
                self.assertGreaterEqual(
                    StyleInBrowserTest.lowest_contrast(colour, self.SECTION), 4.5
                )
        return title

    # The backgrounds of an element and everything it sits in, up to the page.
    BACKGROUNDS_ABOVE = """(el) => {
        const found = [];
        for (let at = el; at; at = at.parentElement) {
            found.push(getComputedStyle(at).backgroundColor);
        }
        return found;
    }"""

    def assert_outside_section_boxes(self, element):
        """Shown, and not on a 段落框's beige or its title bar's."""
        expect(element).to_be_visible()
        backgrounds = element.evaluate(self.BACKGROUNDS_ABOVE)
        self.assertNotIn(self.SECTION, backgrounds)
        self.assertNotIn(self.SECTION_TITLE, backgrounds)

    def assert_printed_section_box(self, part):
        """A 段落框 on paper (#318 acceptance 12): no beige, a thin grey frame, its title bold
        above a grey line."""
        title = part.get_by_role("heading").first
        with self.subTest(part=title.inner_text()):
            self.assertEqual(self.style(part, "backgroundColor"), "rgba(0, 0, 0, 0)")
            self.assert_every_side(part, Width="1px", Style="solid", Color=self.PRINT_GREY)
            self.assertEqual(self.style(title, "backgroundColor"), "rgba(0, 0, 0, 0)")
            self.assertEqual(self.style(title, "fontWeight"), "700")
            self.assertEqual(self.style(title, "borderBottomWidth"), "1px")
            self.assertEqual(self.style(title, "borderBottomStyle"), "solid")
            self.assertEqual(self.style(title, "borderBottomColor"), self.PRINT_GREY)

    # Spec #297 acceptance 1: every white card under a warm shadow is a link.
    def test_every_white_card_is_a_link(self):
        with self.saving_artifacts():
            for name, signed_in, path in self.PAGES:
                with self.subTest(page=name):
                    self.visit(signed_in, path)
                    self.assertEqual(self.page.evaluate(self.WHITE_CARDS_THAT_ARE_NOT_LINKS), [])

    # Spec #308 acceptance 12 (#316): white means tappable. "White" is what a person sees as a
    # white surface: an element's own background is opaque white (rgb(255, 255, 255), with or
    # without a shadow), it is on screen, and nothing above it fades it (the login banner's bars
    # are white at 35% opacity: pale blue on the blue banner, not white). Every such element must
    # be, or sit inside, one of these:
    WHITE_ALLOWED = ", ".join(
        (
            "a",  # a link, including every white card
            "button",  # a button, including an outline button given a white fill on a tint (#311)
            "input, select, textarea",  # a box to type in or a list to pick from
            "summary",  # a dropdown's bar (看完整建議, 逐題回答, a report's questionnaire)
            "label:has(input)",  # an answer choice: the label around its radio button
            "table",  # a table (spec #308: tables are the rule's exception)
            ".chart-canvas, .audiogram-chart, .ioi-chart",  # a chart's drawing area (#301)
            ".auth-card",  # the login and register form card (#300)
            # The site's frame, not a block of content: the header and its menu bar are white
            # since the brand refresh (ADR 0012).
            ".site-header, .site-nav",
            # Register's banner: the done step's bar is a thin progress line on the blue, not a
            # surface.
            ".auth-hero .step-progress-segment",
        )
    )
    # A dropdown (details) is allowed as a box only: what opens inside it is checked like the rest,
    # so every dropdown is opened first (a report's questionnaires fold into dropdowns, #314).
    WHITE_BUT_NOT_TAPPABLE = """(allowed) => {
        document.querySelectorAll("details").forEach((box) => { box.open = true; });
        const faded = (el) => el
            && (getComputedStyle(el).opacity !== "1" || faded(el.parentElement));
        return [...document.querySelectorAll("body *")]
            .filter((el) => getComputedStyle(el).backgroundColor === "rgb(255, 255, 255)")
            .filter((el) => el.checkVisibility() && !faded(el))
            .filter((el) => !el.matches("details") && !el.closest(allowed))
            .map((el) => `${el.tagName.toLowerCase()}.${el.getAttribute("class")} `
                + el.textContent.trim().replace(/\\s+/g, " ").slice(0, 30));
    }"""
    # The answering page of each questionnaire, each with its own intro (spec #308 acceptance 10).
    WHITE_ANSWERING_PAGES = tuple(
        (f"answering {code}", True, lambda test, code=code: test.answering(code))
        for code in ("hhia-s", "thi", "ssq12-tw", "sadl", "ioi-ha")
    )
    # What React draws after the page loads; wait for it so its white elements are counted too.
    DRAWN_LATER = (
        ("#answer-app", "#answer-app fieldset"),
        ("#audiogram-app", "#audiogram-app > *"),
        ("#trend-plot", "#trend-plot .recharts-wrapper"),
        ("#audiogram-chart", "#audiogram-chart svg"),
    )

    def white_but_not_tappable(self):
        for mount, drawn in self.DRAWN_LATER:
            if self.page.locator(mount).count():
                self.page.locator(drawn).first.wait_for(state="attached")
        return self.page.evaluate(self.WHITE_BUT_NOT_TAPPABLE, self.WHITE_ALLOWED)

    def test_every_white_element_can_be_tapped(self):
        with self.saving_artifacts():
            for name, signed_in, path in self.PAGES + self.WHITE_ANSWERING_PAGES:
                with self.subTest(page=name):
                    self.visit(signed_in, path)
                    self.assertEqual(self.white_but_not_tappable(), [])

    # #299: the signed-out home's four steps, result example and audiologist line are flat.
    def test_first_visit_home_blocks_are_flat(self):
        with self.saving_artifacts():
            self.visit(False, "/")
            for text in ("建立帳號", "回答問題", "馬上看到結果", "隔一段時間再做一次"):
                with self.subTest(step=text):
                    self.assert_lined(self.main().get_by_role("listitem").filter(has_text=text))
            self.assert_flat(self.main().get_by_role("figure"))
            self.assert_flat(self.main().locator("p").filter(has_text="設計與審定"))

    # #299: 歡迎回來 is flat with its two buttons as before; 您還可以's cards stay white cards.
    # Option D (ADR 0026): inside it, a blue greeting band, still not a white card.
    def test_returning_home_welcome_is_flat_and_more_cards_stay_white(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.returning_home())
            welcome = (
                self.main()
                .locator("section")
                .filter(has=self.page.get_by_role("heading", name="歡迎回來"))
            )
            self.assert_flat(welcome)
            band = welcome.locator(".welcome-band")
            # The brand gradient under the two faint rings.
            self.assertTrue(self.style(band, "backgroundImage").endswith(self.GRADIENT))
            self.assertEqual(self.style(band, "boxShadow"), "none")
            records = welcome.get_by_role("link", name="看我的紀錄與趨勢", exact=True)
            self.assertEqual(self.style(records, "backgroundImage"), self.GRADIENT)
            again = welcome.get_by_role("link", name="再做一次", exact=True)
            self.assertEqual(self.style(again, "borderTopColor"), self.PRIMARY)
            # ADR 0026: side by side on a wide screen.
            self.assertEqual(records.bounding_box()["y"], again.bounding_box()["y"])
            cards = self.page.get_by_role("region", name="您還可以").locator("a.link-card")
            self.assertGreater(cards.count(), 0)
            for card in cards.all():
                with self.subTest(card=card.inner_text()):
                    self.assert_white_card(card)

    # #309: advice 1-3 sit in one 並列區塊 with a line between each, where each had a thin line on
    # its left; the links in it still look like links and the cards below stay white cards.
    # THI's support message above them keeps its thin line.
    def test_result_advice_is_one_tinted_block_with_links_that_look_like_links(self):
        links_seen = 0
        with self.saving_artifacts():
            # HHIE-S and HHIA-S at 20 (mild to moderate), THI at full marks: the pages with advice.
            for name, signed_in, path in WHITE_CARD_PAGES_HOME_RESULT[2:]:
                with self.subTest(page=name):
                    self.visit(signed_in, path)
                    advice = self.main().locator("ol.next-steps")
                    self.assert_tinted(advice)
                    self.assert_readable_on_tint(advice)
                    # Three steps, four on THI's page: all in the one block.
                    steps = advice.locator("> li")
                    self.assert_lines_between(steps)
                    for step in steps.all():
                        self.assertEqual(self.style(step, "backgroundColor"), "rgba(0, 0, 0, 0)")
                        self.assertEqual(self.style(step, "boxShadow"), "none")
                    links = advice.get_by_role("link")
                    links_seen += links.count()
                    for link in links.all():
                        with self.subTest(link=link.inner_text()):
                            self.assertEqual(self.style(link, "color"), self.PRIMARY)
                            self.assertEqual(self.style(link, "textDecorationLine"), "underline")
                    cards = self.main().locator(".result-actions a.link-card")
                    self.assertGreater(cards.count(), 0)
                    for card in cards.all():
                        with self.subTest(card=card.inner_text()[:10]):
                            self.assert_white_card(card)
            self.assert_lined(self.main().get_by_text(THI_SUPPORT_MESSAGE, exact=True))
        self.assertGreater(links_seen, 0)

    # #316: the 建議您下一步 box (returning home and every result page) has no white left: its icon
    # tile and its 因為 line are a light blue deeper than the box; only its button is tappable.
    def test_next_step_box_is_blue_with_only_its_button_to_tap(self):
        with self.saving_artifacts():
            for name, signed_in, path in (
                *WHITE_CARD_PAGES_HOME_RESULT[1:],
                ("SADL result", True, lambda test: test.result("sadl", 4)),
            ):
                with self.subTest(page=name):
                    self.visit(signed_in, path)
                    box = self.main().locator(".next-step")
                    self.assertEqual(self.style(box, "backgroundColor"), self.BLUE_SOFT)
                    for part in (".action-card-icon", ".next-step-because"):
                        self.assertEqual(
                            self.style(box.locator(part), "backgroundColor"), self.BLUE_DEEP
                        )
                    because = box.get_by_text("因為：", exact=False)
                    for colour in set(because.evaluate(self.TEXT_COLOURS)):
                        with self.subTest(colour=colour):
                            self.assertGreaterEqual(
                                StyleInBrowserTest.lowest_contrast(colour, self.BLUE_DEEP), 4.5
                            )
                    stroke = self.style(box.locator(".action-card-icon svg"), "stroke")
                    self.assertGreaterEqual(
                        StyleInBrowserTest.lowest_contrast(stroke, self.BLUE_DEEP), 4.5
                    )
                    self.assertEqual(box.get_by_role("link").count(), 1)
                    self.assertEqual(
                        self.style(box.get_by_role("link"), "backgroundImage"), self.GRADIENT
                    )

    # #299: no sideways scrolling or cut text on a phone at 200% text, on both homes and every
    # questionnaire's result page.
    # ADR 0026: at double text size on a phone the elder gives way to the title.
    def test_welcome_back_elder_gives_way_at_double_text_size(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.returning_home(), width=320)
            elder = self.main().locator(".welcome-band .home-illustration")
            expect(elder).to_be_visible()
            self.assert_fits_uncut("home, returning")
            expect(elder).to_be_hidden()

    def test_home_and_result_pages_fit_a_phone_at_double_text_size(self):
        results = tuple(page for page in WHITE_CARD_PAGES_RECORDS if page[0].endswith(" result"))
        with self.saving_artifacts():
            for name, signed_in, path in WHITE_CARD_PAGES_HOME_RESULT + results:
                with self.subTest(page=name):
                    self.visit(signed_in, path, width=320)
                    self.assert_fits_uncut(name)

    # #320 (#318 acceptance 2, 6, 7): my guide's status parts are 段落框, their bars (with the
    # normal limit's and the threshold's lines), links and 怎麼算的 dropdown as before; 看我的路線
    # is outside them. #321 (#318 acceptance 4): the route is one 段落框 too.
    def test_guide_parts_and_route_are_section_boxes_with_their_links(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.guide_with_records())
            for name, link, scale in (
                ("問卷結果", None, None),
                ("要不要找聽力師評估", "去之前要準備什麼", "正常上限 25"),
                ("身障鑑定門檻", "找鑑定醫院", "門檻 45%"),
            ):
                with self.subTest(part=name):
                    part = self.main().get_by_role("region", name=name)
                    title = self.assert_section_box(part)
                    expect(title).to_have_text(name)
                    if link:
                        expect(part.get_by_role("link", name=link, exact=True)).to_be_visible()
                    if scale:
                        expect(part.get_by_text(scale, exact=True)).to_be_visible()
                        for line in part.locator(".meter-line").all():
                            expect(line).to_be_visible()
                            self.assertEqual(self.style(line, "backgroundColor"), self.HEADING)
            threshold = self.main().get_by_role("region", name="身障鑑定門檻")
            worked = threshold.get_by_text("怎麼算的", exact=True)
            self.assertEqual(self.style(worked, "color"), self.PRIMARY)
            worked.click()
            expect(threshold.get_by_text("3. 身障鑑定門檻是 45.0%。")).to_be_visible()
            self.assert_outside_section_boxes(
                self.main().get_by_role("link", name="看我的路線", exact=True)
            )
            self.assert_route_box()
            done = self.main().locator(".route-stop").filter(has_text="已完成").first
            expect(done.get_by_role("link").first).to_be_visible()

    # #321 (#318 acceptance 4): the 選配路線 is one 段落框 titled in its bar. Its stops have no
    # frame and no fill of their own but the 目前這一站's pale blue box with its blue frame and
    # filled blue number; the other numbers are pale blue circles (#316), a 不適用 one grey. The
    # joining lines are the deeper beige, easier to see than the pale line they had, and no mark
    # is white (white is what can be tapped), each mark's words 4.5:1 or more on it.
    PALE_GREY = "rgb(241, 243, 245)"
    GREY_LINE = "rgb(206, 212, 218)"
    JOINING_LINE = "(el) => getComputedStyle(el, '::after').backgroundColor"

    def assert_route_box(self):
        route = self.main().get_by_role("region", name="選配與補助，一步一步看")
        expect(self.assert_section_box(route, words_on_box=False)).to_have_text(
            "選配與補助，一步一步看"
        )
        stops = route.locator(".route-stop")
        self.assertEqual(stops.count(), 9)
        # Acceptance: each stop other than the 目前這一站 sits on a 並列區塊's beige, no frame.
        for stop in route.locator(".route-stop:not([aria-current])").all():
            with self.subTest(stop=stop.get_attribute("data-stop")):
                box = stop.locator(".route-box")
                self.assert_tinted(box)
                self.assert_readable_on_tint(box, skip_own_backgrounds=True)
        here = route.locator(".route-stop[aria-current=step]")
        if here.count():
            box = here.locator(".route-box")
            self.assertEqual(self.style(box, "backgroundColor"), self.BLUE_SOFT)
            self.assert_every_side(box, Color=self.PRIMARY, Style="solid")
            self.assertEqual(self.style(box, "boxShadow"), "none")
            number = here.locator(".route-number")
            self.assertEqual(self.style(number, "backgroundColor"), self.PRIMARY)
        # #316: a stop's number is a pale blue circle with a blue number, like the chapters'
        # numbered steps, not white.
        numbers = route.locator(".route-stop:not([aria-current], .is-na) .route-number")
        self.assertGreater(numbers.count(), 1)
        for number in numbers.all():
            with self.subTest(stop=number.inner_text()):
                self.assertEqual(self.style(number, "backgroundColor"), self.BLUE_SOFT)
                self.assertEqual(self.style(number, "color"), self.PRIMARY)
                self.assertEqual(self.style(number, "borderTopColor"), self.PRIMARY)
        self.assertGreaterEqual(
            StyleInBrowserTest.lowest_contrast(self.PRIMARY, self.BLUE_SOFT), 4.5
        )
        for number in route.locator(".route-stop.is-na .route-number").all():
            with self.subTest(stop=number.inner_text()):
                self.assertEqual(self.style(number, "backgroundColor"), self.PALE_GREY)
                self.assertEqual(self.style(number, "borderTopColor"), self.GREY_LINE)
        for stop in stops.all()[:-1]:
            with self.subTest(line_below=stop.get_attribute("data-stop")):
                line = stop.evaluate(self.JOINING_LINE)
                self.assertEqual(line, self.TINT_LINE)
                self.assertGreater(
                    StyleInBrowserTest.lowest_contrast(line, self.SECTION),
                    self.WARM_BORDER_ON_SECTION,
                )
        for mark in route.locator(".route-mark").all():
            with self.subTest(mark=mark.inner_text()):
                background = self.style(mark, "backgroundColor")
                self.assertNotEqual(background, self.WHITE)
                self.assertNotEqual(background, "rgba(0, 0, 0, 0)")
                self.assertGreaterEqual(
                    StyleInBrowserTest.lowest_contrast(self.style(mark, "color"), background), 4.5
                )
        return route

    # #321 (#318 acceptance 3, 4, 13): signed out (no stop marked) and on a route with every
    # kind of stop, the route is the same 段落框, the 目前這一站's button in it as before; on a
    # phone at 200% text nothing scrolls sideways or is cut.
    def test_guide_route_is_one_section_box_signed_out_and_with_every_kind_of_stop(self):
        with self.saving_artifacts():
            for name, signed_in, path in (
                ("signed out", False, "/guide"),
                ("below the threshold", True, lambda test: test.guide_below_and_not_applicable()),
            ):
                with self.subTest(page=name):
                    self.visit(signed_in, path)
                    route = self.assert_route_box()
                    if signed_in:
                        for kind in (".is-below", ".is-na"):
                            expect(route.locator(f".route-stop{kind}").first).to_be_visible()
                        button = route.get_by_role("link", name="去之前要準備什麼", exact=True)
                        self.assertEqual(self.style(button, "backgroundImage"), self.GRADIENT)
                    else:
                        expect(route.locator(".route-mark")).to_have_count(0)
                    self.visit(signed_in, path, width=320)
                    self.assert_fits_uncut(name)

    # #319 (#318 acceptance 1, 5, 6, 7): every titled part of every chapter, signed in or not, is a
    # 段落框 with its links in it; outside the boxes only the chapter's title (still blue-barred),
    # its lead and a tip of its own. The question at the foot and its answered form are 段落框
    # with their buttons.
    def test_guide_chapter_parts_are_section_boxes_with_their_links(self):
        linked = set()
        with self.saving_artifacts():
            for slug in HearingAidGuideTest.CHAPTERS:
                for signed_in in (True, False):
                    with self.subTest(chapter=slug, signed_in=signed_in):
                        self.visit(signed_in, f"/guide/{slug}")
                        article = self.main().get_by_role("article")
                        self.assert_titled(article.get_by_role("heading", level=1))
                        parts = article.locator(":scope > section")
                        self.assertGreater(parts.count(), 0)
                        for part in parts.all():
                            self.assert_section_box(part)
                        outside = article.locator(":scope > :not(section)")
                        for each in outside.all():
                            with self.subTest(outside=each.inner_text()[:10]):
                                # #367: form 9's 本頁段落 jump stays outside the boxes too.
                                tag = each.evaluate("el => el.tagName")
                                self.assertIn(tag, ("H1", "P", "NAV"))
                                self.assertNotEqual(
                                    self.style(each, "backgroundColor"), self.SECTION
                                )
                        self.assert_flat(self.main().locator("footer"))
                        if parts.get_by_role("link").count():
                            linked.add(slug)
            # The chapters with links in their parts (the others link only in their sources);
            # #367 links the report from before-you-go's things to bring.
            self.assertEqual(
                linked,
                {"before-you-go", "form-9", "types-and-prices", "after-fitting", "form-25"},
            )
            self.visit(True, "/guide/assessment")
            question = self.main().get_by_role("region", name="看完了嗎？")
            self.assert_section_box(question)
            for answer in ("有", "還沒有，正在申請鑑定", "沒有，不申請身障補助"):
                with self.subTest(answer=answer):
                    expect(question.get_by_role("button", name=answer, exact=True)).to_be_visible()
            self.visit(True, lambda test: test.answered_chapter())
            answered = self.main().get_by_role("region", name="已記下：有身障證明")
            self.assert_section_box(answered)
            expect(
                answered.get_by_role("link", name="修改身障鑑定與鑑定醫院的回答")
            ).to_be_visible()
            again = answered.get_by_role("link", name="回選配路線看下一站", exact=True)
            self.assertEqual(self.style(again, "backgroundImage"), self.GRADIENT)

    # #319: the boxes stand apart; inside them the facts' labels, steps' titles and lists' leads
    # are still larger bold subheads, and the lines between labelled facts (and between a
    # county's hospitals) are the deeper beige, easier to see than the pale line they had.
    GUIDE_SUBHEADS = (
        ("before-you-go", ("適不適合我",)),
        ("assessment", ("雙耳整體障礙比率", "到公所申請")),
        ("form-9", ("補助上限，依助聽器等級", "做評估，拿到九號表", "縣市補助")),
        ("types-and-prices", ("耳掛型",)),
        ("after-fitting", ("剛開始不習慣是正常的",)),
        ("form-25", ("誰要做",)),
    )

    def test_guide_chapter_boxes_stand_apart_with_subheads_and_visible_lines(self):
        with self.saving_artifacts():
            for slug, subheads in self.GUIDE_SUBHEADS:
                with self.subTest(chapter=slug):
                    self.visit(False, f"/guide/{slug}?county={HearingAidGuideTest.COUNTY}")
                    article = self.main().get_by_role("article")
                    parts = article.locator(":scope > section").all()
                    boxes = [part.bounding_box() for part in parts]
                    for above, below in pairwise(boxes):
                        self.assertGreaterEqual(below["y"] - (above["y"] + above["height"]), 18)
                    body = float(self.style(article.locator("p").first, "fontSize")[:-2])
                    for text in subheads:
                        with self.subTest(subhead=text):
                            subhead = article.get_by_text(text, exact=True)
                            self.assertGreaterEqual(
                                float(self.style(subhead, "fontSize")[:-2]), 1.2 * body - 0.01
                            )
                            self.assertEqual(self.style(subhead, "color"), self.HEADING)
                            self.assertEqual(self.style(subhead, "fontWeight"), "700")
                    lines = article.locator(".key-list > div + div, #hospital-list > li")
                    for line in lines.all():
                        with self.subTest(line=line.inner_text()[:10]):
                            side = "Bottom" if line.evaluate("el => el.tagName") == "LI" else "Top"
                            colour = self.style(line, f"border{side}Color")
                            self.assertEqual(colour, self.TINT_LINE)
                            self.assertGreater(
                                StyleInBrowserTest.lowest_contrast(colour, self.SECTION),
                                self.WARM_BORDER_ON_SECTION,
                            )

    # #319 (#318 acceptance 12): on paper no beige: each 段落框 is a thin grey frame, its title
    # bold above a grey line; the chapter's title, lead and tip print as before.
    def test_printed_guide_chapter_boxes_are_grey_frames(self):
        with self.saving_artifacts():
            for slug in HearingAidGuideTest.CHAPTERS:
                with self.subTest(chapter=slug):
                    self.visit(True, f"/guide/{slug}")
                    self.page.emulate_media(media="print")
                    parts = self.main().locator("article > section, #stop-question")
                    self.assertGreater(parts.count(), 1)
                    for part in parts.all():
                        self.assert_printed_section_box(part)
                    self.assert_titled(self.main().get_by_role("heading", level=1))

    # #320, #321 (#318 acceptance 12): my guide's status parts and its route print as grey
    # frames too, with and without an audiogram.
    def test_printed_guide_status_boxes_are_grey_frames(self):
        with self.saving_artifacts():
            # Without an audiogram first: the second visit adds one.
            for path, names in (
                (
                    lambda test: test.guide_without_audiogram(),
                    ("問卷結果", "聽力圖", "選配與補助，一步一步看"),
                ),
                (
                    lambda test: test.guide_with_records(),
                    ("問卷結果", "要不要找聽力師評估", "身障鑑定門檻", "選配與補助，一步一步看"),
                ),
            ):
                self.visit(True, path)
                self.page.emulate_media(media="print")
                for name in names:
                    self.assert_printed_section_box(self.main().get_by_role("region", name=name))
                self.assert_titled(self.main().get_by_role("heading", level=1))

    # #320 (#318 acceptance 3): before any record, and with a questionnaire but no audiogram, the
    # note and buttons on top are outside the boxes; 聽力圖, with its button, is a 段落框.
    def test_guide_note_and_buttons_stay_outside_and_the_audiogram_part_is_boxed(self):
        with self.saving_artifacts():
            self.visit(False, "/guide")
            self.assert_outside_section_boxes(self.main().get_by_text("登入後，這裡會依您的問卷"))
            self.assert_outside_section_boxes(
                self.main().get_by_role("link", name="登入", exact=True)
            )
            self.visit(True, "/guide")
            self.assert_outside_section_boxes(self.main().get_by_text("依您在 HearWell 最新的紀錄"))
            for button in ("開始篩檢", "記錄醫院的聽力圖"):
                with self.subTest(button=button):
                    self.assert_outside_section_boxes(
                        self.main().get_by_role("link", name=button, exact=True).first
                    )
            self.visit(True, lambda test: test.guide_without_audiogram())
            self.assert_outside_section_boxes(self.main().get_by_text("依您在 HearWell 最新的紀錄"))
            self.assert_section_box(self.main().get_by_role("region", name="問卷結果"))
            audiogram = self.main().get_by_role("region", name="聽力圖")
            expect(self.assert_section_box(audiogram)).to_have_text("聽力圖")
            record = audiogram.get_by_role("link", name="記錄醫院的聽力圖", exact=True)
            self.assertEqual(self.style(record, "backgroundImage"), self.GRADIENT)

    # #319, #320, #321 (#318 acceptance 13): on a phone at 200% text a long part title wraps
    # inside its title bar, which stays inside its box, on my guide (with records, the route's
    # title included) and in the six chapters.
    LINES = """(el) => {
        const style = getComputedStyle(el);
        const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
        return (el.clientHeight - padding) / parseFloat(style.lineHeight);
    }"""

    def test_guide_part_titles_wrap_in_their_bars_at_double_text_size(self):
        pages = [("guide", lambda test: test.guide_with_records(), ".section-box")] + [
            (slug, f"/guide/{slug}", "article > section, #stop-question")
            for slug in HearingAidGuideTest.CHAPTERS
        ]
        with self.saving_artifacts():
            for name, path, parts in pages:
                wrapped = 0
                with self.subTest(page=name):
                    self.visit(True, path, width=320)
                    self.assert_fits_uncut(name)
                    for part in self.main().locator(parts).all():
                        title = part.get_by_role("heading").first
                        with self.subTest(part=title.inner_text()):
                            box, bar = part.bounding_box(), title.bounding_box()
                            self.assertLessEqual(
                                bar["x"] + bar["width"], box["x"] + box["width"] + 0.5
                            )
                            wrapped += title.evaluate(self.LINES) > 1.5
                    self.assertGreater(wrapped, 0)

    # #313: the things to bring and the checks to expect are a list, one per line, each with its
    # icon and nothing around it: no white, no frame, no rounded pill.
    GUIDE_ICON_LISTS = (
        ("before-you-go", ("身分證", "現在用的助聽器（有的話）")),
        ("assessment", ("純音聽力檢查", "鼓室圖", "身分證影本", "印章")),
        ("form-25", ("購買憑證", "二十五號表")),
    )

    def test_guide_things_to_bring_are_plain_lists_with_icons(self):
        with self.saving_artifacts():
            for slug, texts in self.GUIDE_ICON_LISTS:
                with self.subTest(chapter=slug):
                    self.visit(False, f"/guide/{slug}")
                    article = self.main().get_by_role("article")
                    for text in texts:
                        with self.subTest(item=text):
                            item = article.get_by_role("listitem").filter(
                                has_text=re.compile(rf"^\s*{re.escape(text)}\s*$")
                            )
                            expect(item.locator("svg")).to_be_visible()
                            self.assert_flat(item)
                            self.assertEqual(self.style(item, "borderTopWidth"), "0px")
                            self.assertEqual(self.style(item, "borderRadius"), "0px")
                    # One per line, close together like a list: each item starts below the one
                    # before it, nearer than two paragraphs (18px) are.
                    lists = article.locator("ul:has(> li > svg)")
                    self.assertGreater(lists.count(), 0)
                    for each in lists.all():
                        boxes = [li.bounding_box() for li in each.locator("> li").all()]
                        for above, below in pairwise(boxes):
                            gap = below["y"] - (above["y"] + above["height"])
                            self.assertGreaterEqual(gap, 0)
                            self.assertLess(gap, 18)

    # #312: each of the family guide's topics is a 並列區塊 under its blue-barred title: its tips
    # on the beige with a deeper beige line between each two, each tip's point a subhead larger
    # than the words under it. Signed in and signed out alike. 傳給家人 and the sources stay
    # flat; the urgent topic keeps its blue frame and pale blue, without a shadow, like the
    # 建議您下一步 box, and 119's box as before.
    def test_family_guide_topics_are_tinted_and_the_urgent_one_stands_out(self):
        with self.saving_artifacts():
            for signed_in in (False, True):
                with self.subTest(signed_in=signed_in):
                    self.visit(signed_in, "/family")
                    for name in ("怎麼跟聽損的家人說話", "陪伴配戴助聽器"):
                        with self.subTest(topic=name):
                            topic = self.main().get_by_role("region", name=name)
                            self.assert_flat(topic)
                            self.assert_titled(topic.get_by_role("heading", name=name))
                            tips = topic.get_by_role("list")
                            self.assert_tinted(tips)
                            self.assert_readable_on_tint(tips)
                            self.assert_lines_between(tips.get_by_role("listitem"))
                            for tip in tips.get_by_role("listitem").all():
                                point = tip.locator("strong")
                                with self.subTest(tip=point.inner_text()):
                                    # 1.2 times the 18px body text (ADR 0024).
                                    self.assertEqual(self.style(tip, "fontSize"), "18px")
                                    self.assertEqual(self.style(point, "fontSize"), "21.6px")
                                    # The heading colour, not link blue.
                                    self.assertEqual(self.style(point, "color"), "rgb(33, 37, 41)")
                    for name in ("傳給家人", "出處"):
                        with self.subTest(part=name):
                            part = self.main().get_by_role("region", name=name)
                            self.assert_flat(part)
                            self.assert_titled(part.get_by_role("heading", name=name))
                    sources = self.main().get_by_role("region", name="出處").get_by_role("link")
                    self.assertGreater(sources.count(), 0)
                    urgent = self.main().get_by_role("region", name="什麼時候要馬上就醫")
                    self.assertEqual(self.style(urgent, "backgroundColor"), "rgb(238, 243, 250)")
                    self.assertEqual(self.style(urgent, "borderTopColor"), self.PRIMARY)
                    self.assertEqual(self.style(urgent, "borderTopWidth"), "2px")  # 0.125rem
                    self.assertEqual(self.style(urgent, "boxShadow"), "none")
                    urgent_tips = urgent.get_by_role("listitem")
                    # Its own grey lines and spacing, as before.
                    second = urgent_tips.nth(1)
                    self.assertEqual(self.style(second, "borderTopColor"), "rgb(206, 212, 218)")
                    self.assertEqual(self.style(second, "paddingTop"), "13.5px")
                    # #316: the 119 line is not white (white means tappable) but a light blue a
                    # little deeper than the box, so it still stands out; 119 stays large and bold.
                    call = urgent.get_by_text("如果同時出現", exact=False)
                    self.assertEqual(self.style(call, "backgroundColor"), self.BLUE_DEEP)
                    self.assertEqual(self.style(call, "boxShadow"), "none")
                    number = call.get_by_text("119", exact=True)
                    self.assertEqual(self.style(number, "fontWeight"), "800")
                    self.assertEqual(self.style(number, "fontSize"), "31.5px")  # 1.75rem
                    for colour in set(call.evaluate(self.TEXT_COLOURS)):
                        with self.subTest(colour=colour):
                            self.assertGreaterEqual(
                                StyleInBrowserTest.lowest_contrast(colour, "rgb(214, 226, 242)"),
                                4.5,
                            )

    # #312: the family guide fits a phone at 200% text, signed in and signed out.
    def test_family_guide_fits_a_phone_at_double_text_size(self):
        with self.saving_artifacts():
            for signed_in in (False, True):
                with self.subTest(signed_in=signed_in):
                    self.visit(signed_in, "/family", width=320)
                    self.assert_fits_uncut(f"family guide, signed in: {signed_in}")

    # #302: the 了解 page's cards stay white cards.
    def test_learn_cards_stay_white_cards(self):
        with self.saving_artifacts():
            self.visit(False, "/learn")
            cards = self.main().get_by_role("link")
            self.assertEqual(cards.count(), 2)
            for card in cards.all():
                with self.subTest(card=card.inner_text()):
                    self.assert_white_card(card)

    # #303: the family's 「您可以怎麼幫忙」 and 「先看重點」 are flat; the three cards in it stay
    # white cards and go where they went before.
    def test_family_help_is_flat_and_its_three_cards_stay_white(self):
        with self.saving_artifacts():
            self.visit(False, lambda test: test.shared_report())
            self.assert_flat(self.main().get_by_role("region", name="先看重點"))
            help_block = self.main().get_by_role("region", name="您可以怎麼幫忙")
            self.assert_flat(help_block)
            cards = help_block.get_by_role("link")
            self.assertEqual(
                [card.get_attribute("href") for card in cards.all()],
                ["/family#talk-title", "/family#aid-title", "/family#urgent-title"],
            )
            for card in cards.all():
                with self.subTest(card=card.inner_text()):
                    self.assert_white_card(card)

    # #302: the privacy notice's highlights and contact, and the consent page's highlights, are
    # flat blocks framed by their titles.
    def test_privacy_and_consent_highlights_are_flat(self):
        with self.saving_artifacts():
            self.visit(False, "/privacy")
            for name in ("先看重點", "有問題或要刪除資料？"):
                with self.subTest(part=name):
                    part = self.main().get_by_role("region", name=name)
                    self.assert_flat(part)
                    self.assert_titled(part.get_by_role("heading", name=name))
            expect(
                self.main()
                .get_by_role("region", name="有問題或要刪除資料？")
                .get_by_role("link", name="hearwellweb@gmail.com")
            ).to_be_visible()
            self.visit(True, lambda test: test.undecided())
            highlights = self.main().get_by_role("region", name="重點", exact=True)
            self.assert_flat(highlights)
            self.assert_titled(highlights.get_by_role("heading", name="重點", exact=True))

    # #302: no sideways scrolling or cut text on a phone at 200% text, on my guide, its chapters
    # and the other learn pages.
    def test_learn_pages_fit_a_phone_at_double_text_size(self):
        with self.saving_artifacts():
            for name, signed_in, path in WHITE_CARD_PAGES_LEARN:
                with self.subTest(page=name):
                    self.visit(signed_in, path, width=320)
                    self.assert_fits_uncut(name)

    # #311: the share page's steps 1-3 are 並列區塊 titled by a larger subhead; their buttons
    # are still buttons.
    def test_share_steps_are_tinted_and_keep_their_buttons(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.share_settings())
            for step in ("家人會看到什麼", "產生連結", "傳給家人"):
                with self.subTest(step=step):
                    block = self.main().get_by_role("region", name=step)
                    self.assert_tinted(block)
                    self.assert_block_title(block.get_by_role("heading", name=step, exact=True))
                    self.assert_readable_on_tint(block, skip_own_backgrounds=True)
            cancel = self.main().get_by_role("button", name="取消分享", exact=True)
            expect(cancel).to_be_visible()
            self.assertEqual(self.style(cancel, "borderTopStyle"), "solid")
            self.assert_outline_button_readable(cancel)

    # #303: the report's audiogram on screen is flat, with the blue bar on its title; the
    # summary keeps its blue frame. (A questionnaire's part folds onto the tint since #314.)
    def test_report_parts_are_flat_and_the_summary_keeps_its_blue_frame(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.report())
            self.assert_flat(self.main().get_by_role("region", name=re.compile("^聽力圖（")))
            audiogram_title = self.main().get_by_role("heading", name=re.compile("^聽力圖（"))
            self.assertEqual(self.style(audiogram_title, "borderLeftColor"), self.PRIMARY)
            summary = self.main().get_by_role("region", name="重點摘要")
            self.assertEqual(self.style(summary, "backgroundColor"), self.WHITE)
            self.assertEqual(self.style(summary, "borderTopColor"), self.PRIMARY)

    # #303: on paper the report's parts stay unframed, as before.
    def test_printed_report_parts_stay_unframed(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.report())
            self.page.emulate_media(media="print")
            for selector in ("#report-audiogram", "#report-hhie-s"):
                with self.subTest(part=selector):
                    part = self.page.locator(selector)
                    self.assert_flat(part)
                    self.assertEqual(self.style(part, "borderTopWidth"), "0px")
                    self.assertEqual(self.style(part, "paddingLeft"), "0px")
            title = self.page.locator("#audiogram-title")
            self.assertEqual(self.style(title, "borderLeftColor"), self.PRIMARY)

    # #314: the report with a fold for HHIE-S (its kept comparison inside), SSQ12-TW, SADL and
    # IOI-HA (grouped by an earlier unaided HHIE-S), and an audiogram.
    def folded_report(self):
        self.ioi_ha()
        self.answered("ssq12-tw", 5)
        self.answered("sadl", 4)
        unaided = self.answered("hhie-s", 2)
        aided = self.answered("hhie-s", 0)
        Submission.objects.filter(pk=aided.pk).update(wearing_hearing_aid=True)
        ReportComparison.objects.create(
            user=self.user, questionnaire=unaided.questionnaire, unaided=unaided, aided=aided
        )
        self.audiogram()
        return "/report"

    def both_folded_reports(self):
        """The owner's folded report and the family's copy of it, signed in and not."""
        owner = self.folded_report()
        family = f"/shared/{ReportShare.objects.create(user=self.user).token}/report"
        return (("owner", True, owner), ("family", False, family))

    def report_folds(self):
        """Each questionnaire's summary row."""
        return self.main().locator(REPORT_FOLDS)

    def fold_body(self, fold):
        """What a questionnaire's summary row opens: the 並列區塊 under it."""
        return fold.locator("xpath=following-sibling::*")

    def visit_open_report(self, signed_in, path, width=1024):
        """The report with every questionnaire's fold opened."""
        self.visit(signed_in, path, width=width)
        open_report_folds(self.page)

    def tab_to(self, target):
        """Presses Tab, from wherever the focus is, until target has the focus."""
        for _ in range(60):
            self.page.keyboard.press("Tab")
            if target.evaluate("el => el === document.activeElement"):
                return
        self.fail("Tab never reached it")

    # #314 (spec #308 acceptance 1, 6-8): on both reports each questionnaire starts as a closed
    # summary row that looks like the site's dropdowns; a click, or Tab to it and Enter, opens
    # only that one onto the tint, its comparison inside, and again closes it; a reload closes
    # it. The audiogram stays open. Every fold opens onto the tint with readable text. It opens
    # without JavaScript too.
    def test_report_folds_by_questionnaire_closed_until_opened(self):
        with self.saving_artifacts():
            for name, signed_in, path in self.both_folded_reports():
                with self.subTest(report=name):
                    self.visit(signed_in, path)
                    expect(
                        self.main().get_by_role("region", name=re.compile("^聽力圖（"))
                    ).to_be_visible()
                    if signed_in:
                        expect(self.main().get_by_role("region", name="重點摘要")).to_be_visible()
                    expect(
                        self.main().get_by_role("heading", level=2, name="生活影響", exact=True)
                    ).to_be_visible()
                    folds = self.report_folds()
                    self.assertEqual(
                        [fold.get_by_role("heading", level=3).inner_text() for fold in folds.all()],
                        ["HHIE-S", "SSQ12-TW", "SADL", "IOI-HA 助聽器效益"],
                    )
                    for fold in folds.all():
                        expect(self.fold_body(fold)).to_be_hidden()
                    summary = folds.first
                    title = summary.get_by_role("heading", level=3)
                    # The latest record (aided, all 0): its date, score and level.
                    expect(summary).to_have_text(
                        re.compile(r"^HHIE-S\s*最近一次 \d{4}/\d\d/\d\d\s*0 分 無/極輕微影響$")
                    )
                    part = self.main().get_by_role("region", name=re.compile("^HHIE-S（"))
                    comparison = self.main().get_by_role(
                        "region", name=re.compile("^配戴狀態比較（HHIE-S")
                    )
                    expect(part).to_be_hidden()
                    expect(comparison).to_be_hidden()
                    # Like the site's dropdowns: white, a grey edge, no shadow, a chevron.
                    self.assertEqual(self.style(summary, "backgroundColor"), self.WHITE)
                    self.assertEqual(self.style(summary, "borderTopColor"), self.GREY_EDGE)
                    self.assertEqual(self.style(summary, "boxShadow"), "none")
                    chevron = summary.evaluate("el => getComputedStyle(el, '::after').maskImage")
                    self.assertIn("M6 9l6 6 6-6", chevron)
                    self.assert_block_title(title)
                    summary.click()
                    expect(part).to_be_visible()
                    expect(comparison).to_be_visible()
                    for other in folds.all()[1:]:
                        expect(self.fold_body(other)).to_be_hidden()
                    body = self.fold_body(summary)
                    expect(
                        body.get_by_role("region", name=re.compile("^配戴狀態比較（HHIE-S"))
                    ).to_be_visible()
                    chevron = summary.evaluate("el => getComputedStyle(el, '::after').maskImage")
                    self.assertIn("M6 15l6-6 6 6", chevron)
                    summary.click()
                    expect(part).to_be_hidden()
                    summary.click()
                    self.page.reload()
                    expect(part).to_be_hidden()
                    self.tab_to(summary)
                    self.page.keyboard.press("Enter")
                    expect(part).to_be_visible()
                    self.page.keyboard.press("Enter")
                    expect(part).to_be_hidden()
                    for fold in folds.all():
                        with self.subTest(fold=fold.inner_text()[:8]):
                            fold.click()
                            self.assert_tinted(self.fold_body(fold))
                            self.assert_readable_on_tint(self.fold_body(fold))
                    self.visit(signed_in, path, javascript=False)
                    self.report_folds().first.click()
                    expect(
                        self.main().get_by_role("region", name=re.compile("^HHIE-S（"))
                    ).to_be_visible()

    # #314 (spec #308 acceptance 9, 14): on a phone at 200% text both reports fit with every fold
    # open; on paper every fold is open, the one the reader opened and those left closed alike,
    # and no summary row shows.
    def test_report_folds_open_on_paper_and_fit_a_phone_open(self):
        with self.saving_artifacts():
            for name, signed_in, path in self.both_folded_reports():
                with self.subTest(report=name):
                    self.visit_open_report(signed_in, path, width=320)
                    self.assert_fits_uncut(name)
                    self.page.reload()  # every fold closed again, the text its normal size
                    folds = self.report_folds()
                    self.assertEqual(folds.count(), 4)
                    folds.nth(1).click()
                    expect(self.fold_body(folds.nth(1))).to_be_visible()
                    self.page.emulate_media(media="print")
                    for fold in folds.all():
                        expect(fold).to_be_hidden()
                        expect(self.fold_body(fold).get_by_role("region").first).to_be_visible()
                    expect(
                        self.page.get_by_role("region", name=re.compile("^配戴狀態比較（HHIE-S"))
                    ).to_be_visible()

    # #315: both reports with their two kinds of table: HHIE-S's recent records (three of them,
    # one of each level, 2 being IOI-HA's norm basis) and IOI-HA's items compared with the norm.
    def table_reports(self):
        for score in (0, 4):
            self.answered("hhie-s", score)
        self.ioi_ha()
        family = f"/shared/{ReportShare.objects.create(user=self.user).token}/report"
        return (("owner", True, "/report"), ("family", False, family))

    def open_report_tables(self, signed_in, path, width):
        """The report with every fold open, and its tables."""
        self.visit_open_report(signed_in, path, width)
        tables = self.main().get_by_role("table")
        self.assertEqual(tables.count(), 2)
        return tables

    LINES = """el => {
        const range = document.createRange();
        range.selectNodeContents(el);
        return new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size;
    }"""

    # #315 (spec #308 acceptance 13): on a phone at the normal text size every date in the
    # reports' tables stays on one line, and nothing is cut.
    def test_report_table_dates_stay_on_one_line(self):
        with self.saving_artifacts():
            for name, signed_in, path in self.table_reports():
                for width in (320, 390):
                    with self.subTest(report=name, width=width):
                        self.open_report_tables(signed_in, path, width)
                        dates = self.main().get_by_role(
                            "cell", name=re.compile(r"^\d{4}\/\d\d\/\d\d$")
                        )
                        self.assertEqual(dates.count(), 3)
                        for cell in dates.all():
                            self.assertEqual(cell.evaluate(self.LINES), 1, cell.inner_text())
                        self.assertEqual(self.page.evaluate(self.CUT_OFF), [])

    def records(self, table):
        """A table's records: its rows of cells, the header row left out."""
        return table.get_by_role("row").filter(has=self.page.get_by_role("cell"))

    # #315 (spec #308 acceptance 14): on a phone at 200% text, where a table does not fit, each
    # record stacks into a block of its own: one value under another, each after its column's
    # name, a line between two records; nothing scrolls sideways or is cut. With room, at the
    # normal size, it stays a table of side-by-side columns.
    def test_report_table_records_stack_when_the_table_does_not_fit(self):
        with self.saving_artifacts():
            for name, signed_in, path in self.table_reports():
                for width in (320, 390):
                    with self.subTest(report=name, width=width):
                        tables = self.open_report_tables(signed_in, path, width)
                        self.assert_fits_uncut(f"{name}, {width}", width)
                        for table in tables.all():
                            columns = table.get_by_role("columnheader").all_inner_texts()
                            for header in table.get_by_role("columnheader").all():
                                self.assertLessEqual(header.bounding_box()["width"], 1)
                            records = self.records(table)
                            self.assert_lines_between(records)
                            for record in records.all():
                                cells = record.get_by_role("cell")
                                labels = [
                                    cell.evaluate("el => getComputedStyle(el, '::before').content")
                                    for cell in cells.all()
                                ]
                                self.assertEqual([label.split('"')[1] for label in labels], columns)
                                boxes = [cell.bounding_box() for cell in cells.all()]
                                for above, below in pairwise(boxes):
                                    self.assertGreaterEqual(
                                        below["y"], above["y"] + above["height"] - 0.5
                                    )
            # On a phone at 200% text the stacked records are still tables to a screen reader, as
            # the browser's own accessibility tree says: column names, and cells that hold only
            # their values (the names shown in front of them are not read twice).
            self.visit_open_report(True, "/report", width=320)
            self.assert_fits_uncut("owner, accessibility tree")
            session = self.context.new_cdp_session(self.page)
            nodes = session.send("Accessibility.getFullAXTree")["nodes"]
            named = [
                (node["role"]["value"], node.get("name", {}).get("value", ""))
                for node in nodes
                if not node.get("ignored")
            ]
            self.assertEqual([role for role, _ in named].count("table"), 2)
            self.assertEqual(
                [name for role, name in named if role == "columnheader"],
                ["日期", "總分", "分級", "助聽器", "項目", "回答", "與常模比較"],
            )
            cells = [name for role, name in named if role == "cell"]
            self.assertEqual(len(cells), 3 * 4 + 7 * 3)
            self.assertIn("2026", cells[0])
            for cell in cells:
                self.assertNotRegex(cell, "^(日期|總分|分級|助聽器|項目|回答|與常模比較)")
            self.assertEqual([role for role, _ in named].count("row"), 2 + 3 + 7)
            # With room, at the normal size: side-by-side columns under a header row whose names
            # do not break either.
            self.visit_open_report(True, "/report", width=390)
            for table in self.main().get_by_role("table").all():
                for header in table.get_by_role("columnheader").all():
                    self.assertGreater(header.bounding_box()["width"], 1)
                    self.assertEqual(header.evaluate(self.LINES), 1, header.inner_text())
                for record in self.records(table).all():
                    tops = {
                        round(cell.bounding_box()["y"]) for cell in record.get_by_role("cell").all()
                    }
                    self.assertEqual(len(tops), 1, record.inner_text())

    # #303 (#298's pick): the account details are flat rows with a thin line between them;
    # every link row is a white card of its own and goes where it went before.
    def test_account_details_are_flat_rows_and_link_rows_are_white_cards(self):
        with self.saving_artifacts():
            self.visit(True, "/account")
            details = self.main().get_by_role("region", name="我的帳號").locator("dl")
            self.assert_flat(details)
            rows = details.locator(":scope > div")
            self.assertEqual(rows.count(), 3)
            self.assertEqual(self.style(rows.nth(0), "borderTopWidth"), "0px")
            for row in rows.all()[1:]:
                with self.subTest(row=row.inner_text()):
                    self.assertEqual(self.style(row, "borderTopWidth"), "1px")
                    self.assertEqual(self.style(row, "borderTopColor"), self.LINE)
            links = self.main().get_by_role("link")
            self.assertEqual(
                [link.get_attribute("href") for link in links.all()],
                [
                    "/share",
                    "/family",
                    "/add_to_home",
                    "/my_data/download",
                    "/privacy",
                    "/account/delete",
                ],
            )
            for link in links.all():
                with self.subTest(link=link.get_attribute("href")):
                    self.assert_white_card(link)

    # #303: no sideways scrolling or cut text on a phone at 200% text on the report, sharing and
    # account pages.
    def test_sharing_and_account_pages_fit_a_phone_at_double_text_size(self):
        with self.saving_artifacts():
            for name, signed_in, path in WHITE_CARD_PAGES_SHARING:
                with self.subTest(page=name):
                    self.visit(signed_in, path, width=320)
                    self.assert_fits_uncut(name)

    # #300: the answering page's questions are flat; its choices stay white with a grey edge.
    GREY_EDGE = "rgb(206, 212, 218)"

    def assert_white_choices(self, question):
        choices = question.locator("label")
        self.assertGreater(choices.count(), 1)
        for choice in choices.all():
            with self.subTest(choice=choice.inner_text()):
                self.assertEqual(self.style(choice, "backgroundColor"), self.WHITE)
                self.assertEqual(self.style(choice, "borderTopColor"), self.GREY_EDGE)
                self.assertEqual(self.style(choice, "boxShadow"), "none")

    def assert_questions_apart(self, questions):
        """More space between two questions than between two choices inside one."""
        choices = questions.first.locator("label")
        inside = choices.nth(1).bounding_box()["y"] - (
            choices.nth(0).bounding_box()["y"] + choices.nth(0).bounding_box()["height"]
        )
        boxes = [question.bounding_box() for question in questions.all()]
        for above, below in pairwise(boxes):
            self.assertGreater(below["y"] - (above["y"] + above["height"]), inside)

    def test_answering_questions_are_flat_and_choices_stay_white(self):
        with self.saving_artifacts():
            # React: one question per page, here the wearing question first.
            self.visit(True, lambda test: test.answering("hhie-s"))
            question = self.main().locator(".answer-app").get_by_role("group")
            self.assert_flat(question)
            self.assert_white_choices(question)
            self.assertEqual(self.page.evaluate(self.WHITE_CARDS_THAT_ARE_NOT_LINKS), [])
            # The Django form, as when React does not load: every question on one page, apart by
            # number, title and space.
            self.visit(True, lambda test: test.answering("hhie-s"), javascript=False)
            questions = self.main().locator("#answer-form").get_by_role("group")
            self.assertEqual(questions.count(), 1 + QUESTION_COUNT)
            for question in questions.all():
                with self.subTest(question=question.inner_text()[:12]):
                    self.assert_flat(question)
                    self.assert_white_choices(question)
            self.assert_questions_apart(questions)
            self.assertEqual(self.page.evaluate(self.WHITE_CARDS_THAT_ARE_NOT_LINKS), [])

    def test_answering_fits_a_phone_at_double_text_size_with_questions_apart(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.answering("hhie-s"), width=320)
            expect(self.main().locator(".answer-app").get_by_role("group")).to_be_visible()
            self.assert_fits_uncut("answering")
            self.visit(True, lambda test: test.answering("hhie-s"), width=320, javascript=False)
            self.assert_fits_uncut("answering without JavaScript")
            self.assert_questions_apart(self.main().locator("#answer-form").get_by_role("group"))

    # #313: in the four intros the answers are bold words in the sentence, with no white boxes
    # beside it; at 200% on a phone nothing runs off or is cut.
    INTRO_ANSWERS = (
        ("hhie-s", ("常常", "有時", "從未")),
        ("hhia-s", ("會", "有時", "不會")),
        ("ssq12-tw", ("0–10", "不適用")),
        ("thi", ("經常", "偶爾", "不會")),
    )

    def test_answering_intros_bold_the_answers_in_the_sentence(self):
        with self.saving_artifacts():
            for code, words in self.INTRO_ANSWERS:
                with self.subTest(questionnaire=code):
                    self.visit(True, lambda test, code=code: test.answering(code), width=320)
                    how = (
                        self.main()
                        .locator("section")
                        .filter(has=self.page.get_by_role("heading", name="怎麼回答"))
                    )
                    for word in words:
                        with self.subTest(word=word):
                            bold = how.get_by_text(word, exact=True)
                            expect(bold).to_have_count(1)
                            self.assertEqual(self.style(bold, "fontWeight"), "700")
                            # Inside the sentence: its paragraph says more than the word.
                            sentence = bold.locator("xpath=ancestor::p[1]")
                            self.assertGreater(len(sentence.inner_text()), len(word) + 5)
                    whites = how.evaluate(
                        """(el) => [...el.querySelectorAll("*")]
                            .filter((node) => getComputedStyle(node).backgroundColor
                                === "rgb(255, 255, 255)")
                            .map((node) => node.outerHTML.slice(0, 80))"""
                    )
                    self.assertEqual(whites, [])
                    self.assert_fits_uncut(code)

    # #300: login and register keep their form card white: the rule's one exception.
    def test_login_and_register_form_cards_stay_white_cards(self):
        with self.saving_artifacts():
            for path, button in (("/login", "登入"), ("/register", "註冊")):
                with self.subTest(page=path):
                    self.visit(False, path)
                    form_card = self.main().locator(".auth-card")
                    expect(form_card.get_by_role("button", name=button, exact=True)).to_be_visible()
                    self.assert_white_card(form_card)

    # #300: the suggested questionnaire is flat with its 開始作答 button; whole cards stay white.
    def test_suggested_questionnaire_is_flat_and_questionnaire_cards_stay_white(self):
        with self.saving_artifacts():
            self.visit(True, "/questionnaire_list?concern=hearing_aid&age_group=older")
            suggested = (
                self.main()
                .get_by_role("region")
                .filter(has=self.page.get_by_role("link", name="開始作答", exact=True))
            )
            self.assert_flat(suggested)
            self.assertEqual(
                self.style(suggested.get_by_role("link", name="開始作答"), "backgroundImage"),
                self.GRADIENT,
            )
            for path in (
                "/questionnaire_list?concern=hearing_aid&age_group=older",
                "/questionnaire_list?choose=self",
            ):
                with self.subTest(page=path):
                    self.visit(True, path)
                    cards = self.main().locator("a.link-card").filter(visible=True)
                    self.assertGreater(cards.count(), 0)
                    for card in cards.all():
                        with self.subTest(card=card.inner_text()[:12]):
                            self.assert_white_card(card)

    # #301: a chart's drawing area is a sheet of paper, not a card to tap.
    def assert_paper(self, canvas, card):
        expect(canvas).to_be_visible()
        self.assertEqual(self.style(canvas, "backgroundColor"), self.WHITE)
        self.assertEqual(self.style(canvas, "borderTopStyle"), "solid")
        self.assertEqual(self.style(canvas, "borderTopWidth"), "1px")
        self.assertEqual(self.style(canvas, "boxShadow"), "none")
        radius = float(self.style(canvas, "borderTopLeftRadius").removesuffix("px"))
        card_radius = float(self.style(card, "borderTopLeftRadius").removesuffix("px"))
        self.assertLess(radius, card_radius)

    # Spec #297 acceptance 6 (#301): the trend chart, the IOI-HA chart and the audiogram.
    def test_chart_drawing_areas_are_white_paper_with_a_small_radius(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.trend_records())
            # The chart grows from 0 to its full width; measure once it is drawn.
            self.page.locator("#trend-plot .recharts-wrapper").wait_for()
            card = self.main().locator("a.link-card").first
            self.assert_paper(self.page.locator("#trend-plot").locator(".."), card)
            self.visit(True, lambda test: test.ioi_ha_records())
            card = self.main().locator("a.link-card").first
            self.assert_paper(self.page.get_by_role("region", name="IOI-HA 各題與常模"), card)
            self.visit(True, lambda test: test.audiogram_detail())
            self.page.locator("#audiogram-chart svg").first.wait_for()
            card = self.main().locator("a.link-card").first
            self.assert_paper(self.page.locator("#audiogram-chart"), card)

    # IOI-HA's norm on its scale and legend: grey cells with a darker grey edge.
    NORM_GREY = "rgb(206, 212, 218)"
    NORM_EDGE = "rgb(108, 117, 125)"

    def assert_tinted_items(self, items, title, count, ratio, before):
        """#310: each item its own 並列區塊, its title (found by `title` inside it) `ratio` times
        the text and larger than the `before` px it had on a phone before ADR 0024."""
        self.assertEqual(items.count(), count)
        for item in items.all():
            with self.subTest(item=item.inner_text()[:10]):
                self.assert_tinted(item)
                self.assert_readable_on_tint(item)
                self.assertGreater(self.assert_block_title(title(item), ratio), before)

    # #310: IOI-HA's items, SADL's four facets and SSQ12-TW's lowest answers are each a 並列區塊
    # with a larger title; IOI-HA's summary and 接下來 stay flat.
    def test_result_items_are_tinted_blocks_with_larger_titles(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.ioi_ha_result())
            self.assert_flat(self.main().locator("section").filter(has_text="比較對象：").first)
            self.assert_flat(self.page.get_by_role("region", name="接下來", exact=True))
            # Each item's name is its block's title (1.35 times); it was 1.25rem, 22.5px.
            self.assert_tinted_items(
                self.main().locator("ol > li"),
                lambda item: item.get_by_role("heading"),
                7,
                1.35,
                22.5,
            )
            self.visit(True, lambda test: test.result("sadl", 4))
            facets = (
                self.main()
                .get_by_role("list")
                .filter(has=self.page.get_by_role("heading", level=3))
                .get_by_role("listitem")
            )
            # Each facet's name is its block's title (1.35 times); it was 1.25rem, 22.5px.
            self.assert_tinted_items(
                facets, lambda item: item.get_by_role("heading"), 4, 1.35, 22.5
            )
            self.visit(True, lambda test: test.result("ssq12-tw", 5))
            lowest = self.page.get_by_role("region", name=re.compile("分數最低的")).get_by_role(
                "listitem"
            )
            # The question beside its score tag is a bold subhead (1.2 times); it was body text,
            # 18px.
            self.assert_tinted_items(
                lowest, lambda item: item.get_by_text(re.compile("[？?]$")), 3, 1.2, 18
            )

    # Spec #308 acceptance 4: a tappable card's title and the answering page's question keep the
    # size they had before ADR 0024, measured on main (36ae501) at this 390px phone width: the
    # card titles 1.25rem, the question calc(1.275rem + 0.3vw).
    def test_card_titles_and_questions_keep_their_size(self):
        with self.saving_artifacts():
            for name, path in (
                ("returning home", lambda test: test.returning_home()),
                ("HHIE-S result", lambda test: test.result("hhie-s", 2)),
            ):
                with self.subTest(page=name):
                    self.visit(True, path, width=390)
                    titles = self.main().locator("a.link-card .link-card-title")
                    self.assertGreater(titles.count(), 0)
                    for title in titles.all():
                        with self.subTest(card=title.inner_text()):
                            self.assertEqual(self.style(title, "fontSize"), "22.5px")
            self.visit(True, lambda test: test.answering("hhie-s"), width=390)
            question = self.main().get_by_role("group").locator("legend")
            expect(question).to_be_visible()
            self.assertEqual(self.style(question, "fontSize"), "24.12px")

    # #310: the IOI-HA scale's empty cells are clear with a thin deeper beige frame, so they do
    # not read as white things to tap; the norm's grey cells, the blue dot and the legend stay.
    def test_ioi_ha_scale_cells_are_clear_with_a_thin_line(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.ioi_ha_result())
            item = self.main().locator("ol > li").first
            cells = item.locator(".ioi-scale > *")
            self.assertEqual(cells.count(), 5)
            # Every item is below the norm at 1: the norm is grey cells further right.
            band = item.locator(".ioi-scale > .ioi-cell-band")
            self.assertGreater(band.count(), 0)
            for cell in cells.all():
                is_band = cell.evaluate("(el) => el.classList.contains('ioi-cell-band')")
                with self.subTest(band=is_band):
                    self.assertEqual(self.style(cell, "borderTopStyle"), "solid")
                    self.assertEqual(self.style(cell, "borderTopWidth"), "1px")
                    if is_band:
                        self.assertEqual(self.style(cell, "backgroundColor"), self.NORM_GREY)
                        self.assertEqual(self.style(cell, "borderTopColor"), self.NORM_EDGE)
                    else:
                        self.assertEqual(self.style(cell, "backgroundColor"), "rgba(0, 0, 0, 0)")
                        self.assertEqual(self.style(cell, "borderTopColor"), self.TINT_LINE)
            dot = item.locator(".ioi-scale .ioi-dot-latest")
            self.assertEqual(dot.count(), 1)
            self.assertEqual(self.style(dot, "backgroundColor"), self.PRIMARY)
            legend = self.main().locator(".ioi-legend-band")
            self.assertEqual(self.style(legend, "backgroundColor"), self.NORM_GREY)
            self.assertEqual(self.style(legend, "borderTopColor"), self.NORM_EDGE)

    # #301: 我的紀錄's record cards stay white cards; the summaries above them are not.
    def test_my_records_keep_white_record_cards_and_flat_summaries(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.trend_records())
            records = self.main().locator('a.link-card[href^="/submission/"]')
            self.assertEqual(records.count(), 2)
            for record in records.all():
                with self.subTest(record=record.inner_text()[:10]):
                    self.assert_white_card(record)
            self.assert_flat(self.page.get_by_role("region", name="和上一次比"))
            # The pale blue summary box above the chart: not white, no shadow (ADR 0022).
            trend = self.page.get_by_role("region", name="HHIE-S 總分變化")
            summary = trend.get_by_text("最近一次（").locator("..")
            self.assertNotEqual(self.style(summary, "backgroundColor"), self.WHITE)
            self.assertEqual(self.style(summary, "boxShadow"), "none")

    # 2026-10-24 comparison page, option A: 和上一次比's two records side by side.
    def test_since_last_sets_the_two_records_side_by_side(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.trend_records(), width=320)
            since_last = self.page.get_by_role("region", name="和上一次比")
            previous = since_last.locator(".since-last-cell").first
            latest = since_last.locator(".since-last-latest")
            # 上一次 on a 並列區塊's beige, 最近一次 pale blue in a brand-blue frame; neither white.
            self.assertEqual(self.style(previous, "backgroundColor"), self.TINT)
            self.assertEqual(self.style(latest, "backgroundColor"), self.BLUE_SOFT)
            self.assert_every_side(latest, Color=self.PRIMARY, Style="solid", Width="2px")
            for cell in (previous, latest):
                self.assertEqual(self.style(cell, "boxShadow"), "none")
                score = float(self.style(cell.locator(".since-last-score"), "fontSize")[:-2])
                label = float(self.style(cell.locator(".since-last-label"), "fontSize")[:-2])
                date = float(self.style(cell.locator(".since-last-date"), "fontSize")[:-2])
                self.assertGreater(score, label * 1.5)
                self.assertLess(date, label)
            arrow = since_last.locator(".since-last-arrow")
            self.assertEqual(self.style(arrow, "color"), self.PRIMARY)
            # Screen readers hear each record as one line, the brackets and colon included.
            # trend_records makes both on the same day, so each date has its time.
            expect(since_last).to_match_aria_snapshot(
                '- heading "和上一次比" [level=2]\n'
                "- paragraph: /上一次 （ \\d{4}/\\d\\d/\\d\\d \\d\\d:\\d\\d ）： 20 分/\n"
                "- paragraph: /最近一次 （ \\d{4}/\\d\\d/\\d\\d \\d\\d:\\d\\d ）： 40 分/\n"
                "- paragraph:\n"
                "  - strong: 比上一次多 20 分（分數越低越好）"
            )

            def boxes():
                return [cell.bounding_box() for cell in (previous, latest)]

            # Side by side on the smallest phone, the arrow pointing right...
            before, after = boxes()
            self.assertEqual(before["y"], after["y"])
            self.assertLess(before["x"], after["x"])
            self.assertEqual(self.style(arrow, "transform"), "none")
            # ...one above the other at 200% text, nothing cut, the arrow turned to point down.
            self.assert_fits_uncut("和上一次比")
            before, after = boxes()
            self.assertEqual(before["x"], after["x"])
            self.assertLess(before["y"] + before["height"], after["y"])
            self.assertNotEqual(self.style(arrow, "transform"), "none")

    def assert_outline_button_readable(self, button):
        """#311: an outline button in a 並列區塊 is filled white (white is what can be tapped), so
        its words keep 4.5:1; the danger red on the beige alone is 3.6:1."""
        self.assertEqual(self.style(button, "backgroundColor"), self.WHITE)
        self.assertGreaterEqual(
            StyleInBrowserTest.lowest_contrast(self.style(button, "color"), self.WHITE), 4.5
        )

    # #311: each ear's result is a 並列區塊 that keeps the line in its ear's colour on top.
    EAR_LINES = (("右耳", "rgb(192, 57, 43)"), ("左耳", "rgb(31, 78, 140)"))

    # #311: the audiogram's ear results and the comparison page's two pairs are 並列區塊 titled
    # by a larger subhead, the comparison's buttons as before; the summary above the ears and the
    # new audiogram's how-to on an ear step stay flat (#301).
    def test_ear_results_and_comparison_pairs_are_tinted(self):
        with self.saving_artifacts():
            self.visit(True, lambda test: test.audiogram_detail())
            self.assert_flat(self.page.get_by_role("region", name="兩耳程度"))
            for ear, colour in self.EAR_LINES:
                with self.subTest(ear=ear):
                    heading = self.page.get_by_role("heading", name=ear, exact=True)
                    block = self.main().locator("section").filter(has=heading)
                    self.assert_tinted(block, top_line=colour)
                    self.assert_block_title(heading)
                    self.assert_readable_on_tint(block, skip_own_backgrounds=True)
            self.visit(True, lambda test: test.hhi_comparison())
            for title, button in (
                ("目前查看的兩筆", "改放這一組到報告"),
                ("聽力報告裡的組合", "從報告移除"),
            ):
                with self.subTest(block=title):
                    block = self.page.get_by_role("region", name=title)
                    self.assert_tinted(block)
                    self.assert_block_title(block.get_by_role("heading", name=title, exact=True))
                    self.assert_readable_on_tint(block, skip_own_backgrounds=True)
                    expect(block.get_by_role("button", name=button, exact=True)).to_be_visible()
            save = self.page.get_by_role("button", name="改放這一組到報告", exact=True)
            self.assertEqual(self.style(save, "backgroundImage"), self.GRADIENT)
            self.assert_outline_button_readable(
                self.page.get_by_role("button", name="從報告移除", exact=True)
            )
            self.assertEqual(self.page.evaluate(self.WHITE_CARDS_THAT_ARE_NOT_LINKS), [])
            self.open(signed_in=True)
            audiogram_step(self.page, self.live_server_url, 2)
            expect(self.main().get_by_text("報告上的 O 是右耳")).to_be_visible()
            self.assertEqual(self.page.evaluate(self.WHITE_CARDS_THAT_ARE_NOT_LINKS), [])

    # #311: no sideways scrolling or cut text on a phone at 200% text on the three pages with
    # its 並列區塊.
    def test_ear_results_share_steps_and_comparison_fit_a_phone_at_double_text_size(self):
        pages = (
            ("audiogram", lambda test: test.audiogram_detail()),
            ("share settings", lambda test: test.share_settings()),
            ("aided and unaided comparison", lambda test: test.hhi_comparison()),
        )
        with self.saving_artifacts():
            for name, path in pages:
                with self.subTest(page=name):
                    self.visit(True, path, width=320)
                    self.assert_fits_uncut(name)

    # #301: no sideways scrolling on a phone at 200% text on 我的紀錄's two tabs and an audiogram.
    def test_records_and_audiogram_fit_a_phone_at_double_text_size(self):
        pages = (
            ("my records, questionnaires", lambda test: test.trend_records()),
            ("my records, audiograms", lambda test: test.audiogram_records()),
            ("audiogram", lambda test: test.audiogram_detail()),
        )
        with self.saving_artifacts():
            for name, path in pages:
                with self.subTest(page=name):
                    self.visit(True, path, width=320)
                    self.assert_fits_a_phone_at_double_text_size(name)


class BackToTopTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """Spec #338 (ticket #340): the back-to-top button, signed out, on a guide chapter (a long
    page) and the login page (a short one)."""

    LONG = "/guide/form-9"
    SHORT = "/login"
    # Whether the focus is on the first element after the page's title that Tab can reach.
    ON_NEXT_AFTER_TITLE = """() => {
        const title = document.querySelector("main h1");
        const reachable = [...document.querySelectorAll(
            "a[href], button, input, select, textarea, summary, [tabindex]"
        )].filter((el) => el.tabIndex >= 0 && el.checkVisibility({visibilityProperty: true})
            && title.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
        return document.activeElement === reachable[0];
    }"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def open(self, path, width=390, height=700, javascript=True, motion="no-preference"):
        self.context = self.browser.new_context(
            viewport={"width": width, "height": height},
            java_script_enabled=javascript,
            reduced_motion=motion,
        )
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)
        self.page.goto(f"{self.live_server_url}{path}")
        self.page.wait_for_load_state("load")

    def scroll_to(self, y):
        self.page.evaluate("y => window.scrollTo({top: y, behavior: 'instant'})", y)

    def screens(self, count):
        """count viewport heights, in pixels."""
        return self.page.evaluate("count => count * window.innerHeight", count)

    def button(self):
        """What a screen reader finds: nothing while the button is folded away."""
        return self.page.get_by_role("button", name="回到頂端", exact=True)

    def tab_from_end_of_content(self):
        """Focuses the content's last link, button or fold where the page is, then presses Tab."""
        last = self.page.evaluate("""() => {
            const shown = [...document.querySelectorAll("main :is(a[href], button, summary)")]
                .filter((el) => el.checkVisibility());
            shown.at(-1).focus({preventScroll: true});
            return document.activeElement === shown.at(-1);
        }""")
        self.assertTrue(last)
        self.page.keyboard.press("Tab")

    # #338 acceptance 1
    def test_shows_past_two_screens_above_the_tabs_and_folds_away(self):
        self.open(self.LONG)
        footer_link = self.page.get_by_role("contentinfo").get_by_role("link").first
        with self.saving_artifacts():
            expect(self.button()).to_have_count(0)
            self.scroll_to(self.screens(2) + 10)
            button = self.button()
            expect(button).to_be_visible()
            expect(button).to_have_text("↑ 回到頂端")
            box = button.bounding_box()
            tab_bar = self.page.get_by_role("navigation", name="主要導覽").bounding_box()
            self.assertGreaterEqual(box["height"], 44)
            self.assertGreater(box["x"], 390 / 2)
            self.assertLessEqual(box["x"] + box["width"], 390)
            self.assertLessEqual(box["y"] + box["height"], tab_bar["y"])
            colour, background = button.evaluate(
                "b => [getComputedStyle(b).color, getComputedStyle(b).backgroundImage]"
            )
            self.assertEqual(colour, "rgb(255, 255, 255)")
            self.assertIn("rgb(31, 78, 140)", background)
            # Tab goes from the end of the content to the button, then on to the footer.
            self.tab_from_end_of_content()
            expect(button).to_be_focused()
            self.page.keyboard.press("Tab")
            expect(footer_link).to_be_focused()

            # The focus scrolls the footer link into view, smoothly; let that end first.
            self.page.wait_for_function(
                "() => { const still = scrollY === window.lastY; window.lastY = scrollY; "
                "return still; }",
                polling=200,
            )
            self.scroll_to(self.screens(2))
            expect(self.button()).to_have_count(0)
            self.tab_from_end_of_content()
            expect(footer_link).to_be_focused()

    # #338 acceptance 2 and 3
    def test_goes_to_the_title_smoothly_or_straight_with_reduced_motion(self):
        for motion, smooth in (("no-preference", True), ("reduce", False)):
            with self.subTest(motion=motion):
                self.open(self.LONG, motion=motion)
                # Smooth scrolling starts once the page and fonts are in (layout.html).
                expect(self.page.locator("html")).to_have_class(re.compile(r"\bsmooth-scroll\b"))
                # Fades in, or with reduced motion is simply there: read as it shows, before a
                # fade could end.
                fading = self.page.evaluate(
                    """async (y) => {
                        const scrolled = new Promise((done) => {
                            addEventListener("scroll", done, {once: true});
                        });
                        window.scrollTo({top: y, behavior: "instant"});
                        await scrolled;
                        const button = [...document.querySelectorAll("button")]
                            .find((b) => b.textContent.includes("回到頂端"));
                        return button.getAnimations()
                            .some((a) => a.transitionProperty === "opacity");
                    }""",
                    self.screens(3),
                )
                self.assertEqual(fading, smooth)
                button = self.button()
                expect(button).to_be_visible()
                # Right after the click a smooth scroll has only just begun.
                at_top = button.evaluate("b => { b.click(); return window.scrollY === 0; }")
                self.assertEqual(at_top, not smooth)
                self.page.wait_for_function("window.scrollY === 0")
                title = self.main().get_by_role("heading", level=1)
                expect(title).to_be_focused()
                expect(title).to_be_in_viewport()
                self.page.keyboard.press("Tab")
                self.assertTrue(self.page.evaluate(self.ON_NEXT_AFTER_TITLE))

    # #338 acceptance 4
    def test_short_page_has_no_button_at_its_foot(self):
        self.open(self.SHORT, height=844)
        with self.saving_artifacts():
            bottom = self.page.evaluate("document.documentElement.scrollHeight - innerHeight")
            self.assertLessEqual(bottom, self.screens(2))
            self.scroll_to(bottom)
            expect(self.button()).to_have_count(0)

    # #338 acceptance 5: at the foot of a long page the footer's last line stays above the
    # button; at 200% text, 320px wide, nothing scrolls sideways.
    def test_last_line_clears_the_button_and_double_text_fits(self):
        for width, double in ((390, False), (320, True)):
            with self.subTest(width=width, double_text=double):
                self.open(self.LONG, width=width, height=640)
                if double:
                    self.assert_fits_a_phone_at_double_text_size(self.LONG, width)
                # The footer's room for the button follows the tab bar's height, which the page
                # takes in a frame after the text grows: wait for it, or the page grows after the
                # scroll and its foot is no longer in view.
                self.page.wait_for_function(
                    """() => document.documentElement.style.getPropertyValue("--tab-bar-height")
                        === `${document.querySelector(".site-nav").offsetHeight}px`""",
                    timeout=5000,
                )
                self.scroll_to(self.page.evaluate("document.documentElement.scrollHeight"))
                button = self.button()
                expect(button).to_be_visible()
                last = self.page.get_by_role("contentinfo").locator("p").last.bounding_box()
                self.assertLessEqual(last["y"] + last["height"], button.bounding_box()["y"])
                self.assertLessEqual(
                    self.page.evaluate("document.documentElement.scrollWidth"), width
                )

    # #338 acceptance 6
    def test_no_button_on_paper_or_without_javascript(self):
        with self.subTest(media="print"):
            self.open(self.LONG)
            self.scroll_to(self.screens(3))
            expect(self.button()).to_be_visible()
            self.page.emulate_media(media="print")
            expect(self.button()).to_be_hidden()
        with self.subTest(javascript=False):
            self.open(self.LONG, javascript=False)
            self.scroll_to(self.screens(3))
            self.assertGreater(self.page.evaluate("window.scrollY"), self.screens(2))
            expect(self.page.get_by_text("回到頂端")).to_have_count(0)


class ScrollHintTest(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """Spec #338 (ticket #344): the compare page's number tables scroll sideways in their box,
    with a shadow on the side not yet seen and, when they do not fit, 表格可以左右滑動 above."""

    HINT = "表格可以左右滑動"
    # Under a shadow even the gaps between words are grey; without one some pixel is white.
    SHADED, CLEAR = 235, 250
    # The lightness of a screenshot's lightest pixel, read in a canvas as e2e/compare_shots.py
    # reads its screenshots: on a page of its own, as the page under test may have no JavaScript.
    LIGHTEST = """async (src) => {
        const image = await new Promise((resolve, reject) => {
            const loaded = new Image();
            loaded.onload = () => resolve(loaded);
            loaded.onerror = reject;
            loaded.src = src;
        });
        const canvas = new OffscreenCanvas(image.width, image.height);
        const context = canvas.getContext("2d");
        context.drawImage(image, 0, 0);
        const pixels = context.getImageData(0, 0, image.width, image.height).data;
        let lightest = 0;
        for (let i = 0; i < pixels.length; i += 4) {
            const [r, g, b] = pixels.subarray(i, i + 3);
            lightest = Math.max(lightest, Math.floor((r + g + b) / 3));
        }
        return lightest;
    }"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()
        cls.pixels = cls.browser.new_page()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        user = consented_user(username="scroll_hint_e2e")
        for tested_on, db in ((date(2026, 5, 1), 40), (date(2026, 9, 28), 55)):
            audiogram = Audiogram.objects.create(user=user, tested_on=tested_on)
            AudiogramPoint.objects.bulk_create(
                AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=db)
                for ear in ("right", "left")
                for f in (500, 1000, 2000, 4000)
            )
        self.client.force_login(user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, width, javascript=True, double_text=False):
        """The compare page with its numbers' fold open; the screen is tall enough for both."""
        self.context = self.browser.new_context(
            viewport={"width": width, "height": 1600}, java_script_enabled=javascript
        )
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)
        self.page.goto(f"{self.live_server_url}/audiograms/compare")
        self.page.wait_for_load_state("load")
        if double_text:
            self.double_text()
        self.numbers().locator("summary").click()

    def numbers(self):
        return self.main().locator("details", has_text="看每個頻率的數字")

    def boxes(self):
        """The two number tables' scrolling boxes, as a screen reader finds them."""
        boxes = self.numbers().get_by_role("region", name=re.compile("^右耳 "))
        expect(boxes).to_have_count(2)
        return boxes.all()

    def shown_hints(self):
        return self.main().get_by_text(self.HINT, exact=True).filter(visible=True)

    def overflows(self, box):
        return box.evaluate("box => box.scrollWidth > box.clientWidth")

    def scroll_to_end(self, box):
        box.evaluate("box => box.scrollTo({left: box.scrollWidth, behavior: 'instant'})")

    def edge_lightness(self, box):
        """How light the box's left and right edges are, at their lightest pixel, two pixels in.
        Measured mid-screen, clear of the bottom tab bar fixed over the page."""
        box.evaluate("box => box.scrollIntoView({block: 'center', behavior: 'instant'})")
        rect = box.bounding_box()
        lightness = []
        for x in (round(rect["x"]) + 2, round(rect["x"] + rect["width"]) - 3):
            png = self.page.screenshot(
                clip={"x": x, "y": round(rect["y"]), "width": 1, "height": int(rect["height"])}
            )
            source = "data:image/png;base64," + base64.b64encode(png).decode()
            lightness.append(self.pixels.evaluate(self.LIGHTEST, source))
        return lightness

    def assert_shaded(self, box, left, right):
        for side, shaded, lightness in zip(
            ("left", "right"), (left, right), self.edge_lightness(box), strict=True
        ):
            if shaded:
                self.assertLess(lightness, self.SHADED, f"{side} edge has no shadow")
            else:
                self.assertGreaterEqual(lightness, self.CLEAR, f"{side} edge has a shadow")

    # #338 acceptance 18
    def test_double_text_shows_the_hint_and_the_shadow_moves_to_the_left_at_the_end(self):
        self.open(320, double_text=True)
        with self.saving_artifacts():
            boxes = self.boxes()
            expect(self.shown_hints()).to_have_count(len(boxes))
            for box, hint in zip(boxes, self.shown_hints().all(), strict=True):
                self.assertTrue(self.overflows(box))
                # Just above its table.
                hint_box, table_box = hint.bounding_box(), box.bounding_box()
                gap = table_box["y"] - (hint_box["y"] + hint_box["height"])
                self.assertGreaterEqual(gap, 0)
                self.assertLess(gap, 20)
                self.assert_shaded(box, left=False, right=True)
                self.scroll_to_end(box)
                self.assert_shaded(box, left=True, right=False)

    # #338 acceptance 19; and the hint follows the text size and the screen's width.
    def test_fitting_tables_have_no_shadow_or_hint_and_the_hint_follows_size_changes(self):
        self.open(390)
        with self.saving_artifacts():
            for box in self.boxes():
                self.assertFalse(self.overflows(box))
                self.assert_shaded(box, left=False, right=False)
            expect(self.shown_hints()).to_have_count(0)
            self.page.set_viewport_size({"width": 320, "height": 1600})
            self.double_text()
            expect(self.shown_hints()).to_have_count(2)
            self.double_text(on=False)
            expect(self.shown_hints()).to_have_count(0)
            self.double_text()
            expect(self.shown_hints()).to_have_count(2)
            self.page.set_viewport_size({"width": 1280, "height": 1600})
            expect(self.shown_hints()).to_have_count(0)

    # #338 acceptance 20
    def test_without_javascript_the_shadow_stays_and_paper_shows_neither(self):
        with self.subTest(javascript=False):
            self.open(320, javascript=False, double_text=True)
            for box in self.boxes():
                self.assertTrue(self.overflows(box))
                self.assert_shaded(box, left=False, right=True)
            expect(self.main().get_by_text(self.HINT)).to_have_count(0)
        with self.subTest(media="print"):
            self.open(320, double_text=True)
            expect(self.shown_hints()).to_have_count(2)
            self.page.emulate_media(media="print")
            expect(self.shown_hints()).to_have_count(0)
            for box in self.boxes():
                self.assert_shaded(box, left=False, right=False)


class ScrollHelpersOnAPhone(OnAPhone):
    """Spec #338's play-in-view, meter and jump tests: on a phone, signed in as a returning user
    with an HHIE-S record (every answer 2, so 20 of 40) and an audiogram, each ear at one level
    across the four frequencies (RIGHT_DB, LEFT_DB)."""

    fixtures = ("questions_fixture.json",)
    RIGHT_DB = LEFT_DB = 55

    def setUp(self):
        self.user = consented_user(username="scroll_helpers_e2e")
        self.hhie_s = Questionnaire.objects.get(code="hhie-s")
        self.submission = Submission.objects.create(
            user=self.user, questionnaire=self.hhie_s, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=self.submission, question=question, score=2)
            for question in self.hhie_s.questions.all()
        )
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 1))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=db)
            for ear, db in (("right", self.RIGHT_DB), ("left", self.LEFT_DB))
            for f in (500, 1000, 2000, 4000)
        )
        self.client.force_login(self.user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def bring_into_view(self, selector):
        self.page.locator(selector).evaluate(
            "el => el.scrollIntoView({block: 'center', behavior: 'instant'})"
        )

    def wait_until(self, selector, state):
        """Until every animation in the first match of selector (itself, what is inside it and
        their ::before and ::after) is in that state, each one started."""
        self.page.wait_for_function(
            """([selector, state]) => {
                const all = document.querySelector(selector).getAnimations({subtree: true});
                return all.length && all.every(a => a.playState === state && a.startTime !== null);
            }""",
            arg=[selector, state],
        )


class PlayInViewTest(SavesFailureArtifacts, ScrollHelpersOnAPhone, StaticLiveServerTestCase):
    """Spec #338 (ticket #341, ADR 0029): entrance animations play once they are in view; on a
    phone, signed in as a returning user (the home's gauge) whose guide has a 目前這一站. Having
    read nothing, the 目前這一站 is 去找聽力師之前 (as in HearingAidGuideTest); HHIE-S at 20 of
    40 puts the home gauge's needle at 90 degrees."""

    # Each animation's name and state, by what it moves: route-ring on the 目前這一站, gauge-draw
    # and gauge-needle on the home's gauge, wave-jump and wave-sweep on the header.
    ANIMATIONS = """(within) => document.getAnimations()
        .filter(a => a.effect.target.closest(within))
        .map(a => ({ name: a.animationName, state: a.playState, time: a.currentTime }))"""
    STOP = '[aria-current="step"]'
    GAUGE = ".score-gauge"
    WAVE = ".site-wave"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def open(
        self,
        path,
        width=390,
        height=640,
        javascript=True,
        motion="no-preference",
        double=False,
        prepare=None,
    ):
        """prepare, if given, is called with the browser context before the page opens."""
        self.context = self.browser.new_context(
            viewport={"width": width, "height": height},
            java_script_enabled=javascript,
            reduced_motion=motion,
        )
        self.context.add_cookies([self.cookie])
        if double:
            # Set before the page's scripts run, so the page is judged at that size from the start.
            self.context.add_init_script(
                f"""document.addEventListener("readystatechange", () => {{
                    document.documentElement.style.setProperty(
                        "font-size", "{self.DOUBLE_TEXT_SIZE}", "important");
                }}, {{ once: true }});"""
            )
        if prepare:
            prepare(self.context)
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)
        self.page.goto(f"{self.live_server_url}{path}")

    def animations(self, within):
        return self.page.evaluate(self.ANIMATIONS, within)

    def states(self, within):
        return {a["state"] for a in self.animations(within)}

    def scroll_by(self, y):
        self.page.evaluate("y => window.scrollBy({top: y, behavior: 'instant'})", y)

    # #338 acceptance 7: below the screen the ring waits; partly showing, or with its foot under
    # the tab bar, it still waits; wholly in view it plays once, and coming back does not replay.
    def test_current_stop_ring_plays_once_in_view(self):
        self.open("/guide")
        with self.saving_artifacts():
            here = self.main().locator(self.STOP)
            expect(here).to_contain_text("去找聽力師之前")
            expect(here).not_to_be_in_viewport()
            self.assertEqual(
                self.animations(self.STOP), [{"name": "route-ring", "state": "paused", "time": 0}]
            )
            # Its top just showing above the tab bar.
            tab_bar = self.page.get_by_role("navigation", name="主要導覽").bounding_box()
            self.scroll_by(here.bounding_box()["y"] - tab_bar["y"] + 20)
            expect(here).to_be_in_viewport()
            self.assertEqual(self.states(self.STOP), {"paused"})
            # On the screen, but its foot 10px under the tab bar.
            box = here.bounding_box()
            self.assertLess(box["height"], tab_bar["y"] / 2)
            self.scroll_by(box["y"] + box["height"] - tab_bar["y"] - 10)
            self.assertGreaterEqual(here.bounding_box()["y"], 0)
            self.assertEqual(self.states(self.STOP), {"paused"})

            self.bring_into_view(self.STOP)
            self.wait_until(self.STOP, "finished")
            ended = self.animations(self.STOP)
            # Away and back again: still ended, not playing a second time.
            self.page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
            self.bring_into_view(self.STOP)
            self.page.wait_for_timeout(300)
            self.assertEqual(self.animations(self.STOP), ended)

    # #338 acceptance 10 (this ticket's part): with reduced motion the route's ring and the
    # home's gauge are their end look from the start, nothing playing or waiting to play.
    def test_reduced_motion_shows_the_end_at_once(self):
        self.open("/guide", motion="reduce")
        with self.saving_artifacts():
            expect(self.main().locator(self.STOP)).to_have_count(1)
            self.assertEqual(self.page.evaluate("document.getAnimations().length"), 0)
            self.page.goto(f"{self.live_server_url}/")
            needle = self.page.locator(".score-gauge-needle")
            expect(needle).to_be_attached()
            self.assertEqual(self.page.evaluate("document.getAnimations().length"), 0)
            # At the score, 90 degrees: rotate(90deg) as a matrix.
            expect(needle).to_have_css("transform", "matrix(0, 1, -1, 0, 0, 0)")

    # #338 acceptance 11 (this ticket's part): without JavaScript nothing waits for the screen:
    # the ring below it and the gauge play on arrival, and the header wave on every page.
    def test_without_javascript_animations_play_on_arrival(self):
        self.open("/guide", javascript=False)
        with self.saving_artifacts():
            expect(self.main().locator(self.STOP)).not_to_be_in_viewport()
            self.assertEqual(self.states(self.STOP), {"running"})
            self.assertEqual(self.states(self.WAVE), {"running"})
            self.page.goto(f"{self.live_server_url}/")
            self.assertEqual(self.states(self.GAUGE), {"running"})
            self.assertEqual(self.states(self.WAVE), {"running"})

    # #338 acceptance 12: at 200% text on a phone the returning user's gauge is below the screen
    # and waits; the header wave, on screen, plays at once (on the tab's first page only).
    def test_double_text_gauge_waits_and_header_wave_plays_at_once(self):
        self.open("/", width=320, double=True)
        with self.saving_artifacts():
            gauge = self.page.locator(self.GAUGE)
            tab_bar = self.page.get_by_role("navigation", name="主要導覽").bounding_box()
            box = gauge.bounding_box()
            self.assertGreater(box["y"] + box["height"], tab_bar["y"])
            self.assertEqual(
                {a["name"]: a["state"] for a in self.animations(self.GAUGE)},
                {"gauge-draw": "paused", "gauge-needle": "paused"},
            )
            self.assertEqual(self.states(self.WAVE), {"running"})
            # Not yet drawn: the needle still at 0, rotate(0deg) as a matrix.
            expect(gauge.locator(".score-gauge-needle")).to_have_css(
                "transform", "matrix(1, 0, 0, 1, 0, 0)"
            )

            self.bring_into_view(self.GAUGE)
            self.wait_until(self.GAUGE, "finished")
            expect(gauge.locator(".score-gauge-needle")).to_have_css(
                "transform", "matrix(0, 1, -1, 0, 0, 0)"
            )
            self.page.goto(f"{self.live_server_url}/questionnaire_list")
            self.assertEqual(self.animations(self.WAVE), [])

    # #338 review: the layout changing without a scroll (here the text going back to its usual
    # size; a fold opening, a late font or a chart growing does the same) brings the gauge into
    # view, and it plays.
    def test_gauge_plays_when_the_layout_brings_it_into_view(self):
        self.open("/", width=320, double=True)
        with self.saving_artifacts():
            expect(self.page.locator(self.GAUGE)).to_be_attached()
            self.page.wait_for_timeout(300)
            self.assertEqual(self.states(self.GAUGE), {"paused"})
            self.double_text(on=False)
            self.wait_until(self.GAUGE, "finished")
            self.assertEqual(self.page.evaluate("window.scrollY"), 0)

    # #338 review: when scroll-helpers.js never runs (here it fails to load), nothing waits for
    # ever: about 3 seconds after the page starts, the animations play as without JavaScript,
    # the ring below the screen too.
    def test_animations_play_anyway_when_the_scroll_helpers_fail_to_load(self):
        self.open(
            "/guide",
            prepare=lambda context: context.route("**/scroll-helpers.js", lambda r: r.abort()),
        )
        with self.saving_artifacts():
            here = self.main().locator(self.STOP)
            expect(here).not_to_be_in_viewport()
            self.assertEqual(self.states(self.STOP), {"paused"})
            self.wait_until(self.STOP, "finished")
            expect(here).not_to_be_in_viewport()
            # Started about 3 seconds after the page did (the document timeline's 0).
            start = here.evaluate("el => el.getAnimations({subtree: true})[0].startTime")
            self.assertGreaterEqual(start, 3000)
            self.assertLess(start, 4500)

    # #338 review: each helper sets up on its own. Without ResizeObserver (iPhones before iOS
    # 13.4) the back-to-top button, set up before the others, cannot finish; the entrance
    # animations still wait to be in view, and a jump still lights its box.
    def test_one_helper_failing_leaves_the_others_working(self):
        self.open(
            "/guide",
            prepare=lambda context: context.add_init_script("delete window.ResizeObserver"),
        )
        with self.saving_artifacts():
            expect(self.main().locator(self.STOP)).not_to_be_in_viewport()
            # Past the 3 seconds after which the animations would stop waiting.
            self.page.wait_for_timeout(3500)
            self.assertEqual(self.states(self.STOP), {"paused"})
            self.bring_into_view(self.STOP)
            self.wait_until(self.STOP, "finished")

            self.page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
            self.main().get_by_role("link", name="看我的路線").click()
            route = self.main().locator('section[aria-labelledby="contents-title"]')
            expect(route).to_have_css("outline-color", "rgb(31, 78, 140)")
            expect(route).to_have_css("outline-style", "solid")


class GuideMeterFillTest(SavesFailureArtifacts, ScrollHelpersOnAPhone, StaticLiveServerTestCase):
    """Spec #338 (ticket #342, ADR 0029): my guide's meters fill from 0 once they are in view,
    the two ears together, the ratio on its own; on a phone, for a user with an HHIE-S record
    (so the meters start below the screen) and an audiogram of 60 and 50 dB HL (a 40.0% ratio)."""

    RIGHT_DB, LEFT_DB = 60, 50
    EARS = 'section[aria-labelledby="fitting-title"] .meter'
    RATIO = 'section[aria-labelledby="threshold-title"] .meter'
    # Each animation in the meter: its name, state, time, start, length, and the class of what
    # it moves.
    ANIMATIONS = """(meter) => meter.getAnimations({subtree: true}).map(a => ({
        name: a.animationName, state: a.playState, time: a.currentTime, start: a.startTime,
        duration: a.effect.getComputedTiming().duration, target: a.effect.target.className,
    }))"""
    # How full each bar is drawn, as a share of its track.
    FILLS = """(meter) => [...meter.querySelectorAll(".meter-bar")].map(
        bar => bar.getBoundingClientRect().width / bar.parentElement.clientWidth)"""
    # The first bar's fill, as a share of where it ends, every 100ms through its animation.
    CURVE = """(meter) => {
        const bar = meter.querySelector(".meter-bar");
        const [fill] = bar.getAnimations();
        const end = bar.getBoundingClientRect().width;
        fill.pause();
        const shares = [];
        for (let time = 0; time <= 1200; time += 100) {
            fill.currentTime = time;
            shares.push(bar.getBoundingClientRect().width / end);
        }
        fill.finish();
        return shares;
    }"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def open(self, path="/guide", javascript=True, motion="no-preference"):
        self.context = self.browser.new_context(
            viewport={"width": 390, "height": 640},
            java_script_enabled=javascript,
            reduced_motion=motion,
        )
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)
        self.page.goto(f"{self.live_server_url}{path}")

    def animations(self, meter):
        return self.page.locator(meter).evaluate(self.ANIMATIONS)

    def assert_fills(self, meter, expected):
        found = self.page.locator(meter).evaluate(self.FILLS)
        self.assertEqual(len(found), len(expected))
        for fill, share in zip(found, expected, strict=True):
            self.assertAlmostEqual(fill, share, delta=0.01)

    def assert_below_the_tab_bar(self, meter):
        """The meter is not wholly in view: its foot is under the tab bar or below the screen."""
        tab_bar = self.page.get_by_role("navigation", name="主要導覽").bounding_box()
        box = self.page.locator(meter).bounding_box()
        self.assertGreater(box["y"] + box["height"], tab_bar["y"])

    def assert_ear_numbers(self):
        ears = self.page.locator(self.EARS)
        expect(ears).to_contain_text("右耳四頻平均 60 dB HL")
        expect(ears).to_contain_text("左耳四頻平均 50 dB HL")

    # #338 acceptance 8: below the screen both ear bars wait at 0; with their box wholly in
    # view they grow together, from 0 to their numbers over 1.2 seconds, quickly at first, then
    # slowly, never past the end. Only the bars move, not the line or its label, and the numbers
    # beside them are the end ones throughout.
    def test_ear_bars_fill_together_once_in_view(self):
        self.open()
        with self.saving_artifacts():
            ears = self.page.locator(self.EARS)
            self.assert_below_the_tab_bar(self.EARS)
            waiting = self.animations(self.EARS)
            self.assertEqual(
                [(a["name"], a["state"], a["time"], a["target"]) for a in waiting],
                [("meter-fill", "paused", 0, f"meter-bar meter-bar-{side}")
                 for side in ("right", "left")],
            )  # fmt: skip
            self.assert_fills(self.EARS, (0, 0))
            self.assert_ear_numbers()

            self.bring_into_view(self.EARS)
            self.wait_until(self.EARS, "running")
            playing = self.animations(self.EARS)
            self.assertEqual(len({a["start"] for a in playing}), 1)
            self.assertEqual({a["duration"] for a in playing}, {1200})
            self.assert_ear_numbers()

            self.wait_until(self.EARS, "finished")
            self.assert_fills(self.EARS, (60 / 120, 50 / 120))
            self.assert_ear_numbers()
            curve = ears.evaluate(self.CURVE)
            self.assertEqual(curve[0], 0)
            self.assertAlmostEqual(curve[-1], 1, delta=0.001)
            self.assertEqual(curve, sorted(curve))
            self.assertLessEqual(max(curve), 1.001)
            # Quick at first: three quarters of the way by half time.
            self.assertGreater(curve[6], 0.75)

    # #338 acceptance 9: the ratio's bar, in a box of its own, still waits at 0 after the ears
    # have filled, and fills only once it is in view. With a no-response point its hatched part
    # is in place from the start and only the bar grows into it.
    def test_ratio_bar_waits_for_its_own_box(self):
        self.open()
        with self.saving_artifacts():
            ratio = self.page.locator(self.RATIO)
            expect(ratio).to_contain_text("雙耳障礙比率（估算） 約 40.0%")
            # The ears' box wholly in view just above the tab bar, the ratio's still below it.
            tab_bar = self.page.get_by_role("navigation", name="主要導覽").bounding_box()
            ears = self.page.locator(self.EARS).bounding_box()
            self.page.evaluate(
                "y => window.scrollBy({top: y, behavior: 'instant'})",
                ears["y"] + ears["height"] - tab_bar["y"] + 10,
            )
            self.wait_until(self.EARS, "finished")
            self.assert_below_the_tab_bar(self.RATIO)
            self.assertEqual(
                [(a["state"], a["time"]) for a in self.animations(self.RATIO)], [("paused", 0)]
            )
            self.assert_fills(self.RATIO, (0,))

            self.bring_into_view(self.RATIO)
            self.wait_until(self.RATIO, "finished")
            self.assert_fills(self.RATIO, (0.40,))
            expect(ratio).to_contain_text("雙耳障礙比率（估算） 約 40.0%")

            # 40 and 80 dB HL, the left unheard at 4000 Hz: at least about 35.0%.
            points = AudiogramPoint.objects.filter(audiogram__user=self.user)
            points.filter(ear="right").update(db=40)
            points.filter(ear="left").update(db=80)
            points.filter(ear="left", frequency=4000).update(db=DB_MAX["air"], no_response=True)
            self.page.goto(f"{self.live_server_url}/guide")
            expect(ratio).to_contain_text("雙耳障礙比率（估算） 至少約 35.0%")
            self.assertEqual(
                [(a["state"], a["time"], a["target"]) for a in self.animations(self.RATIO)],
                [("paused", 0, "meter-bar meter-bar-ratio")],
            )
            self.assert_fills(self.RATIO, (0,))
            hatched_from = ratio.evaluate(
                """meter => {
                    const track = meter.querySelector(".meter-track");
                    const beyond = meter.querySelector(".meter-beyond").getBoundingClientRect();
                    return (beyond.left - track.getBoundingClientRect().left - track.clientLeft)
                        / track.clientWidth;
                }"""
            )
            self.assertAlmostEqual(hatched_from, 0.35, delta=0.01)

    # #338 acceptance 10 (this ticket's part): with reduced motion the meters are drawn to their
    # numbers from the start, below the screen, with nothing playing.
    def test_reduced_motion_draws_the_meters_full_at_once(self):
        self.open(motion="reduce")
        with self.saving_artifacts():
            self.assert_below_the_tab_bar(self.RATIO)
            for meter, fills in ((self.EARS, (60 / 120, 50 / 120)), (self.RATIO, (0.40,))):
                self.assertEqual(self.animations(meter), [], meter)
                self.assert_fills(meter, fills)

    # #338 acceptance 11 (this ticket's part): without JavaScript nothing waits for the screen:
    # both meters fill on arrival, though below it.
    def test_without_javascript_meters_fill_on_arrival(self):
        self.open(javascript=False)
        with self.saving_artifacts():
            self.assert_below_the_tab_bar(self.RATIO)
            for meter, count in ((self.EARS, 2), (self.RATIO, 1)):
                self.assertEqual(
                    [(a["name"], a["state"]) for a in self.animations(meter)],
                    [("meter-fill", "running")] * count,
                    meter,
                )

    # #338 acceptance 21: the result page's score position bar and SSQ12's position bar stay
    # still, scrolled to or not.
    def test_result_position_bars_stay_still(self):
        call_command("seed_questionnaires", verbosity=0)
        ssq12 = Questionnaire.objects.get(code="ssq12-tw")
        ssq12_record = Submission.objects.create(
            user=self.user, questionnaire=ssq12, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=ssq12_record, question=question, score=5)
            for question in ssq12.questions.all()
        )
        self.open(f"/submission/{self.submission.pk}")
        with self.saving_artifacts():
            for record, bar in ((self.submission, ".score-bar"), (ssq12_record, ".ssq-bar")):
                self.page.goto(f"{self.live_server_url}/submission/{record.pk}")
                found = self.page.locator(bar)
                expect(found).to_be_attached()
                self.page.evaluate("window.scrollTo({top: 99999, behavior: 'instant'})")
                found.evaluate("el => el.scrollIntoView({block: 'center', behavior: 'instant'})")
                self.page.wait_for_timeout(300)
                self.assertEqual(
                    found.evaluate("el => el.getAnimations({subtree: true}).length"), 0, bar
                )


class JumpHighlightTest(SavesFailureArtifacts, ScrollHelpersOnAPhone, StaticLiveServerTestCase):
    """Spec #338 (ticket #343, ADR 0029): the box a jump lands on lights up in the brand blue
    with a pale blue glow, about 3 seconds; on a phone, signed in as a returning user."""

    # 50 dB in both ears is a 37.5% ratio, short of the threshold, so my guide offers
    # 「看沒有身障證明時」.
    RIGHT_DB = LEFT_DB = 50
    # Every frame for a while, what the reader sees of one box: its outline and glow, where it
    # is on the screen (and where the tab bar starts), and how far the page has scrolled.
    SAMPLE = """([selector, ms]) => {
        const start = () => {
            const samples = window.samples = [];
            const t0 = performance.now();
            const tick = () => {
                const box = document.querySelector(selector);
                const style = getComputedStyle(box);
                const rect = box.getBoundingClientRect();
                samples.push({
                    t: performance.now() - t0, y: scrollY,
                    outline: style.outlineStyle === "none" ? "none" : style.outlineColor,
                    glow: style.boxShadow, top: rect.top, bottom: rect.bottom,
                    visible: document.querySelector(".site-nav").getBoundingClientRect().top,
                });
                if (samples.at(-1).t < ms) requestAnimationFrame(tick); else window.sampled = true;
            };
            tick();
        };
        if (document.readyState === "loading") addEventListener("DOMContentLoaded", start);
        else start();
    }"""
    COLOUR = re.compile(r"rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)")
    CERTIFICATE = 'section[aria-labelledby="without-certificate"]'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def open(self, path, motion="no-preference"):
        self.context = self.browser.new_context(
            viewport={"width": 390, "height": 640}, reduced_motion=motion
        )
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)
        self.page.goto(f"{self.live_server_url}{path}")
        # Smooth scrolling starts once the page and its fonts are in (layout.html).
        expect(self.page.locator("html")).to_have_class(re.compile(r"\bsmooth-scroll\b"))

    def sample_next_page(self, selector, ms=6000):
        self.context.add_init_script(f"({self.SAMPLE})(['{selector}', {ms}])")

    def sample_this_page(self, selector, ms=6000):
        self.page.evaluate(self.SAMPLE, [selector, ms])

    def samples(self):
        self.page.wait_for_function("window.sampled", timeout=15000)
        return self.page.evaluate("window.samples")

    def light(self, sample):
        """How strongly the outline and the glow show the brand blue, 0 to 1 (0.25 is the
        glow's full strength): 0 for none, or another colour."""

        def alpha(text):
            found = self.COLOUR.search(text)
            if not found or tuple(map(int, found.groups()[:3])) != (31, 78, 140):
                return 0
            return float(found.group(4) or 1)

        return alpha(sample["outline"]), alpha(sample["glow"])

    def assert_lights(self, samples, reduced=False, scrolled=False):
        lit = [s for s in samples if self.light(s)[0] > 0]
        self.assertTrue(lit, "the box never lit")
        on, off = lit[0]["t"], lit[-1]["t"]
        # Lit once, in one go.
        self.assertEqual(lit, [s for s in samples if on <= s["t"] <= off])
        after = [s for s in samples if s["t"] > off]
        # Only once the page had stopped moving (after scrolling there, when it did), with the
        # box in view above the tab bar, wholly or filling half of what shows.
        first = lit[0]
        if scrolled:
            self.assertNotEqual(samples[0]["y"], first["y"])
        # Not moving from then on. (A scroll event may still come a frame later for a scroll
        # already done, as the page opens: the position is what counts.)
        self.assertEqual({s["y"] for s in lit + after}, {first["y"]})
        visible = first["visible"]
        shown = min(first["bottom"], visible) - max(first["top"], 0)
        self.assertTrue(
            (first["top"] >= 0 and first["bottom"] <= visible) or shown >= visible / 2, first
        )
        # Held at full strength about 1.5 seconds: the brand blue, a pale blue glow.
        for sample in samples:
            if on <= sample["t"] <= on + 1300:
                self.assertEqual(self.light(sample), (1, 0.25), sample)
        # Then fading for 1.5 seconds, or, with reduced motion, full until it goes at once.
        fading = [s for s in lit if 0 < self.light(s)[0] < 1]
        if reduced:
            self.assertEqual(fading, [])
        else:
            self.assertTrue([s for s in fading if on + 1700 <= s["t"] <= on + 2700], lit)
        self.assertGreater(off - on, 2800)
        self.assertLess(off - on, 3300)
        # And back as it was.
        self.assertTrue(after)
        self.assertEqual({self.light(s) for s in after}, {(0, 0)})

    def assert_never_lights(self, samples):
        """Neither the brand-blue outline nor the glow, at any moment."""
        self.assertEqual({self.light(s) for s in samples}, {(0, 0)})

    # #338 acceptance 13: from my guide to the form 9 chapter, landing on 沒有身障證明時; the
    # 段落框 lights once the page is still, holds, and fades within about 3 seconds.
    # Acceptance 16: with reduced motion it shows at once and goes at once 3 seconds later.
    def test_section_box_lights_after_a_jump_from_another_page(self):
        for motion in ("no-preference", "reduce"):
            with self.subTest(motion=motion):
                self.open("/guide", motion=motion)
                with self.saving_artifacts():
                    self.sample_next_page(self.CERTIFICATE)
                    self.main().get_by_role("link", name="看沒有身障證明時").first.click()
                    expect(self.page).to_have_url(re.compile(r"/guide/form-9#without-certificate$"))
                    samples = self.samples()
                    self.assert_lights(samples, reduced=motion == "reduce")
                    if motion == "reduce":
                        self.assertEqual(self.page.evaluate("document.getAnimations().length"), 0)

    # Acceptance 14: the family page's topic cards, on the page and from the shared report; the
    # whole topic lights, heading and block (marked a 並列區塊).
    def test_family_topic_lights_on_the_page_and_from_the_shared_report(self):
        topic = 'section[aria-labelledby="{}"]'
        self.open("/family")
        with self.saving_artifacts():
            self.sample_this_page(topic.format("aid-title"))
            self.main().get_by_role("link", name="陪伴配戴助聽器").click()
            self.assert_lights(self.samples(), scrolled=True)

            share = ReportShare.objects.create(user=self.user)
            self.page.goto(f"{self.live_server_url}/shared/{share.token}/report")
            self.sample_next_page(topic.format("talk-title"))
            self.page.get_by_role("link", name="怎麼跟聽損的家人說話").click()
            expect(self.page).to_have_url(re.compile(r"/family#talk-title$"))
            self.assert_lights(self.samples())

        # The urgent topic is a card of its own, with a look of its own; it lights the same way,
        # with reduced motion too.
        for motion in ("no-preference", "reduce"):
            with self.subTest(motion=motion):
                self.open("/family", motion=motion)
                self.sample_this_page(topic.format("urgent-title"))
                self.main().get_by_role("link", name="什麼時候要馬上就醫").click()
                self.assert_lights(self.samples(), reduced=motion == "reduce", scrolled=True)

    # Acceptance 15: 看我的路線 lights the route's 段落框, the focus still on its heading; a
    # stop's 修改 lights that stop.
    def test_route_and_its_stop_light(self):
        AidAndSubsidy.objects.create(user=self.user, certificate="yes")
        self.open("/guide")
        with self.saving_artifacts():
            self.sample_this_page('section[aria-labelledby="contents-title"]')
            self.main().get_by_role("link", name="看我的路線").click()
            heading = self.main().get_by_role("heading", name="選配與補助，一步一步看")
            expect(heading).to_be_focused()
            self.assert_lights(self.samples(), scrolled=True)
            expect(heading).to_be_focused()

            self.sample_next_page("#stop-assessment .route-box")
            self.main().get_by_role("link", name="修改身障鑑定與鑑定醫院的回答").click()
            expect(self.page).to_have_url(re.compile(r"\?edit=assessment#stop-assessment$"))
            self.assert_lights(self.samples())

    # Acceptance 17: the skip link and the answer page's error summary light nothing; the
    # question keeps only its red marking.
    def test_skip_link_and_error_summary_light_nothing(self):
        self.open("/family")
        with self.saving_artifacts():
            self.sample_this_page("main", ms=1500)
            self.page.keyboard.press("Tab")
            self.page.keyboard.press("Enter")
            expect(self.main()).to_be_focused()
            self.assert_never_lights(self.samples())

            # Sent with nothing answered, past the browser's own check, for the server's summary.
            self.page.goto(f"{self.live_server_url}/questionnaire/{self.hhie_s.pk}")
            with self.page.expect_navigation():
                self.page.evaluate("document.getElementById('answer-form').submit()")
            expect(self.page.locator("html")).to_have_class(re.compile(r"\bsmooth-scroll\b"))
            summary = self.page.locator("#error-summary")
            self.sample_this_page("#question-3", ms=1500)
            summary.get_by_role("link", name="第 3 題").click()
            expect(self.page).to_have_url(re.compile(r"#question-3$"))
            self.assert_never_lights(self.samples())
            # Its red marking is still there: the error under the question, in the error red.
            error = self.page.locator("#question-3").get_by_text("這一題還沒有回答")
            expect(error).to_be_visible()
            expect(error).to_have_css("color", "rgb(143, 42, 18)")

    # Acceptance 17's other error summary: the 配戴比較 form's links light nothing either.
    def test_comparison_form_error_links_light_nothing(self):
        aided = Submission.objects.create(
            user=self.user, questionnaire=self.hhie_s, wearing_hearing_aid=True
        )
        Answer.objects.bulk_create(
            Answer(submission=aided, question=question, score=0)
            for question in self.hhie_s.questions.all()
        )
        # 查看比較 with neither record chosen.
        self.open(f"/comparisons/{self.hhie_s.pk}?action=preview")
        with self.saving_artifacts():
            errors = self.page.locator("#comparison-errors")
            for name, target in (("沒戴助聽器時", "#id_unaided_0"), ("戴助聽器時", "#id_aided_0")):
                self.sample_this_page(target, ms=1500)
                errors.get_by_role("link", name=name, exact=True).click()
                expect(self.page).to_have_url(re.compile(f"{target}$"))
                self.assert_never_lights(self.samples())


class FooterPinButtonRowsT359Test(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#359 (spec #354, 全站共通): the footer at the window's foot on short pages, the gap between
    the danger and cancel buttons, and the step-by-step button rows on phones."""

    fixtures = ("questions_fixture.json",)
    DESKTOP = (1440, 900)
    PHONE = (390, 844)
    SHORT_PAGES = ("/shared/no-such-link", "/add_to_home", "/audiograms/new")
    # The footer's top edge and the box above it, both in pixels from the page's top.
    FOOTER_GAP = """() => {
        const footer = document.querySelector(".site-footer").getBoundingClientRect();
        const main = document.getElementById("main-content").getBoundingClientRect();
        return footer.top - main.bottom;
    }"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.user = consented_user(username="footer_pin_e2e", password="Fake-pass-2468")
        self.client.force_login(self.user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, path, size):
        width, height = size
        self.context = self.browser.new_context(viewport={"width": width, "height": height})
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)
        self.page.goto(f"{self.live_server_url}{path}")
        self.page.wait_for_load_state("load")

    def rem(self):
        return self.page.evaluate("parseFloat(getComputedStyle(document.documentElement).fontSize)")

    # Acceptance 1: a short page's footer ends at the window's foot, the arch keeps at least its
    # 5.5rem above it, and on a phone the tab bar covers none of the footer's words.
    def test_short_pages_pin_the_footer_to_the_bottom(self):
        with self.saving_artifacts():
            for size in (self.DESKTOP, self.PHONE):
                for path in self.SHORT_PAGES:
                    with self.subTest(path=path, width=size[0]):
                        self.open(path, size)
                        self.page.evaluate("window.scrollTo({top: 1e6, behavior: 'instant'})")
                        footer = self.page.locator(".site-footer").bounding_box()
                        self.assertAlmostEqual(footer["y"] + footer["height"], size[1], delta=1)
                        gap = self.page.evaluate(self.FOOTER_GAP)
                        self.assertGreaterEqual(gap, 5.5 * self.rem() - 1)
                        if size == self.PHONE:
                            tab_bar = self.page.locator(".site-nav").bounding_box()
                            last_line = self.page.locator(".site-footer p").last.bounding_box()
                            self.assertLessEqual(last_line["y"] + last_line["height"], tab_bar["y"])

    # Acceptance 1: on a long page the gap above the footer is the 5.5rem it was before.
    def test_long_page_keeps_the_gap_above_the_footer(self):
        with self.saving_artifacts():
            for size in (self.DESKTOP, self.PHONE):
                with self.subTest(width=size[0]):
                    self.open("/privacy", size)
                    self.assertGreater(
                        self.page.evaluate("document.documentElement.scrollHeight"), size[1]
                    )
                    gap = self.page.evaluate(self.FOOTER_GAP)
                    self.assertAlmostEqual(gap, 5.5 * self.rem(), delta=1)

    # Acceptance 3: 確定刪除 (刪除帳號) and 取消 are at least 1rem apart, side by side or stacked.
    def test_delete_and_cancel_stand_apart(self):
        with self.saving_artifacts():
            audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 1))
            pages = (
                (f"/audiograms/{audiogram.pk}/delete", "確定刪除"),
                ("/account/delete", "刪除帳號"),
            )
            for size in (self.DESKTOP, self.PHONE):
                for path, danger in pages:
                    with self.subTest(path=path, width=size[0]):
                        self.open(path, size)
                        main = self.main()
                        first = main.get_by_role("button", name=danger, exact=True).bounding_box()
                        cancel = main.get_by_role("link", name="取消", exact=True).bounding_box()
                        beside = cancel["x"] - (first["x"] + first["width"])
                        below = cancel["y"] - (first["y"] + first["height"])
                        self.assertGreaterEqual(max(beside, below), self.rem() - 0.5)

    def buttons(self, names):
        return [self.main().get_by_role(role, name=name, exact=True) for role, name in names]

    def assert_row_filled(self, names):
        """On a phone the row's buttons share its whole width: one fills it, two take half each."""
        buttons = self.buttons(names)
        for button in buttons:
            expect(button).to_be_visible()
        # Measured at one moment: after 下一題 the page may still be scrolling to the question.
        row, *boxes = buttons[0].evaluate(
            "el => [el.parentElement, ...el.parentElement.querySelectorAll(':scope > .btn')]"
            ".map((part) => part.getBoundingClientRect().toJSON())"
        )
        self.assertEqual(len(boxes), len(names))
        first, last = boxes[0], boxes[-1]
        self.assertAlmostEqual(first["x"], row["x"], delta=1)
        self.assertAlmostEqual(last["x"] + last["width"], row["x"] + row["width"], delta=1)
        if len(buttons) == 2:
            self.assertAlmostEqual(first["width"], last["width"], delta=1)
            self.assertAlmostEqual(first["y"], last["y"], delta=1)

    def assert_words_wide(self, names):
        """Each button is as wide as its words, under half its row."""
        for (_, name), button in zip(names, self.buttons(names), strict=True):
            row = button.evaluate("el => el.parentElement.getBoundingClientRect().width")
            self.assertLess(button.bounding_box()["width"], row / 2, name)

    WIZARD = (("link", "上一步"), ("button", "下一步"))

    # Acceptance 4: the wizard's 上一步／下一步 fill the row on a phone; a wide screen is as before.
    def test_wizard_buttons_fill_the_row_on_a_phone(self):
        with self.saving_artifacts():
            self.open("/questionnaire_list", self.PHONE)
            self.assert_row_filled(self.WIZARD)
            self.open("/questionnaire_list", self.DESKTOP)
            self.assert_words_wide(self.WIZARD)

    # Acceptance 4: 下一題 alone fills the row; 上一題 with 下一題, then with 送出, take half each.
    def test_answer_buttons_fill_the_row_on_a_phone(self):
        with self.saving_artifacts():
            hhie_s = Questionnaire.objects.get(code="hhie-s")
            self.open(f"/questionnaire/{hhie_s.pk}", self.PHONE)
            expect(self.main().get_by_role("group")).to_contain_text("有沒有戴助聽器")
            self.assert_row_filled((("button", "下一題"),))
            self.answer("沒戴")
            self.next()
            self.question(1)
            self.assert_row_filled((("button", "上一題"), ("button", "下一題")))
            for number in range(1, QUESTION_COUNT):
                self.answer("有時", number)
                self.next()
            self.question(QUESTION_COUNT)
            self.assert_row_filled((("button", "上一題"), ("button", "送出")))
            self.open(f"/questionnaire/{hhie_s.pk}", self.DESKTOP)
            expect(self.main().get_by_role("group")).to_contain_text("有沒有戴助聽器")
            self.assert_words_wide((("button", "下一題"),))

    # Acceptance 4: other pages keep buttons as wide as their words on a phone.
    def test_other_button_rows_keep_their_width_on_a_phone(self):
        with self.saving_artifacts():
            audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 1))
            self.open(f"/audiograms/{audiogram.pk}/delete", self.PHONE)
            self.assert_words_wide((("button", "確定刪除"), ("link", "取消")))


class TypeSizesT357Test(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#357 (spec #354): text a reader needs is at least 1rem, and the site-wide small styles."""

    fixtures = ("questions_fixture.json",)
    HEADING = WhiteCardRuleTest.HEADING
    WHITE = WhiteCardRuleTest.WHITE
    REM = 18  # the site's 112.5% root

    # The white card rule's page-making helpers, borrowed rather than inherited so its own tests
    # do not run twice.
    open = WhiteCardRuleTest.open
    visit = WhiteCardRuleTest.visit
    style = WhiteCardRuleTest.style
    answered = WhiteCardRuleTest.answered
    result = WhiteCardRuleTest.result
    ioi_ha = WhiteCardRuleTest.ioi_ha
    ioi_ha_result = WhiteCardRuleTest.ioi_ha_result
    audiogram = WhiteCardRuleTest.audiogram
    report = WhiteCardRuleTest.report
    shared_report = WhiteCardRuleTest.shared_report
    guide_with_records = WhiteCardRuleTest.guide_with_records
    answered_chapter = WhiteCardRuleTest.answered_chapter
    trend_records = WhiteCardRuleTest.trend_records
    answering = WhiteCardRuleTest.answering

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        call_command("seed_questionnaires", verbosity=0)
        self.user = consented_user(username="type_sizes_e2e")
        self.client.force_login(self.user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def two_audiograms(self):
        """The audiogram comparison, which needs two audiograms."""
        self.audiogram()
        Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 20))
        return "/audiograms/compare"

    def route_with_answer(self):
        """My guide with the assessment stop answered, so its kept answer shows on the route."""
        self.answered_chapter()
        return "/guide"

    def font_size(self, locator):
        return float(self.style(locator, "fontSize")[:-2])

    # Acceptance 2: the score bar's level and both ends, IOI-HA's scale ends and the guide's
    # meter label are 1rem; on a narrow phone the bar's level stays whole inside the bar.
    def test_labels_needed_to_read_a_chart_are_1rem(self):
        cases = (
            ("home's score bar", False, "/", (".score-bar-current span", ".score-bar-ends > span")),
            (
                "result's score bar",
                True,
                lambda test: test.result("hhie-s", 4),
                (".score-bar-current span", ".score-bar-ends > span"),
            ),
            ("IOI-HA result", True, lambda test: test.ioi_ha_result(), (".ioi-scale-ends > span",)),
            ("guide's meter", True, lambda test: test.guide_with_records(), (".meter-scale",)),
        )
        for name, signed_in, path, selectors in cases:
            with self.subTest(page=name):
                self.visit(signed_in, path, width=320)
                for selector in selectors:
                    labels = self.main().locator(selector)
                    expect(labels.first).to_be_visible()
                    for label in labels.all():
                        self.assertEqual(self.font_size(label), self.REM, selector)
                if ".score-bar-current span" in selectors:
                    bar = self.main().locator(".score-bar").bounding_box()
                    row = self.main().locator(".score-bar-current").bounding_box()
                    level = self.main().locator(".score-bar-current span").bounding_box()
                    self.assertGreaterEqual(level["x"], bar["x"])
                    self.assertLessEqual(level["x"] + level["width"], bar["x"] + bar["width"])
                    self.assertGreaterEqual(level["y"], row["y"])
                    self.assertLessEqual(level["y"] + level["height"], row["y"] + row["height"])

    # Acceptance 3: the footer, the report's and the family's copy's two reminders (the
    # audiogram's under it), form help and the route's gap and kept answer are at least 1rem;
    # so is the audiogram comparison's line legend, needed to read the chart (owner, #357).
    def test_text_to_read_is_at_least_1rem(self):
        audiogram_reminder = "#report-audiogram > p:last-child"
        cases = (
            ("footer", False, "/", ".site-footer p"),
            ("form help", False, "/register", ".field-help"),
            (
                "report",
                True,
                lambda test: test.report(),
                f".report-disclaimer, {audiogram_reminder}",
            ),
            (
                "family's report",
                False,
                lambda test: test.shared_report(),
                f".report-disclaimer, {audiogram_reminder}",
            ),
            ("route's gap", False, "/guide", ".route-gap"),
            (
                "audiogram comparison's legend",
                True,
                lambda test: test.two_audiograms(),
                ".compare-legend",
            ),
            ("route's kept answer", True, lambda test: test.route_with_answer(), ".route-answer"),
        )
        for name, signed_in, path, selector in cases:
            with self.subTest(page=name):
                self.visit(signed_in, path, width=390)
                texts = self.page.locator(selector)
                expect(texts.first).to_be_attached()
                if name.endswith("report"):
                    expect(texts).to_have_count(2)
                    expect(texts.first).to_contain_text("不能取代聽力師的判讀")
                    expect(texts.last).to_contain_text("不是醫療診斷")
                for text in texts.all():
                    self.assertGreaterEqual(self.font_size(text), self.REM, selector)

    # Acceptance 4: a form's question (legend) is in the heading colour.
    def test_every_form_question_is_in_the_heading_colour(self):
        cases = (
            ("wizard", "/questionnaire_list?wizard=1"),
            ("answer page", lambda test: test.answering("hhie-s")),
            ("guide chapter question", "/guide/assessment"),
            ("new audiogram", "/audiograms/new"),
        )
        for name, path in cases:
            with self.subTest(page=name):
                self.visit(True, path, width=390)
                if name == "new audiogram":
                    # The symbols' groups, in the typed-numbers fold of 標右耳.
                    audiogram_step(self.page, self.live_server_url, 2)
                    self.main().get_by_text("用數值輸入（鍵盤或螢幕閱讀器）").click()
                legends = self.main().locator("legend:not(.visually-hidden)")
                expect(legends.first).to_be_visible()
                for legend in legends.all():
                    self.assertEqual(self.style(legend, "color"), self.HEADING)

    # Acceptance 5: on a 390 phone the page title (about 29px) is at least 4px above the
    # section title 我的帳號, whose size stays calc(1.275rem + 0.3vw).
    def test_page_title_stands_above_section_titles_on_a_phone(self):
        self.visit(True, "/account", width=390)
        with self.saving_artifacts():
            title = self.font_size(self.main().get_by_role("heading", level=1, name="帳號設定"))
            section = self.font_size(self.main().get_by_role("heading", level=2, name="我的帳號"))
            self.assertAlmostEqual(title, 29, delta=0.5)
            self.assertAlmostEqual(section, 1.275 * self.REM + 0.003 * 390, delta=0.01)
            self.assertGreaterEqual(title - section, 4)

    # Acceptance 6: a blue summary box keeps its round right corners, but its thick left line is
    # straight, not bent round the corners.
    def test_blue_summary_boxes_have_a_straight_left_line(self):
        self.trend_records()
        aided = self.answered("hhie-s", 0)
        Submission.objects.filter(pk=aided.pk).update(wearing_hearing_aid=True)
        self.visit(True, "/my_hearing?questionnaire=hhie-s", width=390)
        for selector in (".trend-summary", ".aided-difference"):
            with self.subTest(box=selector):
                box = self.main().locator(selector)
                expect(box).to_be_visible()
                # 0.375rem, drawn in whole pixels.
                self.assertEqual(self.style(box, "borderLeftWidth"), "6px")
                self.assertEqual(self.style(box, "borderTopLeftRadius"), "0px")
                self.assertEqual(self.style(box, "borderBottomLeftRadius"), "0px")
                self.assertEqual(self.style(box, "borderTopRightRadius"), "27px")

    # Acceptance 7: on a phone the signed-in line has an opaque background over the header wave.
    def test_signed_in_line_hides_the_header_wave_on_a_phone(self):
        self.visit(True, "/", width=390)
        with self.saving_artifacts():
            account = self.page.locator(".site-account")
            expect(account).to_have_text("目前登入：type_sizes_e2e")
            self.assertEqual(self.style(account, "backgroundColor"), self.WHITE)
            # The line does sit over the wave's bars, which is why it needs the background.
            line = account.bounding_box()
            wave = self.page.locator(".site-wave").bounding_box()
            self.assertGreater(line["y"] + line["height"], wave["y"] + wave["height"] * 0.7)


class AudiogramPagesT365Test(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#365 (spec #354): the delete page's title and preview on a phone, and the compare page's
    line samples in the chosen ear's colours."""

    PHONE = (390, 844)
    # The chart's colours (AudiogramChart.jsx): each ear's own, lighter for the older one.
    LINE_COLOURS = (
        (("right", False), "rgb(192, 57, 43)"),
        (("right", True), "rgb(232, 165, 157)"),
        (("left", False), "rgb(31, 78, 140)"),
        (("left", True), "rgb(157, 181, 214)"),
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.user = consented_user(username="audiogram_pages_e2e")
        self.client.force_login(self.user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, path, size):
        width, height = size
        self.context = self.browser.new_context(viewport={"width": width, "height": height})
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)
        self.page.goto(f"{self.live_server_url}{path}")
        self.page.wait_for_load_state("load")

    def audiogram(self, tested_on, db):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=tested_on)
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=db)
            for ear in ("right", "left")
            for f in (500, 1000, 2000, 4000)
        )
        return audiogram

    def assert_word_on_one_line(self):
        word = self.main().get_by_role("heading", level=1).locator("span", has_text="聽力圖")
        lines = word.evaluate(
            "span => { const range = document.createRange(); range.selectNodeContents(span);"
            " return new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size; }"
        )
        self.assertEqual(lines, 1)

    # Acceptance 5: on a 390 phone the title keeps 聽力圖 whole and the audiogram shows under it;
    # at 200% text on 320 it still does, without widening the page.
    def test_delete_page_keeps_the_word_whole_and_shows_the_audiogram(self):
        audiogram = self.audiogram(date(2026, 9, 1), 40)
        with self.saving_artifacts():
            self.open(f"/audiograms/{audiogram.pk}/delete", self.PHONE)
            title = self.main().get_by_role("heading", level=1)
            expect(title).to_have_text("確定要刪除 2026/09/01 的聽力圖嗎？")
            self.assert_word_on_one_line()
            thumbnail = self.main().locator(".audiogram-thumbnail")
            expect(thumbnail).to_be_visible()
            badges = self.main().locator(".level-badge")
            expect(badges).to_have_count(2)
            self.assertLess(
                title.bounding_box()["y"], thumbnail.bounding_box()["y"], "thumbnail under title"
            )
            self.open(f"/audiograms/{audiogram.pk}/delete", (320, 640))
            self.assert_fits_a_phone_at_double_text_size("delete audiogram")
            self.assert_word_on_one_line()

    # Acceptance 4: 舊 and 新 each have their line sample in the chosen ear's colour, and the
    # legend stays under the chart.
    def test_compare_line_samples_follow_the_chosen_ear(self):
        old = self.audiogram(date(2026, 1, 10), 30)
        new = self.audiogram(date(2026, 9, 10), 40)
        with self.saving_artifacts():
            for ear in ("right", "left"):
                with self.subTest(ear=ear):
                    self.open(f"/audiograms/compare?a={new.pk}&b={old.pk}&ear={ear}", self.PHONE)
                    for label, is_old in (("舊", True), ("新", False)):
                        row = self.main().locator("summary", has_text=label)
                        line = row.locator("svg.compare-line")
                        expect(line).to_be_visible()
                        stroke = line.evaluate("svg => getComputedStyle(svg).stroke")
                        self.assertEqual(stroke, dict(self.LINE_COLOURS)[(ear, is_old)], label)
                        # Right after the word.
                        word = row.locator(".compare-pick-label").bounding_box()
                        self.assertGreater(line.bounding_box()["x"], word["x"] + word["width"] - 1)
                    plot = self.page.locator(".audiogram-plot svg")
                    plot.wait_for()
                    legend = self.main().locator(".compare-legend")
                    self.assertGreaterEqual(
                        legend.bounding_box()["y"],
                        plot.bounding_box()["y"] + plot.bounding_box()["height"],
                    )


class FittingGuideT367Test(SavesFailureArtifacts, OnAPhone, StaticLiveServerTestCase):
    """#367 (spec #354): the guide's route and chapters, measured on a phone and a desktop."""

    fixtures = ("questions_fixture.json",)
    PHONE = 390
    DESKTOP = 1024
    # The last line of a sentence: its width in ems, the line's fragments taken together.
    LAST_LINE_EMS = """el => {
        const range = document.createRange();
        range.selectNodeContents(el);
        const rects = [...range.getClientRects()].filter(r => r.width > 0);
        const bottom = Math.max(...rects.map(r => r.bottom));
        const last = rects.filter(r => r.bottom > bottom - 2);
        const width = Math.max(...last.map(r => r.right)) - Math.min(...last.map(r => r.left));
        return width / parseFloat(getComputedStyle(el).fontSize);
    }"""

    open = WhiteCardRuleTest.open
    visit = WhiteCardRuleTest.visit
    answering = WhiteCardRuleTest.answering

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        call_command("seed_questionnaires", verbosity=0)
        self.user = consented_user(username="fitting_guide_t367_e2e")
        self.client.force_login(self.user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def route_at_the_assessment(self):
        """My guide here at the assessment, its question open: 55 dB both ears, 去找聽力師之前
        read. Made once, the test opening it at two widths."""
        if Audiogram.objects.filter(user=self.user).exists():
            return "/guide"
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 1))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=55)
            for ear in ("right", "left")
            for f in (500, 1000, 2000, 4000)
        )
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        return "/guide"

    def boxes(self, locator):
        expect(locator.first).to_be_visible()
        return [item.bounding_box() for item in locator.all()]

    # Acceptance 2: on a phone each answer fills its own row; on a desktop they share one row,
    # equally wide. The answer page keeps one answer a row.
    def test_single_choice_answers_are_equal_rows_on_a_phone_and_one_row_on_a_desktop(self):
        cases = (
            (
                "route",
                lambda test: test.route_at_the_assessment(),
                ".route-stop[aria-current=step] fieldset .stop-answers",
                ".btn",
            ),
            ("chapter", "/guide/assessment", "#stop-question fieldset .stop-answers", ".btn"),
            (
                "chapter radios",
                "/guide/after-fitting",
                "#stop-question fieldset:has(input[name=ear]) div.choice-group",
                "label",
            ),
        )
        for name, path, group, option in cases:
            for width in (self.PHONE, self.DESKTOP):
                with self.subTest(page=name, width=width):
                    self.visit(True, path, width=width)
                    group_box = self.main().locator(group).bounding_box()
                    boxes = self.boxes(self.main().locator(group).locator(option))
                    self.assertGreater(len(boxes), 1)
                    widths = [box["width"] for box in boxes]
                    self.assertLessEqual(max(widths) - min(widths), 1, widths)
                    tops = [round(box["y"]) for box in boxes]
                    if width == self.PHONE:
                        self.assertEqual(tops, sorted(set(tops)))
                        self.assertAlmostEqual(widths[0], group_box["width"], delta=1)
                    else:
                        self.assertEqual(len(set(tops)), 1, tops)
        for width in (self.PHONE, self.DESKTOP):
            with self.subTest(page="answer page", width=width):
                self.visit(True, self.answering("hhie-s"), width=width)
                labels = self.main().locator("div.choice-group label:visible")
                tops = [round(box["y"]) for box in self.boxes(labels)]
                self.assertEqual(tops, sorted(set(tops)))

    # Acceptance 4: each group's meanings start at one line, none ending on a line of one or
    # two characters; at 200% they may drop under the numbers, the page still a phone's width.
    def test_large_number_rows_line_up_on_a_phone(self):
        for slug in ("assessment", "form-9", "types-and-prices"):
            with self.subTest(chapter=slug):
                self.visit(False, f"/guide/{slug}", width=self.PHONE)
                groups = self.main().locator(".fact-rows")
                expect(groups.first).to_be_visible()
                for group in groups.all():
                    values = self.boxes(group.locator(".fact-rows-value"))
                    meanings = group.locator("li > :last-child")
                    starts = {round(box["x"]) for box in self.boxes(meanings)}
                    self.assertEqual(len(starts), 1, starts)
                    for value, meaning in zip(values, self.boxes(meanings), strict=True):
                        self.assertLess(meaning["y"], value["y"] + value["height"])
                    for meaning in meanings.all():
                        self.assertGreater(meaning.evaluate(self.LAST_LINE_EMS), 2.5)
            with self.subTest(chapter=slug, double_text_size=True):
                self.assert_fits_a_phone_at_double_text_size(slug, width=self.PHONE)
                for row in self.main().locator(".fact-rows li").all():
                    value = row.locator(".fact-rows-value").bounding_box()
                    meaning = row.locator(":scope > :last-child").bounding_box()
                    self.assertGreaterEqual(meaning["y"], value["y"] + value["height"] - 1)

    # Acceptance 7: form 9's jump to its six parts, two columns on a phone.
    def test_form_9_jumps_to_its_parts_in_two_columns_on_a_phone(self):
        self.visit(False, "/guide/form-9", width=self.PHONE)
        jump = self.main().get_by_role("navigation", name="本頁段落")
        boxes = self.boxes(jump.get_by_role("link"))
        self.assertEqual(len(boxes), 6)
        self.assertEqual(len({round(box["x"]) for box in boxes}), 2)
        self.assertEqual(len({round(box["y"]) for box in boxes}), 3)
        jump.get_by_role("link", name="補助多少").click()
        expect(self.page).to_have_url(re.compile(r"/guide/form-9#amount-title$"))
        expect(self.main().get_by_role("heading", name="補助多少")).to_be_in_viewport()
        self.page.goto(f"{self.live_server_url}/guide/form-9")
        self.assert_fits_a_phone_at_double_text_size("form 9 at 200%", width=self.PHONE)

    # Acceptance 8: 1.5rem between 配戴之後's title and its first box.
    def test_after_fitting_keeps_its_title_off_the_first_box(self):
        for width in (self.PHONE, self.DESKTOP):
            with self.subTest(width=width):
                self.visit(False, "/guide/after-fitting", width=width)
                title = self.main().get_by_role("heading", level=1).bounding_box()
                box = self.main().locator(".section-box").first.bounding_box()
                self.assertAlmostEqual(box["y"] - (title["y"] + title["height"]), 27, delta=0.5)
