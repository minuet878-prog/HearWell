import re
from pathlib import Path
from unittest import mock

from django.db import DatabaseError, IntegrityError
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.urls import reverse

from screening.forms import BaseAnswerFormSet
from screening.models import (
    Answer,
    Category,
    Question,
    Questionnaire,
    Submission,
    SubmissionQuerySet,
)
from screening.tests.helpers import consented_user, fake_definition, register


def answer_loading_script(content):
    """The answer page's own inline script; every page also carries the header wave's (#138)."""
    scripts = re.finditer(r"<script>(.*?)</script>", content, re.DOTALL)
    return next((script for script in scripts if "answer-loading" in script.group(1)), None)


class ScreeningViewAcceptValueTests(TestCase):
    def setUp(self):
        self.user_a = consented_user(username="user_a")
        self.questionnaire = Questionnaire.objects.create(
            questionnaire_name="測試問卷", code="hhie-s"
        )
        self.question = Question.objects.create(
            questionnaire=self.questionnaire,
            question_text="數值正確？",
            question_number=1,
            category=Category.EMOTIONAL,
        )

    def test_screening_view_accept_correct_value(self):
        self.client.force_login(self.user_a)
        url = reverse("screening", kwargs={"questionnaire_id": self.questionnaire.id})
        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-0-score": "4",
            "form-0-question_id": str(self.question.id),
            "wearing_hearing_aid": "True",
        }
        response = self.client.post(url, data)
        submission = Submission.objects.get(user=self.user_a, questionnaire=self.questionnaire)
        expected_reversed_url = reverse("result", kwargs={"submission_id": submission.id})
        self.assertTrue(Answer.objects.filter(question=self.question, score=4).exists())
        self.assertRedirects(response, expected_reversed_url)


class EmptyQuestionnaireSubmissionTests(TestCase):
    def setUp(self):
        self.user_a = consented_user(username="user_a")
        self.questionnaire = Questionnaire.objects.create(
            questionnaire_name="測試空submission", code="test"
        )

    def test_zero_question_questionnaire(self):
        self.client.force_login(self.user_a)
        url = reverse("screening", kwargs={"questionnaire_id": self.questionnaire.id})
        data = {
            "form-TOTAL_FORMS": 0,
            "form-INITIAL_FORMS": 0,
        }
        self.client.post(url, data)
        self.assertFalse(
            Submission.objects.filter(user=self.user_a, questionnaire=self.questionnaire).exists()
        )


