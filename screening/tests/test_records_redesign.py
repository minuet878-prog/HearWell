"""#465 (spec #453, the #464 mockup): 我的紀錄, the audiogram pages and the wearing comparison in
the redesign: one score block, one solid button a state, the newest three records with the rest
folded, and the audiogram input without the bottom tab bar. The rules and words are unchanged."""

import datetime
import re
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Audiogram, AudiogramPoint, ReportComparison, Submission
from screening.questionnaires import hhie_s
from screening.tests import test_audiogram
from screening.tests.helpers import consented_user, submission_with_answers

TAIPEI = timezone.get_fixed_timezone(8 * 60)
SOLID = re.compile(r'class="btn btn-primary\b[^"]*"[^>]*>([^<]*)<')
FOLD = re.compile(r'<details class="result-details[^"]*"[^>]*>(.*?)</details>', re.S)


def text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def solid_buttons(main):
    return [label.strip() for label in SOLID.findall(main)]


def fold_titled(main, title):
    """The <details> list-row fold whose summary title is `title`, or None."""
    for fold in FOLD.findall(main):
        summary = fold[: fold.index("</summary>")]
        if f'<span class="link-card-title">{title}</span>' in summary:
            return fold
    return None


class Records(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())

    def setUp(self):
        self.user = consented_user(username="records_user")
        self.client.force_login(self.user)

    def hhie_s(self, scores, day, wearing=False):
        submission = submission_with_answers(
            self.user, hhie_s.CODE, scores, wearing_hearing_aid=wearing
        )
        moment = datetime.datetime(*day, 10, 0, tzinfo=TAIPEI)
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def main(self, url, **params):
        content = self.client.get(url, params).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def records(self):
        return self.main(reverse("my_hearing"), questionnaire=hhie_s.CODE)


class MyRecordsTests(Records):
    def test_one_score_block_says_the_latest_and_the_one_before(self):
        # 1A: the 「和上一次比」 and 「最近一次」 boxes are one block in the level's colour, their
        # words as they were.
        self.hhie_s([4, 4, 4, 4, 2, 0, 0, 0, 0, 0], (2026, 5, 20))  # 18
        self.hhie_s([4, 4, 4, 2, 0, 0, 0, 0, 0, 0], (2026, 11, 12))  # 14
        main = self.records()
        block = re.search(
            r'<div class="result-banner result-banner-([a-z_]+) records-score">'
            r"(.*?)</div>\s*</div>",
            main,
            re.S,
        )
        self.assertEqual(block.group(1), "mild_to_moderate")
        self.assertEqual(
            text(block.group(2)),
            "最近一次（2026/11/12，沒戴助聽器） 14 分 輕度到中度影響 "
            "比上一次少 4 分（分數越低越好） 上一次（2026/05/20）：18 分",
        )
        self.assertNotIn("和上一次比", main)
        self.assertNotIn("trend-summary", main)
        self.assertEqual(main.count("records-score"), 1)

    def test_a_first_record_keeps_the_chart_line_in_the_block(self):
        self.hhie_s([4, 4, 4, 2, 0, 0, 0, 0, 0, 0], (2026, 11, 12))
        block = re.search(r'records-score">(.*?)</div>\s*</div>', self.records(), re.S)
        self.assertEqual(
            text(block.group(1)),
            "最近一次（2026/11/12，沒戴助聽器） 14 分 輕度到中度影響 "
            "再做一次篩檢，就能看到分數的變化。",
        )

    def test_the_report_is_the_only_solid_button_and_share_is_a_row(self):
        self.hhie_s([0] * 10, (2026, 11, 12))
        main = self.records()
        self.assertEqual(solid_buttons(main), ["看／印聽力報告"])
        report = reverse("health_report")
        self.assertRegex(main, rf'class="btn btn-primary[^"]*" href="{report}">看／印聽力報告')
        self.assertNotIn("要給醫師或家人看？", main)
        self.assertIn('<span class="link-card-title">傳給家人看</span>', main)

    def test_a_due_retest_takes_the_solid_button_and_the_report_becomes_a_row(self):
        self.hhie_s([0] * 10, (2025, 1, 2))
        main = self.records()
        self.assertEqual(solid_buttons(main), ["再做一次（大約 3 分鐘）"])
        self.assertIn(f'href="{reverse("health_report")}">', main[main.index("records-score") :])
        self.assertIn('<span class="link-card-title">看／印聽力報告</span>', main)

    def test_the_wearing_comparison_folds_under_its_summary(self):
        unaided = self.hhie_s([4, 4, 4, 4, 2, 0, 0, 0, 0, 0], (2026, 5, 20))  # 18
        aided = self.hhie_s([4, 4, 4, 0, 0, 0, 0, 0, 0, 0], (2026, 8, 15), wearing=True)  # 12
        ReportComparison.objects.create(
            user=self.user, questionnaire=unaided.questionnaire, unaided=unaided, aided=aided
        )
        main = self.records()
        fold = fold_titled(main, "配戴狀態比較")
        self.assertIn("沒戴 18 分、有戴 12 分，少了 6 分", fold[: fold.index("</summary>")])
        self.assertIn("報告保留的兩筆：", fold)
        compare = reverse("hhi_comparison", args=[unaided.questionnaire_id])
        self.assertIn(
            f'class="btn btn-outline-primary btn-lg" href="{compare}">比較戴與不戴助聽器</a>', fold
        )
        self.assertNotIn('<h3 id="difference-title"', main)

    def test_the_newest_three_show_and_the_rest_fold_with_their_dates(self):
        # 8A: 「看以前的 N 筆」 (draft), the dates of the folded ones under it.
        days = [(2024, 1, 10), (2024, 6, 1), (2025, 11, 8), (2026, 5, 20), (2026, 8, 15)]
        for day in days:
            self.hhie_s([0] * 10, day)
        main = self.records()
        fold = fold_titled(main, "看以前的 2 筆")
        summary = text(fold[: fold.index("</summary>")])
        self.assertEqual(summary, "看以前的 2 筆 2024/01/10 到 2024/06/01")
        rows = main[main.index('id="records-title"') :]
        shown = rows[: rows.index('<details class="result-details"')]
        self.assertEqual(
            re.findall(r"<strong>(\d{4}/\d\d/\d\d)</strong>", shown),
            ["2026/08/15", "2026/05/20", "2025/11/08"],
        )
        self.assertEqual(
            re.findall(r"<strong>(\d{4}/\d\d/\d\d)</strong>", fold), ["2024/06/01", "2024/01/10"]
        )

    def test_three_records_or_fewer_fold_nothing(self):
        for day in [(2026, 1, 2), (2026, 5, 20), (2026, 8, 15)]:
            self.hhie_s([0] * 10, day)
        self.assertNotIn("看以前的", self.records())


