"""#304 (spec #297, ADR 0023): every result page shows the home page's 建議您下一步."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, NormGroup, Questionnaire, Submission
from screening.questionnaires import hhie_s
from screening.tests import test_home_next_step, test_result_pages
from screening.tests.helpers import action_cards, consented_user

SUGGESTIONS = (
    "記錄醫院的聽力圖",
    "修改這張聽力圖",
    "了解助聽器選配與補助",
    "分享報告給家人",
    "印聽力報告給醫師看",
)
REPORT_CARD = (reverse("health_report"), "看／印聽力報告", "可以印出來或存成 PDF")
OTHERS_TITLE = "其他您可以做的"


class ResultNextStepTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        # What the home page tests' answer() needs: HHIE-S and its questions.
        cls.hhie_s = Questionnaire.objects.get(code=hhie_s.CODE)
        cls.questions = list(cls.hhie_s.questions.all())

    answer = test_home_next_step.HomeNextStepTests.answer
    make = test_home_next_step.HomeNextStepTests.make
    suggest = test_home_next_step.HomeNextStepTests.suggest
    section = test_home_next_step.HomeNextStepTests.section
    next_step = test_home_next_step.HomeNextStepTests.next_step

    def sign_in(self, username):
        self.user = consented_user(username=username)
        self.client.force_login(self.user)

    def answer_all(self):
        """One submission of each of the six questionnaires, as test_result_pages answers them."""
        submissions = {}
        for code, (score, _, _) in test_result_pages.QUESTIONNAIRES.items():
            questionnaire = Questionnaire.objects.get(code=code)
            submission = Submission.objects.create(
                user=self.user,
                questionnaire=questionnaire,
                wearing_hearing_aid=code in test_result_pages.ALWAYS_AIDED,
                norm_group=NormGroup.MILD_MODERATE if code == "ioi-ha" else "",
                norm_basis=submissions.get("hhie-s"),
            )
            Answer.objects.bulk_create(
                Answer(submission=submission, question=question, score=score)
                for question in questionnaire.questions.all()
            )
            submissions[code] = submission
        return submissions

    def result(self, submission):
        content = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def test_every_result_page_suggests_what_the_home_page_does(self):
        # Acceptance 8: label, title, 「因為」, button text and link, for every suggestion.
        for suggestion in SUGGESTIONS:
            with self.subTest(suggestion=suggestion):
                self.sign_in(f"result {suggestion}")
                submissions = self.answer_all()
                # Last, so the newest answer is HHIE-S without hearing aids, as on home.
                self.suggest(suggestion)
                home = self.next_step()
                self.assertEqual(home[0], suggestion)
                for code, submission in submissions.items():
                    with self.subTest(questionnaire=code):
                        self.assertEqual(self.next_step(self.result(submission)), home)

    def test_the_suggestion_tops_the_tappable_cards_with_the_others_titled_below(self):
        # Spec #297: the box comes first, then a small title over the other cards (the
        # optional SSQ12-TW card on HHIE-S without hearing aids among them).
        self.sign_in("result order")
        submissions = self.answer_all()
        for code, submission in submissions.items():
            with self.subTest(questionnaire=code):
                main = self.result(submission)
                self.assertEqual(main.count(OTHERS_TITLE), 1)
                above, below = main.split(OTHERS_TITLE)
                self.next_step(above)
                self.assertEqual(action_cards(above), [])
                self.assertNotEqual(action_cards(below), [])
        ssq12 = reverse("screening", args=[Questionnaire.objects.get(code="ssq12-tw").pk])
        above, below = self.result(submissions["hhie-s"]).split(OTHERS_TITLE)
        self.assertNotIn(f'href="{ssq12}"', above)
        self.assertIn(f'href="{ssq12}"', below)
        records = f'href="{reverse("my_hearing")}?'
        self.assertLess(below.index(f'href="{ssq12}"'), below.index(records))

    def test_suggesting_the_report_leaves_out_the_report_card(self):
        # Acceptance 9: only 印聽力報告 has a card of its own below; others keep it.
        for suggestion in SUGGESTIONS:
            with self.subTest(suggestion=suggestion):
                self.sign_in(f"report card {suggestion}")
                submissions = self.answer_all()
                self.suggest(suggestion)
                for code, submission in submissions.items():
                    with self.subTest(questionnaire=code):
                        cards = action_cards(self.result(submission))
                        if suggestion == "印聽力報告給醫師看":
                            self.assertNotIn(REPORT_CARD, cards)
                        else:
                            self.assertIn(REPORT_CARD, cards)

    def test_an_old_result_suggests_by_the_user_s_state_now(self):
        # Acceptance 10: the audiogram came after the answer, so no 記錄醫院的聽力圖 now.
        self.sign_in("old result")
        submissions = self.answer_all()
        self.answer()
        before = self.next_step(self.result(submissions["thi"]))
        self.assertEqual(before[0], "記錄醫院的聽力圖")
        self.make((20, 20, 20, 20), (20, 20, 20, 20))
        for code, submission in submissions.items():
            with self.subTest(questionnaire=code):
                self.assertEqual(
                    self.next_step(self.result(submission)),
                    ("分享報告給家人", test_home_next_step.SHARE, "/share", "去分享"),
                )
