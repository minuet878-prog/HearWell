"""Selected HHI comparisons are explicit and persist per questionnaire (#82)."""

import re
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.models import Answer, Question, Questionnaire, Submission
from screening.tests.helpers import consented_user

TAIPEI = ZoneInfo("Asia/Taipei")


def radio_cards(page, name):
    """(text, checked) of each radio card of one group, as the page shows them."""
    found = re.findall(r"<label[^>]*>(<input[^>]*>)\s*(.*?)</label>", page.content.decode(), re.S)
    return [(text.strip(), " checked" in tag) for tag, text in found if f'name="{name}"' in tag]


class HhiComparisonTests(TestCase):
    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.questionnaire = Questionnaire.objects.get(code="hhia-s")
        self.user = consented_user(username="compare_user", password="Test-pass-12345")
        self.other = consented_user(username="compare_other")
        self.client.force_login(self.user)
        self.url = f"/comparisons/{self.questionnaire.pk}"

    def record(self, wearing, score=2, user=None, questionnaire=None):
        questionnaire = questionnaire or self.questionnaire
        record = Submission.objects.create(
            user=user or self.user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=q, score=score)
            for q in questionnaire.questions.all()
        )
        return record

    def test_preview_does_not_save_and_saved_pair_survives_new_records(self):
        unaided = self.record(False, 4)
        aided = self.record(True, 2)
        data = {"unaided": unaided.pk, "aided": aided.pk}
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "聽力報告裡的組合")
        page = self.client.get(self.url, data)
        self.assertContains(page, "目前查看的兩筆")
        self.assertContains(page, "40 分")
        self.assertContains(page, "20 分")
        self.assertNotContains(page, "聽力報告裡的組合")
        response = self.client.post(self.url, {**data, "action": "save"})
        self.assertRedirects(response, self.url)
        self.record(False, 0)
        self.record(True, 0)
        self.client.logout()
        self.client.login(username="compare_user", password="Test-pass-12345")
        page = self.client.get(self.url)
        saved = page.context["saved"]
        self.assertEqual(saved.unaided_id, unaided.pk)
        self.assertEqual(saved.aided_id, aided.pk)
        self.assertContains(page, "聽力報告裡的組合")
        self.assertContains(page, "不一定是開始使用助聽器前後")

    def test_versions_keep_independent_pairs_and_removal_keeps_answers(self):
        hhie = Questionnaire.objects.create(code="hhie-s", questionnaire_name="HHIE-S")
        Question.objects.bulk_create(
            Question(questionnaire=hhie, question_text=f"題{n}", question_number=n)
            for n in range(1, 11)
        )
        first = self.record(False)
        second = self.record(True)
        self.client.post(self.url, {"unaided": first.pk, "aided": second.pk, "action": "save"})
        other_first = self.record(False, questionnaire=hhie)
        other_second = self.record(True, questionnaire=hhie)
        other_url = f"/comparisons/{hhie.pk}"
        self.client.post(
            other_url, {"unaided": other_first.pk, "aided": other_second.pk, "action": "save"}
        )
        replacement = self.record(True, 0)
        self.client.post(self.url, {"unaided": first.pk, "aided": replacement.pk, "action": "save"})
        self.assertEqual(self.client.get(self.url).context["saved"].aided_id, replacement.pk)
        self.assertEqual(self.client.get(other_url).context["saved"].aided_id, other_second.pk)
        count = Answer.objects.count()
        self.client.post(self.url, {"action": "remove"})
        self.assertFalse(
            self.user.report_comparisons.filter(questionnaire=self.questionnaire).exists()
        )
        self.assertEqual(self.user.report_comparisons.count(), 1)
        self.assertEqual(Answer.objects.count(), count)
        self.assertTrue(Submission.objects.filter(pk=second.pk).exists())

    def test_invalid_selections_cannot_replace_saved_pair_or_leak_other_users(self):
        first = self.record(False)
        second = self.record(True)
        data = {"unaided": first.pk, "aided": second.pk, "action": "save"}
        self.client.post(self.url, data)
        stranger = self.record(True, user=self.other)
        unknown = self.record(None)
        incomplete = self.record(True)
        incomplete.answers.first().delete()
        other_questionnaire = Questionnaire.objects.create(
            code="hhie-s", questionnaire_name="HHIE-S"
        )
        Question.objects.bulk_create(
            Question(questionnaire=other_questionnaire, question_text=f"題{n}", question_number=n)
            for n in range(1, 11)
        )
        different = self.record(True, questionnaire=other_questionnaire)
        for bad in (first, stranger, unknown, incomplete, different):
            with self.subTest(record=bad.pk):
                response = self.client.post(self.url, {**data, "aided": bad.pk})
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, 'id="comparison-errors"', status_code=400)
                self.assertEqual(self.user.report_comparisons.get().aided_id, second.pk)
        self.client.force_login(self.other)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.other.report_comparisons.exists())
        self.client.post(self.url, {"action": "remove"})
        self.assertTrue(self.user.report_comparisons.exists())
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_export_and_account_deletion_include_only_own_saved_comparisons(self):
        first = self.record(False, 4)
        second = self.record(True, 2)
        self.client.post(self.url, {"unaided": first.pk, "aided": second.pk, "action": "save"})
        stranger = self.record(False, 0, user=self.other)
        stranger_aided = self.record(True, 0, user=self.other)
        self.client.force_login(self.other)
        self.client.post(
            self.url, {"unaided": stranger.pk, "aided": stranger_aided.pk, "action": "save"}
        )
        self.client.force_login(self.user)
        payload = self.client.get("/my_data/download").json()
        comparisons = payload["report_comparisons"]
        self.assertEqual(len(comparisons), 1)
        self.assertEqual(comparisons[0]["questionnaire"], self.questionnaire.questionnaire_name)
        self.assertEqual(comparisons[0]["unaided"]["total_score"], 40)
        self.assertEqual(comparisons[0]["aided"]["total_score"], 20)
        response = self.client.post("/account/delete", {"password": "Test-pass-12345"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Submission.objects.filter(user_id=self.user.pk).exists())
        self.assertTrue(Submission.objects.filter(pk=stranger.pk).exists())
        self.assertTrue(self.other.report_comparisons.exists())

    def test_query_count_does_not_grow_with_records(self):
        self.record(False)
        self.record(True)
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for _ in range(5):
            self.record(False)
            self.record(True)
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(many), len(few))


