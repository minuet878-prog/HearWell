"""#455 (spec #453, ADR 0044), #744 (spec #741, ADR 0074): the 照顧旅程's seven steps judged from
a user's records on a given day."""

from datetime import date, datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.care_journey import (
    CURRENT,
    DONE,
    LATER,
    NOT_NEEDED,
    AudiogramResult,
    Countdown,
    EarResult,
    Entry,
    JourneyCard,
    NextScreening,
    care_journey,
)
from screening.fitting_route import GUIDE_PAGE, HOSPITAL_SEARCH, fitting_state
from screening.models import (
    AidAndSubsidy,
    AidLevel,
    Audiogram,
    AudiogramSource,
    Category,
    Certificate,
    GuideChapterView,
    Question,
    Questionnaire,
    Submission,
    Subsidy,
)
from screening.questionnaires import hhia_s, hhie_s, ioi_ha, thi
from screening.scoring import LIFE_IMPACT_BUTTON
from screening.tests import test_fitting_advice, test_guide_summary
from screening.tests.helpers import consented_user

TODAY = date(2026, 11, 12)
NORMAL = (20, 20, 20, 20)
MILD_EAR = (30, 30, 30, 30)  # 輕度: with no life impact, 追蹤
PTA_45 = (45, 45, 45, 45)  # 建議評估選配, the estimate 30%: short of the threshold
PTA_55 = test_guide_summary.PTA_55  # 建議評估選配, the estimate 45%: the threshold reached
D, C, L, N = DONE, CURRENT, LATER, NOT_NEEDED

HOSPITAL = Entry("查詢醫療院所", "/qa/where-to-get-a-hearing-test", "pin")
GUIDE = Entry("看助聽器選配與補助", "/guide", "guide")
TYPES_AND_PRICES = Entry("看助聽器的種類與價格", "/guide/types-and-prices", "tag")
SOURCES = (
    Entry("醫院檢查報告", "/audiograms/new", "report-file", come_back=True),
    Entry("AirPods 自我檢測", "/audiograms/import", "airpods"),
)
NORMAL_WORDS = "您的聽力檢測結果為正常，但若有耳鳴、耳悶等其他症狀，仍建議尋求醫師協助。"
MILD_WORDS = "您的聽力未達補助資格，但依舊可以考慮配戴助聽器。"
GUIDE_WORDS = "統整助聽器補助流程供您參考。"
TIME_UP = "時間到了！"  # noqa: RUF001


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

    def fresh_user(self, name):
        """A user of their own for each subtest: records are PROTECTed from deleting."""
        self.user = consented_user(username=name, birth_year=1950)

    def answer(self, code=hhie_s.CODE, on=TODAY, wearing=False):
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.questionnaires[code], wearing_hearing_aid=wearing
        )
        moment = timezone.make_aware(datetime(on.year, on.month, on.day, 12))
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def self_test(self, right, left, tested_on=date(2026, 10, 1)):
        """An AirPods self test, as the iPhone import saves one."""
        audiogram = self.make(right, left, tested_on=tested_on)
        Audiogram.objects.filter(pk=audiogram.pk).update(source=AudiogramSource.SELF_TEST)
        return audiogram

    def missing_frequency(self):
        audiogram = self.make(NORMAL, NORMAL)
        audiogram.points.filter(ear="left", frequency=4000).delete()
        return audiogram

    def view(self, chapter, on=TODAY):
        view = GuideChapterView.objects.create(user=self.user, chapter=chapter)
        moment = timezone.make_aware(datetime(on.year, on.month, on.day, 12))
        GuideChapterView.objects.filter(pk=view.pk).update(first_viewed_at=moment)

    def aid(self, **fields):
        AidAndSubsidy.objects.update_or_create(user=self.user, defaults=fields)

    def journey(self, today=TODAY):
        return care_journey(self.user, today)

    def states(self, today=TODAY):
        return [step.state for step in self.journey(today).steps]


