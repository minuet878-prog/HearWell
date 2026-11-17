"""Ticket #696 (spec #693 acceptance 1-4): the life-impact result pages and the guest save card
stop pushing hearing aids; the guest's advice links to where to have the hearing checked."""

import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.questionnaires import hhia_s, hhie_s
from screening.tests import test_guest_save
from screening.tests.helpers import consented_user, submission_with_answers

# The owner's wording in spec #693, written out so a changed definition fails.
GUIDE = "看助聽器選配與補助"
CHECK = "並做聽力檢查；有 AirPods Pro 的話，也可以先用 iPhone 做聽力自我測試。"
LIMITS = "這份問卷反映您感受到的生活影響，不能判定聽損程度，也不能單憑分數決定是否需要助聽器。"
SEVERE_STEP = (
    "聽力問題已經嚴重影響到您的生活了，若您尚未採取任何行動，"
    "建議立即前往醫院耳鼻喉科尋求專業建議，" + CHECK
)
SEVERE_ADVICE = (
    "聽力問題已經嚴重影響到您的生活了，許多人常常會忽視這一塊，聽不到這件事"
    "情往往已經十分嚴重了才會發現，若您尚未採取任何行動建議立即前往醫院耳鼻"
    "喉科尋求專業建議，" + CHECK + "聽力喪失影響的並不只是聽不聽得到，"
    "無形中也會增加社交活動的壓力（例如因為聽不清楚常會在聊天的過程中退縮、"
    "裝作聽得懂等），這些壓力以及情緒的低落會增加長者的認知負擔。"
)
SAVE_REASONS = {
    "mild_to_moderate": "註冊保存後，看完醫師可以接著記下聽力圖，網站會依聽力圖幫您整理下一步。",
    "severe": "註冊保存後，就醫拿到聽力圖可以記下來，網站會依聽力圖幫您整理下一步。",
}
WHERE_TO_TEST_URL = reverse("qa_answer", args=["where-to-get-a-hearing-test"])
WHERE_TO_TEST = f'<a class="next-steps-link" href="{WHERE_TO_TEST_URL}">去哪裡做聽力檢查</a>'
SCORES = {
    "normal": [0] * 10,
    "mild_to_moderate": [4, 4, 2, 0, 0, 0, 4, 0, 0, 2],  # 16
    "severe": [4] * 10,
}
CODES = (hhie_s.CODE, hhia_s.CODE)


class NoAidAdviceResultTests(TestCase):
    fixtures = ("questions_fixture.json",)  # HHIE-S

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())  # HHIA-S
        cls.user = consented_user(username="no_aid_user")

    def setUp(self):
        self.client.force_login(self.user)

    def main(self, code, level):
        submission = submission_with_answers(
            self.user, code, SCORES[level], wearing_hearing_aid=False
        )
        content = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def test_no_level_links_to_the_guide_and_hhie_s_normal_keeps_the_audiogram(self):
        # Acceptance 1.
        for code in CODES:
            for level in SCORES:
                with self.subTest(questionnaire=code, level=level):
                    main = self.main(code, level)
                    self.assertNotIn(GUIDE, main)
                    self.assertNotIn(f'href="{reverse("guide")}"', main)
        main = self.main(hhie_s.CODE, "normal")
        self.assertIn(f'href="{reverse("audiogram_new")}">記錄聽力圖</a>', main)

    def test_hhie_s_severe_says_to_have_the_hearing_checked(self):
        # Acceptance 2: the advice and step 1, the words around them unchanged.
        main = self.main(hhie_s.CODE, "severe")
        self.assertNotIn("考慮配戴助聽器", main)
        self.assertIn(f'<p class="result-one-line">{SEVERE_STEP}</p>', main)
        self.assertIn(f"<p>{SEVERE_ADVICE} {LIMITS}</p>", main)

    def test_hhie_s_states_its_limits_after_the_advice_and_at_the_bottom(self):
        # Acceptance 3: the one sentence HHIA-S has, not its line for those who wear aids.
        for level in SCORES:
            with self.subTest(level=level):
                main = self.main(hhie_s.CODE, level)
                advice = re.search(
                    r"<summary>看完整建議</summary>\s*<p>(.*?)</p>", main, re.S
                ).group(1)
                self.assertTrue(advice.endswith(f"。 {LIMITS}"), advice)
                self.assertNotIn("已配戴助聽器者", advice)
                note = f'<p class="source-note">{LIMITS}</p>'
                self.assertIn(note, main)
                self.assertLess(main.rindex("</details>"), main.index(note))


class NoAidAdviceGuestTests(test_guest_save.GuestSaveTestCase):
    def guest(self, code, level):
        questionnaire = self.hhie_s if code == hhie_s.CODE else self.hhia_s
        return self.guest_html(SCORES[level], questionnaire)

    def test_the_save_card_promises_the_next_step_by_the_audiogram(self):
        # Acceptance 4.
        for code in CODES:
            for level, reason in SAVE_REASONS.items():
                with self.subTest(questionnaire=code, level=level):
                    html = self.guest(code, level)
                    self.assertIn(reason, html)
                    self.assertNotIn("助聽器選配", html)

    def test_the_advice_links_to_where_to_have_the_hearing_checked(self):
        # The #694 mockup, the owner's A: the same step and words as before, its one link now
        # the Q&A answer step 2's 還沒 opens; said once, not again in the fold.
        advice = {
            (hhie_s.CODE, "normal"): hhie_s.NEXT_STEPS["normal"][1]["text"],
            (hhie_s.CODE, "mild_to_moderate"): hhie_s.NEXT_STEPS["mild_to_moderate"][1]["text"],
            (hhie_s.CODE, "severe"): SEVERE_STEP,
            (hhia_s.CODE, "normal"): hhia_s.NEXT_STEPS["normal"][1]["text"],
            (hhia_s.CODE, "mild_to_moderate"): hhia_s.NEXT_STEPS["mild_to_moderate"][1]["text"],
            (hhia_s.CODE, "severe"): hhia_s.NEXT_STEPS["severe"][1]["text"],
        }
        for (code, level), text in advice.items():
            with self.subTest(questionnaire=code, level=level):
                html = self.guest(code, level)
                start = html.index('class="result-advice')
                box = html[start : html.index('class="result-next"', start)]
                self.assertIn(f"<p>{text}</p>", box)
                self.assertEqual(box.count("<a "), 1)
                self.assertIn(WHERE_TO_TEST, box)
                self.assertEqual(html.count(f"<p>{text}</p>"), 1)
                self.assertNotIn(GUIDE, html)
