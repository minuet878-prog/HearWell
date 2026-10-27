import json
import re
from datetime import date, timedelta

from django.contrib.admin.models import LogEntry
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening import models
from screening.models import Consent, NoMatchReason, QuestionLog, User
from screening.qa_assistant import content
from screening.tests import test_layout
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
                self.assertRedirects(
                    self.ask(question), reverse("qa_home"), fetch_redirect_response=False
                )
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
        response = self.client.post(reverse("qa_search"), {"question": ""}, follow=True)
        form = main_of(response)
        self.assertIn(self.REMINDER, form)
        self.assertIn(
            'aria-invalid="true" aria-describedby="id_question_error id_question_helptext"', form
        )


class QuestionLogAdminTests(TestCase):
    """#400 acceptance 4 and 5 (ADR 0034, 0035): the owner reads the log each month, ticks why a
    question matched nothing and deletes one early; the question and what it matched stay."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(username="qa_log_admin", password="pw")
        cls.matched = QuestionLog.objects.create(
            question="耳機補助怎麼申請", faq_code="hearing-aid-subsidy"
        )
        cls.unmatched = QuestionLog.objects.create(question="今天天氣如何")
        cls.not_in_faq = QuestionLog.objects.create(
            question="哪裡可以修助聽器", reason=NoMatchReason.NOT_IN_FAQ
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.changelist = reverse("admin:screening_questionlog_changelist")

    def change_url(self, log):
        return reverse("admin:screening_questionlog_change", args=[log.pk])

    def rows(self, query=""):
        """{question: the row's text}, in the order listed."""
        page = self.client.get(self.changelist + query).content.decode()
        body = page[page.index("<tbody>") : page.index("</tbody>")]
        return {
            row.group(1): test_layout._text(row.group(0))
            for row in re.finditer(r"<tr>.*?<a href=\"[^\"]+\">([^<]+)</a>.*?</tr>", body, re.S)
        }

    def test_the_list_shows_the_question_result_reason_and_date(self):
        response = self.client.get(self.changelist)
        self.assertEqual(response.status_code, 200)
        headers = re.findall(r'<th scope="col" class="[^"]*column-(\w+)', response.content.decode())
        self.assertEqual(headers, ["question", "result", "reason", "created_at"])
        rows = self.rows()
        self.assertIn("hearing-aid-subsidy", rows["耳機補助怎麼申請"])
        self.assertIn("沒對到", rows["今天天氣如何"])
        self.assertIn("題庫沒有", rows["哪裡可以修助聽器"])
        self.assertIn(str(timezone.localdate(self.matched.created_at).year), rows["今天天氣如何"])

    def test_the_newest_come_first(self):
        self.assertEqual(
            list(self.rows()), ["哪裡可以修助聽器", "今天天氣如何", "耳機補助怎麼申請"]
        )

    def test_filter_what_matched_nothing_and_by_reason(self):
        self.assertEqual(list(self.rows("?matched=no")), ["哪裡可以修助聽器", "今天天氣如何"])
        self.assertEqual(list(self.rows("?matched=yes")), ["耳機補助怎麼申請"])
        self.assertEqual(list(self.rows("?reason__exact=not_in_faq")), ["哪裡可以修助聽器"])
        page = self.client.get(self.changelist).content.decode()
        for label in ("沒對到", "有對到", "問法不同", "題庫沒有", "不該回答"):
            with self.subTest(label=label):
                self.assertRegex(page, rf'<a href="\?[^"]+">{label}</a>')

    def test_only_the_reason_can_change(self):
        response = self.client.get(self.change_url(self.unmatched))
        self.assertEqual(response.status_code, 200)
        form = response.content.decode()
        self.assertIn('<select name="reason"', form)
        for field in ("question", "faq_code", "created_at"):
            with self.subTest(field=field):
                self.assertNotIn(f'name="{field}"', form)
        self.assertIn("今天天氣如何", form)
        response = self.client.post(
            self.change_url(self.unmatched),
            {"reason": "different_wording", "question": "改過的問句", "faq_code": "my-results"},
        )
        self.assertRedirects(response, self.changelist)
        log = QuestionLog.objects.get(pk=self.unmatched.pk)
        self.assertEqual(log.reason, NoMatchReason.DIFFERENT_WORDING)
        self.assertEqual(log.question, "今天天氣如何")
        self.assertEqual(log.faq_code, "")

    def test_the_reason_is_one_of_the_three_or_blank(self):
        response = self.client.post(self.change_url(self.unmatched), {"reason": "other"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(QuestionLog.objects.get(pk=self.unmatched.pk).reason, "")
        self.client.post(self.change_url(self.not_in_faq), {"reason": ""})
        self.assertEqual(QuestionLog.objects.get(pk=self.not_in_faq.pk).reason, "")

    def test_nothing_can_be_added(self):
        add = reverse("admin:screening_questionlog_add")
        self.assertEqual(self.client.get(add).status_code, 403)
        self.assertEqual(self.client.post(add, {"question": "假的"}).status_code, 403)
        self.assertEqual(QuestionLog.objects.count(), 3)

    def test_one_can_be_deleted_early(self):
        delete = reverse("admin:screening_questionlog_delete", args=[self.unmatched.pk])
        self.assertRedirects(self.client.post(delete, {"post": "yes"}), self.changelist)
        self.assertEqual(
            set(QuestionLog.objects.values_list("question", flat=True)),
            {"耳機補助怎麼申請", "哪裡可以修助聽器"},
        )


class QuestionLogAdminHistoryTests(TestCase):
    """ADR 0034 (cross review of #396): the admin's history keeps no copy of what was typed, so
    a question deleted early or after 90 days is gone."""

    def setUp(self):
        self.client.force_login(User.objects.create_superuser(username="qa_log_history"))
        self.changelist = reverse("admin:screening_questionlog_changelist")
        self.logs = [
            QuestionLog.objects.create(question=question)
            for question in ("王小明的病歷號碼", "陳大華的耳朵", "林美玲的助聽器")
        ]

    def assert_no_question_in_the_history(self):
        entries = LogEntry.objects.all()
        self.assertTrue(entries)
        for entry in entries:
            # change_message is JSON with its Chinese escaped, so its text is read as well.
            text = " ".join((entry.object_id, entry.object_repr, entry.change_message, str(entry)))
            for log in self.logs:
                with self.subTest(text=text, question=log.question):
                    self.assertNotIn(log.question, text)

    def test_ticking_the_reason(self):
        change = reverse("admin:screening_questionlog_change", args=[self.logs[0].pk])
        self.client.post(change, {"reason": NoMatchReason.NOT_IN_FAQ})
        self.assert_no_question_in_the_history()

    def test_deleting_one(self):
        delete = reverse("admin:screening_questionlog_delete", args=[self.logs[0].pk])
        self.assertRedirects(self.client.post(delete, {"post": "yes"}), self.changelist)
        self.assert_no_question_in_the_history()

    def test_deleting_those_selected(self):
        response = self.client.post(
            self.changelist,
            {
                "action": "delete_selected",
                "_selected_action": [log.pk for log in self.logs[1:]],
                "post": "yes",
            },
        )
        self.assertRedirects(response, self.changelist)
        self.assertEqual(list(QuestionLog.objects.all()), self.logs[:1])
        self.assert_no_question_in_the_history()


class QuestionLogAdminQueryTests(TestCase):
    """CODING_STANDARDS 15: the log grows each month, its list takes the same queries."""

    def test_two_or_many_questions_take_the_same_queries(self):
        self.client.force_login(User.objects.create_superuser(username="qa_log_owner"))
        changelist = reverse("admin:screening_questionlog_changelist")
        QuestionLog.objects.bulk_create(QuestionLog(question=f"問句 {n}") for n in range(2))
        self.client.get(changelist)  # the first request also looks up what the admin caches
        with CaptureQueriesContext(connection) as two:
            self.assertEqual(self.client.get(changelist).status_code, 200)
        QuestionLog.objects.bulk_create(
            QuestionLog(question=f"多的問句 {n}", faq_code="hearing-aid-subsidy", reason="")
            for n in range(20)
        )
        with self.assertNumQueries(len(two)):
            self.assertEqual(self.client.get(changelist).status_code, 200)


class QuestionLogPrivacyTests(TestCase):
    """#400 acceptance 3 (ADR 0034): the privacy notice says what is kept, why, how long and how
    it goes; the date moves but the version stays, so nobody is stopped to agree again."""

    def setUp(self):
        page = self.client.get(reverse("privacy")).content.decode()
        self.main = page[page.index("<main") : page.index("</main>")]

    def section(self):
        start = self.main.index('<h2 id="question-log-title"')
        return test_layout._text(self.main[start : self.main.index("<h2", start + 1)])

    def test_a_section_on_the_question_log_listed_on_top(self):
        self.assertIn(
            '<h2 id="question-log-title" class="h4 mt-6">問答小助手的提問紀錄</h2>', self.main
        )
        self.assertIn('<li><a href="#question-log-title">問答小助手的提問紀錄</a></li>', self.main)
        # Right after what is collected, so 會交給誰's 上面所有資料 covers it too.
        self.assertLess(
            self.main.index('<h2 id="collected-title"'),
            self.main.index('<h2 id="question-log-title"'),
        )
        self.assertLess(
            self.main.index('<h2 id="question-log-title"'),
            self.main.index('<h2 id="storage-title"'),
        )

    def test_it_says_what_is_kept_why_anonymously_and_for_90_days(self):
        section = self.section()
        for words in (
            "您打的問題原文",
            "找到的第一題（或沒有找到）",
            "提問的時間",
            "從清單點選題目不會記錄",
            "補充問答小助手的題目",
            "提問紀錄是匿名的",
            "不記錄您的帳號、IP 位址",
            "保存 90 天後自動刪除",
            "我們會提早刪除那一筆",
            "「下載我的資料」不包含提問紀錄",
            "請不要在問題裡輸入姓名、電話、身分證字號、病歷號碼",
        ):
            with self.subTest(words=words):
                self.assertIn(words, section)

    def test_the_purpose_and_how_long_are_in_their_sections_too(self):
        # Every statement stays true (privacy.html): 不做上面以外的用途, 保存到您刪除帳號.
        why = self.main[self.main.index('id="why-title"') : self.main.index('id="collected-title"')]
        self.assertIn("<li>看大家在問答小助手怎麼問，補充題目。</li>", why)
        storage = self.main[
            self.main.index('id="storage-title"') : self.main.index('id="recipients-title"')
        ]
        self.assertIn("<li>問答小助手的提問紀錄保存 90 天後自動刪除。</li>", storage)

    def test_the_date_moves_and_the_version_stays(self):
        self.assertEqual(models.PRIVACY_UPDATED_ON, date(2026, 10, 27))
        self.assertEqual(models.CONSENT_VERSION, 2)
        self.assertIn("第 2 版，2026/10/27 更新", self.main)

    def test_who_agreed_before_is_not_asked_again(self):
        user = User.objects.create_user(username="qa_log_agreed_before")
        Consent.objects.create(user=user, version=2)
        Consent.objects.filter(user=user).update(agreed_at=timezone.now() - timedelta(days=30))
        self.client.force_login(user)
        for name in ("my_hearing", "questionnaire_list"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)


class QuestionLogAccountTests(TestCase):
    """#400 acceptance 6 (ADR 0034): not linked to an account, so 下載我的資料 and 刪除帳號
    leave it out, as the privacy notice says."""

    PASSWORD = "Xk9#mPq2vLw"

    def setUp(self):
        self.user = consented_user(username="qa_log_account", password=self.PASSWORD)
        self.client.force_login(self.user)
        self.client.post(reverse("qa_search"), {"question": "耳機補助怎麼申請"})

    def test_the_download_has_no_question_log(self):
        response = self.client.get(reverse("download_my_data"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertNotIn("耳機補助", json.dumps(data, ensure_ascii=False))
        self.assertFalse({"question_log", "question_logs", "questions"} & set(data))

    def test_deleting_the_account_leaves_the_anonymous_log(self):
        self.client.post(reverse("delete_account"), {"password": self.PASSWORD})
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(
            list(QuestionLog.objects.values_list("question", flat=True)), ["耳機補助怎麼申請"]
        )
