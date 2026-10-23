import json
import re
from datetime import date, timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import (
    AidAndSubsidy,
    Answer,
    Audiogram,
    AudiogramPoint,
    Category,
    NormGroup,
    Question,
    Questionnaire,
    ReportShare,
    Submission,
    User,
)
from screening.questionnaires.ioi_ha import ITEM_CHOICES as IOI_HA_CHOICES
from screening.scoring import IOI_HA_BELOW_NORM_NOTES
from screening.tests.helpers import action_cards, consented_user

# Unaided 4x5 + 2x3 + 0x2 = 26 (顯著影響, emotional 20, social 6); aided all 2 = 20.
UNAIDED = [4, 4, 4, 4, 4, 2, 2, 2, 0, 0]
AIDED = [2] * 10
# Against mild_moderate norms: item 2 below, item 7 above, the rest within.
IOI_SCORES = [5, 2, 3, 4, 3, 5, 5]
SECTION_ORDER = ["report-audiogram", "report-hhie-s", "report-difference", "report-ioi-ha"]


def _section(content, section_id):
    match = re.search(rf'<section[^>]*id="{section_id}".*?</section>', content, re.S)
    return match.group(0) if match else ""


class HealthReportTests(TestCase):
    """Spec docs/specs/phase-08/phase8_c3_report.md, acceptance 1-16."""

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
        self.url = reverse("health_report")
        self.user = consented_user(username="report_a", email="a@example.com", birth_year=1955)
        self.other = consented_user(username="report_b", email="b@example.com")
        self.client.force_login(self.user)

    def _hhie_s(self, user, scores, wearing, days_ago):
        submission = Submission.objects.create(
            user=user, questionnaire=self.hhie_s, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=q, score=s)
            for q, s in zip(self.hhie_questions, scores, strict=True)
        )
        Submission.objects.filter(pk=submission.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        return submission

    def _ioi_ha(self, user, basis, days_ago=1):
        submission = Submission.objects.create(
            user=user,
            questionnaire=self.ioi_ha,
            norm_group=NormGroup.MILD_MODERATE if basis else NormGroup.UNGROUPED,
            norm_basis=basis,
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=q, score=s)
            for q, s in zip(self.ioi_questions, IOI_SCORES, strict=True)
        )
        Submission.objects.filter(pk=submission.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        return submission

    def _audiogram(self, user, tested_on, right_air, left_air, right_bone=None):
        audiogram = Audiogram.objects.create(user=user, tested_on=tested_on)
        points = []
        for ear, conduction, values in (
            ("right", "air", right_air),
            ("left", "air", left_air),
            ("right", "bone", right_bone),
        ):
            for frequency, db in zip((500, 1000, 2000, 4000), values or (), strict=False):
                points.append(
                    AudiogramPoint(
                        audiogram=audiogram,
                        ear=ear,
                        conduction=conduction,
                        frequency=frequency,
                        db=db,
                    )
                )
        AudiogramPoint.objects.bulk_create(points)
        return audiogram

    def _full_records(self):
        unaided = self._hhie_s(self.user, UNAIDED, wearing=False, days_ago=30)
        aided = self._hhie_s(self.user, AIDED, wearing=True, days_ago=2)
        self.client.post(
            f"/comparisons/{self.hhie_s.pk}",
            {"unaided": unaided.pk, "aided": aided.pk, "action": "save"},
        )
        self._ioi_ha(self.user, basis=unaided)
        # Right 45 dB HL 中度 感音神經性 (bone 40); left 35 dB HL 輕度, no bone.
        self._audiogram(
            self.user,
            date(2026, 9, 28),
            right_air=(40, 45, 50, 45),
            left_air=(30, 35, 40, 35),
            right_bone=(35, 40, 45, 40),
        )
        return unaided, aided

    def _content(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    # 1
    def test_shows_every_part_consistent_with_the_site(self):
        _, aided = self._full_records()
        content = self._content()
        # ① header
        self.assertIn("report_a", content)
        self.assertIn(f"1955（{date.today().year - 1955} 歲）", content)
        self.assertIn("姓名：", content)
        # ② HHIE-S latest, from the same scoring path as the result page
        hhie = _section(content, "report-hhie-s")
        aided = Submission.objects.get(pk=aided.pk)
        self.assertIn(f"{aided.total_answer_score} 分", hhie)
        self.assertIn(aided.classified["text"], hhie)
        self.assertIn(f"情緒 {aided.emotional_score}", hhie)
        self.assertIn(f"社交 {aided.social_score}", hhie)
        self.assertIn("有戴", hhie)
        # ③ difference, same as my records
        self.assertIn("少了 6 分", _section(content, "report-difference"))
        # ④ IOI-HA, same comparison as its result page
        ioi = _section(content, "report-ioi-ha")
        self.assertIn("輕度至中度", ioi)
        self.assertInHTML(
            f"<tr><td>幫助程度</td><td>{IOI_HA_CHOICES[2][1]}</td><td>低於常模</td></tr>", ioi
        )
        self.assertInHTML(
            f"<tr><td>生活樂趣</td><td>{IOI_HA_CHOICES[7][4]}</td><td>高於常模</td></tr>", ioi
        )
        result_page = self.client.get(
            reverse("result", args=[Submission.objects.get(questionnaire=self.ioi_ha).pk])
        )
        # The result page says the same comparison in its own words (#187).
        self.assertContains(result_page, "比一般使用者低的 1 項")
        self.assertContains(result_page, f"您的回答：{IOI_HA_CHOICES[2][1]}")
        # ⑤ audiogram interpretation, same as the audiogram page
        audiogram = _section(content, "report-audiogram")
        self.assertIn("2026/09/28", audiogram)
        self.assertIn("45 dB HL", audiogram)
        self.assertIn("中度", audiogram)
        self.assertIn("感音神經性", audiogram)
        self.assertIn("35 dB HL", audiogram)
        self.assertIn("輕度", audiogram)

    # phase9_ui_refresh_4d_ioi_ha_items.md acceptance 6a: notes stay on the result page
    def test_ioi_ha_notes_not_in_report(self):
        self._full_records()  # item 2 is below the norm
        ioi = _section(self._content(), "report-ioi-ha")
        self.assertIn("低於常模", ioi)
        self.assertNotIn(IOI_HA_BELOW_NORM_NOTES[2], ioi)

    # 2
    def test_shows_nothing_of_other_users(self):
        self._hhie_s(self.user, AIDED, wearing=True, days_ago=1)
        basis = self._hhie_s(self.other, UNAIDED, wearing=False, days_ago=1)
        self._ioi_ha(self.other, basis=basis)
        self._audiogram(self.other, date(2025, 1, 2), right_air=(90, 90, 90, 90), left_air=())
        content = self._content()
        self.assertNotIn("report_b", content)
        self.assertNotIn('id="report-ioi-ha"', content)
        # 4.1: no account data besides the user name, not even one's own email.
        self.assertNotIn("a@example.com", content)
        self.assertNotIn("b@example.com", content)
        self.assertNotIn("2025/01/02", content)
        self.assertNotIn("顯著影響", content)
        self.assertNotIn('id="report-audiogram"', content)

    # 3
    def test_signed_out_goes_to_login_and_back(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )

    # 4
    def test_without_consent_goes_to_consent_page(self):
        user = User.objects.create_user(username="report_old")
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertTrue(response.url.startswith(reverse("consent")))

    # 5
    def test_no_records_shows_empty_message_without_print_button(self):
        content = self._content()
        self.assertIn("還沒有可以放進報告的紀錄", content)
        self.assertIn(f'href="{reverse("questionnaire_list")}"', content)
        self.assertNotIn('id="print-button"', content)
        self.assertNotIn('id="report-summary"', content)

    # 6
    def test_zero_score_is_shown_as_zero(self):
        self._hhie_s(self.user, [0] * 10, wearing=False, days_ago=1)
        hhie = _section(self._content(), "report-hhie-s")
        self.assertIn("0 分", hhie)
        self.assertIn("無/極輕微影響", hhie)

    # 7
    def test_has_date_and_disclaimer(self):
        self._hhie_s(self.user, AIDED, wearing=True, days_ago=1)
        content = self._content()
        self.assertIn(f"產生日期：{timezone.localdate():%Y/%m/%d}", content)
        self.assertIn("自我篩檢結果，不是醫療診斷", content)

    # 8 (the print view itself is checked in a real browser by e2e.main_flow)
    def test_print_button_and_print_styles(self):
        self._hhie_s(self.user, AIDED, wearing=True, days_ago=1)
        content = self._content()
        self.assertIn('id="print-button"', content)
        self.assertIn("screening/print-button.js", content)
        # The level is written out in a bordered label, not shown by colour alone.
        self.assertIn(
            '<span class="report-level report-level-mild_to_moderate">輕度到中度影響</span>',
            content,
        )

    # 9
    def test_query_count_does_not_grow_with_records(self):
        self._full_records()
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for i in range(18):
            self._hhie_s(self.user, AIDED, wearing=True, days_ago=40 + i)
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(many), len(few))

    # 10
    def test_history_page_links_to_report(self):
        # The report and sharing it, as two action cards under 「要給醫師或家人看？」.
        content = self.client.get(reverse("my_hearing")).content.decode()
        section = content[content.index('aria-labelledby="for-doctor-title"') :]
        self.assertEqual(
            action_cards(section),
            [
                (self.url, "看／印聽力報告", "可以印出來或存成 PDF"),
                (reverse("share_report"), "傳給家人看", "家人不用登入就能看"),
            ],
        )

    # 11
    def test_history_table_lists_latest_five(self):
        for days_ago in range(1, 8):
            self._hhie_s(self.user, AIDED, wearing=True, days_ago=days_ago)
        hhie = _section(self._content(), "report-hhie-s")
        self.assertIn("共 7 次，列出最近 5 次", hhie)
        dates = re.findall(r"<td>(\d{4}/\d{2}/\d{2})</td>", hhie)
        expected = [
            f"{timezone.localtime(timezone.now() - timedelta(days=d)):%Y/%m/%d}"
            for d in range(1, 6)
        ]
        self.assertEqual(dates, expected)

    # 12
    def test_only_sections_with_records_appear(self):
        self._hhie_s(self.user, AIDED, wearing=True, days_ago=1)
        content = self._content()
        self.assertIn('id="report-hhie-s"', content)
        for section_id in ("report-ioi-ha", "report-audiogram", "report-difference"):
            with self.subTest(section_id=section_id):
                self.assertNotIn(f'id="{section_id}"', content)
        self.assertNotIn("audiogram-view.js", content)

    # 13
    def test_draws_latest_audiogram_and_works_without_js(self):
        self._audiogram(self.user, date(2025, 5, 1), right_air=(80, 80, 80, 80), left_air=())
        latest = self._audiogram(
            self.user, date(2026, 9, 28), right_air=(40, 45, 50, 45), left_air=(30, 35, 40, 35)
        )
        content = self._content()
        self.assertIn("screening/frontend/audiogram-view.js", content)
        data = re.search(
            r'<script id="audiogram-points" type="application/json">(.*?)</script>', content
        )
        points = json.loads(data.group(1))
        expected = {(p.ear, p.conduction, p.frequency, p.db) for p in latest.points.all()}
        drawn = {(p["ear"], p["conduction"], p["frequency"], p["db"]) for p in points}
        self.assertEqual(drawn, expected)
        # The interpretation is in the HTML itself, not drawn by JS.
        self.assertIn("45 dB HL", _section(content, "report-audiogram"))
        self.assertNotIn("2025/05/01", content)

    # 14
    def test_aided_difference_matches_history_page(self):
        self._full_records()
        # The difference is on the HHIE-S tab; the newest record here is IOI-HA.
        url = f"{reverse('my_hearing')}?questionnaire=hhie-s"
        history = self.client.get(url).content.decode()
        self.assertIn("少了 6 分", history)
        self.assertIn("少了 6 分", _section(self._content(), "report-difference"))

    # 15
    def test_summary_matches_details(self):
        self._full_records()
        content = self._content()
        summary = _section(content, "report-summary")
        self.assertIn("右耳 45 dB HL 中度", summary)
        self.assertIn("左耳 35 dB HL 輕度", summary)
        self.assertIn("20 分", summary)
        self.assertIn("輕度到中度影響", summary)
        # No arrow: the two records can be in either order in time (review 1).
        self.assertIn("沒戴 26 分、有戴 20 分，少了 6 分", summary)
        self.assertNotIn("→", summary)
        self.assertIn("7 項中 1 項低於常模、1 項高於常模", summary)
        ioi = _section(content, "report-ioi-ha")
        self.assertEqual(ioi.count("<td>低於常模</td>"), 1)
        self.assertEqual(ioi.count("<td>高於常模</td>"), 1)

    # 16
    def test_title_and_section_order(self):
        self._full_records()
        content = self._content()
        self.assertIn("<title>HearWell 聽力報告</title>", content)
        self.assertIn("HearWell 聽力報告</h1>", content)
        positions = [content.index(f'id="{section_id}"') for section_id in SECTION_ORDER]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(content.index('id="report-summary"'), positions[0])

    # Ungrouped IOI-HA (outside the numbered list): no comparison, as on its result page.
    def test_ungrouped_ioi_ha_has_no_comparison(self):
        self._ioi_ha(self.user, basis=None)
        content = self._content()
        self.assertIn("無法和常模比較", _section(content, "report-summary"))
        ioi = _section(content, "report-ioi-ha")
        self.assertIn("未分組", ioi)
        self.assertNotIn("低於常模", ioi)
        self.assertNotIn("高於常模", ioi)


class HearingAidReportLineTests(TestCase):
    """#287 (spec #284 acceptance 20): the owner's printed report says which hearing aids they
    wear; the family's copy, built from the same template, does not."""

    LINE = "助聽器：雙耳，2026/05/01 開始戴，中階型"

    def setUp(self):
        self.user = consented_user(username="report_wearer")
        self.client.force_login(self.user)
        HealthReportTests._audiogram(
            self, self.user, date(2026, 9, 28), (40, 45, 50, 45), (30, 35, 40, 35)
        )

    def fill(self, **fields):
        defaults = {"certificate": "yes", "fitted_on": date(2026, 5, 1), "ear": "both"}
        AidAndSubsidy.objects.create(user=self.user, **(defaults | fields))

    def summary(self):
        content = self.client.get(reverse("health_report")).content.decode()
        return re.sub(r"\s+", " ", _section(content, "report-summary"))

    def test_the_line_in_the_summary_without_the_certificate(self):
        self.fill(subsidy="disability", level="mid")
        summary = self.summary()
        self.assertIn(f"<li>{self.LINE}</li>", summary)
        content = self.client.get(reverse("health_report")).content.decode()
        self.assertNotIn("身障證明", content)

    def test_paying_otherwise_has_no_level(self):
        self.fill(subsidy="other")
        self.assertIn("<li>助聽器：雙耳，2026/05/01 開始戴</li>", self.summary())

    def test_a_level_not_known_is_left_out(self):
        self.fill(subsidy="disability", level="unknown")
        self.assertIn("<li>助聽器：雙耳，2026/05/01 開始戴</li>", self.summary())

    def test_no_line_without_the_ear_the_date_or_the_level(self):
        self.fill(fitted_on=None, ear="", subsidy="other")
        self.assertNotIn("開始戴", self.summary())
        self.assertNotIn("<li>助聽器：", self.summary())

    def test_the_shared_report_never_has_it(self):
        self.fill(subsidy="disability", level="mid")
        share = ReportShare.objects.create(user=self.user)
        self.client.logout()
        content = self.client.get(reverse("shared_report", args=[share.token])).content.decode()
        self.assertIn("report-summary", content)  # the shared template is the one tested
        self.assertNotIn("開始戴", content)
        self.assertNotIn("中階型", content)
        self.assertNotIn("身障證明", content)

    def test_query_count_is_the_same_with_and_without_it(self):
        with CaptureQueriesContext(connection) as without:
            self.client.get(reverse("health_report"))
        self.fill(subsidy="disability", level="mid")
        with CaptureQueriesContext(connection) as filled:
            self.client.get(reverse("health_report"))
        self.assertEqual(len(filled), len(without))
