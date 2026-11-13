"""Spec #519 (tickets #521, #522): which 怎麼戴上、拿下 drawings carry a motion, and that each is
the one the owner reviewed in wear-motion-review.md's table. Playing it is wear-motion.js's, tested
in frontend/src/wear-motion.test.js and e2e.main_flow.WearMotionTest."""

import html
import json
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from screening.tests import test_family_wear, test_family_zone

REVIEW = Path(settings.BASE_DIR) / "docs/planning/redesign/wear-motion-review.md"
NUMBERS = r"-?\d+(?:\.\d+)?"


def _pieces(text):
    return [int(n) for n in re.search(r"第 \[([\d, ]+)\] 塊", text).group(1).split(", ")]


def _pose(text):
    return [float(n) for n in re.findall(NUMBERS, text)]


def _reviewed_motions():
    """{code: data-motion} as the review's table says, written the way the drawings carry it."""
    table = REVIEW.read_text().split("## 每張的動作")[1].split("## 審過的說明")[0]
    motions = {}
    for code, cell in re.findall(r"^\| `([a-z_]+)` \| [^|]+ \| (.+) \|$", table, re.M):
        motion = {"parts": [], "cues": []}
        for line in cell.split("<br>"):
            label, text = line.split("：", 1)
            if label.startswith("會動"):
                part = {
                    "pieces": _pieces(text),
                    "pivot": _pose(re.search(r"軸心 \(([^)]+)\)", text).group(1)),
                    "keys": [],
                }
                spans = re.findall(r"(\d+)–(\d+)%：\(([^)]+)\) → \(([^)]+)\)", text)
                for start, end, before, after in spans:
                    # Each span starts where the last one ended.
                    if part["keys"]:
                        assert part["keys"][-1] == [float(start), *_pose(before)], (code, line)
                    else:
                        part["keys"].append([float(start), *_pose(before)])
                    part["keys"].append([float(end), *_pose(after)])
                motion["parts"].append(part)
            elif label == "跟著動的線":
                points = re.search(r"第 \[([\d, ]+)\] 組座標", text).group(1).split(", ")
                which = int(re.search(r"「會動 (\d+)」", text).group(1)) - 1
                motion.setdefault("lines", []).append(
                    {"pieces": _pieces(text), "with": which, "points": [int(p) for p in points]}
                )
            elif label == "線變形":
                start, end = re.search(r"(\d+)–(\d+)% 變成審定圖", text).groups()
                # The shape changes over its part's whole span: the review times it so.
                assert motion["parts"][0]["keys"][0][0] == float(start), code
                assert motion["parts"][0]["keys"][-1][0] == float(end), code
                motion.setdefault("shapes", []).append(
                    {
                        "pieces": _pieces(text),
                        "with": 0,
                        "from": re.search(r"起點形狀 `([^`]+)`", text).group(1),
                    }
                )
            elif label.startswith("箭頭"):
                motion["cues"] = _pieces(text)
            else:
                raise AssertionError(f"{code}: {line}")
        motions[code] = motion
    return motions


def _as_numbers(motion):
    """The marker with every number a float, so 15 and 15.0 compare equal."""
    if isinstance(motion, dict):
        return {key: _as_numbers(value) for key, value in motion.items()}
    if isinstance(motion, list):
        return [_as_numbers(value) for value in motion]
    if isinstance(motion, int):
        return float(motion)
    return motion


class WearMotionMarkerTests(test_family_zone.SignsInWithARecord, TestCase):
    def setUp(self):
        response = self.client.get(reverse("family_hearing_aids"))
        self.assertEqual(response.status_code, 200)
        main = test_family_zone._main(response.content.decode())
        section = re.search(
            r'<section[^>]*aria-labelledby="wear-title".*?</section>', main, re.S
        ).group()
        start = section.index("data-pick-explanations")
        explanations = section[start : section.index("data-pick-live", start)]
        chunks = explanations.split('<strong class="tint-subhead block">')[1:]
        self.section = section
        # {code: the drawing's <svg> tag} for every step of every shape, as the server sends it.
        self.drawings = {}
        for chunk in chunks:
            shape = chunk.split("</strong>")[0]
            groups = test_family_wear.STEPS[shape]
            steps = [step for group in groups for step in group]
            items = re.findall(r"<li>(.*?)</li>", chunk, re.S)
            for item, (_, _, code) in zip(items, steps, strict=True):
                self.drawings[code] = re.search(r"<svg[^>]*>", item).group()

    def test_the_review_has_the_twelve_steps_of_the_spec(self):
        self.assertEqual(
            set(_reviewed_motions()),
            {
                "behind_ear_mould_twist_in",
                "behind_ear_mould_hook_on",
                "behind_ear_mould_lift_off",
                "behind_ear_mould_twist_out",
                "behind_ear_dome_hook_on",
                "behind_ear_dome_push_in",
                "behind_ear_dome_tuck_line",
                "behind_ear_dome_untuck_line",
                "behind_ear_dome_pull_out",
                "behind_ear_dome_lift_off",
                "in_ear_twist_in",
                "in_ear_twist_out",
            },
        )

    # #519 acceptance 1 and 13 (#522): the twelve carry the motion the owner reviewed, from its
    # start, in its direction, over its distance.
    def test_each_of_the_twelve_carries_its_reviewed_motion(self):
        for code, reviewed in _reviewed_motions().items():
            with self.subTest(code=code):
                marker = re.search(r"data-motion='([^']+)'", self.drawings[code])
                self.assertIsNotNone(marker)
                carried = json.loads(html.unescape(marker.group(1)))
                self.assertEqual(_as_numbers(carried), _as_numbers(reviewed))

    # Acceptance 1: 分左右, 開機, 關機收好 and 耳內's 對準耳道 do not move.
    def test_the_other_six_carry_no_motion(self):
        still = set(self.drawings) - set(_reviewed_motions())
        self.assertEqual(
            still,
            {
                "wear_left_right",
                "behind_ear_switch_on",
                "behind_ear_put_away",
                "in_ear_switch_on",
                "in_ear_line_up",
                "in_ear_put_away",
            },
        )
        for code in still:
            with self.subTest(code=code):
                self.assertNotIn("data-motion", self.drawings[code])

    # Acceptance 9: wear-motion.js adds 看動作, so without JavaScript there is no button that does
    # nothing, only the reviewed drawings.
    def test_the_server_sends_no_play_button(self):
        self.assertNotIn("<button", self.section)
        self.assertNotIn("看動作", self.section)
