import re

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening import models
from screening.models import Consent
from screening.tests import test_layout, test_report
from screening.tests.helpers import consented_user

ACCOUNT_LINK = re.compile(r'<a[^>]*href="/account"[^>]*>')


class AccountSettingsTests(TestCase):
    """Spec docs/specs/phase-09/phase9_ui_refresh_3_structure.md, acceptance 1-10 and 12."""

    _hhie_s = test_report.HealthReportTests._hhie_s
    _ioi_ha = test_report.HealthReportTests._ioi_ha
    # The report tests' fake questionnaires, borrowed as the classmethod itself (not bound to them).
    setUpTestData = test_report.HealthReportTests.__dict__["setUpTestData"]

    def setUp(self):
        self.url = reverse("account_settings")
        self.user = consented_user(username="settings_a", email="a@example.com", birth_year=1955)
        self.client.force_login(self.user)

    def _main(self, url=None):
        response = self.client.get(url or self.url)
        self.assertEqual(response.status_code, 200)
        # The <main> element only: the header repeats the user name.
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    # 1
    def test_shows_own_account_with_delete_last(self):
        main = self._main()
        text = test_layout._text(main)
        for expected in ("帳號設定", "settings_a", "a@example.com", "1955"):
            self.assertIn(expected, text)
        agreed = timezone.localtime(self.user.consents.get().agreed_at)
        self.assertIn(f"您在 {agreed:%Y/%m/%d} 同意了目前的版本", text)
        self.assertIn(f'href="{reverse("download_my_data")}"', main)
        # A file for keeping, not the report for a doctor (review 1).
        self.assertIn("把您在 HearWell 的所有資料下載成一個檔案保存。", text)
        self.assertNotIn("醫師", text)
        self.assertIn(f'href="{reverse("privacy")}"', main)
        links = re.findall(r'<a[^>]*href="([^"]+)"', main)
        self.assertEqual(links[-1], reverse("delete_account"))
        self.assertIn("刪除帳號", test_layout._text(main.rsplit("<a", 1)[1]))

    # 2
    def test_signed_out_goes_to_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )

    # 3
    def test_open_before_agreeing(self):
        self.user.consents.all().delete()
        Consent.objects.create(user=self.user, version=models.CONSENT_VERSION - 1)
        main = self._main()
        self.assertIn("您還沒有同意目前的隱私權說明", test_layout._text(main))
        self.assertIn(f'href="{reverse("consent")}"', main)

    # 4
    def test_blank_fields_say_not_filled(self):
        self.user.email = ""
        self.user.birth_year = None
        self.user.save()
        text = test_layout._text(self._main())
        self.assertEqual(text.count("未填"), 2)

    # 5
    def test_shows_nothing_of_other_users(self):
        consented_user(username="settings_b", email="b@example.com", birth_year=1940)
        text = test_layout._text(self._main())
        for other in ("settings_b", "b@example.com", "1940"):
            self.assertNotIn(other, text)

    # 6
    def test_header_and_footer_lead_to_settings(self):
        content = self.client.get(reverse("index")).content.decode()
        header = content.split("</header>", 1)[0]
        self.assertRegex(
            header,
            r'<a[^>]*href="/account"[^>]*aria-label="目前登入：settings_a，帳號設定"[^>]*>'
            r"\s*目前登入：<strong>settings_a</strong>\s*</a>",
        )
        self.assertRegex(test_layout._footer(content), ACCOUNT_LINK)
        self.client.logout()
        content = self.client.get(reverse("index")).content.decode()
        self.assertNotRegex(content, ACCOUNT_LINK)

    # 7
    def test_my_records_no_longer_hold_account_actions(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        main = self._main(reverse("my_hearing"))
        self.assertNotIn(f'href="{reverse("download_my_data")}"', main)
        self.assertNotIn(f'href="{reverse("delete_account")}"', main)

    # 8
    def test_delete_page_goes_back_to_settings(self):
        for staff in (False, True):
            with self.subTest(staff=staff):
                self.user.is_staff = staff
                self.user.save()
                main = self._main(reverse("delete_account"))
                self.assertIn(f'href="{self.url}"', main)
                self.assertNotIn(f'href="{reverse("my_hearing")}"', main)

    # 9
    def test_privacy_notice_points_to_settings(self):
        text = test_layout._text(self._main(reverse("privacy")))
        self.assertIn("登入後到「帳號設定」頁按「下載我的資料」", text)
        self.assertIn("登入後到「帳號設定」頁按「刪除帳號」", text)
        self.assertNotIn("到「我的紀錄」頁按", text)
        self.assertEqual(models.CONSENT_VERSION, 1)

    # 10
    def test_questionnaire_switch(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=2)
        main = self._main(reverse("my_hearing"))
        self.assertNotIn('class="history-tabs"', main)
        basis = self._hhie_s(self.user, test_report.UNAIDED, wearing=False, days_ago=3)
        self._ioi_ha(self.user, basis, days_ago=1)
        main = self._main(f"{reverse('my_hearing')}?questionnaire=hhie-s")
        nav = re.search(r'<nav class="history-tabs"[^>]*>(.*?)</nav>', main, re.S).group(1)
        links = re.findall(r"<a ([^>]*)>([^<]*)</a>", nav)
        self.assertEqual([text for _, text in links], ["HHIE-S", "IOI-HA"])
        self.assertIn('aria-current="page"', links[0][0])
        self.assertNotIn("aria-current", links[1][0])

    # 12
    def test_home_order_and_text(self):
        expected = (
            "了解聽力對您生活的影響",
            "聽力變化很慢，自己常常沒發現。花 3 分鐘看看聽力對生活的影響。",
            "開始篩檢",
            "回答問題，大約 3 分鐘。",
            "很多人在察覺聽力問題好幾年後，才尋求協助。及早了解，才能及早處理。",
            "由聽力師開發",  # replaced the old one-line claim (phase9_ui_refresh_4a_home.md 4.1)
        )
        for logged_in in (True, False):
            if not logged_in:
                self.client.logout()
            with self.subTest(logged_in=logged_in):
                text = test_layout._text(self._main(reverse("index")))
                positions = [text.index(part) for part in expected]
                self.assertEqual(positions, sorted(positions))
                self.assertNotIn("可達 10 年", text)
                self.assertNotIn("結果僅供參考", text)
