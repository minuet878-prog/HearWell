"""Age and purpose recommendations (#80) and the recommendation wizard (#152, #345)."""

import re
import uuid
from datetime import date, datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import (
    Answer,
    Audiogram,
    Consent,
    Question,
    Questionnaire,
    Submission,
    User,
)
from screening.scoring import RETEST_DUE_TEXT
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
                self.assertContains(page, "看我的紀錄")
                if not wearing:
                    self.assertContains(page, "不必兩份都填")
                    self.assertContains(page, reverse("screening", args=[self.ssq.pk]))
                else:
                    self.assertNotContains(page, "不必兩份都填")

    def test_anonymous_users_still_need_login(self):
        self.assertEqual(self.client.get(reverse("questionnaire_list")).status_code, 302)


class ConcernWizardTests(TestCase):
    """The recommendation wizard asking what the user most wants to know (#345, ADR 0028)."""

    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        cls.by_code = {q.code: q for q in Questionnaire.objects.defined()}

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

    def test_step_one_asks_what_the_user_most_wants_to_know(self):
        self.login_age(70)
        page = self.wizard()
        main = page.content.decode()
        fieldset = re.search(r"<fieldset>(.*?)</fieldset>", main, re.S).group(1)
        self.assertIn(
            '<legend class="font-bold text-xl/normal">您最想了解什麼？</legend>', fieldset
        )
        options = re.findall(
            r'<input type="radio" name="concern" value="([^"]+)"[^>]*>\s*([^<]+?)\s*</label>',
            fieldset,
        )
        self.assertEqual(
            options,
            [
                ("life_impact", "聽不清楚對生活、心情的影響"),
                ("tinnitus", "耳鳴的困擾"),
                ("listening", "吵雜地方、多人說話聽不懂"),
                ("hearing_aid", "助聽器戴得好不好"),
                ("unsure", "不確定"),
            ],
        )
        self.assertNotContains(page, "您現在有戴助聽器嗎？")
        self.assertNotContains(page, 'name="age_group"')

    def hhi_record(self, user, *, wearing, questionnaire="hhie-s", answered=10, when=None):
        # A complete record answers all 10 items with an HHI choice.
        submission = Submission.objects.create(
            user=user, questionnaire=self.by_code[questionnaire], wearing_hearing_aid=wearing
        )
        questions = self.by_code[questionnaire].questions.order_by("question_number")[:answered]
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=2) for question in questions
        )
        if when:
            Submission.objects.filter(pk=submission.pk).update(created_at=when)
        return submission

    def also_cards(self, page):
        # The 「也可以做」 cards as (href, text), in order; [] without that heading.
        main = page.content.decode()
        if "也可以做" not in main:
            return []
        also = main[main.index("也可以做") : main.index("看其他問卷")]
        return re.findall(r'<a class="link-card[^"]*" href="([^"]+)">(.*?)</a>', also, re.S)

    def start_url(self, code):
        return reverse("screening", args=[self.by_code[code].pk])

    def assert_recommends(self, page, code, why):
        recommended = self.by_code[code]
        self.assertEqual(page.context["recommended"], recommended)
        main = page.content.decode()
        self.assertIn('<h1 class="h3 mt-2">推薦您做這一份</h1>', main)
        self.assertIn(f"{recommended.definition.topic}<span", main)
        self.assertIn(f">{recommended}</span>", main)
        self.assertIn(f"<p><strong>為什麼推薦：</strong>{why}</p>", main)

    def test_life_impact_or_unsure_with_a_known_age_recommends_by_age_in_two_steps(self):
        # #339 acceptance 11.
        whys = {
            "life_impact": "這份問卷幫您了解聽力對日常生活和心情的影響。",
            "unsure": "不確定的話，先從這份開始，了解聽力對日常生活和心情的影響。",
        }
        for age, code in ((70, "hhie-s"), (66, "hhie-s"), (64, "hhia-s"), (40, "hhia-s")):
            for concern, why in whys.items():
                with self.subTest(age=age, concern=concern):
                    self.login_age(age)
                    page = self.wizard(concern=concern)
                    self.assertContains(page, "第 2 步／共 2 步")
                    self.assertEqual(step_bar(page), (2, 2))
                    self.assert_recommends(page, code, why)
                    self.assertContains(page, f'href="{self.start_url(code)}">開始作答</a>')
                    self.assertNotContains(page, "也可以做")

    def test_tinnitus_and_listening_recommend_thi_and_ssq12_alone(self):
        # #339 acceptance 12.
        for concern, code, why in (
            ("tinnitus", "thi", "這份問卷幫您了解耳鳴對生活和情緒的影響。"),
            ("listening", "ssq12-tw", "這份問卷問您在吵雜環境、多人說話時聽得懂多少。"),
        ):
            for age in (70, None):
                with self.subTest(concern=concern, age=age):
                    self.login_age(age)
                    page = self.wizard(concern=concern)
                    self.assertEqual(step_bar(page), (2, 2))
                    self.assert_recommends(page, code, why)
                    self.assertContains(page, f'href="{self.start_url(code)}">開始作答</a>')
                    self.assertNotContains(page, "也可以做")
                    self.assertNotContains(page, "如果您有耳鳴")

    def test_hearing_aid_without_an_unaided_record_catches_one_up_first(self):
        # #339 acceptance 13: the life-impact questionnaire by the usual pick, started on 沒戴.
        for age, code in ((70, "hhie-s"), (40, "hhia-s")):
            with self.subTest(age=age):
                self.login_age(age)
                page = self.wizard(concern="hearing_aid")
                self.assertEqual(step_bar(page), (2, 2))
                self.assert_recommends(
                    page,
                    code,
                    "您有戴助聽器，但還沒有沒戴助聽器時的紀錄。"
                    "先了解沒戴助聽器時的情況，之後做助聽器成效問卷才能比較。",
                )
                self.assertContains(
                    page, f'href="{self.start_url(code)}?preselect=unaided">開始作答</a>'
                )
                self.assertEqual(
                    [href for href, _ in self.also_cards(page)],
                    [self.start_url("ioi-ha"), self.start_url("sadl")],
                )

    def test_hearing_aid_with_an_unaided_record_recommends_ioi_ha(self):
        # #339 acceptance 14.
        user = self.login_age(70)
        self.hhi_record(user, wearing=False)
        page = self.wizard(concern="hearing_aid")
        self.assert_recommends(
            page,
            "ioi-ha",
            "您有戴助聽器，也有沒戴助聽器時的紀錄。這份問卷了解助聽器對您的幫助，"
            "並和沒戴時困擾程度相近的一般使用者比較。",
        )
        self.assertContains(page, f'href="{self.start_url("ioi-ha")}">開始作答</a>')
        cards = self.also_cards(page)
        self.assertEqual(
            [href for href, _ in cards], [self.start_url("hhie-s"), self.start_url("sadl")]
        )
        self.assertIn("戴著助聽器再做一次「聽力對生活的影響」（HHIE-S）", cards[0][1])
        self.assertIn("和沒戴時的結果比較，看助聽器幫了多少。", cards[0][1])
        self.assertNotIn(self.by_code["hhie-s"].definition.audience, cards[0][1])

    def test_the_aided_retake_is_the_latest_life_impact_questionnaire(self):
        # An HHIA-S answered unaided at 64 stays the one to answer again worn past 65 (ADR 0028).
        user = self.login_age(70)
        self.hhi_record(user, wearing=False, questionnaire="hhia-s")
        cards = self.also_cards(self.wizard(concern="hearing_aid"))
        self.assertEqual(cards[0][0], self.start_url("hhia-s"))
        self.assertIn("戴著助聽器再做一次「聽力對生活的影響」（HHIA-S）", cards[0][1])

    def test_without_a_birth_year_only_a_life_impact_result_asks_the_age(self):
        # #339 acceptance 15.
        self.login_age(None)
        page = self.wizard()
        self.assertContains(page, "第 1 步／共 3 步")
        self.assertEqual(step_bar(page), (1, 3))
        page = self.wizard(concern="tinnitus")
        self.assertContains(page, "第 2 步／共 2 步")
        self.assertEqual(page.context["recommended"], self.by_code["thi"])
        for concern in ("life_impact", "unsure", "hearing_aid"):
            with self.subTest(concern=concern):
                page = self.wizard(concern=concern)
                self.assertContains(page, "第 2 步／共 3 步")
                self.assertEqual(step_bar(page), (2, 3))
                self.assertContains(
                    page, '<legend class="font-bold text-xl/normal">您目前的實際年齡？</legend>'
                )
                self.assertContains(page, f'<input type="hidden" name="concern" value="{concern}">')
                self.assertNotIn("recommended", page.context)
        for age_group, code in (("older", "hhie-s"), ("adult", "hhia-s")):
            with self.subTest(age_group=age_group):
                page = self.wizard(concern="life_impact", age_group=age_group)
                self.assertContains(page, "第 3 步／共 3 步")
                self.assertEqual(step_bar(page), (3, 3))
                self.assertEqual(page.context["recommended"], self.by_code[code])

    def test_turning_65_this_year_asks_the_age(self):
        # #339 acceptance 16: the birth year cannot tell 64 from 65.
        self.login_age(65)
        self.assertEqual(step_bar(self.wizard()), (1, 3))
        page = self.wizard(concern="unsure")
        self.assertEqual(step_bar(page), (2, 3))
        self.assertContains(page, 'name="age_group"')

    def test_a_life_impact_record_is_recommended_again_without_asking_the_age(self):
        # #339 acceptance 17: the latest life-impact record, not the age, picks it.
        user = self.login_age(65)
        self.hhi_record(user, wearing=False, questionnaire="hhia-s")
        page = self.wizard(wizard="1")
        self.assertEqual(step_bar(page), (1, 2))
        page = self.wizard(concern="life_impact")
        self.assertEqual(step_bar(page), (2, 2))
        self.assertNotContains(page, 'name="age_group"')
        self.assertEqual(page.context["recommended"], self.by_code["hhia-s"])

    def test_the_latest_life_impact_record_wins_over_the_age(self):
        for older, newer in (("hhia-s", "hhie-s"), ("hhie-s", "hhia-s")):
            with self.subTest(newer=newer):
                user = self.login_age(40)
                self.hhi_record(user, wearing=True, questionnaire=older, when=date(2026, 1, 1))
                self.hhi_record(user, wearing=True, questionnaire=newer, when=date(2026, 3, 1))
                # Not a life-impact record (GLOSSARY): a later THI changes nothing.
                Submission.objects.create(user=user, questionnaire=self.by_code["thi"])
                page = self.wizard(concern="unsure")
                self.assertEqual(page.context["recommended"], self.by_code[newer])

    def test_nothing_chosen_stays_on_the_step_with_the_error(self):
        # #339 acceptance 18; what the server shows for an empty or tampered answer.
        self.login_age(None)
        for params, step, name, error in (
            ({"concern": ""}, (1, 3), "concern", "請選擇您最想了解的事"),
            (
                {"concern": "life_impact", "age_group": ""},
                (2, 3),
                "age_group",
                "請選擇您的年齡區間",
            ),
        ):
            with self.subTest(params=params):
                page = self.wizard(**params)
                self.assertEqual(step_bar(page), step)
                self.assertNotIn("recommended", page.context)
                self.assertContains(
                    page,
                    f'<div id="id_{name}_error">\n    \n    '
                    f'<p class="text-danger field-error mb-0">{error}</p>',
                )
                self.assertContains(page, 'aria-invalid="true"')
        page = self.wizard(concern="anything")
        self.assertEqual(step_bar(page), (1, 3))
        self.assertContains(page, 'id="id_concern_error"')

    def assert_catalog(self, html):
        # The whole questionnaire list, every defined questionnaire once.
        self.assertEqual(html.count("questionnaire-card"), len(self.by_code))
        for questionnaire in self.by_code.values():
            self.assertIn(f'href="{reverse("screening", args=[questionnaire.pk])}"', html)

    def test_every_step_has_back_and_choose_yourself(self):
        # #339 acceptance 19.
        wizard = reverse("questionnaire_list")
        choose = f'href="{wizard}?choose=self">自己選問卷</a>'
        for age, params, back in (
            (None, {}, reverse("index")),
            (70, {}, reverse("index")),
            (None, {"concern": "unsure"}, f"{wizard}?chosen=unsure"),
        ):
            with self.subTest(age=age, params=params):
                self.login_age(age)
                page = self.wizard(**params)
                self.assertContains(page, f'href="{back}">上一步</a>')
                self.assertContains(page, choose)
        for age, params, back in (
            (None, {"concern": "unsure", "age_group": "older"}, f"{wizard}?concern=unsure"),
            (70, {"concern": "tinnitus"}, f"{wizard}?chosen=tinnitus"),
            (70, {"concern": "hearing_aid"}, f"{wizard}?chosen=hearing_aid"),
        ):
            with self.subTest(age=age, params=params):
                self.login_age(age)
                main = self.wizard(**params).content.decode()
                self.assertIn(f'href="{back}">上一步</a>', main)
                self.assertIn(choose, main)
                details = main[main.index("<details") : main.index("</details>")]
                self.assertIn("<summary>看其他問卷</summary>", details)
                self.assert_catalog(details)

    def test_back_to_step_one_keeps_the_answer_chosen(self):
        self.login_age(None)
        page = self.wizard(chosen="unsure")
        self.assertEqual(step_bar(page), (1, 3))
        radios = r'<input type="radio" name="concern" value="([^"]+)"[^>]*checked'
        checked = re.findall(radios, page.content.decode())
        self.assertEqual(checked, ["unsure"])
        self.assertNotContains(page, 'id="id_concern_error"')

    def test_after_catching_up_the_hearing_aid_answer_recommends_ioi_ha(self):
        # #154 acceptance 4: start from the catch-up link, send the form as a browser without
        # JavaScript does (the preselected 沒戴 kept, first choice on every question), ask again.
        user = self.login_age(66)
        page = self.wizard(concern="hearing_aid")
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
        page = self.wizard(concern="hearing_aid")
        self.assertEqual(page.context["recommended"], self.by_code["ioi-ha"])
        self.assertEqual(page.context["reason"], "has_norm_basis")

    def test_only_records_that_set_the_ioi_ha_norm_group_count(self):
        # Same records as the IOI-HA norm basis: the user's own, unaided, complete HHI.
        other = consented_user(username="someone_else", birth_year=date.today().year - 70)
        self.hhi_record(other, wearing=False)
        user = self.login_age(70)
        self.hhi_record(user, wearing=True)
        self.hhi_record(user, wearing=False, answered=9)
        page = self.wizard(concern="hearing_aid")
        self.assertEqual(page.context["recommended"], self.by_code["hhie-s"])
        self.assertEqual(page.context["reason"], "needs_norm_basis")
        # And the other way round: this user's records do not change the other's.
        self.client.force_login(other)
        page = self.wizard(concern="hearing_aid")
        self.assertEqual(page.context["recommended"], self.by_code["ioi-ha"])

    def test_an_unaided_ssq12_record_is_no_norm_basis(self):
        # IOI-HA's norm group comes from HHIA-S or HHIE-S only, so SSQ12 does not count.
        user = self.login_age(70)
        ssq12 = self.by_code["ssq12-tw"]
        submission = Submission.objects.create(
            user=user, questionnaire=ssq12, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=5)
            for question in ssq12.questions.all()
        )
        page = self.wizard(concern="hearing_aid")
        self.assertEqual(page.context["recommended"], self.by_code["hhie-s"])
        self.assertEqual(page.context["reason"], "needs_norm_basis")

    def test_choose_yourself_lists_every_questionnaire(self):
        self.login_age(None)
        page = self.wizard(choose="self")
        self.assertContains(page, '<h1 class="h3 mt-2">自行選擇問卷</h1>', html=False)
        self.assertNotContains(page, 'name="concern"')
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
        self.assertNotContains(
            self.wizard(**{"from": "consent", "concern": "life_impact"}), greeting
        )

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
        # #339 acceptance 20.
        self.login_age(None)
        page = self.client.get(reverse("questionnaire_list"))
        page = self.submit_choice(page, "life_impact")
        self.assertContains(page, "第 2 步／共 3 步")
        page = self.submit_choice(page, "adult")
        self.assertContains(page, "第 3 步／共 3 步")
        start = re.search(r'href="([^"]+)">開始作答</a>', page.content.decode()).group(1)
        answer = self.client.get(start)
        self.assertEqual(answer.context["questionnaire"], self.by_code["hhia-s"])
        self.assertContains(answer, 'id="answer-form"')


