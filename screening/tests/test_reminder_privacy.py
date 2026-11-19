from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening import models
from screening.questionnaires.definition import RETEST_MONTHS
from screening.tests import test_layout


class ReminderPrivacyTests(TestCase):
    """Spec #656 acceptance 41, 42 (#664, ADR 0065): the privacy notice says how the email
    重測提醒 uses the email, that an email can be added, and the backup's exception; the numbers
    are the program's. The date moves but the version stays 8."""

    def setUp(self):
        page = self.client.get(reverse("privacy")).content.decode()
        self.main = page[page.index("<main") : page.index("</main>")]

    def part(self, title_id, next_id):
        html = self.main[self.main.index(f'id="{title_id}"') : self.main.index(f'id="{next_id}"')]
        return test_layout._text(html)

    def test_why_it_is_collected_includes_the_reminder(self):
        why = self.part("why-title", "collected-title")
        self.assertIn(
            f"您打開 email 重測提醒時，在上次篩檢滿 {RETEST_MONTHS} 個月那天寄一封提醒信給您，"
            "可以隨時取消。",
            why,
        )

    def test_what_is_collected_includes_the_reminder_setting_and_sends(self):
        collected = self.part("collected-title", "line-title")
        self.assertIn("您有沒有打開 email 重測提醒、哪天打開，以及寄過哪幾次提醒信。", collected)

    def test_the_forgot_password_part_no_longer_says_no_other_email(self):
        part = self.part("password-reset-title", "retest-reminder-title")
        self.assertNotIn("網站不寄其他信", part)
        self.assertIn(
            "只有您自己申請時才寄。除了這封信，只有您打開 email 重測提醒時，"
            "網站才會寄提醒信給您（見下一段）。",
            part,
        )

    def test_a_part_of_its_own_after_the_forgot_password_part(self):
        self.assertIn(
            '<h2 id="retest-reminder-title" class="fold-row-title">email 重測提醒</h2>', self.main
        )
        self.assertLess(
            self.main.index('id="password-reset-title"'),
            self.main.index('id="retest-reminder-title"'),
        )
        self.assertLess(
            self.main.index('id="retest-reminder-title"'),
            self.main.index('id="question-log-title"'),
        )

    def test_it_says_when_it_writes_what_is_in_it_and_how_to_cancel(self):
        part = self.part("retest-reminder-title", "question-log-title")
        for words in (
            f"上次做完生活影響問卷（HHIE-S 或 HHIA-S）滿 {RETEST_MONTHS} 個月的那天早上",
            "寄一封提醒信到您帳號的 email",
            "預設不寄；同一次到期只寄一封，不會一直催。",
            "信裡有您的使用者名稱、「再做一次」和取消提醒的連結，不寫分數或結果。",
            "可以隨時取消：按信裡的「取消提醒」（不用登入），或到「帳號設定」關掉。",
            "寄信服務和重設密碼信一樣是 Resend（資料存放在美國），信保存 30 天後自動刪除。",
        ):
            with self.subTest(words=words):
                self.assertIn(words, part)

    def test_it_says_an_email_can_be_added_in_the_account_settings(self):
        part = self.part("retest-reminder-title", "question-log-title")
        self.assertIn(
            "帳號沒有 email 的（例如用 LINE 註冊時沒填），可以在「帳號設定」自己補上，"
            "補之前要先確認是您本人。",
            part,
        )

    def test_where_it_is_kept_names_the_reminder_email_and_the_backup_exception(self):
        storage = self.part("storage-title", "recipients-title")
        self.assertIn(
            "重設密碼信和重測提醒信會傳到美國的寄信服務 Resend，保存 30 天後自動刪除。", storage
        )
        # Closing grill Q2 of 「讓家屬找得到」 item 1: old backups are kept while the host is out
        # of reach.
        self.assertIn(
            "在備份中最多再保留 10 天，之後自動清除。連不上網站主機時，舊備份會先留著，"
            "可能暫時超過 10 天。",
            storage,
        )

    def test_who_receives_it_says_resend_also_sends_the_reminder(self):
        recipients = self.part("recipients-title", "sharing-title")
        self.assertIn(
            "Resend（寄信服務，資料存放在美國）：只在您申請重設密碼、或打開 email 重測提醒時，"
            "經手收件信箱和信的內容（使用者名稱、重設連結或提醒信的連結），保存 30 天後自動刪除。",
            recipients,
        )

    def test_the_date_moved_and_the_version_stayed(self):
        # It stayed 8; spec #733 raised it to 9 for the 整體統計 (test_aggregate_statistics).
        self.assertGreaterEqual(models.CONSENT_VERSION, 8)
        self.assertGreaterEqual(models.PRIVACY_UPDATED_ON, date(2026, 11, 17))
        updated_on = f"{models.PRIVACY_UPDATED_ON:%Y/%m/%d}"
        self.assertIn(f"第 {models.CONSENT_VERSION} 版，{updated_on} 更新", self.main)