class AudiogramListTests(Records):
    def make(self, tested_on):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=tested_on)
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, **p)
            for p in test_audiogram._four(test_audiogram._air, "right", (30, 30, 30, 30))
        )

    def test_add_is_the_only_solid_button(self):
        self.make(date(2026, 10, 3))
        main = self.main(reverse("audiogram_list"))
        self.assertEqual(solid_buttons(main), ["記錄聽力圖"])

    def test_the_newest_three_show_and_the_rest_fold_with_their_dates(self):
        # 8E: 「看以前的 N 張」 (draft).
        for day in [(2023, 9, 14), (2024, 3, 20), (2024, 10, 5), (2025, 4, 12), (2025, 10, 20)]:
            self.make(date(*day))
        main = self.main(reverse("audiogram_list"))
        fold = fold_titled(main, "看以前的 2 張")
        self.assertEqual(
            text(fold[: fold.index("</summary>")]), "看以前的 2 張 2023/09/14 到 2024/03/20"
        )
        self.assertEqual(fold.count("audiogram-card"), 2)
        self.assertEqual(main.count("audiogram-card") - fold.count("audiogram-card"), 3)

    def test_three_audiograms_fold_nothing(self):
        for day in [(2024, 3, 20), (2025, 4, 12), (2025, 10, 20)]:
            self.make(date(*day))
        self.assertNotIn("看以前的", self.main(reverse("audiogram_list")))


class Audiograms(Records):
    def make(self, right, left):
        points = [
            *test_audiogram._four(test_audiogram._air, "right", right),
            *test_audiogram._four(test_audiogram._air, "left", left),
        ]
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 3))
        AudiogramPoint.objects.bulk_create(AudiogramPoint(audiogram=audiogram, **p) for p in points)
        return audiogram