class ReturningCatalogueTests(TestCase):
    """The screening tab's questionnaire catalogue for returning users (#346, ADR 0028)."""

    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        cls.ordered = sorted(
            Questionnaire.objects.defined(),
            key=lambda q: (q.definition.list_rank, q.pk),
        )
        cls.by_code = {q.code: q for q in cls.ordered}

    def login(self, *codes, birth_year=1956):
        # A user with one record of each of `codes`; none makes a new user.
        user = consented_user(username=f"catalogue_{uuid.uuid4().hex[:8]}", birth_year=birth_year)
        for code in codes:
            self.record(user, code)
        self.client.force_login(user)
        return user

    def record(self, user, code, when=None):
        submission = Submission.objects.create(user=user, questionnaire=self.by_code[code])
        if when:
            Submission.objects.filter(pk=submission.pk).update(created_at=when)
        return submission

    def catalogue(self, **params):
        return self.client.get(reverse("questionnaire_list"), params)

    def cards(self, page):
        # Each catalogue card as (href, text), in order.
        return re.findall(
            r'<a class="link-card mt-4 questionnaire-card" href="([^"]+)">(.*?)</a>',
            page.content.decode(),
            re.S,
        )

    def test_a_returning_user_sees_the_catalogue_not_the_wizard(self):
        # #339 acceptance 1.
        self.login("thi")
        page = self.catalogue()
        self.assertNotContains(page, 'name="concern"')
        self.assertNotContains(page, "step-progress")
        self.assertEqual(
            [href for href, _ in self.cards(page)],
            [reverse("screening", args=[q.pk]) for q in self.ordered],
        )
        self.assertEqual(len(self.cards(page)), 6)
        self.assertContains(page, f'<a href="{reverse("questionnaire_list")}" aria-current="page">')

    def test_answered_questionnaires_show_the_taipei_date_of_their_latest_record(self):
        # #339 acceptance 2: several records over several days, the latest just after midnight
        # in Taipei (still the day before in UTC) or just before it.
        taipei = ZoneInfo("Asia/Taipei")
        user = self.login()
        for code, when in (
            ("hhie-s", datetime(2026, 2, 1, 10, 0, tzinfo=taipei)),
            ("hhie-s", datetime(2026, 3, 2, 0, 10, tzinfo=taipei)),
            ("hhie-s", datetime(2026, 2, 20, 9, 0, tzinfo=taipei)),
            ("thi", datetime(2026, 1, 5, 8, 0, tzinfo=taipei)),
            ("thi", datetime(2026, 2, 10, 23, 50, tzinfo=taipei)),
        ):
            self.record(user, code, when)
        cards = dict(self.cards(self.catalogue()))
        for questionnaire in self.ordered:
            text = cards[reverse("screening", args=[questionnaire.pk])]
            with self.subTest(code=questionnaire.code):
                tags = re.findall(r'<span class="card-tag">([^<]*)</span>', text)
                last = {"hhie-s": ["上次 2026/03/02"], "thi": ["上次 2026/02/10"]}
                self.assertEqual(tags[2:], last.get(questionnaire.code, []))
                self.assertEqual(tags[0], f"{questionnaire.questions.count()} 題")

    def test_the_dates_come_in_one_query_however_many_cards_have_one(self):
        counts = []
        for codes in (("thi",), ("thi", "hhie-s", "ssq12-tw", "sadl")):
            self.login(*codes)
            with CaptureQueriesContext(connection) as queries:
                self.catalogue()
            counts.append(len(queries))
        self.assertEqual(counts[0], counts[1])

    def test_help_me_choose_opens_step_one_whose_back_returns_to_the_catalogue(self):
        # #339 acceptance 8.
        self.login("hhie-s")
        catalogue = reverse("questionnaire_list")
        main = self.catalogue().content.decode()
        link = f'<a href="{catalogue}?wizard=1">回答幾個問題，幫您挑</a>'
        self.assertIn(f'<p class="mt-6">不確定做哪一份？{link}</p>', main)
        # The last line of the page, under every card.
        self.assertGreater(main.index(link), main.rindex("questionnaire-card"))
        page = self.catalogue(wizard="1")
        self.assertContains(
            page, '<legend class="font-bold text-xl/normal">您最想了解什麼？</legend>'
        )
        self.assertContains(page, f'href="{catalogue}">上一步</a>')
        # Back from step 2 to step 1, whose back still returns to the catalogue.
        page = self.catalogue(chosen="tinnitus")
        self.assertContains(page, 'name="concern"')
        self.assertContains(page, f'href="{catalogue}">上一步</a>')
        self.assertNotContains(self.catalogue(), 'name="concern"')

    def test_a_new_user_still_gets_the_wizard_whose_back_goes_home(self):
        # #339 acceptance 9: no questionnaire record, an audiogram or not.
        user = self.login()
        for audiogram in (False, True):
            if audiogram:
                Audiogram.objects.create(user=user, tested_on=date(2026, 10, 1))
            with self.subTest(audiogram=audiogram):
                page = self.catalogue()
                self.assertContains(
                    page, '<legend class="font-bold text-xl/normal">您最想了解什麼？</legend>'
                )
                self.assertContains(page, f'href="{reverse("index")}">上一步</a>')
                self.assertEqual(self.cards(page), [])

    def test_a_new_users_choose_yourself_has_no_dates_and_no_help_me_choose(self):
        self.login()
        page = self.catalogue(choose="self")
        self.assertEqual(len(self.cards(page)), 6)
        self.assertNotContains(page, "上次")
        self.assertNotContains(page, "幫您挑")

    def test_a_returning_users_choose_yourself_is_the_same_catalogue(self):
        # The wizard's 自己選問卷 link, followed by a returning user who came in by 「幫您挑」.
        self.login("thi")
        page = self.catalogue(choose="self")
        self.assertContains(page, "上次 ")
        self.assertContains(page, "幫您挑")
        self.assertNotContains(page, 'name="concern"')


