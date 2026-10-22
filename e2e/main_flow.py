"""End-to-end: a real browser walks the main flow against a live test server (spec phase6_e2e.md).

Not named test_*.py, so the normal test run skips it; run it by name after building the frontend:
    python manage.py test --settings=config.test_settings e2e.main_flow
"""

import os
import re
from contextlib import contextmanager, nullcontext
from datetime import date, datetime, timedelta
from itertools import combinations, pairwise
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command
from django.test import Client
from playwright.sync_api import expect, sync_playwright

from screening.models import (
    Answer,
    Audiogram,
    AudiogramPoint,
    Category,
    NormGroup,
    Question,
    Questionnaire,
    ReportShare,
    Submission,
    User,
)
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


class NewUserScreeningTest(SavesFailureArtifacts, StaticLiveServerTestCase):
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

    def test_show_password_with_javascript(self):
        """#155 (ticket #151): the 顯示 button shows the password, and hides it again."""
        with self.saving_artifacts():
            self.step1_start_goes_to_register()
            password = self.page.get_by_label("密碼：", exact=True)
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
        """#155: home, register, consent, every wizard step and the answer page, 320px at 200%."""
        self.context.close()
        self.context = self.browser.new_context(
            **{**self.playwright.devices["Pixel 7"], "viewport": {"width": 320, "height": 640}}
        )
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        with self.saving_artifacts():
            self.page.goto(self.live_server_url)
            self.assert_fits_a_phone_at_double_text_size("home")
            self.main().get_by_role("link", name="開始篩檢").click()
            self.assert_fits_a_phone_at_double_text_size("register")
            self.fill_register_form()
            self.main().get_by_role("button", name="註冊").click()
            self.assert_fits_a_phone_at_double_text_size("consent")
            self.main().get_by_role("button", name="我同意，開始篩檢", exact=True).click()
            expect(self.main().locator(".questionnaire-guide")).to_be_visible()
            self.assert_fits_a_phone_at_double_text_size("wizard age")
            self.main().get_by_role("group", name="您目前的實際年齡？").get_by_label(
                "65 歲以上", exact=True
            ).check()
            self.main().get_by_role("button", name="下一步").click()
            self.assert_fits_a_phone_at_double_text_size("wizard hearing aid")
            self.main().get_by_role("group", name="您現在有戴助聽器嗎？").get_by_label(
                "沒有戴", exact=True
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
            expect(self.page.get_by_text("不能判定聽損程度", exact=False)).to_be_visible()
            self.page.get_by_role("navigation", name="主要導覽").get_by_role(
                "link", name="我的紀錄"
            ).click()
            expect(self.main().locator("a.link-card")).to_contain_text("總分：20")

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
            expect(self.main().get_by_role("button", name="下一題")).to_be_disabled()
            self.main().get_by_role("group").get_by_label("不適用", exact=True).check()
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
            expect(self.main().get_by_text("整體平均：6.3／10", exact=True)).to_be_visible()
            expect(self.main().get_by_text("情緒分數", exact=False)).to_have_count(0)
            self.page.screenshot(path="/tmp/hearwell-ssq12-result.png", full_page=True)
            self.main().get_by_role("link", name="看我的紀錄", exact=True).click()
            expect(self.main().locator("a.link-card")).to_contain_text("整體平均：6.3")
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
            self.main().get_by_role("link", name="選擇或管理比較", exact=False).click()
            self.page.get_by_label("未配戴紀錄", exact=True).select_option(str(unaided.pk))
            self.page.get_by_label("配戴紀錄", exact=True).select_option(str(aided.pk))
            self.main().get_by_role("button", name="查看比較", exact=True).focus()
            self.page.keyboard.press("Enter")
            expect(self.main().get_by_text("+1.8 分", exact=False)).to_be_visible()
            self.main().get_by_role("button", name="保留到報告", exact=True).focus()
            self.page.keyboard.press("Enter")
            expect(self.main().get_by_role("button", name="更換報告保留組合")).to_be_visible()
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
                self.page.get_by_label("未配戴紀錄", exact=True).select_option(str(pair[0].pk))
                self.page.get_by_label("配戴紀錄", exact=True).select_option(str(pair[1].pk))
                self.main().get_by_role("button", name="查看比較", exact=True).click()
                self.main().get_by_role("button", name="保留到報告", exact=True).click()
                expect(self.main().get_by_role("button", name="更換報告保留組合")).to_be_visible()
            self.page.goto(f"{self.live_server_url}/report")
            expect(self.page.locator("#report-ssq12")).to_contain_text("整體平均：8.0")
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
            self.main().get_by_text("產生分享連結", exact=True).click()
            self.main().get_by_role("button", name="確認產生", exact=True).click()
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
        age_group = self.main().get_by_role("group", name="您目前的實際年齡？")
        age_group.get_by_role("radio", name="18–64 歲", exact=True).focus()
        self.page.keyboard.press("Space")
        self.main().get_by_role("button", name="下一步").click()
        self.main().get_by_role("group", name="您現在有戴助聽器嗎？").get_by_label(
            "有戴", exact=True
        ).check()
        self.main().get_by_role("button", name="下一步").click()
        # Wearing one with no unaided record: HHIA-S first, SSQ12 listed as also worth doing.
        recommended = self.main().locator("#recommended-title")
        expect(recommended).to_contain_text("HHIA-S")
        self.main().get_by_role("link", name=re.compile("SSQ12-TW")).click()
        expect(self.page.get_by_role("heading", name="SSQ12-TW", exact=True)).to_be_visible()
        self.page.go_back()
        expect(recommended).to_contain_text("HHIA-S")
        self.page.locator("html").evaluate("element => element.style.fontSize = '200%'")
        self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 320)
        self.page.screenshot(path="/tmp/hearwell-recommendations-200.png", full_page=True)
        # #155: the wizard ends on the answer page, the server's form starting on 沒戴 (#154).
        self.main().get_by_role("link", name="開始作答").click()
        expect(self.page).to_have_url(re.compile(r"/questionnaire/\d+\?preselect=unaided$"))
        expect(self.page.get_by_role("heading", name="HHIA-S", exact=True)).to_be_visible()
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

    def main(self):
        return self.page.get_by_role("main")

    def step1_start_goes_to_register(self):
        # Spec #148 (ticket #150): first-time visitors register straight away.
        self.page.goto(self.live_server_url)
        self.main().get_by_role("link", name="開始篩檢").click()
        expect(self.page).to_have_url(re.compile(r"/register\?next=/questionnaire_list$"))

    def assert_step_bar(self, done, total):
        segments = self.main().locator(".step-progress-bar > .step-progress-segment")
        expect(segments).to_have_count(total)
        expect(segments.and_(self.page.locator(".is-done"))).to_have_count(done)

    def assert_fits_a_phone_at_double_text_size(self, where):
        # 2 x the site's 112.5% base, as in SharedLayoutTest; the page is 320px wide. Not
        # add_style_tag: it waits for the style's load event, which never fires without JavaScript.
        self.page.locator("html").evaluate(
            "html => html.style.setProperty('font-size', '225%', 'important')"
        )
        scroll_width = self.page.evaluate("document.documentElement.scrollWidth")
        self.assertLessEqual(scroll_width, 320, where)

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
        self.page.get_by_label("密碼：", exact=True).fill("Fake-pass-2468")
        # Exact: the "顯示密碼確認" toggle button (#151) also has 密碼確認 in its label.
        self.page.get_by_label("密碼確認：", exact=True).fill("Fake-pass-2468")

    def choose_self(self):
        # #152: the wizard's way out to every questionnaire's card.
        self.main().get_by_role("link", name="自己選問卷").click()

    def step3_choose_hhie_s(self):
        # #152 wizard: no birth year, so it asks the age, then the hearing aid, then recommends.
        guide = self.main().locator(".questionnaire-guide")
        steps = self.main().locator(".step-progress-text")
        # Coming from consent: the first screen says the account is done, so 第 1 步 is new.
        expect(guide).to_have_text("帳號建好了\N{FULLWIDTH EXCLAMATION MARK}接下來幫您找適合的問卷")
        expect(steps).to_have_text("第 1 步／共 3 步")
        self.assert_step_bar(1, 3)
        self.main().get_by_role("group", name="您目前的實際年齡？").get_by_label(
            "65 歲以上", exact=True
        ).check()
        self.main().get_by_role("button", name="下一步").click()
        expect(guide).to_have_count(0)
        expect(steps).to_have_text("第 2 步／共 3 步")
        self.assert_step_bar(2, 3)
        self.main().get_by_role("group", name="您現在有戴助聽器嗎？").get_by_label(
            "沒有戴", exact=True
        ).check()
        self.main().get_by_role("button", name="下一步").click()
        expect(steps).to_have_text("第 3 步／共 3 步")
        self.assert_step_bar(3, 3)
        expect(self.main().get_by_role("heading", name="推薦您做這一份")).to_be_visible()
        expect(self.main().locator("#recommended-title")).to_contain_text("HHIE-S")
        expect(self.main()).to_contain_text(
            "為什麼推薦：您沒有戴助聽器，這份問卷供您了解聽力對日常生活和心情的影響。"
        )
        # SSQ12 is only also worth doing for people wearing hearing aids.
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
        nav.get_by_role("link", name="我的紀錄").click()
        # Each record is one card link (spec phase9_ui_refresh_1_shared.md 4.5).
        card = self.main().locator("a.link-card")
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


