import re
from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.audiogram import DEGREE_LEVELS, degree_level
from screening.models import (
    Audiogram,
    Category,
    Question,
    Questionnaire,
    ReportShare,
    Submission,
)
from screening.scoring import classify
from screening.tests import test_report
from screening.tests.helpers import consented_user

LINK_CARD = re.compile(r'<a\b[^>]*class="[^"]*\blink-card\b[^"]*"[^>]*>.*?</a>', re.S)
BADGE = re.compile(r'<span class="level-badge level-badge-([a-z_]+)">([^<]*)</span>')
ARROW = '<span class="link-card-arrow" aria-hidden="true">\u203a</span>'  # the arrow sign


def _main(content):
    """The page without its footer."""
    return content.split('<footer class="site-footer"', 1)[0]


def _footer(content):
    parts = content.split('<footer class="site-footer"', 1)
    return parts[1] if len(parts) == 2 else ""


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _cards(content):
    return LINK_CARD.findall(_main(content))


class LayoutTests(TestCase):
    """Spec docs/specs/phase-09/phase9_ui_refresh_1_shared.md.

    Acceptance 3-10 (1, 2, 11 are e2e)."""

    _hhie_s = test_report.HealthReportTests._hhie_s
    _ioi_ha = test_report.HealthReportTests._ioi_ha
    _audiogram = test_report.HealthReportTests._audiogram

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhie_questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhie_s,
                question_text=f"假 HHIE 題{i}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        cls.ioi_questions = Question.objects.bulk_create(
            Question(questionnaire=cls.ioi_ha, question_text=f"假 IOI 題{i}", question_number=i)
            for i in range(1, 8)
        )

    def setUp(self):
        self.user = consented_user(username="layout_a", birth_year=1955)
        self.client.force_login(self.user)

    def _get(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        return response.content.decode()

    def _hearing_audiograms(self):
        # Right 65 dB HL 中重度, left 15 dB HL 正常; the older one has no points at all.
        full = self._audiogram(
            self.user, date(2026, 9, 28), right_air=(60, 65, 70, 65), left_air=(10, 15, 20, 15)
        )
        empty = Audiogram.objects.create(user=self.user, tested_on=date(2026, 1, 5))
        return full, empty

    # 3
    def test_footer_on_every_page(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        self.client.post(reverse("report_share_create"), {"confirm": "1"})
        share = ReportShare.objects.get()
        signed_in = [reverse("index"), reverse("my_hearing"), reverse("audiogram_list")]
        signed_out = [
            reverse("index"),
            reverse("login"),
            reverse("register"),
            reverse("privacy"),
            reverse("family_guide"),
            reverse("shared_cover", args=[share.token]),
            reverse("shared_report", args=[share.token]),
        ]
        pages = [(url, True) for url in signed_in] + [(url, False) for url in signed_out]
        pages.append((reverse("shared_cover", args=["x" * 43]), False))
        for url, logged_in in pages:
            if not logged_in:
                self.client.logout()
            with self.subTest(url=url, logged_in=logged_in):
                content = self.client.get(url).content.decode()
                footer = _footer(content)
                for name in ("family_guide", "add_to_home", "privacy"):
                    self.assertIn(f'href="{reverse(name)}"', footer)
                self.assertIn("結果僅供參考，不能取代聽力檢查與醫師診斷。", footer)
                self.assertIn('href="mailto:hearwellweb@gmail.com"', footer)
                self.assertIn("hearwellweb@gmail.com", _text(footer))

    # 4
    def test_my_hearing_family_link_only_in_footer(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        content = self._get(reverse("my_hearing"))
        self.assertNotIn(f'href="{reverse("family_guide")}"', _main(content))
        self.assertIn(f'href="{reverse("family_guide")}"', _footer(content))

    # 5 (changed by the owner after review: the footer made these two links repeat)
    def test_home_links_moved_to_footer_disclaimer_stays(self):
        content = self._get(reverse("index"))
        for name in ("family_guide", "add_to_home"):
            with self.subTest(link=name):
                self.assertNotIn(f'href="{reverse(name)}"', _main(content))
                self.assertIn(f'href="{reverse(name)}"', _footer(content))
        self.assertIn("由聽力師開發", _main(content))  # trust block, phase9_ui_refresh_4a_home.md

    # 6
    def test_record_cards_have_level_badges(self):
        records = {
            "normal": self._hhie_s(self.user, [0] * 10, wearing=False, days_ago=3),
            "mild_to_moderate": self._hhie_s(
                self.user, test_report.AIDED, wearing=True, days_ago=2
            ),
            "severe": self._hhie_s(self.user, test_report.UNAIDED, wearing=False, days_ago=1),
        }
        cards = _cards(self._get(reverse("my_hearing")))
        self.assertEqual(len(cards), 3)
        for level, submission in records.items():
            with self.subTest(level=level):
                card = next(c for c in cards if reverse("result", args=[submission.pk]) in c)
                text = classify(submission.total_answer_score, "hhie-s")["text"]
                self.assertEqual(BADGE.findall(card), [(level, text)])

        ioi = self._ioi_ha(self.user, basis=records["severe"])
        cards = _cards(self._get(f"{reverse('my_hearing')}?questionnaire=ioi-ha"))
        card = next(c for c in cards if reverse("result", args=[ioi.pk]) in c)
        self.assertEqual(BADGE.findall(card), [])
        self.assertIn("常模組別", card)

    # 7
    def test_audiogram_degree_badges(self):
        full, empty = self._hearing_audiograms()
        cards = _cards(self._get(reverse("audiogram_list")))
        full_card = next(c for c in cards if reverse("audiogram_detail", args=[full.pk]) in c)
        empty_card = next(c for c in cards if reverse("audiogram_detail", args=[empty.pk]) in c)
        self.assertEqual(BADGE.findall(full_card), [("severe", "中重度"), ("normal", "正常")])
        self.assertEqual(BADGE.findall(empty_card), [("unknown", "資料不足")] * 2)

        detail = _main(self._get(reverse("audiogram_detail", args=[full.pk])))
        self.assertEqual(BADGE.findall(detail), [("severe", "中重度"), ("normal", "正常")])
        detail = _main(self._get(reverse("audiogram_detail", args=[empty.pk])))
        self.assertEqual(BADGE.findall(detail), [("unknown", "資料不足")] * 2)

    # 7: the clinical mapping itself (spec 4.4, the owner's decision Q4 A)
    def test_degree_to_level_mapping(self):
        expected = {
            "正常": "normal",
            "輕度": "mild_to_moderate",
            "中度": "mild_to_moderate",
            "中重度": "severe",
            "重度": "severe",
            "極重度": "severe",
        }
        self.assertEqual(DEGREE_LEVELS, expected)
        for name, level in expected.items():
            self.assertEqual(degree_level(name), level)
        self.assertEqual(degree_level(None), "unknown")

    # 8
    def test_clickable_cards_are_single_links(self):
        made = self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        submission = Submission.objects.get(pk=made.pk)  # created_at was moved after creating
        full, _ = self._hearing_audiograms()
        cases = {
            reverse("questionnaire_list"): (
                reverse("screening", args=[self.hhie_s.pk]),
                ["HHIE-S", "聽力對生活的影響"],
            ),
            reverse("my_hearing"): (
                reverse("result", args=[submission.pk]),
                [
                    f"{timezone.localtime(submission.created_at):%Y/%m/%d}",
                    "總分：20",
                    "有戴",
                    "輕度到中度影響",
                ],
            ),
            reverse("audiogram_list"): (
                reverse("audiogram_detail", args=[full.pk]),
                ["2026/09/28", "右耳", "中重度", "左耳", "正常"],
            ),
        }
        for page, (href, texts) in cases.items():
            with self.subTest(page=page):
                content = self._get(page)
                card = next(c for c in _cards(content) if f'href="{href}"' in c)
                # One link: no link or button nested inside the card.
                self.assertEqual(card.count("<a"), 1)
                self.assertNotIn("<button", card)
                self.assertIn(ARROW, card)
                for text in texts:
                    self.assertIn(text, _text(card))
                self.assertNotIn("查看結果", _main(content))
                self.assertNotIn("stretched-link", content)

    # 9
    def test_my_hearing_has_no_solid_button(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        main = _main(self._get(reverse("my_hearing")))
        self.assertNotIn("btn-primary", main)
        self.assertRegex(
            main, rf'class="btn btn-outline-primary[^"]*" href="{reverse("health_report")}"'
        )

    # 10
    def test_report_page_one_solid_button_until_confirm(self):
        self._hhie_s(self.user, test_report.AIDED, wearing=True, days_ago=1)
        main = _main(self._get(reverse("health_report")))
        before, rest = main.split("<details>", 1)
        inside, after = rest.split("</details>", 1)
        solid = re.compile(r'class="btn btn-primary[^"]*"[^>]*>([^<]*)<')
        # Seen without opening anything: only the print button is solid.
        self.assertEqual(solid.findall(before + after), ["列印或存成 PDF"])
        self.assertRegex(
            inside, r'<summary class="btn btn-outline-primary[^"]*">產生分享連結</summary>'
        )
        self.assertRegex(inside, r'class="btn btn-primary[^"]*" type="submit" name="confirm"')
