import re
from datetime import date
from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse

from screening.models import Category, Question, Questionnaire
from screening.questionnaires import hhie_s
from screening.tests import test_guide, test_guide_summary
from screening.tests.helpers import consented_user

PTA_55 = test_guide_summary.PTA_55
# 48.75 and 36.25 dB HL: the four values are whole decibels, so a PTA ends in .0, .25, .5 or .75.
RIGHT_48_75 = (45, 50, 50, 50)
LEFT_36_25 = (35, 35, 35, 40)
JUMP = "看我的路線"
ROUTE_TITLE = "選配與補助，一步一步看"
RATIO_LABEL = "雙耳障礙比率（估算）"


# HTML elements without an end tag.
VOID = frozenset(
    ("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr")
)


class _ReadAloud(HTMLParser):
    """The page's text that screen readers reach: none inside an aria-hidden element."""

    def __init__(self):
        super().__init__()
        self.hidden = []  # per open element, whether it or an ancestor is aria-hidden
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            above = bool(self.hidden) and self.hidden[-1]
            self.hidden.append(above or dict(attrs).get("aria-hidden") == "true")

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag not in VOID:
            self.hidden.pop()

    def handle_data(self, data):
        if not (self.hidden and self.hidden[-1]):
            self.parts.append(data)


def read_aloud(markup):
    parser = _ReadAloud()
    parser.feed(markup)
    return re.sub(r"\s+", " ", " ".join(parser.parts))


