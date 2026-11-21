"""#746 (spec #741 acceptance 25 as the 實作中本人補充 rewrote it, grill Q14, Q17): an IOI-HA
result page compares with the same person's IOI-HA before it item by item, better, worse or the
same, with no totals. Every item is best at 5, so a higher score is better."""

import re
from datetime import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, NormGroup, Question, Questionnaire, Submission
from screening.questionnaires import ioi_ha
from screening.tests.helpers import consented_user

ITEMS = ("使用時間", "幫助程度", "剩餘困難", "值得程度", "生活影響", "干擾他人", "生活樂趣")


class IoiHaSinceLastTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="ioi_since_last")
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code=ioi_ha.CODE)
        cls.questions = Question.objects.bulk_create(
            Question(questionnaire=cls.ioi_ha, question_text=f"IOI題{i}", question_number=i)
            for i in range(1, 8)
        )

    def setUp(self):
        self.client.force_login(self.user)

    def record(self, scores, day, user=None):
        submission = Submission.objects.create(
            user=user or self.user,
            questionnaire=self.ioi_ha,
            wearing_hearing_aid=True,
            norm_group=NormGroup.UNGROUPED,
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(self.questions, scores, strict=True)
        )
        moment = timezone.make_aware(datetime(*day, 12))
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def section(self, submission):
        content = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        found = re.search(r'<section class="ioi-since-last".*?</section>', content, re.S)
        return found and found.group(0)

    def text(self, html):
        html = re.sub(r"<svg.*?</svg>", "", html, flags=re.S)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()

    def test_the_second_one_shows_each_item_s_change_without_totals(self):
        # Spec #741 acceptance 25: items 1 and 4 better, 2 worse, the rest the same; no total
        # (21 then 23) and no sentence on it.
        self.record((3, 3, 3, 3, 3, 3, 3), (2026, 8, 1))
        second = self.record((4, 2, 3, 5, 3, 3, 3), (2026, 11, 12))
        changes = ("變好", "變差", "一樣", "變好", "一樣", "一樣", "一樣")
        section = self.text(self.section(second))
        self.assertEqual(
            section,
            "和上一次比較 "
            + " ".join(f"{name} {change}" for name, change in zip(ITEMS, changes, strict=True)),
        )
        for gone in ("分", "21", "23"):
            self.assertNotIn(gone, section)

    def test_the_first_one_has_no_comparison(self):
        self.assertIsNone(self.section(self.record((3,) * 7, (2026, 8, 1))))

    def test_an_older_one_compares_with_the_one_before_it_and_never_another_user_s(self):
        # Item 1 against 2026/07/01's 2 the same, against the other user's 5 or 2026/09/01's 1
        # it would not be.
        other = consented_user(username="ioi_since_last_other")
        self.record((5,) * 7, (2026, 7, 15), user=other)
        self.record((2,) * 7, (2026, 7, 1))
        middle = self.record((2, 3, 3, 3, 3, 3, 3), (2026, 8, 1))
        self.record((1,) * 7, (2026, 9, 1))
        self.assertIn("使用時間 一樣 幫助程度 變好", self.text(self.section(middle)))
