"""#504 (spec #502): 怎麼戴上、拿下 on the 助聽器 page, as the server sends it. Picking a shape,
ticking and changing shape in a real browser are in e2e.main_flow.FamilyWearTest."""

import re
from itertools import pairwise
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from screening.tests import test_family_care, test_family_zone

MOULD = "耳掛（有耳模）"
DOME = "耳掛（耳塞和細線）"
IN_THE_EAR = "耳內"
# The words of wear-wording.md as the owner reviewed them on 2026-11-13, written out so a slip in
# the definition shows: for each shape, 戴上 then 拿下, each step as (title, words, drawing code).
LEFT_RIGHT = (
    "分左右",
    "看助聽器上的顏色：紅色戴右耳、藍色戴左耳。沒有顏色的，問聽力師怎麼分。",
    "wear_left_right",
)
SWITCH_ON = "裝電池的：關上電池門。充電的：長按按鍵幾秒，照說明書。"
PUT_AWAY = "裝電池的：打開電池門，放進盒子。充電的：插進充電座，照說明書。"
STEPS = {
    MOULD: (
        [
            LEFT_RIGHT,
            ("開機", SWITCH_ON, "behind_ear_switch_on"),
            (
                "耳模轉進去",
                "拿著耳模，把伸進耳道的那一端對準耳道，輕輕轉著推進去，直到貼平。",
                "behind_ear_mould_twist_in",
            ),
            ("機身掛到耳後", "把機身掛到耳朵上方，放在耳朵後面。", "behind_ear_mould_hook_on"),
        ],
        [
            ("先拿下機身", "把機身從耳朵後面拿下來。", "behind_ear_mould_lift_off"),
            ("轉出耳模", "捏住耳模，輕輕轉出來。不要拉導管。", "behind_ear_mould_twist_out"),
            ("關機收好", PUT_AWAY, "behind_ear_put_away"),
        ],
    ),
    DOME: (
        [
            LEFT_RIGHT,
            ("開機", SWITCH_ON, "behind_ear_switch_on"),
            ("先掛機身", "把機身掛到耳朵上方，放在耳朵後面。", "behind_ear_dome_hook_on"),
            (
                "推進耳塞",
                "捏住細線靠近耳塞的地方，把耳塞輕輕推進耳道，細線貼著頭的側邊。",
                "behind_ear_dome_push_in",
            ),
            (
                "塞好固定線",
                "有固定線的，把它塞進耳殼的凹處，耳塞比較不會掉出來。",
                "behind_ear_dome_tuck_line",
            ),
        ],
        [
            (
                "拉出固定線",
                "有固定線的，先把它從耳殼的凹處拉出來。",
                "behind_ear_dome_untuck_line",
            ),
            (
                "拉出耳塞",
                "捏住細線靠近耳塞的地方，輕輕拉出來。不要拉離耳塞遠的那段細線。",
                "behind_ear_dome_pull_out",
            ),
            ("拿下機身", "把機身從耳朵後面拿下來。", "behind_ear_dome_lift_off"),
            ("關機收好", PUT_AWAY, "behind_ear_put_away"),
        ],
    ),
    IN_THE_EAR: (
        [
            LEFT_RIGHT,
            ("開機", SWITCH_ON, "in_ear_switch_on"),
            ("對準耳道", "拿著機身，拉線朝下、朝後，出聲的那一端對準耳道。", "in_ear_line_up"),
            (
                "轉著推進去",
                "輕輕轉著推進去，推到不鬆、也不痛。另一手可以把耳朵往後上拉一點。",
                "in_ear_twist_in",
            ),
        ],
        [
            ("轉出來", "捏住拉線或機身邊緣，輕輕轉出來。", "in_ear_twist_out"),
            ("關機收好", PUT_AWAY, "in_ear_put_away"),
        ],
    ),
}
# Acceptance 8 as #502's comment of 2026-11-13 changed it.
SQUEAL = (
    "戴好後一直嘯叫（尖尖的叫聲），通常是沒推到位：拿出來再推一次，還是叫就看「助聽器怪怪的」。"
)
# The 18 drawings the owner went through one by one, each in a figure captioned with its code.
REVIEWED_MOCKUP = Path(settings.BASE_DIR) / "docs/planning/redesign/mockup-503-wear.html"