class SevenStepsTests(CareJourneyTestCase):
    """Spec #741 (ADR 0074): the 照顧旅程's seven steps, each one's state by the records."""

    def test_only_hhie_s_the_seven_steps_with_the_hospital_current(self):
        # Spec #741 acceptance 1.
        self.answer()
        journey = self.journey()
        self.assertEqual(
            [step.title for step in journey.steps],
            [
                "填生活影響問卷",
                "到醫院進行聽力檢查",
                "記錄聽力圖",
                "了解助聽器選配與補助",
                "申請補助與配戴助聽器",
                "戴滿 3 個月做效益問卷",
                "半年後再篩檢",
            ],
        )
        self.assertEqual(self.states(), [D, C, L, L, L, L, L])
        self.assertEqual(journey.current, 2)
        self.assertEqual(journey.card.title, "到醫院進行聽力檢查")
        self.assertEqual(journey.card.because, "")
        self.assertIsNone(journey.card.button)
        self.assertEqual(journey.card.entries, (HOSPITAL,))

    def test_every_combination_of_records_gives_each_step_s_state(self):
        # Spec #741's 測試決定: seven steps by each kind of record. (records, the states, the
        # 現在這一步.)
        hhie = self.answer

        def fitted(days_ago, subsidy=Subsidy.OTHER, **fields):
            return lambda: self.aid(
                fitted_on=date.fromordinal(TODAY.toordinal() - days_ago), subsidy=subsidy, **fields
            )

        def ioi(days_ago):
            return lambda: self.answer(
                code=ioi_ha.CODE, on=date.fromordinal(TODAY.toordinal() - days_ago)
            )

        rows = {
            "nothing but a thi": ([lambda: self.answer(code=thi.CODE)], [C, L, L, L, L, L, L], 1),
            "hhie-s only": ([hhie], [D, C, L, L, L, L, L], 2),
            "an airpods test only": (
                [lambda: self.self_test(PTA_55, PTA_55)],
                [C, D, D, L, L, L, L],
                1,
            ),
            "hhie-s and an airpods test": (
                [hhie, lambda: self.self_test(PTA_55, PTA_55)],
                [D, D, D, C, L, L, L],
                4,
            ),
            "hhie-s, the hospital search opened": (
                [hhie, lambda: self.view(HOSPITAL_SEARCH)],
                [D, D, C, L, L, L, L],
                3,
            ),
            "hhie-s, the hospital search opened and an audiogram": (
                [hhie, lambda: self.view(HOSPITAL_SEARCH), lambda: self.make(PTA_55, PTA_55)],
                [D, D, D, C, L, L, L],
                4,
            ),
            "a frequency missing": ([hhie, self.missing_frequency], [D, D, C, L, L, L, L], 3),
            "normal hearing": (
                [hhie, lambda: self.make(NORMAL, NORMAL)],
                [D, D, D, N, N, N, C],
                7,
            ),
            "tracked": ([hhie, lambda: self.make(MILD_EAR, NORMAL)], [D, D, D, N, N, N, C], 7),
            "mild to moderate": (
                [hhie, lambda: self.make(PTA_45, PTA_45)],
                [D, D, D, C, L, L, L],
                4,
            ),
            "mild to moderate, types and prices read": (
                [hhie, lambda: self.make(PTA_45, PTA_45), lambda: self.view("types-and-prices")],
                [D, D, D, D, C, L, L],
                5,
            ),
            "the threshold reached, types and prices read": (
                [hhie, lambda: self.make(PTA_55, PTA_55), lambda: self.view("types-and-prices")],
                [D, D, D, C, L, L, L],
                4,
            ),
            "the threshold reached, my guide opened": (
                [hhie, lambda: self.make(PTA_55, PTA_55), lambda: self.view(GUIDE_PAGE)],
                [D, D, D, D, C, L, L],
                5,
            ),
            "the certificate applying": (
                [
                    hhie,
                    lambda: self.make(PTA_55, PTA_55),
                    lambda: self.view(GUIDE_PAGE),
                    lambda: self.aid(certificate=Certificate.APPLYING),
                ],
                [D, D, D, D, C, L, L],
                5,
            ),
            "fitted, no IOI-HA yet": (
                [hhie, fitted(10)],
                [D, L, L, L, C, L, L],
                5,
            ),
            "fitted 45 days, the first IOI-HA": (
                [hhie, fitted(45), ioi(40)],
                [D, L, L, L, D, C, L],
                6,
            ),
            "fitted 10 days with the subsidy, the first IOI-HA": (
                [hhie, fitted(10, Subsidy.DISABILITY, level=AidLevel.MID), ioi(5)],
                [D, L, L, L, C, L, L],
                5,
            ),
            "the subsidy and form 25 done": (
                [
                    hhie,
                    fitted(60, Subsidy.DISABILITY, level=AidLevel.MID, form_25_done=True),
                    ioi(50),
                ],
                [D, L, L, L, D, C, L],
                6,
            ),
            "fitted 3 months, the first IOI-HA only": (
                [hhie, fitted(100), ioi(90)],
                [D, L, L, L, D, C, L],
                6,
            ),
            "fitted 3 months, the second IOI-HA": (
                [hhie, fitted(100), ioi(90), ioi(2)],
                [D, L, L, L, D, D, C],
                7,
            ),
            "wearing, no date": (
                [lambda: self.answer(wearing=True)],
                [D, L, L, L, C, L, L],
                5,
            ),
            "wearing, normal hearing": (
                [lambda: self.answer(wearing=True), lambda: self.make(NORMAL, NORMAL)],
                [D, D, D, L, C, L, L],
                5,
            ),
        }
        for name, (records, states, current) in rows.items():
            with self.subTest(records=name):
                self.fresh_user(name)
                for record in records:
                    record()
                self.assertEqual(self.states(), states)
                self.assertEqual(self.journey().current, current)


