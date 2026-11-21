import html
import json
import re
from datetime import UTC, date, datetime, timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core import mail
from django.core.cache import caches
from django.core.mail.backends.base import BaseEmailBackend
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from screening import models
from screening import urls as screening_urls
from screening.context_processors import NAMED_BY_CODE
from screening.forms import FEEDBACKS_PER_ADDRESS, RESET_WINDOW
from screening.models import Audiogram, Consent, Feedback, FeedbackNotice, ReportShare, User
from screening.models.feedback import FEEDBACK_KEPT_FOR
from screening.tests import test_layout
from screening.tests.helpers import consented_user, submission_with_answers
from screening.views import feedback as feedback_views


def footer_of(response):
    page = response.content.decode()
    start = page.index('<footer class="site-footer"')
    return page[start : page.index("</footer>", start)]


class SendFeedbackTests(TestCase):
    """Spec #633 (#636): anyone sends a few words from the footer and sees they were sent."""

    def send(self, **data):
        return self.client.post(reverse("feedback"), {"text": "字太小了", **data}, follow=True)

    def test_the_words_are_kept_and_the_sent_page_says_so(self):
        before = timezone.now()
        response = self.send()
        self.assertRedirects(response, reverse("feedback_sent"))
        self.assertContains(response, "已送出")
        feedback = Feedback.objects.get()
        self.assertEqual(feedback.text, "字太小了")
        self.assertEqual(feedback.email, "")
        self.assertFalse(feedback.handled)
        self.assertLessEqual(before, feedback.created_at)

    def test_an_email_typed_is_kept_with_it(self):
        self.send(email="wang@example.com")
        self.assertEqual(Feedback.objects.get().email, "wang@example.com")

    def test_the_page_offers_the_box_and_an_optional_email(self):
        response = self.client.get(reverse("feedback"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="text"')
        self.assertContains(response, 'name="email"')
        self.assertContains(response, "想收到回覆才填")
        self.assertNotContains(response, 'name="email" required')

    def test_what_is_wrong_is_said_and_nothing_kept_with_the_words_still_in_the_box(self):
        cases = {
            "blank": ({"text": "   "}, "請先寫下想說的話", "   "),
            "too long": ({"text": "耳" * 1001}, "請縮短到 1000 字以內", "耳" * 1001),
            "bad email": ({"email": "wang@gmail"}, "Email 格式不對", "字太小了"),
        }
        for case, (data, said, kept) in cases.items():
            with self.subTest(case):
                response = self.client.post(reverse("feedback"), {"text": "字太小了", **data})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, said)
                self.assertContains(response, f">{kept}</textarea>")
                self.assertFalse(Feedback.objects.exists())

    def test_a_box_only_robots_fill_seems_sent_but_keeps_nothing(self):
        response = self.send(website="http://spam.example")
        self.assertRedirects(response, reverse("feedback_sent"))
        self.assertFalse(Feedback.objects.exists())

    def test_the_page_it_came_from_is_said_and_kept_in_words(self):
        cases = {
            "result": "結果頁",
            "guide_chapter:assessment": "選配指引：身障鑑定與鑑定醫院",
            "qa_answer:sudden-hearing-loss": "問答小助手：突然聽不到、耳朵流血，該怎麼辦？",
            "shared_report": "家人看的聽力報告",
        }
        for page, words in cases.items():
            with self.subTest(page):
                shown = self.client.get(reverse("feedback"), {"page": page})
                self.assertContains(shown, f"您是從「{words}」過來的。")
                self.send(page=page)
                self.assertEqual(Feedback.objects.latest("pk").page, words)

    def test_a_page_it_does_not_know_is_neither_said_nor_kept(self):
        for page in ("", "nothing", "guide_chapter:nothing", "qa_answer:nothing", "result:12"):
            with self.subTest(page):
                shown = self.client.get(reverse("feedback"), {"page": page})
                self.assertNotContains(shown, "過來的")
                self.send(page=page)
                self.assertEqual(Feedback.objects.latest("pk").page, "")

    def test_the_sent_page_leads_back_to_the_page_it_came_from(self):
        response = self.send(page="result", next="/submission/12")
        self.assertRedirects(response, f"{reverse('feedback_sent')}?next=%2Fsubmission%2F12")
        self.assertContains(response, 'href="/submission/12"')
        self.assertContains(response, "回到剛才那一頁")

    def test_the_way_back_is_never_another_site(self):
        for next_url in ("", "https://evil.example/", "//evil.example/"):
            with self.subTest(next_url):
                response = self.client.get(reverse("feedback_sent"), {"next": next_url})
                self.assertNotContains(response, 'href="https://evil')
                self.assertNotContains(response, 'href="//evil')
                self.assertContains(
                    response, f'<a class="btn btn-primary btn-lg w-full" href="{reverse("index")}">'
                )
                self.assertContains(response, "回到首頁")

    def test_the_address_it_came_from_is_never_kept(self):
        self.send(page="result", next="/submission/12")
        values = Feedback.objects.values().get()
        self.assertNotIn("/submission/12", [str(value) for value in values.values()])

    def test_every_footer_leads_here_naming_its_page_and_the_way_back(self):
        share = ReportShare.objects.create(user=consented_user(username="feedback_sharer"))
        cases = {
            reverse("privacy"): "page=privacy&amp;next=%2Fprivacy",
            reverse("guide_chapter", args=["assessment"]): (
                "page=guide_chapter%3Aassessment&amp;next=%2Fguide%2Fassessment"
            ),
            f"{reverse('family_talk')}?x=1": "page=family_talk&amp;next=%2Ffamily%2Ftalk%3Fx%3D1",
            # Cross review of spec #633 (P2): a shared report's way back would carry its share
            # code into the feedback pages' addresses, so it has none.
            reverse("shared_cover", args=[share.token]): "page=shared_cover",
            reverse("shared_report", args=[share.token]): "page=shared_report",
        }
        for url, query in cases.items():
            with self.subTest(url):
                footer = footer_of(self.client.get(url))
                self.assertIn(f'href="{reverse("feedback")}?{query}"', footer)
                self.assertNotIn(share.token, footer)

    def test_no_account_address_or_session_is_kept(self):
        self.client.force_login(consented_user(username="feedback_sender"))
        self.client.post(
            reverse("feedback"), {"text": "字太小了", "page": "result"}, REMOTE_ADDR="203.0.113.7"
        )
        fields = {field.name for field in Feedback._meta.get_fields()}
        self.assertEqual(fields, {"id", "text", "email", "page", "created_at", "handled"})
        values = [str(value) for value in Feedback.objects.values().get().values()]
        self.assertNotIn("203.0.113.7", values)
        self.assertNotIn("feedback_sender", values)
        self.assertNotIn(self.client.session.session_key, values)

    def test_a_signed_in_user_finds_the_email_box_empty(self):
        self.client.force_login(
            consented_user(username="feedback_mail", email="feedback_mail@example.com")
        )
        response = self.client.get(reverse("feedback"))
        self.assertNotContains(response, "feedback_mail@example.com")

    def test_one_who_has_not_agreed_to_the_new_version_can_still_send(self):
        self.client.force_login(User.objects.create_user("feedback_new_version", password="x"))
        self.assertEqual(self.client.get(reverse("feedback")).status_code, 200)
        response = self.send()
        self.assertRedirects(response, reverse("feedback_sent"))
        self.assertEqual(Feedback.objects.count(), 1)

    def test_the_download_has_no_feedback_even_with_its_email(self):
        user = consented_user(username="feedback_download", email="download@example.com")
        self.client.force_login(user)
        self.send(text="報告印不出來", email="download@example.com")
        response = self.client.get(reverse("download_my_data"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertNotIn("報告印不出來", json.dumps(data, ensure_ascii=False))
        self.assertFalse({"feedback", "feedbacks"} & set(data))

    def test_its_pages_are_kept_out_of_search(self):
        for url in (reverse("feedback"), reverse("feedback_sent")):
            with self.subTest(url):
                self.assertIn("noindex", self.client.get(url)["X-Robots-Tag"])

    def test_deleting_an_account_leaves_feedback_with_its_email(self):
        user = consented_user(username="feedback_leaving", email="leaving@example.com")
        self.send(email="leaving@example.com")
        user.delete_with_data()
        self.assertEqual(Feedback.objects.get().email, "leaving@example.com")

    def test_the_urgent_box_comes_before_the_form(self):
        page = self.client.get(reverse("feedback")).content.decode()
        urgent = f'href="{reverse("qa_answer", args=["sudden-hearing-loss"])}"'
        self.assertIn(urgent, page)
        self.assertIn("突然聽不到、耳朵流血？請盡快就醫", page)
        self.assertLess(page.index(urgent), page.index('name="text"'))

    def test_people_and_screen_readers_never_meet_the_robots_box(self):
        page = self.client.get(reverse("feedback")).content.decode()
        box = page[: page.index('name="website"')]
        self.assertIn("hidden", box[box.rindex("<div") :])
        self.assertIn('tabindex="-1"', page[page.index('name="website"') - 200 :][:400])


TOO_MANY_AN_HOUR = "這一小時送太多次了，請一小時後再試。您寫的字還在下面。"
TOO_MANY_TODAY = "今天收到的意見太多了，請明天再試，或寫信到"


class FeedbackLimitTests(TestCase):
    """Spec #633 (#637): 5 an hour from one address, as the forgot-password page counts it
    (NUM_PROXIES), and 100 kept a day on the whole site; the words stay in the box."""

    def setUp(self):
        caches["password_reset"].clear()

    def send(self, text="字太小了", forwarded=None, remote="127.0.0.1", **data):
        extra = {"REMOTE_ADDR": remote}
        if forwarded:
            extra["HTTP_X_FORWARDED_FOR"] = forwarded
        return self.client.post(reverse("feedback"), {"text": text, **data}, **extra)

    def assert_refused(self, response, said, text="字太小了"):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, said)
        self.assertContains(response, f">{text}</textarea>")

    def test_the_sixth_in_an_hour_from_one_address_is_refused_with_the_words_kept(self):
        for _ in range(5):
            self.send()
        response = self.send(text="還有一件事")
        self.assert_refused(response, TOO_MANY_AN_HOUR, text="還有一件事")
        self.assertEqual(Feedback.objects.count(), 5)

    def test_an_hour_later_it_works_again(self):
        for _ in range(5):
            self.send()
        later = timezone.now() + timedelta(hours=1, seconds=1)
        # The database cache took its own name for now() when it loaded, so that is the one to move.
        with mock.patch("django.core.cache.backends.db.tz_now", return_value=later):
            self.assertRedirects(self.send(), reverse("feedback_sent"))
        self.assertEqual(Feedback.objects.count(), 6)

    def test_mistakes_do_not_count(self):
        for _ in range(5):
            self.send(text="")
        self.assertRedirects(self.send(), reverse("feedback_sent"))

    def test_the_robots_box_counts_too(self):
        for _ in range(5):
            self.send(website="http://spam.example")
        self.assert_refused(self.send(), TOO_MANY_AN_HOUR)
        self.assertFalse(Feedback.objects.exists())

    def test_the_robots_box_seems_sent_past_the_limit_too(self):
        # Cross review of spec #633 (P5): acceptance 29 holds whatever the count.
        for _ in range(5):
            self.send()
        response = self.send(website="http://spam.example")
        self.assertRedirects(response, reverse("feedback_sent"))
        self.assertEqual(Feedback.objects.count(), 5)

    def test_the_address_is_the_last_one_forwarded(self):
        for _ in range(5):
            self.send(forwarded="1.1.1.1, 9.9.9.9")
        self.assert_refused(self.send(forwarded="2.2.2.2, 9.9.9.9"), TOO_MANY_AN_HOUR)

    def test_two_addresses_behind_the_same_proxy_count_apart(self):
        for _ in range(5):
            self.send(forwarded="8.8.8.8")
        self.assert_refused(self.send(forwarded="8.8.8.8"), TOO_MANY_AN_HOUR)
        self.assertRedirects(self.send(forwarded="7.7.7.7"), reverse("feedback_sent"))

    def test_the_count_keeps_no_address_as_typed(self):
        self.send(forwarded="203.0.113.7")
        with connection.cursor() as cursor:
            cursor.execute("SELECT cache_key FROM password_reset_limits")
            keys = [row[0] for row in cursor.fetchall()]
        self.assertTrue(keys)
        self.assertFalse([key for key in keys if "203.0.113.7" in key])

    def make_kept(self, count, days_ago=0):
        Feedback.objects.bulk_create(Feedback(text="之前的") for _ in range(count))
        if days_ago:
            Feedback.objects.update(created_at=timezone.now() - timedelta(days=days_ago))

    def test_the_hundred_and_first_today_is_refused_with_the_words_kept(self):
        self.make_kept(100)
        response = self.send()
        self.assert_refused(response, TOO_MANY_TODAY)
        self.assertContains(response, "hearwellweb@gmail.com")
        self.assertEqual(Feedback.objects.count(), 100)

    def test_a_day_is_taipeis(self):
        # 2026-11-16 23:30 in Taipei is 15:30 UTC; the next day starts half an hour later there.
        evening = datetime(2026, 11, 16, 15, 30, tzinfo=UTC)
        with mock.patch("django.utils.timezone.now", return_value=evening):
            self.make_kept(100)
        with mock.patch("django.utils.timezone.now", return_value=evening + timedelta(minutes=45)):
            self.assertRedirects(self.send(), reverse("feedback_sent"))


class RefusingBackend(BaseEmailBackend):
    """A mail service that answers with an error, as Resend's can."""

    def send_messages(self, messages):
        raise OSError(f"Resend refused {messages[0].to[0]}")


ADMIN_LIST = "https://testserver/admin/screening/feedback/"


class FeedbackNoticeTests(TestCase):
    """Spec #633 (#638, acceptance 32-36): the first 意見回饋 of a Taipei day sends the owner one
    回饋通知信, with the admin list's link and nothing that was sent."""

    def setUp(self):
        caches["password_reset"].clear()

    def send(self, text="字太小了", **data):
        return self.client.post(reverse("feedback"), {"text": text, **data})

    def test_the_first_today_sends_one_notice_with_only_the_admin_link(self):
        self.send(text="報告印不出來", email="wang@example.com", page="health_report")
        (notice,) = mail.outbox
        self.assertEqual(notice.to, ["hearwellweb@gmail.com"])
        self.assertEqual(notice.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertIn(ADMIN_LIST, notice.body)
        for sent in ("報告印不出來", "wang@example.com", "聽力報告"):
            with self.subTest(sent=sent):
                self.assertNotIn(sent, notice.subject)
                self.assertNotIn(sent, notice.body)

    def test_the_rest_of_the_day_sends_none(self):
        for text in ("一", "二", "三"):
            self.send(text=text, REMOTE_ADDR=f"10.0.0.{len(mail.outbox) + len(text)}")
        self.assertEqual(Feedback.objects.count(), 3)
        self.assertEqual(len(mail.outbox), 1)

    def test_a_taipei_day_later_one_more(self):
        # 2026-11-16 23:30 in Taipei is 15:30 UTC; 45 minutes later it is the 17th there.
        evening = datetime(2026, 11, 16, 15, 30, tzinfo=UTC)
        with mock.patch("django.utils.timezone.now", return_value=evening):
            self.send()
        with mock.patch("django.utils.timezone.now", return_value=evening + timedelta(minutes=45)):
            self.send(REMOTE_ADDR="10.0.0.2")
        self.assertEqual(len(mail.outbox), 2)

    def test_a_day_is_noticed_once_even_at_the_same_moment(self):
        # Two sent together both find no notice yet; only the one that writes the day sends.
        FeedbackNotice.objects.create(day=timezone.localdate())
        self.send()
        self.assertEqual(mail.outbox, [])
        with self.assertRaises(IntegrityError), transaction.atomic():
            FeedbackNotice.objects.create(day=timezone.localdate())

    def test_one_kept_just_before_midnight_is_noticed_on_its_own_day(self):
        # Cross review of spec #633 (P3): kept at 23:59:59, its notice goes a moment past
        # midnight; it uses its own day, so the next day's first one still sends.
        before = datetime(2026, 11, 16, 15, 59, 59, tzinfo=UTC)  # 23:59:59 in Taipei
        after = before + timedelta(seconds=2)
        feedback = Feedback.objects.create(text="字太小了")
        Feedback.objects.filter(pk=feedback.pk).update(created_at=before)
        feedback.refresh_from_db()
        with mock.patch("django.utils.timezone.now", return_value=after):
            feedback_views.notify_owner(RequestFactory().get("/"), feedback)
            self.send(REMOTE_ADDR="10.0.0.4")
        self.assertEqual(
            list(FeedbackNotice.objects.order_by("day").values_list("day", flat=True)),
            [date(2026, 11, 16), date(2026, 11, 17)],
        )
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(EMAIL_BACKEND=f"{__name__}.RefusingBackend")
    def test_a_notice_that_cannot_be_sent_keeps_the_feedback_and_tells_sentry(self):
        with self.assertLogs("screening.views.feedback", "ERROR") as logs:
            response = self.send(text="報告印不出來", email="wang@example.com")
        self.assertRedirects(response, reverse("feedback_sent"))
        self.assertEqual(Feedback.objects.get().text, "報告印不出來")
        (record,) = logs.records
        self.assertIsNotNone(record.exc_info)
        self.assertNotIn("報告印不出來", record.getMessage())
        self.assertNotIn("wang@example.com", record.getMessage())
        self.assertEqual(record.args, ())

    def test_one_refused_for_the_hour_sends_nothing(self):
        for _ in range(5):
            self.send(website="http://spam.example")
        self.assertContains(self.send(), "這一小時送太多次了")
        self.assertEqual(mail.outbox, [])

    def test_nothing_kept_sends_nothing(self):
        self.send(website="http://spam.example")
        self.send(text="")
        Feedback.objects.bulk_create(Feedback(text="之前的") for _ in range(100))
        self.send(REMOTE_ADDR="10.0.0.3")
        self.assertEqual(mail.outbox, [])


class FeedbackPrivacyTests(TestCase):
    """Spec #633 (#641, acceptance 44-47, ADR 0064): the privacy notice says how 意見回饋 is kept,
    in the owner's approved words; the date moves but the version stays 8."""

    def setUp(self):
        page = self.client.get(reverse("privacy")).content.decode()
        self.main = page[page.index("<main") : page.index("</main>")]

    def part(self, title_id, next_id):
        return self.main[self.main.index(f'id="{title_id}"') : self.main.index(f'id="{next_id}"')]

    def test_a_part_of_its_own_after_the_question_log(self):
        self.assertIn('<h2 id="feedback-title" class="fold-row-title">意見回饋</h2>', self.main)
        self.assertLess(
            self.main.index('id="question-log-title"'), self.main.index('id="feedback-title"')
        )
        self.assertLess(
            self.main.index('id="feedback-title"'), self.main.index('id="storage-title"')
        )

    def test_it_says_what_is_kept_anonymously_how_long_and_how_to_delete(self):
        part = test_layout._text(self.part("feedback-title", "storage-title"))
        for words in (
            "您寫的內容",
            "您填的 email（有填才有）",
            "您是從哪一種頁面過來的，例如「結果頁」（不含網址）",
            "送出的時間",
            "意見回饋是匿名的：不記錄您的帳號、IP 位址",
            "「下載我的資料」不包含意見回饋",
            "我們會提早刪除那一則",
            "請寫信到 hearwellweb@gmail.com，附上當時填的 email",
            "請不要在意見回饋裡輸入姓名、電話、身分證字號、病歷號碼",
            "通知信給營運者，信裡不包含您寫的內容和 email",
        ):
            with self.subTest(words=words):
                self.assertIn(words, part)

    def test_the_days_and_the_hour_are_the_programs(self):
        part = test_layout._text(self.part("feedback-title", "storage-title"))
        self.assertIn(f"意見回饋保存 {FEEDBACK_KEPT_FOR.days} 天後自動刪除", part)
        self.assertEqual(RESET_WINDOW, 60 * 60)
        self.assertIn("IP 位址換算過的代碼（不是原文），一小時後自動清除", part)
        # Cross review of spec #633 (P4): the hour's count is the program's too.
        self.assertIn(f"同一個網路每小時最多送 {FEEDBACKS_PER_ADDRESS} 次", part)
        storage = self.part("storage-title", "recipients-title")
        self.assertIn(f"<li>意見回饋保存 {FEEDBACK_KEPT_FOR.days} 天後自動刪除。</li>", storage)
        self.assertIn("超過 90 天的提問紀錄和意見回饋），在備份中最多再保留 10 天", storage)

    def test_why_it_is_kept(self):
        why = self.part("why-title", "collected-title")
        self.assertIn("<li>看大家在意見回饋寫了什麼，修正網站，並回覆想收到回覆的人。</li>", why)

    def test_the_forgot_password_part_still_holds(self):
        part = test_layout._text(self.part("password-reset-title", "question-log-title"))
        # #664 (spec #656) replaced 「網站不寄其他信」 with the email 重測提醒
        # (test_reminder_privacy).
        self.assertIn("只有您自己申請時才寄。", part)

    def test_the_date_moved_and_the_version_stayed(self):
        # It stayed 8; spec #733 raised it to 9 for the 整體統計 (test_aggregate_statistics).
        self.assertGreaterEqual(models.CONSENT_VERSION, 8)
        self.assertGreaterEqual(models.PRIVACY_UPDATED_ON, date(2026, 11, 16))
        updated_on = f"{models.PRIVACY_UPDATED_ON:%Y/%m/%d}"
        self.assertIn(f"第 {models.CONSENT_VERSION} 版，{updated_on} 更新", self.main)

    def test_who_agreed_before_the_date_moved_is_not_asked_again(self):
        user = User.objects.create_user(username="feedback_agreed_before")
        Consent.objects.create(user=user, version=models.CONSENT_VERSION)
        Consent.objects.filter(user=user).update(agreed_at=timezone.now() - timedelta(days=30))
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("my_hearing")).status_code, 200)


REMINDER = (
    "這裡不是諮詢，不會馬上回覆。您寫的內容會匿名保存 90 天，"
    "請不要輸入姓名、電話、身分證字號、病歷號碼。"
)
SENT_LINE = "我們會看每一則意見，但不一定會回覆。有填 email 的，需要時會寫信給您。"


class OwnersWordsTests(TestCase):
    """Spec #633 (#642, acceptance 11, 48): the owner's words from #635, as they were chosen."""

    def test_the_reminder_comes_before_the_urgent_box(self):
        page = self.client.get(reverse("feedback")).content.decode()
        self.assertIn(f'<p class="tip-box">{REMINDER}</p>', page)
        self.assertLess(page.index(REMINDER), page.index("突然聽不到、耳朵流血？請盡快就醫"))

    def test_the_sent_page_says_what_happens_next(self):
        response = self.client.get(reverse("feedback_sent"))
        self.assertContains(response, f"<p>{SENT_LINE}</p>")

    def test_the_notice_says_one_a_day(self):
        self.client.post(reverse("feedback"), {"text": "字太小了"})
        (notice,) = mail.outbox
        self.assertEqual(notice.subject, "聽伴：有新的意見回饋")
        self.assertEqual(
            notice.body,
            f"今天有新的意見回饋，到後台看：\n{ADMIN_LIST}\n今天之後的回饋不會再寄信通知。\n",
        )


# Spec #633 (self-review): addresses that never show a page with the footer, so no feedback link
# names them: redirects, form addresses, files and what only machines read.
NOT_PAGES = {
    "sitemap",
    # Spec #702: 存下來 on the import preview only saves and goes on to the audiogram's page.
    "audiogram_import_save",
    "robots_txt",
    "uptime_check",
    "monitoring_test",
    "logout",
    "google_start",
    "google_callback",
    "google_save_card",
    "google_add",
    "line_start",
    "line_callback",
    "line_save_card",
    "line_add",
    "qa_search",
    "route_answer",
    "report_share_create",
    "report_share_cancel",
    "download_my_data",
    "retest_reminder",
    # Sends the 確認信 again and goes back to account settings (security check 2026-11-19).
    "email_confirm_resend",
    # A 小卡網址 only sends the scan on to its landing page (spec #677).
    "clinic_card_elder",
    "clinic_card_family",
    # The cards' print page has no footer, only the sheet to print (spec #677).
    "clinic_cards",
}


class PageNamesTests(TestCase):
    """Spec #633 acceptance 10, 23 (self-review): every page with the footer has words for
    「您是從…過來的」, so none sends feedback without saying where from."""

    def test_every_page_is_named(self):
        names = {pattern.name for pattern in screening_urls.urlpatterns if pattern.name}
        named = set(feedback_views.PAGE_NAMES) | set(NAMED_BY_CODE)
        self.assertEqual(names - named - NOT_PAGES, set())
        self.assertEqual(NOT_PAGES - names, set())
        self.assertEqual(NOT_PAGES & named, set())

    def test_an_audiogram_page_is_named_without_its_number(self):
        for page, words in (
            ("audiogram_detail", "聽力圖"),
            ("audiogram_speech_banana", "聽力圖的語言香蕉區"),
        ):
            with self.subTest(page):
                self.client.post(reverse("feedback"), {"text": "看不懂", "page": page})
                self.assertEqual(Feedback.objects.latest("pk").page, words)


def feedback_link(response):
    """The footer's 意見回饋 link on a page, as a browser would follow it."""
    found = re.search(r'<a href="(/feedback\?[^"]*)">', footer_of(response))
    return html.unescape(found.group(1))


class FromARealFooterTests(TestCase):
    """Cross review of spec #633 (acceptance 23, 24): from each page's own footer to a row kept,
    with no record number, share code or address in it."""

    fixtures = ("questions_fixture.json",)

    def send_from(self, url, signed_in=None):
        if signed_in:
            self.client.force_login(signed_in)
        link = feedback_link(self.client.get(url))
        form = self.client.get(link)
        self.assertEqual(form.status_code, 200)
        query = parse_qs(urlparse(link).query)
        data = {"text": "這頁看不懂", **{key: values[0] for key, values in query.items()}}
        response = self.client.post(reverse("feedback"), data, REMOTE_ADDR="10.9.0.1")
        self.assertEqual(response.status_code, 302)
        return Feedback.objects.latest("pk")

    def assert_kept_words_only(self, feedback, words, *secrets):
        self.assertEqual(feedback.page, words)
        values = " ".join(
            str(value) for value in Feedback.objects.values().get(pk=feedback.pk).values()
        )
        for secret in secrets:
            with self.subTest(secret=secret):
                self.assertNotIn(secret, values)

    def test_from_a_result_page(self):
        user = consented_user(username="footer_result")
        submission = submission_with_answers(user, "hhie-s", [4] * 10)
        feedback = self.send_from(reverse("result", args=[submission.pk]), signed_in=user)
        self.assert_kept_words_only(feedback, "結果頁", f"/submission/{submission.pk}")

    def test_from_an_audiogram_page(self):
        user = consented_user(username="footer_audiogram")
        audiogram = Audiogram.objects.create(user=user, tested_on=date(2026, 1, 10))
        feedback = self.send_from(reverse("audiogram_detail", args=[audiogram.pk]), signed_in=user)
        self.assert_kept_words_only(feedback, "聽力圖", f"/audiograms/{audiogram.pk}")

    def test_from_a_shared_report_page(self):
        share = ReportShare.objects.create(user=consented_user(username="footer_share"))
        feedback = self.send_from(reverse("shared_report", args=[share.token]))
        self.assert_kept_words_only(feedback, "家人看的聽力報告", share.token)

    def test_from_a_question_page(self):
        feedback = self.send_from(reverse("qa_answer", args=["sudden-hearing-loss"]))
        self.assert_kept_words_only(
            feedback, "問答小助手：突然聽不到、耳朵流血，該怎麼辦？", "/qa/sudden-hearing-loss"
        )


class FormDetailsTests(TestCase):
    """Cross review of spec #633 (acceptance 9, 12, 14, 16, 19, 22, 25): the evidence asked for."""

    def page(self):
        return self.client.get(reverse("feedback")).content.decode()

    def test_one_box_one_optional_email_one_button(self):
        page = self.page()
        self.assertEqual(len(re.findall(r'<textarea[^>]*name="text"', page)), 1)
        emails = re.findall(r'<input[^>]*name="email"[^>]*>', page)
        self.assertEqual(len(emails), 1)
        self.assertNotIn("required", emails[0])
        main = page[page.index("<main") : page.index("</main>")]
        self.assertEqual(re.findall(r"<button[^>]*>([^<]*)</button>", main), ["送出"])

    def test_signed_in_the_email_box_is_empty(self):
        self.client.force_login(consented_user(username="empty_email", email="e@example.com"))
        (email,) = re.findall(r'<input[^>]*name="email"[^>]*>', self.page())
        self.assertIn('value=""', email)

    def test_the_sent_page_has_its_tick(self):
        response = self.client.get(reverse("feedback_sent"))
        self.assertContains(response, '<span aria-hidden="true">✓ </span>已送出，謝謝您')

    def test_an_empty_box_keeps_nothing(self):
        response = self.client.post(reverse("feedback"), {"text": ""})
        self.assertContains(response, "請先寫下想說的話")
        self.assertFalse(Feedback.objects.exists())

    def test_no_way_back_leads_off_the_site(self):
        for next_url in (
            "javascript:alert(1)",
            "\\\\evil.example",
            "http:///evil.example",
            "https:evil",
        ):
            with self.subTest(next_url):
                response = self.client.get(reverse("feedback_sent"), {"next": next_url})
                self.assertContains(
                    response, f'<a class="btn btn-primary btn-lg w-full" href="{reverse("index")}">'
                )
                self.assertNotContains(response, "回到剛才那一頁")

    def test_a_way_off_the_site_is_dropped_when_sending(self):
        response = self.client.post(
            reverse("feedback"), {"text": "字太小了", "next": "https://evil.example/"}
        )
        self.assertRedirects(response, reverse("feedback_sent"))

    def test_signed_in_what_is_kept_is_the_words_email_and_kind(self):
        self.client.force_login(consented_user(username="kept_fields"))
        self.client.post(
            reverse("feedback"),
            {
                "text": "字太小了",
                "email": "k@example.com",
                "page": "result",
                "next": "/submission/9",
            },
        )
        feedback = Feedback.objects.get()
        self.assertEqual(
            (feedback.text, feedback.email, feedback.page, feedback.handled),
            ("字太小了", "k@example.com", "結果頁", False),
        )

    def test_deleting_the_account_on_its_page_leaves_the_feedback(self):
        user = consented_user(
            username="leaving_page", email="lp@example.com", password="Xk9#mPq2vLw"
        )
        self.client.post(reverse("feedback"), {"text": "再見", "email": "lp@example.com"})
        self.client.force_login(user)
        response = self.client.post(reverse("delete_account"), {"password": "Xk9#mPq2vLw"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertEqual(Feedback.objects.get().email, "lp@example.com")
