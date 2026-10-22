"""#193: the standalone 分享報告給家人 page (spec #183 user stories 43-54, acceptance 12-15)."""

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse

from screening.models import Audiogram, Category, Question, Questionnaire, ReportShare
from screening.tests import test_report
from screening.tests.helpers import consented_user

WILL_SEE = [
    "聽力圖",
    "各問卷的分數、分級和建議",
    "每一題的回答",
    "每份問卷最近 5 筆紀錄",
    "放進報告的配戴比較",
    "年齡",
]
WONT_SEE = "不會看到：使用者名稱、出生年"
LATEST_NOTICE = "連結有效期間，家人看到的是您最新的報告，之後新增的紀錄也會看到。"
CREATE_BUTTON = "我知道了，產生連結"
TAIPEI = ZoneInfo("Asia/Taipei")


def _hhie_s_questionnaire():
    questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
    questions = Question.objects.bulk_create(
        Question(
            questionnaire=questionnaire,
            question_text=f"假 HHIE 題{i}",
            question_number=i,
            category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
        )
        for i in range(1, 11)
    )
    return questionnaire, questions


class SharePageTests(TestCase):
    _hhie_s = test_report.HealthReportTests._hhie_s

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s, cls.hhie_questions = _hhie_s_questionnaire()

    def setUp(self):
        self.user = consented_user(username="share_page_a", birth_year=1955)
        self.other = consented_user(username="share_page_b")
        self.client.force_login(self.user)
        self.url = reverse("share_report")

    def _page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response

    # Acceptance 12
    def test_without_link_step_one_lists_what_family_will_and_wont_see(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        response = self._page()
        self.assertIn("no-store", response["Cache-Control"])
        content = response.content.decode()
        self.assertIn("<h1", content)
        self.assertIn("分享報告給家人</h1>", content)
        step_one = content[content.index("家人會看到什麼") : content.index(CREATE_BUTTON)]
        for item in WILL_SEE:
            with self.subTest(item=item):
                self.assertIn(f"<li>{item}</li>", step_one)
        self.assertIn(WONT_SEE, step_one)
        self.assertIn(LATEST_NOTICE, step_one)

    def test_signed_out_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )

    # Acceptance 12: one press, no second confirm; the backend still wants the confirm field
    def test_one_press_makes_the_link_and_returns_to_this_page(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        content = self._page().content.decode()
        form = re.search(
            rf'<form method="post" action="{reverse("report_share_create")}">(.*?)</form>',
            content,
            re.S,
        )
        self.assertIsNotNone(form)
        self.assertIn(f'name="confirm" value="1">{CREATE_BUTTON}</button>', form.group(1))
        self.assertNotIn("<details", content)

        response = self.client.post(reverse("report_share_create"), {"confirm": "1"})
        self.assertRedirects(response, self.url)
        self.assertEqual(ReportShare.objects.active().filter(user=self.user).count(), 1)

    def test_without_confirm_nothing_is_made(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        response = self.client.post(reverse("report_share_create"), {})
        self.assertRedirects(response, self.url)
        self.assertFalse(ReportShare.objects.exists())

    def test_without_records_there_is_nothing_to_share(self):
        content = self._page().content.decode()
        self.assertIn("還沒有可以放進報告的紀錄。", content)
        self.assertNotIn(CREATE_BUTTON, content)
        self.client.post(reverse("report_share_create"), {"confirm": "1"})
        self.assertFalse(ReportShare.objects.exists())

    def _share(self, user):
        """An active link made the way a user makes one, ending at a fixed Taipei time."""
        self.client.force_login(user)
        self._hhie_s(user, test_report.AIDED, wearing=True, days_ago=1)
        self.client.post(reverse("report_share_create"), {"confirm": "1"})
        share = ReportShare.objects.active().get(user=user)
        share.expires_at = datetime(2099, 10, 29, 14, 30, tzinfo=TAIPEI)
        share.save(update_fields=["expires_at"])
        self.client.force_login(self.user)
        return share

    def _share_url(self, share):
        return f"https://testserver{reverse('shared_cover', args=[share.token])}"

    # Acceptance 13
    def test_active_link_shows_expiry_with_time_opens_and_actions(self):
        share = self._share(self.user)
        content = self._page().content.decode()
        self.assertIn("有效到 10 月 29 日 14:30", content)
        self.assertIn("家人打開過 0 次", content)
        self.assertIn("還沒有人打開", content)
        self.assertIn(">再傳一次給家人</button>", content)
        self.assertIn(">複製連結</button>", content)
        self.assertIn(self._share_url(share), content)
        cancel = re.search(
            rf'<form method="post" action="{reverse("report_share_cancel", args=[share.pk])}">'
            r"(.*?)</form>",
            content,
            re.S,
        )
        self.assertIsNotNone(cancel)
        self.assertIn('class="btn btn-outline-danger btn-lg"', cancel.group(1))
        self.assertIn(">取消分享</button>", cancel.group(1))
        self.assertNotIn(CREATE_BUTTON, content)

    def test_active_link_shows_how_often_and_when_last_opened(self):
        share = self._share(self.user)
        ReportShare.objects.filter(pk=share.pk).update(
            open_count=2, last_opened_at=datetime(2099, 10, 23, 9, 5, tzinfo=TAIPEI)
        )
        content = self._page().content.decode()
        self.assertIn("家人打開過 2 次", content)
        self.assertIn("最後一次打開：10 月 23 日 09:05", content)
        self.assertNotIn("還沒有人打開", content)

    # Acceptance 14: the buttons start hidden and only the script shows them; the address shows
    def test_without_javascript_the_address_shows_and_the_buttons_do_not(self):
        share = self._share(self.user)
        content = self._page().content.decode()
        for button_id in ("share-button", "copy-link"):
            with self.subTest(button=button_id):
                tag = re.search(rf'<button[^>]*id="{button_id}"[^>]*>', content)
                self.assertIsNotNone(tag)
                self.assertRegex(tag.group(0), r"\shidden[\s>]")
        address = re.search(r'<p id="share-url"[^>]*>(.*?)</p>', content, re.S)
        self.assertIsNotNone(address)
        self.assertNotRegex(address.group(0), r"<p[^>]*\shidden")
        self.assertIn(self._share_url(share), address.group(1))
        self.assertIn('data-url="' + self._share_url(share) + '"', content)
        self.assertIn("screening/share-button.js", content)
        self.assertIn("screening/copy-link.js", content)
        self.assertRegex(content, r'id="copy-status"[^>]*aria-live="polite"')

    def test_cancel_returns_to_this_page_ready_to_share_again(self):
        share = self._share(self.user)
        response = self.client.post(reverse("report_share_cancel", args=[share.pk]))
        self.assertRedirects(response, self.url)
        self.assertFalse(ReportShare.objects.active().exists())
        content = self._page().content.decode()
        self.assertIn(CREATE_BUTTON, content)
        self.assertNotIn(share.token, content)
        self.assertNotIn("家人打開過", content)

    # Acceptance 15, and the page reads only the signed-in user's own link
    def test_someone_elses_link_cannot_be_cancelled_or_seen(self):
        theirs = self._share(self.other)
        response = self.client.post(reverse("report_share_cancel", args=[theirs.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ReportShare.objects.active().filter(pk=theirs.pk).exists())
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        content = self._page().content.decode()
        self.assertNotIn(theirs.token, content)
        self.assertNotIn("家人打開過", content)
        self.assertIn(CREATE_BUTTON, content)

    # Audiograms can be deleted (submissions cannot), so a live link may outlast every record.
    def test_live_link_can_still_be_cancelled_after_its_records_are_gone(self):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 9, 28))
        self.client.post(reverse("report_share_create"), {"confirm": "1"})
        share = ReportShare.objects.active().get(user=self.user)
        self.client.post(reverse("audiogram_delete", args=[audiogram.pk]))
        self.assertFalse(Audiogram.objects.exists())
        content = self._page().content.decode()
        self.assertIn(reverse("report_share_cancel", args=[share.pk]), content)
        self.assertIn("家人打開過 0 次", content)


class SharePageEntryTests(TestCase):
    """Spec #183 stories 52-53: the report and the home page both lead to the share page."""

    _hhie_s = test_report.HealthReportTests._hhie_s

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s, cls.hhie_questions = _hhie_s_questionnaire()

    def setUp(self):
        self.user = consented_user(username="share_entry")
        self.client.force_login(self.user)
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=30)

    def test_report_has_one_button_to_the_share_page_instead_of_the_block(self):
        content = self.client.get(reverse("health_report")).content.decode()
        button = re.search(r'<a[^>]*href="/share"[^>]*>分享報告給家人</a>', content)
        self.assertIsNotNone(button)
        self.assertIn("btn", button.group(0))
        self.assertLess(button.start(), content.index('id="report-summary"'))
        # Beside the print button, in the row the printout leaves out.
        row = re.search(r'<p class="no-print[^"]*">(.*?)</p>', content, re.S)
        self.assertIn(button.group(0), row.group(1))
        self.assertIn('id="print-button"', row.group(1))
        for old in ("產生分享連結", "確認產生", "share-button.js"):
            with self.subTest(old=old):
                self.assertNotIn(old, content)

    def test_report_with_a_live_link_shows_no_link_details(self):
        self.client.post(reverse("report_share_create"), {"confirm": "1"})
        share = ReportShare.objects.active().get(user=self.user)
        content = self.client.get(reverse("health_report")).content.decode()
        self.assertNotIn(share.token, content)
        self.assertIn('href="/share"', content)

    def test_home_share_card_goes_to_the_share_page(self):
        content = self.client.get(reverse("index")).content.decode()
        self.assertRegex(
            content,
            r'<a class="link-card" href="/share">\s*<span class="link-card-body">\s*'
            r'<span class="link-card-title">分享報告給家人</span>',
        )
        self.assertNotIn("#report-share", content)