class AudiogramStepsTests(CareJourneyTestCase):
    def test_the_first_audiogram_makes_steps_2_and_3_done_together(self):
        # Spec #741 acceptance 2, 3: an AirPods self test counts.
        self.answer()
        self.assertEqual(self.states()[1:3], [C, L])
        self.self_test(PTA_55, PTA_55, tested_on=date(2026, 10, 3))
        steps = self.journey().steps
        self.assertEqual([step.state for step in steps[1:3]], [D, D])
        self.assertEqual([step.done_on for step in steps[1:3]], [date(2026, 10, 3)] * 2)

    def test_opening_the_hospital_search_finishes_step_2_and_step_3_asks_for_an_audiogram(self):
        # Spec #741's 實作中本人補充 (acceptance 1, 4): 查詢醫療院所 opened is step 2 done on
        # that day; step 3, the 現在這一步 without an audiogram, is the small heading and the
        # audiogram's two sources.
        self.answer()
        self.view(HOSPITAL_SEARCH, on=date(2026, 11, 2))
        journey = self.journey()
        self.assertEqual((journey.steps[1].state, journey.steps[1].done_on), (D, date(2026, 11, 2)))
        self.assertEqual(journey.current, 3)
        self.assertEqual(
            journey.card,
            JourneyCard("記錄聽力圖", "", entries=SOURCES, entries_title="聽力圖來源"),
        )

    def test_step_2_is_done_on_whichever_came_first(self):
        # Opened, or any audiogram (grill Q9): the day is the earlier one.
        self.answer()
        self.view(HOSPITAL_SEARCH, on=date(2026, 11, 2))
        self.self_test(PTA_55, PTA_55, tested_on=date(2026, 10, 3))
        self.assertEqual(self.journey().steps[1].done_on, date(2026, 10, 3))

    def test_step_2_done_still_opens_to_the_hospital_search(self):
        # Spec #741's 實作中本人補充: done, step 2 opens to 查詢醫療院所 under its stamp, done by
        # either way.
        for name, record in (
            ("opened", lambda: self.view(HOSPITAL_SEARCH)),
            ("audiogram", lambda: self.self_test(PTA_55, PTA_55)),
        ):
            with self.subTest(name):
                self.fresh_user(name)
                self.answer()
                record()
                step = self.journey().steps[1]
                self.assertEqual((step.state, step.entries), (D, (HOSPITAL,)))

    def test_without_an_audiogram_step_3_opens_to_the_audiogram_s_sources(self):
        # Spec #741 acceptance 4, story 4: with no audiogram, step 3 opens, under its sentence,
        # to the small heading and the two entry cards, whether it is the 現在這一步 or not yet.
        self.answer()
        step = self.journey().steps[2]
        self.assertEqual(step.state, L)
        self.assertEqual(step.entries_title, "聽力圖來源")
        self.assertEqual(step.entries, SOURCES)
        self.missing_frequency()
        self.assertEqual(self.journey().steps[2].entries, ())

    def test_a_missing_frequency_says_so_with_editing_it(self):
        # Spec #741 acceptance 5: the sentence and 修改這張聽力圖, nothing else.
        self.answer()
        audiogram = self.missing_frequency()
        journey = self.journey()
        self.assertEqual(journey.current, 3)
        self.assertEqual(
            journey.card,
            JourneyCard(
                "記錄聽力圖",
                "這張聽力圖缺少頻率，資料不足，無法判斷。",
                button=("修改這張聽力圖", f"/audiograms/{audiogram.pk}/edit"),
            ),
        )

    def test_step_3_done_opens_to_the_audiogram_s_result(self):
        # Spec #741 acceptance 6: each ear's degree and average, and the way to the audiogram.
        self.answer()
        audiogram = self.make(PTA_45, PTA_55, tested_on=date(2026, 6, 2))
        self.assertEqual(
            self.journey().audiogram,
            AudiogramResult(
                f"/audiograms/{audiogram.pk}",
                date(2026, 6, 2),
                (EarResult("右耳", "right", "中度", 45), EarResult("左耳", "left", "中度", 55)),
            ),
        )

    def test_without_step_3_done_there_is_no_audiogram_result(self):
        self.answer()
        self.missing_frequency()
        self.assertIsNone(self.journey().audiogram)


