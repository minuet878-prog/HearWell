"""#459 (spec #453, ADR 0044, mockup #458): the home page as the 照顧旅程, and the 空狀態首頁.
Which step is which is judged in test_care_journey; these check the page shows it."""

import re
from datetime import date, datetime
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import (
    AidAndSubsidy,
    Answer,
    Category,
    Question,
    Questionnaire,
    Submission,
    Subsidy,
)
from screening.questionnaires import hhia_s, hhie_s, ioi_ha
from screening.tests import test_guide_summary
from screening.tests.helpers import consented_user

TODAY = date(2026, 11, 12)
NORMAL = (20, 20, 20, 20)
PTA_45 = (45, 45, 45, 45)  # 建議評估選配, the estimate short of the threshold
PTA_55 = test_guide_summary.PTA_55
# The page's main button: solid, or white on the blue hero card (#749, ADR 0076).
SOLID = re.compile(r'class="btn btn-(?:primary|hero)(?=[ "])')

STAMP = '<span class="done-stamp play-once-stamp" data-play-in-view>'
GUIDE_WORDS = "統整助聽器補助流程供您參考。"
NORMAL_WORDS = "您的聽力檢測結果為正常，但若有耳鳴、耳悶等其他症狀，仍建議尋求醫師協助。"
MILD_WORDS = "您的聽力未達補助資格，但依舊可以考慮配戴助聽器。"


def greets(greeting, title):
    """The bird's lead and the page's title in its bubble (#749)."""
    return rf'<p class="bird-lead">{greeting}，</p>\s*<h1 class="bird-title">{title}</h1>'


class HomeJourneyTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.questionnaires = {}
        for code, count in ((hhie_s.CODE, 10), (hhia_s.CODE, 10), (ioi_ha.CODE, 7)):
            questionnaire = Questionnaire.objects.create(questionnaire_name=code, code=code)
            Question.objects.bulk_create(
                Question(
                    questionnaire=questionnaire,
                    question_text=f"{code}題{i}",
                    question_number=i,
                    category=(
                        (Category.EMOTIONAL if i <= 5 else Category.SOCIAL)
                        if code != ioi_ha.CODE
                        else Category.NONE
                    ),
                )
                for i in range(1, count + 1)
            )
            cls.questionnaires[code] = questionnaire

    def setUp(self):
        self.user = consented_user(username="home_journey", birth_year=1950)
        self.client.force_login(self.user)
        self.now = timezone.make_aware(datetime(2026, 11, 12, 9))
        real_localdate, real_localtime = timezone.localdate, timezone.localtime

        def localdate(value=None, timezone=None):
            return TODAY if value is None else real_localdate(value, timezone)

        def localtime(value=None, timezone=None):
            return real_localtime(self.now if value is None else value, timezone)

        self.enterContext(patch("django.utils.timezone.localdate", localdate))
        self.enterContext(patch("django.utils.timezone.localtime", localtime))

    make = test_guide_summary.GuideSummaryTests.make

    def fresh_user(self, name):
        """A user of their own for each subtest: records are PROTECTed from deleting."""
        self.user = consented_user(username=name, birth_year=1950)
        self.client.force_login(self.user)

    def answer(self, code=hhie_s.CODE, on=TODAY, score=0, wearing=False):
        questionnaire = self.questionnaires[code]
        submission = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        questions = list(questionnaire.questions.order_by("question_number"))
        scores = [score] + [0] * (len(questions) - 1) if code != ioi_ha.CODE else [3] * 7
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=value)
            for question, value in zip(questions, scores, strict=True)
        )
        moment = timezone.make_aware(datetime(on.year, on.month, on.day, 12))
        Submission.objects.filter(pk=submission.pk).update(created_at=moment)
        return submission

    def main(self):
        content = self.client.get(reverse("index")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def part(self, main, css_class):
        found = re.search(rf'<(\w+) class="{css_class}[ "].*?</\1>', main, re.S)
        self.assertIsNotNone(found, f"no {css_class}")
        return found.group(0)

    def text(self, html):
        """The words a screen reader reads, without the decorative arrows."""
        html = re.sub(r'<span[^>]*aria-hidden="true"[^>]*>[^<]*</span>', "", html)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()

    def tiles(self, main):
        return main[
            main.index('<div class="journey-tiles">') : main.index('<section class="journey"')
        ]

    def items(self, main):
        """Each step's (classes, its HTML) in order; a step's entry cards are a list of their
        own, so each step runs to the next one."""
        steps = self.part(main, "journey-steps")
        return [
            re.match(r'<li class="journey-step ([^"]*)"[^>]*>(.*)', item, re.S).groups()
            for item in re.split(r'(?=<li class="journey-step )', steps)[1:]
        ]

    def card(self, main):
        """The 現在這一步's card, without its dot."""
        body = next(body for classes, body in self.items(main) if classes.startswith("is-current"))
        return body[body.index('<div class="journey-card">') :]

    def body(self, main, index):
        """What step `index` (0 first) opens to."""
        body = self.items(main)[index][1]
        return body[body.index('<div class="journey-about-body">') :]

    def opened(self, main, index):
        """What step `index` opens to: its words and its plain links."""
        body = self.body(main, index)
        return self.text(body), re.findall(r'<a href="([^"]*)">', body)

    def entries(self, html):
        """Each entry card's (link, words)."""
        return re.findall(
            r'<a class="entry-card" href="([^"]*)">.*?<span class="entry-card-text">([^<]*)</span>',
            html,
            re.S,
        )

    def steps(self, main):
        """Each step's (state, its words): the 現在這一步's card, any other step's row."""
        found = []
        for classes, body in self.items(main):
            summary = re.search(r"<summary>(.*?)</summary>", body, re.S)
            words = self.text(summary.group(1) if summary else body)
            found.append((classes.split()[0].removeprefix("is-"), words))
        return found


class EmptyStateHomeTests(HomeJourneyTestCase):
    def test_without_any_record_the_home_page_is_the_empty_state(self):
        # Spec #453 acceptance 1: a preview and the start button, no journey or tiles.
        main = self.main()
        self.assertIn('<h1 class="bird-title">從一份問卷開始</h1>', main)
        preview = self.part(main, "empty-preview")
        self.assertEqual(
            self.text(preview),
            "做完第一份問卷，這裡會排出您的照顧旅程 1 回答問題，大約 3 分鐘 "
            "2 馬上看到結果分級和建議 3 首頁一次告訴您一件該做的事",
        )
        self.assertNotIn("<a", preview)  # a preview, not a link
        self.assertRegex(
            main,
            r'<section class="hero-card" data-play-in-view>\s*<p>[^<]*</p>\s*'
            r'<a class="btn btn-hero btn-lg btn-start" '
            rf'href="{reverse("questionnaire_list")}">開始篩檢</a>',
        )
        self.assertEqual(len(SOLID.findall(main)), 1)
        for absent in ("journey-tiles", "journey-steps", "上次結果", "我已經有帳號"):
            self.assertNotIn(absent, main)

    def test_the_empty_state_keeps_the_guide_family_and_home_screen_ways_in(self):
        links = self.part(self.main(), "home-links")
        self.assertEqual(
            re.findall(r'<li([^>]*)><a href="([^"]*)">([^<]*)</a></li>', links),
            [
                ("", "/guide", "了解助聽器選配與補助"),
                ("", "/family", "我是家人"),
                (" data-hide-in-app", "/add_to_home", "加到手機主畫面"),
            ],
        )

    def test_another_account_s_records_leave_the_empty_state(self):
        other = consented_user(username="someone_else")
        Submission.objects.create(user=other, questionnaire=self.questionnaires[hhie_s.CODE])
        self.assertIn("從一份問卷開始", self.main())

    def test_only_a_signed_in_user_sees_it(self):
        # Spec #655 (#673, grill Q3): a visitor sees the two doors instead (test_home_doors); a
        # signed-in user's 空狀態首頁 has no way to log in.
        signed_in = self.main()
        self.client.logout()
        visitor = self.main()
        self.assertIn("從一份問卷開始", signed_in)
        self.assertNotIn("我已經有帳號，登入", signed_in)
        self.assertNotIn("從一份問卷開始", visitor)


class JourneyHomeTests(HomeJourneyTestCase):
    def test_only_an_audiogram_shows_the_journey_with_both_tiles_not_yet(self):
        # Spec #453 acceptance 2, #458 D6: grey tiles that are not links.
        self.make(PTA_55, PTA_55, tested_on=date(2026, 9, 1))
        main = self.main()
        tiles = self.tiles(main)
        self.assertNotIn("<a", tiles)
        self.assertEqual(
            self.text(tiles), "上次結果 還沒做 生活影響問卷 下次篩檢 還沒排 做完問卷後算出"
        )
        self.assertEqual(
            self.steps(main)[:3],
            [
                (
                    "current",
                    "1 現在這一步 填生活影響問卷 "
                    "先做一份生活影響問卷，了解聽力對您生活的影響。 去做問卷",
                ),
                ("done", "到醫院進行聽力檢查 已完成 2026/09/01"),
                ("done", "記錄聽力圖 已完成 2026/09/01"),
            ],
        )

    def test_the_last_result_tile_is_one_link_to_that_result_in_its_level_colour(self):
        # Spec #453 Q15, L1: the latest life-impact record, 4 points on HHIE-S, 無／極輕微影響.
        self.answer(on=date(2026, 9, 1), score=0)
        latest = self.answer(on=date(2026, 9, 26), score=4)
        self.answer(code=ioi_ha.CODE, on=date(2026, 10, 1))
        tiles = self.tiles(self.main())
        tile = re.search(r'<a class="journey-tile ([^"]*)" href="([^"]*)">(.*?)</a>', tiles, re.S)
        self.assertEqual(tile.group(1), "result-banner-normal")
        self.assertEqual(tile.group(2), reverse("result", args=[latest.pk]))
        self.assertEqual(self.text(tile.group(3)), "上次結果 4 分 無／極輕微影響")
        self.assertIn('<span class="journey-tile-arrow" aria-hidden="true">', tile.group(3))

    def test_the_next_screening_tile_says_the_days_left_big_and_the_day_small(self):
        # Spec #453 acceptance 17, turned round in readability batch 1 (the owner's B): 離下次篩檢,
        # the days left big as 上次結果's score, the day small under them.
        self.answer(on=date(2026, 9, 26))
        tiles = self.tiles(self.main())
        tile = tiles.split('<div class="journey-tile journey-tile-info">')[-1]
        self.assertEqual(self.text(tile), "離下次篩檢 134 天 2027/03/26")
        self.assertIn('<span class="journey-tile-score">134 <small>天</small></span>', tile)
        self.assertIn('<span class="journey-tile-small">2027/03/26</span>', tile)

    def test_without_a_day_to_count_to_the_tile_keeps_its_plain_label(self):
        # Readability batch 1: 離 only where there are days to count; 還沒排 and 已到期 as before.
        self.answer(on=date(2026, 5, 12))
        self.make(PTA_55, PTA_55)
        tiles = self.tiles(self.main())
        self.assertIn('<span class="journey-tile-label">下次篩檢</span>', tiles)
        self.assertIn('<span class="journey-tile-date">已到期</span>', tiles)
        self.assertNotIn("離下次篩檢", tiles)

    def test_a_retest_due_before_step_7_says_due_with_a_text_link(self):
        # Spec #453 acceptance 16: step 4 stays the 現在這一步.
        self.answer(on=date(2026, 5, 12))
        self.make(PTA_55, PTA_55)
        main = self.main()
        hhie = reverse("screening", args=[self.questionnaires[hhie_s.CODE].pk])
        tiles = self.tiles(main)
        self.assertIn('<span class="journey-tile-date">已到期</span>', tiles)
        self.assertIn(f'<a class="journey-tile-link" href="{hhie}">再做一次</a>', tiles)
        self.assertEqual(self.steps(main)[3][0], "current")

    def test_a_retest_due_at_step_7_has_no_second_way_on_top(self):
        # #458 D4: the card's button is the same thing.
        self.answer(on=date(2026, 5, 12))
        self.make(NORMAL, NORMAL)
        main = self.main()
        tiles = self.tiles(main)
        self.assertIn('<span class="journey-tile-date">已到期</span>', tiles)
        self.assertNotIn("<a", tiles.split("下次篩檢")[1])
        hhie = reverse("screening", args=[self.questionnaires[hhie_s.CODE].pk])
        self.assertIn(
            f'<a class="btn btn-hero btn-lg" href="{hhie}">再做一次（大約 3 分鐘）</a>',
            self.card(main),
        )

    def test_normal_hearing_steps_4_to_6_and_step_7_counting_down(self):
        # Spec #741 acceptance 9, #458 D2: step 4 says 不符資格, steps 5 and 6 目前不需要, and
        # counting down there is nothing to do today.
        self.answer(on=date(2026, 9, 12))
        self.make(NORMAL, NORMAL, tested_on=date(2026, 9, 1))
        main = self.main()
        self.assertRegex(main, greets("早安", "今天沒有要做的事"))
        self.assertEqual(SOLID.findall(main), [])
        self.assertIn(
            '<p class="journey-count"><span class="visually-hidden">進度 </span>6 / 7</p>', main
        )
        self.assertEqual(
            self.steps(main),
            [
                ("done", "填生活影響問卷 已完成 2026/09/12"),
                ("done", "到醫院進行聽力檢查 已完成 2026/09/01"),
                ("done", "記錄聽力圖 已完成 2026/09/01"),
                ("not-needed", "了解助聽器選配與補助 不符資格"),
                ("not-needed", "申請補助與配戴助聽器 目前不需要"),
                ("not-needed", "戴滿 3 個月做效益問卷 目前不需要"),
                ("current", "7 現在這一步 半年後再篩檢 還有 120 天 下次篩檢 2027/03/12"),
            ],
        )
        self.assertEqual(self.opened(main, 3), (f"{NORMAL_WORDS}", []))

    def test_with_something_to_press_there_is_one_thing_to_do_today(self):
        # An entry card counts, as a button does.
        self.answer()
        self.assertRegex(self.main(), greets("早安", "今天只要做一件事"))

    def test_the_greeting_follows_the_time_of_day_in_taiwan(self):
        # #458 D2: Asia/Taipei, the site's time zone.
        self.answer()
        for hour, greeting in (
            (5, "早安"),
            (11, "早安"),
            (12, "午安"),
            (17, "午安"),
            (18, "晚安"),
            (4, "晚安"),
        ):
            with self.subTest(hour=hour):
                self.now = timezone.make_aware(datetime(2026, 11, 12, hour, 30))
                self.assertRegex(self.main(), greets(greeting, "今天只要做一件事"))

    def test_only_hhie_s_the_seven_steps_and_the_hospital_card(self):
        # Spec #741 acceptance 1: the seven steps' names, step 2 the 現在這一步 with only
        # 查詢醫療院所, no to-dos.
        self.answer()
        main = self.main()
        self.assertEqual(
            [words.split(" 已完成")[0] for _, words in self.steps(main)],
            [
                "填生活影響問卷",
                "2 現在這一步 到醫院進行聽力檢查 查詢醫療院所",
                "記錄聽力圖",
                "了解助聽器選配與補助",
                "申請補助與配戴助聽器",
                "戴滿 3 個月做效益問卷",
                "半年後再篩檢",
            ],
        )
        card = self.card(main)
        self.assertEqual(self.entries(card), [("/qa/where-to-get-a-hearing-test", "查詢醫療院所")])
        self.assertNotIn("<p>", card[card.index("</h3>") : card.index("journey-entries")])
        self.assertEqual(SOLID.findall(card), [])
        for gone in ("要做的事", "checkbox", "網站會知道"):
            self.assertNotIn(gone, main)

    def test_without_an_audiogram_step_3_opens_to_its_two_sources(self):
        # Spec #741 acceptance 4, story 4: the small heading and two entry cards of one size, to
        # recording one (coming back here) and to the iPhone import.
        self.answer()
        main = self.main()
        body = self.body(main, 2)
        self.assertIn('<p class="journey-entries-title">聽力圖來源</p>', body)
        self.assertEqual(
            self.entries(body),
            [
                ("/audiograms/new?next=/", "醫院檢查報告"),
                ("/audiograms/import", "AirPods 自我檢測"),
            ],
        )

    def test_a_missing_frequency_s_card_is_its_sentence_and_editing_it(self):
        # Spec #741 acceptance 5.
        self.answer()
        audiogram = self.make(NORMAL, NORMAL)
        audiogram.points.filter(ear="left", frequency=4000).delete()
        card = self.card(self.main())
        self.assertEqual(
            self.text(card),
            "現在這一步 記錄聽力圖 這張聽力圖缺少頻率，資料不足，無法判斷。 修改這張聽力圖",
        )
        edit = reverse("audiogram_edit", args=[audiogram.pk])
        self.assertIn(f'<a class="btn btn-hero btn-lg" href="{edit}">', card)
        self.assertEqual(self.entries(card), [])

    def test_step_3_done_opens_to_the_stamp_and_the_audiogram_s_result(self):
        # Spec #741 acceptance 6.
        self.answer()
        audiogram = self.make((40, 40, 35, 35), PTA_55, tested_on=date(2026, 6, 2))
        body = self.body(self.main(), 2)
        self.assertIn(STAMP, body)
        result = self.part(body, "journey-audiogram")
        self.assertIn(f'href="/audiograms/{audiogram.pk}"', result)
        self.assertEqual(
            self.text(result),
            "聽力圖結果 2026/06/02 右耳 輕度 平均 37.5 dB 左耳 中度 平均 55 dB 看聽力圖",
        )
        self.assertIn('<span class="level-badge level-badge-mild_to_moderate">輕度</span>', result)

    def test_eligible_step_4_points_to_my_guide_and_opening_it_finishes_it(self):
        # Spec #741 acceptance 7, 8.
        self.answer()
        self.make(PTA_55, PTA_55)
        card = self.card(self.main())
        self.assertEqual(
            self.text(card),
            f"現在這一步 了解助聽器選配與補助 {GUIDE_WORDS} 看助聽器選配與補助",
        )
        self.assertEqual(self.entries(card), [("/guide", "看助聽器選配與補助")])
        self.client.get(reverse("guide"))
        main = self.main()
        self.assertEqual(self.steps(main)[3][0], "done")
        # Done, it opens to the stamp and still the way to my guide (the canvas's 3-a1).
        body = self.body(main, 3)
        self.assertIn(STAMP, body)
        self.assertEqual(self.entries(body), [("/guide", "看助聽器選配與補助")])
        self.assertNotIn(GUIDE_WORDS, body)

    def test_mild_to_moderate_step_4_points_to_types_and_prices(self):
        # Spec #741 acceptance 10: reading that chapter finishes it, and the route goes on to
        # 身障鑑定, the 補助站 not folded by the estimate.
        self.answer()
        self.make(PTA_45, PTA_45)
        card = self.card(self.main())
        self.assertIn(f"<p>{MILD_WORDS}</p>", card)
        self.assertEqual(self.entries(card), [("/guide/types-and-prices", "看助聽器的種類與價格")])
        self.client.get(reverse("guide_chapter", args=["types-and-prices"]))
        main = self.main()
        self.assertEqual(self.steps(main)[3][0], "done")
        self.assertIn('<h3 class="hero-card-title">身障鑑定與鑑定醫院</h3>', self.card(main))

    def test_a_done_step_opens_to_the_vermilion_stamp_step_1_to_the_stamp_alone(self):
        # Spec #741 acceptance 27: played once by site.css's play-once-stamp (ADR 0075, 0077).
        self.answer(on=date(2026, 9, 26))
        main = self.main()
        body = self.body(main, 0)
        self.assertIn(STAMP, body)
        self.assertEqual(self.text(body), "已完成")

    def test_wearing_counts_from_step_5_leaving_steps_1_to_4_unticked(self):
        # Spec #741 acceptance 28: none of steps 1 to 4 is done, none is in the way.
        self.answer(code=ioi_ha.CODE)
        steps = self.steps(self.main())
        self.assertEqual(
            [state for state, _ in steps], ["later"] * 4 + ["current", "later", "later"]
        )
        self.assertIn("配戴助聽器之後", steps[4][1])

    # Step 5's card by each stop (#745): test_answer_cards.

    def fitted(self, on):
        """Worn from `on`, the first IOI-HA done that day (steps 1 and 5 done, step 6 next)."""
        self.answer()
        AidAndSubsidy.objects.create(user=self.user, fitted_on=on, subsidy=Subsidy.OTHER)
        self.answer(code=ioi_ha.CODE, on=on)

    def buttons(self, card):
        return re.findall(r'<a class="btn btn-hero btn-lg" href="([^"]*)">([^<]*)</a>', card)

    def test_step_6_before_3_months_is_its_countdown_card(self):
        # Spec #741 acceptance 24: fitted 2026/09/27, so 3 months is 2026/12/27, 45 days on.
        self.fitted(date(2026, 9, 27))
        card = self.card(self.main())
        self.assertEqual(
            self.text(card),
            "現在這一步 戴滿 3 個月做效益問卷 和上一次進行比較 "
            "還有 45 天 2026/12/27 起可以再做一次",
        )
        self.assertEqual(self.buttons(card), [])
        # The ring: 46 of the 91 days gone, drawn once in view (ADR 0077); the days count up
        # while a screen reader hears the number itself.
        self.assertIn(
            '<path class="countdown-ring-arc play-once-ring" pathLength="1" '
            'd="M52 8A44 44 0 1 1 50.5 96"/>',
            card,
        )
        self.assertIn('<span class="countdown-ring-number" data-count-up>45</span>', card)

    def test_step_6_at_3_months_is_its_button_alone(self):
        # Spec #741 acceptance 25.
        self.fitted(date(2026, 8, 12))
        card = self.card(self.main())
        ioi = reverse("screening", args=[self.questionnaires[ioi_ha.CODE].pk])
        self.assertEqual(self.text(card), "現在這一步 戴滿 3 個月做效益問卷 做效益問卷")
        self.assertEqual(self.buttons(card), [(ioi, "做效益問卷")])
        self.assertNotIn("countdown-card", card)

    def test_step_7_s_three_cases(self):
        # Spec #741 acceptance 26: counting down from a life-impact record a day old, due 6
        # months on, and without one (worn, both IOI-HA done).
        hhie = reverse("screening", args=[self.questionnaires[hhie_s.CODE].pk])

        def counting():
            self.answer(on=date(2026, 11, 11))
            self.make(NORMAL, NORMAL)

        def due():
            self.answer(on=date(2026, 5, 12))
            self.make(NORMAL, NORMAL)

        def none():
            AidAndSubsidy.objects.create(
                user=self.user, fitted_on=date(2026, 5, 1), subsidy=Subsidy.OTHER
            )
            self.answer(code=ioi_ha.CODE, on=date(2026, 5, 10))
            self.answer(code=ioi_ha.CODE, on=date(2026, 9, 1))

        for name, records, words, buttons in (
            ("counting", counting, "還有 180 天 下次篩檢 2027/05/11", []),
            ("due", due, "時間到了！ 再做一次（大約 3 分鐘）", [(hhie, "再做一次（大約 3 分鐘）")]),  # noqa: RUF001
            ("none", none, "還沒有完成第一次篩檢。 去做問卷", [(hhie, "去做問卷")]),
        ):
            with self.subTest(name):
                self.fresh_user(name)
                records()
                card = self.card(self.main())
                self.assertEqual(self.text(card), f"現在這一步 半年後再篩檢 {words}")
                self.assertEqual(self.buttons(card), buttons)

    def test_done_steps_say_their_day(self):
        # #458 D7.
        self.answer(on=date(2026, 9, 26))
        self.make(PTA_55, PTA_55, tested_on=date(2026, 6, 15))
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 7, 1), subsidy=Subsidy.OTHER
        )
        self.answer(code=ioi_ha.CODE, on=date(2026, 7, 15))
        self.answer(code=ioi_ha.CODE, on=date(2026, 10, 15))
        self.assertEqual(
            [body for state, body in self.steps(self.main()) if state == "done"],
            [
                "填生活影響問卷 已完成 2026/09/26",
                "到醫院進行聽力檢查 已完成 2026/06/15",
                "記錄聽力圖 已完成 2026/06/15",
                "申請補助與配戴助聽器 已完成 2026/07/01",
                "戴滿 3 個月做效益問卷 已完成 2026/10/15",
            ],
        )

    def test_print_share_and_add_to_home_are_text_links_under_the_journey(self):
        # Spec #453 acceptance 18: pwa-nav.js hides [data-hide-in-app] in the home-screen app;
        # the page itself hides nothing, so without JavaScript it shows.
        self.answer()
        main = self.main()
        links = self.part(main, "home-links")
        self.assertEqual(
            re.findall(r'<li([^>]*)><a href="([^"]*)">([^<]*)</a></li>', links),
            [
                ("", "/report", "印聽力報告"),
                ("", "/share", "分享給家人"),
                (" data-hide-in-app", "/add_to_home", "加到手機主畫面"),
            ],
        )
        self.assertLess(main.index("journey-steps"), main.index("home-links"))
        self.assertNotRegex(links, r"\shidden[\s=>]")

    def test_the_old_returning_home_is_gone(self):
        # ADR 0044 replaces ADR 0026's greeting band, gauge, elder and grouped cards.
        self.answer()
        main = self.main()
        for gone in (
            "歡迎回來",
            "score-gauge",
            "home-illustration",
            "建議您下一步",
            "您還可以",
            "more-group",
            "看我的紀錄與趨勢",
        ):
            self.assertNotIn(gone, main)

    def test_signed_in_home_is_never_cached(self):
        self.answer()
        response = self.client.get(reverse("index"))
        self.assertIn("no-store", response["Cache-Control"])

    def count_queries(self):
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(reverse("index")).status_code, 200)
        return len(queries)

    def test_queries_do_not_grow_with_records(self):
        # CODING_STANDARDS 15.
        self.make(PTA_55, PTA_55)
        self.answer(on=date(2026, 9, 1))
        self.answer(on=date(2026, 9, 2))
        two = self.count_queries()
        for day in range(3, 9):
            self.answer(on=date(2026, 9, day))
            self.answer(code=hhia_s.CODE, on=date(2026, 8, day))
        self.make(PTA_55, PTA_55, tested_on=date(2026, 8, 1))
        self.assertEqual(self.count_queries(), two)


