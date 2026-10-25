"""Spec #148 batch 1, ticket #150: the new-user home page.
Spec #148 batch 2, ticket #159: the returning-user home page.
"""

import math
import re
from datetime import date, datetime, timedelta
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Audiogram, Category, Question, Questionnaire, Submission
from screening.tests.helpers import consented_user


class NewUserHomeTests(TestCase):
    PASSWORD = "Xk9#mPq2vLw"
    STEPS = (
        "建立帳號，大約 1 分鐘。",
        "回答問題，大約 3 分鐘。",
        "馬上看到結果分級和建議。",
        "半年後再做，看分數變化。",
    )
    OLD_HINT = "第一次使用請先註冊，已有帳號請直接登入。"

    def setUp(self):
        self.list_url = reverse("questionnaire_list")
        self.start_url = f"{reverse('register')}?next={self.list_url}"
        self.login_url = f"{reverse('login')}?next={self.list_url}"

    def _main(self):
        content = self.client.get(reverse("index")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _link(self, main, text):
        """The href of the link in the page body whose whole text is `text`."""
        links = re.findall(r'<a[^>]*href="([^"]*)"[^>]*>\s*([^<]*?)\s*</a>', main)
        hrefs = [href for href, label in links if label == text]
        self.assertEqual(len(hrefs), 1, f"{text}: {links}")
        return hrefs[0]

    def _steps(self, main):
        steps = re.search(r'<ol class="step-cards.*?</ol>', main, re.DOTALL).group(0)
        return re.findall(r"<span>([^<]+)</span>", steps)

    def test_anonymous_sees_start_and_login_buttons_and_four_steps(self):
        main = self._main()
        self.assertEqual(self._link(main, "開始篩檢"), self.start_url)
        self.assertEqual(self._link(main, "我已經有帳號，登入"), self.login_url)
        self.assertEqual(self._steps(main), list(self.STEPS))
        self.assertNotIn(self.OLD_HINT, main)

    def test_hero_labels_sit_above_the_title(self):
        main = self._main()
        hero = main[main.index('<section class="home-hero') : main.index("<h1")]
        chips = re.findall(r'<span class="home-chip">.*?</svg>\s*([^<]+?)\s*</span>', hero, re.S)
        self.assertEqual(chips, ["約 3 分鐘", "國際標準量表"])
        self.assertEqual(hero.count('aria-hidden="true"'), hero.count("<svg"))

    def test_login_is_a_text_link_under_the_start_button(self):
        main = self._main()
        login = re.search(r"<a([^>]*)>\s*我已經有帳號，登入\s*</a>", main)
        self.assertNotIn("btn", login.group(1))
        self.assertLess(main.index(">開始篩檢<"), login.start())

    def test_title_is_larger_and_the_picture_is_the_smiling_elder(self):
        main = self._main()
        self.assertRegex(main, r'<h1 class="[^"]*\btext-center\b[^"]*">了解聽力對您生活的影響</h1>')
        start = main.index('class="home-illustration"')
        picture = main[start : main.index("</svg>", start)]
        for part in ("ill-face", "ill-hair", "ill-cheek", "ill-accent"):
            self.assertIn(part, picture)

    def test_result_preview_shows_the_result_page_score_bar(self):
        # Design picker round 2: the example card carries the same bar as the result page,
        # with HHIE-S's own thresholds and the made-up 18 points.
        main = self._main()
        preview = main[main.index('<figure class="result-preview">') : main.index("</figure>")]
        self.assertIn('<div class="score-bar" aria-hidden="true">', preview)
        for level, width in (("normal", 20), ("mild_to_moderate", 40), ("severe", 40)):
            with self.subTest(level=level):
                self.assertIn(
                    f'class="score-bar-segment score-bar-segment-{level}" '
                    f'style="width: {width}.00%"',
                    preview,
                )
        self.assertIn('class="score-bar-marker" style="--position: 45.00%"', preview)
        self.assertLess(preview.index("result-banner"), preview.index("score-bar"))

    # The logo and the one-time ring are drawn by CSS on btn-start and checked in e2e.
    def test_start_button_uses_the_btn_start_class(self):
        for logged_in in (False, True):
            if logged_in:
                self.client.force_login(consented_user(username="startbutton"))
            with self.subTest(logged_in=logged_in):
                self.assertRegex(
                    self._main(),
                    r'<a class="btn btn-primary btn-lg btn-start w-full"[^>]*>開始篩檢</a>',
                )

    def test_login_button_logs_in_then_chooses_a_questionnaire(self):
        consented_user(username="returning", password=self.PASSWORD)
        page = self.client.get(self._link(self._main(), "我已經有帳號，登入"))
        self.assertContains(
            page, f'<input type="hidden" name="next" value="{self.list_url}">', html=True
        )
        response = self.client.post(
            reverse("login"),
            {"username": "returning", "password": self.PASSWORD, "next": self.list_url},
        )
        self.assertRedirects(response, self.list_url)

    def test_start_registers_then_consents_then_chooses_a_questionnaire(self):
        page = self.client.get(self._link(self._main(), "開始篩檢"))
        self.assertTemplateUsed(page, "screening/register.html")
        self.assertContains(
            page, f'<input type="hidden" name="next" value="{self.list_url}">', html=True
        )
        response = self.client.post(
            reverse("register"),
            {
                "username": "newcomer",
                "email": "newcomer@example.com",
                "password1": self.PASSWORD,
                "password2": self.PASSWORD,
                "next": self.list_url,
            },
        )
        consent_url = f"{reverse('consent')}?next={self.list_url}"
        self.assertRedirects(response, consent_url)
        response = self.client.post(consent_url, {"agree": "1", "next": self.list_url})
        # The wizard's first screen greets the new account (#152).
        self.assertRedirects(response, f"{self.list_url}?from=consent")

    def test_other_protected_pages_still_go_to_login_and_back(self):
        consented_user(username="tester", password=self.PASSWORD)
        for url in (self.list_url, reverse("my_hearing"), reverse("audiogram_list")):
            with self.subTest(url=url):
                self.client.logout()
                login_url = f"{reverse('login')}?next={url}"
                self.assertRedirects(self.client.get(url), login_url)
                response = self.client.post(
                    reverse("login"),
                    {"username": "tester", "password": self.PASSWORD, "next": url},
                )
                self.assertRedirects(response, url)

    def test_signed_in_user_without_records_sees_new_user_home(self):
        audiogram_only = consented_user(username="audiogram_only")
        # Spec #148 story 4: an audiogram is not a questionnaire record.
        Audiogram.objects.create(user=audiogram_only, tested_on=date(2026, 10, 1))
        for user in (consented_user(username="no_records"), audiogram_only):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                main = self._main()
                self.assertEqual(self._link(main, "開始篩檢"), self.list_url)
                self.assertNotIn("我已經有帳號，登入", main)
                self.assertEqual(self._steps(main), list(self.STEPS))
                self.assertNotIn(self.OLD_HINT, main)
                self.assertNotIn("請先註冊", main)

    def test_result_preview_uses_the_result_page_level_style(self):
        # 18 points on HHIE-S is mild to moderate; the result page draws its banner the same way.
        self.assertInHTML(
            '<div class="result-banner result-banner-mild_to_moderate">'
            '<div class="result-level">輕度到中度影響</div>'
            "<div>HHIE-S 總分 18 分（滿分 40）</div></div>",
            self._main(),
        )

    def test_anonymous_home_has_no_never_cache_header(self):
        response = self.client.get(reverse("index"))
        self.assertNotIn("no-store", response.get("Cache-Control", ""))


class ReturningUserHomeTests(TestCase):
    """Spec #148 batch 2, ticket #159: the returning-user home page."""

    # Acceptance 9: "today" and every record's time are fixed, never the real clock.
    TODAY = date(2026, 10, 22)
    NOON = timezone.make_aware(datetime(2026, 10, 22, 12))
    PRIMARY = "btn btn-primary btn-lg"
    SECONDARY = "btn btn-outline-primary btn-lg"

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="returning_tester")
        cls.questions = {}
        for name, code, count in (
            ("HHIE-S", "hhie-s", 10),
            ("HHIA-S", "hhia-s", 10),
            ("IOI-HA", "ioi-ha", 7),
            ("SSQ12-TW", "ssq12-tw", 12),
        ):
            questionnaire = Questionnaire.objects.create(questionnaire_name=name, code=code)
            cls.questions[code] = Question.objects.bulk_create(
                Question(
                    questionnaire=questionnaire,
                    question_text=f"{name}題{i}",
                    question_number=i,
                    category=(
                        (Category.EMOTIONAL if i <= 5 else Category.SOCIAL)
                        if code.startswith("hhi")
                        else Category.NONE
                    ),
                )
                for i in range(1, count + 1)
            )
        cls.hhie_s = Questionnaire.objects.get(code="hhie-s")
        cls.hhia_s = Questionnaire.objects.get(code="hhia-s")

    def setUp(self):
        self.client.force_login(self.user)
        real_localdate = timezone.localdate

        def localdate(value=None, timezone=None):
            return self.TODAY if value is None else real_localdate(value, timezone)

        self.enterContext(patch("django.utils.timezone.localdate", localdate))

    def _submit(self, code, scores, days_ago, user=None, **fields):
        questionnaire = Questionnaire.objects.get(code=code)
        submission = Submission.objects.create(
            user=user or self.user, questionnaire=questionnaire, **fields
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question, score in zip(self.questions[code], scores, strict=True)
        )
        Submission.objects.filter(pk=submission.pk).update(
            created_at=self.NOON - timedelta(days=days_ago)
        )
        submission.refresh_from_db()
        return submission

    def _hhie_s(self, days_ago, user=None):
        return self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago, user=user)  # 12

    def _main(self):
        content = self.client.get(reverse("index")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _retake_url(self, questionnaire):
        return reverse("screening", args=[questionnaire.pk])

    def test_due_retest_shows_reminder_and_primary_retake_button(self):
        # Acceptance 4: 2026/04/22 is exactly six months before "today".
        submission = self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=183)
        main = self._main()
        # Option D (ADR 0026): the due reminder is a pale blue box with a flag.
        self.assertRegex(
            main,
            r'<p class="welcome-reminder welcome-reminder-due"><svg[^>]*><path d="M5 21V4'
            r".*?</svg>"
            r"<span>距離上次的生活影響評估已經滿 6 個月，建議再做一次追蹤。</span></p>",
        )
        self.assertIn(
            f'<a class="{self.PRIMARY}" href="{self._retake_url(self.hhie_s)}">'
            "再做一次（大約 3 分鐘）</a>",
            main,
        )
        self.assertNotIn("看我的紀錄與趨勢", main)
        self.assertIn(reverse("result", args=[submission.id]), main)

    def test_not_due_shows_next_date_and_secondary_retake(self):
        # Acceptance 5: one month in (2026/09/22), so next 2027/03/22.
        self._submit("hhie-s", [4, 4, 4] + [0] * 7, days_ago=30)
        main = self._main()
        self.assertRegex(
            main,
            r'<p class="welcome-reminder"><svg[^>]*><rect .*?</svg>'
            r"<span>下次建議 2027/03/22 再做</span></p>",
        )
        self.assertIn(
            f'<a class="{self.PRIMARY}" href="{reverse("my_hearing")}">看我的紀錄與趨勢</a>', main
        )
        self.assertIn(
            f'<a class="{self.SECONDARY}" href="{self._retake_url(self.hhie_s)}">再做一次</a>', main
        )
        self.assertNotIn("再做一次（大約 3 分鐘）", main)

    def test_last_result_card_shows_the_latest_life_impact_record(self):
        # Acceptance 2: newer IOI-HA and SSQ12 records do not take the card from HHIE-S.
        self._submit("hhie-s", [0] * 10, days_ago=40)
        latest = self._hhie_s(days_ago=30)
        self._submit("ioi-ha", [3] * 7, days_ago=20, norm_group="ungrouped")
        self._submit("ssq12-tw", [6] * 12, days_ago=10)
        main = self._main()
        self.assertIn('<p class="welcome-date">上次是 2026/09/22 做的</p>', main)
        self.assertIn('<h2 class="result-level mb-0">輕度到中度影響</h2>', main)
        self.assertIn("<div>HHIE-S 總分 12 分（滿分 40）</div>", main)
        self.assertIn(f'href="{reverse("result", args=[latest.id])}"', main)

    def test_life_impact_result_has_a_gauge_with_the_needle_at_its_score(self):
        # Welcome back option D: 12 of 40 is 30% of the half circle, 54 degrees from 0.
        self._hhie_s(days_ago=30)
        main = self._main()
        gauge = re.search(r'<svg class="score-gauge".*?</svg>', main, re.S).group(0)
        self.assertIn('aria-hidden="true"', gauge)
        self.assertIn("--angle: 54.00deg", gauge)
        self.assertEqual(
            re.findall(r"score-gauge-arc-(\w+)", gauge), ["normal", "mild_to_moderate", "severe"]
        )
        # The arcs run from 0 on the left to the top score on the right, and meet at the
        # thresholds (8 and 24 points), a small gap either side.
        arcs = re.findall(r' d="([^"]+)"', gauge)
        self.assertTrue(arcs[0].startswith("M30.00 105.00"))
        self.assertTrue(arcs[-1].endswith("190.00 105.00"))

        def points(arc):
            x0, y0, *_, x1, y1 = map(float, re.findall(r"-?\d+\.?\d*", arc))
            return [
                (180 - math.degrees(math.atan2(105 - y, x - 110))) / 180 * 40
                for x, y in ((x0, y0), (x1, y1))
            ]

        ends = [points(arc) for arc in arcs]
        for (_, left), (right, _), threshold in zip(ends[:-1], ends[1:], (8, 24), strict=True):
            self.assertAlmostEqual((left + right) / 2, threshold, places=2)
            self.assertLess(left, right)
        self.assertRegex(gauge, r">\s*0\s*</text>")
        self.assertRegex(gauge, r">\s*40\s*</text>")

    def test_records_without_levels_have_no_gauge(self):
        # The owner's pick: the blue greeting stays, the grey box draws no gauge.
        self._submit("ioi-ha", [3] * 7, days_ago=1, norm_group="ungrouped")
        main = self._main()
        self.assertIn("上次是 2026/10/21 做的", main)
        self.assertNotIn("score-gauge", main)
        # The grey box, with 看這次結果 inside it.
        self.assertRegex(
            main,
            r'(?s)<div class="result-banner result-banner-unknown">'
            r"(?:(?!welcome-reminder|welcome-actions).)*?"
            r'class="welcome-result-link"',
        )

    def test_only_ioi_ha_shows_its_norm_summary_without_a_reminder(self):
        # Acceptance 3. Mild to moderate norms: items 1 and 2 below, item 5 above.
        self._submit("ioi-ha", [1, 1, 3, 3, 5, 3, 3], days_ago=1, norm_group="mild_moderate")
        main = self._main()
        self.assertIn('<h2 class="result-level mb-0">助聽器使用成效（IOI-HA）</h2>', main)
        self.assertIn("<div>7 項中 2 項低於常模、1 項高於常模</div>", main)
        self.assertNotIn("滿 6 個月", main)
        self.assertNotIn("下次建議", main)
        self.assertNotIn("再做一次", main)

    def test_ungrouped_ioi_ha_says_it_cannot_be_compared(self):
        self._submit("ioi-ha", [3] * 7, days_ago=1, norm_group="ungrouped")
        self.assertIn("<div>未分組，無法和常模比較</div>", self._main())

    def test_only_ssq12_shows_its_average(self):
        self._submit("ssq12-tw", [6] * 12, days_ago=1)
        main = self._main()
        self.assertIn('<h2 class="result-level mb-0">日常聆聽能力（SSQ12-TW）</h2>', main)
        self.assertIn("<div>整體平均：6.0／10</div>", main)
        self.assertNotIn("再做一次", main)

    def test_hhia_s_retake_stays_hhia_s_past_65(self):
        # Acceptance 6. Born 1950: over 65 on the fixed "today".
        older = consented_user(username="past_65", birth_year=1950)
        self._submit("hhia-s", [0] * 10, days_ago=1, user=older)
        self.client.force_login(older)
        main = self._main()
        self.assertIn(
            f'<a class="{self.SECONDARY}" href="{self._retake_url(self.hhia_s)}">再做一次</a>', main
        )
        self.assertNotIn(self._retake_url(self.hhie_s), main)

    def test_signed_in_home_is_never_cached(self):
        response = self.client.get(reverse("index"))
        self.assertIn("no-store", response["Cache-Control"])

    def test_only_the_logged_in_user_s_records_are_shown(self):
        other = consented_user(username="someone_else")
        theirs = self._hhie_s(days_ago=1, user=other)
        main = self._main()
        self.assertNotIn(reverse("result", args=[theirs.id]), main)
        self.assertIn("開始篩檢", main)  # this user has no records: still the new-user home

    def _count_queries(self):
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(reverse("index")).status_code, 200)
        return len(queries)

    def test_queries_do_not_grow_with_records(self):
        # CODING_STANDARDS 15, for both kinds of last result card.
        for card, add in (
            ("life impact", lambda days: self._hhie_s(days_ago=days)),
            (
                "IOI-HA",
                lambda days: self._submit(
                    "ioi-ha", [3] * 7, days_ago=days, norm_group="mild_moderate"
                ),
            ),
        ):
            with self.subTest(card=card):
                Answer.objects.all().delete()
                Submission.objects.all().delete()
                add(1)
                add(2)
                two = self._count_queries()
                for days in range(3, 8):
                    add(days)
                if card == "life impact":
                    self._submit("ioi-ha", [3] * 7, days_ago=9, norm_group="mild_moderate")
                    self._submit("ssq12-tw", [6] * 12, days_ago=10)
                self.assertEqual(self._count_queries(), two)

    # Ticket #160: "您還可以" on the returning-user home.
    def _more_section(self, main):
        found = re.search(
            r'<section[^>]*aria-labelledby="more-title".*?</section>', main, re.DOTALL
        )
        self.assertIsNotNone(found, "no 您還可以 section")
        return found.group(0)

    def test_more_you_can_do_links_five_cards_to_their_pages(self):
        # Acceptance 1; #193 moved sharing to its own page; #228 added the hearing-aid guide.
        # #261: without an audiogram the first is the 建議您下一步, the other four cards follow.
        self._hhie_s(days_ago=30)
        section = self._more_section(self._main())
        self.assertIn('<h2 id="more-title" class="h4">您還可以</h2>', section)
        self.assertRegex(
            section,
            r'(?s)<h3 class="next-step-title">記錄醫院的聽力圖</h3>.*?'
            r'<a class="btn btn-primary btn-lg w-full" href="/audiograms/new">去記錄</a>',
        )
        cards = re.findall(
            r'<a class="link-card action-card" href="([^"]*)">.*?'
            r'<span class="link-card-title">([^<]*)</span>',
            section,
            re.DOTALL,
        )
        self.assertEqual(
            cards,
            [
                ("/report", "印聽力報告給醫師看"),
                ("/share", "分享報告給家人"),
                ("/guide", "了解助聽器選配與補助"),
                ("/add_to_home", "加到手機主畫面"),
            ],
        )

    def test_more_you_can_do_shows_all_cards_without_javascript(self):
        # Acceptance 3: only the script hides "加到手機主畫面", so the page itself hides nothing.
        # #261: the mark is on its whole group (test_home_next_step).
        self._hhie_s(days_ago=30)
        section = self._more_section(self._main())
        self.assertEqual(section.count('class="link-card action-card"'), 4)
        self.assertNotRegex(section, r"\shidden[\s=>]")  # the HTML attribute, not aria-hidden
        items = re.findall(r"<li([^>]*)>", section)
        self.assertEqual(items, ["", "", "", ""])

    def test_new_user_home_has_no_more_you_can_do(self):
        # Acceptance 4: no records (and an anonymous visitor) see the new-user home only.
        main = self._main()
        self.assertIn("開始篩檢", main)
        self.assertNotIn("您還可以", main)
        self.client.logout()
        self.assertNotIn("您還可以", self._main())
