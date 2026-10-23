"""Spec #183 (2c batch 2), ticket #196: add-to-home lets the user pick their phone.

Acceptance 20 of #183: tapping 「我用 iPhone」 opens only the iPhone steps (with the 「⋯」
fallback), it opens without JavaScript, and the bottom of the page lists the 4 tabs.
"""

import re
from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from screening.tests.helpers import consented_user

DETAILS = re.compile(
    r"<details([^>]*)>\s*<summary([^>]*)>(.*?)</summary>(.*?)</details>", re.DOTALL
)

IPHONE_STEPS = (
    "用 Safari 打開 HearWell 網站。",
    "點畫面下方的「分享」按鈕（一個方框，上面有向上的箭頭）。如果沒看到，先點「⋯」再點「分享」。",
    "往下滑，點「加入主畫面」。",
    "點右上角的「加入」。",
)
SITE_CSS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "site.css"
ANDROID_STEPS = (
    "用 Chrome 打開 HearWell 網站。",
    "點右上角的「⋮」（三個點）。",
    "點「加到主畫面」或「安裝應用程式」。",
    "再點一次「安裝」或「新增」。",
)


class AddToHomeTests(TestCase):
    def setUp(self):
        content = self.client.get(reverse("add_to_home")).content.decode()
        self.main = content[content.index("<main") : content.index("</main>")]
        # Footer redesign: each summary starts with a decorative phone icon, then its words.
        self.icons = {}
        self.blocks = {}
        for details_attrs, _, summary, body in DETAILS.findall(self.main):
            words = re.sub(r"<svg.*?</svg>", "", summary, flags=re.DOTALL).strip()
            self.icons[words] = summary[: summary.index(words)]
            self.blocks[words] = (details_attrs, body)

    def test_each_phone_has_a_decorative_icon(self):
        for words, icon in self.icons.items():
            with self.subTest(summary=words):
                self.assertRegex(icon, r'^<svg [^>]*aria-hidden="true"')

    def test_iphone_block_holds_only_the_iphone_steps_with_the_fallback(self):
        self.assertEqual(list(self.blocks), ["我用 iPhone", "我用 Android"])
        _, body = self.blocks["我用 iPhone"]
        steps = re.findall(r"<li>(.*?)</li>", body)
        self.assertEqual(steps, list(IPHONE_STEPS))
        self.assertIn("如果沒看到，先點「⋯」再點「分享」。", body)
        for step in ANDROID_STEPS:
            self.assertNotIn(step, body)

    def test_android_block_holds_only_the_android_steps(self):
        _, body = self.blocks["我用 Android"]
        self.assertEqual(re.findall(r"<li>(.*?)</li>", body), list(ANDROID_STEPS))
        for step in IPHONE_STEPS:
            self.assertNotIn(step, body)

    def test_blocks_open_without_javascript_and_start_closed(self):
        # Native <details>/<summary>: the browser opens them and tells screen readers whether
        # they are expanded, with no script; no `open`, so both start closed.
        for summary, (attrs, _) in self.blocks.items():
            with self.subTest(summary=summary):
                self.assertNotRegex(attrs, r"\bopen\b")
        self.assertNotRegex(self.main, r"\son[a-z]+=")
        self.assertNotIn("<script", self.main)

    def test_bottom_of_the_page_names_the_four_tabs(self):
        tabs = "從主畫面打開時，請用畫面下方的「首頁、開始篩檢、我的紀錄、聽力圖」切換頁面。"
        self.assertIn(tabs, self.main.rsplit("</details>", 1)[1])
        # The same four, in the same order, as the tab bar a logged-in user sees.
        self.client.force_login(consented_user(username="addtohometabs"))
        content = self.client.get(reverse("add_to_home")).content.decode()
        nav = content[content.index('<nav aria-label="主要導覽"') : content.index("</nav>")]
        labels = re.findall(r"<span>(.*?)</span>", nav)
        self.assertEqual(labels, ["首頁", "開始篩檢", "我的紀錄", "聽力圖"])

    def test_summaries_are_big_enough_and_only_change_colour(self):
        for summary, (_, body) in self.blocks.items():
            with self.subTest(summary=summary):
                self.assertNotIn("<summary", body)
        self.assertIn('<details class="dropdown-box', self.main)
        css = SITE_CSS.read_text(encoding="utf-8")
        rules = re.findall(r"\.dropdown-box[^{]*\{[^}]*\}", css)
        self.assertTrue(rules)
        # Tap target of at least 44px (2.75rem); hover and press change colour, never position
        # (ADR 0006).
        self.assertTrue(any("min-height: var(--spacing-touch)" in rule for rule in rules))
        self.assertTrue(any(":hover" in rule for rule in rules))
        self.assertTrue(any(":active" in rule for rule in rules))
        for rule in rules:
            self.assertNotIn("transform", rule)
            self.assertNotIn("translate", rule)