class StepInteractionTests(HomeJourneyTestCase):
    """#459 I1 + I2 (the owner's pick on the step interactions page, ADR 0028's 2026-11-12
    exception)."""

    def step_4_with_three_done(self):
        self.answer(on=date(2026, 9, 26), score=4)
        self.make(PTA_55, PTA_55, tested_on=date(2026, 9, 1))

    def test_every_step_but_the_current_one_opens_to_say_what_it_is(self):
        # I1: native <details>, so it opens without JavaScript too; the card is no <details>.
        # A done step opens to its stamp (spec #741 acceptance 27).
        self.step_4_with_three_done()
        main = self.main()
        items = self.items(main)
        self.assertEqual(
            ["<details" in body for _, body in items], [True, True, True, False, True, True, True]
        )
        self.assertEqual(self.opened(main, 0), ("已完成", []))
        self.assertEqual(self.opened(main, 1), ("已完成", []))
        self.assertEqual(
            self.opened(main, 4), ("照選配路線一站一站走，從找聽力師到開始戴助聽器。", [])
        )
        self.assertEqual(
            self.opened(main, 5),
            ("戴滿 3 個月後，再做一次問卷和第一次比較，看看助聽器的幫助。", []),
        )
        # Step 7 opens to its countdown card (the canvas's 5-a).
        self.assertEqual(self.opened(main, 6), ("還有 134 天 下次篩檢 2027/03/26", []))
        self.assertIn('<div class="countdown-card">', self.body(main, 6))
        self.assertNotIn("<details open", main)

    def test_the_line_is_blue_up_to_the_current_step_without_a_progress_bar(self):
        # I2: the walked steps, numbered for the entrance's timing; 「3 / 7」 stays.
        self.step_4_with_three_done()
        main = self.main()
        # Played once the 現在這一步's one thing is in view (ADR 0029; #480 moved the mark there
        # from the whole step, which the to-dos under it made too tall); each stamp and step 7's
        # countdown ring wait too.
        self.assertRegex(
            main,
            r'<li class="journey-step is-current"[^>]*>\s*<span class="journey-dot">4</span>\s*'
            r'<div class="journey-card">\s*<section class="hero-card" data-play-in-view>',
        )
        rings = main.count('<div class="countdown-ring">')
        self.assertEqual(rings, 1)
        self.assertEqual(main.count("data-play-in-view"), 1 + main.count(STAMP) + rings)
        steps = re.findall(r'<li class="journey-step ([^"]*)" style="--journey-step: (\d)"', main)
        self.assertEqual(
            steps,
            [
                ("is-done is-walked", "0"),
                ("is-done is-walked", "1"),
                ("is-done is-walked", "2"),
                ("is-current", "3"),
                ("is-later", "4"),
                ("is-later", "5"),
                ("is-later", "6"),
            ],
        )
        self.assertIn('<span class="visually-hidden">進度 </span>3 / 7</p>', main)
        self.assertNotIn("journey-bar", main)

    def test_only_the_journey_loads_its_script(self):
        script = "screening/frontend/care-journey.js"
        self.assertNotIn(script, self.client.get(reverse("index")).content.decode())
        self.answer()
        self.assertIn(script, self.client.get(reverse("index")).content.decode())


