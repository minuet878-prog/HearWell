from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening.audiogram import DB_MAX
from screening.models import Audiogram, AudiogramPoint
from screening.tests import test_audiogram, test_guide
from screening.tests.helpers import consented_user

# Wording finalised in #220 (M9-M11, M17-M26, M28-M33).
AUDIOGRAM_TITLE = "聽力圖"
THRESHOLD_TITLE = "身障鑑定門檻"
THRESHOLD_NOTE = "雙耳障礙比率達到 45% 以上，就達到身心障礙鑑定「聽覺機能」的門檻。"
REACHED = (
    "依您 2026/10/01 的聽力圖估算，雙耳障礙比率約 45.0%，達到身障鑑定門檻（45%）。"
    "實際以鑑定醫院為準。"
)
NOT_REACHED = (
    "依您 2026/10/01 的聽力圖估算，雙耳障礙比率約 44.7%，未達到身障鑑定門檻（45%）。"
    "實際以鑑定醫院為準。"
)
UNCERTAIN = (
    "依您 2026/10/01 的聽力圖估算，雙耳障礙比率至少約 35.0%。"
    "這張聽力圖有測不到反應的點，無法確定是否達到鑑定門檻，請以鑑定醫院為準。"
)
NO_RESPONSE_NOTE = "這張聽力圖有測不到反應的點，實際比率可能更高。"
INSUFFICIENT = "兩耳都要有四頻平均，才能估算鑑定門檻。"
CERTIFICATE_FIRST = (
    "身障補助要先有身心障礙證明。請先到鑑定醫院申請身障鑑定，"
    "拿到證明後，才能申請九號表的助聽器補助。"
)
FIND_HOSPITAL = "找鑑定醫院"
OTHER_SUBSIDIES = "沒有身障證明的人，可能還有其他補助。"
WITHOUT_CERTIFICATE = "看沒有身障證明時"
HOW = "怎麼算的"
HOW_FORMULA = (
    "這是身心障礙鑑定「聽覺機能」用的公式。四頻平均是氣導 500、1000、2000、4000 Hz 的平均。"
)
ZERO_NOTE = "四頻平均低於 25 dB HL 的耳，以 0% 計。"
CAP_NOTE = "單耳比率超過 100% 的，以 100% 計。"
THRESHOLD_IS = "3. 身障鑑定門檻是 45.0%。"
# The worked steps for right 53.75 dB, left 60 dB, and for an ear under 25 dB.
EACH_EAR = (
    "1. 每一耳：（四頻平均 − 25）× 1.5%。右耳（53.75 − 25）× 1.5% ＝ 43.125%；"  # noqa: RUF001
    "左耳（60 − 25）× 1.5% ＝ 52.5%。"  # noqa: RUF001
)
BOTH_EARS = (
    "2. 比率比較小的一耳是優耳：雙耳 ＝（優耳 × 5 ＋ 劣耳）÷ 6"  # noqa: RUF001
    " ＝（43.125 × 5 ＋ 52.5）÷ 6 ＝ 44.7%，四捨五入到小數一位。"  # noqa: RUF001
)
ZERO_EAR = "右耳（10 − 25）× 1.5% ＝ 0%"  # noqa: RUF001

PTA_55 = (55, 55, 55, 55)
PTA_53_75 = (50, 55, 55, 55)
PTA_60 = (60, 60, 60, 60)


