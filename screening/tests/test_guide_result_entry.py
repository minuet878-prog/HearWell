"""Spec #218, ticket #229: the hearing-aid guide entry on life-impact result pages."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.tests import test_result_next_steps
from screening.tests.helpers import consented_user

# Wording finalised in #220 (E4), written out so a changed definition fails.
GUIDE_LINK = 'href="/guide">看助聽器選配指引</a>'

# The step that recommends a hearing check or assessment, by questionnaire and level
# (0-based): the second step everywhere but HHIE-S's severe level, where it is the first.
GUIDE_STEP = {
    "hhie-s": {"normal": 1, "mild_to_moderate": 1, "severe": 0},
    "hhia-s": {"normal": 1, "mild_to_moderate": 1, "severe": 1},
}


def scores_for(total, count):
    scores = [4] * (total // 4) + [2] * (total % 4 // 2)
    return scores + [0] * (count - len(scores))


class GuideResultEntryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        Question.objects.bulk_create(
            Question(
                questionnaire=hhie_s,
                question_text=f"第{i}題",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.user = consented_user(username="guide_result_user")

    def setUp(self):
        self.client.force_login(self.user)

    def _main(self, code, total):
        questionnaire = Questionnaire.objects.get(code=code)
        questions = list(questionnaire.questions.all())
        submission = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(questions, scores_for(total, len(questions)), strict=True)
        )
        content = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _items(self, main):
        start = main.index('<ol class="next-steps')
        return main[start : main.index("</ol>", start)].split("<li>")[1:]

    def test_the_check_step_links_to_the_guide_after_its_own_link(self):
        # Since the result page tidy-up some check steps have no link of their own, only the guide.
        for code, levels in GUIDE_STEP.items():
            for level, index in levels.items():
                with self.subTest(questionnaire=code, level=level):
                    main = self._main(code, test_result_next_steps.TOTALS[level])
                    item = self._items(main)[index]
                    text, action = test_result_next_steps.STEPS[code][level][index]
                    self.assertIn(f"<span>{text}</span>", item)
                    self.assertIn(GUIDE_LINK, item)
                    if action is None:
                        self.assertEqual(item.count("<a "), 1)
                    else:
                        label, url = action
                        own = f'href="{url}">{label}</a>'
                        self.assertIn(own, item)
                        self.assertLess(item.index(own), item.index(GUIDE_LINK))
                    self.assertEqual(main.count(GUIDE_LINK), 1)

    def test_steps_without_the_guide_link_are_unchanged(self):
        for code, levels in GUIDE_STEP.items():
            for level, guide_index in levels.items():
                with self.subTest(questionnaire=code, level=level):
                    main = self._main(code, test_result_next_steps.TOTALS[level])
                    expected = test_result_next_steps.STEPS[code][level]
                    for index, (item, (text, action)) in enumerate(
                        zip(self._items(main), expected, strict=True)
                    ):
                        if index == guide_index:
                            continue
                        self.assertIn(f"<span>{text}</span>", item)
                        self.assertNotIn('href="/guide"', item)
                        self.assertEqual(item.count("<a "), 0 if action is None else 1)

    def test_thi_is_not_a_life_impact_questionnaire_and_gets_no_guide_link(self):
        for total in (10, 30, 50, 70, 90):
            with self.subTest(total=total):
                self.assertNotIn('href="/guide"', self._main("thi", total))
