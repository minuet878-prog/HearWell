"""#455 (spec #453, ADR 0044): the 照顧旅程 judged from a user's records on a given day."""

from datetime import date, datetime

from django.test import TestCase
from django.utils import timezone

from screening.care_journey import (
    CURRENT,
    DONE,
    LATER,
    NOT_NEEDED,
    JourneyCard,
    NextScreening,
    care_journey,
)
from screening.fitting_route import fitting_state
from screening.models import (
    AidAndSubsidy,
    AidLevel,
    Certificate,
    GuideChapterView,
    Questionnaire,
    Submission,
    Subsidy,
)
from screening.questionnaires import hhia_s, hhie_s, ioi_ha, thi
from screening.tests import test_guide_summary
from screening.tests.helpers import consented_user

TODAY = date(2026, 11, 12)
NORMAL = (20, 20, 20, 20)
PTA_55 = test_guide_summary.PTA_55


class CareJourneyTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.questionnaires = {
            code: Questionnaire.objects.create(questionnaire_name=code, code=code)
            for code in (hhie_s.CODE, hhia_s.CODE, ioi_ha.CODE, thi.CODE)
        }

    def setUp(self):
        self.user = consented_user(username="journey_user", birth_year=1950)

    make = test_guide_summary.GuideSummaryTests.make

    def answer(self, code=hhie_s.CODE, on=TODAY, wearing=False):
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.questionnaires[code], wearing_hearing_aid=wearing
        )
        moment = timezone.make_aware(datetime(on.year, on.month, on.day, 12))
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def journey(self, today=TODAY):
        return care_journey(self.user, today)

    def states(self, today=TODAY):
        return [step.state for step in self.journey(today).steps]


class FirstStepsTests(CareJourneyTestCase):
    def test_the_five_steps_are_named_in_order(self):
        self.answer()
        self.assertEqual(
            [step.title for step in self.journey().steps],
            [
                "填生活影響問卷",
                "記錄聽力圖",
                "了解助聽器選配與補助",
                "戴滿 3 個月做效益問卷",
                "半年後再篩檢",
            ],
        )

    def test_only_an_audiogram_makes_step_2_done_and_step_1_current(self):
        # Spec #453 acceptance 2.
        self.make(PTA_55, PTA_55)
        journey = self.journey()
        self.assertEqual(journey.current, 1)
        self.assertEqual(journey.steps[0].state, CURRENT)
        self.assertEqual(journey.steps[1].state, DONE)
        self.assertIsNone(journey.last_result)

    def test_hhie_s_without_an_audiogram_makes_recording_one_current(self):
        # Spec #453 acceptance 3.
        self.answer()
        journey = self.journey()
        self.assertEqual(self.states(), [DONE, CURRENT, LATER, LATER, LATER])
        self.assertEqual(journey.card.button, ("記錄聽力圖", "/audiograms/new"))

    def test_hhia_s_also_finishes_step_1(self):
        # Spec #453 Q7: either life-impact questionnaire.
        self.answer(code=hhia_s.CODE)
        self.assertEqual(self.states()[0], DONE)

    def test_only_thi_leaves_step_1_undone(self):
        # Spec #453 acceptance 4.
        self.answer(code=thi.CODE)
        self.assertEqual(self.journey().current, 1)
        self.assertEqual(self.states()[0], CURRENT)

    def test_an_audiogram_that_cannot_tell_is_step_2_with_editing_it(self):
        # Spec #453 acceptance 5.
        self.answer()
        audiogram = self.make(NORMAL, NORMAL)
        audiogram.points.filter(ear="left", frequency=4000).delete()
        journey = self.journey()
        self.assertEqual(journey.current, 2)
        self.assertEqual(
            journey.card.button, ("修改這張聽力圖", f"/audiograms/{audiogram.pk}/edit")
        )
        self.assertEqual(journey.card.because, "這張聽力圖缺少頻率，資料不足，無法判斷。")


