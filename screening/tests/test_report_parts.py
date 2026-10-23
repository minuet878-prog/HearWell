"""Health report groups adult results into three parts (#90)."""

import re
from dataclasses import replace
from datetime import datetime
from html.parser import HTMLParser
from io import StringIO
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.test import TestCase

from screening.models import Answer, NormGroup, Question, Questionnaire, Submission
from screening.questionnaires import sadl
from screening.questionnaires.hhia_s import EXPLANATION as HHIA_S_EXPLANATION
from screening.tests import test_report
from screening.tests.helpers import consented_user, register

PARTS = {
    "report-life-impact": "生活影響",
    "report-listening": "日常聆聽能力",
    "report-satisfaction": "助聽器滿意度",
    "report-hearing-aid-outcome": "助聽器使用成效",
}


class _Outline(HTMLParser):
    """Records each section id and heading with the section ids around it."""

    def __init__(self):
        super().__init__()
        self.open_sections = []
        self.parents = {}  # section id -> enclosing section ids, outermost first
        self.headings = []  # (level, enclosing section ids)

    def handle_starttag(self, tag, attrs):
        if tag == "section":
            section_id = dict(attrs).get("id")
            self.parents[section_id] = tuple(self.open_sections)
            self.open_sections.append(section_id)
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append((int(tag[1]), tuple(self.open_sections)))

    def handle_endtag(self, tag):
        if tag == "section":
            self.open_sections.pop()


def _outline(response):
    outline = _Outline()
    outline.feed(response.content.decode())
    return outline


class _Folds(HTMLParser):
    """Each fold straight inside a part (a <details> not inside a questionnaire's section): its
    part, whether it starts open, its summary row's words and headings, and the sections in it."""

    def __init__(self):
        super().__init__()
        self.open_sections = []
        self.details_depth = 0
        self.in_summary = False
        self.folds = []

    def handle_starttag(self, tag, attrs):
        fold = self.folds[-1] if self.details_depth else None
        if tag == "details":
            if not self.details_depth and len(self.open_sections) == 1:
                self.folds.append(
                    {
                        "part": self.open_sections[0],
                        "open": "open" in dict(attrs),
                        "summary": "",
                        "headings": [],
                        "sections": [],
                    }
                )
            if self.details_depth or len(self.open_sections) == 1:
                self.details_depth += 1
        elif tag == "summary" and self.details_depth == 1:
            self.in_summary = True
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self.in_summary:
            fold["headings"].append(int(tag[1]))
        elif tag == "section":
            if fold:
                fold["sections"].append(dict(attrs).get("id"))
            self.open_sections.append(dict(attrs).get("id"))

    def handle_endtag(self, tag):
        if tag == "details" and self.details_depth:
            self.details_depth -= 1
        elif tag == "summary":
            self.in_summary = False
        elif tag == "section":
            self.open_sections.pop()

    def handle_data(self, data):
        if self.in_summary:
            self.folds[-1]["summary"] += data


def _folds(response):
    parser = _Folds()
    parser.feed(response.content.decode())
    for fold in parser.folds:
        fold["summary"] = re.sub(r"\s+", " ", fold["summary"]).strip()
    return parser.folds


