"""#661 (spec #656 acceptance 12-15): the email 重測提醒 turned on from a signed-in user's
HHIE-S or HHIA-S result page (the #657 mockup's result page B), under 建議您下一步."""

import json
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import NormGroup, Questionnaire
from screening.questionnaires import hhia_s, hhie_s, ioi_ha, thi
from screening.tests import test_guest, test_layout, test_reminder_switch
from screening.tests.helpers import consented_user, submission_with_answers

# 01:00 on 2026/11/17 in Taiwan, still the 16th in UTC.
NOW = datetime(2026, 11, 16, 17, tzinfo=UTC)
BLOCK = '<section class="result-reminder"'
# The owner's words beside the switch, settled on 2026-11-17 (#658).
PURPOSE = (
    "打開後，上次做完滿半年的那天早上，我們會寄一封提醒信到您的 email。信裡不會寫分數或結果。"
    "您的 email 只用來寄這個提醒和重設密碼信，隨時可以關掉。"
)


class ResultReminderTests(TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S, IOI-HA

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())  # HHIA-S, THI

    def setUp(self):
        self.enterContext(patch("django.utils.timezone.now", return_value=NOW))
        self.user = consented_user(username="result_reminder", email="a@example.com")
        self.client.force_login(self.user)

    def _result_url(self, code=hhie_s.CODE, score=0, **fields):
        count = Questionnaire.objects.get(code=code).questions.count()
        submission = submission_with_answers(self.user, code, [score] * count, **fields)
        return reverse("result", args=[submission.pk])

    def _block(self, url):
        """The page and the text of its email 重測提醒 block."""
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        page = response.content.decode()
        start = page.index(BLOCK)
        return page, page[start : page.index("</section>", start)]

    # 12
    def test_off_with_an_email_offers_it_under_the_next_step_and_comes_back_on(self):
        for code in (hhie_s.CODE, hhia_s.CODE):
            with self.subTest(code=code):
                url = self._result_url(code)
                page, block = self._block(url)
                # Under 建議您下一步, above 看完整說明.
                self.assertLess(page.index("建議您下一步"), page.index(BLOCK))
                self.assertLess(page.index(BLOCK), page.index('<details class="result-details"'))
                text = test_layout._text(block)
                self.assertIn("半年後再做一次", text)
                self.assertIn("下次建議 2027/05/17。", text)
                self.assertIn(PURPOSE, text)
                self.assertIn("到期時寄 email 提醒我", text)
                self.assertIn("會寄到 a@example.com", text)
                self.assertIn(f'action="{reverse("retest_reminder")}"', block)
                self.assertIn('name="enabled" value="1"', block)
                self.assertIn(f'name="next" value="{url}"', block)
                # An outline button: the page's main button stays 建議您下一步's, white on its
                # hero card (ADR 0076), and the page has no solid one.
                self.assertIn('class="btn btn-outline-primary', block)
                self.assertEqual(page.count("btn-primary"), 0)

                response = self.client.post(
                    reverse("retest_reminder"), {"enabled": "1", "next": url}
                )
                self.assertRedirects(response, url, fetch_redirect_response=False)
                _page, block = self._block(url)
                self.assertIn("已開啟，到期會寄到 a@example.com", test_layout._text(block))
                self.client.post(reverse("retest_reminder"), {"enabled": "0"})

    # 13
    def test_already_on_says_only_that_it_is_on(self):
        self.client.post(reverse("retest_reminder"), {"enabled": "1"})
        for code in (hhie_s.CODE, hhia_s.CODE):
            with self.subTest(code=code):
                _page, block = self._block(self._result_url(code))
                text = test_layout._text(block)
                self.assertEqual(test_reminder_switch.TICKED_ON.findall(block), ["a@example.com"])
                self.assertNotIn("<form", block)
                self.assertNotIn("到期時寄 email 提醒我", text)

    # 14
    def test_without_an_email_says_to_add_one_in_the_account_settings(self):
        self.user.email = ""
        self.user.save(update_fields=["email"])
        for code in (hhie_s.CODE, hhia_s.CODE):
            with self.subTest(code=code):
                _page, block = self._block(self._result_url(code))
                text = test_layout._text(block)
                self.assertIn("想在到期時收到 email 提醒，要先在帳號設定補上 email。", text)
                self.assertIn(f'href="{reverse("account_settings")}"', block)
                self.assertIn("到帳號設定補上 email", text)
                self.assertNotIn("<form", block)
                self.assertNotIn("會寄到", text)

    # 15
    def test_not_on_thi_or_ioi_ha_result_pages(self):
        ioi_ha_record = {
            "score": 3,
            "wearing_hearing_aid": True,
            "norm_group": NormGroup.MILD_MODERATE,
        }
        for code, record in ((thi.CODE, {}), (ioi_ha.CODE, ioi_ha_record)):
            with self.subTest(code=code):
                response = self.client.get(self._result_url(code, **record))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "result-reminder")
                self.assertNotContains(response, "到期時寄 email 提醒我")

    def test_not_on_a_guest_s_result(self):
        self.client.logout()
        cache.clear()  # the guest scoring's rate limit counts in the cache
        self.addCleanup(cache.clear)
        guest = test_guest.GuestTestCase.body
        for code in (hhie_s.CODE, hhia_s.CODE):
            with self.subTest(code=code):
                questionnaire = Questionnaire.objects.get(code=code)
                response = self.client.post(
                    test_guest.GUEST_SCORE,
                    json.dumps(guest(None, questionnaire, [0] * 10)),
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 200)
                html = response.json()["html"]
                self.assertIn("result-banner", html)
                self.assertNotIn("result-reminder", html)
                self.assertNotIn("到期時寄 email 提醒我", html)
                page = self.client.get(reverse("guest_result", args=[code]))
                self.assertEqual(page.status_code, 200)
                self.assertNotContains(page, "result-reminder")
