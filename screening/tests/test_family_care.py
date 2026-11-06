"""#435 (spec #426): 日常保養 on the 助聽器 page, as the server sends it. Picking a shape, ticking
and reloading in a real browser are in e2e.main_flow.FamilyCareTest."""

import re
from itertools import pairwise
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from screening.tests import test_family_hearing_aids, test_family_zone

BEHIND_THE_EAR = "掛在耳後"
IN_THE_EAR = "戴在耳內"
# Words of batch-3-wording.md section 3, written out so a slip in the definition shows:
# (title and how often, what to do), in order.
STEPS = {
    BEHIND_THE_EAR: [
        (
            "1. 擦乾淨（每天）",
            "拿下來後，用乾的軟布或面紙擦機身和耳模或耳塞。不要弄濕，也不要用含酒精或化學成分的濕紙巾。",
        ),
        (
            "2. 清耳垢（每天）",
            "用聽力師給的工具，清掉耳模或耳塞出口的耳垢，不要硬戳。耳塞裡有濾網的，濾網有耳垢就換新。",
        ),
        (
            "3. 看導管（每天）",
            "導管有沒有折到、堵住或裂開，裡面有沒有水氣。處理不來就問聽力師。",
        ),
        (
            "4. 洗耳模（有耳模的，約一週一次）",
            "把導管從助聽器的掛鉤拔下來，導管不要從耳模拔出。耳模泡溫肥皂水洗乾淨，"
            "沖乾淨後把導管裡的水吹出來，放到隔天全乾再裝回去。機身不能碰水。",
        ),
        (
            "5. 關機收好（每天）",
            "不戴的時候關機，放進盒子，遠離高溫和潮濕，也放在小孩和寵物拿不到的地方。"
            "充電式的照說明書充電。",
        ),
    ],
    IN_THE_EAR: [
        ("1. 刷開口（每天）", "一天結束時，用聽力師給的軟刷，刷掉開口上的耳垢和碎屑。"),
        ("2. 挑耳垢（刷不掉時）", "刷不掉的，用挑耳垢的工具輕輕挑，不要硬戳。"),
        ("3. 擦乾淨（每天）", "用乾淨的乾布或面紙全部擦過。不要弄濕。"),
        (
            "4. 關機收好（每天）",
            "不戴的時候關機，放進盒子，遠離高溫和潮濕，也放在小孩和寵物拿不到的地方。"
            "充電式的照說明書充電。",
        ),
    ],
}
DEEP_IN_THE_CANAL = "深耳道型這種放在耳道很深處的，由聽力師在回診時清潔。"
REMINDERS = [
    "戴著助聽器時不要噴髮膠或用其他美髮產品。",
    "沒電的電池馬上換；電池放在小孩和寵物拿不到的地方。",
]
# The drawings the owner went through one by one: the file's figures, in the steps' order.
REVIEWED_DRAWINGS = Path(settings.BASE_DIR) / "docs/planning/family-zone/batch-3-drawings.html"


def _shapes(svg):
    """What an SVG draws: everything inside it, without the spaces between its tags."""
    inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
    return re.sub(r">\s+<", "><", inner).strip()


