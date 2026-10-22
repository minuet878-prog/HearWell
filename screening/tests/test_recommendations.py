"""Age and purpose recommendations (#80) and the questionnaire wizard (#152)."""

import re
import uuid
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.forms import WearingNowForm
from screening.models import Answer, Consent, Question, Questionnaire, Submission, User
from screening.tests.helpers import consented_user, step_bar


class RecommendationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hhie = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        Question.objects.create(
            questionnaire=cls.hhie, question_number=1, question_text="假題目", category="emotional"
        )
        cls.ioi = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        call_command("seed_questionnaires", stdout=StringIO())
        cls.hhia = Questionnaire.objects.get(code="hhia-s")
        cls.ssq = Questionnaire.objects.get(code="ssq12-tw")

    def login_age(self, age):
        user = consented_user(
            username=f"age_{age}", birth_year=None if age is None else date.today().year - age
        )
        self.client.force_login(user)
        return user

    def test_nonrecommended_hhi_stays_available_and_unaided_result_offers_ssq(self):

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


class WizardTests(TestCase):
    """The questionnaire wizard: age, hearing aid, one recommendation (#152)."""

    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        cls.by_code = {q.code: q for q in Questionnaire.objects.all()}

    def login_age(self, age):
        # age None: no birth year. Subtests log in more than one user per test.
        user = consented_user(
            username=f"wizard_{age}_{uuid.uuid4().hex[:8]}",
            birth_year=None if age is None else date.today().year - age,
        )
        self.client.force_login(user)
        return user

    def wizard(self, **params):
        return self.client.get(reverse("questionnaire_list"), params)

    def test_without_birth_year_step_one_of_three_asks_age(self):
        self.login_age(None)
        page = self.wizard()
        self.assertContains(page, "第 1 步／共 3 步")
        self.assertEqual(step_bar(page), (1, 3))
        self.assertContains(page, 'name="age_group"')
        self.assertNotContains(page, 'name="hearing_aid"')

    def test_known_birth_year_skips_age_so_hearing_aid_is_step_one_of_two(self):
        for age in (18, 64, 66, 80):
            with self.subTest(age=age):
                self.login_age(age)
                page = self.wizard()
                self.assertContains(page, "第 1 步／共 2 步")
                self.assertEqual(step_bar(page), (1, 2))
                self.assertContains(page, 'name="hearing_aid"')
                self.assertNotContains(page, 'name="age_group"')

    def test_birth_year_exactly_65_still_asks_age(self):
        self.login_age(65)
        page = self.wizard()
        self.assertContains(page, "第 1 步／共 3 步")
        self.assertContains(page, 'name="age_group"')

    def test_answered_age_moves_to_hearing_aid_as_step_two_of_three(self):
        self.login_age(None)
        page = self.wizard(age_group="older")
        self.assertContains(page, "第 2 步／共 3 步")
        self.assertEqual(step_bar(page), (2, 3))
        self.assertContains(page, 'name="hearing_aid"')
        self.assertContains(page, '<input type="hidden" name="age_group" value="older">')
        bad = self.wizard(age_group="anything")
        self.assertContains(bad, "第 1 步／共 3 步")
        self.assertContains(bad, 'id="id_age_group_error"')

    def hhi_record(self, user, *, wearing, questionnaire="hhie-s", answered=10):
        # A complete record answers all 10 items with an HHI choice.
        submission = Submission.objects.create(
            user=user, questionnaire=self.by_code[questionnaire], wearing_hearing_aid=wearing
        )
        questions = self.by_code[questionnaire].questions.order_by("question_number")[:answered]
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=2) for question in questions
        )
        return submission

    def recommendation(self, age, hearing_aid):
        # age is a birth-year age, or "adult" / "older" answered in the wizard.
        asked = age in ("adult", "older")
        user = self.login_age(None if asked else age)
        params = {"hearing_aid": hearing_aid}
        if asked:
            params["age_group"] = age
        return user, params

    def test_unaided_recommends_life_impact_questionnaire_by_age(self):
        for age, code in (("older", "hhie-s"), (66, "hhie-s"), ("adult", "hhia-s"), (30, "hhia-s")):
            with self.subTest(age=age):
                _, params = self.recommendation(age, "no")
                page = self.wizard(**params)
                recommended = self.by_code[code]
                self.assertEqual(page.context["recommended"], recommended)
                main = page.content.decode()
                self.assertIn("推薦您做這一份", main)
                self.assertIn(f"{recommended.definition.topic}<span", main)
                self.assertIn(f">{recommended}</span>", main)
                self.assertIn(">10 題</span>", main)
                self.assertIn(f">約 {recommended.definition.minutes} 分鐘</span>", main)
                # The same sentence for both ages, word for word as reviewed.
                self.assertIn(
                    "<p><strong>為什麼推薦：</strong>"
                    "您沒有戴助聽器，這份問卷供您了解聽力對日常生活和心情的影響。</p>",
                    main,
                )
                self.assertIn(
                    f'href="{reverse("screening", args=[recommended.pk])}">開始作答</a>', main
                )
                self.assertNotIn("也可以做", main)

    def test_aided_without_unaided_record_recommends_life_impact_and_says_why(self):
        for age, code in (("older", "hhie-s"), (30, "hhia-s")):
            with self.subTest(age=age):
                _, params = self.recommendation(age, "yes")
                page = self.wizard(**params)
                self.assertEqual(page.context["recommended"], self.by_code[code])
                self.assertContains(
                    page,
                    "<p><strong>為什麼推薦：</strong>"
                    "您有戴助聽器，但還沒有沒戴助聽器時的紀錄。"
                    "先了解沒戴助聽器時的情況，之後做助聽器成效問卷才能比較。</p>",
                )
                self.assert_ssq12_also(page)

    def test_catching_up_an_unaided_record_opens_the_answer_page_preselected(self):
        # #154: only this branch marks the link; the other branches' links stay bare (see above).
        _, params = self.recommendation("older", "yes")
        start = reverse("screening", args=[self.by_code["hhie-s"].pk])
        self.assertContains(self.wizard(**params), f'href="{start}?preselect=unaided">開始作答</a>')

    def test_aided_with_unaided_record_recommends_ioi_ha(self):
        user, params = self.recommendation("older", "yes")
        self.hhi_record(user, wearing=False, questionnaire="hhia-s")
        page = self.wizard(**params)
        self.assertEqual(page.context["recommended"], self.by_code["ioi-ha"])
        self.assertContains(
            page,
            "<p><strong>為什麼推薦：</strong>"
            "您有戴助聽器且有沒戴的紀錄。這份問卷能作為助聽器功效的比較。</p>",
        )
        self.assertContains(
            page, f'href="{reverse("screening", args=[self.by_code["ioi-ha"].pk])}">開始作答</a>'
        )
        self.assert_ssq12_also(page)

    def test_after_catching_up_aided_recommends_ioi_ha(self):
        # #154 acceptance 4: start from the catch-up link, send the form as a browser without
        # JavaScript does (the preselected 沒戴 kept, first choice on every question), ask again.
        user = self.login_age(66)
        page = self.wizard(hearing_aid="yes")
        start = re.search(r'href="([^"]+)">開始作答</a>', page.content.decode()).group(1)
        html = self.client.get(start).content.decode()
        form = re.search(r'<form id="answer-form" action="([^"]+)".*?</form>', html, re.S)
        data = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', form[0]))
        radios = re.findall(r'<input type="radio" name="([^"]+)" value="([^"]*)"', form[0])
        for name, value in radios:
            data.setdefault(name, value)
        checked = re.search(r'name="wearing_hearing_aid" value="([^"]+)"[^>]*checked>', form[0])
        data["wearing_hearing_aid"] = checked.group(1)
        response = self.client.post(form.group(1), data)
        submission = Submission.objects.get(user=user)
        self.assertRedirects(response, reverse("result", args=[submission.id]))
        self.assertIs(submission.wearing_hearing_aid, False)
        page = self.wizard(hearing_aid="yes")
        self.assertEqual(page.context["recommended"], self.by_code["ioi-ha"])
        self.assertEqual(page.context["reason"], "has_norm_basis")

    def assert_ssq12_also(self, page):
        main = page.content.decode()
        also = main[main.index("也可以做") : main.index("看其他問卷")]
        ssq12 = self.by_code["ssq12-tw"]
        self.assertIn(f'href="{reverse("screening", args=[ssq12.pk])}"', also)
        self.assertEqual(also.count("questionnaire-card"), 1)

    def test_only_records_that_set_the_ioi_ha_norm_group_count(self):
        # Same records as the IOI-HA norm basis: the user's own, unaided, complete HHI.
        other = consented_user(username="someone_else")
        self.hhi_record(other, wearing=False)
        user, params = self.recommendation("older", "yes")
        self.hhi_record(user, wearing=True)
        self.hhi_record(user, wearing=False, answered=9)
        page = self.wizard(**params)
        self.assertEqual(page.context["recommended"], self.by_code["hhie-s"])
        self.assertEqual(page.context["reason"], "needs_norm_basis")
        # And the other way round: this user's records do not change the other's.
        self.client.force_login(other)
        page = self.wizard(age_group="older", hearing_aid="yes")
        self.assertEqual(page.context["recommended"], self.by_code["ioi-ha"])

    def test_an_unaided_ssq12_record_is_no_norm_basis(self):
        # IOI-HA's norm group comes from HHIA-S or HHIE-S only, so SSQ12 does not count.
        user, params = self.recommendation("older", "yes")
        ssq12 = self.by_code["ssq12-tw"]
        submission = Submission.objects.create(
            user=user, questionnaire=ssq12, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=5)
            for question in ssq12.questions.all()
        )
        page = self.wizard(**params)
        self.assertEqual(page.context["recommended"], self.by_code["hhie-s"])
        self.assertEqual(page.context["reason"], "needs_norm_basis")

    def test_hearing_aid_answer_comes_out_as_true_or_false(self):
        # The address keeps no / yes; the view gets the answer itself.
        for value, wearing in (("no", False), ("yes", True)):
            with self.subTest(value=value):
                form = WearingNowForm({"hearing_aid": value})
                self.assertTrue(form.is_valid())
                self.assertIs(form.cleaned_data["hearing_aid"], wearing)

    def test_invalid_hearing_aid_answer_stays_on_that_step(self):
        self.login_age(66)
        page = self.wizard(hearing_aid="maybe")
        self.assertContains(page, "第 1 步／共 2 步")
        self.assertContains(page, 'id="id_hearing_aid_error"')
        self.assertNotIn("recommended", page.context)

    def assert_catalog(self, html):
        # The whole questionnaire list, every defined questionnaire once.
        self.assertEqual(html.count("questionnaire-card"), len(self.by_code))
        for questionnaire in self.by_code.values():
            self.assertIn(f'href="{reverse("screening", args=[questionnaire.pk])}"', html)

    def test_every_step_has_back_and_choose_yourself(self):
        wizard = reverse("questionnaire_list")
        choose = f'href="{wizard}?choose=self">自己選問卷</a>'
        for age, params, back in (
            (None, {}, reverse("index")),
            (None, {"age_group": "older"}, wizard),
            (66, {}, reverse("index")),
        ):
            with self.subTest(age=age, params=params):
                self.login_age(age)
                page = self.wizard(**params)
                self.assertContains(page, f'href="{back}">上一步</a>')
                self.assertContains(page, choose)
        for age, params, back in (
            (None, {"age_group": "older", "hearing_aid": "no"}, f"{wizard}?age_group=older"),
            (66, {"hearing_aid": "yes"}, wizard),
        ):
            with self.subTest(age=age, params=params):
                self.login_age(age)
                main = self.wizard(**params).content.decode()
                self.assertIn(f'href="{back}">上一步</a>', main)
                details = main[main.index("<details") : main.index("</details>")]
                self.assertIn("<summary>看其他問卷</summary>", details)
                self.assert_catalog(details)

    def test_choose_yourself_lists_every_questionnaire(self):
        self.login_age(None)
        page = self.wizard(choose="self")
        self.assertContains(page, '<h1 class="h3 mt-2">自行選擇問卷</h1>', html=False)
        self.assertNotContains(page, 'name="age_group"')
        self.assert_catalog(page.content.decode())

    def test_greeting_only_on_the_first_screen_after_consent(self):
        # The sentence ends with a full-width exclamation mark, kept out of the source for Ruff.
        greeting = "帳號建好了\N{FULLWIDTH EXCLAMATION MARK}接下來幫您找適合的問卷"
        for age in (None, 66):
            with self.subTest(age=age):
                self.login_age(age)
                self.assertContains(self.wizard(**{"from": "consent"}), greeting)
                self.assertNotContains(self.wizard(), greeting)
        self.login_age(None)
        self.assertNotContains(self.wizard(**{"from": "consent", "age_group": "older"}), greeting)

    def register_and_agree(self, next_url):
        # A brand-new account, then 「我同意，開始篩檢」 on the consent page that follows.
        password = "Xk9#mPq2vLw"
        self.client.post(
            reverse("register"),
            {
                "username": f"new_{uuid.uuid4().hex[:8]}",
                "email": "new@example.com",
                "password1": password,
                "password2": password,
                "next": next_url,
            },
        )
        return self.client.post(reverse("consent"), {"agree": "", "next": next_url})

    def test_agreeing_right_after_registering_marks_the_way_into_the_wizard(self):
        wizard = reverse("questionnaire_list")
        response = self.register_and_agree(wizard)
        self.assertRedirects(response, f"{wizard}?from=consent")
        self.assertContains(self.client.get(response.url), "帳號建好了")

    def test_an_older_account_agreeing_for_the_first_time_gets_no_greeting(self):
        # Made before the consent page existed (or asked again later): not a new account.
        user = User.objects.create_user(username="brand_new")
        self.client.force_login(user)
        wizard = reverse("questionnaire_list")
        response = self.client.post(reverse("consent"), {"agree": "", "next": wizard})
        self.assertRedirects(response, wizard)
        self.assertNotContains(self.client.get(response.url), "帳號建好了")

    def test_agreeing_keeps_the_query_string_of_next(self):
        choose = f"{reverse('questionnaire_list')}?choose=self"
        response = self.register_and_agree(choose)
        self.assertRedirects(response, f"{choose}&from=consent")
        self.assertContains(self.client.get(response.url), "自行選擇問卷")

    def test_a_new_account_with_an_outside_next_still_goes_home(self):
        for bad in ("https://evil.example.com/questionnaire_list", "//evil.example.com"):
            with self.subTest(next=bad):
                self.client.logout()
                self.assertRedirects(
                    self.register_and_agree(bad), reverse("index"), fetch_redirect_response=False
                )

    def test_the_greeting_comes_once_per_new_account(self):
        wizard = reverse("questionnaire_list")
        self.register_and_agree(wizard)
        # Already agreed: coming back through the consent page is no new account.
        response = self.client.get(reverse("consent"), {"next": wizard})
        self.assertRedirects(response, wizard)
        # Asked to agree again later (a new privacy notice) in the same session: still no greeting.
        Consent.objects.all().delete()
        response = self.client.post(reverse("consent"), {"agree": "", "next": wizard})
        self.assertRedirects(response, wizard)

    def submit_choice(self, page, value):
        # What a browser without JavaScript sends: the form's hidden fields plus one radio.
        html = page.content.decode()
        form = re.search(r'<form method="get" action="([^"]+)">(.*?)</form>', html, re.DOTALL)
        action, body = form.groups()
        data = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', body))
        name = re.search(rf'<input type="radio" name="([^"]+)" value="{value}"', body).group(1)
        return self.client.get(action, data | {name: value})

    def test_wizard_walks_to_the_answer_page_with_forms_and_links_only(self):
        self.login_age(None)
        page = self.client.get(reverse("questionnaire_list"))
        page = self.submit_choice(page, "adult")
        self.assertContains(page, "第 2 步／共 3 步")
        page = self.submit_choice(page, "no")
        self.assertContains(page, "第 3 步／共 3 步")
        start = re.search(r'href="([^"]+)">開始作答</a>', page.content.decode()).group(1)
        answer = self.client.get(start)
        self.assertEqual(answer.context["questionnaire"], self.by_code["hhia-s"])
        self.assertContains(answer, 'id="answer-form"')