class FittingStepsTests(CareJourneyTestCase):
    def test_the_route_s_stop_is_step_3_s_one_thing_with_its_button(self):
        # Spec #453 acceptance 6: steps 1 and 2 done, an assessment suggested, form 9 the
        # 目前這一站; the card is that stop alone, its button saying where it goes.
        self.answer()
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        AidAndSubsidy.objects.create(user=self.user, certificate=Certificate.YES)
        journey = self.journey()
        self.assertEqual(self.states(), [DONE, DONE, CURRENT, LATER, LATER])
        self.assertEqual(
            journey.card,
            JourneyCard(
                "九號表：申請助聽器補助",
                "您已經有身障證明，可以準備申請九號表的助聽器補助。",
                "guide",
                href="/guide/form-9",
                button=("看九號表的流程", "/guide/form-9"),
            ),
        )

    def test_types_and_prices_gets_a_button_on_the_card(self):
        # The owner on #455 (2026-11-12): the chapter is something to read, so step 3's card
        # has a button for it, though the route itself shows none.
        self.answer()
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        AidAndSubsidy.objects.create(user=self.user, certificate=Certificate.NO_SUBSIDY)
        card = self.journey().card
        self.assertEqual(card.href, "/guide/types-and-prices")
        self.assertEqual(card.button, ("去看助聽器種類與價格", "/guide/types-and-prices"))

    def test_waiting_for_the_notice_has_no_button(self):
        # The owner on #455: there is nothing to do but wait, so no button.
        self.answer()
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        AidAndSubsidy.objects.create(user=self.user, certificate=Certificate.YES, form_9_done=True)
        card = self.journey().card
        self.assertEqual(card.title, "等待核定公文")
        self.assertIsNone(card.button)

    def test_within_the_normal_range_steps_3_and_4_are_not_needed(self):
        # Spec #453 acceptance 7: nothing read or answered on the route.
        self.answer(on=date(2026, 9, 12))
        self.make(NORMAL, NORMAL)
        journey = self.journey()
        self.assertEqual(self.states(), [DONE, DONE, NOT_NEEDED, NOT_NEEDED, CURRENT])
        self.assertEqual(journey.current, 5)

    def test_reading_a_chapter_brings_step_3_back(self):
        # Spec #453 acceptance 8, like the route's 等本人開始.
        self.answer()
        self.make(NORMAL, NORMAL)
        GuideChapterView.objects.create(user=self.user, chapter="types-and-prices")
        self.assertEqual(self.states(), [DONE, DONE, CURRENT, LATER, LATER])

    def test_wearing_without_an_audiogram_or_a_date_asks_for_the_date(self):
        # Spec #453 acceptance 9: from step 3 on, step 2 left unticked.
        self.answer(wearing=True)
        journey = self.journey()
        self.assertEqual(journey.current, 3)
        self.assertEqual(self.states(), [DONE, LATER, CURRENT, LATER, LATER])
        self.assertEqual(
            journey.card.because, "記下開始戴的日期，才算得出什麼時候要做使用效益驗證。"
        )
        self.assertEqual(
            journey.card.button, ("記錄配戴的效果", "/guide/after-fitting#record-title")
        )

    def test_wearing_within_the_normal_range_still_needs_step_3(self):
        # The route does not wait for someone wearing hearing aids (spec #291 Q5), so the
        # journey does not call steps 3 and 4 目前不需要 for them either.
        self.answer(wearing=True)
        self.make(NORMAL, NORMAL)
        self.assertEqual(self.states(), [DONE, DONE, CURRENT, LATER, LATER])

    def fit(self, fitted_on, subsidy=Subsidy.OTHER, level=""):
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=fitted_on, subsidy=subsidy, level=level
        )

    def test_form_25_with_its_deadline_is_step_4_s_one_thing(self):
        # Spec #453 acceptance 10: fitted 2026/10/01 with 身障補助 at 中階型, so form 25 is
        # due by 2027/01/01 and today, 2026/11/12, is within its window.
        self.answer()
        self.fit(date(2026, 10, 1), Subsidy.DISABILITY, AidLevel.MID)
        journey = self.journey()
        self.assertEqual(self.states()[2:4], [DONE, CURRENT])
        self.assertEqual(journey.card.title, "二十五號表：使用效益驗證")
        self.assertEqual(
            journey.card.because,
            "您的助聽器要在 2027/01/01 前做使用效益驗證（二十五號表），才能核銷補助。",
        )
        self.assertEqual(journey.card.button, ("看二十五號表要帶什麼", "/guide/form-25"))

    def test_without_form_25_step_4_counts_down_to_3_months_without_a_button(self):
        # Spec #453 acceptance 11: fitted 40 days ago, 2026/10/03; 3 months is 2027/01/03.
        self.answer()
        self.fit(date(2026, 10, 3))
        journey = self.journey()
        self.assertEqual(journey.current, 4)
        self.assertEqual(
            journey.card.because, "再 52 天滿 3 個月，到時候做使用效益問卷（IOI-HA）。"
        )
        self.assertIsNone(journey.card.button)

    def test_waiting_for_the_payout_is_not_step_4_s_card(self):
        # Spec #453: 簡易型 passes form 25 by, so the route is at 等待補助發放; step 4 counts
        # down instead.
        self.answer()
        self.fit(date(2026, 10, 3), Subsidy.DISABILITY, AidLevel.BASIC)
        self.assertEqual(fitting_state(self.user, TODAY).stop, "payout")
        journey = self.journey()
        self.assertEqual(journey.current, 4)
        self.assertEqual(
            journey.card.because, "再 52 天滿 3 個月，到時候做使用效益問卷（IOI-HA）。"
        )

    def test_3_months_on_step_4_s_button_is_ioi_ha(self):
        # Spec #453 acceptance 12: fitted 2026/08/12, 3 months to the day.
        self.answer()
        self.fit(date(2026, 8, 12))
        ioi = self.questionnaires[ioi_ha.CODE]
        self.assertEqual(self.journey().card.button, ("做效益問卷", f"/questionnaire/{ioi.pk}"))
        self.assertEqual(self.journey(date(2026, 11, 11)).card.button, None)

    def test_ioi_ha_from_the_fitting_date_on_finishes_step_4_however_soon(self):
        # Spec #453 acceptance 13: on the fitting date itself counts; before it does not.
        self.answer()
        self.fit(date(2026, 10, 3))
        self.answer(code=ioi_ha.CODE, on=date(2026, 10, 2))
        self.assertEqual(self.states()[3], CURRENT)
        self.answer(code=ioi_ha.CODE, on=date(2026, 10, 3))
        self.assertEqual(self.states()[3], DONE)


