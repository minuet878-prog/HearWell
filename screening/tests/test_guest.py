"""A guest answers HHIE-S or HHIA-S and sees the result (ticket #495, spec #492): the wizard asks
only the age, the answer page scores without saving, and the guest result page draws the result
the browser keeps."""

import json
import re
import uuid
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening import models
from screening.models import Answer, Questionnaire, Submission
from screening.questionnaires import hhia_s, hhie_s, ioi_ha, sadl, ssq12_tw, thi
from screening.tests import test_pages
from screening.tests.helpers import consented_user

GUEST_SCORE = "/api/guest-scores/"
LIMIT = "剛才做了很多次，請過一小時再試。您的作答沒有不見。"
GUEST_LINE = "沒註冊時只計算、不儲存。"


class GuestTestCase(TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S, IOI-HA

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())  # HHIA-S, THI, SSQ12-TW, SADL
        cls.user = consented_user(username="guest_tests")
        cls.hhie_s = Questionnaire.objects.get(code=hhie_s.CODE)
        cls.hhia_s = Questionnaire.objects.get(code=hhia_s.CODE)

    def setUp(self):
        # The rate limit counts in the cache; each test starts and ends with none counted.
        cache.clear()
        self.addCleanup(cache.clear)

    def body(self, questionnaire, scores, wearing=False, just_finished=True):
        questions = questionnaire.questions.order_by("question_number")
        return {
            "questionnaire": questionnaire.pk,
            "wearing_hearing_aid": wearing,
            "answers": [
                {"question": question.pk, "score": score}
                for question, score in zip(questions, scores, strict=False)
            ],
            "just_finished": just_finished,
        }

    def guest_score(self, body, **extra):
        return self.client.post(
            GUEST_SCORE, json.dumps(body), content_type="application/json", **extra
        )

    def nav_labels(self, response):
        nav = test_pages.RedesignLayoutTests.NAV.findall(response.content.decode())
        self.assertEqual(len(nav), 1)
        return re.findall(r"<span[^>]*>([^<]+)</span>\s*</a>", nav[0])


