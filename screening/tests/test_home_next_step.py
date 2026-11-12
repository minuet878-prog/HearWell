"""#261 (spec #257): the reason for every 目前這一站, on the home page's 現在這一步 card since
#459 (ADR 0042) and on a result page's 建議您下一步. The rest of the home page is
test_home_journey's."""

import re
from dataclasses import replace
from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.fitting_route import fitting_state
from screening.models import (
    Answer,
    Category,
    Question,
    Questionnaire,
    Submission,
)
from screening.questionnaires import hhie_s
from screening.tests import test_guide_summary
from screening.tests.helpers import consented_user

# Spec #291's drafts, one for each stop of the nine-stop route but form 25 (#296); #363
# (spec #354) made four of them say why: the drafts the owner settles on review.
BEFORE_YOU_GO = "因為：第一次去找聽力師前先準備好，看診時比較不會漏問。"
ASSESSMENT = "因為：先確認有沒有身障證明，才知道能不能申請補助。"
FORM_9 = "因為：您已經有身障證明，可以準備申請九號表的助聽器補助。"
NOTICE = "因為：九號表送出後要等公所的核定公文，先了解接下來會發生什麼。"
TYPES_AND_PRICES = "因為：可以看看助聽器的種類與價格，比較之後再買。"
AFTER_FITTING = "因為：記下開始戴的日期，才算得出什麼時候要做使用效益驗證。"
PAYOUT = "因為：驗證做完了，接下來看補助什麼時候發、怎麼發。"

# A result page's 建議您下一步 (#461): title, button link and text.
RESULT_NEXT_STEP = re.compile(
    r'<h2 class="result-next-title">([^<]*)</h2>\s*'
    r'<a class="btn btn-primary btn-lg w-full" href="([^"]*)">([^<]*)</a>',
)


class EveryStopNextStepTests(TestCase):
    """#292 (spec #291 acceptance 21): a reason for every stop of the nine, so the home page
    never fails on one. Stops 4, 5, 6, 8 and 9 need answers the later tickets add, so the
    route's stop is set here on the state the records give: an assessment suggested and not
    fitted, so the 現在這一步 is step 3, the 目前這一站 (#459)."""

    def setUp(self):
        self.user = consented_user(username="every_stop_user")
        self.client.force_login(self.user)
        real_localdate = timezone.localdate

        def localdate(value=None, timezone=None):
            return date(2026, 6, 15) if value is None else real_localdate(value, timezone)

        self.enterContext(patch("django.utils.timezone.localdate", localdate))
        self.answer()

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
        def state_at(user, today):
            return replace(fitting_state(user, today), stop=stop)

        return patch("screening.care_journey.fitting_state", state_at)

    def test_each_stop_on_the_guide_says_why(self):
        # On the home page's card, without 「因為：」 (#458 D10).
        self.make(test_guide_summary.PTA_55, test_guide_summary.PTA_55)
        for stop, because in (
            ("before-you-go", BEFORE_YOU_GO),
            ("assessment", ASSESSMENT),
            ("form-9", FORM_9),
            ("notice", NOTICE),
            ("types-and-prices", TYPES_AND_PRICES),
            ("after-fitting", AFTER_FITTING),
            ("payout", PAYOUT),
        ):
            with self.subTest(stop=stop), self.at(stop):
                content = self.client.get(reverse("index")).content.decode()
                self.assertIn(
                    f'<p class="journey-card-because">{because.removeprefix("因為：")}</p>',
                    content,
                )

    def test_each_reworded_stop_is_a_result_page_s_suggestion_too(self):
        # #363 (spec #354): the reworded stops, on a result page's box. Since #455 (ADR 0042) a
        # result page suggests the 照顧旅程's 現在這一步: here step 3 (an assessment suggested),
        # the stop with the route's own button. 等待核定公文 has no button on the route, so the
        # page suggests sharing instead (spec #453 acceptance 22); 等待補助發放 is never step 3's.
        # #461 (the #460 mockup R1): the result page's box has no 「因為」.
        submission = Submission.objects.get(user=self.user)
        self.make(test_guide_summary.PTA_55, test_guide_summary.PTA_55)
        for stop, expected in (
            ("before-you-go", ("去找聽力師之前", "/guide/before-you-go", "去之前要準備什麼")),
            (
                "after-fitting",
                ("配戴助聽器之後", "/guide/after-fitting#record-title", "記錄配戴的效果"),
            ),
            ("notice", ("分享報告給家人", "/share", "去分享")),
        ):
            with self.subTest(stop=stop), self.at(stop):
                content = self.client.get(reverse("result", args=[submission.pk])).content
                self.assertEqual(RESULT_NEXT_STEP.findall(content.decode()), [expected])
