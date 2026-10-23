"""Spec #148 batch 2, ticket #157: result page next steps by level."""

from django.test import TestCase
from django.urls import reverse

from screening.models import Answer, Category, Question, Questionnaire, Submission
from screening.questionnaires import hhia_s
from screening.tests.helpers import consented_user, fake_definition, register

RETEST = ("半年後再做一次，時間到了首頁會提醒您。", None)
AUDIOGRAM = ("記錄聽力圖", "/audiograms/new")
REPORT = ("看／印聽力報告", "/report")

# The owner's finalized wording (#156, with the corrections noted there), written out here so a
# changed definition fails instead of being copied into the expectation. A step's own link (the
# guide link after it is test_guide_result_entry's): the report only where its words mention the
# report or this result (result page tidy-up), as the closing row of every result page links it.
STEPS = {
    "hhie-s": {
        "normal": (
            (
                "這次結果顯示您的聽覺自覺障礙程度為無或僅有輕微障礙，暫時沒有明顯影響情緒與社交活動。",
                None,
            ),
            (
                "不過高齡族群的聽力退化通常不容易自己察覺；如果還沒做過聽力檢查，"
                "建議至醫院進行定期篩檢。",
                AUDIOGRAM,
            ),
            RETEST,
        ),
        "mild_to_moderate": (
            (
                "聽力問題已經慢慢影響您的社交活動與情緒，例如與家人因聽不清楚而起爭執、"
                "在吵雜場合感到窘迫而退縮。",
                None,
            ),
            (
                "這次篩檢能讓您體認到聽力對生活的影響，建議前往醫院耳鼻喉科進行聽力相關檢查，"
                "並詢問專業意見。",
                None,
            ),
            RETEST,
        ),
        "severe": (
            (
                "聽力問題已經嚴重影響到您的生活了，若您尚未採取任何行動，"
                "建議立即前往醫院耳鼻喉科尋求專業建議，並考慮配戴助聽器。",
                None,
            ),
            (
                "聽力喪失影響的並不只是聽不聽得到，無形中也會增加社交活動的壓力，"
                "這些壓力以及情緒的低落會增加長者的認知負擔。",
                None,
            ),
            RETEST,
        ),
    },
    "hhia-s": {
        "normal": (
            ("您這次回報的生活影響較少。", None),
            ("如果您仍覺得聽不清楚，建議安排聽力評估。", AUDIOGRAM),
            RETEST,
        ),
        "mild_to_moderate": (
            ("您回報的聽力困擾已經影響部分日常生活。", None),
            ("建議安排聽力評估，並帶這份結果與聽力師或耳鼻喉科醫師討論。", REPORT),
            RETEST,
        ),
        "severe": (
            ("您回報的聽力困擾對生活有顯著影響。", None),
            ("建議儘早安排聽力評估，與聽力師或耳鼻喉科醫師討論適合您的協助方式。", None),
            RETEST,
        ),
    },
}

HHIA_S_NOTE = (
    "這份問卷反映您感受到的生活影響，不能判定聽損程度，也不能單憑分數決定是否需要助聽器。"
    " 已配戴助聽器者，可帶結果回原聽力照護單位討論。"
)
# The advice as it read before #157, unchanged ("完整建議").
ADVICE = {
    "hhie-s": {
        "normal": (
            "您的聽覺自覺障礙程度為無或是僅有輕微障礙，聽力的部分並未明顯影響"
            "您的情緒以及社交活動，然而高齡族群的聽力退化往往是較無自覺的，"
            "建議若未進行過聽力檢查能夠至醫院進行定期篩檢。"
        ),
        "mild_to_moderate": (
            "聽力的問題已經慢慢開始影響到您的社交活動以及情緒，例如"
            "與家人之間常常因為聽不清楚或是電視聲音等而產生爭吵、在多人且吵雜的"
            "社交環境當中會因為聽不清楚而導致社交上的窘迫及退縮，許多聽力衰退"
            "帶來的問題是微妙且和緩的，但經過此次篩檢能夠讓您體認到聽力對自身生"
            "活的影響，建議前往醫院耳鼻喉科進行聽力相關檢查及詢問相關專業意見。"
        ),
        "severe": (
            "聽力問題已經嚴重影響到您的生活了，許多人常常會忽視這一塊，聽不到這件事"
            "情往往已經十分嚴重了才會發現，若您尚未採取任何行動建議立即前往醫院耳鼻"
            "喉科尋求專業建議，並且考慮配戴助聽器。聽力喪失影響的並不只是聽不聽得到，"
            "無形中也會增加社交活動的壓力（例如因為聽不清楚常會在聊天的過程中退縮、"
            "裝作聽得懂等），這些壓力以及情緒的低落會增加長者的認知負擔。"
        ),
    },
    "hhia-s": {
        "normal": "您這次回報的生活影響較少。若仍有聽不清楚的困擾，建議安排聽力評估。 "
        + HHIA_S_NOTE,
        "mild_to_moderate": (
            "您回報聽力困擾已影響部分日常生活。建議安排聽力評估，"
            "並帶這份結果與聽力師或耳鼻喉科醫師討論。 " + HHIA_S_NOTE
        ),
        "severe": (
            "您回報聽力困擾對生活有顯著影響。建議儘早安排聽力評估，"
            "與聽力師或耳鼻喉科醫師討論適合您的協助方式。 " + HHIA_S_NOTE
        ),
    },
}
UNKNOWN_ADVICE = (
    "這次的作答結果無法判讀分級，可能是資料有誤。建議重新作答一次；"
    "若對聽力有疑慮，請直接諮詢聽力師或耳鼻喉科醫師。"
)
TOTALS = {"normal": 4, "mild_to_moderate": 16, "severe": 32}


class ResultNextStepsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="next_steps_user")
        cls.questionnaires = {}
        for code, name in (("hhie-s", "HHIE-S"), ("hhia-s", "HHIA-S")):
            questionnaire = Questionnaire.objects.create(questionnaire_name=name, code=code)
            Question.objects.bulk_create(
                Question(
                    questionnaire=questionnaire,
                    question_text=f"第{i}題",
                    question_number=i,
                    category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
                )
                for i in range(1, 11)
            )
            cls.questionnaires[code] = questionnaire
        cls.unknown = Questionnaire.objects.create(
            questionnaire_name="未設定門檻問卷", code="unconfigured"
        )
        cls.unknown_question = Question.objects.create(
            questionnaire=cls.unknown, question_text="第一題", question_number=1
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.enterContext(register(fake_definition("unconfigured")))

    def _submit(self, questionnaire, total):
        scores = [4] * (total // 4) + [2] * (total % 4 // 2)
        scores += [0] * (10 - len(scores))
        submission = Submission.objects.create(user=self.user, questionnaire=questionnaire)
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(questionnaire.questions.all(), scores, strict=True)
        )
        return submission

    def _main(self, submission):
        content = self.client.get(reverse("result", args=[submission.id])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _steps(self, main):
        start = main.index('<ol class="next-steps')
        return main[start : main.index("</ol>", start)]

    def test_each_level_shows_its_finalized_steps_and_action_buttons(self):
        for code, levels in STEPS.items():
            for level, expected in levels.items():
                with self.subTest(questionnaire=code, level=level):
                    main = self._main(self._submit(self.questionnaires[code], TOTALS[level]))
                    steps = self._steps(main)
                    items = steps.split("<li>")[1:]
                    self.assertEqual(len(items), len(expected))
                    for item, (text, action) in zip(items, expected, strict=True):
                        self.assertIn(f"<span>{text}</span>", item)
                        if action is None:
                            for _, own_url in (AUDIOGRAM, REPORT):
                                self.assertNotIn(f'href="{own_url}"', item)
                        else:
                            label, url = action
                            self.assertIn(f'href="{url}">{label}</a>', item)

    def test_the_step_list_keeps_its_list_role(self):
        # The steps drop their bullets for the numbered circles, and Safari then stops telling
        # VoiceOver it is a list; role="list" keeps 「清單，共 3 項」, as on the home page's steps.
        main = self._main(self._submit(self.questionnaires["hhie-s"], TOTALS["severe"]))
        self.assertRegex(main, r'<ol class="next-steps[^"]*" role="list">')

    def test_full_advice_is_unchanged_for_every_level(self):
        for code, levels in ADVICE.items():
            for level, advice in levels.items():
                with self.subTest(questionnaire=code, level=level):
                    main = self._main(self._submit(self.questionnaires[code], TOTALS[level]))
                    self.assertIn(f"<p>{advice}</p>", main)

    def test_hhia_s_states_its_limits_under_the_steps_outside_the_folded_advice(self):
        # Text-heavy pages tidy-up: the full advice is folded away, and it was the only place
        # HHIA-S said what the score cannot tell; the owner chose to show that under the steps.
        limits = hhia_s.EXPLANATION
        for level in ("normal", "mild_to_moderate", "severe"):
            with self.subTest(level=level):
                main = self._main(self._submit(self.questionnaires["hhia-s"], TOTALS[level]))
                note = f'<p class="source-note">{limits}</p>'
                self.assertIn(note, main)
                self.assertLess(main.index("</ol>"), main.index(note))
                self.assertLess(main.index(note), main.index("<summary>看完整建議</summary>"))
        main = self._main(self._submit(self.questionnaires["hhie-s"], TOTALS["normal"]))
        self.assertNotIn('class="source-note"', main)

    def test_no_step_list_when_unclassifiable(self):
        submission = Submission.objects.create(user=self.user, questionnaire=self.unknown)
        Answer.objects.create(submission=submission, question=self.unknown_question, score=4)
        with self.assertLogs("screening.scoring", "ERROR"):
            main = self._main(submission)
        self.assertNotIn("接下來建議您", main)
        self.assertNotIn("next-steps", main)
        self.assertIn(f"<p>{UNKNOWN_ADVICE}</p>", main)

    def test_only_own_submission_is_visible(self):
        other = consented_user(username="someone_else")
        hhie_s = self.questionnaires["hhie-s"]
        submission = Submission.objects.create(user=other, questionnaire=hhie_s)
        Answer.objects.create(submission=submission, question=hhie_s.questions.first(), score=4)
        response = self.client.get(reverse("result", args=[submission.id]))
        self.assertEqual(response.status_code, 404)