class AudiogramDetailTests(Audiograms):
    def detail(self, audiogram):
        return self.main(reverse("audiogram_detail", args=[audiogram.id]))

    def test_each_ear_is_a_block_in_its_degree_colour(self):
        main = self.detail(self.make((40, 40, 45, 40), (30, 35, 35, 35)))
        ears = re.findall(
            r'<div class="result-banner result-banner-([a-z_]+) audiogram-ear-block"[^>]*>'
            r"(.*?)</div>",
            main,
            re.S,
        )
        self.assertEqual(
            [(colour, text(block)) for colour, block in ears],
            [
                ("mild_to_moderate", "右耳 中度 四頻平均： 41.25 dB HL"),
                ("mild_to_moderate", "左耳 輕度 四頻平均： 33.75 dB HL"),
            ],
        )

    def test_the_guide_is_the_solid_button_when_an_ear_is_over_25(self):
        main = self.detail(self.make((40, 40, 45, 40), (30, 35, 35, 35)))
        self.assertEqual(solid_buttons(main), ["看助聽器選配與補助"])
        self.assertIn('<span class="link-card-title">看語言香蕉區</span>', main)

    def test_the_speech_banana_is_the_solid_button_without_the_guide(self):
        # Both ears within 25 dB: recommends_fitting_assessment is False, no guide.
        main = self.detail(self.make((20, 20, 20, 20), (15, 15, 15, 15)))
        self.assertEqual(solid_buttons(main), ["看語言香蕉區"])
        self.assertNotIn("看助聽器選配與補助", main)
        self.assertNotIn('<span class="link-card-title">看語言香蕉區</span>', main)

    def test_type_no_response_and_reading_the_chart_wait_in_the_full_explanation(self):
        audiogram = self.make((40, 40, 45, 40), (30, 35, 35, 35))
        AudiogramPoint.objects.filter(audiogram=audiogram, ear="left", frequency=4000).update(
            no_response=True
        )
        main = self.detail(audiogram)
        fold = fold_titled(main, "看完整說明")
        for words in (
            "類型：需要骨導資料才能判斷",
            "含無反應的頻率，實際聽力可能更差",
            "看懂這張圖",
            "dB 數字越大，代表要越大聲才聽得到。",
        ):
            self.assertIn(words, fold)
            self.assertEqual(main.count(words), fold.count(words))
        self.assertIsNotNone(fold_titled(main, "標記的數值"))

    def test_edit_delete_and_back_are_text_links(self):
        audiogram = self.make((40, 40, 45, 40), (30, 35, 35, 35))
        main = self.detail(audiogram)
        links = re.search(r'<p class="quiet-links">(.*?)</p>', main, re.S).group(1)
        self.assertEqual(text(links), "修改這張 刪除這張 回聽力圖清單")
        self.assertNotIn("btn btn-outline-primary", links)


class SpeechBananaTests(Audiograms):
    def banana(self, audiogram):
        return self.main(reverse("audiogram_speech_banana", args=[audiogram.id]))

    def test_the_guide_is_a_pale_blue_card_with_the_one_solid_button(self):
        main = self.banana(self.make((40, 40, 45, 40), (30, 35, 35, 35)))
        card = re.search(r'<div class="result-next">(.*?)</div>', main, re.S).group(1)
        self.assertEqual(text(card), "依您的聽力圖整理下一步 看助聽器選配與補助")
        self.assertEqual(solid_buttons(main), ["看助聽器選配與補助"])

    def test_no_guide_no_solid_button(self):
        main = self.banana(self.make((20, 20, 20, 20), (15, 15, 15, 15)))
        self.assertEqual(solid_buttons(main), [])

    def test_reading_the_chart_folds_and_the_source_stays_out(self):
        main = self.banana(self.make((40, 40, 45, 40), (30, 35, 35, 35)))
        fold = fold_titled(main, "看懂這張圖")
        self.assertIn("這張圖沒有列火警和煙霧警報。", fold)
        self.assertNotIn("語言香蕉區與注音位置參考", fold)
        self.assertIn("語言香蕉區與注音位置參考", main)

    def test_back_is_a_text_link(self):
        audiogram = self.make((40, 40, 45, 40), (30, 35, 35, 35))
        main = self.banana(audiogram)
        back = reverse("audiogram_detail", args=[audiogram.id])
        self.assertIn(f'<p class="quiet-links"><a href="{back}">回這張聽力圖</a></p>', main)


class AudiogramInputTabBarTests(Records):
    """D5: no bottom tab bar while marking an audiogram; the way out is 不新增了 / 不修改了."""

    def nav(self, url):
        content = self.client.get(url).content.decode()
        return re.search(r'<nav aria-label="主要導覽" class="site-nav([^"]*)"', content).group(1)

    def test_the_input_and_edit_pages_hide_it_on_phones(self):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 3))
        for url in (reverse("audiogram_new"), reverse("audiogram_edit", args=[audiogram.id])):
            with self.subTest(url=url):
                self.assertEqual(self.nav(url), " site-nav-tucked")

    def test_the_other_record_pages_keep_it(self):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 3))
        for url in (
            reverse("audiogram_list"),
            reverse("audiogram_detail", args=[audiogram.id]),
            f"{reverse('my_hearing')}?view=questionnaires",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.nav(url), "")