class GuideSummaryTests(TestCase):
    """#226: 我的選配指引 with an audiogram, its 聽力圖 and 身障鑑定門檻 boxes."""

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="guide_summary")

    def setUp(self):
        self.client.force_login(self.user)

    def make(self, right, left, tested_on=date(2026, 10, 1), user=None, no_response_at=None):
        points = [
            *test_audiogram._four(test_audiogram._air, "right", right),
            *test_audiogram._four(test_audiogram._air, "left", left),
        ]
        if no_response_at:
            # Unheard at the audiometer's limit, as the input page records it.
            points = [
                {**p, "db": DB_MAX["air"], "no_response": True}
                if (p["ear"], p["frequency"]) == no_response_at
                else p
                for p in points
            ]
        audiogram = Audiogram.objects.create(user=user or self.user, tested_on=tested_on)
        AudiogramPoint.objects.bulk_create(AudiogramPoint(audiogram=audiogram, **p) for p in points)
        return audiogram

    def text(self):
        return test_guide.text_of(self.client.get(reverse("guide")))

    def test_uses_the_latest_audiogram_and_says_its_date(self):
        self.make(PTA_60, PTA_60, tested_on=date(2026, 3, 1))
        self.make(PTA_53_75, PTA_60, tested_on=date(2026, 10, 1))
        text = self.text()
        self.assertIn(AUDIOGRAM_TITLE, text)
        self.assertIn(
            "依您 2026/10/01 的聽力圖：右耳四頻平均 53.75 dB HL，左耳四頻平均 60 dB HL。", text
        )
        self.assertNotIn("2026/03/01", text)

    def test_reached_says_so_and_points_to_assessment_first(self):
        self.make(PTA_55, PTA_55)
        response = self.client.get(reverse("guide"))
        text = test_guide.text_of(response)
        for sentence in (THRESHOLD_TITLE, THRESHOLD_NOTE, REACHED, CERTIFICATE_FIRST):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, text)
        self.assertContains(
            response,
            f'<a href="{reverse("guide_chapter", args=["assessment"])}">{FIND_HOSPITAL}</a>',
        )
        self.assertNotIn("未達到", text)
        self.assertNotIn(NO_RESPONSE_NOTE, text)

    def test_not_reached_points_to_subsidies_without_a_certificate(self):
        self.make(PTA_53_75, PTA_60)
        response = self.client.get(reverse("guide"))
        text = test_guide.text_of(response)
        self.assertIn(NOT_REACHED, text)
        self.assertIn(OTHER_SUBSIDIES, text)
        without = reverse("guide_chapter", args=["form-9"]) + "#without-certificate"
        self.assertContains(response, f'<a href="{without}">{WITHOUT_CERTIFICATE}</a>')
        self.assertNotIn(CERTIFICATE_FIRST, text)

    def test_uncertain_never_says_not_reached(self):
        # Left 4 kHz unheard at 120 dB: 35.0% is only a lower bound.
        self.make((40, 40, 40, 40), (80, 80, 80, 80), no_response_at=("left", 4000))
        response = self.client.get(reverse("guide"))
        text = test_guide.text_of(response)
        self.assertIn(UNCERTAIN, text)
        self.assertNotIn("未達到", text)
        self.assertIn(OTHER_SUBSIDIES, text)
        assessment = reverse("guide_chapter", args=["assessment"])
        self.assertContains(response, f'<a href="{assessment}">{FIND_HOSPITAL}</a>')
        without = reverse("guide_chapter", args=["form-9"]) + "#without-certificate"
        self.assertContains(response, f'<a href="{without}">{WITHOUT_CERTIFICATE}</a>')

    def test_reached_with_a_no_response_point_notes_it(self):
        # Right 55, 55, 55 and 2 kHz unheard at 120: PTA 71.25, so 49.1% at least.
        self.make(PTA_55, PTA_55, no_response_at=("right", 2000))
        text = self.text()
        self.assertIn(REACHED.replace("45.0%", "49.1%"), text)
        self.assertIn(NO_RESPONSE_NOTE, text)

    def test_a_missing_frequency_leaves_too_little_data(self):
        audiogram = self.make(PTA_55, PTA_55)
        audiogram.points.filter(ear="left", frequency=4000).delete()
        text = self.text()
        self.assertIn("右耳四頻平均 55 dB HL，左耳：資料不足，無法判讀", text)
        self.assertIn(INSUFFICIENT, text)
        self.assertNotIn(HOW, text)

    def test_how_it_was_worked_out(self):
        self.make(PTA_53_75, PTA_60)
        response = self.client.get(reverse("guide"))
        self.assertContains(response, f"<summary>{HOW}</summary>")
        text = test_guide.text_of(response)
        for sentence in (
            HOW_FORMULA,
            EACH_EAR,
            BOTH_EARS,
            THRESHOLD_IS,
        ):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, text)
        self.assertNotIn(ZERO_NOTE, text)
        self.assertNotIn(CAP_NOTE, text)

    def test_an_ear_over_100_percent_is_noted_as_100(self):
        self.make((90, 90, 95, 95), PTA_55)
        text = self.text()
        self.assertIn(CAP_NOTE, text)
        self.assertNotIn(ZERO_NOTE, text)

    def test_both_ears_without_a_pta_say_so_once(self):
        audiogram = self.make(PTA_55, PTA_55)
        audiogram.points.filter(frequency=4000).delete()
        text = self.text()
        self.assertIn("依您 2026/10/01 的聽力圖：兩耳都資料不足，無法判讀。", text)
        self.assertNotIn("右耳：資料不足", text)

    def test_an_ear_under_25_is_noted_as_0_percent(self):
        self.make((10, 10, 10, 10), (100, 100, 100, 100))
        text = self.text()
        self.assertIn(ZERO_EAR, text)
        self.assertIn(ZERO_NOTE, text)

    def test_no_level_is_shown_whatever_the_result(self):
        cases = {
            "reached": ((PTA_55, PTA_55), {}),
            "not_reached": ((PTA_53_75, PTA_60), {}),
            "uncertain": (((40,) * 4, (80,) * 4), {"no_response_at": ("left", 4000)}),
        }
        for status, (ears, options) in cases.items():
            Audiogram.objects.filter(user=self.user).delete()
            self.make(*ears, **options)
            text = self.text()
            for level in ("第 1 級", "第1級", "1 級", "輕度", "中度", "重度", "等級"):
                with self.subTest(status=status, level=level):
                    self.assertNotIn(level, text)

    def test_signed_in_page_is_never_cached_and_reads_only_own_records(self):
        self.make(PTA_55, PTA_55, user=consented_user(username="guide_summary_other"))
        response = self.client.get(reverse("guide"))
        self.assertIn("no-store", response["Cache-Control"])
        text = test_guide.text_of(response)
        self.assertNotIn(THRESHOLD_TITLE, text)
        self.assertNotIn("四頻平均", text)