class HhiComparisonRadioCardTests(TestCase):
    """The comparison page picks the two records with radio cards (#190)."""

    def setUp(self):
        self.questionnaire = Questionnaire.objects.create(
            code="hhie-s", questionnaire_name="HHIE-S"
        )
        Question.objects.bulk_create(
            Question(questionnaire=self.questionnaire, question_text=f"題{n}", question_number=n)
            for n in range(1, 11)
        )
        self.user = consented_user(username="radio_user")
        self.client.force_login(self.user)
        self.url = f"/comparisons/{self.questionnaire.pk}"

    def record(self, wearing, score, when):
        record = Submission.objects.create(
            user=self.user, questionnaire=self.questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=q, score=score)
            for q in self.questionnaire.questions.all()
        )
        Submission.objects.filter(pk=record.pk).update(created_at=when)
        return record

    def test_cards_show_date_and_score_with_time_on_shared_days_and_none_chosen(self):
        self.record(False, 2, datetime(2026, 4, 20, 10, 30, tzinfo=TAIPEI))
        self.record(False, 4, datetime(2026, 4, 20, 15, 5, tzinfo=TAIPEI))
        self.record(True, 0, datetime(2026, 9, 2, 9, 0, tzinfo=TAIPEI))
        page = self.client.get(self.url)
        self.assertContains(page, "<legend", count=2)
        self.assertContains(page, "沒戴助聽器時</legend>")
        self.assertContains(page, "戴助聽器時</legend>")
        self.assertCountEqual(
            radio_cards(page, "unaided"),
            [("2026/04/20 10:30・20 分", False), ("2026/04/20 15:05・40 分", False)],
        )
        self.assertEqual(radio_cards(page, "aided"), [("2026/09/02・0 分", False)])

    def test_preview_without_javascript_then_button_follows_the_saved_pair(self):
        unaided = self.record(False, 4, datetime(2026, 4, 20, 10, 30, tzinfo=TAIPEI))
        aided = self.record(True, 2, datetime(2026, 9, 2, 9, 0, tzinfo=TAIPEI))
        other_aided = self.record(True, 0, datetime(2026, 9, 9, 9, 0, tzinfo=TAIPEI))
        chosen = {"unaided": unaided.pk, "aided": aided.pk, "action": "preview"}
        # A plain GET form submission, as a browser without JavaScript sends it.
        page = self.client.get(self.url, chosen)
        self.assertContains(page, "目前查看的兩筆")
        self.assertContains(page, "差值不能單獨判定助聽器效益")
        self.assertContains(page, ">放進聽力報告</button>")
        self.assertIn(("2026/04/20・40 分", True), radio_cards(page, "unaided"))
        self.assertIn(("2026/09/02・20 分", True), radio_cards(page, "aided"))
        response = self.client.post(self.url, {**chosen, "action": "save"})
        self.assertRedirects(response, self.url)
        for page in (self.client.get(self.url), self.client.get(self.url, chosen)):
            self.assertContains(page, "這一組已經在聽力報告裡")
            self.assertNotContains(page, 'value="save"')
            self.assertIn(("2026/09/02・20 分", True), radio_cards(page, "aided"))
        page = self.client.get(self.url, {**chosen, "aided": other_aided.pk})
        self.assertContains(page, ">改放這一組到報告</button>")
        self.assertNotContains(page, "這一組已經在聽力報告裡")
        self.assertNotContains(page, "放進聽力報告</button>")

    def test_saved_pair_card_and_removal_keeps_every_answer(self):
        unaided = self.record(False, 4, datetime(2026, 4, 20, 10, 30, tzinfo=TAIPEI))
        aided = self.record(True, 2, datetime(2026, 9, 2, 9, 0, tzinfo=TAIPEI))
        pair = {"unaided": unaided.pk, "aided": aided.pk, "action": "save"}
        page = self.client.post(self.url, pair, follow=True)
        # The flash says it in the card's words.
        self.assertContains(page, "已放進聽力報告，新增紀錄不會自動換掉這一組。")
        self.assertNotContains(page, "自動換組")
        self.assertContains(page, "聽力報告裡的組合")
        self.assertContains(page, "新增紀錄不會自動換掉")
        self.assertContains(page, ">從報告移除</button>")
        answers = Answer.objects.filter(submission__user=self.user).count()
        page = self.client.post(self.url, {"action": "remove"}, follow=True)
        self.assertContains(page, "已從報告移除這一組，原始作答保持不變。")
        self.assertNotContains(page, "聽力報告裡的組合")
        self.assertNotContains(page, "從報告移除</button>")
        self.assertIn(("2026/04/20・40 分", False), radio_cards(page, "unaided"))
        self.assertEqual(Answer.objects.filter(submission__user=self.user).count(), answers)
        self.assertEqual(self.user.submissions.count(), 2)

    def test_missing_choice_keeps_error_summary_linked_to_the_group(self):
        unaided = self.record(False, 4, datetime(2026, 4, 20, 10, 30, tzinfo=TAIPEI))
        self.record(True, 2, datetime(2026, 9, 2, 9, 0, tzinfo=TAIPEI))
        response = self.client.post(self.url, {"unaided": unaided.pk, "action": "save"})
        self.assertContains(response, 'id="comparison-errors"', status_code=400)
        self.assertContains(response, 'href="#id_aided_0">戴助聽器時</a>', status_code=400)
        self.assertContains(response, 'id="id_aided_0"', status_code=400)
        self.assertContains(response, 'aria-describedby="id_aided_error"', status_code=400)
        self.assertContains(response, '<div id="id_aided_error">', status_code=400)
        self.assertIn(("2026/04/20・40 分", True), radio_cards(response, "unaided"))
        self.assertFalse(self.user.report_comparisons.exists())