class OneSolidButtonTests(HomeJourneyTestCase):
    """Spec #453 acceptance 19 and 20 across the states the journey has."""

    def test_every_state_has_at_most_one_solid_button_and_dates_in_full(self):
        def fitted(on, ioi_on=None, **fields):
            def records():
                AidAndSubsidy.objects.create(
                    user=self.user, fitted_on=on, subsidy=Subsidy.OTHER, **fields
                )
                if ioi_on:
                    self.answer(code=ioi_ha.CODE, on=ioi_on)

            return records

        states = {
            "audiogram only": [lambda: self.make(PTA_55, PTA_55)],
            "step 2": [lambda: self.answer()],
            "step 4": [lambda: self.answer(), lambda: self.make(PTA_55, PTA_55)],
            "step 5": [lambda: self.answer(), fitted(date(2026, 10, 3))],
            "step 6 counting": [
                lambda: self.answer(),
                fitted(date(2026, 10, 3), date(2026, 10, 3)),
            ],
            "step 6 due": [lambda: self.answer(), fitted(date(2026, 8, 1), date(2026, 8, 1))],
            "step 7 counting": [
                lambda: self.answer(on=date(2026, 9, 26)),
                lambda: self.make(NORMAL, NORMAL),
            ],
            "step 7 due": [
                lambda: self.answer(on=date(2026, 5, 10)),
                lambda: self.make(NORMAL, NORMAL),
            ],
            "due at step 4": [
                lambda: self.answer(on=date(2026, 4, 20)),
                lambda: self.make(PTA_55, PTA_55),
            ],
        }
        for name, records in states.items():
            with self.subTest(state=name):
                self.fresh_user(name)
                for record in records:
                    record()
                main = self.main()
                self.assertLessEqual(len(SOLID.findall(main)), 1)
                # A day is never written month/day only, as 9/26.
                self.assertNotRegex(self.text(main), r"(?<![\d/])\d{1,2}/\d{1,2}(?![\d/])")
