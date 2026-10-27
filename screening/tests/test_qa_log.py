import re

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import NoMatchReason, QuestionLog
from screening.qa_assistant import content
from screening.tests.helpers import consented_user


def main_of(response):
    page = response.content.decode()
    return page[page.index("<main") : page.index("</main>")]


class QuestionLogTests(TestCase):
    """#400 (spec #396, ADR 0034): every typed question kept anonymously, nothing clicked."""

    def ask(self, question, **kwargs):
        return self.client.post(reverse("qa_search"), {"question": question}, **kwargs)

    def test_typing_keeps_the_question_its_first_match_and_when(self):
        before = timezone.now()
        self.ask("耳機補助怎麼申請")
        log = QuestionLog.objects.get()
        self.assertEqual(log.question, "耳機補助怎麼申請")
        self.assertEqual(log.faq_code, "hearing-aid-subsidy")
        self.assertLessEqual(before, log.created_at)
        self.assertLessEqual(log.created_at, timezone.now())
        self.assertEqual(log.reason, "")

    def test_the_first_match_is_the_first_one_shown(self):
        self.ask("助聽器")
        shown = self.client.session["qa_results"]
        self.assertGreater(len(shown), 1)
        self.assertEqual(QuestionLog.objects.get().faq_code, shown[0])

    def test_nothing_matched_is_kept_without_a_question_code(self):
        self.ask("今天天氣如何")
        log = QuestionLog.objects.get()
        self.assertEqual(log.question, "今天天氣如何")
        self.assertEqual(log.faq_code, "")

    def test_each_question_is_its_own_record(self):
        self.ask("耳機補助怎麼申請")
        self.ask("耳機補助怎麼申請")
        self.assertEqual(QuestionLog.objects.count(), 2)

    def test_no_account_address_or_session_is_kept(self):
        self.client.force_login(consented_user(username="qa_log_asker"))
        self.ask("耳機補助怎麼申請", REMOTE_ADDR="203.0.113.7")
        fields = {field.name for field in QuestionLog._meta.get_fields()}
        self.assertEqual(fields, {"id", "question", "faq_code", "created_at", "reason"})
        values = QuestionLog.objects.values().get()
        self.assertNotIn("203.0.113.7", values.values())
        self.assertNotIn("qa_log_asker", values.values())
        self.assertNotIn(self.client.session.session_key, values.values())

    def test_blank_or_too_long_keeps_nothing(self):
        for question in ("", "   ", "耳" * 201):
            with self.subTest(question=question):
                self.assertEqual(self.ask(question).status_code, 200)
                self.assertFalse(QuestionLog.objects.exists())

    def test_clicking_the_lists_keeps_nothing(self):
        faq = content.BY_CODE["hearing-aid-subsidy"]
        pages = (
            reverse("qa_home"),
            reverse("qa_topic", args=[faq.topic]),
            reverse("qa_answer", args=[faq.code]),
            reverse("qa_answer", args=[content.URGENT_CODE]),
        )
        for url in pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertFalse(QuestionLog.objects.exists())

    def test_the_reasons_the_owner_ticks(self):
        # ADR 0035: why a question matched nothing, blank until the owner ticks one.
        self.assertEqual(
            [label for _, label in NoMatchReason.choices],
            ["問法不同", "題庫沒有", "不該回答"],
        )


class QuestionLogReminderTests(TestCase):
    """#400 acceptance 2: the reminder by the box, read with it and at least 1rem."""

    REMINDER = (
        "您打的問題會匿名保存 90 天，用來補充題目；請不要輸入姓名、電話、身分證字號、病歷號碼"
    )

    def test_the_box_says_what_is_kept_and_what_not_to_type(self):
        form = main_of(self.client.get(reverse("qa_home")))
        form = form[form.index('<form method="post"') : form.index("</form>")]
        reminder = re.search(r'<div id="id_question_helptext" class="([^"]+)">(.*?)</div>', form)
        self.assertIsNotNone(reminder)
        self.assertIn("field-help", reminder.group(1).split())
        self.assertIn(self.REMINDER, reminder.group(2))
        self.assertRegex(form, r'<input [^>]*aria-describedby="id_question_helptext"[^>]*id="id_')

    def test_the_reminder_stays_with_a_hint_after_a_blank_question(self):
        response = self.client.post(reverse("qa_search"), {"question": ""})
        form = main_of(response)
        self.assertIn(self.REMINDER, form)
        self.assertIn(
            'aria-invalid="true" aria-describedby="id_question_error id_question_helptext"', form
        )
