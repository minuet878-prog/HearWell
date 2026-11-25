"""Ticket #706 (spec #702 acceptance 15-18, ADR 0068): the 身障鑑定門檻 estimate reads hearing
exams only; a self test still counts as an audiogram for everything else."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening.care_journey import DONE, care_journey
from screening.models import Audiogram, AudiogramPoint, AudiogramSource
from screening.tests import test_guide, test_guide_cards, test_guide_summary
from screening.tests.helpers import consented_user

PTA_30 = (30, 30, 30, 30)
PTA_60 = test_guide_summary.PTA_60
SELF_TEST_ONLY = "自我測試不能用來估算身障鑑定。想知道有沒有達到鑑定門檻，請到鑑定醫院做聽力檢查。"


def _threshold_part(text):
    """The 身障鑑定門檻 part of the page's text, up to its fold."""
    start = text.index("身障鑑定門檻")
    return text[start : text.index("看完整說明", start) if "看完整說明" in text[start:] else None]


class SelfTestAssessmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="guide_self_test")

    def setUp(self):
        self.client.force_login(self.user)

    make = test_guide_summary.GuideSummaryTests.make

    def self_test(self, right, left, tested_on):
        audiogram = self.make(right, left, tested_on=tested_on)
        Audiogram.objects.filter(pk=audiogram.pk).update(source=AudiogramSource.SELF_TEST)
        return audiogram

    def page(self):
        return self.client.get(reverse("guide")).content.decode()

    def test_only_a_self_test_says_go_for_an_exam_and_estimates_nothing(self):
        """Acceptance 15."""
        self.self_test(PTA_60, PTA_60, date(2026, 10, 1))
        page = self.page()
        part = _threshold_part(test_guide.text_of(self.client.get(reverse("guide"))))
        self.assertIn(SELF_TEST_ONLY, part)
        for said in ("達到身障鑑定門檻（45%）", "未達到", "雙耳障礙比率約", "至少約", "怎麼算的"):
            self.assertNotIn(said, part)
        self.assertNotIn("meter-ratio", page)
        # 要不要找聽力師評估 still reads it (spec #693's rule, acceptance 18).
        self.assertIn("四頻平均", test_guide.text_of(self.client.get(reverse("guide"))))

    def test_a_newer_self_test_leaves_the_estimate_to_the_older_exam(self):
        """Acceptance 16: the exam's ratio, the exam's date, and the owner's sentence."""
        self.make(PTA_60, PTA_60, tested_on=date(2024, 5, 3))
        self.self_test(PTA_30, PTA_30, date(2026, 10, 1))
        text = test_guide.text_of(self.client.get(reverse("guide")))
        # The page's audiogram is still the newest one.
        self.assertIn("依您 2026/10/01 的聽力圖", text)
        part = _threshold_part(text)
        self.assertIn(
            "依您 2024/05/03 的聽力圖估算，雙耳障礙比率約 52.5%，達到身障鑑定門檻（45%）。"
            "實際以鑑定醫院為準。",
            part,
        )
        self.assertIn("依您 2024/05/03 的聽力檢查估算。之後的自我測試不列入估算。", part)
        self.assertNotIn(SELF_TEST_ONLY, part)

    def test_the_newest_being_an_exam_is_as_before(self):
        """Acceptance 17."""
        self.self_test(PTA_30, PTA_30, date(2024, 5, 3))
        self.make(PTA_60, PTA_60, tested_on=date(2026, 10, 1))
        part = _threshold_part(test_guide.text_of(self.client.get(reverse("guide"))))
        self.assertIn("依您 2026/10/01 的聽力圖估算，雙耳障礙比率約 52.5%", part)
        self.assertNotIn("之後的自我測試不列入估算", part)
        self.assertNotIn(SELF_TEST_ONLY, part)

    def test_a_self_test_still_completes_the_audiogram_stop(self):
        """Acceptance 18: 照顧旅程 step 2 and the route's first stop are done (#779: the
        記錄聽力圖 引導卡 stamped), and 建議評估選配 (spec #693's rule) reads the self test,
        whatever the source."""
        self.self_test(PTA_60, PTA_60, date(2026, 10, 1))
        cards = dict(test_guide_cards.cards(self.client.get(reverse("guide"))))
        self.assertIn(test_guide_cards.STAMP, cards["audiogram"])
        self.assertEqual(care_journey(self.user, date(2026, 11, 17)).steps[1].state, DONE)
        text = test_guide.text_of(self.client.get(reverse("guide")))
        self.assertIn("您有一耳以上的四頻平均超過 40 dB HL，建議找聽力師評估選配助聽器。", text)

    def test_an_older_exam_too_incomplete_to_estimate_says_only_that(self):
        """No 「依您…的聽力檢查估算」 after 「兩耳都要有四頻平均」: nothing was estimated."""
        exam = self.make(PTA_60, PTA_60, tested_on=date(2024, 5, 3))
        AudiogramPoint.objects.filter(audiogram=exam, ear="left", frequency=4000).delete()
        self.self_test(PTA_30, PTA_30, date(2026, 10, 1))
        part = _threshold_part(test_guide.text_of(self.client.get(reverse("guide"))))
        self.assertIn("兩耳都要有四頻平均，才能估算鑑定門檻。", part)
        self.assertNotIn("聽力檢查估算", part)