class GuideStepTests(CareJourneyTestCase):
    """Step 4, 了解助聽器選配與補助, by 不符資格's three cases (grill Q12, Q22)."""

    def step_4(self):
        return self.journey().steps[3]

    def test_eligible_it_points_to_my_guide_and_opening_it_finishes_it(self):
        # Spec #741 acceptance 7, 8.
        self.answer()
        self.make(PTA_55, PTA_55)
        journey = self.journey()
        self.assertEqual(journey.current, 4)
        self.assertEqual(
            journey.card,
            JourneyCard("了解助聽器選配與補助", GUIDE_WORDS, entries=(GUIDE,)),
        )
        self.view(GUIDE_PAGE, on=date(2026, 11, 2))
        step = self.step_4()
        self.assertEqual((step.state, step.done_on), (D, date(2026, 11, 2)))
        # Opened: the stamp, and still the way to my guide (the canvas's 3-a1).
        self.assertEqual(step.entries, (GUIDE,))
        self.assertFalse(step.ineligible)

    def test_normal_hearing_is_ineligible_and_not_needed_to_step_6(self):
        # Spec #741 acceptance 9.
        self.answer()
        self.make(NORMAL, NORMAL)
        journey = self.journey()
        self.assertEqual(journey.current, 7)
        step = self.step_4()
        self.assertEqual((step.state, step.ineligible, step.about), (N, True, NORMAL_WORDS))
        self.assertEqual(step.entries, ())
        self.assertEqual([s.ineligible for s in journey.steps[4:6]], [False, False])

    def test_mild_to_moderate_points_to_types_and_prices_and_reading_it_finishes_it(self):
        # Spec #741 acceptance 10: and the 補助站 stay on the route, whatever the estimate.
        self.answer()
        self.make(PTA_45, PTA_45)
        journey = self.journey()
        self.assertEqual(journey.current, 4)
        self.assertEqual(
            journey.card,
            JourneyCard("了解助聽器選配與補助", MILD_WORDS, entries=(TYPES_AND_PRICES,)),
        )
        self.assertTrue(self.step_4().ineligible)
        self.view("types-and-prices", on=date(2026, 11, 5))
        self.assertEqual(self.step_4().state, D)
        self.assertEqual(self.step_4().done_on, date(2026, 11, 5))
        route = fitting_state(self.user, TODAY)
        self.assertEqual(route.home_stop, "assessment")
        self.aid(certificate=Certificate.APPLYING)
        self.assertIn("form-9", fitting_state(self.user, TODAY).stops)

    def test_mild_to_moderate_my_guide_opened_finishes_it_too(self):
        self.answer()
        self.make(PTA_45, PTA_45)
        self.view(GUIDE_PAGE)
        self.assertEqual(self.step_4().state, D)

    def test_a_self_test_alone_estimates_nothing_so_it_is_eligible(self):
        # ADR 0068: only an exam estimates the threshold; without one, the subsidy's words.
        self.answer()
        self.self_test(PTA_45, PTA_45)
        self.assertEqual(self.journey().card.entries, (GUIDE,))
        self.assertFalse(self.step_4().ineligible)

    def test_the_earlier_of_two_views_is_the_day(self):
        self.answer()
        self.make(PTA_45, PTA_45)
        self.view("types-and-prices", on=date(2026, 11, 5))
        self.view(GUIDE_PAGE, on=date(2026, 11, 7))
        self.assertEqual(self.step_4().done_on, date(2026, 11, 5))