class DuplicateAnswerSubmissionTests(TestCase):
    def setUp(self):
        self.user_a = consented_user(username="user_a")
        self.questionnaire = Questionnaire.objects.create(
            questionnaire_name="測試重複答案", code="test"
        )
        self.enterContext(register(fake_definition("test")))
        self.question_1 = Question.objects.create(
            questionnaire=self.questionnaire,
            question_text="第一題",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        self.question_2 = Question.objects.create(
            questionnaire=self.questionnaire,
            question_text="第二題",
            question_number=2,
            category=Category.SOCIAL,
        )

    def test_duplicate_answer_submission(self):
        self.client.force_login(self.user_a)
        url = reverse("screening", kwargs={"questionnaire_id": self.questionnaire.id})
        data = {
            "form-TOTAL_FORMS": 3,
            "form-INITIAL_FORMS": 0,
            "form-0-score": 4,
            "form-0-question_id": str(self.question_1.id),
            "form-1-score": 2,
            "form-1-question_id": str(self.question_2.id),
            "form-2-score": 2,
            "form-2-question_id": str(self.question_1.id),
            "wearing_hearing_aid": "True",
        }
        response = self.client.post(url, data)
        self.assertFalse(
            Submission.objects.filter(user=self.user_a, questionnaire=self.questionnaire).exists()
        )
        self.assertEqual(response.status_code, 200)


class HearingAidTests(TestCase):
    PROMPT = "這次填答時，您有沒有戴助聽器？"
    ERROR = "請選擇這次有沒有戴助聽器"

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="user")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.question = Question.objects.create(
            questionnaire=cls.questionnaire,
            question_text="第一題",
            question_number=1,
            category=Category.EMOTIONAL,
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.questionnaire.id])

    def _post(self, **extra):
        data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-0-score": "4",
            "form-0-question_id": str(self.question.id),
            **extra,
        }
        return self.client.post(self.url, data)

    def _make_submission(self, wearing):
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.create(submission=submission, question=self.question, score=4)
        return submission

    def test_failure_midway_leaves_nothing(self):
        # The web form and the API share formset.save(); this guards its all-or-nothing.
        with (
            mock.patch.object(Answer.objects, "bulk_create", side_effect=DatabaseError),
            self.assertRaises(DatabaseError),
        ):
            self._post(wearing_hearing_aid="False")
        self.assertFalse(Submission.objects.exists())

    def test_question_shown_before_first_question_without_default(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertLess(content.index(self.PROMPT), content.index("第一題"))
        self.assertContains(response, 'name="wearing_hearing_aid" value="True"')
        self.assertContains(response, 'name="wearing_hearing_aid" value="False"')
        self.assertContains(response, "有戴")
        self.assertContains(response, "沒戴")
        self.assertNotContains(response, "checked")

    def test_wearing_choices_put_unaided_first_with_the_same_values(self):
        # #362: 沒戴 then 有戴, as the wizard and React page; what is saved stays False / True.
        html = self.client.get(self.url).content.decode()
        fieldset = r'<fieldset id="question-hearing-aid".*?</fieldset>'
        content = re.search(fieldset, html, re.S).group()
        choices = re.findall(r'value="(True|False)"[^>]*>\s*([^<]+?)\s*</label>', content)
        self.assertEqual(choices, [("False", "沒戴"), ("True", "有戴")])

    def test_wearing_saved_and_shown_on_result(self):
        response = self._post(wearing_hearing_aid="True")
        submission = Submission.objects.get(user=self.user)
        self.assertIs(submission.wearing_hearing_aid, True)
        response = self.client.get(response.url)
        self.assertContains(response, "助聽器：有戴")

    def test_not_wearing_saved_and_shown_on_result(self):
        response = self._post(wearing_hearing_aid="False")
        submission = Submission.objects.get(user=self.user)
        self.assertIs(submission.wearing_hearing_aid, False)
        response = self.client.get(response.url)
        self.assertContains(response, "助聽器：沒戴")

    def test_missing_answer_rejected_and_answers_kept(self):
        response = self._post()
        self.assertFalse(Submission.objects.exists())
        self.assertContains(response, self.ERROR)
        self.assertContains(
            response,
            '<input type="radio" name="form-0-score" value="4" class="choice-group"'
            ' id="id_form-0-score_0" checked>',
            html=True,
        )

    def test_hearing_aid_choice_kept_when_answer_missing(self):
        response = self._post(**{"form-0-score": "", "wearing_hearing_aid": "False"})
        self.assertFalse(Submission.objects.exists())
        self.assertContains(
            response,
            '<input type="radio" name="wearing_hearing_aid" value="False" class="choice-group"'
            ' required id="id_wearing_hearing_aid_0" checked>',
            html=True,
        )

    def test_tampered_value_rejected(self):
        response = self._post(wearing_hearing_aid="maybe")
        self.assertFalse(Submission.objects.exists())
        self.assertContains(response, self.ERROR)

    def test_unrecorded_submission_shows_unrecorded(self):
        submission = self._make_submission(None)
        response = self.client.get(reverse("result", args=[submission.id]))
        self.assertContains(response, "助聽器：未記錄")
        response = self.client.get(reverse("my_hearing"))
        self.assertContains(response, "助聽器：未記錄")

    def test_history_shows_each_status(self):
        for wearing in (True, False, None):
            self._make_submission(wearing)
        response = self.client.get(reverse("my_hearing"))
        for label in ("助聽器：有戴", "助聽器：沒戴", "助聽器：未記錄"):
            self.assertContains(response, label, count=1)

    def test_status_does_not_change_score(self):
        wearing = self._make_submission(True)
        not_wearing = self._make_submission(False)
        self.assertEqual(wearing.total_answer_score, not_wearing.total_answer_score)
        self.assertEqual(wearing.result.level, not_wearing.result.level)

    def test_new_text_uses_readable_style(self):
        submission = self._make_submission(True)
        response = self.client.get(reverse("result", args=[submission.id]))
        self.assertContains(response, '<p class="text-black mb-1">助聽器：有戴</p>', html=True)


class PreselectUnaidedTests(TestCase):
    """#154: the catch-up link starts the hearing aid question on 沒戴; the user may change it."""

    HINT = "請想沒戴助聽器時的情況來回答"

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="catching_up")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.question = Question.objects.create(
            questionnaire=cls.questionnaire,
            question_text="第一題",
            question_number=1,
            category=Category.EMOTIONAL,
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.questionnaire.id])

    def hearing_aid_fieldset(self, response):
        html = response.content.decode()
        return re.search(r'<fieldset id="question-hearing-aid".*?</fieldset>', html, re.S).group()

    def test_form_starts_on_unaided_with_the_hint(self):
        fieldset = self.hearing_aid_fieldset(self.client.get(self.url, {"preselect": "unaided"}))
        self.assertInHTML(
            '<input type="radio" name="wearing_hearing_aid" value="False" class="choice-group"'
            ' required id="id_wearing_hearing_aid_0" checked>',
            fieldset,
        )
        self.assertEqual(fieldset.count("checked"), 1)
        # Said in the question's group, so a screen reader reads it with the choices.
        self.assertIn('aria-describedby="hearing-aid-hint"', fieldset)
        self.assertIn(f'<p id="hearing-aid-hint">{self.HINT}</p>', fieldset)

    def test_tells_react_to_start_on_unaided_too(self):
        # answer-main.jsx hands this to AnswerApp; without the parameter React chooses nothing.
        for params, marked in (({"preselect": "unaided"}, True), ({}, False)):
            with self.subTest(params=params):
                content = self.client.get(self.url, params).content.decode()
                app = re.search(r'<div id="answer-app"[^>]*>', content).group()
                self.assertEqual("data-preselect-unaided" in app, marked)

    def answers(self, **extra):
        return {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 1,
            "form-0-score": "4",
            "form-0-question_id": str(self.question.id),
            **extra,
        }

    def test_changed_to_aided_is_saved_as_aided(self):
        page = self.client.get(self.url, {"preselect": "unaided"})
        action = re.search(r'<form id="answer-form" action="([^"]+)"', page.content.decode())
        response = self.client.post(action.group(1), self.answers(wearing_hearing_aid="True"))
        submission = Submission.objects.get(user=self.user)
        self.assertRedirects(response, reverse("result", args=[submission.id]))
        self.assertIs(submission.wearing_hearing_aid, True)

    def test_the_parameter_never_answers_for_the_user(self):
        # Sent without a choice, even to the marked address: asked again, nothing saved.
        response = self.client.post(f"{self.url}?preselect=unaided", self.answers())
        self.assertFalse(Submission.objects.exists())
        self.assertContains(response, HearingAidTests.ERROR)

    def test_no_preselection_otherwise(self):
        for params in ({}, {"preselect": "aided"}, {"preselect": ""}):
            with self.subTest(params=params):
                fieldset = self.hearing_aid_fieldset(self.client.get(self.url, params))
                self.assertNotIn("checked", fieldset)
                self.assertNotIn(self.HINT, fieldset)