class GuideMetersTests(TestCase):
    """#260: 我的選配指引's 要不要找聽力師評估 and 身障鑑定門檻 as meters, and the jump to the
    選配路線."""

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="guide_meters")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)
        cls.hhie_questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhie_s,
                question_text=f"假 HHIE 題{i}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )

    def setUp(self):
        self.client.force_login(self.user)

    make = test_guide_summary.GuideSummaryTests.make
    answer = test_guide_summary.GuideSummaryStatesTests.answer

    def page(self):
        return self.client.get(reverse("guide")).content.decode()

    def section(self, title_id):
        """The markup of the card a heading id labels."""
        found = re.search(
            rf'<section [^>]*aria-labelledby="{title_id}">(.*?)</section>', self.page(), re.S
        )
        self.assertIsNotNone(found, title_id)
        return found.group(1)

    @staticmethod
    def text(markup):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup))

    @staticmethod
    def bars(markup):
        """Each drawn bar's opening tag, by the ear or ratio it draws."""
        return re.findall(r'<[a-z]+ class="meter-bar[^"]*"[^>]*>', markup)

    def test_meters_come_between_the_questionnaire_and_the_route(self):
        self.answer()
        self.make(RIGHT_48_75, LEFT_36_25)
        text = test_guide.text_of(self.client.get(reverse("guide")))
        order = ["問卷結果", "要不要找聽力師評估", "身障鑑定門檻", JUMP, ROUTE_TITLE]
        positions = [text.find(part) for part in order]
        self.assertNotIn(-1, positions, dict(zip(order, positions, strict=True)))
        self.assertEqual(positions, sorted(positions))

    def test_each_ear_has_a_bar_with_its_number_and_the_normal_limit(self):
        self.make(RIGHT_48_75, LEFT_36_25)
        fitting = self.section("fitting-title")
        text = self.text(fitting)
        parts = [
            "依您 2026/10/01 的聽力圖：",
            "右耳四頻平均 48.75 dB HL",
            "左耳四頻平均 36.25 dB HL",
            test_guide_summary.RECOMMENDS,
        ]
        positions = [text.find(part) for part in parts]
        self.assertNotIn(-1, positions, text)
        self.assertEqual(positions, sorted(positions))
        self.assertIn("正常上限 25", text)
        bars = self.bars(fitting)
        self.assertEqual(len(bars), 2)
        self.assertIn("meter-bar-right", bars[0])
        self.assertIn("meter-bar-left", bars[1])

    def test_the_audiogram_card_is_folded_into_the_fitting_meter(self):
        self.make(RIGHT_48_75, LEFT_36_25)
        self.assertNotIn('id="audiogram-title"', self.page())

    def test_an_ear_without_a_pta_says_too_little_data_and_has_no_bar(self):
        audiogram = self.make(PTA_55, PTA_55)
        audiogram.points.filter(ear="left", frequency=4000).delete()
        fitting = self.section("fitting-title")
        text = self.text(fitting)
        self.assertIn("右耳四頻平均 55 dB HL", text)
        self.assertIn("左耳四頻平均 資料不足，無法判讀", text)
        bars = self.bars(fitting)
        self.assertEqual(len(bars), 1)
        self.assertIn("meter-bar-right", bars[0])
        # Without both ears there is no ratio to draw.
        self.assertEqual(self.bars(self.section("threshold-title")), [])

    def test_both_ears_without_a_pta_keep_the_sentence_and_draw_nothing(self):
        audiogram = self.make(PTA_55, PTA_55)
        audiogram.points.filter(frequency=4000).delete()
        fitting = self.section("fitting-title")
        self.assertIn("依您 2026/10/01 的聽力圖：兩耳都資料不足，無法判讀。", self.text(fitting))
        self.assertNotIn("正常上限 25", self.text(fitting))
        self.assertEqual(self.bars(fitting), [])

    def test_no_response_points_draw_a_lower_bound(self):
        cases = {
            "uncertain": (((40,) * 4, (80,) * 4), ("left", 4000), "35.0"),
            "reached": ((PTA_55, PTA_55), ("right", 2000), "49.1"),
        }
        for status, (ears, no_response_at, ratio) in cases.items():
            self.user.audiograms.all().delete()
            self.make(*ears, no_response_at=no_response_at)
            threshold = self.section("threshold-title")
            with self.subTest(status=status):
                self.assertIn(f"{RATIO_LABEL} 至少約 {ratio}%", self.text(threshold))
                self.assertIn("門檻 45%", self.text(threshold))
                self.assertEqual(len(self.bars(threshold)), 1)
                self.assertIn('class="meter-beyond"', threshold)

    def test_without_no_response_points_the_ratio_is_plain(self):
        self.make(test_guide_summary.PTA_53_75, test_guide_summary.PTA_60)
        threshold = self.section("threshold-title")
        text = self.text(threshold)
        self.assertIn(f"{RATIO_LABEL} 約 44.7%", text)
        self.assertNotIn(f"{RATIO_LABEL} 至少約", text)
        self.assertIn("門檻 45%", text)
        self.assertEqual(len(self.bars(threshold)), 1)
        self.assertNotIn("meter-beyond", threshold)

    def test_bars_are_hidden_from_screen_readers(self):
        self.make(PTA_55, PTA_55, no_response_at=("right", 2000))
        page = self.page()
        meters = re.findall(r'<div class="meter-track[^"]*"[^>]*>', page)
        self.assertEqual(len(meters), 3)
        for meter in meters:
            with self.subTest(meter=meter):
                self.assertIn('aria-hidden="true"', meter)

    def test_the_reference_values_are_read_aloud_though_the_bars_are_not(self):
        # Self-review of #260: with a hearing aid or a missing frequency the sentence never
        # says 25, so the labels beside the lines must reach screen readers.
        self.make(PTA_55, PTA_55, no_response_at=("right", 2000))
        spoken = read_aloud(self.page())
        self.assertIn("正常上限 25", spoken)
        self.assertIn("門檻 45%", spoken)

    def test_the_jump_goes_to_the_route_title_which_takes_focus(self):
        self.make(RIGHT_48_75, LEFT_36_25)
        page = self.page()
        arrow = '<span aria-hidden="true"> ↓</span>'
        self.assertRegex(page, rf'<a class="btn [^"]*" href="#contents-title">{JUMP}{arrow}</a>')
        self.assertRegex(page, r'<h2 id="contents-title" [^>]*tabindex="-1"')

    def test_without_an_audiogram_there_are_no_meters_or_jump(self):
        for records in ("none", "questionnaire only"):
            if records == "questionnaire only":
                self.answer()
            page = self.page()
            with self.subTest(records=records):
                self.assertNotIn(JUMP, page)
                self.assertNotIn("meter-", page)
                self.assertNotIn("正常上限 25", page)
                self.assertIn(ROUTE_TITLE, page)

    def test_signed_out_there_are_no_meters_or_jump(self):
        self.client.logout()
        page = self.page()
        self.assertNotIn(JUMP, page)
        self.assertNotIn("meter-", page)
        self.assertIn(ROUTE_TITLE, page)

    def test_the_audiogram_date_is_the_latest(self):
        self.make(PTA_55, PTA_55, tested_on=date(2026, 3, 1))
        self.make(RIGHT_48_75, LEFT_36_25)
        self.assertIn("依您 2026/10/01 的聽力圖：", self.text(self.section("fitting-title")))