class RouteStepTests(CareJourneyTestCase):
    """Step 5, 申請補助與配戴助聽器: the route's 目前這一站, but 記錄聽力圖; each stop's card
    (#745) is test_answer_cards'."""

    def setUp(self):
        super().setUp()
        self.answer()
        self.make(PTA_55, PTA_55)
        self.view(GUIDE_PAGE)

    def test_the_route_s_stop_is_step_5_s_card_its_answer_card_unanswered(self):
        # #745: form 9's answer card, nothing chosen; the route's own button kept for the
        # result pages, where the card is not shown.
        self.aid(certificate=Certificate.YES)
        self.assertEqual(self.states(), [D, D, D, D, C, L, L])
        card = self.journey().card
        self.assertEqual(card.title, "九號表：申請助聽器補助")
        self.assertEqual(card.question.stop, "form-9")
        self.assertEqual(card.question.field, "form_9_done")
        self.assertEqual(
            [(c.value, c.text, c.chosen) for c in card.question.choices],
            [("True", "是", False), ("False", "否", False)],
        )
        self.assertIsNone(card.button)
        self.assertEqual(card.away, ("看九號表的流程", "/guide/form-9"))

    def test_each_stop_answered_moves_step_5_s_card_on(self):
        for fields, title in (
            ({}, "身障鑑定與鑑定醫院"),
            ({"certificate": Certificate.YES}, "九號表：申請助聽器補助"),
            ({"form_9_done": True}, "等待核定公文"),
            (
                {"notice_received": True, "approved_ears": "both", "level": AidLevel.MID},
                "去找聽力師之前",
            ),
        ):
            with self.subTest(title=title):
                if fields:
                    self.aid(**fields)
                self.assertEqual(self.journey().card.title, title)
                self.assertEqual(self.journey().current, 5)

    def test_none_folds_the_subsidy_stops_to_before_you_go(self):
        self.aid(certificate=Certificate.NO_SUBSIDY)
        self.assertEqual(self.journey().card.title, "去找聽力師之前")

    def test_types_and_prices_is_passed_by_to_after_fitting(self):
        # ADR 0074: my guide is at 助聽器的種類與價格, the home page's card at the stop after it.
        self.view("before-you-go")
        self.aid(certificate=Certificate.NO_SUBSIDY)
        self.assertEqual(fitting_state(self.user, TODAY).stop, "types-and-prices")
        card = self.journey().card
        self.assertEqual(card.title, "配戴助聽器之後")
        self.assertEqual([entry.text for entry in card.entries], ["記下開始配戴的日期", "填問卷"])

    def test_after_fitting_waits_for_the_first_ioi_ha(self):
        # Spec #741 acceptance 22, in the state: the date alone leaves step 5 at 配戴之後.
        self.aid(fitted_on=date(2026, 11, 1), subsidy=Subsidy.OTHER)
        self.assertEqual((self.journey().current, self.journey().card.title), (5, "配戴助聽器之後"))
        self.answer(code=ioi_ha.CODE, on=date(2026, 11, 8))
        self.assertEqual(self.journey().current, 6)
        self.assertEqual(self.journey().steps[4].done_on, date(2026, 11, 1))

    def test_form_25_is_step_5_s_with_the_subsidy(self):
        # Spec #741 acceptance 23's stop: fitted 10 days ago with the subsidy, the IOI-HA done.
        self.aid(fitted_on=date(2026, 11, 2), subsidy=Subsidy.DISABILITY, level=AidLevel.MID)
        self.answer(code=ioi_ha.CODE, on=date(2026, 11, 9))
        journey = self.journey()
        self.assertEqual(journey.current, 5)
        self.assertEqual(journey.card.title, "二十五號表：使用效益驗證")

    def test_waiting_for_the_notice_has_no_button(self):
        # The owner on #455: there is nothing to do but wait, so no button; #745: the card asks
        # whether it came.
        self.aid(certificate=Certificate.YES, form_9_done=True)
        card = self.journey().card
        self.assertEqual(card.title, "等待核定公文")
        self.assertIsNone(card.button)
        self.assertEqual(card.question.question, "您收到核定公文了嗎？")


class WearingTests(CareJourneyTestCase):
    def test_wearing_counts_from_step_5_without_ticking_steps_1_to_4(self):
        # Spec #741 acceptance 28.
        self.answer(code=thi.CODE, wearing=True)
        journey = self.journey()
        self.assertEqual(journey.current, 5)
        self.assertEqual(self.states(), [L, L, L, L, C, L, L])
        self.assertEqual(journey.card.title, "配戴助聽器之後")
        self.assertEqual(
            journey.card.because, "配戴一個月後才能做二十五號表，配合問卷使用更能知道助聽器的效果。"
        )


class EffectStepTests(CareJourneyTestCase):
    """Step 6, 戴滿 3 個月做效益問卷 (#746 draws its countdown card)."""

    def fit(self, fitted_on):
        AidAndSubsidy.objects.create(user=self.user, fitted_on=fitted_on, subsidy=Subsidy.OTHER)
        self.answer(code=ioi_ha.CODE, on=fitted_on)

    def test_before_3_months_step_6_is_its_countdown_card_without_a_button(self):
        # Spec #741 acceptance 24: worn 45 days, the first IOI-HA done. Fitted 2026/11/30, so 3
        # months is 2027/02/28, 90 days on: 45 days left, half the wait gone.
        self.answer(on=date(2027, 1, 1))
        self.fit(date(2026, 11, 30))
        journey = self.journey(date(2027, 1, 14))
        self.assertEqual(journey.current, 6)
        self.assertEqual(journey.card.because, "和上一次進行比較")
        self.assertEqual(
            journey.card.countdown,
            Countdown(date(2027, 2, 28), 45, 0.5, below="起可以再做一次"),
        )
        self.assertIsNone(journey.card.button)

    def test_3_months_on_step_6_is_its_button_alone(self):
        # Spec #741 acceptance 25: only 做效益問卷, no sentence and no countdown.
        self.answer()
        self.fit(date(2026, 8, 12))
        card = self.journey().card
        self.assertEqual((card.because, card.countdown), ("", None))

    def test_3_months_on_step_6_s_button_is_ioi_ha(self):
        self.answer()
        self.fit(date(2026, 8, 12))
        ioi = self.questionnaires[ioi_ha.CODE]
        self.assertEqual(self.journey().card.button, ("做效益問卷", f"/questionnaire/{ioi.pk}"))
        self.assertIsNone(self.journey(date(2026, 11, 11)).card.button)

    def test_an_ioi_ha_from_3_months_on_finishes_step_6(self):
        # ADR 0074: the second IOI-HA; the first, from the fitting date on, is step 5's.
        self.answer()
        self.fit(date(2026, 8, 12))
        self.answer(code=ioi_ha.CODE, on=date(2026, 11, 11))
        self.assertEqual(self.states()[5], C)
        self.answer(code=ioi_ha.CODE, on=date(2026, 11, 12))
        self.assertEqual(self.states()[5], D)


