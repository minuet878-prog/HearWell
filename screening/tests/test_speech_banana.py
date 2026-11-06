import json
import re
from datetime import date
from itertools import pairwise
from math import log2
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from screening.audiogram import SPEECH_BANANA, SPEECH_GROUPS, speech_banana
from screening.models import Audiogram, AudiogramPoint
from screening.tests.helpers import action_cards, consented_user

HEARD = "可能聽得到"
HARD = "可能不容易聽到"
BROKEN = "無法確定（聽力線在這裡因無反應斷開）"
NO_MARK = "這個頻率沒有標記，無法估計"


def _mark(frequency, db, ear="right", conduction="air", no_response=False, masked=False):
    return mock.Mock(
        ear=ear,
        conduction=conduction,
        frequency=frequency,
        db=db,
        no_response=no_response,
        masked=masked,
    )


def _marks(*pairs, **fields):
    return [_mark(frequency, db, **fields) for frequency, db in pairs]


def _texts(points, ear="right"):
    return [result["text"] for result in speech_banana(points)[ear]["results"]]


def _edge_at(edge, frequency):
    """The outline's level at frequency, straight between its points on the log axis."""
    for (f1, db1), (f2, db2) in pairwise(sorted(edge)):
        if f1 <= frequency <= f2:
            return db1 + log2(frequency / f1) / log2(f2 / f1) * (db2 - db1)
    raise AssertionError(frequency)


