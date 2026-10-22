"""Spec #218, ticket #228: the hearing-aid guide entry on the home page."""

import re

from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.tests.helpers import consented_user

# Wording finalised in #220 (follow-up comment, E1).
CARD = "了解助聽器選配與補助"


class ReturningUserGuideEntryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="guide_entry_tester")
        questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        questions = Question.objects.bulk_create(
            Question(
                questionnaire=questionnaire,
                question_text=f"HHIE-S題{i}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        submission = Submission.objects.create(user=cls.user, questionnaire=questionnaire)
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=0) for question in questions
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.content = self.client.get(reverse("index")).content.decode()

    def test_more_you_can_do_has_a_guide_card_linking_to_the_summary_page(self):
        section = re.search(
            r'<section[^>]*aria-labelledby="more-title".*?</section>', self.content, re.DOTALL
        ).group(0)
        cards = re.findall(
            r'<li([^>]*)><a class="link-card" href="([^"]*)">\s*<span class="link-card-body">\s*'
            r'<span class="link-card-title">([^<]*)</span>',
            section,
        )
        self.assertIn(("", "/guide", CARD), cards)

    def test_bottom_tab_bar_is_unchanged(self):
        nav = self.content[
            self.content.index('<nav aria-label="主要導覽"') : self.content.index("</nav>")
        ]
        self.assertEqual(
            re.findall(r"<span>(.*?)</span>", nav), ["首頁", "開始篩檢", "我的紀錄", "聽力圖"]
        )