class RetestStepTests(CareJourneyTestCase):
    def normal_range(self, answered_on):
        self.hhie = self.answer(on=answered_on)
        self.make(NORMAL, NORMAL)

    def test_counting_down_step_7_is_its_countdown_card_at_6_of_7(self):
        # Spec #741 acceptance 26: steps 1 to 6 done or 目前不需要, the last HHIE-S a day ago;
        # 2026/11/11 to 2027/05/11 is 181 days, 1 of them gone.
        self.normal_range(date(2026, 11, 11))
        journey = self.journey()
        self.assertEqual(journey.current, 7)
        wait = Countdown(date(2027, 5, 11), 180, 1 / 181, above="下次篩檢")
        self.assertEqual(journey.card.countdown, wait)
        self.assertEqual(journey.card.because, "")
        self.assertIsNone(journey.card.button)
        # Step 7 opened before it is the 現在這一步 shows the same card (the canvas's 5-a).
        self.assertEqual(journey.next_screening.countdown, wait)

    def test_6_months_on_step_7_says_time_is_up(self):
        # Spec #741 acceptance 26.
        self.normal_range(date(2026, 5, 12))
        card = self.journey().card
        self.assertEqual((card.because, card.button[0]), (TIME_UP, "再做一次（大約 3 分鐘）"))
        self.assertIsNone(card.countdown)

    def test_6_months_on_step_7_s_button_opens_the_same_questionnaire(self):
        # Spec #453 acceptance 15: HHIA-S answered, HHIA-S again, whatever the age says.
        self.hhie = self.answer(code=hhia_s.CODE, on=date(2026, 5, 12))
        self.make(NORMAL, NORMAL)
        hhia = self.questionnaires[hhia_s.CODE]
        self.assertEqual(
            self.journey().card.button, ("再做一次（大約 3 分鐘）", f"/questionnaire/{hhia.pk}")
        )

    def test_a_retest_due_at_step_4_keeps_step_4_and_says_due_on_top(self):
        # Spec #453 acceptance 16.
        self.answer(on=date(2026, 5, 12))
        self.make(PTA_55, PTA_55)
        journey = self.journey()
        self.assertEqual(journey.current, 4)
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

    def test_a_retest_moves_step_7_on_from_the_new_day(self):
        # Spec #453 story 20.
        self.normal_range(date(2026, 5, 12))
        self.answer(on=date(2026, 11, 12))
        self.assertEqual(self.journey().next_screening.on, date(2027, 5, 12))
        self.assertEqual(self.states()[6], C)

    def test_without_a_life_impact_record_step_7_is_due_and_asks_for_one(self):
        # Worn, both IOI-HA done, so steps 5 and 6 are done; born 1950, HHIE-S.
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 5, 1), subsidy=Subsidy.OTHER
        )
        self.answer(code=ioi_ha.CODE, on=date(2026, 5, 10))
        self.answer(code=ioi_ha.CODE, on=date(2026, 9, 1))
        journey = self.journey()
        self.assertEqual(self.states(), [L, L, L, L, D, D, C])
        hhie = self.questionnaires[hhie_s.CODE]
        # #458 D6: the 下次篩檢 tile has no day to count from, not called due.
        self.assertIsNone(journey.next_screening)
        self.assertEqual(journey.card.because, "還沒有完成第一次篩檢。")
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
        # Step 1 the latest life-impact record, steps 2 and 3 the audiogram's test day, step 4
        # my guide's first opening, step 5 the fitting date, step 6 the IOI-HA 3 months on.
        self.answer(on=date(2026, 3, 2))
        self.answer(on=date(2026, 9, 26))
        self.make(PTA_55, PTA_55, tested_on=date(2026, 6, 15))
        self.view(GUIDE_PAGE, on=date(2026, 6, 20))
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
                date(2026, 6, 15),
                date(2026, 6, 20),
                date(2026, 7, 1),
                date(2026, 10, 15),
                None,
            ],
        )

    def test_a_step_not_done_has_no_day(self):
        # An audiogram missing a frequency leaves step 3 undone, without a day.
        self.answer()
        audiogram = self.missing_frequency()
        self.assertEqual(
            [step.done_on for step in self.journey().steps],
            [TODAY, audiogram.tested_on, None, None, None, None, None],
        )


class WithoutLifeImpactTilesTests(CareJourneyTestCase):
    """#459 (#458 D6): with no life-impact record there is nothing to show on top yet."""

    def test_only_an_audiogram_leaves_both_tiles_without_a_record(self):
        self.make(PTA_55, PTA_55)
        journey = self.journey()
        self.assertIsNone(journey.last_result)
        self.assertIsNone(journey.next_screening)

    def test_a_life_impact_record_gives_the_tile_its_day(self):
        self.answer(on=date(2026, 9, 26))
        self.assertIsNotNone(self.journey().next_screening)