def _reviewed_drawings():
    """{code: what it draws} for the mockup's drawings sheet."""
    sheet = REVIEWED_MOCKUP.read_text()
    sheet = sheet[sheet.index("4　線條圖草稿") : sheet.index("5　實測數值")]
    drawings = {}
    for figure in re.findall(r"<figure>(.*?)</figure>", sheet, re.S):
        code = re.search(r"<code>([a-z_]+)</code>", figure).group(1)
        drawings[code] = test_family_care._shapes(re.search(r"<svg.*?</svg>", figure, re.S).group())
    return drawings


def _text(html):
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", html))


class FamilyWearTests(test_family_zone.SignsInWithARecord, TestCase):
    def setUp(self):
        self.url = reverse("family_hearing_aids")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.content = response.content.decode()
        self.main = test_family_zone._main(self.content)
        self.section = re.search(
            r'<section[^>]*aria-labelledby="wear-title".*?</section>', self.main, re.S
        ).group()

    # Acceptance 1: the jump list, in order, with the new row landing on the section.
    def test_jump_list_puts_wear_between_adjusting_and_care(self):
        nav = re.search(r'<nav aria-label="這一頁的內容">.*?</nav>', self.main, re.S).group()
        self.assertEqual(
            re.findall(r'<span class="link-card-title">([^<]+)</span>', nav),
            ["助聽器怪怪的", "陪長輩適應", "怎麼戴上、拿下", "日常保養"],
        )
        self.assertRegex(nav, r'(?s)href="#wear-title"[^>]*>.*?怎麼戴上、拿下.*?</a>')
        self.assertRegex(self.section, r'<h2 id="wear-title"[^>]*>怎麼戴上、拿下</h2>')

    # Acceptance 2: the sections themselves, in the same order.
    def test_section_comes_after_adjusting_and_before_care(self):
        titles = re.findall(r'<h2 id="([a-z-]+)"', self.main)
        self.assertEqual(titles, ["problems-title", "adjusting-title", "wear-title", "care-title"])

    # Acceptance 4: the question and its three shapes, none picked yet.
    def test_asks_which_shape_with_three_unpicked_choices(self):
        self.assertIn("<p>勾選不會留下，換外型也會清掉。</p>", self.section)
        self.assertRegex(self.section, r"<legend[^>]*>他的助聽器是哪一種？</legend>")
        radios = re.findall(r'<input type="radio"[^>]*><span>([^<]+)</span>', self.section)
        self.assertEqual(radios, [MOULD, DOME, IN_THE_EAR])
        self.assertNotIn("checked", self.section)

    def _options(self):
        """{label: the HTML under it} for each shape, as the server sends them."""
        start = self.section.index("data-pick-explanations")
        explanations = self.section[start : self.section.index("data-pick-live", start)]
        chunks = explanations.split('<strong class="tint-subhead block">')[1:]
        return {chunk.split("</strong>")[0]: chunk.split("</strong>", 1)[1] for chunk in chunks}

    # Acceptance 5 without a script: every shape is sent, its steps in 戴上 then 拿下, each group
    # under its own title and numbered from 1, each step with a drawing, its words and a box.
    # Acceptance 9: the words are the ones the owner reviewed.
    def test_each_shape_has_two_titled_groups_of_steps_with_words_drawing_and_box(self):
        options = self._options()
        self.assertEqual(list(options), [MOULD, DOME, IN_THE_EAR])
        for shape, groups in STEPS.items():
            chunk = options[shape]
            self.assertEqual(re.findall(r"<h3[^>]*>([^<]+)</h3>", chunk), ["戴上", "拿下"])
            lists = re.findall(r"<ol[^>]*>(.*?)</ol>", chunk, re.S)
            self.assertEqual(len(lists), 2, shape)
            for found, steps in zip(lists, groups, strict=True):
                items = re.findall(r"<li>(.*?)</li>", found, re.S)
                self.assertEqual(len(items), len(steps), shape)
                for number, (item, (title, words, _)) in enumerate(
                    zip(items, steps, strict=True), start=1
                ):
                    with self.subTest(shape=shape, title=title):
                        label = re.search(r"<label[^>]*>(.*)</label>", item, re.S).group(1)
                        self.assertEqual(
                            re.search(r"<strong[^>]*>([^<]+)</strong>", label).group(1),
                            f"{number}. {title}",
                        )
                        self.assertEqual(_text(label), f"{number}.{title}{words}")
                        self.assertEqual(item.count('type="checkbox"'), 1)
                        self.assertEqual(item.count("<svg"), 1)

    # Acceptance 9: each step's drawing is the one the owner reviewed under its code.
    def test_each_step_has_the_drawing_the_owner_reviewed(self):
        reviewed = _reviewed_drawings()
        self.assertEqual(len(reviewed), 18)
        options = self._options()
        used = set()
        for shape, groups in STEPS.items():
            items = re.findall(r"<li>(.*?)</li>", options[shape], re.S)
            steps = [step for group in groups for step in group]
            for item, (title, _, code) in zip(items, steps, strict=True):
                with self.subTest(shape=shape, title=title):
                    drawn = re.search(r"<svg.*?</svg>", item, re.S).group()
                    self.assertEqual(test_family_care._shapes(drawn), reviewed[code])
                    used.add(code)
        self.assertEqual(used, set(reviewed))

    # Acceptance 7: 拿下's last step says to switch off and put away, and links to 日常保養.
    def test_the_last_step_of_taking_out_links_to_care(self):
        for shape, chunk in self._options().items():
            with self.subTest(shape=shape):
                last = re.findall(r"<li>(.*?)</li>", chunk.split("<h3")[2], re.S)[-1]
                self.assertIn("關機收好", last)
                self.assertRegex(
                    last, r'<a [^>]*href="#care-title"[^>]*>怎麼收，看「日常保養」</a>'
                )
                self.assertEqual(chunk.count('href="#care-title"'), 1)

    # Acceptance 8: after 戴上's steps, before 拿下, the squeal sentence links to 助聽器怪怪的.
    def test_the_squeal_sentence_sits_between_the_groups_and_links_to_problems(self):
        for shape, chunk in self._options().items():
            with self.subTest(shape=shape):
                between = chunk[chunk.index("</ol>") : chunk.index("<h3", chunk.index("</ol>"))]
                self.assertEqual(_text(between), SQUEAL)
                self.assertRegex(
                    between, r'<a [^>]*href="#problems-title"[^>]*>「助聽器怪怪的」</a>'
                )
                self.assertEqual(_text(chunk).count(SQUEAL), 1)

    # Acceptance 3: the same for an account with records, and nothing of theirs.
    def test_signed_in_user_gets_the_same_section_without_their_data(self):
        self.sign_in_with_a_record("wear_private")
        content = self.client.get(self.url).content.decode()
        self.assertIn(self.section, test_family_zone._main(content))
        self.assert_shows_no_record(content, "wear_private")

    # Acceptance 11: a screen reader hears the words, not the drawings; the drawings have no stop
    # for the keyboard, image file or script of their own.
    def test_every_drawing_is_hidden_from_screen_readers(self):
        tags = re.findall(r"<svg[^>]*>", self.section)
        self.assertEqual(len(tags), 4 + 3 + 5 + 4 + 4 + 2)
        for tag in tags:
            with self.subTest(tag=tag):
                self.assertIn('aria-hidden="true"', tag)
                self.assertIn('focusable="false"', tag)
        self.assertNotIn("<img", self.section)
        self.assertNotIn("<script", self.section)
        self.assertNotIn("<title", self.section)

    # Drawn twice on a page once picked: an id in one would clash with its copy.
    def test_the_drawings_have_no_ids(self):
        for svg in re.findall(r"<svg.*?</svg>", self.section, re.S):
            self.assertNotIn(" id=", svg)

    # Acceptance 6 as the server sends it: nothing to send and nothing to bring back.
    def test_boxes_are_in_no_form_have_no_name_and_are_not_put_back(self):
        boxes = re.findall(r'<input type="checkbox"[^>]*>', self.section)
        self.assertEqual(len(boxes), 22)
        for box in boxes:
            with self.subTest(box=box):
                self.assertIn('autocomplete="off"', box)
                self.assertNotIn("name=", box)
        self.assertNotIn("<form", self.main)
        self.assertIn("no-store", self.client.get(self.url).get("Cache-Control", ""))

    # The whole page keeps its one title and its levels with the two group titles in it.
    def test_page_has_one_main_heading_and_levels_never_skip(self):
        self.assertEqual(re.findall(r"<h1[^>]*>([^<]*)</h1>", self.content), ["助聽器"])
        levels = [int(level) for level in re.findall(r"<h([1-6])[\s>]", self.main)]
        for previous, level in pairwise(levels):
            self.assertLessEqual(level, previous + 1)
