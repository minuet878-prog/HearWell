"""Spec #183 (2c batch 2), ticket #196: add-to-home lets the user pick their phone.

Acceptance 20 of #183: tapping 「我用 iPhone」 opens only the iPhone steps (with the 「⋯」
fallback), it opens without JavaScript, and the bottom of the page lists the 4 tabs.
"""

import re

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
        self.blocks = {
            summary.strip(): (details_attrs, body)
            for details_attrs, _, summary, body in DETAILS.findall(self.main)
        }

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
