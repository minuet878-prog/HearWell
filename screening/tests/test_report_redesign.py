"""#471 (mockup #470 groups 1-3): the report, the share page and the family's copy restyled.

The owner picked report B (each fold row says its summary line), share A (N3 steps) and, on the
family's copy, the print button after the highlights (D5). The printed report stays as it was:
e2e.main_flow checks paper in a real browser.
"""

import re
from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import AidAndSubsidy, ReportShare, Submission
from screening.tests import test_report

TAG = re.compile(r"<[^>]+>")
FOLD_ROW = re.compile(r'<details class="report-fold">\s*<summary>(.*?)</summary>', re.S)


def _text(html):
    """A row's words, its title and the line under it parted by a space."""
    html = re.sub(r'</h2>|</span>(?=<span class="report-info-value">)', " ", html)
    return re.sub(r"\s+", " ", TAG.sub("", html)).strip()


def _main(content):
    return content[content.index("<main") : content.index("</main>")]


class ReportRowsTests(TestCase):
    _hhie_s = test_report.HealthReportTests._hhie_s
    _ioi_ha = test_report.HealthReportTests._ioi_ha
    _audiogram = test_report.HealthReportTests._audiogram
    _full_records = test_report.HealthReportTests._full_records
    setUpTestData = classmethod(test_report.HealthReportTests.setUpTestData.__func__)
    setUp = test_report.HealthReportTests.setUp

    def _content(self):
        response = self.client.get(reverse("health_report"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_each_fold_row_says_its_summary_line(self):
        _, aided = self._full_records()
        aided = Submission.objects.get(pk=aided.pk)
        ioi_ha = Submission.objects.get(questionnaire=self.ioi_ha)
        rows = [_text(row) for row in FOLD_ROW.findall(self._content())]

        self.assertEqual(
            rows,
            [
                "聽力圖（2026/09/28） 右耳 45 dB HL 中度、感音神經性；左耳 35 dB HL 輕度",
                f"HHIE-S（{timezone.localtime(aided.created_at):%Y/%m/%d}） "
                "20 分，輕度到中度影響，助聽器：有戴",
                f"IOI-HA（{timezone.localtime(ioi_ha.created_at):%Y/%m/%d}） "
                "7 項中 1 項低於常模、1 項高於常模",
            ],
        )

    def test_a_row_writes_its_level_as_a_level_badge(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        content = self._content()
        row = FOLD_ROW.search(content).group(1)

        self.assertIn(
            '<span class="level-badge level-badge-mild_to_moderate">輕度到中度影響</span>', row
        )
        self.assertNotIn("report-level", content)

    def test_the_print_button_is_the_one_solid_button_under_the_details(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        main = _main(self._content())

        self.assertEqual(main.count("btn-primary"), 1)
        button = main.index('id="print-button"')
        self.assertLess(main.index("產生日期："), button)
        self.assertLess(button, main.index('<details class="report-fold">'))

    def test_sharing_and_records_are_list_rows_after_the_folds(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        main = _main(self._content())
        rows = main[main.rindex("</details>") : main.index("report-disclaimer")]

        self.assertEqual(
            re.findall(
                r'<a class="link-card action-card" href="([^"]+)".*?title">([^<]+)<', rows, re.S
            ),
            [(reverse("share_report"), "分享報告給家人"), (reverse("my_hearing"), "回我的紀錄")],
        )
        self.assertIn('id="report-share"', rows)
        self.assertNotIn("btn-outline-primary", main)

    def test_hearing_aids_and_a_kept_comparison_are_information_rows(self):
        self._full_records()
        AidAndSubsidy.objects.create(
            user=self.user, certificate="yes", fitted_on=date(2026, 5, 1), ear="both"
        )
        main = _main(self._content())
        infos = [
            _text(info)
            for info in re.findall(r'<div class="report-info no-print">(.*?)</div>', main, re.S)
        ]

        self.assertEqual(
            infos,
            [
                "助聽器 雙耳，2026/05/01 開始戴",
                "報告保留比較（HHIE-S） 沒戴 26 分、有戴 20 分，少了 6 分",
            ],
        )
        manage = re.search(r"<a([^>]*)>更換或移除 HHIE-S 比較</a>", main)
        self.assertNotIn("btn", manage.group(1))


class SharedReportOrderTests(TestCase):
    _hhie_s = test_report.HealthReportTests._hhie_s
    _audiogram = test_report.HealthReportTests._audiogram
    setUpTestData = classmethod(test_report.HealthReportTests.setUpTestData.__func__)

    def setUp(self):
        user = test_report.consented_user(username="shared_order", birth_year=1956)
        self._hhie_s(user, test_report.UNAIDED, wearing=False, days_ago=1)
        self._audiogram(user, date(2026, 9, 28), (40, 45, 50, 45), (30, 35, 40, 35))
        self.share = ReportShare.objects.create(user=user)
        self.answered_on = timezone.localtime(user.submissions.get().created_at)

    def _main(self):
        response = self.client.get(reverse("shared_report", args=[self.share.token]))
        return _main(response.content.decode())

    def test_the_print_button_follows_the_highlights_and_the_help(self):
        main = self._main()
        order = [
            main.index("這是您的家人在聽伴自己作答與輸入的自我篩檢結果。"),
            main.index("聽伴聽力報告</h1>"),
            main.index("先看重點</h2>"),
            main.index("您可以怎麼幫忙</h2>"),
            main.index('id="print-button"'),
            main.index("年齡："),
            main.index('<details class="report-fold">'),
        ]

        self.assertEqual(order, sorted(order))
        self.assertEqual(main.count("btn-primary"), 1)

    def test_the_life_impact_highlight_is_a_block_in_its_level_colour(self):
        highlights = re.search(r'<section id="family-highlights".*?</section>', self._main(), re.S)

        self.assertInHTML(
            '<div class="family-level result-banner-severe">'
            '<span class="family-level-label">聽力對生活的影響</span>'
            '<span class="family-level-name">顯著影響</span>'
            f"<span>{self.answered_on:%Y/%m/%d} 作答</span></div>",
            highlights.group(0),
        )

    def test_the_help_links_are_list_rows_with_icons(self):
        help_links = re.search(r'<section id="family-help".*?</section>', self._main(), re.S)

        self.assertEqual(help_links.group(0).count('class="link-card action-card"'), 3)
        self.assertEqual(help_links.group(0).count('class="action-card-icon"'), 3)


class ShareInvalidTests(TestCase):
    def test_back_home_is_the_solid_button(self):
        response = self.client.get(reverse("shared_cover", args=["no-such-token"]))

        self.assertContains(
            response,
            f'<a class="btn btn-primary btn-lg w-full" href="{reverse("index")}">回首頁</a>',
            html=True,
            status_code=404,
        )


class ShareStepsTests(TestCase):
    """Share A: the three steps as N3 numbers on a line (the care journey's look)."""

    _hhie_s = test_report.HealthReportTests._hhie_s
    setUpTestData = classmethod(test_report.HealthReportTests.setUpTestData.__func__)

    def setUp(self):
        self.user = test_report.consented_user(username="share_steps")
        self.client.force_login(self.user)
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)

    def _main(self):
        return _main(self.client.get(reverse("share_report")).content.decode())

    def _steps(self, main):
        steps = re.search(r'<ol class="step-list share-steps[^"]*".*?</ol>', main, re.S).group(0)
        return re.split(r"<li class=\"share-step\"", steps)[1:]

    def test_before_sharing_the_third_step_waits_in_grey(self):
        main = self._main()
        one, two, three = self._steps(main)

        self.assertIn("家人會看到什麼</h2>", one)
        self.assertNotIn("<details", one)
        self.assertIn("我知道了，產生連結</button>", two)
        self.assertIn('<span class="step-list-number is-later" aria-hidden="true">3</span>', three)
        self.assertIn("產生連結後才能傳。", three)
        self.assertEqual(main.count("btn-primary"), 1)

    def test_the_latest_report_notice_moves_under_the_steps(self):
        for shared in (False, True):
            if shared:
                ReportShare.objects.create(user=self.user)
            with self.subTest(shared=shared):
                main = self._main()
                self.assertIn(
                    "連結有效期間，家人看到的是您最新的報告，之後新增的紀錄也會看到。",
                    main[main.index("</ol>") :],
                )

    def test_while_shared_what_the_family_sees_folds_and_sending_is_the_solid_button(self):
        share = ReportShare.objects.create(user=self.user)
        main = self._main()
        one, two, three = self._steps(main)

        fold = re.search(r"<details.*?</details>", one, re.S).group(0)
        self.assertIn("家人會看到什麼</h2></summary>", fold)
        self.assertIn("<li>聽力圖</li>", fold)
        self.assertIn("有效到", two)
        self.assertEqual(main.count("btn-primary"), 1)
        self.assertRegex(three, r'class="btn btn-primary btn-lg w-full"[^>]*hidden>再傳一次給家人<')
        self.assertRegex(
            three, r'class="btn btn-outline-primary btn-lg w-full"[^>]*hidden>複製連結<'
        )
        cancel = re.search(
            rf'action="{reverse("report_share_cancel", args=[share.pk])}">(.*?)</form>', three, re.S
        )
        self.assertIn(
            '<button class="danger-link" type="submit">取消分享</button>', cancel.group(1)
        )