class SpeechBananaRuleTests(SimpleTestCase):
    """Spec #436 判斷規則 (ADR 0040). Groups by position: 460, 1200, 2400, 3300, 5500, 6600 Hz."""

    def test_group_above_the_line_between_two_marks_may_be_heard(self):
        # #436: the line is about 35 dB at 1200 Hz, and group 2 sits at 46 dB.
        self.assertEqual(_texts(_marks((1000, 30), (2000, 50)))[1], HEARD)

    def test_group_below_the_line_may_be_hard_to_hear(self):
        # Worked by hand: at 1200 Hz the line is about 57.9 dB.
        self.assertEqual(_texts(_marks((1000, 50), (2000, 80)))[1], HARD)

    def test_the_line_runs_straight_on_the_log_frequency_axis(self):
        # Group 5 is 39 dB at 5500 Hz. On the chart's log axis the line there is 0 + 50 x
        # log2(5500/4000) / log2(6000/4000), about 39.3 dB; on a linear axis it would be 37.5 dB.
        self.assertEqual(_texts(_marks((4000, 0), (6000, 50)))[4], HARD)

    def test_a_group_exactly_on_the_line_may_be_hard_to_hear(self):
        self.assertEqual(_texts(_marks((3000, 44), (4000, 44)))[3], HARD)
        self.assertEqual(_texts(_marks((6000, 35), (8000, 35)))[5], HARD)
        # One dB better is on the other side of it.
        self.assertEqual(_texts(_marks((3000, 43), (4000, 43)))[3], HEARD)

    def test_only_500_to_4000_leaves_groups_1_5_6_without_an_estimate(self):
        texts = _texts(_marks((500, 40), (1000, 45), (2000, 50), (4000, 55)))
        self.assertEqual([texts[0], texts[4], texts[5]], [NO_MARK] * 3)
        for group in (1, 2, 3):
            self.assertIn(texts[group], (HEARD, HARD))

    def test_marks_are_read_in_frequency_order(self):
        shuffled = _marks((2000, 50), (500, 40), (4000, 55), (1000, 45))
        in_order = _marks((500, 40), (1000, 45), (2000, 50), (4000, 55))
        self.assertEqual(_texts(shuffled), _texts(in_order))
        self.assertEqual(
            speech_banana(shuffled)["right"]["stretches"],
            [[(500, 40), (1000, 45), (2000, 50), (4000, 55)]],
        )

    def test_a_no_response_mark_breaks_the_line_on_both_sides(self):
        points = [*_marks((1000, 30), (2000, 40)), _mark(4000, 120, no_response=True)]
        texts = _texts(points)
        self.assertEqual(texts[2], BROKEN)
        self.assertEqual(texts[3], BROKEN)
        # Before the break the line still counts: group 2 has a result of its own.
        self.assertEqual(texts[1], HEARD)

    def test_a_no_response_mark_on_the_low_side_breaks_the_line_too(self):
        points = [_mark(4000, 120, no_response=True), _mark(8000, 40)]
        self.assertEqual(_texts(points)[4], BROKEN)

    def test_past_a_highest_mark_with_no_response_there_is_no_estimate(self):
        points = [_mark(2000, 40), _mark(4000, 120, no_response=True)]
        self.assertEqual(_texts(points)[4], NO_MARK)

    def test_one_mark_makes_no_line(self):
        self.assertEqual(_texts([_mark(1000, 30)]), [NO_MARK] * 6)

    def test_only_bone_marks_give_no_estimate_and_no_stretches(self):
        result = speech_banana(_marks((500, 30), (1000, 30), (2000, 30), conduction="bone"))
        for ear in ("right", "left"):
            self.assertEqual([r["text"] for r in result[ear]["results"]], [NO_MARK] * 6)
            self.assertEqual(result[ear]["stretches"], [])

    def test_bone_marks_do_not_change_the_result(self):
        air = _marks((1000, 30), (2000, 50))
        bone = _marks((1000, 90), (2000, 90), conduction="bone")
        self.assertEqual(speech_banana([*air, *bone]), speech_banana(air))

    def test_masking_does_not_change_the_result(self):
        plain = _marks((1000, 30), (2000, 50), (4000, 60))
        masked = _marks((1000, 30), (2000, 50), (4000, 60), masked=True)
        self.assertEqual(speech_banana(masked), speech_banana(plain))

    def test_each_ear_is_judged_on_its_own_marks(self):
        right = _marks((1000, 30), (2000, 50))
        left = _marks((1000, 70), (2000, 80), ear="left")
        result = speech_banana([*right, *left])
        self.assertEqual(result["right"]["results"][1]["text"], HEARD)
        self.assertEqual(result["left"]["results"][1]["text"], HARD)
        self.assertEqual(result["left"]["stretches"], [[(1000, 70), (2000, 80)]])

    def test_a_no_response_mark_splits_the_stretches_and_is_in_neither(self):
        points = [
            *_marks((500, 30), (1000, 35)),
            _mark(2000, 120, no_response=True),
            *_marks((3000, 50), (4000, 55)),
        ]
        self.assertEqual(
            speech_banana(points)["right"]["stretches"],
            [[(500, 30), (1000, 35)], [(3000, 50), (4000, 55)]],
        )

    def test_a_stretch_of_one_mark_is_not_returned(self):
        points = [
            _mark(500, 30),
            _mark(1000, 120, no_response=True),
            *_marks((2000, 50), (4000, 55)),
        ]
        self.assertEqual(speech_banana(points)["right"]["stretches"], [[(2000, 50), (4000, 55)]])

    def test_the_result_says_which_of_the_four_it_is(self):
        points = [*_marks((250, 80), (1000, 30), (2000, 30)), _mark(3000, 120, no_response=True)]
        statuses = [r["status"] for r in speech_banana(points)["right"]["results"]]
        self.assertEqual(statuses, ["hard", "heard", "broken", "no_mark", "no_mark", "no_mark"])

    def test_the_six_groups_are_the_reviewed_ones(self):
        self.assertEqual(
            [
                (g["rows"], g["frequency"], g["db"], g["description"], g["examples"])
                for g in SPEECH_GROUPS
            ],
            [
                (("ㄩㄧㄨ", "ㄝㄜㄛㄦ"), 460, 44, "母音的低音部分", "ㄧ「一」、ㄨ「五」、ㄩ「魚」"),
                (("ㄚㄨㄛ", "ㄚㄜㄦ"), 1200, 46, "母音", "ㄚ「阿」、ㄛ「喔」、ㄜ「鵝」"),
                (
                    ("ㄝㄩㄇㄖ", "ㄧㄋㄌ"),
                    2400,
                    48,
                    "鼻音、ㄌ 和母音的高音部分",
                    "ㄇ「媽」、ㄋ「你」、ㄌ「老」",
                ),
                (
                    ("ㄏㄅㄉㄍ", "ㄆㄎㄊ"),
                    3300,
                    44,
                    "短促的子音",
                    "ㄅ「爸」、ㄉ「大」、ㄍ「哥」、ㄎ「看」",
                ),
                (
                    ("ㄈㄐㄑㄓ", "ㄔㄒㄕ"),
                    5500,
                    39,
                    "高音的子音",
                    "ㄕ「是」、ㄑ「七」、ㄒ「西」、ㄔ「吃」",
                ),
                (("ㄗㄙㄘ",), 6600, 35, "最高音的子音", "ㄙ「四」、ㄘ「菜」、ㄗ「字」"),
            ],
        )

    def test_the_outline_passes_through_the_reviewed_readings(self):
        # #436's table, within the half a dB the drawn points are rounded to.
        table = {
            500: (38, 53),
            1000: (40, 56),
            2000: (40, 58),
            3000: (38, 56),
            4000: (36, 52),
            6000: (28, 45),
            8000: (23, 40),
        }
        for frequency, (top, bottom) in table.items():
            with self.subTest(frequency=frequency):
                self.assertAlmostEqual(_edge_at(SPEECH_BANANA["top"], frequency), top, delta=0.5)
                self.assertAlmostEqual(
                    _edge_at(SPEECH_BANANA["bottom"], frequency), bottom, delta=0.5
                )