class SharedLayoutTest(SavesFailureArtifacts, StaticLiveServerTestCase):
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
            first = self.page.get_by_label("未配戴紀錄", exact=True)
            first.focus()
            # Headless Chromium supports select type-ahead but ignores arrow selection.
            first.press(str(unaided.created_at.year)[0])
            self.page.get_by_label("配戴紀錄", exact=True).select_option(str(aided.pk))
            expect(first).to_have_value(str(unaided.pk))
            self.page.get_by_role("button", name="查看比較", exact=True).click()
            expect(self.page.get_by_role("heading", name="目前查看的兩筆")).to_be_visible()
            expect(self.page.get_by_text("-20 分", exact=False)).to_be_visible()
            self.page.get_by_role("button", name="保留到報告", exact=True).focus()
            self.page.keyboard.press("Enter")
            expect(self.page.get_by_role("button", name="移除報告保留組合")).to_be_visible()
            # Submit a stale/foreign id through the actual form to check server-side errors.
            self.page.locator('input[name="aided"]').evaluate("el => el.value = '999999'")
            self.page.get_by_role("button", name="更換報告保留組合").click()
            expect(self.page.locator("#comparison-errors")).to_be_focused()
            expect(self.page.get_by_role("button", name="移除報告保留組合")).to_be_visible()
            self.page.get_by_role("button", name="移除報告保留組合").click()
            expect(self.page.get_by_text("尚未保留比較組合。", exact=True)).to_be_visible()

    def test_ioi_discloses_hhia_basis_before_saving(self):
        """#81: HTML IOI-HA reveals and keeps the chosen adult HHI source."""
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
            expect(self.page.get_by_text("本次常模依據：", exact=False)).to_contain_text("HHIA-S")
            expect(self.page.get_by_text("本次常模依據：", exact=False)).to_contain_text("40 分")
            for n in range(1, 8):
                self.page.locator(f"#question-{n}").get_by_role("radio").first.check()
            self.page.get_by_role("button", name="送出", exact=True).click()
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
                    self.page.wait_for_load_state("networkidle")
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
                self.page.goto(f"{self.live_server_url}/audiograms/new")
                main = self.page.get_by_role("main")
                for name in ("遮蔽：關", "清除剛標的點", "存檔"):
                    with self.subTest(width=width, button=name):
                        widths = main.get_by_role("button", name=name).evaluate(
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
            self.page.goto(f"{self.live_server_url}/questionnaire_list")
            self.page.wait_for_load_state("networkidle")
            expect(self.page.locator("#pwa-back")).to_be_hidden()

    # 2, 3, 4
    def test_back_button_returns_to_the_previous_page(self):
        self.open()
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            self.page.wait_for_load_state("networkidle")
            expect(self.page.locator("#pwa-back")).to_have_count(0)
            self.page.get_by_role("navigation", name="主要導覽").get_by_role(
                "link", name="開始篩檢"
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
        self.page.wait_for_load_state("networkidle")
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
    # #138-#140 (2a): the brand gradient; #139: the primary button's states (choice C in #136,
    # with a soft glow so it never looks like the keyboard ring).
    GRADIENT = "linear-gradient(rgb(31, 78, 140), rgb(58, 107, 176))"
    PRESSED_GRADIENT = "linear-gradient(rgb(23, 59, 106), rgb(47, 92, 156))"
    GLOW = "rgba(58, 107, 176, 0.45) 0px 0px 16.2px 3.6px"
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
            "--color-gradient-end": "#3a6bb0",
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
        # #124: The pre-migration .h3 at 1024px is calc(1.3rem + .6vw) on an 18px root, weight 500,
        # line height 1.2 and a .5rem bottom margin; its .text-muted (now .text-body) was the body
        # text colour.
        self.open(javascript=False)
        with self.saving_artifacts():
            for path, selector in (
                ("/questionnaire_list", "h1.h3"),
                (f"/questionnaire/{self.hhie_s.pk}", "p.h3.text-body"),
            ):
                with self.subTest(selector=selector):
                    self.page.goto(f"{self.live_server_url}{path}")
                    element = self.page.locator(selector)
                    self.assertEqual(self.style(element, "fontSize"), "29.544px")
                    self.assertEqual(self.style(element, "fontWeight"), "500")
                    self.assertEqual(self.style(element, "lineHeight"), "35.4528px")
                    self.assertEqual(self.style(element, "marginBottom"), "9px")
                    self.assertEqual(self.style(element, "color"), self.TEXT)

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
        audiogram = self.audiogram(date(2026, 9, 28))
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
                "註冊",
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
                {
                    **regular,
                    "backgroundColor": clear,
                    "color": "rgb(248, 249, 250)",
                    "borderTopColor": "rgb(248, 249, 250)",
                },
                "rgba(248, 249, 250, 0.5)",
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
                "/account/delete",
                True,
                "link",
                "下載我的資料",
                {
                    "backgroundColor": clear,
                    "color": self.PRIMARY,
                    "borderTopColor": clear,
                    "textDecorationLine": "underline",
                },
                "rgba(49, 132, 253, 0.5)",
            ),
            (
                f"/audiograms/{audiogram.pk}",
                True,
                "link",
                "刪除這張聽力圖",
                {
                    **regular,
                    "backgroundColor": clear,
                    "color": "rgb(220, 53, 69)",
                    "borderTopColor": "rgb(220, 53, 69)",
                },
                "rgba(220, 53, 69, 0.5)",
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

    def test_button_hover_and_press_colours(self):
        # The outline variant whose hover and press colours the site set itself; the primary
        # button's states are in test_primary_button_states_follow_choice_c (#139).
        cases = (("link", "註冊", self.PRIMARY, "rgb(23, 59, 106)"),)
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
        primary_ring = "rgba(31, 78, 140, 0.25) 0px 0px 0px 4.5px"
        field_focus_ring = "rgba(13, 110, 253, 0.25) 0px 0px 0px 4.5px"
        border = "rgb(222, 226, 230)"
        self.audiogram(date(2026, 9, 28))
        with self.saving_artifacts():
            self.open(signed_in=False)
            self.page.goto(f"{self.live_server_url}/login")
            username = self.page.get_by_label("使用者名稱")
            self.assertEqual(self.size(username)[1], 42.5)
            self.assertEqual(
                self.styles(username, "padding", "borderTopColor", "borderTopLeftRadius", "color"),
                {
                    "padding": "6.75px 13.5px",
                    "borderTopColor": border,
                    "borderTopLeftRadius": "13.5px",  # 0.75rem since #137
                    "color": self.TEXT,
                },
            )
            self.assertEqual(
                self.style(self.page.locator("label.form-label").first, "marginBottom"), "9px"
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
            self.assertEqual(
                self.styles(field, "borderTopLeftRadius", "borderTopRightRadius", "marginLeft"),
                {"borderTopLeftRadius": "0px", "borderTopRightRadius": "0px", "marginLeft": "-1px"},
            )
            self.assertEqual(
                self.styles(unit, "borderTopLeftRadius", "borderTopRightRadius", "marginLeft"),
                {
                    "borderTopLeftRadius": "0px",
                    "borderTopRightRadius": "13.5px",
                    "marginLeft": "-1px",
                },
            )
            self.assertEqual({self.size(part)[1] for part in (year, field, unit)}, {42.5})

            self.open()
            self.page.goto(f"{self.live_server_url}/audiograms/new")
            self.page.get_by_text("用數值輸入").click()
            select = self.page.get_by_label("右耳氣導 500 Hz", exact=True)
            self.assertEqual(self.size(select)[1], 42.5)
            self.assertEqual(self.style(select, "padding"), "6.75px 40.5px 6.75px 13.5px")
            self.assertIn("svg", self.style(select, "backgroundImage"))
            select.focus()
            self.assertEqual(self.style(select, "borderTopColor"), "rgb(134, 183, 254)")
            self.assertEqual(self.style(select, "boxShadow"), field_focus_ring)
            mask = self.page.get_by_label("右耳氣導 500 Hz 遮蔽")
            self.assertEqual(self.size(mask), (18, 18))
            self.assertEqual(self.style(mask, "opacity"), "0.5")
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
            date_field = self.page.get_by_label("檢查日期")
            self.assertEqual(
                self.styles(date_field, "padding", "fontSize", "borderTopLeftRadius"),
                {"padding": "9px 18px", "fontSize": "22.5px", "borderTopLeftRadius": "13.5px"},
            )
            self.assertGreaterEqual(self.size(date_field)[1], 44)

            self.audiogram(date(2026, 10, 5))
            self.page.goto(f"{self.live_server_url}/audiograms/compare")
            first = self.page.get_by_label("第一張")
            self.assertEqual(
                self.styles(first, "padding", "fontSize", "borderTopLeftRadius"),
                {
                    "padding": "9px 40.5px 9px 18px",
                    "fontSize": "22.5px",
                    "borderTopLeftRadius": "13.5px",
                },
            )
            self.assertGreaterEqual(self.size(first)[1], 44)

    def test_cards_tables_alerts_and_lists_look_as_before(self):
        first = self.audiogram(date(2026, 9, 28))
        self.audiogram(date(2026, 10, 5))
        with self.saving_artifacts():
            self.open()
            self.page.goto(f"{self.live_server_url}/family")
            card = self.page.locator(".card.card-body").first
            self.assertEqual(
                self.styles(
                    card,
                    "display",
                    "padding",
                    "borderTopWidth",
                    "borderTopColor",
                    "borderTopLeftRadius",
                    "backgroundColor",
                ),
                {
                    "display": "flex",
                    "padding": "18px",
                    "borderTopWidth": "1px",
                    "borderTopColor": self.WARM_BORDER,  # and 1.5rem since #137
                    "borderTopLeftRadius": "27px",
                    "backgroundColor": "rgb(255, 255, 255)",
                },
            )

            self.page.goto(f"{self.live_server_url}/audiograms/{first.pk}")
            table = self.page.locator("table.table").first
            self.assertEqual(self.style(table, "marginBottom"), "18px")
            self.assertEqual(self.size(table)[0], self.size(table.locator(".."))[0])
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

            self.page.goto(f"{self.live_server_url}/audiograms/new")
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
            self.page.get_by_label("密碼").fill("not-the-password")
            submit.click()
            error = self.page.locator("#login_error")
            expect(error).to_be_visible()
            self.assertEqual(self.style(error, "color"), self.ERROR)

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

    # Without JavaScript the trend summary stays and the chart card, which would stay empty, hides.
    def test_trend_summary_shows_without_javascript(self):
        self.submission(self.hhie_s, (2,) * 10)
        self.open(javascript=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/my_hearing?questionnaire=hhie-s")
            expect(self.page.locator(".trend-summary")).to_be_visible()
            expect(self.page.locator("#trend-chart .card")).to_be_hidden()

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

    def test_answer_choices_are_large_buttons_in_a_row(self):
        self.open(javascript=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire/{self.hhie_s.pk}")
            labels = self.page.locator("#id_form-0-score label")
            first, second = labels.nth(0).bounding_box(), labels.nth(1).bounding_box()
            self.assertGreaterEqual(first["height"], 3 * 18)  # 3rem at the 18px base
            self.assertGreaterEqual(first["width"], 44)  # #119 acceptance 6
            self.assertEqual(first["y"], second["y"])
            self.assertLess(first["x"], second["x"])

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
            ("/", ".step-cards li", self.WHITE),
        )
        cases = (
            ("/questionnaire_list?choose=self", "main a.link-card", self.WHITE),
            ("/my_hearing?questionnaire=hhie-s", "#trend-chart .card", self.WHITE),
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
        # #159: these are the new-user home's own elements, so check them signed out.
        home_cases = (
            ("/", ".step-cards li", large),
            ("/", ".home-band", large),
            ("/", ".result-preview", large),
        )
        cases = (
            ("/questionnaire_list?choose=self", "main a.link-card", large),
            ("/questionnaire_list?from=consent", ".questionnaire-guide", large),
            ("/my_hearing?questionnaire=hhie-s", ".trend-summary", large),
            ("/my_hearing?questionnaire=hhie-s", ".aided-difference", large),
            ("/my_hearing?questionnaire=hhie-s", "#trend-chart .card", large),
            ("/my_hearing?questionnaire=ioi-ha", ".ioi-chart", large),
            (f"/audiograms/{audiogram.pk}", ".audiogram-chart", large),
            (f"/submission/{basis.pk}", ".result-banner", medium),
            (f"/submission/{ioi.pk}", ".ioi-note", medium),
            ("/audiograms/new", "#tested-on", medium),
            ("/audiograms/new", ".audiogram-table .form-select", medium),
            ("/audiograms/new", ".audiogram-symbol", medium),
            # Left as they were: badges, thumbnails and the charts themselves.
            ("/my_hearing?questionnaire=hhie-s", ".level-badge", "18px"),
            ("/audiograms", ".audiogram-thumbnail", "4.5px"),
            (f"/audiograms/{audiogram.pk}", ".audiogram-svg", "0px"),
        )
        with self.saving_artifacts():
            self.open(signed_in=False)
            for path, selector, radius in home_cases:
                with self.subTest(path=path, selector=selector):
                    self.page.goto(f"{self.live_server_url}{path}")
                    found = self.page.locator(selector).first
                    expect(found).to_be_attached()
                    self.assertEqual(self.style(found, "borderTopLeftRadius"), radius)
            self.open()
            for path, selector, radius in cases:
                with self.subTest(path=path, selector=selector):
                    self.page.goto(f"{self.live_server_url}{path}")
                    found = self.page.locator(selector).first
                    expect(found).to_be_attached()
                    self.assertEqual(self.style(found, "borderTopLeftRadius"), radius)

    def test_large_white_blocks_have_warm_borders_and_shadows(self):
        self.submission(self.hhie_s, [2] * 10)
        # #159: the step cards are the new-user home's own elements, so check them signed out.
        home_cases = (("/", ".step-cards li"),)
        cases = (
            ("/questionnaire_list?choose=self", "main a.link-card"),
            ("/my_hearing?questionnaire=hhie-s", "#trend-chart .card"),
        )
        with self.saving_artifacts():
            self.open(signed_in=False)
            for path, selector in home_cases:
                with self.subTest(path=path, selector=selector):
                    self.page.goto(f"{self.live_server_url}{path}")
                    found = self.page.locator(selector).first
                    expect(found).to_be_attached()
                    self.assertEqual(self.style(found, "borderTopColor"), self.WARM_BORDER)
                    self.assertEqual(
                        self.style(found, "boxShadow"),
                        "rgba(120, 90, 50, 0.08) 0px 4.5px 13.5px 0px",
                    )
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
            self.page.goto(f"{self.live_server_url}/audiograms/new")
            self.page.get_by_role("button", name="遮蔽：關").click()
            switch = self.page.get_by_role("button", name="遮蔽：開（△ □ [ ]）")
            self.assertEqual(
                self.styles(switch, "backgroundColor", "borderTopColor", "color"),
                {
                    "backgroundColor": "rgb(179, 89, 0)",
                    "borderTopColor": "rgb(179, 89, 0)",
                    "color": self.WHITE,
                },
            )

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

    def test_header_is_a_blue_gradient_with_a_hidden_wave(self):
        self.open()
        with self.saving_artifacts():
            for path in ("/", "/questionnaire_list"):
                with self.subTest(path=path):
                    self.page.goto(f"{self.live_server_url}{path}")
                    header = self.page.locator(".site-header")
                    self.assertEqual(self.style(header, "backgroundImage"), self.GRADIENT)
                    wave = header.locator(".site-wave")
                    self.assertEqual(wave.get_attribute("aria-hidden"), "true")
                    expect(wave.locator("span")).to_have_count(28)

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
        audiogram = self.audiogram(date(2026, 9, 28))
        cases = (
            (False, "/login", "button", "登入"),
            (False, "/login", "link", "註冊"),
            (True, "/", "button", "登出"),
            (True, f"/audiograms/{audiogram.pk}", "link", "刪除這張聽力圖"),
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
            (f"/audiograms/{audiogram.pk}", "link", "刪除這張聽力圖", "color"),
            ("/report", "button", "取消分享", "color"),
        )
        self.open()
        with self.saving_artifacts():
            for path, role, name, prop in cases:
                with self.subTest(button=name):
                    self.page.goto(f"{self.live_server_url}{path}")
                    button = self.page.get_by_role(role, name=name, exact=True)
                    self.assertEqual(self.style(button, prop), red)
                    self.assertEqual(self.style(button, "borderTopColor"), red)

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
                f"{self.FOCUS_RING}, rgba(58, 107, 176, 0.45) 0px 0px 16.2px 8.1px",
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
                "link", name="我的紀錄"
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
        # #159: the step cards are the new-user home's own elements, so check them signed out.
        home_cases = (("/", ".step-cards li"),)
        cases = (
            ("/my_hearing", ".trend-summary"),
            (f"/submission/{record.pk}", ".result-banner"),
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
