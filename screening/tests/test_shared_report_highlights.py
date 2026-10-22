import re
from datetime import date, datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Category, Question, Questionnaire, ReportShare, Submission
from screening.tests import test_report
from screening.tests.helpers import consented_user

INTRO = "這是您的家人在 HearWell 自己作答與輸入的自我篩檢結果。"
DISCLAIMER = "結果僅供參考，不能取代聽力檢查與醫師診斷。"
TAG = re.compile(r"<[^>]+>")


def _text(html):
    return re.sub(r"\s+", " ", TAG.sub("", html)).strip()


def _card(content, card_id):
    match = re.search(rf'<section[^>]*id="{card_id}".*?</section>', content, re.S)
    return match.group(0) if match else ""


class SharedReportHighlightsTests(TestCase):
    """Spec #183 batch 2, ticket #194: what the family sees above the shared report."""

    # Same fake records as the report tests.
    _hhie_s = test_report.HealthReportTests._hhie_s
    _ioi_ha = test_report.HealthReportTests._ioi_ha
    _audiogram = test_report.HealthReportTests._audiogram

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
        self.user = consented_user(username="shared_a", email="a@example.com")
        self.share = ReportShare.objects.create(user=self.user)

    def _shared(self, share=None):
        # The family is never logged in.
        response = self.client.get(reverse("shared_report", args=[(share or self.share).token]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _on(self, submission, day):
        # A fixed date (noon in Taipei), so the expected text is a plain literal.
        moment = timezone.make_aware(datetime(2026, 10, day, 12))
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)

    def _right_moderate_left_mild(self):
        # Right 45 dB HL 中度, left 35 dB HL 輕度 (the report tests' audiogram).
        return self._audiogram(
            self.user,
            date(2026, 9, 28),
            right_air=(40, 45, 50, 45),
            left_air=(30, 35, 40, 35),
        )

    # Acceptance 16
    def test_highlights_show_latest_life_impact_and_both_ears(self):
        self._on(self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=2), 20)  # 20
        self._right_moderate_left_mild()
        content = self._shared()
        self.assertIn(INTRO, content)
        highlights = _text(_card(content, "family-highlights"))
        self.assertIn("先看重點", highlights)
        self.assertIn("聽力對生活的影響", highlights)
        self.assertIn("輕度到中度影響", highlights)
        self.assertIn("2026/10/20 作答", highlights)
        self.assertRegex(highlights, r"右耳：\s*中度\s+左耳：\s*輕度")
        self.assertIn(DISCLAIMER, highlights)

    # Acceptance 17
    def test_only_an_audiogram_lists_only_the_two_ears(self):
        self._right_moderate_left_mild()
        highlights = _text(_card(self._shared(), "family-highlights"))
        self.assertRegex(highlights, r"右耳：\s*中度\s+左耳：\s*輕度")
        self.assertNotIn("聽力對生活的影響", highlights)
        self.assertNotIn("作答", highlights)

    def test_only_life_impact_lists_no_ears(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=2)
        highlights = _text(_card(self._shared(), "family-highlights"))
        self.assertIn("聽力對生活的影響", highlights)
        self.assertNotIn("右耳", highlights)
        self.assertNotIn("聽力圖", highlights)

    # Acceptance 17
    def test_no_life_impact_and_no_audiogram_hides_the_card(self):
        self._ioi_ha(self.user, basis=None)
        content = self._shared()
        self.assertIn("IOI-HA", content)  # the full report still shows
        self.assertNotIn("family-highlights", content)
        self.assertNotIn("先看重點", content)

    def test_life_impact_is_the_latest_one_as_on_the_home_page(self):
        # Newer records of other questionnaires do not replace the latest life-impact one.
        self._on(self._hhie_s(self.user, [0] * 10, wearing=False, days_ago=9), 10)  # 0
        self._on(self._hhie_s(self.user, test_report.UNAIDED, wearing=False, days_ago=5), 15)
        self._on(self._ioi_ha(self.user, basis=None), 20)
        highlights = _text(_card(self._shared(), "family-highlights"))
        self.assertIn("2026/10/15 作答", highlights)
        self.assertIn("顯著影響", highlights)  # 26
        self.assertNotIn("2026/10/10", highlights)
        self.assertNotIn("2026/10/20", highlights)

    def test_highlights_use_the_latest_audiogram(self):
        self._audiogram(
            self.user, date(2026, 5, 1), right_air=(10, 10, 10, 10), left_air=(10, 10, 10, 10)
        )
        self._right_moderate_left_mild()  # 2026/09/28
        highlights = _text(_card(self._shared(), "family-highlights"))
        self.assertIn("聽力圖（2026/09/28）", highlights)
        self.assertNotIn("正常", highlights)

    def test_an_ear_without_enough_points_says_it_cannot_be_read(self):
        # Q21: an ear without its four-frequency average is written as on the audiogram card.
        self._audiogram(self.user, date(2026, 9, 28), right_air=(40, 45, 50, 45), left_air=(30,))
        highlights = _text(_card(self._shared(), "family-highlights"))
        self.assertRegex(highlights, r"右耳：\s*中度\s+左耳：\s*資料不足，無法判讀")

    # Acceptance 16 (ticket #194 acceptance 4)
    def test_help_cards_link_to_the_three_family_guide_sections(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=2)
        help_card = _card(self._shared(), "family-help")
        self.assertIn("您可以怎麼幫忙", _text(help_card))
        links = re.findall(r'<a class="link-card" href="([^"]+)">(.*?)</a>', help_card, re.S)
        self.assertEqual(
            [(href, _text(body).rstrip("› ")) for href, body in links],
            [
                ("/family#talk-title", "怎麼跟聽損的家人說話"),
                ("/family#aid-title", "陪伴配戴助聽器"),
                ("/family#urgent-title", "什麼時候要馬上就醫"),
            ],
        )
        guide = self.client.get(reverse("family_guide")).content.decode()
        for anchor, title in (
            ("talk-title", "怎麼跟聽損的家人說話"),
            ("aid-title", "陪伴配戴助聽器"),
            ("urgent-title", "什麼時候要馬上就醫"),
        ):
            with self.subTest(anchor=anchor):
                self.assertRegex(guide, rf'id="{anchor}"[^>]*>{title}<')

    def test_help_links_carry_no_share_token_and_the_page_sends_no_referrer(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=2)
        response = self.client.get(reverse("shared_report", args=[self.share.token]))
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        help_card = _card(response.content.decode(), "family-help")
        self.assertEqual(len(re.findall(r"<a ", help_card)), 3)
        self.assertNotIn(self.share.token, help_card)
