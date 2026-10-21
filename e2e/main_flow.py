"""End-to-end: a real browser walks the main flow against a live test server (spec phase6_e2e.md).

Not named test_*.py, so the normal test run skips it; run it by name after building the frontend:
    python manage.py test --settings=config.test_settings e2e.main_flow
"""

import os
import re
from contextlib import contextmanager, nullcontext
from datetime import date, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command
from playwright.sync_api import expect, sync_playwright

from screening.models import (
    Answer,
    Audiogram,
    AudiogramPoint,
    Category,
    NormGroup,
    Question,
    Questionnaire,
    Submission,
)
from screening.tests.helpers import consented_user, fake_definition, register

# Playwright runs an event loop in this thread, which makes Django refuse database calls.
# The Django docs' fix for Playwright; this module is only imported by the e2e run.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

ARTIFACTS = settings.BASE_DIR / "e2e-artifacts"
QUESTION_COUNT = 10


class NewUserScreeningTest(StaticLiveServerTestCase):
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
            self.step1_start_needs_login()
            self.step2_register()
            self.step3_choose_hhie_s()
            self.step4_answer_and_change_one()
            self.step5_submit()
            self.step6_history()
            self.step7_report_prints_without_site_chrome()

    def test_adult_completes_hhia_s_with_keyboard(self):
        """Issue #78: real React flow, original labels, focus and saved results."""
        call_command("seed_questionnaires", verbosity=0)
        with self.saving_artifacts():
            self.step1_start_needs_login()
            self.step2_register()
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
            expect(self.page.get_by_text("輕至中度影響")).to_be_visible()
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
        self.step1_start_needs_login()
        self.step2_register()
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
        expect(self.page.get_by_text("輕至中度影響")).to_be_visible()

    def test_ssq12_scale_draft_and_average(self):
        """#79: range input, N/A, zero and draft restoration in a real browser."""
        call_command("seed_questionnaires", verbosity=0)
        with self.saving_artifacts():
            self.step1_start_needs_login()
            self.step2_register()
            self.main().get_by_role("link", name="了解目前聆聽能力", exact=True).click()
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
        self.step1_start_needs_login()
        self.step2_register()
        self.main().get_by_role("link", name="了解目前聆聽能力", exact=True).click()
        self.page.get_by_role("group", name="這次填答時，您有沒有戴助聽器？").get_by_label(
            "沒戴", exact=True
        ).check()
        for number in range(1, 13):
            self.page.locator(f"#question-{number}").get_by_role(
                "radio", name="不適用" if number == 1 else "0", exact=True
            ).check()
        self.main().get_by_role("button", name="送出").click()
        expect(self.main().get_by_text("未計算：包含不適用題目", exact=True)).to_be_visible()

    def test_age_confirmation_and_purpose_links_without_javascript(self):
        """#80: server-rendered selection preserves browser back and scales at 320px."""
        call_command("seed_questionnaires", verbosity=0)
        self.context.close()
        self.context = self.browser.new_context(
            java_script_enabled=False, viewport={"width": 320, "height": 800}
        )
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.step1_start_needs_login()
        self.step2_register()
        age_group = self.main().get_by_role("group", name="您目前的實際年齡？")
        age_group.get_by_role("radio", name="18–64 歲", exact=True).focus()
        self.page.keyboard.press("Space")
        self.main().get_by_role("button", name="看適合我的問卷").click()
        expect(
            self.main().get_by_text("依您的年齡，建議先了解聽力對生活的影響（HHIA-S）", exact=False)
        ).to_be_visible()
        self.main().get_by_role("link", name="了解目前聆聽能力", exact=True).click()
        expect(self.page.get_by_role("heading", name="SSQ12-TW", exact=True)).to_be_visible()
        self.page.go_back()
        expect(
            self.main().get_by_text("依您的年齡，建議先了解聽力對生活的影響（HHIA-S）", exact=False)
        ).to_be_visible()
        self.page.locator("html").evaluate("element => element.style.fontSize = '200%'")
        self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 320)
        self.page.screenshot(path="/tmp/hearwell-recommendations-200.png", full_page=True)

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

    @contextmanager
    def saving_artifacts(self):
        """On failure, keep this test's screenshot and trace for debugging (CI uploads them)."""
        try:
            yield
        except BaseException:
            ARTIFACTS.mkdir(exist_ok=True)
            self.page.screenshot(path=ARTIFACTS / "failure.png", full_page=True)
            self.context.tracing.stop(path=ARTIFACTS / "trace.zip")
            raise

    def main(self):
        return self.page.get_by_role("main")

    def step1_start_needs_login(self):
        self.page.goto(self.live_server_url)
        self.main().get_by_role("link", name="開始篩檢").click()
        expect(self.page.get_by_text("登入後會帶您回到剛剛的頁面")).to_be_visible()

    def step2_register(self):
        self.main().get_by_role("link", name="註冊").click()
        self.page.get_by_label("使用者名稱").fill("e2e_user")
        self.page.get_by_label("電子郵件").fill("e2e_user@example.com")
        self.page.get_by_label("密碼：", exact=True).fill("Fake-pass-2468")
        self.page.get_by_label("密碼確認").fill("Fake-pass-2468")
        self.main().get_by_role("button", name="註冊").click()
        # New accounts agree to the privacy notice first (spec phase7_consent_privacy.md).
        self.main().get_by_role("button", name="我同意").click()
        expect(self.page.get_by_text("目前登入：e2e_user")).to_be_visible()
        expect(self.page).to_have_url(re.compile(r"/questionnaire_list$"))

    def step3_choose_hhie_s(self):
        self.main().get_by_role("link", name="HHIE-S").click()
        # React took over: only its hearing aid question shows, the Django form is hidden.
        hearing_aid = self.page.get_by_role("group", name="這次填答時，您有沒有戴助聽器？")
        expect(hearing_aid).to_be_visible()
        expect(self.page.get_by_role("group")).to_have_count(1)

    def step4_answer_and_change_one(self):
        self.answer("沒戴")
        self.next()
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

    def step5_submit(self):
        self.main().get_by_role("button", name="送出").click()
        expect(self.page).to_have_url(re.compile(r"/submission/\d+$"))
        # Every answer 有時 (2 points) x 10, question 1 counted with its changed answer.
        expect(self.page.get_by_text("總分 20 分")).to_be_visible()
        expect(self.page.get_by_text("輕度到中度影響")).to_be_visible()

    def step6_history(self):
        nav = self.page.get_by_role("navigation", name="主要導覽")
        nav.get_by_role("link", name="我的紀錄").click()
        # Each record is one card link (spec phase9_ui_refresh_1_shared.md 4.5).
        card = self.main().locator("a.link-card")
        expect(card).to_have_count(1)
        expect(card).to_contain_text("總分：20")
        # The record card only: the trend chart, drawn later by React, repeats the level text.
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


