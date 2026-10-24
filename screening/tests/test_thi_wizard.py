"""THI in the recommendation wizard: the tinnitus answer recommends it, no other line (#345)."""

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

    def test_no_result_links_thi_on_a_line_of_its_own(self):
        # #345: the tinnitus answer recommends THI, so the #216 line under every result is gone.
        thi = reverse("screening", args=[self.by_code["thi"].pk])
        for concern in ("life_impact", "listening", "hearing_aid", "unsure"):
            for norm_basis in (False, True):
                with self.subTest(concern=concern, norm_basis=norm_basis):
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
                    main = self.wizard(concern=concern).content.decode()
                    self.assertIn("推薦您做這一份", main)
                    self.assertNotIn("如果您有耳鳴", main)
                    # THI is only in the 看其他問卷 list.
                    self.assertEqual(main.count(f'href="{thi}"'), 1)
                    details = main[main.index("<details") : main.index("</details>")]
                    self.assertIn(f'href="{thi}"', details)

    def test_the_tinnitus_answer_never_asks_the_age(self):
        self.login_age(None)
        self.assertEqual(step_bar(self.wizard()), (1, 3))
        page = self.wizard(concern="tinnitus")
        self.assertEqual(step_bar(page), (2, 2))
        self.assertEqual(page.context["recommended"], self.by_code["thi"])
