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
