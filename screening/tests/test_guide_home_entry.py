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

    def test_bottom_tab_bar_is_home_screening_records_learn(self):
        nav = self.content[
            self.content.index('<nav aria-label="主要導覽"') : self.content.index("</nav>")
        ]
        self.assertEqual(re.findall(r"<span>(.*?)</span>", nav), ["首頁", "篩檢", "紀錄", "了解"])


class NewUserGuideEntryTests(TestCase):
    """The owner picked option B: one card between the steps and the result preview. #471
    (mockup #458 ⑪): the visitor's home is the 空狀態首頁 too, the way in a text link."""

    def test_visitor_sees_the_guide_link_after_the_start_button(self):
        content = self.client.get(reverse("index")).content.decode()
        link = content.index(f'<li><a href="/guide">{CARD}</a></li>')
        self.assertGreater(link, content.index(">開始篩檢</a>"))

    def test_signed_in_user_without_records_has_a_guide_link(self):
        # #459: the 空狀態首頁 keeps the way in as a text link (mockup #458 A).
        self.client.force_login(consented_user(username="guide_entry_new"))
        content = self.client.get(reverse("index")).content.decode()
        self.assertIn(f'<li><a href="/guide">{CARD}</a></li>', content)
