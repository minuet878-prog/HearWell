"""#461 (spec #453, the #460 mockup R1): what a result page's first screen shows and what waits
behind 看完整說明."""

import datetime
import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import NormGroup, Questionnaire, ReportShare, Submission
from screening.questionnaires import hhie_s
from screening.scoring import get_advice
from screening.tests import test_guide_summary, test_result_pages
from screening.tests.helpers import consented_user, submission_with_answers

TAIPEI = timezone.get_fixed_timezone(8 * 60)
SOLID = re.compile(r'class="btn btn-primary\b')
BANNER = re.compile(r'<div class="result-banner result-banner-([a-z_]+)">(.*?)</div>\s*<p', re.S)
DETAILS = re.compile(
    r'<details class="result-details"([^>]*)>(.*?)</details>\s*(?=<a|</div>)', re.S
)
ROW = re.compile(
    r'<a class="link-card action-card" href="([^"]*)">.*?'
    r'<span class="link-card-title">(.*?)</span>',
    re.S,
)
SHARE_ROW = (reverse("share_report"), "分享給家人")
PRINT_ROW = (reverse("health_report"), "印聽力報告給醫師看")


def details(main):
    """The 看完整說明 fold's opening tag and what is in it: up to the first list row after it."""
    start = main.index('<details class="result-details"')
    return main[start : main.index('<a class="link-card action-card"', start)]


def text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


class GradedResultPageTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())

    make = test_guide_summary.GuideSummaryTests.make

    def setUp(self):
        self.user = consented_user(username="redesign_user")
        self.client.force_login(self.user)

    def hhie_s(self, scores, day):
        submission = submission_with_answers(
            self.user, hhie_s.CODE, scores, wearing_hearing_aid=False
        )
        moment = datetime.datetime(*day, 10, 0, tzinfo=TAIPEI)
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def main(self, submission):
        content = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def test_the_level_block_has_the_score_the_level_and_the_line_against_last_time(self):
        # Acceptance 23: in the level's colour (L1), with no verdict.
        self.hhie_s([4, 4, 4, 4, 2, 0, 0, 0, 0, 0], (2026, 3, 26))  # 18
        latest = self.hhie_s([4, 4, 4, 2, 0, 0, 0, 0, 0, 0], (2026, 11, 12))  # 14
        main = self.main(latest)
        colour, banner = BANNER.search(main).groups()
        self.assertEqual(colour, "mild_to_moderate")
        self.assertEqual(
            text(banner),
            "總分 14 分（滿分 40） 輕度到中度影響 上次 2026/03/26 是 18 分，這次少 4 分",
        )
        for verdict in ("進步", "退步", "改善", "變好", "變差"):
            self.assertNotIn(verdict, main)

    def test_a_changed_level_is_written_in_the_block(self):
        # Acceptance 24.
        self.hhie_s([4, 4, 2, 0, 0, 0, 0, 0, 0, 0], (2026, 3, 26))  # 10
        latest = self.hhie_s([4, 2, 0, 0, 0, 0, 0, 0, 0, 0], (2026, 11, 12))  # 6
        banner = text(BANNER.search(self.main(latest)).group(2))
        change = "分級從「輕度到中度影響」變成「無／極輕微影響」"
        self.assertTrue(banner.endswith(f"這次少 4 分 {change}"), banner)

    def test_the_first_record_has_no_line_against_last_time(self):
        # Acceptance 25.
        main = self.main(self.hhie_s([2] * 10, (2026, 11, 12)))
        self.assertNotIn("result-since-last", main)
        self.assertNotIn("上次", text(BANNER.search(main).group(2)))

    def test_an_old_record_is_compared_with_the_one_before_it(self):
        # Acceptance 26.
        self.hhie_s([4, 4, 4, 4, 4, 0, 0, 0, 0, 0], (2026, 1, 5))  # 20
        old = self.hhie_s([4, 4, 4, 4, 0, 0, 0, 0, 0, 0], (2026, 3, 26))  # 16
        self.hhie_s([4, 0, 0, 0, 0, 0, 0, 0, 0, 0], (2026, 11, 12))  # 4
        self.assertIn("上次 2026/01/05 是 20 分，這次少 4 分", self.main(old))

    def test_one_sentence_follows_the_block_then_the_suggestion_then_the_rows(self):
        # R1: the reviewed step 1 word for word, the 建議下一步 card, then the list rows.
        main = self.main(self.hhie_s([4, 4, 2, 2, 0, 0, 0, 0, 0, 0], (2026, 11, 12)))  # 12
        steps = hhie_s.NEXT_STEPS["mild_to_moderate"]
        after_banner = main[BANNER.search(main).end() - 2 :]
        self.assertTrue(
            after_banner.startswith(f'<p class="result-one-line">{steps[0]["text"]}</p>'),
            after_banner[:200],
        )
        order = [
            steps[0]["text"],
            '<p class="result-next-label">建議您下一步</p>',
            '<details class="result-details">',
            "<span>看完整說明</span>",
            ">分享給家人<",
            ">印聽力報告給醫師看<",
        ]
        positions = [main.index(piece) for piece in order]
        self.assertEqual(positions, sorted(positions))

    def test_the_full_explanation_is_folded_with_every_word_kept(self):
        # R1: the score bar, steps 2-3, the full advice, the subscores and the answers.
        main = self.main(self.hhie_s([4, 4, 2, 2, 0, 0, 0, 0, 0, 0], (2026, 11, 12)))
        fold = details(main)
        self.assertNotIn("open", fold[: fold.index(">")])
        steps = hhie_s.NEXT_STEPS["mild_to_moderate"]
        for piece in (
            '<div class="score-bar"',
            steps[1]["text"],
            steps[2]["text"],
            "看助聽器選配指引",
            get_advice("mild_to_moderate", hhie_s.CODE),
            "情緒分數：",
            "助聽器：沒戴",
        ):
            with self.subTest(piece=piece):
                self.assertIn(piece, fold)
        self.assertNotIn(steps[0]["text"], fold)
        self.assertEqual(main.count('<div class="score-bar"'), 1)

    def test_step_one_keeps_its_link(self):
        # HHIE-S 顯著影響's step 1 links to the guide: the link stays with its sentence.
        main = self.main(self.hhie_s([4] * 8 + [0, 0], (2026, 11, 12)))  # 32
        step = hhie_s.NEXT_STEPS["severe"][0]
        one_line = main[main.index('<p class="result-one-line">') : main.index("result-next-label")]
        self.assertIn(step["text"], one_line)
        self.assertIn(f'href="{reverse("guide")}">看助聽器選配指引</a>', one_line)

    def test_suggesting_sharing_or_printing_leaves_its_row_out(self):
        # Within the normal range the journey counts down: it suggests sharing, then printing
        # once a link was ever made (spec #453 acceptance 22).
        submission = self.hhie_s([0] * 10, (2026, 11, 12))
        self.make((20, 20, 20, 20), (20, 20, 20, 20))
        with self.subTest(suggested="share"):
            rows = ROW.findall(self.main(submission))
            self.assertNotIn(SHARE_ROW, rows)
            self.assertIn(PRINT_ROW, rows)
        ReportShare.objects.create(user=self.user, revoked_at=timezone.now())
        with self.subTest(suggested="print"):
            rows = ROW.findall(self.main(submission))
            self.assertNotIn(PRINT_ROW, rows)
            self.assertIn(SHARE_ROW, rows)