class FamilyCareTests(test_family_zone.SignsInWithARecord, TestCase):
    def setUp(self):
        self.url = reverse("family_hearing_aids")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.content = response.content.decode()
        self.main = test_family_zone._main(self.content)
        self.section = re.search(
            r'<section[^>]*aria-labelledby="care-title".*?</section>', self.main, re.S
        ).group()

    def _options(self):
        """{label: the HTML under it} for each shape, as the server sends them."""
        start = self.section.index("data-pick-explanations")
        explanations = self.section[start : self.section.index("data-pick-live", start)]
        chunks = explanations.split('<strong class="tint-subhead block">')[1:]
        return {chunk.split("</strong>")[0]: chunk.split("</strong>", 1)[1] for chunk in chunks}

    def _steps(self, chunk):
        return re.findall(r"<li[^>]*>.*?</li>", chunk, re.S)

    def test_the_section_has_its_heading_question_and_two_shapes(self):
        self.assertRegex(self.section, r'<h2 id="care-title"[^>]*>日常保養</h2>')
        self.assertIn("他的助聽器是哪一種？", self.section)
        self.assertEqual(
            re.findall(
                r'<input type="radio" name="hearing-aid-care" autocomplete="off">'
                r"<span>([^<]+)</span>",
                self.section,
            ),
            [BEHIND_THE_EAR, IN_THE_EAR],
        )

    # Acceptance 33 without a script: the server sends both shapes, in full.
    # Acceptance 34: each step has its words, a drawing and a box.
    def test_each_shape_has_its_steps_in_order_with_words_drawing_and_box(self):
        options = self._options()
        for shape, steps in STEPS.items():
            found = self._steps(options[shape])
            self.assertEqual(len(found), len(steps), shape)
            for step, (title, words) in zip(found, steps, strict=True):
                with self.subTest(title=title):
                    label = re.search(r"<label[^>]*>(.*)</label>", step, re.S).group(1)
                    self.assertEqual(
                        re.search(r"<strong[^>]*>([^<]+)</strong>", label).group(1), title
                    )
                    self.assertEqual(re.sub(r"<[^>]+>", "", label).strip(), title + words)
                    self.assertEqual(step.count('type="checkbox"'), 1)
                    self.assertEqual(step.count("<svg"), 1)

    # The owner went through these drawings one by one: the shapes are the reviewed file's.
    def test_the_drawings_are_the_ones_the_owner_reviewed(self):
        reviewed = [
            _shapes(svg)
            for svg in re.findall(r"<svg.*?</svg>", REVIEWED_DRAWINGS.read_text(), re.S)
        ]
        options = self._options()
        drawn = [
            _shapes(re.search(r"<svg.*?</svg>", step, re.S).group())
            for shape in STEPS
            for step in self._steps(options[shape])
        ]
        self.assertEqual(len(reviewed), 9)
        self.assertEqual(drawn, reviewed)

    # A drawing is never the only way to know a step: the words say it, and it is hidden from
    # screen readers, without a stop for the keyboard, an image file or a script of its own.
    def test_every_drawing_is_hidden_from_screen_readers(self):
        tags = re.findall(r"<svg[^>]*>", self.section)
        self.assertEqual(len(tags), 9)
        for tag in tags:
            with self.subTest(tag=tag):
                self.assertIn('aria-hidden="true"', tag)
                self.assertIn('focusable="false"', tag)
        self.assertNotIn("<img", self.section)
        self.assertNotIn("<script", self.section)
        self.assertNotIn("<title", self.section)
        self.assertNotRegex(self.section, r"<(text|desc)[\s>]")

    # Drawn twice on a page once picked: an id in one would clash with its copy.
    def test_the_drawings_have_no_ids(self):
        for svg in re.findall(r"<svg.*?</svg>", self.section, re.S):
            self.assertNotIn(" id=", svg)

    # Nothing to send and nothing to bring back: ticks stay on the page until it reloads.
    def test_boxes_are_in_no_form_have_no_name_and_are_not_put_back(self):
        boxes = re.findall(r'<input type="checkbox"[^>]*>', self.section)
        self.assertEqual(len(boxes), 9)
        for box in boxes:
            with self.subTest(box=box):
                self.assertIn('autocomplete="off"', box)
                self.assertNotIn("name=", box)
        self.assertNotIn("<form", self.main)

    # On a shared phone, 上一頁 should not bring back someone else's ticks.
    def test_the_response_is_never_stored(self):
        self.assertIn("no-store", self.client.get(self.url).get("Cache-Control", ""))

    def test_deep_in_the_canal_comes_after_the_in_the_ear_steps_only(self):
        options = self._options()
        chunk = options[IN_THE_EAR]
        self.assertGreater(chunk.index(DEEP_IN_THE_CANAL), chunk.rindex("</ol>"))
        self.assertNotIn(DEEP_IN_THE_CANAL, options[BEHIND_THE_EAR])

    # For both shapes, so under the question rather than under either of them.
    def test_reminders_for_both_shapes_are_below_the_question(self):
        after = self.section[self.section.index("</fieldset>") :]
        self.assertRegex(after, r"<h3[^>]*>兩種都適用的提醒</h3>")
        self.assertEqual(re.findall(r"<li>([^<]+)</li>", after), REMINDERS)

    def test_jump_link_comes_last_and_lands_on_the_section(self):
        nav = re.search(r'<nav aria-label="這一頁的內容">.*?</nav>', self.main, re.S).group()
        self.assertEqual(re.findall(r'href="([^"]+)"', nav)[-1], "#care-title")
        self.assertRegex(nav, r'(?s)href="#care-title"[^>]*>.*?日常保養.*?</a>')

    def test_no_brand_names_in_the_section(self):
        for brand in test_family_hearing_aids.BRANDS:
            with self.subTest(brand=brand):
                self.assertNotIn(brand.lower(), self.section.lower())

    # Acceptance 37: the whole page keeps its one title and its levels with this section in it.
    def test_page_has_one_main_heading_and_levels_never_skip(self):
        self.assertEqual(re.findall(r"<h1[^>]*>([^<]*)</h1>", self.content), ["助聽器"])
        levels = [int(level) for level in re.findall(r"<h([1-6])[\s>]", self.main)]
        for previous, level in pairwise(levels):
            self.assertLessEqual(level, previous + 1)

    def test_signed_in_user_gets_the_same_section_without_their_data(self):
        self.sign_in_with_a_record("care_private")
        content = self.client.get(self.url).content.decode()
        self.assertIn(self.section, test_family_zone._main(content))
        self.assert_shows_no_record(content, "care_private")

    def test_says_ticks_are_not_kept(self):
        self.assertIn("<p>勾選不會留下，換外型也會清掉。</p>", self.main)

    def test_no_step_points_at_another_shape(self):
        self.assertNotIn("同上", self.main)
