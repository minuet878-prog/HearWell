"""#261 (spec #257): every 目前這一站 on the home page's 現在這一步 card since #459 (ADR 0044),
each its own card since #745 (the canvas's 照顧旅程展開), and on a result page's 建議您下一步.
The rest of the home page is test_home_journey's, each card's answers test_answer_cards'."""

import re
from dataclasses import replace
from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.fitting_route import GUIDE_PAGE, fitting_state
from screening.models import (
    Answer,
    Category,
    GuideChapterView,
    Question,
    Questionnaire,
    Submission,
)
from screening.questionnaires import hhie_s
from screening.tests import test_guide_summary
from screening.tests.helpers import consented_user

# A result page's 建議您下一步 (#461): title, button link and text.
RESULT_NEXT_STEP = re.compile(
    r'<h2 class="hero-card-title">([^<]*)</h2>\s*'
    r'<a class="btn btn-hero btn-lg" href="([^"]*)">([^<]*)</a>',
)


class EveryStopNextStepTests(TestCase):
    """#292 (spec #291 acceptance 21): a card for every stop of the nine but 助聽器的種類與價格,
    which the home page passes by (ADR 0074), and 等待補助發放, at which step 5 is done, so the
    home page never fails on one. Stops need
    answers the later tickets add, so the route's stop is set here on the state the records
    give: an assessment suggested, my guide opened and not fitted, so the 現在這一步 is step 5,
    the 目前這一站 (#459, #744)."""

    def setUp(self):
        self.user = consented_user(username="every_stop_user")
        self.client.force_login(self.user)
        real_localdate = timezone.localdate

        def localdate(value=None, timezone=None):
            return date(2026, 6, 15) if value is None else real_localdate(value, timezone)

        self.enterContext(patch("django.utils.timezone.localdate", localdate))
        self.answer()
        GuideChapterView.objects.create(user=self.user, chapter=GUIDE_PAGE)

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhie_s,
                question_text=f"HHIE-S題{i}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )

    make = test_guide_summary.GuideSummaryTests.make

    def answer(self):
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.hhie_s, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=0) for question in self.questions
        )

    def at(self, stop):
        # The 補助站 shown too, or the four of them are folded off the route (#596).
        def state_at(user, today):
            state = fitting_state(user, today)
            return replace(state, stop=stop, home_stop=stop, subsidy_shown=True)

        return patch("screening.care_journey.fitting_state", state_at)

    def test_each_stop_has_its_card_with_something_to_press(self):
        # #745: an answer card, a button or entry cards, under the stop's title.
        self.make(test_guide_summary.PTA_55, test_guide_summary.PTA_55)
        for stop, title, thing in (
            ("before-you-go", "去找聽力師之前", "了解須知"),
            ("assessment", "身障鑑定與鑑定醫院", "您有身心障礙證明嗎？"),
            ("form-9", "九號表：申請助聽器補助", "您的九號表完成了嗎？"),
            ("notice", "等待核定公文", "您收到核定公文了嗎？"),
            ("after-fitting", "配戴助聽器之後", "記下開始配戴的日期"),
            ("form-25", "二十五號表：使用效益驗證", "看二十五號表要帶什麼"),
        ):
            with self.subTest(stop=stop), self.at(stop):
                content = self.client.get(reverse("index")).content.decode()
                self.assertIn(f'<h2 class="hero-card-title">{title}</h2>', content)
                self.assertIn(thing, content)

    def test_each_reworded_stop_is_a_result_page_s_suggestion_too(self):
        # #363 (spec #354): the reworded stops, on a result page's box. Since #455 (ADR 0044) a
        # result page suggests the 照顧旅程's 現在這一步: here step 5 (an assessment suggested),
        # the stop with the route's own button. 等待核定公文 has no button on the route, so the
        # page suggests sharing instead (spec #453 acceptance 22).
        # #461 (the #460 mockup R1): the result page's box has no 「因為」. #745: the button or
        # first entry card of the home page's card; where that is an answer card, which the
        # result page does not show, the route's own button.
        submission = Submission.objects.get(user=self.user)
        self.make(test_guide_summary.PTA_55, test_guide_summary.PTA_55)
        for stop, expected in (
            ("before-you-go", ("去找聽力師之前", "/guide/before-you-go", "了解須知")),
            ("assessment", ("身障鑑定與鑑定醫院", "/guide/assessment", "找鑑定醫院")),
            ("form-9", ("九號表：申請助聽器補助", "/guide/form-9", "看九號表的流程")),
            (
                "after-fitting",
                ("配戴助聽器之後", "/guide/after-fitting#stop-question", "記下開始配戴的日期"),
            ),
            ("notice", ("分享報告給家人", "/share", "去分享")),
        ):
            with self.subTest(stop=stop), self.at(stop):
                content = self.client.get(reverse("result", args=[submission.pk])).content
                self.assertEqual(RESULT_NEXT_STEP.findall(content.decode()), [expected])
