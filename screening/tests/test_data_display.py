import re
from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse

from screening.models import Category, Question, Questionnaire, Submission
from screening.tests import test_layout, test_report
from screening.tests.helpers import consented_user

TAIPEI = ZoneInfo("Asia/Taipei")
IOI_DIRECTION = "7 題都是分數越高，代表助聽器的效益越好。"


class DataDisplayTests(TestCase):
    """Spec docs/specs/phase-09/phase9_ui_refresh_2_data.md, acceptance 9 and 13 (Django-drawn parts)."""

    _hhie_s = test_report.HealthReportTests._hhie_s
    _ioi_ha = test_report.HealthReportTests._ioi_ha

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
        self.user = consented_user(username="display_a")
        self.client.force_login(self.user)

    def _at(self, submission, *when):
        Submission.objects.filter(pk=submission.pk).update(
            created_at=datetime(*when, tzinfo=TAIPEI)
        )
        return submission

    def _page(self, questionnaire="hhie-s"):
        response = self.client.get(f"{reverse('my_hearing')}?questionnaire={questionnaire}")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    # 9
    def test_cards_on_a_shared_day_show_the_time(self):
        early = self._at(self._hhie_s(self.user, [2] * 10, False, 0), 2026, 10, 15, 14, 30)
        late = self._at(self._hhie_s(self.user, [0] * 10, True, 0), 2026, 10, 15, 16, 10)
        alone = self._at(self._hhie_s(self.user, [4] * 10, False, 0), 2026, 10, 1, 9, 5)
        cards = test_layout._cards(self._page())
        text = {
            pk: test_layout._text(next(c for c in cards if reverse("result", args=[pk]) in c))
            for pk in (early.pk, late.pk, alone.pk)
        }
        self.assertIn("2026/10/15 14:30", text[early.pk])
        self.assertIn("2026/10/15 16:10", text[late.pk])
        self.assertIn("2026/10/01", text[alone.pk])
        self.assertNotIn("09:05", text[alone.pk])

    # 18: the chart draws only the day's last record of a status; the cards keep both
    def test_cards_keep_both_records_of_a_status_on_one_day(self):
        early = self._at(self._hhie_s(self.user, [1] * 10, False, 0), 2026, 10, 15, 9, 0)
        late = self._at(self._hhie_s(self.user, [2] * 10, False, 0), 2026, 10, 15, 15, 0)
        cards = test_layout._cards(self._page())
        for record, time in ((early, "09:00"), (late, "15:00")):
            card = next(c for c in cards if reverse("result", args=[record.pk]) in c)
            self.assertIn(f"2026/10/15 {time}", test_layout._text(card))

    # 9: a shared day across questionnaires is not a shared day within one tab
    def test_other_questionnaire_on_the_same_day_adds_no_time(self):
        basis = self._at(self._hhie_s(self.user, [4] * 10, False, 0), 2026, 10, 15, 9, 0)
        self._at(self._ioi_ha(self.user, basis), 2026, 10, 15, 10, 0)
        card = next(
            c for c in test_layout._cards(self._page()) if reverse("result", args=[basis.pk]) in c
        )
        self.assertNotIn("09:00", test_layout._text(card))

    # 13 (IOI-HA part), grouped and ungrouped
    def test_ioi_ha_says_higher_is_better(self):
        basis = self._hhie_s(self.user, test_report.UNAIDED, False, 3)
        self._ioi_ha(self.user, basis, days_ago=2)
        self.assertIn(IOI_DIRECTION, self._page("ioi-ha"))
        other = consented_user(username="display_b")
        self.client.force_login(other)
        self._ioi_ha(other, None)
        self.assertIn(IOI_DIRECTION, self._page("ioi-ha"))

    # 12 (structure; the alignment itself is measured in the browser by e2e)
    def test_ioi_ha_draws_one_line_per_score_row(self):
        basis = self._hhie_s(self.user, test_report.UNAIDED, False, 3)
        self._ioi_ha(self.user, basis, days_ago=2)
        content = self._page("ioi-ha")
        # Lines come first in each grid, so the text up to the first </div> holds them all.
        grids = re.findall(r'<div class="ioi-grid"[^>]*>(.*?)</div>', content, re.S)
        self.assertEqual(len(grids), 8)  # the score axis and 7 items
        for grid in grids:
            rows = re.findall(r'<i class="ioi-line" style="grid-row: (\d)"></i>', grid)
            self.assertEqual(rows, ["1", "2", "3", "4", "5"])
