"""#746 (spec #741 acceptance 25, grill Q14, Q17): an IOI-HA result page compares with the same
person's IOI-HA before it, as the HHI comparison does: both totals side by side, and each item
better, worse or the same. Every item is best at 5, so a higher score is better."""

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

    def test_the_second_one_shows_both_totals_and_each_item_s_change(self):
        # Spec #741 acceptance 25: 21 then 23, items 1 and 4 better, 2 worse, the rest the same.
        self.record((3, 3, 3, 3, 3, 3, 3), (2026, 8, 1))
        second = self.record((4, 2, 3, 5, 3, 3, 3), (2026, 11, 12))
        changes = ("變好", "變差", "一樣", "變好", "一樣", "一樣", "一樣")
        self.assertEqual(
            self.text(self.section(second)),
            "和上一次比較 上一次 21 分 2026/08/01 這一次 23 分 2026/11/12 "
            "這一次比上一次多 2 分（分數越高越好） "
            + " ".join(f"{name} {change}" for name, change in zip(ITEMS, changes, strict=True)),
        )

    def test_lower_and_the_same_totals(self):
        self.record((3, 3, 3, 3, 3, 3, 3), (2026, 8, 1))
        lower = self.record((2, 3, 3, 3, 3, 3, 3), (2026, 9, 1))
        same = self.record((2, 3, 3, 3, 3, 3, 3), (2026, 10, 1))
        self.assertIn("這一次比上一次少 1 分（分數越高越好）", self.text(self.section(lower)))
        self.assertIn("兩次的總分一樣", self.text(self.section(same)))

    def test_the_first_one_has_no_comparison(self):
        self.assertIsNone(self.section(self.record((3,) * 7, (2026, 8, 1))))

    def test_an_older_one_compares_with_the_one_before_it_and_never_another_user_s(self):
        other = consented_user(username="ioi_since_last_other")
        self.record((1,) * 7, (2026, 6, 1), user=other)
        self.record((2,) * 7, (2026, 7, 1))
        middle = self.record((3,) * 7, (2026, 8, 1))
        self.record((5,) * 7, (2026, 9, 1))
        self.assertIn("上一次 14 分 2026/07/01 這一次 21 分", self.text(self.section(middle)))