class TamperedAnswerTests(TestCase):
    ERROR = "表單資料有誤，請重新確認每一題的作答"

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="tester")
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.questionnaire,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.questionnaire.id])

    def _data(self, skip=()):
        # Same management form the real page sends: every form is an initial form.
        data = {"form-TOTAL_FORMS": 10, "form-INITIAL_FORMS": 10, "wearing_hearing_aid": "True"}
        for i, question in enumerate(self.questions):
            data[f"form-{i}-question_id"] = str(question.id)
            if question.question_number not in skip:
                data[f"form-{i}-score"] = "4"
        return data

    def _assert_rejected(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ERROR)
        # No "還有 N 題" summary; a cleared form may still be marked under its question.
        self.assertNotContains(response, "題沒有回答")
        self.assertFalse(Submission.objects.exists())
        self.assertFalse(Answer.objects.exists())

    def test_extra_empty_forms_are_rejected(self):
        data = self._data()
        data["form-TOTAL_FORMS"] = 12
        self._assert_rejected(self.client.post(self.url, data))

    def test_cleared_new_form_is_rejected(self):
        data = self._data()
        data["form-INITIAL_FORMS"] = 0
        del data["form-4-question_id"], data["form-4-score"]
        self._assert_rejected(self.client.post(self.url, data))

    def test_fewer_forms_than_questions_still_rejected(self):
        data = self._data()
        data["form-TOTAL_FORMS"] = 9
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "有題目沒有作答")
        self.assertFalse(Submission.objects.exists())

    def test_question_from_another_questionnaire_rejected(self):
        other = Questionnaire.objects.create(questionnaire_name="其他問卷", code="other")
        foreign = Question.objects.create(
            questionnaire=other, question_text="別的題", question_number=1, category=Category.SOCIAL
        )
        data = self._data()
        data["form-9-question_id"] = str(foreign.id)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Submission.objects.exists())
        self.assertFalse(Answer.objects.exists())

    def test_normal_answers_still_saved(self):
        response = self.client.post(self.url, self._data())
        submission = Submission.objects.get()
        self.assertRedirects(response, reverse("result", args=[submission.id]))
        self.assertEqual(submission.answers.count(), 10)

    def test_unanswered_question_still_pointed_out(self):
        content = self.client.post(self.url, self._data(skip=(3,))).content.decode()
        self.assertIn("還有 1 題沒有回答，請看標示紅字的題目。", content)
        self.assertFalse(Submission.objects.exists())


