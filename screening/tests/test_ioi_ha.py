import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.db.models import RestrictedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening import scoring
from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.questionnaires import ioi_ha
from screening.tests.helpers import action_cards, consented_user


class IoiHaTests(TestCase):
    """Spec docs/specs/phase-04/phase4_ioi_ha.md, acceptance 1-22."""

    INTRO = "本量表適合已配戴助聽器的人"
    HEARING_AID_PROMPT = "這次填答時，您有沒有戴助聽器？"
    SOURCE = ("原量表：IOI-HA（Cox 等人）", "中譯：林克寰《助聽器選配與驗證》", "CC BY 3.0 台灣")
    NORM_SOURCE = "常模：Cox、Alexander、Beyer（2003）"
    ADVICE = "如有多項低於常模，可以帶這份結果跟您的聽力師討論"
    UNGROUPED_NOTE = "需要一筆完整有效的未配戴 HHIA-S／HHIE-S 紀錄，才能跟常模比較"
    COMPARISONS = ("低於常模", "在範圍內", "高於常模")

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="ioi_user")
        cls.other = consented_user(username="ioi_other")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhie_questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhie_s,
                question_text=f"HHIE題{i}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        cls.ioi_questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.ioi_ha,
                question_text=f"IOI題{i}",
                question_number=i,
                category="",
            )
            for i in range(1, 8)
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.ioi_ha.id])

    def _main(self, response):
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _hhie_s(self, total, wearing, user=None, created_at=None):
        # total must be even: 4s first, then one 2 if needed.
        scores = [4] * (total // 4) + [2] * (total % 4 // 2)
        scores += [0] * (10 - len(scores))
        submission = Submission.objects.create(
            user=user or self.user, questionnaire=self.hhie_s, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(self.hhie_questions, scores, strict=True)
        )
        if created_at is not None:
            Submission.objects.filter(pk=submission.pk).update(created_at=created_at)
        return submission

    def _post(self, scores=(3,) * 7, **extra):
        data = {"form-TOTAL_FORMS": 7, "form-INITIAL_FORMS": 0}
        for i, (question, score) in enumerate(zip(self.ioi_questions, scores, strict=True)):
            data[f"form-{i}-score"] = str(score)
            data[f"form-{i}-question_id"] = str(question.id)
        data.update(extra)
        return self.client.post(self.url, data)

    def _ioi_submission(self):
        return Submission.objects.get(questionnaire=self.ioi_ha)

    def _items(self, main):
        # By question number, wherever the result page groups them (#187).
        items = re.findall(r'<li class="ioi-item">(.*?)</li>', main, re.DOTALL)
        return sorted(items, key=lambda item: int(re.search(r"IOI題(\d+)", item).group(1)))

    # Answering (1-4)
    def test_answer_page_items_and_text(self):
        main = self._main(self.client.get(self.url))
        self.assertEqual(main.count("<fieldset"), 7)
        for i in range(7):
            with self.subTest(form=i):
                for value in range(1, 6):
                    self.assertIn(f'name="form-{i}-score" value="{value}"', main)
                self.assertNotIn(f'name="form-{i}-score" value="0"', main)
        for label in ioi_ha.ITEM_CHOICES[1]:
            self.assertIn(label, main)
        self.assertNotIn("checked", main)
        self.assertNotIn("常常", main)
        self.assertNotIn(self.HEARING_AID_PROMPT, main)
        self.assertNotIn("wearing_hearing_aid", main)
        self.assertIn(self.INTRO, main)
        for part in self.SOURCE:
            self.assertIn(part, main)

    def test_each_item_shows_its_own_choices(self):
        main = self._main(self.client.get(self.url))
        fieldsets = re.findall(r"<fieldset.*?</fieldset>", main, re.DOTALL)
        for number, fieldset in enumerate(fieldsets, start=1):
            with self.subTest(item=number):
                for label in ioi_ha.ITEM_CHOICES[number]:
                    self.assertIn(label, fieldset)

    def test_missing_answer_not_saved_and_answers_kept(self):
        response = self._post(**{"form-6-score": ""})
        self.assertFalse(Submission.objects.filter(questionnaire=self.ioi_ha).exists())
        self.assertContains(response, "還有 1 題沒有回答")
        self.assertContains(
            response,
            '<input type="radio" name="form-0-score" value="3" class="choice-group"'
            ' id="id_form-0-score_2" checked>',
            html=True,
        )

    def test_tampered_score_rejected(self):
        for score in (0, 6):
            with self.subTest(score=score):
                response = self._post(**{"form-0-score": str(score)})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Submission.objects.filter(questionnaire=self.ioi_ha).exists())
                self.assertContains(response, "表單資料有誤")

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}")

    # Grouping (5-12)
    def _group_after_post(self):
        self.assertEqual(self._post().status_code, 302)
        return self._ioi_submission()

    def test_unaided_24_is_mild_moderate(self):
        basis = self._hhie_s(24, wearing=False)
        submission = self._group_after_post()
        self.assertEqual(submission.norm_group, "mild_moderate")
        self.assertEqual(submission.norm_basis, basis)

    def test_unaided_26_is_moderately_severe(self):
        self._hhie_s(26, wearing=False)
        self.assertEqual(self._group_after_post().norm_group, "moderately_severe")

    def test_unaided_0_is_mild_moderate(self):
        self._hhie_s(0, wearing=False)
        self.assertEqual(self._group_after_post().norm_group, "mild_moderate")

    def test_latest_unaided_used_even_if_aided_is_newer(self):
        basis = self._hhie_s(30, wearing=False)
        self._hhie_s(10, wearing=True)
        submission = self._group_after_post()
        self.assertEqual(submission.norm_group, "moderately_severe")
        self.assertEqual(submission.norm_basis, basis)

    def test_latest_of_several_unaided_used(self):
        self._hhie_s(30, wearing=False, created_at=timezone.now() - timedelta(days=9))
        basis = self._hhie_s(10, wearing=False)
        submission = self._group_after_post()
        self.assertEqual(submission.norm_group, "mild_moderate")
        self.assertEqual(submission.norm_basis, basis)

    def test_ungrouped_without_unaided_hhie_s(self):
        cases = {"no HHIE-S": (), "unrecorded": (None,), "aided": (True,), "both": (None, True)}
        for name, statuses in cases.items():
            with self.subTest(case=name):
                Answer.objects.all().delete()
                Submission.objects.all().delete()
                for wearing in statuses:
                    self._hhie_s(10, wearing=wearing)
                submission = self._group_after_post()
                self.assertEqual(submission.norm_group, "ungrouped")
                self.assertIsNone(submission.norm_basis)

    def test_other_users_hhie_s_not_used(self):
        self._hhie_s(30, wearing=False, user=self.other)
        submission = self._group_after_post()
        self.assertEqual(submission.norm_group, "ungrouped")
        self.assertIsNone(submission.norm_basis)

    def test_group_fixed_after_new_hhie_s(self):
        self._hhie_s(10, wearing=False)
        submission = self._group_after_post()
        self._hhie_s(30, wearing=False)
        submission.refresh_from_db()
        self.assertEqual(submission.norm_group, "mild_moderate")
        main = self._main(self.client.get(reverse("result", args=[submission.id])))
        self.assertIn("沒戴助聽器時填的 HHIE-S，10 分", main)

    def test_ungrouped_stays_ungrouped(self):
        submission = self._group_after_post()
        self._hhie_s(30, wearing=False)
        submission.refresh_from_db()
        self.assertEqual(submission.norm_group, "ungrouped")
        main = self._main(self.client.get(reverse("result", args=[submission.id])))
        self.assertIn(self.UNGROUPED_NOTE, main)

    # Result (13-16)
    def test_compare_to_norm_both_groups(self):
        cases = (
            # mild_moderate item 4 (Sat) is 2-4
            ("mild_moderate", 4, 1, "below"),
            ("mild_moderate", 4, 2, "within"),
            ("mild_moderate", 4, 4, "within"),
            ("mild_moderate", 4, 5, "above"),
            # moderately_severe item 3 (RAL) is 2-4, item 1 (Use) is 4-5
            ("moderately_severe", 3, 1, "below"),
            ("moderately_severe", 3, 3, "within"),
            ("moderately_severe", 3, 5, "above"),
            ("moderately_severe", 1, 3, "below"),
            ("moderately_severe", 1, 5, "within"),
        )
        for group, number, score, expected in cases:
            with self.subTest(group=group, item=number, score=score):
                self.assertEqual(scoring.compare_to_norm(group, number, score), expected)

    def test_result_page_marks_each_item(self):
        self._hhie_s(10, wearing=False)
        # mild_moderate: item 2 (3-4) gets 5, item 4 (2-4) gets 1, item 5 (3-4) gets 4.
        response = self.client.get(self._post(scores=(3, 5, 3, 1, 4, 3, 3)).url)
        items = self._items(self._main(response))
        self.assertEqual(len(items), 7)
        self.assertIn("比一般使用者好", items[1])
        self.assertIn("比一般使用者低", items[3])
        self.assertIn("在一般範圍內", items[4])
        self.assertIn(ioi_ha.ITEM_CHOICES[4][0], items[3])

    def test_grouped_result_page(self):
        when = datetime(2026, 10, 1, 4, 0, tzinfo=ZoneInfo("UTC"))
        self._hhie_s(24, wearing=False, created_at=when)
        with self.assertNoLogs("screening.scoring", level="ERROR"):
            response = self.client.get(self._post().url)
        self.assertContains(response, "<title>IOI-HA 結果\uff5cHearWell</title>", html=False)
        main = self._main(response)
        for text in (
            "2026/10/01",
            "24 分",
            self.ADVICE,
            self.NORM_SOURCE,
            *self.SOURCE,
        ):
            with self.subTest(text=text):
                self.assertIn(text, main)
        for text in ("總分", "助聽器：", "無法判讀", "建議前往"):
            with self.subTest(absent=text):
                self.assertNotIn(text, main)

    def test_ungrouped_result_page(self):
        with self.assertNoLogs("screening.scoring", level="ERROR"):
            response = self.client.get(self._post().url)
        main = self._main(response)
        items = self._items(main)
        self.assertEqual(len(items), 7)
        self.assertIn(self.UNGROUPED_NOTE, main)
        for text in self.COMPARISONS:
            self.assertNotIn(text, main)
        self.assertNotIn("總分", main)

    def test_result_page_uses_moderately_severe_norms(self):
        # Item 1 = 3 is within mild_moderate (3-5) but below moderately_severe (4-5).
        self._hhie_s(30, wearing=False)
        main = self._main(self.client.get(self._post().url))
        self.assertIn("沒戴助聽器時填的 HHIE-S，30 分", main)
        items = self._items(main)
        self.assertIn("比一般使用者低", items[0])
        self.assertIn("在一般範圍內", items[1])

    def test_user_records_delete_together_but_basis_not_alone(self):
        basis = self._hhie_s(10, wearing=False)
        self._post()
        basis.answers.all().delete()
        with self.assertRaises(RestrictedError):
            basis.delete()
        Answer.objects.filter(submission__user=self.user).delete()
        Submission.objects.filter(user=self.user).delete()
        self.assertFalse(Submission.objects.filter(user=self.user).exists())

    def test_other_users_result_is_404(self):
        self.client.force_login(self.other)
        self._post()
        submission = self._ioi_submission()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("result", args=[submission.id])).status_code, 404)

    # History, trend chart, API (17-19)
    def test_history_rows(self):
        self._post()
        self._hhie_s(10, wearing=False)
        self._post()
        with self.assertNoLogs("screening.scoring", level="ERROR"):
            main = self._main(self.client.get(reverse("my_hearing")))
        cards = main.split('class="link-card"')[1:]
        ioi_cards = [card for card in cards if "IOI-HA" in card]
        self.assertEqual(len(ioi_cards), 2)
        self.assertIn("輕度至中度", ioi_cards[0])
        self.assertIn("未分組", ioi_cards[1])
        for card in ioi_cards:
            self.assertRegex(card, r"\d{4}/\d{2}/\d{2}")
            for text in ("總分", "助聽器：", "無法判讀"):
                self.assertNotIn(text, card)

    def test_api_lists_only_hhie_s(self):
        hhie = self._hhie_s(10, wearing=False)
        self._post()
        results = self.client.get("/api/submissions/").json()["results"]
        self.assertEqual([item["id"] for item in results], [hhie.id])
        codes = [item["code"] for item in self.client.get("/api/questionnaires/").json()]
        self.assertEqual(codes, ["hhie-s"])

    def test_api_detail_for_ioi_ha_is_404(self):
        self._post()
        submission = self._ioi_submission()
        self.assertEqual(self.client.get(f"/api/submissions/{submission.id}/").status_code, 404)

    # HHIE-S unchanged (20)
    def test_hhie_s_page_and_answers_unchanged(self):
        main = self._main(self.client.get(reverse("screening", args=[self.hhie_s.id])))
        self.assertIn(self.HEARING_AID_PROMPT, main)
        self.assertIn("常常", main)
        self.assertNotIn(self.INTRO, main)
        self.assertNotIn(self.SOURCE[0], main)
        data = {"form-TOTAL_FORMS": 10, "form-INITIAL_FORMS": 0, "wearing_hearing_aid": "False"}
        for i, question in enumerate(self.hhie_questions):
            data[f"form-{i}-score"] = "4"
            data[f"form-{i}-question_id"] = str(question.id)
        for score in ("1", "3", "5"):
            with self.subTest(score=score):
                response = self.client.post(
                    reverse("screening", args=[self.hhie_s.id]), {**data, "form-0-score": score}
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Submission.objects.exists())
        self.client.post(reverse("screening", args=[self.hhie_s.id]), data)
        submission = Submission.objects.get()
        self.assertEqual(submission.norm_group, "")
        self.assertIsNone(submission.norm_basis)
        self.assertEqual(submission.total_answer_score, 40)

    # Entry (21-22)
    def test_questionnaire_list_card(self):
        response = self.client.get(reverse("questionnaire_list") + "?choose=self")
        self.assertContains(response, "<title>選擇問卷\uff5cHearWell</title>")
        main = self._main(response)
        self.assertRegex(
            main, rf'<a[^>]*href="{self.url}"[^>]*>(\s*<[^>]+>)*\s*助聽器使用成效（IOI-HA）'
        )
        # Count and time are tags since phase9_ui_refresh_4b_questionnaire_cards.md 4.1.
        for audience, tags in (
            ("適合已配戴助聽器的人。", ("7 題", "約 2 分鐘")),
            ("適合 65 歲以上的長輩。", ("10 題", "約 3 分鐘")),
        ):
            self.assertIn(audience, main)
            for tag in tags:
                self.assertIn(f'<span class="card-tag">{tag}</span>', main)

    # Spec phase9_ui_refresh_4d_ioi_ha_items.md, acceptance 1-6b.
    # 5 is test_other_users_result_is_404; each _post() makes a new submission with its own page.
    NOTE_SOURCE = "逐題解讀由聽力師依臨床經驗撰寫，不能取代個別諮詢。"

    def _notes_on(self, scores):
        # Notes per item on the result page, None where an item has none.
        items = self._items(self._main(self.client.get(self._post(scores=scores).url)))
        self.assertEqual(len(items), 7)
        return [
            m.group(1) if (m := re.search(r'<p class="ioi-note">(.*?)</p>', item, re.S)) else None
            for item in items
        ]

    # 1
    def test_notes_only_on_items_below_norm(self):
        self._hhie_s(10, wearing=False)  # mild_moderate: 1 is below every item, 3 within
        # Item 4 = 5 is above its norm (2-4): above gets no note either (review a).
        scores = (1, 3, 1, 5, 3, 3, 3)
        items = self._items(self._main(self.client.get(self._post(scores=scores).url)))
        self.assertIn("比一般使用者好", items[3])
        notes = self._notes_on(scores)
        notes_text = scoring.IOI_HA_BELOW_NORM_NOTES
        self.assertEqual(notes, [notes_text[1], None, notes_text[3], None, None, None, None])

    # 2
    def test_each_item_gets_its_own_note(self):
        self._hhie_s(10, wearing=False)
        for number in range(1, 8):
            with self.subTest(item=number):
                scores = [3] * 7
                scores[number - 1] = 1
                expected = [None] * 7
                expected[number - 1] = scoring.IOI_HA_BELOW_NORM_NOTES[number]
                self.assertEqual(self._notes_on(scores), expected)

    # 3
    def test_no_notes_when_nothing_below_norm(self):
        self._hhie_s(10, wearing=False)
        main = self._main(self.client.get(self._post(scores=(3,) * 7).url))
        self.assertNotIn("ioi-note", main)
        for note in scoring.IOI_HA_BELOW_NORM_NOTES.values():
            self.assertNotIn(note, main)

    # 4
    def test_no_notes_when_ungrouped(self):
        main = self._main(self.client.get(self._post(scores=(1,) * 7).url))
        self.assertNotIn("ioi-note", main)
        for note in scoring.IOI_HA_BELOW_NORM_NOTES.values():
            self.assertNotIn(note, main)
        self.assertIn(self.UNGROUPED_NOTE, main)

    # 6
    def test_note_inside_item_after_answer(self):
        self._hhie_s(10, wearing=False)
        items = self._items(self._main(self.client.get(self._post(scores=(1,) + (3,) * 6).url)))
        first = items[0]
        self.assertLess(first.index("您的回答："), first.index(scoring.IOI_HA_BELOW_NORM_NOTES[1]))

    # 6b
    def test_note_source_only_on_ioi_ha_result(self):
        ungrouped = self.client.get(self._post().url)
        self.assertIn(self.NOTE_SOURCE, self._main(ungrouped))
        hhie_s = self._hhie_s(10, wearing=False)
        grouped = self.client.get(self._post().url)
        self.assertIn(self.NOTE_SOURCE, self._main(grouped))
        for page in (reverse("result", args=[hhie_s.id]), self.url):
            with self.subTest(page=page):
                self.assertNotIn(self.NOTE_SOURCE, self._main(self.client.get(page)))

    def test_notes_are_the_confirmed_text(self):
        # Clinical text confirmed by the audiologist (spec 4.2); change it only with their sign-off.
        self.assertEqual(
            scoring.IOI_HA_BELOW_NORM_NOTES,
            {
                1: "您每天戴助聽器的時間比多數使用者短。可能是還不習慣、戴起來不舒服，"
                "或覺得聲音不自然。可以告訴聽力師哪些時候不想戴，請他幫忙調整。",
                2: "在您最想聽清楚的場合，助聽器的幫助比多數使用者少。"
                "可以記下是哪些場合聽不清楚，帶去請聽力師調整設定。",
                3: "戴了助聽器之後，您仍然覺得困難比多數使用者多。吵雜的場合本來就比較難，"
                "可以請聽力師檢查設定，也可以一起練習溝通的技巧。",
                4: "您覺得助聽器值得的程度比多數使用者低。可能是效果不如預期、使用上麻煩，"
                "或花費的考量。把您在意的地方告訴聽力師，一起看看怎麼改善。",
                5: "戴了助聽器後，您的日常生活或工作受到的影響仍比多數使用者多。"
                "可以說說哪些活動最困擾您，請聽力師針對這些情況調整。",
                6: "您覺得聽力困難對身邊的人造成的干擾比多數使用者多。可以和家人聊聊他們的感受，"
                "也可以請家人陪您一起找聽力師討論溝通的方法。",
                7: "助聽器讓您享受生活的程度提升得比多數使用者少。"
                "可以想想有哪些想做、卻因為聽不清楚而放棄的事，和聽力師討論怎麼幫上忙。",
            },
        )