class SpeechBananaPageTests(TestCase):
    """Spec #436 進入與權限 and what the page hands the browser; the drawing is tested in e2e."""

    CARD = ("看語言香蕉區", "看哪些說話聲可能不容易聽到")

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="speech_banana_page")
        cls.other = consented_user(username="speech_banana_other")

    def setUp(self):
        self.client.force_login(self.user)

    def _make(self, *points, user=None, tested_on=date(2026, 9, 1)):
        audiogram = Audiogram.objects.create(user=user or self.user, tested_on=tested_on)
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(
                audiogram=audiogram,
                ear=ear,
                conduction=conduction,
                frequency=frequency,
                db=db,
                no_response=no_response,
            )
            for ear, conduction, frequency, db, no_response in points
        )
        return audiogram

    def _url(self, audiogram):
        return reverse("audiogram_speech_banana", args=[audiogram.id])

    def _main(self, response):
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _cards(self, audiogram):
        response = self.client.get(reverse("audiogram_detail", args=[audiogram.id]))
        return action_cards(self._main(response))

    def _data(self, audiogram):
        content = self.client.get(self._url(audiogram)).content.decode()
        found = re.search(r'<script id="speech-banana-data"[^>]*>(.*?)</script>', content, re.S)
        return json.loads(found.group(1))

    def test_card_links_to_this_audiogram_when_either_ear_has_air_marks(self):
        for ear in ("right", "left"):
            with self.subTest(ear=ear):
                audiogram = self._make((ear, "air", 1000, 40, False))
                self.assertIn((self._url(audiogram), *self.CARD), self._cards(audiogram))

    def test_no_card_with_only_bone_marks(self):
        audiogram = self._make(("right", "bone", 1000, 40, False))
        self.assertNotIn(self.CARD[0], [title for _, title, _ in self._cards(audiogram)])

    def test_signed_out_goes_to_the_login_page(self):
        audiogram = self._make(("right", "air", 1000, 40, False))
        self.client.logout()
        url = self._url(audiogram)
        self.assertRedirects(
            self.client.get(url), f"{reverse('login')}?next={url}", fetch_redirect_response=False
        )

    def test_someone_elses_audiogram_is_404(self):
        theirs = self._make(("right", "air", 1000, 40, False), user=self.other)
        self.assertEqual(self.client.get(self._url(theirs)).status_code, 404)

    def test_the_response_must_not_be_cached(self):
        audiogram = self._make(("right", "air", 1000, 40, False))
        self.assertIn("no-store", self.client.get(self._url(audiogram))["Cache-Control"])

    def test_title_has_the_test_date_and_the_page_loads_its_own_script(self):
        audiogram = self._make(("right", "air", 1000, 40, False))
        response = self.client.get(self._url(audiogram))
        self.assertContains(response, "2026/09/01 聽力圖的語言香蕉區</h1>")
        self.assertContains(response, "<title>2026/09/01 聽力圖的語言香蕉區")
        self.assertContains(response, "screening/frontend/speech-banana.js")

    def test_the_page_is_for_the_audiogram_opened(self):
        older = self._make(("right", "air", 1000, 40, False), tested_on=date(2026, 1, 5))
        self._make(("right", "air", 1000, 80, False), tested_on=date(2026, 9, 1))
        self.assertContains(self.client.get(self._url(older)), "2026/01/05 聽力圖的語言香蕉區")
        self.assertEqual(self._data(older)["ears"][0]["marks"][0]["db"], 40)

    def test_the_browser_gets_the_outline_and_the_groups(self):
        data = self._data(self._make(("right", "air", 1000, 40, False)))
        self.assertEqual(data["banana"]["top"][0], [281, 36])
        self.assertEqual(data["banana"]["bottom"][0], [10660, 26])
        self.assertEqual(
            [
                (g["rows"], g["frequency"], g["db"], g["description"], g["examples"])
                for g in data["groups"][:1] + data["groups"][-1:]
            ],
            [
                (["ㄩㄧㄨ", "ㄝㄜㄛㄦ"], 460, 44, "母音的低音部分", "ㄧ「一」、ㄨ「五」、ㄩ「魚」"),
                (["ㄗㄙㄘ"], 6600, 35, "最高音的子音", "ㄙ「四」、ㄘ「菜」、ㄗ「字」"),
            ],
        )
        self.assertEqual(len(data["groups"]), 6)

    def test_the_browser_gets_both_ears_results_and_only_air_marks(self):
        audiogram = self._make(
            ("right", "air", 1000, 30, False),
            ("right", "air", 2000, 50, False),
            ("right", "bone", 1000, 20, False),
        )
        right, left = self._data(audiogram)["ears"]
        self.assertEqual((right["ear"], right["label"]), ("right", "右耳"))
        self.assertEqual((left["ear"], left["label"]), ("left", "左耳"))
        self.assertEqual(
            sorted((m["conduction"], m["frequency"], m["db"]) for m in right["marks"]),
            [("air", 1000, 30), ("air", 2000, 50)],
        )
        self.assertEqual(right["results"][1], {"status": "heard", "text": HEARD})
        self.assertEqual(right["stretches"], [[[1000, 30], [2000, 50]]])
        # #436 story 5: the ear with no air marks says so, the other still has its result.
        self.assertEqual(left["marks"], [])
        self.assertEqual([r["text"] for r in left["results"]], [NO_MARK] * 6)
        self.assertEqual(left["stretches"], [])