class StepAboutTests(CareJourneyTestCase):
    """#459 I1: each step opens to say what it is, the canvas's words (spec #741)."""

    def test_each_step_says_what_it_is_and_its_entry_cards(self):
        self.answer(code=thi.CODE)
        steps = self.journey().steps
        self.assertEqual(
            [step.about for step in steps],
            [
                "先做一份生活影響問卷，了解聽力對您生活的影響。",
                "到醫院做聽力檢查並取得聽力報告。",
                "記錄您在醫院做的聽力檢查或 AirPods 自我測試結果。",
                GUIDE_WORDS,
                "照選配路線一站一站走，從找聽力師到開始戴助聽器。",
                "戴滿 3 個月後，再做一次問卷和第一次比較，看看助聽器的幫助。",
                "還沒有完成第一次篩檢。",
            ],
        )
        self.assertEqual(
            [step.entries for step in steps], [(), (HOSPITAL,), SOURCES, (GUIDE,), (), (), ()]
        )

    def test_step_7_opens_to_what_its_card_says_without_its_button(self):
        # The canvas's 5-a: counting down, its countdown card in place of words; due, TIME_UP.
        self.answer(on=date(2026, 9, 26))
        step = self.journey().steps[6]
        self.assertEqual(step.state, L)
        self.assertEqual(
            (step.about, step.countdown), ("", self.journey().next_screening.countdown)
        )
        self.fresh_user("due")
        self.answer(on=date(2026, 5, 12))
        step = self.journey().steps[6]
        self.assertEqual((step.about, step.countdown), (TIME_UP, None))

    def test_a_done_step_opens_to_its_stamp_alone_but_steps_2_and_4(self):
        # Spec #741 acceptance 27: step 1 only the stamp; step 3 the audiogram's card, which
        # CareJourney.audiogram holds; step 2 still 查詢醫療院所 (實作中本人補充), step 4 its
        # way to my guide.
        self.answer()
        self.make(PTA_55, PTA_55)
        self.view(GUIDE_PAGE)
        steps = self.journey().steps
        self.assertEqual([step.state for step in steps[:4]], [D, D, D, D])
        self.assertEqual([step.entries for step in steps[:4]], [(), (HOSPITAL,), (), (GUIDE,)])


class ViewingDoesNotStartRouteJourneyTests(CareJourneyTestCase):
    """#695 (spec #693 acceptance 10 to 12): within the normal range steps 4 to 6 are
    目前不需要 until the user answers a question on the route; reading chapters is not enough."""

    def setUp(self):
        super().setUp()
        self.answer()
        self.make(NORMAL, NORMAL)

    def test_reading_chapters_keeps_steps_4_to_6_not_needed(self):
        for chapter in ("before-you-go", "types-and-prices"):
            GuideChapterView.objects.create(user=self.user, chapter=chapter)
        self.assertEqual(self.states(), [D, D, D, N, N, N, C])

    def test_answering_a_route_question_brings_steps_4_to_6_back(self):
        # The route goes on from the first stop not done; 不符資格 goes with 目前不需要.
        AidAndSubsidy.objects.create(user=self.user, certificate=Certificate.APPLYING)
        journey = self.journey()
        self.assertEqual(self.states(), [D, D, D, C, L, L, L])
        self.assertFalse(journey.steps[3].ineligible)
        self.assertEqual(journey.card.entries, (GUIDE,))

    def test_wearing_and_reading_chapters_still_needs_step_5(self):
        # Acceptance 12, in part: someone wearing hearing aids is not waited on, as before.
        self.answer(wearing=True)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        self.assertEqual(self.states(), [D, D, D, L, C, L, L])


