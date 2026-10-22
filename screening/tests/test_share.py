import json
import re
from datetime import date, timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening import models
from screening.models import Category, Consent, Question, Questionnaire, ReportShare
from screening.scoring import IOI_HA_BELOW_NORM_NOTES, classify
from screening.tests import test_report
from screening.tests.helpers import consented_user

INVALID_TEXT = "這個連結已經失效，請向分享的家人要新的連結"
SCORE = re.compile(r"\d+ 分")
COVER_TEXT = "家人分享了一份 HearWell 聽力報告給您"
TOKEN_WITH_DB = "XKCHYOI8__zeol2dBAdjP9Vp19URZ_MGg9va6Do_KVs"


def _taipei(moment):
    return timezone.localtime(moment).strftime("%Y/%m/%d %H:%M")


class ReportShareTests(TestCase):
    """Spec docs/specs/phase-08/phase8_c1_family_share.md, acceptance 1-23 (24 is manual)."""

    # Same fake records as the report tests, so both pages are compared on equal data.
    _hhie_s = test_report.HealthReportTests._hhie_s
    _ioi_ha = test_report.HealthReportTests._ioi_ha
    _audiogram = test_report.HealthReportTests._audiogram
    _full_records = test_report.HealthReportTests._full_records

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhie_questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhie_s,
                question_text=f"假 HHIE 題{i}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        cls.ioi_questions = Question.objects.bulk_create(
            Question(questionnaire=cls.ioi_ha, question_text=f"假 IOI 題{i}", question_number=i)
            for i in range(1, 8)
        )

    def setUp(self):
        self.user = consented_user(username="share_a", email="a@example.com", birth_year=1955)
        self.other = consented_user(username="share_b", email="b@example.com")
        self.client.force_login(self.user)

    def _create(self, **data):
        return self.client.post(reverse("report_share_create"), data or {"confirm": "1"})

    def _share(self, user=None):
        """An active link made the way a user makes one."""
        self.client.force_login(user or self.user)
        self._create()
        return ReportShare.objects.active().get(user=user or self.user)

    def _cover(self, share):
        return self.client.get(reverse("shared_cover", args=[share.token]))

    def _shared(self, share):
        return self.client.get(reverse("shared_report", args=[share.token]))

    def _report(self):
        response = self.client.get(reverse("health_report"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _assert_invalid(self, token):
        for name in ("shared_cover", "shared_report"):
            response = self.client.get(reverse(name, args=[token]))
            self.assertContains(response, INVALID_TEXT, status_code=404)
            self.assertNotRegex(response.content.decode(), SCORE)
            self.assertNotContains(response, "打開報告", status_code=404)

    # 1
    def test_create_shows_link_expiry_and_zero_opens(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        before = timezone.now()
        response = self._create()
        self.assertRedirects(response, reverse("health_report"))
        share = ReportShare.objects.get(user=self.user)
        self.assertGreaterEqual(share.expires_at, before + timedelta(days=7))
        self.assertLessEqual(share.expires_at, timezone.now() + timedelta(days=7))
        content = self._report()
        self.assertIn(f"https://testserver{reverse('shared_cover', args=[share.token])}", content)
        self.assertIn(f"有效到 {_taipei(share.expires_at)}", content)
        self.assertIn("已開啟 0 次", content)
        self.assertIn("還沒有人打開", content)
        self.assertIn("取消分享", content)

    # 1: the code cannot be guessed, and carries no user id
    def test_token_is_long_random_and_unrelated_to_user(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        first = self._share()
        first.revoked_at = timezone.now()
        first.save()
        second = self._share()
        self.assertGreaterEqual(len(second.token), 40)
        self.assertNotEqual(first.token, second.token)
        self.assertEqual(reverse("shared_cover", args=[second.token]), f"/shared/{second.token}")

    # 2
    def test_family_sees_same_results_as_owner(self):
        self._full_records()
        share = self._share()
        owner = self._report()
        self.client.logout()
        response = self._shared(share)
        self.assertEqual(response.status_code, 200)
        shared = response.content.decode()
        for section in ["report-summary", *test_report.SECTION_ORDER]:
            with self.subTest(section=section):
                self.assertNotEqual(test_report._section(owner, section), "")
                self.assertEqual(
                    test_report._section(shared, section), test_report._section(owner, section)
                )
        self.assertIn("不是醫療診斷", shared)
        self.assertIn(
            f"這是家人分享給您的報告，連結有效到 {timezone.localtime(share.expires_at):%-m月%-d日}",
            shared,
        )

    # 3
    def test_expired_link_is_invalid(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        ReportShare.objects.filter(pk=share.pk).update(expires_at=timezone.now())
        self.client.logout()
        self._assert_invalid(share.token)

    # 4
    def test_cancelled_link_is_invalid(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        response = self.client.post(reverse("report_share_cancel", args=[share.pk]))
        self.assertRedirects(response, reverse("health_report"))
        self.assertFalse(ReportShare.objects.active().exists())
        self.client.logout()
        self._assert_invalid(share.token)

    # 5
    def test_deleted_account_link_is_invalid(self):
        self._full_records()
        share = self._share()
        self.user.delete_with_data()
        self.assertFalse(ReportShare.objects.exists())
        self._assert_invalid(share.token)

    # 6
    def test_cannot_cancel_someone_elses_link(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        self.client.force_login(self.other)
        response = self.client.post(reverse("report_share_cancel", args=[share.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ReportShare.objects.active().filter(pk=share.pk).exists())
        # Nor see it: the other user's report page shows no trace of A's link.
        self.assertNotIn(share.token, self._report())

    # 7
    def test_unknown_or_malformed_code_is_invalid(self):
        self.client.logout()
        for token in ("x" * 43, "abc", "not-a-real-code"):
            with self.subTest(token=token):
                self._assert_invalid(token)

    # phase9_ui_refresh_4d_ioi_ha_items.md acceptance 6a: the family copy has no notes either
    def test_ioi_ha_notes_not_in_shared_report(self):
        self._full_records()  # item 2 is below the norm
        share = self._share()
        self.client.logout()
        content = self._shared(share).content.decode()
        self.assertIn("低於常模", content)
        self.assertNotIn(IOI_HA_BELOW_NORM_NOTES[2], content)

    # 8
    def test_owner_sees_open_count_and_last_open(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        self.client.logout()
        for _ in range(3):
            self._shared(share)
        share.refresh_from_db()
        self.assertEqual(share.open_count, 3)
        self.client.force_login(self.user)
        content = self._report()
        self.assertIn("已開啟 3 次", content)
        self.assertIn(f"最後一次開啟：{_taipei(share.last_opened_at)}", content)
        self.assertNotIn("還沒有人打開", content)

    # 9
    def test_family_pages_not_cached_indexed_or_referred(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        self.client.logout()
        responses = {
            "cover": self._cover(share),
            "report": self._shared(share),
            "invalid": self.client.get(reverse("shared_cover", args=["x" * 43])),
        }
        for name, response in responses.items():
            with self.subTest(page=name):
                self.assertIn("no-store", response["Cache-Control"])
                self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
                self.assertEqual(response["Referrer-Policy"], "no-referrer")
                self.assertContains(
                    response,
                    '<meta name="robots" content="noindex, nofollow">',
                    status_code=response.status_code,
                )

    # 10
    def test_zero_score_shown_as_zero(self):
        self._hhie_s(self.user, [0] * 10, wearing=False, days_ago=1)
        share = self._share()
        self.client.logout()
        section = test_report._section(self._shared(share).content.decode(), "report-hhie-s")
        self.assertIn("0 分", section)
        self.assertIn(classify(0, "hhie-s")["text"], section)

    # 11
    def test_signed_out_cannot_manage(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        self.client.logout()
        login = reverse("login")
        for url in (
            reverse("report_share_create"),
            reverse("report_share_cancel", args=[share.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.post(url, {"confirm": "1"})
                self.assertRedirects(response, f"{login}?next={url}", fetch_redirect_response=False)
        self.assertEqual(ReportShare.objects.count(), 1)
        self.assertTrue(ReportShare.objects.active().filter(pk=share.pk).exists())

    # 12
    def test_no_records_cannot_share(self):
        content = self._report()
        self.assertNotIn("產生分享連結", content)
        self._create()
        self.assertFalse(ReportShare.objects.exists())

    # 13
    def test_query_count_does_not_grow(self):
        self._audiogram(self.user, date(2026, 9, 28), right_air=(40, 45, 50, 45), left_air=())
        # Aided and unaided both present from the start, so only the record count differs.
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        self._hhie_s(self.user, test_report.UNAIDED, wearing=False, days_ago=2)
        share = self._share()
        self.client.logout()
        with CaptureQueriesContext(connection) as two:
            self._shared(share)
        for day in range(3, 21):
            self._hhie_s(self.user, test_report.UNAIDED, wearing=False, days_ago=day)
        with CaptureQueriesContext(connection) as twenty:
            self._shared(share)
        self.assertEqual(len(twenty), len(two))

    # 14
    def test_only_one_active_link(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        self.assertNotIn("產生分享連結", self._report())
        self._create()
        self.assertEqual(list(ReportShare.objects.active()), [share])
        self.assertEqual(ReportShare.objects.count(), 1)

    # 15
    def test_cover_has_no_health_data_and_does_not_count(self):
        self._full_records()
        share = self._share()
        # A real CI token that contains "dB" (PR #233), so the token can't pass for health data.
        ReportShare.objects.filter(pk=share.pk).update(token=TOKEN_WITH_DB)
        share.refresh_from_db()
        self.client.logout()
        response = self._cover(share)
        self.assertContains(response, COVER_TEXT)
        self.assertContains(response, f'href="{reverse("shared_report", args=[share.token])}"')
        self.assertContains(response, "打開報告")
        self.assertContains(
            response, f"連結有效到 {timezone.localtime(share.expires_at):%-m月%-d日}"
        )
        # The random token in the link isn't health data, but could contain "dB" by chance.
        content = response.content.decode().replace(share.token, "")
        self.assertNotRegex(content, SCORE)
        for text in ("顯著影響", "dB", "聽力圖", "歲", 'id="audiogram-chart"'):
            with self.subTest(text=text):
                self.assertNotIn(text, content)
        share.refresh_from_db()
        self.assertEqual(share.open_count, 0)
        self.assertIsNone(share.last_opened_at)
        self._shared(share)
        share.refresh_from_db()
        self.assertEqual(share.open_count, 1)
        self.assertIsNotNone(share.last_opened_at)

    # 16
    def test_privacy_notice_mentions_sharing_without_asking_again(self):
        response = self.client.get(reverse("privacy"))
        self.assertContains(response, "您可以主動把聽力報告分享給別人")
        self.assertContains(response, "拿到連結的人不用登入就看得到")
        self.assertContains(response, models.PRIVACY_UPDATED_ON.strftime("%Y/%m/%d"))
        self.assertTrue(self.user.has_consented())
        self.assertEqual(self.client.get(reverse("health_report")).status_code, 200)

    # 17
    def test_link_works_while_owner_has_not_agreed_to_new_notice(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        self.user.consents.all().delete()
        Consent.objects.create(user=self.user, version=models.CONSENT_VERSION - 1)
        self.assertFalse(self.user.has_consented())
        self.client.logout()
        self.assertEqual(self._shared(share).status_code, 200)

    # 17 (4.2): a family member signed in to their own account, not yet agreed, is not stopped
    def test_signed_in_viewer_without_consent_can_open(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        viewer = models.User.objects.create_user(username="family_viewer")
        self.client.force_login(viewer)
        self.assertEqual(self._cover(share).status_code, 200)
        self.assertEqual(self._shared(share).status_code, 200)

    # 18
    def test_share_block_on_report_and_not_printed(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        content = self._report()
        self.assertRegex(content, r'<section[^>]*id="report-share"[^>]*class="[^"]*no-print')
        self.assertLess(content.index('id="report-share"'), content.index('id="report-summary"'))
        self.assertIn("產生分享連結", test_report._section(content, "report-share"))

    # 19
    def test_family_version_hides_identity_but_shows_age(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        self.client.logout()
        content = self._shared(share).content.decode()
        for text in ("share_a", "1955", "姓名：", "a@example.com", "出生年"):
            with self.subTest(text=text):
                self.assertNotIn(text, content)
        self.assertIn(f"年齡：{date.today().year - 1955} 歲", content)

        self._hhie_s(self.other, test_report.AIDED, wearing=True, days_ago=1)
        other_share = self._share(self.other)
        self.client.logout()
        self.assertNotIn("年齡：", self._shared(other_share).content.decode())

    # 20
    def test_family_sees_latest_records(self):
        self._hhie_s(self.user, test_report.UNAIDED, wearing=False, days_ago=3)
        share = self._share()
        self.assertIn("連結有效期間，家人看到的是您最新的報告", self._report())
        newer = self._hhie_s(self.user, [0] * 10, wearing=True, days_ago=0)
        self.client.logout()
        section = test_report._section(self._shared(share).content.decode(), "report-hhie-s")
        self.assertIn(f"最近一次 {timezone.localtime(newer.created_at):%Y/%m/%d}", section)
        self.assertIn("共 2 次", section)

    # 21
    def test_export_lists_shares_without_code(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        cancelled = self._share()
        self.client.post(reverse("report_share_cancel", args=[cancelled.pk]))
        active = self._share()
        self._shared(active)
        response = self.client.get(reverse("download_my_data"))
        text = response.content
        data = json.loads(text)
        shares = data["report_shares"]
        self.assertEqual(len(shares), 2)
        for item in shares:
            self.assertEqual(
                set(item),
                {"created_at", "expires_at", "cancelled", "open_count", "last_opened_at"},
            )
        by_cancelled = {item["cancelled"]: item for item in shares}
        self.assertEqual(by_cancelled[False]["open_count"], 1)
        self.assertIsNotNone(by_cancelled[False]["last_opened_at"])
        self.assertEqual(by_cancelled[True]["open_count"], 0)
        self.assertIsNone(by_cancelled[True]["last_opened_at"])
        decoded = text.decode()
        self.assertNotIn(cancelled.token, decoded)
        self.assertNotIn(active.token, decoded)

    # 22
    def test_after_expiry_or_cancel_block_starts_over(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        self.client.logout()
        self._shared(share)
        self.client.force_login(self.user)
        for end in ("expired", "cancelled"):
            with self.subTest(end=end):
                if end == "expired":
                    ReportShare.objects.filter(pk=share.pk).update(expires_at=timezone.now())
                else:
                    share = self._share()
                    self.client.post(reverse("report_share_cancel", args=[share.pk]))
                block = test_report._section(self._report(), "report-share")
                self.assertIn("產生分享連結", block)
                self.assertNotIn("已開啟", block)
                self.assertNotIn(share.token, block)

    # 23
    def test_nothing_made_without_confirm(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        block = test_report._section(self._report(), "report-share")
        # The confirm button sits inside the closed <details>, so it is never the first click.
        self.assertRegex(block, re.compile(r'<details>.*name="confirm".*</details>', re.S))
        self._create(other="1")
        self.assertFalse(ReportShare.objects.exists())

    def test_cannot_cancel_an_already_ended_link(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        ReportShare.objects.filter(pk=share.pk).update(expires_at=timezone.now())
        response = self.client.post(reverse("report_share_cancel", args=[share.pk]))
        self.assertEqual(response.status_code, 404)

    # Review 3-1 (4.1): signed in but not agreed yet goes to consent, nothing made or cancelled
    def test_not_consented_owner_sent_to_consent(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        share = self._share()
        self.user.consents.all().delete()
        for url in (
            reverse("report_share_create"),
            reverse("report_share_cancel", args=[share.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.post(url, {"confirm": "1"})
                self.assertRedirects(
                    response, f"{reverse('consent')}?next={url}", fetch_redirect_response=False
                )
        self.assertEqual(ReportShare.objects.count(), 1)
        self.assertTrue(ReportShare.objects.active().filter(pk=share.pk).exists())

    # Review 3-3 (4.2): no internal ids, i.e. no links into the owner's records
    def test_family_version_has_no_links_to_records(self):
        self._full_records()
        share = self._share()
        self.client.logout()
        content = self._shared(share).content.decode()
        for path in ("/submission/", "/audiograms/"):
            with self.subTest(path=path):
                self.assertNotIn(path, content)