class ReactAnswerPageTests(TestCase):
    """Spec docs/specs/phase-05/phase5_react_answer.md: Django side of the React answer page."""

    ANSWER_JS = "screening/frontend/answer.js"
    LOGOUT_JS = "screening/frontend/logout.js"
    VITE_CONFIG = Path(__file__).resolve().parent.parent.parent / "frontend" / "vite.config.js"

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="react_answer")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code="hhia-s")
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        for questionnaire in (cls.hhie_s, cls.hhia_s, cls.ioi_ha):
            Question.objects.create(
                questionnaire=questionnaire,
                question_text=f"{questionnaire.code} 第1題",
                question_number=1,
                category="" if questionnaire.code == "ioi-ha" else Category.EMOTIONAL,
            )

    def setUp(self):
        self.client.force_login(self.user)

    def _page(self, questionnaire):
        return self.client.get(reverse("screening", args=[questionnaire.id]))

    def test_hhie_s_and_hhia_s_load_react_with_their_data(self):
        for questionnaire in (self.hhie_s, self.hhia_s):
            with self.subTest(code=questionnaire.code):
                response = self._page(questionnaire)
                self.assertContains(response, self.ANSWER_JS)
                self.assertContains(response, 'id="answer-app"')
                self.assertContains(response, f'data-questionnaire-id="{questionnaire.id}"')
                self.assertContains(response, f'data-user-id="{self.user.id}"')

    def test_django_form_is_still_complete_without_js(self):
        # Fallback when the JS does not load: the full form is rendered and posts as before.
        response = self._page(self.hhie_s)
        self.assertContains(response, 'id="answer-form"')
        self.assertContains(response, 'name="wearing_hearing_aid"')
        self.assertContains(response, "hhie-s 第1題")
        self.assertContains(response, 'type="submit"')
        question = self.hhie_s.questions.get()
        response = self.client.post(
            reverse("screening", args=[self.hhie_s.id]),
            {
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-0-question_id": str(question.id),
                "form-0-score": "4",
                "wearing_hearing_aid": "False",
            },
        )
        submission = Submission.objects.get(user=self.user)
        self.assertRedirects(response, reverse("result", args=[submission.id]))

    def test_intro_is_outside_the_form(self):
        # React hides the form, so the name, count and instructions must stay visible outside it.
        content = self._page(self.hhie_s).content.decode()
        form_start = content.index('id="answer-form"')
        self.assertLess(content.index("<h1"), form_start)
        self.assertLess(content.index("共 1 題"), form_start)
        self.assertLess(content.index("本問卷的目的"), form_start)

    def test_hands_react_the_minutes_and_the_intro(self):
        # #153: React works out the minutes left and folds the intro after the hearing aid question.
        for questionnaire in (self.hhie_s, self.hhia_s):
            with self.subTest(code=questionnaire.code):
                content = self._page(questionnaire).content.decode()
                app = re.search(r'<div id="answer-app"[^>]*>', content).group()
                self.assertIn(f'data-minutes="{questionnaire.definition.minutes}"', app)
                # The definition's intro, word for word, in the box React reads it from.
                intro = re.search(r'<div id="answer-intro">(.*?)</div>', content, re.S).group(1)
                expected = render_to_string(
                    questionnaire.definition.intro_template, {"questionnaire": questionnaire}
                )
                self.assertEqual(intro.strip(), expected.strip())
                self.assertLess(
                    content.index('id="answer-intro"'), content.index('id="answer-app"')
                )
                # Without JS the one-page form keeps its old progress text and has no bar.
                form = content[content.index('id="answer-form"') :]
                count = questionnaire.questions.count()
                for number in range(1, count + 1):
                    self.assertIn(
                        f'<span class="question-progress">第 {number} 題／共 {count} 題</span>',
                        form,
                    )
                self.assertNotIn("還剩大約", content)
                self.assertNotIn("step-progress-bar", content)

    def test_answer_js_only_on_answer_pages(self):
        for url in (reverse("index"), reverse("questionnaire_list"), reverse("my_hearing")):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), self.ANSWER_JS)

    def test_logout_js_when_logged_in_only(self):
        for url in (reverse("index"), reverse("questionnaire_list"), reverse("my_hearing")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, self.LOGOUT_JS)
                self.assertContains(response, 'id="logout-form"')
        self.client.logout()
        for url in (reverse("index"), reverse("login"), reverse("register")):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), self.LOGOUT_JS)

    def test_bundle_paths_match_vite_output(self):
        # The templates and the Vite build must agree on where the bundles live.
        config = self.VITE_CONFIG.read_text(encoding="utf-8")
        self.assertIn('"../screening/static/screening/frontend"', config)
        for entry in ('"trend-chart"', '"answer"', '"logout"'):
            with self.subTest(entry=entry):
                self.assertIn(entry, config)


