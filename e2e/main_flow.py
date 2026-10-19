"""End-to-end: a real browser walks the main flow against a live test server (spec phase6_e2e.md).

Not named test_*.py, so the normal test run skips it; run it by name after building the frontend:
    python manage.py test --settings=config.test_settings e2e.main_flow
"""

import os
import re
from contextlib import contextmanager
from datetime import date, datetime
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
    NormGroup,
    Questionnaire,
    Submission,
)
from screening.tests.helpers import consented_user

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
        call_command("seed_hhia_s", verbosity=0)
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
        call_command("seed_hhia_s", verbosity=0)
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
        call_command("seed_ssq12", verbosity=0)
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

    def test_ssq12_without_javascript_keeps_explicit_na(self):
        call_command("seed_ssq12", verbosity=0)
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
        call_command("seed_hhia_s", verbosity=0)
        call_command("seed_ssq12", verbosity=0)
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