class ReportPartsTests(TestCase):
    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.hhia = Questionnaire.objects.get(code="hhia-s")
        self.ssq = Questionnaire.objects.get(code="ssq12-tw")
        self.sadl = Questionnaire.objects.get(code="sadl")
        self.thi = Questionnaire.objects.get(code="thi")
        self.hhie = Questionnaire.objects.create(code="hhie-s", questionnaire_name="HHIE-S")
        Question.objects.bulk_create(
            Question(questionnaire=self.hhie, question_text=f"假 HHIE 題{n}", question_number=n)
            for n in range(1, 11)
        )
        self.ioi = Questionnaire.objects.create(code="ioi-ha", questionnaire_name="IOI-HA")
        Question.objects.bulk_create(
            Question(questionnaire=self.ioi, question_text=f"假 IOI 題{n}", question_number=n)
            for n in range(1, 8)
        )
        self.user = consented_user(username="report_parts")
        self.client.force_login(self.user)

    def record(self, questionnaire, wearing=None, score=2, **fields):
        record = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=wearing, **fields
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=q, score=score)
            for q in questionnaire.questions.all()
        )
        return record

    def on(self, record, day):
        """Moves record to noon on day October 2026 in Taipei, for a plain date to expect."""
        moment = datetime(2026, 10, day, 12, tzinfo=ZoneInfo("Asia/Taipei"))
        Submission.objects.filter(pk=record.pk).update(created_at=moment)
        return record

    def save_pair(self, questionnaire):
        unaided = self.record(questionnaire, wearing=False)
        aided = self.record(questionnaire, wearing=True)
        self.client.post(
            f"/comparisons/{questionnaire.pk}",
            {"unaided": unaided.pk, "aided": aided.pk, "action": "save"},
        )
        return unaided

    def family_report(self):
        self.client.post("/report/share", {"confirm": "1"})
        share = self.user.report_shares.get()
        self.client.logout()
        return self.client.get(f"/shared/{share.token}/report")

    def test_comparison_texts_on_owner_and_family_reports(self):
        # Issue #102: the moved comparison parts read as before, with a real difference.
        for questionnaire, unaided, aided in (
            (self.hhie, 4, 2),
            (self.hhia, 2, 0),
            (self.ssq, 4, 6),
        ):
            first = self.record(questionnaire, wearing=False, score=unaided)
            second = self.record(questionnaire, wearing=True, score=aided)
            self.client.post(
                f"/comparisons/{questionnaire.pk}",
                {"unaided": first.pk, "aided": second.pk, "action": "save"},
            )
        ssq_item = self.ssq.questions.get(question_number=1).question_text
        for response in (self.client.get("/report"), self.family_report()):
            content = response.content.decode()
            for section, sentence in (
                ("report-difference", "差值（配戴 \u2212 未配戴）：-20 分，少了 20 分。"),
                ("report-comparison-hhia-s", "差值（配戴 \u2212 未配戴）：-20 分，少了 20 分。"),
                ("report-comparison-ssq12-tw", "差值（配戴 \u2212 未配戴）：+2.0 分。"),
            ):
                with self.subTest(section=section):
                    self.assertIn(sentence, test_report._section(content, section))
            self.assertIn(
                f"{ssq_item}<br>未配戴：<strong>4</strong>；配戴：<strong>6</strong>",
                test_report._section(content, "report-comparison-ssq12-tw"),
            )

    def test_each_result_and_its_comparison_sit_in_their_part(self):
        basis = self.save_pair(self.hhie)
        self.save_pair(self.hhia)
        self.save_pair(self.ssq)
        self.record(self.ioi, score=3, norm_group=NormGroup.MILD_MODERATE, norm_basis=basis)
        with register(replace(sadl.DEFINITION, listed=True)):
            self.record(self.sadl)
            owner = self.client.get("/report")
            for response in (owner, self.family_report()):
                outline = _outline(response)
                for part in PARTS:
                    self.assertEqual(outline.parents[part], ())
                expected = {
                    "report-hhie-s": "report-life-impact",
                    "report-difference": "report-life-impact",
                    "report-hhia-s": "report-life-impact",
                    "report-comparison-hhia-s": "report-life-impact",
                    "report-ssq12": "report-listening",
                    "report-comparison-ssq12-tw": "report-listening",
                    "report-sadl": "report-satisfaction",
                    "report-ioi-ha": "report-hearing-aid-outcome",
                }
                for section_id, part in expected.items():
                    self.assertEqual(outline.parents[section_id], (part,), section_id)
                # Each comparison follows its own questionnaire, not the other HHI.
                life = [
                    s
                    for s, parents in outline.parents.items()
                    if parents == ("report-life-impact",)
                ]
                for questionnaire, comparison in (
                    ("report-hhie-s", "report-difference"),
                    ("report-hhia-s", "report-comparison-hhia-s"),
                ):
                    self.assertEqual(life[life.index(questionnaire) + 1], comparison)

    # #314: on screen each questionnaire is one fold, closed, its summary row saying its name,
    # latest date and result; its kept comparison folds with it. Owner and family alike.
    def test_each_questionnaire_is_a_closed_fold_with_its_summary_row(self):
        hhie_unaided = self.on(self.record(self.hhie, wearing=False, score=4), 1)  # 40
        hhie_aided = self.on(self.record(self.hhie, wearing=True, score=2), 2)  # 20
        hhia_unaided = self.on(self.record(self.hhia, wearing=False, score=4), 3)  # 40
        hhia_aided = self.on(self.record(self.hhia, wearing=True, score=0), 4)  # 0
        self.on(self.record(self.thi), 5)  # 25 items x 2 = 50
        ssq_unaided = self.on(self.record(self.ssq, wearing=False, score=4), 6)
        ssq_aided = self.on(self.record(self.ssq, wearing=True, score=6), 7)
        for unaided, aided in (
            (hhie_unaided, hhie_aided),
            (hhia_unaided, hhia_aided),
            (ssq_unaided, ssq_aided),
        ):
            self.client.post(
                f"/comparisons/{unaided.questionnaire_id}",
                {"unaided": unaided.pk, "aided": aided.pk, "action": "save"},
            )
        ioi = self.record(
            self.ioi, wearing=True, norm_group=NormGroup.MILD_MODERATE, norm_basis=hhie_unaided
        )
        # Against mild_moderate norms: item 2 below, item 7 above (the report tests' answers).
        for answer, score in zip(
            ioi.answers.order_by("question__question_number"), test_report.IOI_SCORES, strict=True
        ):
            Answer.objects.filter(pk=answer.pk).update(score=score)
        self.on(ioi, 9)
        expected = [
            (
                "report-life-impact",
                "HHIA-S 最近一次 2026/10/04 0 分 無／極輕微影響",
                ["report-hhia-s", "report-comparison-hhia-s"],
            ),
            (
                "report-life-impact",
                "HHIE-S 最近一次 2026/10/02 20 分 輕度到中度影響",
                ["report-hhie-s", "report-difference"],
            ),
            ("report-tinnitus", "THI 最近一次 2026/10/05 50 分 中度障礙", ["report-thi"]),
            (
                "report-listening",
                "SSQ12-TW 最近一次 2026/10/07 平均 6.0 分",
                ["report-ssq12", "report-comparison-ssq12-tw"],
            ),
            ("report-satisfaction", "SADL 最近一次 2026/10/08 整體滿意度 4.0", ["report-sadl"]),
            (
                "report-hearing-aid-outcome",
                "IOI-HA 助聽器效益 最近一次 2026/10/09 7 項中 1 項低於常模、1 項高於常模",
                ["report-ioi-ha"],
            ),
        ]
        with register(replace(sadl.DEFINITION, listed=True)):
            self.on(self.record(self.sadl, score=4), 8)
            owner = self.client.get("/report")
            for name, response in (("owner", owner), ("family", self.family_report())):
                with self.subTest(report=name):
                    folds = _folds(response)
                    self.assertEqual(
                        [(f["part"], f["summary"], f["sections"]) for f in folds], expected
                    )
                    for fold in folds:
                        self.assertFalse(fold["open"], fold["summary"])
                        self.assertEqual(fold["headings"], [3], fold["summary"])

    def test_parts_are_level_two_and_their_contents_level_three(self):
        basis = self.save_pair(self.hhie)
        self.save_pair(self.ssq)
        self.record(self.ioi, score=3, norm_group=NormGroup.MILD_MODERATE, norm_basis=basis)
        with register(replace(sadl.DEFINITION, listed=True)):
            self.record(self.sadl)
            owner = self.client.get("/report")
            for response in (owner, self.family_report()):
                outline = _outline(response)
                self.assertEqual([level for level, _ in outline.headings].count(1), 1)
                part_titles = {
                    sections[0] for _, sections in outline.headings if len(sections) == 1
                }
                self.assertLessEqual(set(PARTS), part_titles)
                # #314: a part's own title is level 2; every heading after it in the part (each
                # questionnaire's summary row and the titles inside its fold) is level 3.
                for part in PARTS:
                    levels = [
                        level for level, sections in outline.headings if sections[:1] == (part,)
                    ]
                    self.assertEqual(levels[0], 2, part)
                    self.assertGreater(len(levels), 1, part)
                    self.assertEqual(set(levels[1:]), {3}, part)

    def test_parts_without_records_are_left_out(self):
        self.record(self.hhie, wearing=False)
        owner = self.client.get("/report")
        for page in (owner, self.family_report()):
            self.assertContains(page, 'id="report-life-impact"')
            self.assertEqual([fold["summary"][:6] for fold in _folds(page)], ["HHIE-S"])
            for part in ("report-listening", "report-hearing-aid-outcome"):
                self.assertNotContains(page, f'id="{part}"')

    def test_hhia_s_note_appears_once(self):
        self.record(self.hhia, wearing=False)
        self.assertContains(self.client.get("/report"), HHIA_S_EXPLANATION, count=1)
        self.assertContains(self.family_report(), HHIA_S_EXPLANATION, count=1)