class SharedLayoutTest(StaticLiveServerTestCase):
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

    def open(self, width, height=900):
        self.context = self.browser.new_context(viewport={"width": width, "height": height})
        self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    saving_artifacts = NewUserScreeningTest.saving_artifacts

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
            self.page.goto(f"{self.live_server_url}/questionnaire_list")
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

    # phase9_ui_refresh_4a_home.md acceptance 8: step cards stack on a phone
    def test_home_step_cards_stack_on_a_phone(self):
        self.open(320, 640)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            boxes = [card.bounding_box() for card in self.page.locator(".step-cards > li").all()]
            self.assertEqual(len(boxes), 3)
            self.assertEqual({box["x"] for box in boxes}, {boxes[0]["x"]})
            for upper, lower in pairwise(boxes):
                self.assertGreaterEqual(lower["y"], upper["y"] + upper["height"])
            scroll_width = self.page.evaluate("document.documentElement.scrollWidth")
            self.assertLessEqual(scroll_width, 320)

    # phase9_ui_refresh_4a_home.md review 1: at 200% text the step cards still fit a phone
    def test_home_step_cards_fit_a_phone_at_double_text_size(self):
        self.open(320, 640)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/")
            self.page.add_style_tag(content="html { font-size: 225% !important; }")  # 2 x 112.5%
            for card in self.page.locator(".step-cards > li").all():
                box = card.bounding_box()
                self.assertLessEqual(box["x"] + box["width"], 320)


class PwaNavTest(StaticLiveServerTestCase):
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

    saving_artifacts = NewUserScreeningTest.saving_artifacts

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


class StyleInBrowserTest(StaticLiveServerTestCase):
    """#123: style rules measured as the browser computes them, whatever produced the CSS."""

    fixtures = ("questions_fixture.json",)
    TEXT = "rgb(73, 80, 87)"
    PRIMARY = "rgb(31, 78, 140)"
    ERROR = "rgb(194, 59, 28)"
    # (level, scores, background, text colour); "unknown" keeps only its colour checked.
    BANNERS = (
        ("normal", (0,) * 10, "rgb(227, 244, 236)", "rgb(30, 123, 85)"),
        ("mild_to_moderate", (2,) * 6 + (0,) * 4, "rgb(255, 244, 214)", "rgb(138, 90, 0)"),
        ("severe", (4,) * 10, "rgb(254, 236, 231)", ERROR),
        ("unknown", (2,) * 10, None, TEXT),
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

    saving_artifacts = NewUserScreeningTest.saving_artifacts

    def setUp(self):
        self.user = consented_user(username="style_e2e")
        self.hhie_s = Questionnaire.objects.get(code="hhie-s")
        self.client.force_login(self.user)
        self.cookie = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            "url": self.live_server_url,
        }

    def open(self, signed_in=True, width=1024, javascript=True):
        self.context = self.browser.new_context(
            viewport={"width": width, "height": 900}, java_script_enabled=javascript
        )
        if signed_in:
            self.context.add_cookies([self.cookie])
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)

    def style(self, locator, prop):
        return locator.evaluate("(el, prop) => getComputedStyle(el)[prop]", prop)

    def submission(self, questionnaire, scores):
        record = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=question, score=score)
            for question, score in zip(questionnaire.questions.all(), scores, strict=True)
        )
        return record

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
                    if background:
                        self.assertEqual(self.style(banner, "backgroundColor"), background)

    def test_answer_choices_are_large_buttons_in_a_row(self):
        self.open(javascript=False)
        with self.saving_artifacts():
            self.page.goto(f"{self.live_server_url}/questionnaire/{self.hhie_s.pk}")
            labels = self.page.locator("#id_form-0-score label")
            first, second = labels.nth(0).bounding_box(), labels.nth(1).bounding_box()
            self.assertGreaterEqual(first["height"], 3 * 18)  # 3rem at the 18px base
            self.assertEqual(first["y"], second["y"])
            self.assertLess(first["x"], second["x"])

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