class AnswerFlashTests(TestCase):
    """Spec docs/specs/phase-05/phase5_answer_flash.md, acceptance 1, 6-8 (page side)."""

    # Borrowed without inheriting (and rerunning) its tests; unwrap so `cls` is this class.
    setUpTestData = classmethod(ReactAnswerPageTests.setUpTestData.__func__)
    setUp = ReactAnswerPageTests.setUp
    _page = ReactAnswerPageTests._page

    def test_loading_note_and_script_come_before_the_form(self):
        for questionnaire in (self.hhie_s, self.hhia_s):
            with self.subTest(code=questionnaire.code):
                content = self._page(questionnaire).content.decode()
                form_start = content.index('id="answer-form"')
                status = re.search(r'<p id="answer-loading"[^>]*>', content)
                self.assertIsNotNone(status)
                self.assertIn('role="status"', status.group())
                # B1 (ADR 0027): the sliding track under 題目載入中….
                self.assertRegex(status.group(), r'class="[^"]*\bloading-message\b')
                self.assertLess(status.start(), form_start)
                inline = answer_loading_script(content)
                self.assertIsNotNone(inline)
                self.assertLess(inline.start(), form_start)
                self.assertIn("answer-loading", inline.group(1))
                self.assertIn("5000", inline.group(1))
                # Without JS the note stays empty: its text only comes from the script.
                self.assertEqual(
                    re.search(r'<p id="answer-loading"[^>]*>(.*?)</p>', content).group(1), ""
                )

    def test_form_is_not_hidden_in_the_html(self):
        # Acceptance 6: only the class the script adds hides the form.
        content = self._page(self.hhie_s).content.decode()
        form_tag = re.search(r'<form id="answer-form"[^>]*>', content).group()
        self.assertNotIn("hidden", form_tag)
        self.assertNotIn("style=", form_tag)
        self.assertNotIn("answer-loading", re.search(r"<html[^>]*>", content).group())