class WearingComparisonTests(Records):
    """Each state of 比較戴與不戴助聽器 has one solid button at most."""

    def setUp(self):
        super().setUp()
        self.unaided_old = self.hhie_s([4, 4, 4, 4, 2, 0, 0, 0, 0, 0], (2026, 5, 20))  # 18
        self.aided = self.hhie_s([4, 4, 4, 0, 0, 0, 0, 0, 0, 0], (2026, 8, 15), wearing=True)
        self.unaided = self.hhie_s([4, 4, 4, 2, 0, 0, 0, 0, 0, 0], (2026, 11, 12))  # 14
        self.url = reverse("hhi_comparison", args=[self.unaided.questionnaire_id])

    def test_opened_it_is_the_form_with_its_solid_button(self):
        main = self.main(self.url)
        self.assertEqual(solid_buttons(main), ["查看比較"])
        self.assertIsNone(fold_titled(main, "換別的兩筆"))
        back = f"{reverse('my_hearing')}?questionnaire={hhie_s.CODE}"
        self.assertIn(f'<p class="quiet-links mt-6"><a href="{back}">回我的紀錄</a></p>', main)

    def test_looking_at_a_new_pair_puts_it_first_and_folds_the_rest(self):
        ReportComparison.objects.create(
            user=self.user,
            questionnaire=self.unaided.questionnaire,
            unaided=self.unaided_old,
            aided=self.aided,
        )
        main = self.main(self.url, unaided=self.unaided.pk, aided=self.aided.pk, action="preview")
        self.assertEqual(solid_buttons(main), ["改放這一組到報告"])
        self.assertLess(main.index("目前查看的兩筆"), main.index("<details"))
        saved = fold_titled(main, "聽力報告裡的組合")
        self.assertIn("沒戴 18 分、有戴 12 分，少了 6 分", saved[: saved.index("</summary>")])
        self.assertIn("從報告移除", saved)
        form = fold_titled(main, "換別的兩筆")
        self.assertIn(
            '<button class="btn btn-outline-primary btn-lg" name="action" value="preview">'
            "查看比較</button>",
            form,
        )

    def test_opened_with_a_pair_in_the_report_shows_it_first(self):
        ReportComparison.objects.create(
            user=self.user,
            questionnaire=self.unaided.questionnaire,
            unaided=self.unaided,
            aided=self.aided,
        )
        main = self.main(self.url)
        self.assertEqual(solid_buttons(main), [])
        self.assertLess(main.index("這一組已經在聽力報告裡"), main.index("<details"))
        self.assertIn("從報告移除", main[: main.index("<details")])
        self.assertIsNotNone(fold_titled(main, "換別的兩筆"))

    def test_looking_at_the_saved_pair_has_no_solid_button(self):
        ReportComparison.objects.create(
            user=self.user,
            questionnaire=self.unaided.questionnaire,
            unaided=self.unaided,
            aided=self.aided,
        )
        main = self.main(self.url, unaided=self.unaided.pk, aided=self.aided.pk, action="preview")
        self.assertEqual(solid_buttons(main), [])
        self.assertIn("這一組已經在聽力報告裡", main)
        self.assertIsNotNone(fold_titled(main, "換別的兩筆"))


class AudiogramCompareTests(Audiograms):
    """The #464 mockup 6: the summary on the page, its notes folded, the way back a text link."""

    def test_the_notes_fold_and_the_way_back_is_a_text_link(self):
        old = self.make((30, 30, 30, 35), (30, 30, 30, 30))
        new = self.make((35, 35, 35, 40), (30, 30, 30, 30))
        main = self.main(reverse("audiogram_compare"), a=new.id, b=old.id)
        self.assertIn(
            "機器、地點、耳機不同，數字本來就會差幾分貝。", fold_titled(main, "看懂這張比較")
        )
        self.assertIn('data-section="pta"', fold_titled(main, "看每個頻率的數字"))
        self.assertIn(
            f'<p class="quiet-links"><a href="{reverse("audiogram_list")}">回聽力圖清單</a></p>',
            main,
        )
        self.assertNotIn('class="tip-box"', main)
        # Each folded 換一張 row keeps its own 比較, as before: the page shows none until one opens.
        self.assertEqual(solid_buttons(main), ["比較", "比較"])
