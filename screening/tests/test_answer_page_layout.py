"""#755 (spec #741 acceptance 47, P10, P21): the answer page's layout, as the page draws it.
React's part (the choices, 上一題／下一題, the count, 已儲存) is AnswerApp.test.jsx's."""

import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import Questionnaire
from screening.tests.helpers import consented_user

LEAVE = "離開"


def header(content):
    return content[content.index("<header") : content.index("</header>")]


class AnswerPageLayoutTests(TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S, IOI-HA
    CODES = ("hhie-s", "hhia-s", "thi", "ssq12-tw", "sadl", "ioi-ha")

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())  # HHIA-S, THI, SSQ12-TW, SADL
        cls.user = consented_user(username="answer_layout", birth_year=1950)

    def page(self, code, signed_in=True):
        if signed_in:
            self.client.force_login(self.user)
        else:
            self.client.logout()
        pk = Questionnaire.objects.get(code=code).pk
        return self.client.get(reverse("screening", args=[pk])).content.decode()

    # P21: 離開 at the top left all the time, in place of 聽伴 and the floating back button, which
    # on this page would go back a question rather than out. The topic on the right went in the
    # owner's 2026-11-27 walkthrough: nothing on the right.
    def test_the_header_says_leave_at_the_top_left_and_nothing_on_the_right(self):
        for code, signed_in in [(code, True) for code in self.CODES] + [("hhie-s", False)]:
            with self.subTest(code=code, signed_in=signed_in):
                top = header(self.page(code, signed_in))
                start = re.search(r'<div class="site-header-start">(.*?)</div>', top, re.S).group(1)
                leave = re.fullmatch(
                    r'\s*<a class="site-leave" href="([^"]+)">(.*?)</a>\s*', start, re.S
                )
                self.assertIsNotNone(leave, start)
                self.assertEqual(leave.group(1), reverse("questionnaire_list"))
                self.assertIn('<path d="M15 6l-6 6 6 6"/>', leave.group(2))
                self.assertEqual(re.sub(r"<[^>]+>|\s", "", leave.group(2)), LEAVE)
                self.assertNotIn("data-site-back", top)
                self.assertNotIn("site-brand", top)
                self.assertNotIn("site-header-title", top)
                self.assertNotIn("site-avatar", top)
                self.assertNotIn("site-login", top)

    # P21: the reassurance's first sentence is gone; where a draft is kept the second stays.
    def test_it_no_longer_says_it_is_not_a_test(self):
        for code, signed_in in [(code, True) for code in self.CODES] + [("hhie-s", False)]:
            with self.subTest(code=code, signed_in=signed_in):
                self.assertNotIn("這不是考試", self.page(code, signed_in))

    # P21: 這份問卷在問什麼？ folded under the questions. React draws its own fold under its
    # buttons (AnswerApp.test.jsx); the form given back without React folds the intro there too.
    def test_the_intro_is_folded_under_the_questions(self):
        for code in self.CODES:
            with self.subTest(code=code):
                content = self.page(code)
                fold = re.search(
                    r'<details class="questionnaire-fold" id="answer-intro-fold">\s*<summary>'
                    r"(.*?)</summary>\s*<div id=\"answer-intro\">",
                    content,
                    re.S,
                )
                self.assertIsNotNone(fold)
                self.assertEqual(re.sub(r"<[^>]+>|\s", "", fold.group(1)), "這份問卷在問什麼？")
                self.assertLess(content.index("</form>"), fold.start())
                self.assertLess(content.index('id="answer-app"'), fold.start())

    # P10: the questions and choices word for word as the questionnaire has them, in the form
    # given back without React and in what React reads (AnswerApp.test.jsx draws them as given).
    def test_questions_and_choices_are_the_questionnaires_own_words(self):
        for code in self.CODES:
            with self.subTest(code=code):
                questionnaire = Questionnaire.objects.get(code=code)
                content = self.page(code)
                form = content[content.index('<form id="answer-form"') : content.index("</form>")]
                legends = re.findall(
                    r'<legend class="font-bold text-xl/normal"><span class="question-progress">'
                    r"[^<]*</span>([^<]*)</legend>",
                    form,
                )
                questions = list(questionnaire.questions.order_by("question_number"))
                texts = [question.question_text for question in questions]
                if questionnaire.definition.questions:
                    self.assertEqual(texts, [t for _, t in questionnaire.definition.questions])
                self.assertEqual(legends, texts)
                api = self.client.get(f"/api/questionnaires/{questionnaire.pk}/").json()
                self.assertEqual([q["text"] for q in api["questions"]], texts)
                for question, shown in zip(questions, api["questions"], strict=True):
                    labels = [
                        label
                        for _, label in questionnaire.definition.choices(question.question_number)
                    ]
                    self.assertEqual([c["label"] for c in shown["choices"]], labels)

    def test_other_pages_keep_the_name_and_the_back_button(self):
        self.client.force_login(self.user)
        top = header(self.client.get(reverse("questionnaire_list")).content.decode())
        self.assertIn("site-brand", top)
        self.assertIn("data-site-back", top)
        self.assertNotIn("site-leave", top)