class RetestStepTests(CareJourneyTestCase):
    def normal_range(self, answered_on):
        self.hhie = self.answer(on=answered_on)
        self.make(NORMAL, NORMAL)

    def test_counting_down_step_5_says_the_day_without_a_button_at_4_of_5(self):
        # Spec #453 acceptance 14: steps 1 to 4 done or 目前不需要, the last HHIE-S 2 months
        # ago, so the next one is 2027/03/12, 120 days on; the 下次篩檢 tile says the day, so
        # the card says what happens then instead (#458 D8).
        self.normal_range(date(2026, 9, 12))
        journey = self.journey()
        self.assertEqual(journey.current, 5)
        self.assertEqual(journey.card.because, "時間到了，這裡會出現「再做一次」的按鈕。")
        self.assertIsNone(journey.card.button)
        self.assertEqual(journey.progress, 4)

    def test_6_months_on_step_5_s_button_opens_the_same_questionnaire(self):
        # Spec #453 acceptance 15: HHIA-S answered, HHIA-S again, whatever the age says.
        self.hhie = self.answer(code=hhia_s.CODE, on=date(2026, 5, 12))
        self.make(NORMAL, NORMAL)
        hhia = self.questionnaires[hhia_s.CODE]
        self.assertEqual(
            self.journey().card.button, ("再做一次（大約 3 分鐘）", f"/questionnaire/{hhia.pk}")
        )

    def test_a_retest_due_at_step_3_keeps_step_3_and_says_due_on_top(self):
        # Spec #453 acceptance 16.
        self.answer(on=date(2026, 5, 12))
        self.make(PTA_55, PTA_55)
        journey = self.journey()
        self.assertEqual(journey.current, 3)
        hhie = self.questionnaires[hhie_s.CODE]
        self.assertEqual(
            journey.next_screening, NextScreening(None, None, True, f"/questionnaire/{hhie.pk}")
        )

    def test_the_next_screening_tile_says_the_day_and_the_days_left(self):
        # Spec #453 acceptance 17.
        self.normal_range(date(2026, 9, 26))
        screening = self.journey().next_screening
        self.assertEqual((screening.on, screening.days_left), (date(2027, 3, 26), 134))
        self.assertFalse(screening.due)

    def test_a_retest_moves_step_5_on_from_the_new_day(self):
        # Spec #453 story 20.
        self.normal_range(date(2026, 5, 12))
        self.answer(on=date(2026, 11, 12))
        self.assertEqual(self.journey().next_screening.on, date(2027, 5, 12))
        self.assertEqual(self.states()[4], CURRENT)

    def test_without_a_life_impact_record_step_5_is_due_and_asks_for_one(self):
        # Spec #453: worn and IOI-HA done, so steps 3 and 4 are done; born 1950, HHIE-S.
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 5, 1), subsidy=Subsidy.OTHER
        )
        self.answer(code=ioi_ha.CODE, on=date(2026, 9, 1))
        journey = self.journey()
        self.assertEqual(self.states(), [LATER, LATER, DONE, DONE, CURRENT])
        hhie = self.questionnaires[hhie_s.CODE]
        # #458 D6: the 下次篩檢 tile has no day to count from, not called due.
        self.assertIsNone(journey.next_screening)
        self.assertEqual(journey.card.button, ("去做問卷", f"/questionnaire/{hhie.pk}"))

    def test_without_an_age_step_1_opens_the_catalogue(self):
        # life_impact_questionnaire cannot choose without an age; the catalogue recommends one.
        self.user.birth_year = None
        self.user.save()
        self.make(PTA_55, PTA_55)
        self.assertEqual(self.journey().card.button, ("去做問卷", "/questionnaire_list"))

    def test_the_last_result_tile_is_the_latest_life_impact_record(self):
        # Spec #453 Q15: not a later questionnaire of another kind.
        hhie = self.answer(on=date(2026, 9, 1))
        self.answer(code=thi.CODE, on=date(2026, 10, 1))
        self.assertEqual(self.journey().last_result, hhie)