class EveryResultPageTests(TestCase):
    fixtures = ("questions_fixture.json",)
    # The six records of test_result_pages, one per questionnaire, made for this class.
    setUpTestData = classmethod(test_result_pages.ResultPagesTests.setUpTestData.__func__)
    setUp = test_result_pages.ResultPagesTests.setUp
    _main = test_result_pages.ResultPagesTests._main

    def test_every_result_page_has_one_solid_button_at_most(self):
        # ADR 0041: the 建議下一步 card's.
        for code in test_result_pages.QUESTIONNAIRES:
            with self.subTest(code=code):
                main = self._main(code)
                self.assertEqual(len(SOLID.findall(main)), 1)
                self.assertLess(main.index("result-next-label"), SOLID.search(main).start())

    def test_every_result_page_folds_its_explanation_then_lists_sharing_and_printing(self):
        for code in test_result_pages.QUESTIONNAIRES:
            with self.subTest(code=code):
                main = self._main(code)
                self.assertEqual(main.count('<details class="result-details">'), 1)
                rows = ROW.findall(main)
                self.assertEqual(rows[:2], [SHARE_ROW, PRINT_ROW])

    def test_pages_that_are_not_graded_have_no_level_block_and_no_comparison(self):
        # Acceptance 25; SSQ12-TW's 「比上一次」 and 0-10 bar went with it (#461).
        earlier = Submission.objects.filter(user=self.user).order_by("created_at")
        Submission.objects.filter(pk__in=earlier.values("pk")).update(
            created_at=timezone.now() - timezone.timedelta(days=30)
        )
        for code in ("ssq12-tw", "ioi-ha", "sadl"):
            with self.subTest(code=code):
                first = self.submissions[code]
                answers = first.answers.order_by("question__question_number")
                again = submission_with_answers(
                    self.user,
                    code,
                    [answer.score for answer in answers],
                    wearing_hearing_aid=first.wearing_hearing_aid,
                    norm_group=first.norm_group,
                    norm_basis=first.norm_basis,
                )
                response = self.client.get(reverse("result", args=[again.pk]))
                main = response.content.decode()
                self.assertNotIn("result-banner", main)
                self.assertNotIn("上次", main)
                self.assertNotIn("比上一次", main)
                self.assertNotIn("ssq-bar", main)
                self.assertIn('<div class="result-summary">', main)

    def test_the_summary_of_a_page_that_is_not_graded(self):
        # The pale grey block (no level colour, ADR 0007) and, under it, its one sentence.
        expected = {
            "ssq12-tw": ("整體平均 6.0 分（滿分 10）", "分數越高，代表您回報的聆聽能力越好。"),
            "sadl": (
                "整體滿意度：4.0 分（滿分 7）",
                Questionnaire.objects.get(code="sadl").definition.result_note,
            ),
            "ioi-ha": ("7 項中，有 0 項比一般使用者低", None),
        }
        for code, (summary, sentence) in expected.items():
            with self.subTest(code=code):
                main = self._main(code)
                block = re.search(r'<div class="result-summary">(.*?)</div>', main, re.S)
                self.assertEqual(text(block.group(1)), summary)
                if sentence:
                    self.assertIn(f'<p class="result-one-line">{sentence}</p>', main)


class IoiHaUngroupedTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())

    def test_without_a_norm_group_the_summary_says_what_it_needs(self):
        user = consented_user(username="ungrouped_user")
        self.client.force_login(user)
        submission = submission_with_answers(
            user, "ioi-ha", [3] * 7, wearing_hearing_aid=True, norm_group=NormGroup.UNGROUPED
        )
        main = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        block = re.search(r'<div class="result-summary">(.*?)</div>', main, re.S)
        self.assertEqual(
            text(block.group(1)),
            "需要一筆完整有效的未配戴 HHIA-S／HHIE-S 紀錄，才能跟常模比較。",
        )
