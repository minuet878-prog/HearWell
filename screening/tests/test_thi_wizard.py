"""THI on the wizard result: one line for anyone with tinnitus, no extra step (#216, spec #208)."""

import uuid
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Questionnaire, Submission
from screening.tests.helpers import consented_user, step_bar


class ThiWizardTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        cls.by_code = {q.code: q for q in Questionnaire.objects.defined()}

    def login_age(self, age):
        # age None: no birth year. Subtests log in more than one user per test.
        user = consented_user(
            username=f"thi_wizard_{age}_{uuid.uuid4().hex[:8]}",
            birth_year=None if age is None else date.today().year - age,
        )
        self.client.force_login(user)
        return user

    def wizard(self, **params):
        return self.client.get(reverse("questionnaire_list"), params)

    def assert_tinnitus_line(self, page):
        thi = reverse("screening", args=[self.by_code["thi"].pk])
        self.assertContains(page, f'<a href="{thi}">如果您有耳鳴：耳鳴障礙量表（THI）</a>', count=1)

    def test_unaided_result_offers_thi_to_anyone_with_tinnitus(self):
        for age in (30, 80):
            with self.subTest(age=age):
                self.login_age(age)
                self.assert_tinnitus_line(self.wizard(hearing_aid="no"))

    def test_aided_result_offers_thi_and_keeps_also_worth_doing(self):
        for norm_basis in (False, True):
            with self.subTest(norm_basis=norm_basis):
                user = self.login_age(80)
                if norm_basis:
                    # An unaided HHIE-S answered in full sets the IOI-HA norm group.
                    hhie = self.by_code["hhie-s"]
                    submission = Submission.objects.create(
                        user=user, questionnaire=hhie, wearing_hearing_aid=False
                    )
                    Answer.objects.bulk_create(
                        Answer(submission=submission, question=question, score=2)
                        for question in hhie.questions.all()
                    )
                page = self.wizard(hearing_aid="yes")
                recommended = "ioi-ha" if norm_basis else "hhie-s"
                self.assertEqual(page.context["recommended"], self.by_code[recommended])
                self.assert_tinnitus_line(page)
                main = page.content.decode()
                also = main[main.index("也可以做") : main.index("看其他問卷")]
                for code in ("ssq12-tw", "sadl"):
                    self.assertIn(
                        f'href="{reverse("screening", args=[self.by_code[code].pk])}"', also
                    )
                # With a norm basis, the aided life-impact retake comes first (F1).
                self.assertEqual(also.count("questionnaire-card"), 3 if norm_basis else 2)

    def test_asking_age_still_takes_three_steps(self):
        self.login_age(None)
        self.assertEqual(step_bar(self.wizard()), (1, 3))
        self.assertEqual(step_bar(self.wizard(age_group="older")), (2, 3))
        page = self.wizard(age_group="older", hearing_aid="no")
        self.assertEqual(step_bar(page), (3, 3))
        self.assert_tinnitus_line(page)
