from datetime import UTC, datetime, timedelta
from unittest import mock

from django.core.cache import caches
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Feedback, ReportShare, User
from screening.tests.helpers import consented_user


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
            reverse("shared_cover", args=[share.token]): "page=shared_cover&amp;next=",
        }
        for url, query in cases.items():
            with self.subTest(url):
                footer = footer_of(self.client.get(url))
                self.assertIn(f'href="{reverse("feedback")}?{query}', footer)

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
