"""The questionnaires or audiograms switch on 我的紀錄 and the audiogram list (#270, ADR 0019)."""

import re
from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Audiogram, Question, Questionnaire, Submission
from screening.questionnaires import hhie_s
from screening.tests.helpers import consented_user

QUESTIONNAIRES = f"{reverse('my_hearing')}?view=questionnaires"


class RecordsSwitchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="records_switch")
        cls.other = consented_user(username="records_switch_other")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)
        cls.question = Question.objects.create(
            questionnaire=cls.hhie_s, question_text="第1題", question_number=1
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _submission(self):
        submission = Submission.objects.create(user=self.user, questionnaire=self.hhie_s)
        Answer.objects.create(submission=submission, question=self.question, score=4)
        return submission

    def _audiogram(self, user=None):
        return Audiogram.objects.create(user=user or self.user, tested_on=date(2026, 10, 1))

    def _main(self, response):
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _switch(self, main):
        """(href, text, is current) of each link in the switch, or None without one."""
        match = re.search(r'<nav[^>]*aria-label="紀錄種類"[^>]*>(.*?)</nav>', main, re.S)
        if match is None:
            return None
        links = re.findall(r'<a href="([^"]*)"( aria-current="page")?>([^<]*)</a>', match.group(1))
        return [(href, text, bool(current)) for href, current, text in links]

    def _heading_then_switch(self, main):
        """The h1's text, if the switch comes right after it."""
        match = re.search(r"<h1[^>]*>([^<]*)</h1>\s*<nav[^>]*aria-label=\"紀錄種類\"", main)
        return None if match is None else match.group(1)

    def test_my_hearing_shows_the_switch_under_its_heading_with_questionnaires_current(self):
        submission = self._submission()
        main = self._main(self.client.get(reverse("my_hearing")))
        self.assertEqual(self._heading_then_switch(main), "我的紀錄")
        self.assertEqual(
            self._switch(main),
            [(QUESTIONNAIRES, "問卷", True), (reverse("audiogram_list"), "聽力圖", False)],
        )
        # The questionnaire records stay below the switch.
        self.assertLess(
            main.index('aria-label="紀錄種類"'), main.index(reverse("result", args=[submission.id]))
        )

    def test_audiogram_list_shows_the_switch_under_its_heading_with_audiograms_current(self):
        self._audiogram()
        main = self._main(self.client.get(reverse("audiogram_list")))
        self.assertEqual(self._heading_then_switch(main), "我的紀錄")
        self.assertEqual(
            self._switch(main),
            [(QUESTIONNAIRES, "問卷", False), (reverse("audiogram_list"), "聽力圖", True)],
        )
        # The audiogram list's own buttons and cards stay below the switch.
        self.assertLess(main.index('aria-label="紀錄種類"'), main.index("新增聽力圖"))

    def test_other_audiogram_pages_have_no_switch(self):
        audiogram = self._audiogram()
        self._audiogram()
        urls = (
            reverse("audiogram_new"),
            reverse("audiogram_detail", args=[audiogram.id]),
            reverse("audiogram_compare"),
            reverse("audiogram_edit", args=[audiogram.id]),
            reverse("audiogram_delete", args=[audiogram.id]),
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(self._switch(self._main(response)))

    def test_questionnaires_link_stays_on_the_questionnaire_side(self):
        submission = self._submission()
        self._audiogram()
        response = self.client.get(QUESTIONNAIRES)
        self.assertEqual(response.status_code, 200)
        main = self._main(response)
        self.assertEqual(self._switch(main)[0], (QUESTIONNAIRES, "問卷", True))
        self.assertIn(reverse("result", args=[submission.id]), main)

    def test_only_audiograms_opens_the_audiogram_list(self):
        self._audiogram()
        response = self.client.get(reverse("my_hearing"))
        self.assertRedirects(response, reverse("audiogram_list"))

    def test_questionnaires_link_with_only_audiograms_shows_the_empty_questionnaire_side(self):
        self._audiogram()
        response = self.client.get(QUESTIONNAIRES)
        self.assertEqual(response.status_code, 200)
        main = self._main(response)
        self.assertEqual(self._switch(main)[0], (QUESTIONNAIRES, "問卷", True))
        self.assertIn("<p>您還沒有做過篩檢紀錄</p>", main)

    def test_no_records_keeps_the_empty_prompt(self):
        response = self.client.get(reverse("my_hearing"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("<p>您還沒有做過篩檢紀錄</p>", self._main(response))

    def test_someone_elses_audiograms_do_not_move_me(self):
        self._audiogram(user=self.other)
        response = self.client.get(reverse("my_hearing"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("<p>您還沒有做過篩檢紀錄</p>", self._main(response))

    def test_audiogram_list_keeps_its_address(self):
        self.assertEqual(reverse("audiogram_list"), "/audiograms")
        self.assertEqual(self.client.get("/audiograms").status_code, 200)
