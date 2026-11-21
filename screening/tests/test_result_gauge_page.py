"""#750 (spec #741 acceptance 48, user stories 42-43, page grill P16, canvas ProResult): the result
page's green line, title, semicircle gauge with the score and the short level, the two bars against
last time, the blue 建議下一步 card and the rows under it, then what each page had besides."""

import datetime
import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Submission
from screening.questionnaires import hhie_s, thi
from screening.tests.helpers import consented_user, submission_with_answers

TAIPEI = timezone.get_fixed_timezone(8 * 60)
# The score block in its level's colour, up to the 建議下一步 card under it.
BLOCK = re.compile(
    r'<div class="result-banner result-banner-([a-z_]+)">(.*?)<section class="hero-card"', re.S
)
# The gauge's arcs: each level's, the latest's drawn once in view (play-once-gauge).
ARC = re.compile(r'<path class="gauge-arc gauge-arc-([a-z_]+)([^"]*)" d="M[^"]+"')
BAR = re.compile(r'<span class="result-bar-fill[^"]*" style="width: ([\d.]+)%"></span>')
# A row's title: a link's, or a fold's after its icon.
ROW_TITLE = re.compile(
    r'(?:<span class="link-card-title[^"]*">|<summary>\s*<span class="action-card-icon".*?</svg>'
    r"</span>\s*<span>)([^<]*)",
    re.S,
)


def text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


class ResultGaugePageTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())

    def setUp(self):
        self.user = consented_user(username="gauge_page_user")
        self.client.force_login(self.user)

    def record(self, code, scores, day):
        submission = submission_with_answers(self.user, code, scores, wearing_hearing_aid=False)
        moment = datetime.datetime(*day, 10, 0, tzinfo=TAIPEI)
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def main(self, submission):
        content = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def test_the_top_says_it_is_saved_and_titles_the_page_as_the_canvas(self):
        main = self.main(self.record(hhie_s.CODE, [4, 4, 2, 2] + [0] * 6, (2026, 11, 12)))
        saved = main.index('<p class="result-saved" role="status">')
        self.assertIn("做完了，已存到我的紀錄。", main[saved : main.index("</p>", saved)])
        self.assertLess(saved, main.index('class="bird-dialogue"'))
        self.assertIn('<h1 class="bird-title">看看聽力對生活的影響</h1>', main)

    def test_the_gauge_draws_every_level_and_the_latest_once_in_view(self):
        main = self.main(self.record(hhie_s.CODE, [4, 4, 2, 2] + [0] * 6, (2026, 11, 12)))  # 12
        colour, block = BLOCK.search(main).groups()
        self.assertEqual(colour, "mild_to_moderate")
        self.assertEqual(
            ARC.findall(block),
            [
                ("normal", ""),
                ("mild_to_moderate", " gauge-arc-current play-once-gauge"),
                ("severe", ""),
            ],
        )
        self.assertIn('pathLength="1"', block)
        # The ends of the scale, and the score counting up beside it.
        self.assertIn('<span class="gauge-end">0</span><span class="gauge-end">40</span>', block)
        self.assertIn('總分 <span class="gauge-score" data-count-up>12</span> 分', block)
        self.assertIn('<p class="result-level-short" aria-hidden="true">輕到中度</p>', block)
        # Read in its place: the score out of the full score, then the level.
        self.assertIn(
            '<p id="result-score" class="visually-hidden">'
            '總分 <span class="result-number" data-count-up>12</span> 分（滿分 40）</p>',
            block,
        )

    def test_five_levels_draw_five_arcs(self):
        main = self.main(self.record(thi.CODE, [2] * 21 + [0] * 4, (2026, 11, 12)))  # 42
        self.assertEqual(
            [colour for colour, _ in ARC.findall(BLOCK.search(main).group(2))],
            ["normal", "mild_to_moderate", "mild_to_moderate", "severe", "severe"],
        )

    def test_two_bars_compare_with_last_time(self):
        self.record(hhie_s.CODE, [4, 4, 4, 4, 2] + [0] * 5, (2026, 3, 26))  # 18
        latest = self.record(hhie_s.CODE, [4, 4, 4, 2] + [0] * 6, (2026, 11, 12))  # 14
        block = BLOCK.search(self.main(latest)).group(2)
        # Out of 40: 18 is 45%, 14 is 35%.
        self.assertEqual(BAR.findall(block), ["45.00", "35.00"])
        since = block[block.index('<div class="result-since-last">') :]
        self.assertEqual(
            text(since),
            # The label, the line a screen reader reads, then the bars it skips.
            "比上次少 4 分 上次 2026/03/26 是 18 分 上一次 18 分 這一次 14 分",
        )

    def test_the_first_record_has_no_bars(self):
        main = self.main(self.record(hhie_s.CODE, [2] * 10, (2026, 11, 12)))
        self.assertNotIn("result-bar", main)

    def test_the_blue_card_then_the_rows_then_the_extras(self):
        main = self.main(self.record(hhie_s.CODE, [4, 4, 2, 2] + [0] * 6, (2026, 11, 12)))
        card = main.index('<section class="hero-card"')
        self.assertIsNotNone(BLOCK.search(main))
        self.assertIn("建議您下一步", main[card : main.index("</section>", card)])
        rows = main[main.index('<div class="result-list">') :]
        self.assertEqual(
            ROW_TITLE.findall(rows),
            [
                "看每一題的回答",
                "這個分數怎麼算",
                "印聽力報告",
                "分享給家人",
                "看紀錄與趨勢",
                "了解日常聆聽能力",
            ],
        )
        # The 重測提醒 comes under the rows (P16), the card just above them.
        self.assertLess(main.index('<div class="result-list">'), main.index("result-reminder"))

    def test_the_rows_open_on_the_answers_and_on_how_the_score_is_counted(self):
        main = self.main(self.record(hhie_s.CODE, [4, 4, 2, 2] + [0] * 6, (2026, 11, 12)))
        answers, counted = re.findall(
            r'<details class="result-details">(.*?)</details>', main, re.S
        )[:2]
        self.assertIn("看每一題的回答", answers)
        self.assertIn("助聽器：沒戴", text(answers))
        counted = text(counted)
        self.assertIn("每一題的分數加起來就是總分", counted)
        # The levels by their full names, with their ranges, from the thresholds.
        for line in ("0–8 分：無／極輕微影響", "9–24 分：輕度到中度影響", "25–40 分：顯著影響"):
            self.assertIn(line, counted)
        for step in hhie_s.NEXT_STEPS["mild_to_moderate"]:
            self.assertIn(step["text"], counted)