class CompletionDateTests(CareJourneyTestCase):
    """#459 (#458 D7): a done step says when, so someone sees their record was kept."""

    def test_each_done_step_says_the_day_it_was_done(self):
        # Step 1 the latest life-impact record, step 2 the audiogram's test day, step 3 the
        # fitting date, step 4 the latest IOI-HA from the fitting date on.
        self.answer(on=date(2026, 3, 2))
        self.answer(on=date(2026, 9, 26))
        self.make(PTA_55, PTA_55, tested_on=date(2026, 6, 15))
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 7, 1), subsidy=Subsidy.OTHER
        )
        self.answer(code=ioi_ha.CODE, on=date(2026, 8, 1))
        self.answer(code=ioi_ha.CODE, on=date(2026, 10, 15))
        self.assertEqual(
            [step.done_on for step in self.journey().steps],
            [
                date(2026, 9, 26),
                date(2026, 6, 15),
                date(2026, 7, 1),
                date(2026, 10, 15),
                None,
            ],
        )

    def test_a_step_not_done_has_no_day(self):
        # An audiogram missing a frequency is not done, so it has no day either.
        self.answer()
        audiogram = self.make(NORMAL, NORMAL)
        audiogram.points.filter(ear="left", frequency=4000).delete()
        self.assertEqual(
            [step.done_on for step in self.journey().steps], [TODAY, None, None, None, None]
        )


class WithoutLifeImpactTilesTests(CareJourneyTestCase):
    """#459 (#458 D6): with no life-impact record there is nothing to show on top yet."""

    def test_only_an_audiogram_leaves_both_tiles_without_a_record(self):
        # Spec #453 acceptance 2: no 上次結果, and no day to count 下次篩檢 from, so it is not
        # called due either.
        self.make(PTA_55, PTA_55)
        journey = self.journey()
        self.assertIsNone(journey.last_result)
        self.assertIsNone(journey.next_screening)

    def test_a_life_impact_record_gives_the_tile_its_day(self):
        self.answer(on=date(2026, 9, 26))
        self.assertIsNotNone(self.journey().next_screening)


class StepAboutTests(CareJourneyTestCase):
    """#459 I1 (the owner's pick on the step interactions page): each step opens to say what it
    is; the 現在這一步's card says its own."""

    def test_each_step_says_what_it_is(self):
        self.answer()
        self.assertEqual(
            [step.about for step in self.journey().steps],
            [
                "先做一份生活影響問卷，了解聽力對您生活的影響。",
                "選配指引要用聽力圖才能整理下一步。",
                "照選配路線一站一站走，從找聽力師、申請補助到開始戴助聽器。",
                "買了助聽器、戴滿 3 個月後，做使用效益問卷（IOI-HA），看助聽器幫了多少。",
                "時間到了，這裡會出現「再做一次」的按鈕。",
            ],
        )