class FittingAdviceJourneyTests(test_fitting_advice.LifeImpactTestCase):
    """#697 (spec #693, ADR 0067): steps 4 to 6 by 建議評估選配, 目前不需要 only for normal and
    track, 之後 while a questionnaire is wanted first."""

    def setUp(self):
        self.user = consented_user(username="advice_journey", birth_year=1950)

    make = test_guide_summary.GuideSummaryTests.make

    def states(self):
        return [step.state for step in care_journey(self.user, TODAY).steps]

    def record(self, scores, wearing=None):
        submission = test_fitting_advice.record(self.user, scores, on=date(2026, 11, 1))
        Submission.objects.filter(pk=submission.pk).update(wearing_hearing_aid=wearing)

    def test_mild_with_life_impact_makes_step_4_current(self):
        # Spec #693 acceptance 6.
        self.make(MILD_EAR, NORMAL)
        self.record(test_fitting_advice.MILD_SCORES)
        self.assertEqual(self.states(), [D, D, D, C, L, L, L])

    def test_tracked_steps_4_to_6_are_not_needed(self):
        # Spec #693 acceptance 7.
        self.make(MILD_EAR, NORMAL)
        self.record(test_fitting_advice.NORMAL_SCORES)
        self.assertEqual(self.states(), [D, D, D, N, N, N, C])

    def test_a_questionnaire_first_leaves_steps_4_to_6_later_and_step_1_current(self):
        # Spec #693 acceptance 8.
        self.make(MILD_EAR, NORMAL)
        journey = care_journey(self.user, TODAY)
        self.assertEqual(journey.current, 1)
        self.assertEqual(self.states(), [C, D, D, L, L, L, L])

    def test_wearing_needs_step_5_whatever_the_advice(self):
        # Spec #693 acceptance 12: from step 5 on.
        self.make(MILD_EAR, NORMAL)
        self.record(test_fitting_advice.NORMAL_SCORES, wearing=True)
        self.assertEqual(self.states(), [D, D, D, L, C, L, L])


class SelfReview693UnreadableLifeImpactTests(test_fitting_advice.LifeImpactTestCase):
    """The self review on #693: the latest life-impact record 無法判讀 (a total off the
    thresholds table) leaves step 1 the 現在這一步, to be done again, whatever the hearing (the
    owner, 2026-11-17); 上次結果 still shows that record."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # An 11th item makes four on every item 44, over the table's 40: 無法判讀.
        Question.objects.create(
            questionnaire=Questionnaire.objects.get(code=hhie_s.CODE),
            question_text="假題11",
            question_number=11,
            category=Category.SOCIAL,
        )
        # IOI-HA has seven items, which the home page's pages read.
        Question.objects.filter(questionnaire__code=ioi_ha.CODE, question_number__gt=7).delete()

    def setUp(self):
        self.user = consented_user(username="unreadable_journey", birth_year=1950)
        self.unreadable = test_fitting_advice.record(self.user, (4,) * 11)

    make = test_guide_summary.GuideSummaryTests.make

    def journey(self):
        return care_journey(self.user, TODAY)

    def test_the_record_is_unreadable(self):
        self.assertEqual(self.unreadable.result.level["level"], "unknown")

    def test_mild_hearing_makes_step_1_current_with_its_button(self):
        self.make(MILD_EAR, NORMAL)
        journey = self.journey()
        self.assertEqual(journey.current, 1)
        self.assertEqual([step.state for step in journey.steps], [C, D, D, L, L, L, L])
        self.assertIsNone(journey.steps[0].done_on)
        self.assertEqual(journey.card.button[0], LIFE_IMPACT_BUTTON)

    def test_whatever_the_hearing_step_1_is_current(self):
        for right in (None, NORMAL, PTA_55):
            with self.subTest(right=right):
                Audiogram.objects.filter(user=self.user).delete()
                if right is not None:
                    self.make(right, NORMAL)
                self.assertEqual(self.journey().current, 1)
                self.assertEqual(self.journey().steps[0].state, C)

    def test_the_last_result_tile_still_shows_the_record(self):
        self.assertEqual(self.journey().last_result, self.unreadable)

    def test_the_home_page_opens_on_step_1(self):
        self.make(MILD_EAR, NORMAL)
        self.client.force_login(self.user)
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # #751: a 無法判讀 score has no gauge to draw; the score stands alone.
        self.assertIn(
            '<span class="journey-tile-score"><span>44</span> <small>分</small></span>',
            content,
        )
        self.assertNotIn('<div class="gauge"', content)
        self.assertIn(f">{LIFE_IMPACT_BUTTON}</a>", content)

    def test_the_result_page_opens(self):
        # Its 建議下一步 is the 照顧旅程's card (next_step), so the same cause.
        self.make(MILD_EAR, NORMAL)
        self.client.force_login(self.user)
        response = self.client.get(reverse("result", args=[self.unreadable.pk]))
        self.assertEqual(response.status_code, 200)


class CrossReview693WearingAudiogramJourneyTests(test_fitting_advice.LifeImpactTestCase):
    """The cross review on #693, acceptance 12: wearing hearing aids, one ear 30 dB HL and the
    other without 4000 Hz, no life-impact record: steps 2 and 3 are done, as before spec #693."""

    def setUp(self):
        self.user = consented_user(username="wearing_audiogram_journey", birth_year=1950)
        audiogram = self.make(MILD_EAR, NORMAL)
        audiogram.points.filter(ear="left", frequency=4000).delete()
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 5, 1))

    make = test_guide_summary.GuideSummaryTests.make

    def test_steps_2_and_3_are_done_with_the_audiogram_s_date(self):
        journey = care_journey(self.user, TODAY)
        self.assertEqual([step.state for step in journey.steps[1:3]], [D, D])
        self.assertEqual(journey.steps[2].done_on, date(2026, 10, 1))
