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
    GuideChapterView,
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
PTA_55 = test_guide_summary.PTA_55
SOLID = re.compile(r'class="btn btn-primary\b')
# The 現在這一步 card's 待辦 (spec #478), left to test_journey_todos: these check its one thing.
TODOS = re.compile(r'<div class="todos">.*?</div>', re.S)


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

    def card(self, main):
        return TODOS.sub("", self.part(main, "journey-card"))

    def items(self, main):
        """Each step's (classes, its HTML) in order."""
        steps = TODOS.sub("", self.part(main, "journey-steps"))
        return re.findall(r'<li class="journey-step ([^"]*)"[^>]*>(.*?)</li>', steps, re.S)

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
        self.assertIn('<h1 class="h3">從一份問卷開始</h1>', main)
        preview = self.part(main, "empty-preview")
        self.assertEqual(
            self.text(preview),
            "做完第一份問卷，這裡會排出您的照顧旅程 1 回答問題，大約 3 分鐘 "
            "2 馬上看到結果分級和建議 3 首頁一次告訴您一件該做的事",
        )
        self.assertNotIn("<a", preview)  # a preview, not a link
        self.assertRegex(
            main,
            r'<a class="btn btn-primary btn-lg btn-start w-full" data-play-in-view '
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

    def test_a_visitor_sees_it_with_registering_to_keep_the_result(self):
        # #471 (mockup #458 ⑪ for a visitor): the same page, with a way to log in; #499: its last
        # step registering to keep the result. A signed-in user has neither (test_home for the
        # visitor's).
        signed_in = self.main()
        self.client.logout()
        visitor = self.main()
        for main, signed_out in ((signed_in, False), (visitor, True)):
            with self.subTest(signed_out=signed_out):
                self.assertIn("從一份問卷開始", main)
                self.assertEqual("想保存再註冊，不註冊也看得到結果。" in main, signed_out)
                self.assertEqual("我已經有帳號，登入" in main, signed_out)


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
            self.steps(main)[:2],
            [
                (
                    "current",
                    "1 現在這一步 填生活影響問卷 "
                    "先做一份生活影響問卷，了解聽力對您生活的影響。 去做問卷",
                ),
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

    def test_the_next_screening_tile_says_the_day_big_and_the_days_left_small(self):
        # Spec #453 acceptance 17.
        self.answer(on=date(2026, 9, 26))
        tiles = self.tiles(self.main())
        self.assertIn('<span class="journey-tile-date">2027/03/26</span>', tiles)
        self.assertIn('<span class="journey-tile-small">還有 134 天</span>', tiles)

    def test_a_retest_due_before_step_5_says_due_with_a_text_link(self):
        # Spec #453 acceptance 16: step 3 stays the 現在這一步, the one solid button its.
        self.answer(on=date(2026, 5, 12))
        self.make(PTA_55, PTA_55)
        main = self.main()
        hhie = reverse("screening", args=[self.questionnaires[hhie_s.CODE].pk])
        tiles = self.tiles(main)
        self.assertIn('<span class="journey-tile-date">已到期</span>', tiles)
        self.assertIn(f'<a class="journey-tile-link" href="{hhie}">再做一次</a>', tiles)
        self.assertEqual(self.steps(main)[2][0], "current")
        self.assertEqual(len(SOLID.findall(main)), 1)

    def test_a_retest_due_at_step_5_has_no_second_way_on_top(self):
        # #458 D4: the card's button is the same thing.
        self.answer(on=date(2026, 5, 12))
        self.make(NORMAL, NORMAL)
        main = self.main()
        tiles = self.tiles(main)
        self.assertIn('<span class="journey-tile-date">已到期</span>', tiles)
        self.assertNotIn("<a", tiles.split("下次篩檢")[1])
        hhie = reverse("screening", args=[self.questionnaires[hhie_s.CODE].pk])
        self.assertIn(
            f'<a class="btn btn-primary btn-lg w-full" href="{hhie}">再做一次（大約 3 分鐘）</a>',
            self.card(main),
        )

    def test_counting_down_there_is_nothing_to_do_today_and_no_solid_button(self):
        # Spec #453 acceptance 14 and 7, #458 D2: 目前不需要 said beside steps 3 and 4.
        self.answer(on=date(2026, 9, 12))
        self.make(NORMAL, NORMAL, tested_on=date(2026, 9, 1))
        main = self.main()
        self.assertIn('<h1 class="h3">早安，今天沒有要做的事</h1>', main)
        self.assertEqual(SOLID.findall(main), [])
        self.assertIn(
            '<p class="journey-count"><span class="visually-hidden">進度 </span>4 / 5</p>', main
        )
        self.assertEqual(
            self.steps(main),
            [
                ("done", "填生活影響問卷 已完成 2026/09/12"),
                ("done", "記錄聽力圖 已完成 2026/09/01"),
                ("not-needed", "了解助聽器選配與補助 目前不需要"),
                ("not-needed", "戴滿 3 個月做效益問卷 目前不需要"),
                ("current", "5 現在這一步 半年後再篩檢 時間到了，這裡會出現「再做一次」的按鈕。"),
            ],
        )

    def test_with_a_button_there_is_one_thing_to_do_today(self):
        self.answer()
        self.assertIn('<h1 class="h3">早安，今天只要做一件事</h1>', self.main())

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
                self.assertIn(f'<h1 class="h3">{greeting}，今天只要做一件事</h1>', self.main())

    def test_step_3_s_card_is_the_stop_its_reason_and_its_button(self):
        # Spec #453 acceptance 6; the owner on #458: no 目前這一站 label, no 「因為：」 (D10).
        self.answer()
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        AidAndSubsidy.objects.create(user=self.user, certificate="yes")
        card = self.card(self.main())
        self.assertEqual(
            self.text(card),
            "現在這一步 九號表：申請助聽器補助 您已經有身障證明，可以準備申請九號表的助聽器補助。 "
            "看九號表的流程",
        )
        self.assertIn(
            '<a class="btn btn-primary btn-lg w-full" href="/guide/form-9">看九號表的流程</a>', card
        )
        self.assertNotIn("checkbox", card)

    def test_a_stop_without_a_button_links_to_its_page_in_words(self):
        # 等待核定公文 has nothing to do but wait (#455): a text link, no solid button.
        self.answer()
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        AidAndSubsidy.objects.create(user=self.user, certificate="yes", form_9_done=True)
        main = self.main()
        self.assertEqual(SOLID.findall(main), [])
        self.assertIn(
            '<a class="journey-card-link" href="/guide/form-9#steps-title">看這一站的說明</a>',
            self.card(main),
        )

    def test_each_card_shows_the_journey_s_words_and_button(self):
        # Spec #453 acceptance 3, 5, 9, 11, 12 on the page; judged in test_care_journey.
        def no_audiogram():
            self.answer()

        def missing_frequency():
            self.answer()
            audiogram = self.make(NORMAL, NORMAL)
            audiogram.points.filter(ear="left", frequency=4000).delete()
            return audiogram

        def wearing_without_a_date():
            self.answer(wearing=True)

        def fitted_40_days_ago():
            self.answer()
            AidAndSubsidy.objects.create(
                user=self.user, fitted_on=date(2026, 10, 3), subsidy=Subsidy.OTHER
            )

        def fitted_3_months_ago():
            self.answer()
            AidAndSubsidy.objects.create(
                user=self.user, fitted_on=date(2026, 8, 12), subsidy=Subsidy.OTHER
            )

        ioi = reverse("screening", args=[self.questionnaires[ioi_ha.CODE].pk])
        for records, title, because, button in (
            (
                no_audiogram,
                "記錄聽力圖",
                "您還沒有記錄聽力圖，選配指引要用聽力圖才能整理下一步。",
                ("/audiograms/new", "記錄聽力圖"),
            ),
            (
                missing_frequency,
                "記錄聽力圖",
                "這張聽力圖缺少頻率，資料不足，無法判斷。",
                ("edit", "修改這張聽力圖"),
            ),
            (
                wearing_without_a_date,
                "配戴助聽器之後",
                "記下開始戴的日期，才算得出什麼時候要做使用效益驗證。",
                ("/guide/after-fitting#record-title", "記錄配戴的效果"),
            ),
            (
                fitted_40_days_ago,
                "戴滿 3 個月做效益問卷",
                "再 52 天滿 3 個月，到時候做使用效益問卷（IOI-HA）。",
                None,
            ),
            (
                fitted_3_months_ago,
                "戴滿 3 個月做效益問卷",
                "您已經戴滿 3 個月，可以做使用效益問卷（IOI-HA），看助聽器幫了多少。",
                (ioi, "做效益問卷"),
            ),
        ):
            with self.subTest(records=records.__name__):
                self.fresh_user(records.__name__)
                audiogram = records()
                card = self.card(self.main())
                self.assertIn(f'<h3 class="journey-card-title">{title}</h3>', card)
                self.assertIn(f'<p class="journey-card-because">{because}</p>', card)
                self.assertNotIn("因為", card)
                buttons = re.findall(
                    r'<a class="btn btn-primary[^"]*" href="([^"]*)">([^<]*)</a>', card
                )
                if button is None:
                    self.assertEqual(buttons, [])
                    continue
                href, text = button
                if href == "edit":
                    href = reverse("audiogram_edit", args=[audiogram.pk])
                self.assertEqual(buttons, [(href, text)])

    def test_done_steps_say_their_day(self):
        # #458 D7: step 3 its fitting date, step 4 its IOI-HA's.
        self.answer(on=date(2026, 9, 26))
        self.make(PTA_55, PTA_55, tested_on=date(2026, 6, 15))
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 7, 1), subsidy=Subsidy.OTHER
        )
        self.answer(code=ioi_ha.CODE, on=date(2026, 10, 15))
        self.assertEqual(
            [body for state, body in self.steps(self.main()) if state == "done"],
            [
                "填生活影響問卷 已完成 2026/09/26",
                "記錄聽力圖 已完成 2026/06/15",
                "了解助聽器選配與補助 已完成 2026/07/01",
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

    def step_3_with_two_done(self):
        self.answer(on=date(2026, 9, 26), score=4)
        self.make(PTA_55, PTA_55, tested_on=date(2026, 9, 1))

    def test_every_step_but_the_current_one_opens_to_say_what_it_is(self):
        # I1: native <details>, so it opens without JavaScript too; the card is no <details>.
        self.step_3_with_two_done()
        result = self.user.submissions.get().pk
        items = self.items(self.main())
        self.assertEqual(["<details" in body for _, body in items], [True, True, False, True, True])

        def opened(index):
            body = re.search(r'<div class="journey-about-body">(.*?)</div>', items[index][1], re.S)
            return self.text(body.group(1)), re.findall(r'<a href="([^"]*)">', body.group(1))

        self.assertEqual(
            opened(0),
            (
                "先做一份生活影響問卷，了解聽力對您生活的影響。 "
                "上次結果：無／極輕微影響 看上次結果",
                [reverse("result", args=[result])],
            ),
        )
        self.assertEqual(
            opened(1), ("選配指引要用聽力圖才能整理下一步。 看助聽器選配與補助", ["/guide"])
        )
        self.assertEqual(
            opened(3),
            ("買了助聽器、戴滿 3 個月後，做使用效益問卷（IOI-HA），看助聽器幫了多少。", []),
        )
        self.assertEqual(
            opened(4),
            (
                "時間到了，這裡會出現「再做一次」的按鈕。 下次篩檢 2027/03/26・還有 134 天",
                [],
            ),
        )
        self.assertNotIn("<details open", self.main())

    def test_the_line_is_blue_up_to_the_current_step_without_a_progress_bar(self):
        # I2: the walked steps, numbered for the entrance's timing; 「2 / 5」 stays.
        self.step_3_with_two_done()
        main = self.main()
        # Played once the 現在這一步's one thing is in view (ADR 0029; #480 moved the mark there
        # from the whole step, which the to-dos under it made too tall).
        self.assertRegex(
            main,
            r'<li class="journey-step is-current"[^>]*>\s*<span class="journey-dot">3</span>\s*'
            r'<div class="journey-card">\s*<div class="journey-card-main" '
            r"data-play-in-view>",
        )
        self.assertEqual(main.count("data-play-in-view"), 1)
        steps = re.findall(r'<li class="journey-step ([^"]*)" style="--journey-step: (\d)"', main)
        self.assertEqual(
            steps,
            [
                ("is-done is-walked", "0"),
                ("is-done is-walked", "1"),
                ("is-current", "2"),
                ("is-later", "3"),
                ("is-later", "4"),
            ],
        )
        self.assertIn('<span class="visually-hidden">進度 </span>2 / 5</p>', main)
        self.assertNotIn("journey-bar", main)

    def test_only_the_journey_loads_its_script(self):
        script = "screening/frontend/care-journey.js"
        self.assertNotIn(script, self.client.get(reverse("index")).content.decode())
        self.answer()
        self.assertIn(script, self.client.get(reverse("index")).content.decode())


class OneSolidButtonTests(HomeJourneyTestCase):
    """Spec #453 acceptance 19 and 20 across the states #458 drew."""

    def test_every_state_has_at_most_one_solid_button_and_dates_in_full(self):
        def fitted(on, **fields):
            return lambda: AidAndSubsidy.objects.create(
                user=self.user, fitted_on=on, subsidy=Subsidy.OTHER, **fields
            )

        states = {
            "audiogram only": [lambda: self.make(PTA_55, PTA_55)],
            "step 2": [lambda: self.answer()],
            "step 3": [lambda: self.answer(), lambda: self.make(PTA_55, PTA_55)],
            "step 4 counting": [lambda: self.answer(), fitted(date(2026, 10, 3))],
            "step 4 due": [lambda: self.answer(), fitted(date(2026, 8, 1))],
            "step 5 counting": [
                lambda: self.answer(on=date(2026, 9, 26)),
                lambda: self.make(NORMAL, NORMAL),
            ],
            "step 5 due": [
                lambda: self.answer(on=date(2026, 5, 10)),
                lambda: self.make(NORMAL, NORMAL),
            ],
            "due at step 3": [
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