class IoiHaResultRedesignTests(TestCase):
    """Ticket #187 (spec #183, IOI-HA stories 1-11, acceptance 1-2)."""

    BASIS_DAY = datetime(2026, 10, 1, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    ANSWERED_AT = datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    # mild_moderate: item 1 (3-5) and item 6 (3-5) below, item 4 (2-4) above, the rest within.
    TWO_BELOW_ONE_ABOVE = (1, 3, 3, 5, 3, 2, 3)

    setUpTestData = IoiHaTests.__dict__["setUpTestData"]
    _main = IoiHaTests._main
    _hhie_s = IoiHaTests._hhie_s
    _post = IoiHaTests._post

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("screening", args=[self.ioi_ha.id])

    def _result(self, scores, grouped=True):
        if grouped:
            self._hhie_s(24, wearing=False, created_at=self.BASIS_DAY)
        result_url = self._post(scores=scores).url
        Submission.objects.filter(questionnaire=self.ioi_ha).update(created_at=self.ANSWERED_AT)
        return self.client.get(result_url)

    def _below(self, main):
        # The expanded group of items below the norm.
        match = re.search(r'<section class="ioi-below".*?</section>', main, re.S)
        return match.group(0) if match else ""

    def _others(self, main):
        # The collapsed group of every other item.
        match = re.search(r'<details class="ioi-others[^"]*".*?</details>', main, re.S)
        return match.group(0) if match else ""

    def _items(self, html):
        return re.findall(r'<li class="ioi-item[^"]*">(.*?)</li>', html, re.S)

    def _scale(self, item):
        # The 5-cell scale, score 1 to 5: "B" is a norm cell, "*" marks the answer.
        scale = re.search(r'<div class="ioi-scale" aria-hidden="true">(.*?)</div>', item, re.S)
        cells = re.findall(r'<span class="ioi-cell( ioi-cell-band)?">(.*?)</span>', scale.group(1))
        return ["B" * bool(band) + "*" * ("ioi-dot" in inside) or "-" for band, inside in cells]

    def test_title_is_the_topic_with_code_and_date_below(self):
        main = self._main(self._result(self.TWO_BELOW_ONE_ABOVE))
        self.assertRegex(main, r"<h1[^>]*>助聽器使用成效</h1>")
        self.assertIn("IOI-HA・2026/10/15 作答", main)
        self.assertLess(main.index("助聽器使用成效</h1>"), main.index("IOI-HA・2026/10/15"))

    def test_grouped_summary_and_groups(self):
        # Acceptance 1.
        main = self._main(self._result(self.TWO_BELOW_ONE_ABOVE))
        self.assertIn("7 項中，有 2 項比一般使用者低", main)
        self.assertIn("比較對象：一般助聽器使用者中，中間一半的人（常模）", main)
        self.assertIn("分組依據：2026/10/01 沒戴助聽器時填的 HHIE-S，24 分。", main)
        self.assertIn("這是常模比較的分組，不代表聽損程度。", main)
        self.assertNotIn("常模組別", main)

        below = self._below(main)
        self.assertIn("比一般使用者低的 2 項", below)
        self.assertNotIn("<details", below)
        below_items = self._items(below)
        self.assertEqual(len(below_items), 2)
        for item, number, label in (
            (below_items[0], 1, ioi_ha.ITEM_CHOICES[1][0]),
            (below_items[1], 6, ioi_ha.ITEM_CHOICES[6][1]),
        ):
            with self.subTest(item=number):
                self.assertIn(scoring.IOI_HA_ITEM_NAMES[number], item)
                self.assertIn(f"IOI題{number}", item)
                self.assertIn(f"您的回答：{label}", item)
                self.assertIn(scoring.IOI_HA_BELOW_NORM_NOTES[number], item)

        others = self._others(main)
        self.assertIn("其他 5 項", others)
        self.assertNotIn("<details open", others)
        other_items = self._items(others)
        self.assertEqual(len(other_items), 5)
        names = [scoring.IOI_HA_ITEM_NAMES[n] for n in (2, 3, 4, 5, 7)]
        for item, name, number in zip(other_items, names, (2, 3, 4, 5, 7), strict=True):
            with self.subTest(item=number):
                self.assertIn(name, item)
                expected = "比一般使用者好" if number == 4 else "在一般範圍內"
                self.assertIn(expected, item)
                label = ioi_ha.ITEM_CHOICES[number][4 if number == 4 else 2]
                self.assertIn(f"您的回答：{label}", item)
                self.assertNotIn("ioi-note", item)
        # The advice sentence keeps 「低於常模」 word for word; the items no longer say it.
        for old in ("（低於常模）", "在範圍內", "高於常模"):
            with self.subTest(absent=old):
                self.assertNotIn(old, main)

    def test_each_item_has_a_hidden_scale_of_norm_and_answer(self):
        main = self._main(self._result(self.TWO_BELOW_ONE_ABOVE))
        below = self._items(self._below(main))
        others = self._items(self._others(main))
        # Item 1 answered 1 against 3-5, item 4 answered 5 against 2-4,
        # item 2 answered 3 against 3-4.
        self.assertEqual(self._scale(below[0]), ["*", "-", "B", "B", "B"])
        self.assertEqual(self._scale(others[2]), ["-", "B", "B", "B", "*"])
        self.assertEqual(self._scale(others[0]), ["-", "-", "B*", "B", "-"])
        legend = re.search(r'<ul class="trend-legend" aria-hidden="true">(.*?)</ul>', main, re.S)
        self.assertIn("一般使用者的範圍（常模）", legend.group(1))
        self.assertIn("您的回答", legend.group(1))

    def test_screen_readers_get_each_comparison_and_answer_as_text(self):
        # Acceptance: the words carry what the scale shows, even inside the folded group.
        main = self._main(self._result(self.TWO_BELOW_ONE_ABOVE))
        items = self._items(self._below(main)) + self._items(self._others(main))
        expected = (
            (1, "比一般使用者低", 0),
            (6, "比一般使用者低", 1),
            (2, "在一般範圍內", 2),
            (3, "在一般範圍內", 2),
            (4, "比一般使用者好", 4),
            (5, "在一般範圍內", 2),
            (7, "在一般範圍內", 2),
        )
        for item, (number, versus, choice) in zip(items, expected, strict=True):
            with self.subTest(item=number):
                text = re.sub(
                    r'<div class="ioi-scale" aria-hidden="true">.*?</div>', "", item, flags=re.S
                )
                self.assertIn(versus, text)
                self.assertIn(f"您的回答：{ioi_ha.ITEM_CHOICES[number][choice]}", text)

    def _next(self, main):
        match = re.search(r'<section[^>]*aria-labelledby="ioi-next-title".*?</section>', main, re.S)
        return match.group(0)

    def test_ungrouped_has_no_groups_band_or_advice(self):
        # Acceptance 3.
        main = self._main(self._result(self.TWO_BELOW_ONE_ABOVE, grouped=False))
        self.assertIn(IoiHaTests.UNGROUPED_NOTE, main)
        for absent in (
            "比一般使用者",
            "在一般範圍內",
            "項中，有",
            "比較對象",
            "其他 ",
            "ioi-below",
            "ioi-others",
            "ioi-cell-band",
            "ioi-legend-band",
            "一般使用者的範圍",
            "ioi-note",
            IoiHaTests.ADVICE,
        ):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, main)
        items = self._items(main)
        self.assertEqual(len(items), 7)
        for number, item in enumerate(items, start=1):
            with self.subTest(item=number):
                self.assertIn(scoring.IOI_HA_ITEM_NAMES[number], item)
                self.assertIn(f"IOI題{number}", item)
                score = self.TWO_BELOW_ONE_ABOVE[number - 1]
                self.assertIn(f"您的回答：{ioi_ha.ITEM_CHOICES[number][score - 1]}", item)
                expected = ["-"] * 5
                expected[score - 1] = "*"
                self.assertEqual(self._scale(item), expected)
        for text in (IoiHaTests.NORM_SOURCE, IoiHaTests.NOTE_SOURCE, *IoiHaTests.SOURCE):
            with self.subTest(source=text):
                self.assertIn(text, main)

    def test_advice_word_for_word_only_when_grouped(self):
        # Acceptance 4: the sentence shows even with no item below the norm, as before.
        for scores in (self.TWO_BELOW_ONE_ABOVE, (3,) * 7):
            with self.subTest(scores=scores):
                next_steps = self._next(self._main(self._result(scores)))
                self.assertIn(
                    '<p class="mb-0">如有多項低於常模，可以帶這份結果跟您的聽力師討論。</p>',
                    next_steps,
                )

    def test_heading_outline_skips_no_level_and_nests_items_under_their_group(self):
        # Rule 17: each item heading sits one level under its own group, or under the title.
        def outline(main):
            headings = re.findall(r"<h([1-6])[^>]*>(.*?)</h\1>", main, re.S)
            return [(int(level), re.sub(r"<[^>]+>", "", text).strip()) for level, text in headings]

        names = scoring.IOI_HA_ITEM_NAMES
        # #304: the closing cards, under the 建議下一步 (IOI-HA means wearing them: 配戴之後).
        closing = [(2, "了解助聽器選配與補助"), (2, "其他您可以做的")]
        cases = {
            "grouped, two below": (
                self.TWO_BELOW_ONE_ABOVE,
                True,
                [(1, "助聽器使用成效"), (2, "比一般使用者低的 2 項")]
                + [(3, names[n]) for n in (1, 6)]
                + [(2, "其他 5 項")]
                + [(3, names[n]) for n in (2, 3, 4, 5, 7)]
                + [(2, "接下來")]
                + closing,
            ),
            "grouped, none below": (
                (3,) * 7,
                True,
                [(1, "助聽器使用成效"), (2, "其他 7 項")]
                + [(3, names[n]) for n in range(1, 8)]
                + [(2, "接下來")]
                + closing,
            ),
            "ungrouped": (
                self.TWO_BELOW_ONE_ABOVE,
                False,
                # Nothing to take to the audiologist without norms: no 「接下來」 (result pages
                # tidy-up), the closing row of buttons is enough.
                [(1, "助聽器使用成效")] + [(2, names[n]) for n in range(1, 8)] + closing,
            ),
        }
        for case, (scores, grouped, expected) in cases.items():
            with self.subTest(case):
                Answer.objects.all().delete()
                Submission.objects.all().delete()
                self.assertEqual(outline(self._main(self._result(scores, grouped))), expected)

    def test_next_steps_only_when_grouped_with_the_links_in_the_closing_row(self):
        # Result pages tidy-up: the report and records links moved to the row every result page
        # ends with (test_result_pages), so 「接下來」 is only the advice, shown when grouped.
        main = self._main(self._result((3,) * 7, grouped=False))
        self.assertNotIn("ioi-next-title", main)
        self.assertNotIn(IoiHaTests.ADVICE, main)
        Answer.objects.all().delete()
        Submission.objects.all().delete()
        main = self._main(self._result((3,) * 7, grouped=True))
        next_steps = self._next(main)
        self.assertIn(IoiHaTests.ADVICE, next_steps)
        self.assertNotIn("<a ", next_steps)
        self.assertIn(
            (reverse("health_report"), "看／印聽力報告", "可以印出來或存成 PDF"), action_cards(main)
        )


class IoiHaFixtureTests(TestCase):
    def test_fixture_matches_rule_tables(self):
        call_command("loaddata", "questions_fixture.json", verbosity=0)
        self.assertEqual(Questionnaire.objects.get(code="hhie-s").questions.count(), 10)
        questions = Questionnaire.objects.get(code="ioi-ha").questions.all()
        numbers = [question.question_number for question in questions]
        self.assertEqual(numbers, list(range(1, 8)))
        self.assertEqual({question.category for question in questions}, {""})
        self.assertEqual(set(ioi_ha.ITEM_CHOICES), set(numbers))
        for labels in ioi_ha.ITEM_CHOICES.values():
            self.assertEqual(len(labels), 5)
        for group in ("mild_moderate", "moderately_severe"):
            norms = scoring.IOI_HA_NORMS[group]
            self.assertEqual(set(norms), set(numbers))
            for low, high in norms.values():
                self.assertTrue(1 <= low <= high <= 5)
