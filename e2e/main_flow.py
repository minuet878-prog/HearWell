"""End-to-end: a real browser walks the main flow against a live test server (spec phase6_e2e.md).

Not named test_*.py, so the normal test run skips it; run it by name after building the frontend:
    python manage.py test --settings=config.test_settings e2e.main_flow
"""

import os
import re

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import expect, sync_playwright

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
        try:
            self.step1_start_needs_login()
            self.step2_register()
            self.step3_choose_hhie_s()
            self.step4_answer_and_change_one()
            self.step5_submit()
            self.step6_history()
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
        expect(self.main().get_by_role("link", name="查看結果")).to_have_count(1)
        expect(self.page.get_by_text("總分：20")).to_be_visible()
        # The record card only: the trend chart, drawn later by React, repeats the level text.
        card = self.main().locator(".card", has=self.page.get_by_role("link", name="查看結果"))
        expect(card.get_by_text("輕度到中度影響")).to_be_visible()

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
