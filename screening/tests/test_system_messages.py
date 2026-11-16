"""The feedback batch (the owner's picks in mockup-feedback.html, 2026-11-16): the words a page
shows at its top after something was done (Django's messages), and the sentences added for three
things that said nothing when done."""

import re
from datetime import date

from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from screening.models import Audiogram, ReportShare
from screening.tests.helpers import consented_user

BANNER = re.compile(
    r'<div class="system-message system-message-(\w+)" role="(\w+)">(.*?)</div>', re.S
)


def banners(html):
    """Each banner as (kind, role, its words without tags)."""
    return [
        (kind, role, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", body)).strip())
        for kind, role, body in BANNER.findall(html)
    ]


def drawn(*messages):
    return render_to_string("screening/system_message.html", {"messages": list(messages)})


class SystemMessageTests(TestCase):
    """F1 A: a whole bar with its colour and mark; read out, the failed one at once."""

    def test_success_is_a_green_bar_with_a_tick_read_out_politely(self):
        html = drawn(Message(constants.SUCCESS, "密碼改好了"))
        self.assertEqual(banners(html), [("success", "status", "密碼改好了")])
        self.assertIn('class="system-message-mark" aria-hidden="true"', html)

    def test_a_failure_is_a_red_bar_read_out_at_once(self):
        html = drawn(Message(constants.ERROR, "這個 LINE 帳號已經用在另一個帳號。"))
        self.assertEqual(banners(html), [("error", "alert", "這個 LINE 帳號已經用在另一個帳號。")])

    def test_a_note_is_a_blue_bar(self):
        html = drawn(Message(constants.INFO, "這份作答剛才已經送出。"))
        self.assertEqual(banners(html), [("info", "status", "這份作答剛才已經送出。")])

    def test_one_bar_a_page_the_latest(self):
        # GOV.UK: at most one a page.
        html = drawn(Message(constants.INFO, "較早的"), Message(constants.SUCCESS, "最新的"))
        self.assertEqual(banners(html), [("success", "status", "最新的")])

    def test_nothing_without_a_message(self):
        self.assertEqual(drawn().strip(), "")

    def test_a_page_draws_it_over_its_title(self):
        user = consented_user(username="message_reader")
        self.client.force_login(user)
        audiogram = Audiogram.objects.create(user=user, tested_on=date(2026, 9, 1))
        response = self.client.post(reverse("audiogram_delete", args=[audiogram.pk]), follow=True)
        main = response.content.decode().split('id="main-content"', 1)[1]
        self.assertLess(main.index('class="system-message '), main.index("<h1"))


class DoneSentenceTests(TestCase):
    """F2: the three things that said nothing when done, as the owner finalised the words."""

    def setUp(self):
        self.user = consented_user(username="done_sentences")
        self.client.force_login(self.user)

    def test_deleting_an_audiogram_names_its_date(self):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 9, 1))
        response = self.client.post(reverse("audiogram_delete", args=[audiogram.pk]), follow=True)
        self.assertIn(
            ("success", "status", "已刪除 2026/09/01 的聽力圖。"),
            banners(response.content.decode()),
        )

    def test_cancelling_a_share_says_the_link_no_longer_opens(self):
        share = ReportShare.objects.create(user=self.user)
        response = self.client.post(reverse("report_share_cancel", args=[share.pk]), follow=True)
        self.assertIn(
            ("success", "status", "已取消分享，原本的連結不能再打開。"),
            banners(response.content.decode()),
        )

    def test_logging_out_says_so_on_the_home_page(self):
        response = self.client.post(reverse("logout"), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse("index"))
        self.assertIn(("success", "status", "已登出。"), banners(response.content.decode()))


class DownloadNoteTests(TestCase):
    """F4 B: 下載我的資料 gets what download-note.js needs; its words are in its own test."""

    def test_the_row_and_its_status_area_wait_for_the_script(self):
        self.client.force_login(consented_user(username="downloader"))
        content = self.client.get(reverse("account_settings")).content.decode()
        self.assertIn("screening/download-note.js", content)
        link = re.search(r"<a [^>]*data-download-note[^>]*>(.*?)</a>", content, re.S)
        self.assertIn(f'href="{reverse("download_my_data")}"', link.group(0))
        self.assertIn(
            "<span data-download-words>把您在聽伴的所有資料下載成一個檔案保存。</span>",
            link.group(1),
        )
        self.assertRegex(
            content[link.end() :],
            r'^\s*<span class="visually-hidden" role="status" data-download-status></span>',
        )