class WizardTests(GuestTestCase):
    """#492 acceptance 2, 4: without an account the wizard asks the age alone."""

    def test_asks_only_the_age(self):
        response = self.client.get(reverse("questionnaire_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "您目前的實際年齡？")
        self.assertContains(response, 'name="age_group" value="adult"')
        self.assertContains(response, 'name="age_group" value="older"')
        self.assertNotContains(response, "您最想了解什麼？")
        self.assertNotContains(response, 'name="concern"')
        # The catalogue needs an account: no way there from a guest's wizard.
        self.assertNotContains(response, "?choose=self")

    def test_the_age_goes_straight_to_its_answer_page(self):
        for age_group, questionnaire in (("older", self.hhie_s), ("adult", self.hhia_s)):
            with self.subTest(age_group=age_group):
                response = self.client.get(reverse("questionnaire_list"), {"age_group": age_group})
                self.assertRedirects(
                    response,
                    reverse("screening", args=[questionnaire.pk]),
                    fetch_redirect_response=False,
                )
                self.assertEqual(self.client.get(response["Location"]).status_code, 200)

    def test_a_concern_or_the_catalogue_still_asks_the_age(self):
        for params in ({"concern": "tinnitus"}, {"choose": "self"}, {"age_group": "child"}):
            with self.subTest(params=params):
                response = self.client.get(reverse("questionnaire_list"), params)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "您目前的實際年齡？")

    def test_signed_in_the_wizard_is_as_before(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("questionnaire_list"))
        self.assertContains(response, "您最想了解什麼？")
        self.assertNotContains(response, "您目前的實際年齡？")
        response = self.client.get(reverse("questionnaire_list"), {"age_group": "older"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "您最想了解什麼？")


class AnswerPageTests(GuestTestCase):
    """#492 acceptance 3, 4, 5, 6."""

    def test_other_questionnaires_still_ask_to_log_in(self):
        for code in (thi.CODE, ssq12_tw.CODE, ioi_ha.CODE, sadl.CODE):
            with self.subTest(code=code):
                url = reverse("screening", args=[Questionnaire.objects.get(code=code).pk])
                response = self.client.get(url)
                self.assertRedirects(
                    response, f"{reverse('login')}?next={url}", fetch_redirect_response=False
                )

    def test_sending_the_web_form_asks_to_log_in(self):
        # A guest's answers are scored by the scoring-only endpoint; the web form saves records.
        url = reverse("screening", args=[self.hhie_s.pk])
        response = self.client.post(url, {})
        self.assertRedirects(
            response, f"{reverse('login')}?next={url}", fetch_redirect_response=False
        )
        self.assertEqual(Submission.objects.count(), 0)

    def test_the_guest_line_and_the_wearing_question(self):
        for questionnaire in (self.hhie_s, self.hhia_s):
            with self.subTest(questionnaire=questionnaire):
                response = self.client.get(reverse("screening", args=[questionnaire.pk]))
                content = response.content.decode()
                meta = content.index('class="answer-meta"')
                line = content.index(GUEST_LINE)
                self.assertLess(meta, line)  # the line under the questionnaire's name (G2)
                privacy = f'<a class="inline-link" href="{reverse("privacy")}">隱私權說明</a>'
                self.assertTrue(content[line:].startswith(GUEST_LINE + privacy))
                self.assertContains(response, "data-guest")
                self.assertContains(response, f'data-questionnaire-code="{questionnaire.code}"')
                # The wearing question is asked as for an account (no skip, nothing preset).
                self.assertNotContains(response, "data-skip-wearing")
                self.assertNotContains(response, "data-always-aided")
                self.assertContains(response, questionnaire.definition.wearing_question)

    def test_signed_in_the_answer_page_is_as_before(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("screening", args=[self.hhie_s.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, GUEST_LINE)
        self.assertNotContains(response, "data-guest")

    def test_the_tab_bar_is_the_logged_out_one(self):
        for url in (
            reverse("questionnaire_list"),
            reverse("screening", args=[self.hhie_s.pk]),
            reverse("guest_result", args=[self.hhie_s.code]),
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    self.nav_labels(self.client.get(url)),
                    list(test_pages.RedesignLayoutTests.LOGGED_OUT_ITEMS),
                )

    def test_its_questions_are_open_to_a_guest(self):
        # The React answer page reads them from the API.
        for questionnaire in (self.hhie_s, self.hhia_s):
            with self.subTest(questionnaire=questionnaire):
                response = self.client.get(f"/api/questionnaires/{questionnaire.pk}/")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.json()["questions"]), 10)
        for code in (thi.CODE, ioi_ha.CODE):
            with self.subTest(code=code):
                pk = Questionnaire.objects.get(code=code).pk
                self.assertEqual(self.client.get(f"/api/questionnaires/{pk}/").status_code, 403)


def shown_on_the_result_page(content):
    """(total, emotional, social, level text) as a result page shows them."""
    total = re.search(r'總分 <span class="result-number">(\d+)</span>', content).group(1)
    emotional, social = re.search(r"情緒分數：(\d+)　社交分數：(\d+)", content).groups()
    level = re.search(r'<h2 class="result-block-level"[^>]*>([^<]+)</h2>', content).group(1)
    return int(total), int(emotional), int(social), level


class GuestScoreTests(GuestTestCase):
    """#492 acceptance 7–11: the scoring-only endpoint."""

    # HHIE-S item order; a worked example per level (emotional items 1, 2, 4, 7, 9).
    LEVELS = (
        ([0, 2, 0, 0, 2, 0, 0, 2, 0, 0], (6, 2, 4, "無／極輕微影響"), "normal"),
        ([4, 4, 2, 0, 0, 0, 4, 0, 0, 2], (16, 12, 4, "輕度到中度影響"), "mild_to_moderate"),
        ([4, 4, 4, 4, 4, 4, 4, 4, 2, 0], (34, 18, 16, "顯著影響"), "severe"),
    )

    def test_saves_nothing(self):
        submissions, answers = Submission.objects.count(), Answer.objects.count()
        for scores, _shown, _level in self.LEVELS:
            for questionnaire in (self.hhie_s, self.hhia_s):
                self.assertEqual(
                    self.guest_score(self.body(questionnaire, scores)).status_code, 200
                )
        self.assertEqual(Submission.objects.count(), submissions)
        self.assertEqual(Answer.objects.count(), answers)

    def test_the_same_scores_and_level_as_the_signed_in_result_page(self):
        self.client.force_login(self.user)
        for scores, shown, level in self.LEVELS:
            with self.subTest(level=level):
                body = self.body(self.hhie_s, scores)
                response = self.guest_score(body)
                self.assertEqual(response.status_code, 200)
                data = response.json()
                saved = self.client.post(
                    "/api/submissions/",
                    json.dumps(body),
                    content_type="application/json",
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                )
                self.assertEqual(saved.status_code, 201)
                page = self.client.get(reverse("result", args=[saved.json()["id"]]))
                self.assertEqual(shown_on_the_result_page(page.content.decode()), shown)
                total, emotional, social, text = shown
                self.assertEqual(
                    data["scores"], {"total": total, "emotional": emotional, "social": social}
                )
                self.assertEqual(
                    data["level"],
                    {"code": level, "text": text, "color": self.hhie_s.definition.color(level)},
                )
                self.assertEqual(shown_on_the_result_page(data["html"]), shown)

    def test_the_response(self):
        response = self.guest_score(self.body(self.hhia_s, [0] * 10, wearing=True))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            set(data),
            {"questionnaire", "wearing_hearing_aid", "wearing_text", "scores", "level", "html"},
        )
        self.assertEqual(data["questionnaire"], {"code": hhia_s.CODE, "name": "HHIA-S"})
        self.assertIs(data["wearing_hearing_aid"], True)
        self.assertEqual(data["wearing_text"], "有戴助聽器")
        self.assertEqual(data["level"]["code"], "normal")

    def test_invalid_answers_get_the_signed_in_errors(self):
        questions = list(self.hhie_s.questions.order_by("question_number"))
        foreign = Questionnaire.objects.get(code=thi.CODE).questions.first()
        valid = self.body(self.hhie_s, [0] * 10)
        cases = {
            "missing": self.body(self.hhie_s, [0] * 9),
            "duplicate": valid
            | {"answers": [*valid["answers"][:9], {"question": questions[0].pk, "score": 0}]},
            "foreign": valid
            | {"answers": [*valid["answers"][:9], {"question": foreign.pk, "score": 0}]},
            "not a choice": self.body(self.hhie_s, [3] + [0] * 9),
            "no wearing": {
                key: value for key, value in valid.items() if key != "wearing_hearing_aid"
            },
            "wearing not a boolean": valid | {"wearing_hearing_aid": "yes"},
        }
        for name, body in cases.items():
            with self.subTest(name):
                guest = self.guest_score(body)
                self.client.force_login(self.user)
                signed_in = self.client.post(
                    "/api/submissions/",
                    json.dumps(body),
                    content_type="application/json",
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                )
                self.client.logout()
                self.assertEqual(guest.status_code, 400)
                self.assertEqual(signed_in.status_code, 400)
                self.assertEqual(guest.json(), signed_in.json())
        self.assertEqual(Submission.objects.count(), 0)

    def test_just_finished_is_a_boolean_it_needs(self):
        valid = self.body(self.hhie_s, [0] * 10)
        for value in ("missing", None, "true", 1):
            with self.subTest(value=value):
                body = dict(valid)
                if value == "missing":
                    del body["just_finished"]
                else:
                    body["just_finished"] = value
                response = self.guest_score(body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(set(response.json()), {"just_finished"})
        for value in (True, False):
            with self.subTest(value=value):
                self.assertEqual(
                    self.guest_score(valid | {"just_finished": value}).status_code, 200
                )

    def test_the_41st_in_an_hour_from_one_address_gets_429(self):
        # 40, not the grill's 20 (implementation decision I1): one questionnaire scores twice.
        body = self.body(self.hhie_s, [0] * 10)
        for _ in range(40):
            self.assertEqual(self.guest_score(body).status_code, 200)
        response = self.guest_score(body)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {"detail": LIMIT})
        self.assertNotIn("scores", response.json())
        # Another address still gets its own 40.
        self.assertEqual(self.guest_score(body, REMOTE_ADDR="203.0.113.9").status_code, 200)

    def test_invalid_requests_count_too(self):
        for _ in range(40):
            self.assertEqual(self.guest_score({}).status_code, 400)
        self.assertEqual(self.guest_score(self.body(self.hhie_s, [0] * 10)).status_code, 429)

    def test_other_questionnaires_are_refused(self):
        for code in (thi.CODE, ssq12_tw.CODE, ioi_ha.CODE, sadl.CODE):
            with self.subTest(code=code):
                questionnaire = Questionnaire.objects.get(code=code)
                body = self.body(questionnaire, [0] * questionnaire.questions.count())
                response = self.guest_score(body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(set(response.json()), {"questionnaire"})


class GuestResultPageTests(GuestTestCase):
    """#492 acceptance 4, 12, 13: the guest result page."""

    def section(self, scores, wearing=False):
        return self.guest_score(self.body(self.hhie_s, scores, wearing)).json()["html"]

    def test_the_page_never_cached_for_its_questionnaire(self):
        for questionnaire in (self.hhie_s, self.hhia_s):
            with self.subTest(questionnaire=questionnaire):
                response = self.client.get(reverse("guest_result", args=[questionnaire.code]))
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response["Cache-Control"])
                self.assertContains(
                    response, f'<h1 class="h3 mt-2 mb-1">{questionnaire.definition.topic}</h1>'
                )
                self.assertContains(response, f'data-code="{questionnaire.code}"')
                self.assertContains(response, f'data-score-url="{GUEST_SCORE}"')
                self.assertContains(response, f'data-home-url="{reverse("index")}"')
                self.assertContains(response, "guest-result.js")

    def test_other_questionnaires_have_none(self):
        for code in (thi.CODE, ioi_ha.CODE, "nonexistent"):
            with self.subTest(code=code):
                self.assertEqual(
                    self.client.get(reverse("guest_result", args=[code])).status_code, 404
                )

    def test_signed_in_goes_home(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("guest_result", args=[self.hhie_s.code]))
        self.assertRedirects(response, reverse("index"), fetch_redirect_response=False)

    def test_the_section_has_the_whole_result(self):
        scores = [4, 4, 2, 0, 0, 0, 4, 0, 0, 2]
        html = self.section(scores)
        self.assertIn('總分 <span class="result-number">16</span> 分（滿分 40）', html)
        self.assertIn(">輕度到中度影響</h2>", html)
        self.assertIn('<div class="score-bar" aria-hidden="true">', html)
        self.assertIn("情緒分數：12　社交分數：4", html)
        self.assertIn("助聽器：沒戴", html)
        self.assertIn(hhie_s.ADVICE["mild_to_moderate"], html)
        labels = dict(hhie_s.CHOICES)
        for question, score in zip(
            self.hhie_s.questions.order_by("question_number"), scores, strict=True
        ):
            self.assertIn(f"<li>{question.question_text}——{labels[score]}</li>", html)

    def test_the_section_has_no_comparison_report_or_sharing(self):
        # Even with a signed-in record of the same answers: a guest's result has no account.
        self.client.force_login(self.user)
        for _ in range(2):
            self.client.post(
                "/api/submissions/",
                json.dumps(self.body(self.hhie_s, [4] * 10)),
                content_type="application/json",
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
        self.client.logout()
        html = self.section([4] * 10)
        self.assertNotIn("result-since-last", html)
        # The 照顧旅程 card's place holds the save card instead (#496).
        self.assertEqual(html.count('<div class="result-next">'), 1)
        self.assertIn('<h2 class="result-next-title">註冊保存這次結果</h2>', html)
        for name in ("share_report", "health_report", "my_hearing"):
            self.assertNotIn(f'href="{reverse(name)}', html)


class PrivacyTests(GuestTestCase):
    """#492 acceptance 33."""

    def test_the_new_sentence_and_the_same_consent_version(self):
        response = self.client.get(reverse("privacy"))
        self.assertContains(response, "未註冊時只計算、不儲存，作答留在您的瀏覽器")
        # Spec #478 raised it to 5 the same day; #492 adds no version of its own (spec #505
        # raised it to 6 for Google).
        self.assertGreaterEqual(models.CONSENT_VERSION, 5)


class GuestClearRowTests(GuestTestCase):
    """#498 (#492 acceptance 16, the #493 mockup's E1): the guest result's section ends with the
    red row 「清除這次結果」, which opens its confirmation under it; a record's page has none."""

    CONFIRM = "清除後就找不回來了，確定嗎？"

    def test_the_guest_section_ends_with_the_row_and_its_confirmation(self):
        html = self.guest_score(self.body(self.hhie_s, [4] * 10)).json()["html"]
        row = re.search(r"<details [^>]*data-guest-clear>(.*?)</details>", html, re.S)
        self.assertIsNotNone(row)
        row = row.group(1)
        summary = re.search(r"<summary>(.*?)</summary>", row, re.S).group(1)
        self.assertIn('data-icon="trash"', summary)
        self.assertIn("<span>清除這次結果</span>", summary)
        self.assertIn(f"data-guest-clear-question>{self.CONFIRM}</p>", row)
        # Red solid 清除 above, the blue frame 不要 under it (#470's account deletion).
        self.assertRegex(
            row,
            r'<button type="button" class="btn btn-danger[^"]*" data-guest-clear-yes>清除</button>'
            r'\s*<button type="button" class="btn btn-outline-primary[^"]*" data-guest-clear-no>'
            r"不要</button>",
        )
        # The last row of the result's list, after 看完整說明.
        self.assertLess(html.index('class="result-details"'), html.index("data-guest-clear"))

    def test_a_records_result_page_has_no_clear_row(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/submissions/",
            json.dumps(self.body(self.hhie_s, [4] * 10)),
            content_type="application/json",
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        page = self.client.get(reverse("result", args=[response.json()["id"]]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "data-guest-clear")
        self.assertNotContains(page, self.CONFIRM)


class GuestLimitBehindTheProxyTests(GuestTestCase):
    """Implementation decision I2: behind the VPS's one Nginx, which appends the connection's
    address to X-Forwarded-For, the limit counts the last address only."""

    REAL = "198.51.100.7"

    def use_up_the_hour(self, **extra):
        body = self.body(self.hhie_s, [0] * 10)
        for _ in range(40):
            self.assertEqual(self.guest_score(body, **extra).status_code, 200)
        return body

    def test_counts_the_last_address_of_a_forged_header(self):
        body = self.use_up_the_hour(HTTP_X_FORWARDED_FOR=f"1.2.3.4, {self.REAL}")
        # The same connection without the forged part is the same source.
        self.assertEqual(self.guest_score(body, REMOTE_ADDR=self.REAL).status_code, 429)
        # Another real address behind the same forged first value is not.
        response = self.guest_score(body, HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.9")
        self.assertEqual(response.status_code, 200)

    def test_changing_the_first_value_does_not_get_round_the_limit(self):
        body = self.use_up_the_hour(HTTP_X_FORWARDED_FOR=f"1.2.3.4, {self.REAL}")
        response = self.guest_score(body, HTTP_X_FORWARDED_FOR=f"5.6.7.8, {self.REAL}")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {"detail": LIMIT})

    def test_without_the_header_counts_the_connection(self):
        body = self.use_up_the_hour(REMOTE_ADDR=self.REAL)
        self.assertEqual(self.guest_score(body, REMOTE_ADDR=self.REAL).status_code, 429)
        self.assertEqual(self.guest_score(body, REMOTE_ADDR="203.0.113.9").status_code, 200)


class GuestFallbackTests(GuestTestCase):
    """Implementation decision I3: the web form saves records, so a guest whose React page does
    not load is asked to register instead (shown by the page's script, answer-main.test.jsx)."""

    CANNOT_LOAD = "這個瀏覽器載不出免註冊作答，請註冊後再做。"

    def test_a_guest_page_holds_the_register_note(self):
        url = reverse("screening", args=[self.hhie_s.pk])
        # After registering (and consenting), back to this questionnaire.
        register = f"/register?next=%2Fquestionnaire%2F{self.hhie_s.pk}"
        self.assertEqual(url, f"/questionnaire/{self.hhie_s.pk}")
        response = self.client.get(url)
        note = re.search(
            r'<div id="answer-guest-fallback" role="alert" hidden>(.*?)</div>',
            response.content.decode(),
            re.S,
        )
        self.assertIsNotNone(note)
        self.assertIn(self.CANNOT_LOAD, note.group(1))
        self.assertIn(f'href="{register}">註冊新帳號</a>', note.group(1))
        # React reads the same link for a browser that cannot keep the result (I4).
        self.assertContains(response, f'data-register-url="{register}"')

    def test_without_javascript_a_guest_gets_the_note_not_the_form(self):
        """Self-review P3: the form is hidden from the start, and <noscript> says the I3 note."""
        response = self.client.get(reverse("screening", args=[self.hhie_s.pk]))
        content = response.content.decode()
        register = f"/register?next=%2Fquestionnaire%2F{self.hhie_s.pk}"
        note = re.search(r"<noscript>(.*?)</noscript>", content, re.S)
        self.assertIsNotNone(note)
        self.assertIn(self.CANNOT_LOAD, note.group(1))
        self.assertIn(f'href="{register}">註冊新帳號</a>', note.group(1))
        self.assertRegex(content, r'<form id="answer-form"[^>]* hidden>')

    def test_signed_in_the_form_comes_back_as_before(self):
        self.client.force_login(self.user)
        content = self.client.get(reverse("screening", args=[self.hhie_s.pk])).content.decode()
        self.assertNotIn("<noscript>", content)
        self.assertNotRegex(content, r'<form id="answer-form"[^>]* hidden>')
        self.assertNotIn('id="answer-guest-fallback"', content)
        self.assertNotIn(self.CANNOT_LOAD, content)
        self.assertNotIn("data-register-url", content)
