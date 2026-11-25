"""#780 (spec #774 acceptance 8-9, ADR 0083): my guide's two 結論標籤 under the bird, and the
audiogram's numbers and formula in a fold under the 章節磚, shut until opened."""

import re
from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Audiogram, AudiogramSource, Submission
from screening.tests import test_guide, test_guide_meters, test_guide_summary
from screening.tests.helpers import consented_user

PTA_55 = test_guide_summary.PTA_55
PTA_60 = test_guide_summary.PTA_60
# The owner's picks of 2026-11-24 (#774 實作中本人補充).
SAID = "依您 2026/10/01 的聽力圖，整理出兩個重點。"
FOLD_TITLE = "看聽力圖數值與計算公式"
TAG = re.compile(r'<li class="guide-tag( is-suggestion)?">(.*?)</li>')


def tags(content):
    """The 結論標籤 as (words, suggests something to do), in page order."""
    return [(words, bool(blue)) for blue, words in TAG.findall(content)]


def outside_fold(content):
    """The page without its 看聽力圖數值與計算公式 fold."""
    opening, inside = test_guide.numbers_fold(content)
    return content.replace(opening + inside, "")


class ConclusionTagsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # GuideSummaryStatesTests' HHIE-S with ten items, for this class's own user.
        test_guide_summary.GuideSummaryStatesTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.user)

    make = test_guide_summary.GuideSummaryTests.make
    answer = test_guide_summary.GuideSummaryStatesTests.answer

    def page(self):
        return self.client.get(reverse("guide")).content.decode()

    def test_the_bird_says_two_points_from_the_audiogram_and_two_tags_follow_it(self):
        """#774 acceptance 8: under the bird, the two tags, then the cards."""
        self.make(PTA_55, PTA_55)
        content = self.page()
        bubble = re.search(r'<div class="bird-bubble">(.*?)</div>', content, re.S).group(1)
        self.assertRegex(bubble, rf"<p[^>]*>{SAID}</p>")
        self.assertEqual(tags(content), [("建議找聽力師評估", True), ("估算達到鑑定門檻", True)])
        self.assertLess(content.index("bird-bubble"), content.index('class="guide-tags"'))
        self.assertLess(content.index('class="guide-tags"'), content.index('class="guide-card'))
        # The bird says it now; the general line would come between it and its tags.
        self.assertNotIn(test_guide_summary.SIGNED_IN_INTRO, content)

    def test_the_fitting_tag_follows_the_advice(self):
        """ADR 0067's results, and wearing hearing aids before them, as the fold's sentence."""
        cases = {
            "track": ((40,) * 4, (20,) * 4, "slight", ("建議每年追蹤", False)),
            "questionnaire first": ((30,) * 4, (20,) * 4, None, ("先做生活影響問卷", True)),
            "normal": ((25,) * 4, (20,) * 4, None, ("兩耳在正常範圍", False)),
            "wearing": ((30,) * 4, (20,) * 4, "wearing", ("已在使用助聽器", False)),
        }
        for case, (right, left, questionnaire, tag) in cases.items():
            Answer.objects.filter(submission__user=self.user).delete()
            Submission.objects.filter(user=self.user).delete()
            Audiogram.objects.filter(user=self.user).delete()
            if questionnaire == "slight":
                self.answer(scores=test_guide_summary.SLIGHT)
            if questionnaire == "wearing":
                self.answer(wearing=True)
            self.make(right, left)
            with self.subTest(case=case):
                self.assertEqual(tags(self.page())[0], tag)

    def test_a_missing_frequency_tags_both_as_too_little_data(self):
        audiogram = self.make(PTA_55, PTA_55)
        audiogram.points.filter(frequency=4000).delete()
        self.assertEqual(
            tags(self.page()), [("聽力圖資料不足", False), ("資料不足，無法估算", False)]
        )

    def test_the_threshold_tag_follows_the_estimate(self):
        """ADR 0017's results: never 未達 for a lower bound."""
        cases = {
            "not reached": (
                (test_guide_summary.PTA_53_75, PTA_60),
                {},
                ("估算未達鑑定門檻", False),
            ),
            "uncertain": (
                ((40,) * 4, (80,) * 4),
                {"no_response_at": ("left", 4000)},
                ("無法確定是否達到門檻", False),
            ),
            "reached, at least": (
                (PTA_55, PTA_55),
                {"no_response_at": ("right", 2000)},
                ("估算達到鑑定門檻", True),
            ),
        }
        for case, (ears, options, tag) in cases.items():
            Audiogram.objects.filter(user=self.user).delete()
            self.make(*ears, **options)
            with self.subTest(case=case):
                self.assertEqual(tags(self.page())[1], tag)

    def test_only_a_self_test_estimates_no_threshold(self):
        """#774 acceptance 9 (ADR 0068): no 達到 or 未達 either way."""
        audiogram = self.make(PTA_60, PTA_60, tested_on=date(2026, 10, 1))
        Audiogram.objects.filter(pk=audiogram.pk).update(source=AudiogramSource.SELF_TEST)
        found = tags(self.page())
        self.assertEqual(found[1], ("自我測試不估算門檻", False))
        for words, _ in found:
            with self.subTest(words=words):
                self.assertNotIn("達到", words)
                self.assertNotIn("未達", words)

    def test_a_newer_self_test_leaves_the_tag_to_the_older_exam(self):
        self.make(PTA_60, PTA_60, tested_on=date(2024, 5, 3))
        newer = self.make((30,) * 4, (30,) * 4, tested_on=date(2026, 10, 1))
        Audiogram.objects.filter(pk=newer.pk).update(source=AudiogramSource.SELF_TEST)
        content = self.page()
        self.assertIn(SAID, content)
        self.assertEqual(tags(content)[1], ("估算達到鑑定門檻", True))

    def test_without_an_audiogram_there_are_no_tags_and_no_fold(self):
        """#774 acceptance 8: signed out, without records, with a questionnaire only."""
        for records in ("signed out", "none", "questionnaire only"):
            if records == "signed out":
                self.client.logout()
            else:
                self.client.force_login(self.user)
            if records == "questionnaire only":
                self.answer()
            content = self.page()
            with self.subTest(records=records):
                self.assertEqual(tags(content), [])
                self.assertNotIn('class="guide-tags"', content)
                self.assertIsNone(test_guide.numbers_fold(content))
                self.assertNotIn(FOLD_TITLE, content)
                self.assertNotIn("整理出兩個重點", content)


class AudiogramNumbersFoldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="guide_fold")

    def setUp(self):
        self.client.force_login(self.user)

    make = test_guide_summary.GuideSummaryTests.make

    def test_the_numbers_and_formula_are_only_in_the_shut_fold_under_the_tiles(self):
        """#774 acceptance 8: the meters, the ratio and 附表二甲's formula."""
        self.make(test_guide_summary.PTA_53_75, PTA_60)
        response = self.client.get(reverse("guide"))
        content = response.content.decode()
        inside = test_guide.inside_numbers_fold(self, response)
        # A native fold: it opens without JavaScript, its title the summary.
        self.assertRegex(inside, rf"^\s*<summary[^>]*>\s*{FOLD_TITLE}\s*</summary>")
        self.assertLess(
            content.rindex('class="chapter-tile"'), test_guide.NUMBERS_FOLD.search(content).start()
        )
        rest = outside_fold(content)
        for drawn in (
            'class="meter',
            "meter-bar",
            "四頻平均",
            "雙耳障礙比率",
            "附表二甲",
            "怎麼算的",
        ):
            with self.subTest(drawn=drawn):
                self.assertIn(drawn, inside)
                self.assertNotIn(drawn, rest)
        bars = test_guide_meters.GuideMetersTests.bars(inside)
        self.assertEqual(len(bars), 3)  # both ears, then the ratio

    def test_opened_the_meters_numbers_are_read_aloud(self):
        """Screen readers reach each number, though not the bars drawing them."""
        self.make(test_guide_summary.PTA_53_75, PTA_60)
        spoken = test_guide_meters.read_aloud(
            test_guide.inside_numbers_fold(self, self.client.get(reverse("guide")))
        )
        for said in (
            "右耳四頻平均 53.75 dB HL",
            "左耳四頻平均 60 dB HL",
            "正常上限 25",
            "雙耳障礙比率（估算） 約 44.7%",
            "門檻 45%",
        ):
            with self.subTest(said=said):
                self.assertIn(said, spoken)
