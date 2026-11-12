"""#304 (spec #297, ADR 0023): every result page shows the 建議您下一步; since #455 (ADR 0044)
it is the 照顧旅程's 現在這一步, as on the home page (#459). #461 (the #460 mockup R1): the card
has its title and button, no 「因為」, and sharing and printing are list rows below it."""

import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.care_journey import care_journey
from screening.models import Answer, NormGroup, Questionnaire, ReportShare, Submission
from screening.questionnaires import hhie_s
from screening.tests import test_guide_summary, test_result_pages
from screening.tests.helpers import consented_user

SUGGESTIONS = (
    "記錄醫院的聽力圖",
    "修改這張聽力圖",
    "了解助聽器選配與補助",
    "分享報告給家人",
    "印聽力報告給醫師看",
)
REPORT_ROW = (reverse("health_report"), "印聽力報告給醫師看")
SHARE_ROW = (reverse("share_report"), "分享給家人")
NEXT_STEP = re.compile(
    r'<div class="result-next">\s*<p class="result-next-label">建議您下一步</p>\s*'
    r'<h2 class="result-next-title">([^<]*)</h2>\s*'
    r'<a class="btn btn-primary btn-lg w-full" href="([^"]*)">([^<]*)</a>\s*</div>',
    re.S,
)
ROW = re.compile(
    r'<a class="link-card action-card" href="([^"]*)">.*?<span class="link-card-title">([^<]*)',
    re.S,
)


class ResultNextStepTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        # What answer() needs: HHIE-S and its questions.
        cls.hhie_s = Questionnaire.objects.get(code=hhie_s.CODE)
        cls.questions = list(cls.hhie_s.questions.all())

    make = test_guide_summary.GuideSummaryTests.make

    def answer(self):
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.hhie_s, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=0) for question in self.questions
        )

    def suggest(self, suggestion):
        """Records that make the 建議您下一步 `suggestion` (a card title, as #261 named them)."""
        self.answer()
        if suggestion == "記錄醫院的聽力圖":
            return
        if suggestion == "修改這張聽力圖":
            audiogram = self.make((20, 20, 20, 20), (20, 20, 20, 20))
            audiogram.points.filter(ear="left", frequency=4000).delete()
        elif suggestion == "了解助聽器選配與補助":
            self.make(test_guide_summary.PTA_55, test_guide_summary.PTA_55)
        else:
            self.make((20, 20, 20, 20), (20, 20, 20, 20))
            if suggestion == "印聽力報告給醫師看":
                ReportShare.objects.create(user=self.user, revoked_at=timezone.now())

    def next_step(self, main):
        """(title, button href, button text) of the page's one 建議您下一步 card."""
        found = NEXT_STEP.findall(main)
        self.assertEqual(len(found), 1, "not one 建議您下一步 card")
        return found[0]

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

    def expected(self, suggestion):
        """(title, button href, button text) a result page suggests now."""
        if suggestion == "記錄醫院的聽力圖":
            # Step 2, the route's 記錄聽力圖 stop and its button.
            return ("記錄聽力圖", "/audiograms/new", "記錄醫院的聽力圖")
        if suggestion == "修改這張聽力圖":
            edit = reverse("audiogram_edit", args=[self.user.audiograms.get().pk])
            return ("記錄聽力圖", edit, "修改這張聽力圖")
        if suggestion == "了解助聽器選配與補助":
            # Step 3 at 去找聽力師之前, the 目前這一站, with the route's button.
            return ("去找聽力師之前", "/guide/before-you-go", "去之前要準備什麼")
        # Within the normal range step 5 counts down without a button (spec #453 acceptance 22).
        if suggestion == "分享報告給家人":
            return ("分享報告給家人", "/share", "去分享")
        return ("印聽力報告給醫師看", "/report", "去印報告")

    def test_every_result_page_suggests_the_care_journey_s_current_step(self):
        # Spec #453 acceptance 21-22 (#455): title, button text and link, for every
        # questionnaire's result page, the journey's card where it has a button.
        for suggestion in SUGGESTIONS:
            with self.subTest(suggestion=suggestion):
                self.sign_in(f"result {suggestion}")
                submissions = self.answer_all()
                # Last, so the newest answer is HHIE-S without hearing aids.
                self.suggest(suggestion)
                expected = self.expected(suggestion)
                card = care_journey(self.user, timezone.localdate()).card
                if card.button is not None:
                    self.assertEqual((card.title, card.button[1]), expected[:2])
                for code, submission in submissions.items():
                    with self.subTest(questionnaire=code):
                        self.assertEqual(self.next_step(self.result(submission)), expected)

    def test_the_suggestion_comes_before_the_list_rows(self):
        # R1: the card, then 看完整說明, sharing and printing, then the page's extras (the optional
        # SSQ12-TW row on HHIE-S without hearing aids among them).
        self.sign_in("result order")
        submissions = self.answer_all()
        for code, submission in submissions.items():
            with self.subTest(questionnaire=code):
                main = self.result(submission)
                above, below = main.split('<div class="result-list">')
                self.next_step(above)
                self.assertEqual(ROW.findall(above), [])
                self.assertNotEqual(ROW.findall(below), [])
        ssq12 = reverse("screening", args=[Questionnaire.objects.get(code="ssq12-tw").pk])
        records = f"{reverse('my_hearing')}?questionnaire=hhie-s"
        rows = [href for href, _ in ROW.findall(self.result(submissions["hhie-s"]))]
        self.assertEqual(rows, [SHARE_ROW[0], REPORT_ROW[0], records, ssq12])

    def test_the_optional_ssq12_card_is_an_action_card_like_the_others(self):
        # #363 (spec #354): an icon and a second line, and 「（SSQ12-TW）」 held together so a
        # phone does not break the name at its hyphen (the e2e test measures it).
        self.sign_in("result ssq12 card")
        submissions = self.answer_all()
        ssq12 = reverse("screening", args=[Questionnaire.objects.get(code="ssq12-tw").pk])
        card = re.search(
            rf'<a class="link-card action-card" href="{ssq12}">\s*'
            r'<span class="action-card-icon" aria-hidden="true" data-icon="clipboard">'
            r"<svg .*?</svg></span>\s*"
            r'<span class="link-card-body">\s*<span class="link-card-title">(.*?)</span>\s*'
            r"<span>([^<]*)</span>",
            self.result(submissions["hhie-s"]),
            re.S,
        )
        self.assertIsNotNone(card)
        self.assertEqual(
            card.group(1), '了解日常聆聽能力<span class="inline-block">（SSQ12-TW）</span>'
        )
        self.assertEqual(card.group(2), "選填，12 題")

    def test_suggesting_sharing_or_the_report_leaves_out_its_row(self):
        # Acceptance 9: only the row the card suggests leaves the list; others keep it.
        for suggestion in SUGGESTIONS:
            with self.subTest(suggestion=suggestion):
                self.sign_in(f"report card {suggestion}")
                submissions = self.answer_all()
                self.suggest(suggestion)
                for code, submission in submissions.items():
                    with self.subTest(questionnaire=code):
                        rows = ROW.findall(self.result(submission))
                        self.assertEqual(REPORT_ROW in rows, suggestion != "印聽力報告給醫師看")
                        self.assertEqual(SHARE_ROW in rows, suggestion != "分享報告給家人")

    def test_an_old_result_suggests_by_the_user_s_state_now(self):
        # Acceptance 10: the audiogram came after the answer, so no 記錄聽力圖 now.
        self.sign_in("old result")
        submissions = self.answer_all()
        self.answer()
        before = self.next_step(self.result(submissions["thi"]))
        self.assertEqual(before, self.expected("記錄醫院的聽力圖"))
        self.make((20, 20, 20, 20), (20, 20, 20, 20))
        for code, submission in submissions.items():
            with self.subTest(questionnaire=code):
                self.assertEqual(
                    self.next_step(self.result(submission)),
                    ("分享報告給家人", "/share", "去分享"),
                )