class RecommendedQuestionnaireTests(TestCase):
    """The 推薦問卷 on top of the returning user's catalogue (#347, ADR 0028)."""

    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        cls.by_code = {q.code: q for q in Questionnaire.objects.defined()}

    def login(self, age=70):
        # age None: no birth year.
        user = consented_user(
            username=f"recommended_{uuid.uuid4().hex[:8]}",
            birth_year=None if age is None else date.today().year - age,
        )
        self.client.force_login(user)
        return user

    def record(self, user, code, *, wearing=None, days_ago=1):
        # A complete record: every item answered with its lowest choice, an HHI choice on HHI.
        questionnaire = self.by_code[code]
        submission = Submission.objects.create(
            user=user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=0)
            for question in questionnaire.questions.all()
        )
        Submission.objects.filter(pk=submission.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        return submission

    def recommended(self, page=None):
        # The 推薦您做這一份 block, or None without one.
        page = page or self.client.get(reverse("questionnaire_list"))
        block = re.search(
            r'<section aria-labelledby="catalogue-recommended"[^>]*>(.*?)</section>',
            page.content.decode(),
            re.S,
        )
        return block and block.group(1)

    def starts(self, block):
        # The block's 開始作答 links, in order.
        return re.findall(r'<a class="btn btn-primary btn-lg" href="([^"]+)">開始作答', block)

    def start_url(self, code):
        return reverse("screening", args=[self.by_code[code].pk])

    def test_a_due_retest_recommends_the_last_life_impact_questionnaire_again(self):
        # #339 acceptance 3: HHIA-S over six months ago, 65 since.
        user = self.login(age=70)
        self.record(user, "hhia-s", wearing=False, days_ago=200)
        page = self.client.get(reverse("questionnaire_list"))
        block = self.recommended(page)
        self.assertIn('<h2 id="catalogue-recommended" class="h4">推薦您做這一份</h2>', block)
        self.assertEqual(self.starts(block), [self.start_url("hhia-s")])
        self.assertIn(f"<strong>為什麼推薦：</strong>{RETEST_DUE_TEXT}</p>", block)
        # Still in the catalogue below, all six cards.
        main = page.content.decode()
        cards = re.findall(r'<a class="link-card mt-4 questionnaire-card" href="([^"]+)">', main)
        self.assertEqual(len(cards), 6)
        self.assertIn(self.start_url("hhia-s"), cards)

    def test_without_a_life_impact_record_one_is_recommended_by_age(self):
        # #339 acceptance 4, and its 40-year-old counterpart.
        for age, code in ((70, "hhie-s"), (40, "hhia-s")):
            with self.subTest(age=age):
                user = self.login(age=age)
                self.record(user, "thi")
                block = self.recommended()
                self.assertEqual(self.starts(block), [self.start_url(code)])
                self.assertIn(
                    "<strong>為什麼推薦：</strong>您還沒做過聽力對生活影響的問卷，"
                    "做一次之後才有基礎可以比較。</p>",
                    block,
                )

    def test_without_a_life_impact_record_or_an_age_both_are_listed(self):
        # #339 acceptance 5: no birth year, or one that cannot tell 64 from 65.
        for age in (None, 65):
            with self.subTest(age=age):
                user = self.login(age=age)
                self.record(user, "thi")
                block = self.recommended()
                self.assertEqual(
                    self.starts(block), [self.start_url("hhie-s"), self.start_url("hhia-s")]
                )
                self.assertEqual(block.count("為什麼推薦："), 1)
                for code in ("hhie-s", "hhia-s"):
                    questionnaire = self.by_code[code]
                    item = block[block.index(f'id="recommended-{code}"') :]
                    item = item[: item.index("開始作答")]
                    self.assertIn(f"<p>{questionnaire.definition.audience}</p>", item)
                    # Two 開始作答 buttons, each named after its questionnaire for screen readers.
                    self.assertIn(
                        f'開始作答<span class="visually-hidden">：{questionnaire}</span></a>', block
                    )

    def test_aided_and_unaided_records_without_ioi_ha_recommend_ioi_ha(self):
        # #339 acceptance 6: an unaided HHIE-S within six months, and a record answered wearing
        # hearing aids: SADL, always saved as worn, or a life-impact one answered worn.
        for aided in ("sadl", "hhia-s"):
            with self.subTest(aided=aided):
                user = self.login()
                self.record(user, "hhie-s", wearing=False, days_ago=30)
                self.record(user, aided, wearing=True)
                block = self.recommended()
                self.assertEqual(self.starts(block), [self.start_url("ioi-ha")])
                self.assertIn(
                    "<strong>為什麼推薦：</strong>您有戴著助聽器的紀錄，也有沒戴時的紀錄，"
                    "可以了解助聽器的成效跟一般使用者比起來怎樣。</p>",
                    block,
                )

    def test_no_rule_holding_leaves_no_recommendation(self):
        # #339 acceptance 7, and rule 3 one condition short each.
        cases = {
            "recent unaided only": (("hhie-s", False),),
            "worn without a norm basis": (("hhie-s", True),),
            "ioi-ha already answered": (("hhie-s", False), ("sadl", True), ("ioi-ha", None)),
        }
        for case, records in cases.items():
            with self.subTest(case):
                user = self.login()
                for code, wearing in records:
                    self.record(user, code, wearing=wearing, days_ago=30)
                page = self.client.get(reverse("questionnaire_list"))
                self.assertIsNone(self.recommended(page))
                self.assertNotContains(page, "推薦您做這一份")
                self.assertEqual(page.content.decode().count("questionnaire-card"), 6)

    def test_a_due_retest_comes_before_ioi_ha(self):
        # Rules 1 and 3 both hold: rule 1 wins.
        user = self.login()
        self.record(user, "hhie-s", wearing=False, days_ago=200)
        self.record(user, "sadl", wearing=True, days_ago=10)
        block = self.recommended()
        self.assertEqual(self.starts(block), [self.start_url("hhie-s")])
        self.assertIn(RETEST_DUE_TEXT, block)

    def test_the_recommendation_queries_do_not_grow_with_the_records(self):
        # Rule 3, the one asking the most: two records, then many of every questionnaire.
        counts = []
        for many in (False, True):
            user = self.login()
            self.record(user, "hhie-s", wearing=False, days_ago=30)
            self.record(user, "sadl", wearing=True)
            if many:
                for code in ("hhie-s", "hhia-s", "sadl", "ssq12-tw", "thi"):
                    for days_ago in (2, 3):
                        self.record(user, code, wearing=code != "thi", days_ago=days_ago)
            with CaptureQueriesContext(connection) as queries:
                block = self.recommended()
            self.assertEqual(self.starts(block), [self.start_url("ioi-ha")])
            counts.append(len(queries))
        self.assertEqual(counts[0], counts[1])

    def test_a_new_users_catalogue_recommends_nothing(self):
        self.login()
        self.assertIsNone(
            self.recommended(self.client.get(reverse("questionnaire_list"), {"choose": "self"}))
        )