class WebDoubleSubmitTests(TestCase):
    """Spec docs/specs/phase-06/phase6_web_double_submit.md, acceptance 1-9."""

    NOTICE = "這份作答剛才已經送出"
    KEY = re.compile(r'name="idempotency_key" value="([0-9a-f-]{36})"')

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="tester")
        cls.other = consented_user(username="other")
        cls.questionnaires = {}
        for code, count in (("hhie-s", 10), ("hhia-s", 10), ("ioi-ha", 7)):
            questionnaire = Questionnaire.objects.create(questionnaire_name=code, code=code)
            Question.objects.bulk_create(
                Question(
                    questionnaire=questionnaire,
                    question_text=f"{code} 第{i}題",
                    question_number=i,
                    category="" if code == "ioi-ha" else Category.EMOTIONAL,
                )
                for i in range(1, count + 1)
            )
            cls.questionnaires[code] = questionnaire

    def setUp(self):
        self.client.force_login(self.user)

    def _url(self, code="hhie-s"):
        return reverse("screening", args=[self.questionnaires[code].id])

    def _key(self, response):
        return self.KEY.search(response.content.decode()).group(1)

    def _open(self, code="hhie-s", client=None):
        return self._key((client or self.client).get(self._url(code)))

    def _data(self, key, code="hhie-s", score=2, skip=()):
        questions = self.questionnaires[code].questions.order_by("question_number")
        data = {"form-TOTAL_FORMS": len(questions), "form-INITIAL_FORMS": len(questions)}
        if code != "ioi-ha":
            data["wearing_hearing_aid"] = "False"
        if key is not None:
            data["idempotency_key"] = key
        for i, question in enumerate(questions):
            data[f"form-{i}-question_id"] = str(question.id)
            if question.question_number not in skip:
                data[f"form-{i}-score"] = str(score)
        return data

    def _post(self, data, code="hhie-s", client=None):
        return (client or self.client).post(self._url(code), data, follow=True)

    def _result_url(self, submission):
        return reverse("result", args=[submission.id])

    # 1, 6: the test client runs no JS, so the server alone stops the second save.
    def test_same_page_twice_saves_once(self):
        key = self._open()
        first = self._post(self._data(key))
        second = self._post(self._data(key))
        submission = Submission.objects.get()
        self.assertRedirects(first, self._result_url(submission))
        self.assertRedirects(second, self._result_url(submission))
        self.assertEqual(submission.answers.count(), 10)

    # 2
    def test_reopening_the_page_answers_again(self):
        first_key, second_key = self._open(), self._open()
        self.assertNotEqual(first_key, second_key)
        self._post(self._data(first_key))
        self._post(self._data(second_key))
        self.assertEqual(Submission.objects.count(), 2)

    # 3
    def test_fixing_a_missing_answer_keeps_the_key(self):
        key = self._open()
        rejected = self.client.post(self._url(), self._data(key, skip=(3,)))
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(self._key(rejected), key)
        self.assertFalse(Submission.objects.exists())
        self._post(self._data(key))
        self._post(self._data(key))
        self.assertEqual(Submission.objects.count(), 1)

    # 4: rule 8, a key is only looked up among the user's own records.
    def test_same_key_for_two_users(self):
        key = self._open()
        self._post(self._data(key))
        other_client = Client()
        other_client.force_login(self.other)
        response = self._post(self._data(key), client=other_client)
        theirs = Submission.objects.get(user=self.other)
        self.assertRedirects(response, self._result_url(theirs))
        self.assertNotContains(response, self.NOTICE)
        self.assertEqual(Submission.objects.filter(user=self.user).count(), 1)

    # 5
    def test_every_web_questionnaire(self):
        for code in ("hhie-s", "hhia-s", "ioi-ha"):
            with self.subTest(code=code):
                key = self._open(code)
                self._post(self._data(key, code), code)
                self._post(self._data(key, code), code)
                count = Submission.objects.filter(questionnaire=self.questionnaires[code]).count()
                self.assertEqual(count, 1)

    # 7, 8
    def test_changed_answers_go_to_the_first_result(self):
        key = self._open()
        first = self._post(self._data(key, score=0))
        self.assertNotContains(first, self.NOTICE)
        second = self._post(self._data(key, score=4))
        submission = Submission.objects.get()
        self.assertRedirects(second, self._result_url(submission))
        self.assertContains(second, self.NOTICE)
        self.assertEqual(submission.total_answer_score, 0)
        # Shown once: reloading the result page does not repeat it.
        self.assertNotContains(self.client.get(self._result_url(submission)), self.NOTICE)

    # 7: a resend from the same page is not validated again, even with an answer cleared.
    def test_resend_with_missing_answer_goes_to_the_first_result(self):
        key = self._open()
        self._post(self._data(key))
        response = self._post(self._data(key, skip=(3,)))
        self.assertRedirects(response, self._result_url(Submission.objects.get()))
        self.assertContains(response, self.NOTICE)

    # 9
    def test_missing_or_malformed_key_still_saves(self):
        for key in (None, "", "not-a-uuid"):
            with self.subTest(key=key):
                response = self._post(self._data(key))
                self.assertRedirects(response, self._result_url(Submission.objects.latest("id")))
        self.assertEqual(Submission.objects.count(), 3)

    # 10: every web questionnaire's fallback form is a POST form in main with a submit <button>,
    # which page-loading.js turns into 送出中… (ADR 0027; it replaced submit-button.js).
    def test_submit_feedback_markup(self):
        for code in ("hhie-s", "ioi-ha"):
            with self.subTest(code=code):
                content = self.client.get(self._url(code)).content.decode()
                main = content[content.index('id="main-content"') :]
                start = main.index('id="answer-form"')
                form = main[start : main.index("</form>", start)]
                self.assertIn('method="POST"', form)
                self.assertIn(
                    '<button class="btn btn-primary btn-lg" type="submit">送出</button>', form
                )

    # Review 1-1: only a clash with this page's own earlier save counts as "already sent";
    # any other IntegrityError must surface, not send the user to an unrelated result.
    def test_other_integrity_errors_are_not_hidden(self):
        Submission.objects.create(user=self.user, questionnaire=self.questionnaires["hhie-s"])
        for key in (None, self._open()):
            with self.subTest(key=key):
                with (
                    mock.patch.object(BaseAnswerFormSet, "save", side_effect=IntegrityError),
                    self.assertRaises(IntegrityError),
                ):
                    self._post(self._data(key))

    # 1: two clicks arriving together; the second only finds the first at the unique constraint.
    def test_simultaneous_clicks_save_once(self):
        key = self._open()
        self._post(self._data(key))
        first = Submission.objects.get()
        real_find = SubmissionQuerySet.find_by_key
        calls = []

        def find(submissions, key):
            # The first lookup misses, as if the other click had not been saved yet.
            calls.append(key)
            return None if len(calls) == 1 else real_find(submissions, key)

        with mock.patch.object(SubmissionQuerySet, "find_by_key", autospec=True, side_effect=find):
            response = self._post(self._data(key))
        self.assertEqual(len(calls), 2)
        self.assertRedirects(response, self._result_url(first))
        self.assertEqual(Submission.objects.count(), 1)


