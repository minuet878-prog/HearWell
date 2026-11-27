"""Ticket #696 (spec #693 acceptance 1-4): the life-impact result pages and the guest save card
stop pushing hearing aids; the guest's advice links to where to have the hearing checked."""

import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.questionnaires import hhia_s, hhie_s
from screening.scoring import get_advice
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
    # The owner's 2026-11-27 walkthrough.
    "mild_to_moderate": "註冊後可記下您的聽力圖，網站會根據您的檢查結果幫您整理下一步。",
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

    def test_no_level_links_to_the_guide(self):
        # Acceptance 1. Its HHIE-S 無／極輕微影響 記錄聽力圖 was step 2's link, which the owner's
        # acceptance of spec #741 (2026-11-21) took off result pages with 看完整建議.
        for code in CODES:
            for level in SCORES:
                with self.subTest(questionnaire=code, level=level):
                    main = self.main(code, level)
                    self.assertNotIn(GUIDE, main)
                    self.assertNotIn(f'href="{reverse("guide")}"', main)
                    self.assertNotIn('class="next-steps-link"', main)

    def test_hhie_s_severe_says_to_have_the_hearing_checked(self):
        # Acceptance 2: the advice and step 1, the words around them unchanged.
        main = self.main(hhie_s.CODE, "severe")
        self.assertNotIn("考慮配戴助聽器", main)
        # Step 1 shown in 這個分數怎麼算 (spec #741, 2026-11-21); the level's whole advice is
        # no longer on result pages since the owner's acceptance that day, only in the report.
        self.assertIn(f'<p class="score-explain-advice">{SEVERE_STEP}</p>', main)
        self.assertEqual(get_advice("severe", hhie_s.CODE), f"{SEVERE_ADVICE} {LIMITS}")
        self.assertNotIn(SEVERE_ADVICE, main)

    def test_hhie_s_states_its_limits_after_the_advice_and_at_the_bottom(self):
        # Acceptance 3: the one sentence HHIA-S has, not its line for those who wear aids.
        for level in SCORES:
            with self.subTest(level=level):
                main = self.main(hhie_s.CODE, level)
                # The advice as the report says it; result pages no longer show it (2026-11-21).
                advice = get_advice(level, hhie_s.CODE)
                self.assertTrue(advice.endswith(f"。 {LIMITS}"), advice)
                self.assertNotIn("已配戴助聽器者", advice)
                note = f'<p class="source-note">{LIMITS}</p>'
                self.assertIn(note, main)
                self.assertLess(main.rindex("</details>"), main.index(note))


def save_card(html):
    """The guest save card's own HTML, from its opening div to the one that closes it."""
    start = html.index('<div class="result-next" data-guest-save-card>')
    depth = 0
    for tag in re.finditer(r"<div\b|</div>", html[start:]):
        depth += 1 if tag.group() == "<div" else -1
        if depth == 0:
            return html[start : start + tag.end()]
    raise AssertionError("the save card is not closed")


class NoAidAdviceGuestTests(test_guest_save.GuestSaveTestCase):
    def guest(self, code, level):
        questionnaire = self.hhie_s if code == hhie_s.CODE else self.hhia_s
        return self.guest_html(SCORES[level], questionnaire)

    def test_the_save_card_promises_the_next_step_by_the_audiogram(self):
        # Acceptance 4 (cross review: said in the card, not anywhere on the page).
        for code in CODES:
            for level, reason in SAVE_REASONS.items():
                with self.subTest(questionnaire=code, level=level):
                    html = self.guest(code, level)
                    self.assertIn(f'<p class="mb-3">{reason}</p>', save_card(html))
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


class NoAidAdviceEducationTests(TestCase):
    """Spec #693 acceptance 16: signed out, the home page, the 了解 tab and the family zone still
    lead to the guide and the hearing-aid education, which anyone may read."""

    def main(self, name):
        content = self.client.get(reverse(name)).content.decode()
        # The footer's 家人專區 is on every page; the entries are the page's own.
        return content[content.index("<main") : content.index("</main>")]

    def test_the_home_page_links_to_the_guide_and_the_family_zone(self):
        main = self.main("index")
        # Spec #741 (#752): the door 想了解助聽器 took the text link's place.
        self.assertIn(f'href="{reverse("guide")}" data-door="door_aids"', main)
        # Spec #655 (#673): the door 我擔心家人的聽力 took 我是家人's place.
        self.assertIn(f'href="{reverse("family_guide")}" data-door="door_family"', main)

    def test_the_learn_tab_links_to_the_guide_and_the_family_zone(self):
        main = self.main("learn")
        for name in ("guide", "family_guide"):
            with self.subTest(link=name):
                self.assertIn(f'class="link-card action-card" href="{reverse(name)}"', main)

    def test_the_family_zone_links_to_living_with_hearing_aids(self):
        main = self.main("family_guide")
        url = reverse("family_hearing_aids")
        self.assertIn(f'class="link-card action-card" href="{url}"', main)
