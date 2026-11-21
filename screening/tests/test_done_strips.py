"""Spec #741's 實作中本人補充: the three pages that say something is done (意見回饋已送出, 已取消
提醒, 保存完成) carry, under the bird's bubble, the green line the result page opens with
(「做完了，已存到我的紀錄。」), the same look."""

import re

from django.test import TestCase
from django.urls import reverse

from screening.tests.helpers import consented_user

TICK = (
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
    '<path d="M5 12.5l4.5 4.5L19 7.5"/></svg>'
)


def strip(words):
    return f'<p class="result-saved" role="status">{TICK}{words}</p>'


class DoneStripTests(TestCase):
    def under_the_bubble(self, html, words):
        """The green line comes right after the bird dialogue's closing tags."""
        self.assertRegex(
            html,
            r'(?s)<div class="bird-dialogue">.*?</h1>\s*</div>\s*</div>\s*'
            + re.escape(strip(words)),
        )

    def test_feedback_sent(self):
        page = self.client.get(reverse("feedback_sent")).content.decode()
        self.under_the_bubble(page, "意見回饋已送出。")

    def test_reminder_cancelled(self):
        page = self.client.get(reverse("reminder_cancelled")).content.decode()
        self.under_the_bubble(page, "已取消 email 重測提醒。")

    def test_guest_result_saved(self):
        # Shown by guest-save.js once saved: the box is on the page, hidden until then.
        self.client.force_login(consented_user(username="done_strip_guest"))
        page = self.client.get(reverse("guest_save")).content.decode()
        done = page[page.index("<div data-guest-done hidden>") :]
        self.under_the_bubble(done, "已存到我的紀錄。")