class WebFormErrorsStayTests(TestCase):
    """Spec docs/specs/phase-06/phase6_web_form_errors_stay.md, acceptance 1-5."""

    ANSWER_JS = ReactAnswerPageTests.ANSWER_JS
    MISSING_ONE = "還有 1 題沒有回答"

    # Borrowed without inheriting (and rerunning) its tests; unwrap so `cls` is this class.
    setUpTestData = classmethod(WebDoubleSubmitTests.setUpTestData.__func__)
    setUp = WebDoubleSubmitTests.setUp
    _url = WebDoubleSubmitTests._url
    _key = WebDoubleSubmitTests._key
    _open = WebDoubleSubmitTests._open
    _data = WebDoubleSubmitTests._data
    KEY = WebDoubleSubmitTests.KEY

    def _assert_stays_on_web_form(self, response):
        content = response.content.decode()
        self.assertNotIn(self.ANSWER_JS, content)
        self.assertNotIn('id="answer-app"', content)
        self.assertNotIn("answer-loading", content)
        self.assertIsNone(answer_loading_script(content))
        form_tag = re.search(r'<form id="answer-form"[^>]*>', content).group()
        self.assertNotIn("hidden", form_tag)
        self.assertNotIn("style=", form_tag)

    def test_missing_answer_shows_errors_keeps_answers_and_no_react(self):
        # Acceptance 1 and 5.
        key = self._open()
        response = self.client.post(self._url(), self._data(key, skip=(3,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.MISSING_ONE)
        content = response.content.decode()
        self.assertIn('aria-describedby="id_form-2-score_error"', content)
        for i in range(10):
            checked = re.search(rf'name="form-{i}-score" value="2"[^>]*checked', content)
            with self.subTest(form=i):
                if i == 2:
                    self.assertIsNone(checked)
                else:
                    self.assertIsNotNone(checked)
        self.assertRegex(content, r'name="wearing_hearing_aid" value="False"[^>]*checked')
        self._assert_stays_on_web_form(response)

    def test_missing_hearing_aid_answer_also_stays_on_web_form(self):
        data = self._data(self._open())
        del data["wearing_hearing_aid"]
        response = self.client.post(self._url(), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-describedby="id_wearing_hearing_aid_error"')
        self._assert_stays_on_web_form(response)

    def test_fixed_answers_save_once_under_the_same_key(self):
        # Acceptance 2.
        key = self._open()
        failed = self.client.post(self._url(), self._data(key, skip=(3,)))
        self.assertEqual(self._key(failed), key)
        response = self.client.post(self._url(), self._data(key), follow=True)
        submission = Submission.objects.get()
        self.assertEqual(str(submission.idempotency_key), key)
        self.assertRedirects(response, reverse("result", args=[submission.id]))

    def test_opening_the_page_still_loads_react(self):
        # Acceptance 3.
        for code in ("hhie-s", "hhia-s", "ioi-ha"):
            with self.subTest(code=code):
                response = self.client.get(self._url(code))
                self.assertContains(response, self.ANSWER_JS)
                self.assertContains(response, 'id="answer-app"')
                self.assertContains(response, 'id="answer-loading"')

    def test_ioi_ha_failed_submit_unchanged(self):
        # Acceptance 4.
        key = self._open("ioi-ha")
        response = self.client.post(self._url("ioi-ha"), self._data(key, "ioi-ha", skip=(3,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.MISSING_ONE)
        self.assertEqual(self._key(response), key)
        self._assert_stays_on_web_form(response)
        self.assertFalse(Submission.objects.exists())


class ErrorSummaryTests(TestCase):
    """Spec docs/specs/phase-06/phase6_a11y_remeasure.md, acceptance 8-10."""

    setUpTestData = classmethod(WebDoubleSubmitTests.setUpTestData.__func__)
    setUp = WebDoubleSubmitTests.setUp
    _url = WebDoubleSubmitTests._url
    _key = WebDoubleSubmitTests._key
    _open = WebDoubleSubmitTests._open
    _data = WebDoubleSubmitTests._data
    KEY = WebDoubleSubmitTests.KEY

    SUMMARY = re.compile(r'<div id="error-summary"[^>]*>.*?</div>', re.DOTALL)

    def _summary(self, data, code="hhie-s"):
        content = self.client.post(self._url(code), data).content.decode()
        match = self.SUMMARY.search(content)
        self.assertIsNotNone(match, "no error summary")
        return content, match.group()

    def _links(self, summary):
        return re.findall(r'<a [^>]*href="#([^"]+)"[^>]*>([^<]+)</a>', summary)

    def _assert_targets_exist(self, content, links):
        for target, _ in links:
            with self.subTest(target=target):
                # The whole question, so its text scrolls into view and is read out.
                self.assertRegex(content, rf'<fieldset id="{re.escape(target)}" tabindex="-1"')

    # 8
    def test_missing_questions_listed_with_links(self):
        content, summary = self._summary(self._data(self._open(), skip=(2, 5, 7)))
        self.assertIn("還有 3 題沒有回答", summary)
        links = self._links(summary)
        self.assertEqual(
            links,
            [
                ("question-2", "第 2 題"),
                ("question-5", "第 5 題"),
                ("question-7", "第 7 題"),
            ],
        )
        self._assert_targets_exist(content, links)

    # 9
    def test_only_hearing_aid_missing_still_has_summary(self):
        data = self._data(self._open())
        del data["wearing_hearing_aid"]
        content, summary = self._summary(data)
        self.assertIn("還有 1 題沒有回答", summary)
        links = self._links(summary)
        self.assertEqual(links, [("question-hearing-aid", "是否戴助聽器")])
        self._assert_targets_exist(content, links)

    def test_hearing_aid_listed_first(self):
        data = self._data(self._open(), skip=(3,))
        del data["wearing_hearing_aid"]
        _, summary = self._summary(data)
        self.assertIn("還有 2 題沒有回答", summary)
        self.assertEqual([text for _, text in self._links(summary)], ["是否戴助聽器", "第 3 題"])

    def test_ioi_ha_has_no_hearing_aid_item(self):
        _, summary = self._summary(self._data(self._open("ioi-ha"), "ioi-ha", skip=(4,)), "ioi-ha")
        self.assertEqual(self._links(summary), [("question-4", "第 4 題")])

    # 10
    def test_summary_takes_focus_and_is_announced(self):
        _, summary = self._summary(self._data(self._open(), skip=(1,)))
        opening = re.match(r"<div[^>]*>", summary).group()
        self.assertIn('role="alert"', opening)
        self.assertIn('tabindex="-1"', opening)
        self.assertRegex(opening, r"\bautofocus\b")

    def test_no_summary_before_submitting(self):
        self.assertNotIn('id="error-summary"', self.client.get(self._url()).content.decode())

    def test_no_template_comment_leaks_onto_the_page(self):
        content, _ = self._summary(self._data(self._open(), skip=(1,)))
        self.assertNotIn("{#", content)
        self.assertNotIn("#}", content)

    def test_generic_error_list_is_not_inside_a_paragraph(self):
        data = self._data(self._open())
        data["form-TOTAL_FORMS"] = 12
        content, summary = self._summary(data)
        self.assertIn("表單資料有誤", summary)
        self.assertNotRegex(content, r"<p[^>]*>\s*<ul")