class WearingComparisonEntryTests(TestCase):
    """One 「比較戴與不戴助聽器」 entry on 我的紀錄 and the result pages (#186)."""

    fixtures = ("questions_fixture.json",)

    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.hhie_s = Questionnaire.objects.get(code="hhie-s")
        self.ssq12 = Questionnaire.objects.get(code="ssq12-tw")
        self.user = consented_user(username="entry_user")
        self.client.force_login(self.user)

    def record(self, questionnaire, wearing, score):
        record = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=q, score=score)
            for q in questionnaire.questions.all()
        )
        return record

    def main(self, url):
        content = self.client.get(url).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def entries(self, questionnaire, result):
        """How many 「比較戴與不戴助聽器」 links its 我的紀錄 tab and a result page show."""
        button = (
            f'href="{reverse("hhi_comparison", args=[questionnaire.pk])}">比較戴與不戴助聽器</a>'
        )
        pages = {
            "我的紀錄": f"{reverse('my_hearing')}?questionnaire={questionnaire.code}",
            "結果頁": reverse("result", args=[result.pk]),
        }
        return {name: self.main(url).count(button) for name, url in pages.items()}

    def test_entry_shows_only_once_a_questionnaire_has_both_wearing_statuses(self):
        hhie_s = self.record(self.hhie_s, False, 2)
        ssq12 = self.record(self.ssq12, False, 6)
        none = {"我的紀錄": 0, "結果頁": 0}
        one = {"我的紀錄": 1, "結果頁": 1}
        self.assertEqual(self.entries(self.hhie_s, hhie_s), none)
        self.assertEqual(self.entries(self.ssq12, ssq12), none)
        # An aided HHIE-S brings HHIE-S's entry only: the condition is per questionnaire.
        self.record(self.hhie_s, True, 0)
        self.assertEqual(self.entries(self.hhie_s, hhie_s), one)
        self.assertEqual(self.entries(self.ssq12, ssq12), none)
        self.record(self.ssq12, True, 8)
        self.assertEqual(self.entries(self.ssq12, ssq12), one)
        for url in (reverse("result", args=[hhie_s.pk]), reverse("result", args=[ssq12.pk])):
            self.assertNotIn("選擇或管理配戴狀態比較", self.main(url))

    def test_hhia_s_entry_follows_the_same_rule(self):
        # Story 23 names HHIA-S too; it shares the result page with HHIE-S.
        hhia_s = Questionnaire.objects.get(code="hhia-s")
        record = self.record(hhia_s, False, 2)
        self.assertEqual(self.entries(hhia_s, record), {"我的紀錄": 0, "結果頁": 0})
        self.record(hhia_s, True, 0)
        self.assertEqual(self.entries(hhia_s, record), {"我的紀錄": 1, "結果頁": 1})

    def test_ssq12_result_page_has_no_choose_questionnaire_button(self):
        ssq12 = self.record(self.ssq12, False, 6)
        main = self.main(reverse("result", args=[ssq12.pk]))
        self.assertNotIn("選擇問卷", main)
        self.assertNotIn(f'href="{reverse("questionnaire_list")}"', main)
