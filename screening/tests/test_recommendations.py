"""Age and purpose recommendations (#80)."""

from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import Question, Questionnaire
from screening.tests.helpers import consented_user


class RecommendationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hhie = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        Question.objects.create(
            questionnaire=cls.hhie, question_number=1, question_text="假題目", category="emotional"
        )
        cls.ioi = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        call_command("seed_questionnaires", stdout=StringIO())
        call_command("seed_questionnaires", stdout=StringIO())
        cls.hhia = Questionnaire.objects.get(code="hhia-s")
        cls.ssq = Questionnaire.objects.get(code="ssq12-tw")

    def login_age(self, age):
        user = consented_user(
            username=f"age_{age}", birth_year=None if age is None else date.today().year - age
        )
        self.client.force_login(user)
        return user

    def test_known_birth_year_recommends_without_asking_again(self):
        for age, code in (
            (18, "hhia-s"),
            (30, "hhia-s"),
            (64, "hhia-s"),
            (66, "hhie-s"),
            (80, "hhie-s"),
        ):
            with self.subTest(age=age):
                self.login_age(age)
                page = self.client.get(reverse("questionnaire_list"))
                self.assertEqual(page.context["recommended"].code, code)
                self.assertNotContains(page, 'name="age_group"')
                self.assertNotContains(page, "第一次使用，請從 HHIE-S 開始")
                override = self.client.get(reverse("questionnaire_list"), {"age_group": "older"})
                self.assertEqual(override.context["recommended"].code, code)

    def test_missing_year_and_boundary_year_ask_only_the_actual_interval(self):
        for age in (None, 65):
            with self.subTest(age=age):
                self.login_age(age)
                page = self.client.get(reverse("questionnaire_list"))
                self.assertIsNone(page.context["recommended"])
                self.assertContains(page, 'name="age_group"')
                for group, code in (("adult", "hhia-s"), ("older", "hhie-s")):
                    page = self.client.get(reverse("questionnaire_list"), {"age_group": group})
                    self.assertEqual(page.context["recommended"].code, code)
                    self.assertNotContains(page, 'name="age_group"')
                bad = self.client.get(reverse("questionnaire_list"), {"age_group": "anything"})
                self.assertIsNone(bad.context["recommended"])
                self.assertContains(bad, 'name="age_group"')

    def test_all_purposes_are_direct_links_even_without_confirmed_age(self):
        self.login_age(None)
        page = self.client.get(reverse("questionnaire_list"))
        for label, questionnaire in (
            ("了解助聽器的幫助", self.ioi),
            ("了解目前聆聽能力", self.ssq),
        ):
            self.assertContains(
                page, f'href="{reverse("screening", args=[questionnaire.pk])}">{label}</a>'
            )
        page = self.client.get(reverse("questionnaire_list"), {"age_group": "adult"})
        self.assertContains(
            page, f'href="{reverse("screening", args=[self.hhia.pk])}">了解聽力對生活的影響</a>'
        )
        self.assertContains(page, "聽力對生活的影響（HHIA-S）")
        self.assertContains(page, "助聽器使用成效（IOI-HA）")
        self.assertContains(page, "日常聆聽能力（SSQ12-TW）")
        self.assertContains(page, "自行選擇問卷")

    def test_nonrecommended_hhi_stays_available_and_unaided_result_offers_ssq(self):
        from screening.models import Answer, Submission

        user = self.login_age(30)
        page = self.client.get(reverse("screening", args=[self.hhie.pk]))
        self.assertContains(page, "適合 65 歲以上")
        self.assertContains(page, 'id="answer-form"')
        question = self.hhie.questions.get()
        for questionnaire in (self.hhie, self.hhia):
            question = questionnaire.questions.first()
            for wearing in (False, True):
                submission = Submission.objects.create(
                    user=user, questionnaire=questionnaire, wearing_hearing_aid=wearing
                )
                Answer.objects.create(submission=submission, question=question, score=0)
                page = self.client.get(reverse("result", args=[submission.pk]))
                self.assertContains(page, "看我的紀錄與趨勢")
                if not wearing:
                    self.assertContains(page, "不必兩份都填")
                    self.assertContains(page, reverse("screening", args=[self.ssq.pk]))
                else:
                    self.assertNotContains(page, "不必兩份都填")

    def test_anonymous_users_still_need_login(self):
        self.assertEqual(self.client.get(reverse("questionnaire_list")).status_code, 302)
