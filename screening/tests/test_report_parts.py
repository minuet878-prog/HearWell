"""Health report groups adult results into three parts (#90)."""

from html.parser import HTMLParser
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from screening.models import Answer, NormGroup, Question, Questionnaire, Submission
from screening.questionnaires.hhia_s import EXPLANATION as HHIA_S_EXPLANATION
from screening.tests import test_report
from screening.tests.helpers import consented_user

PARTS = {
    "report-life-impact": "生活影響",
    "report-listening": "日常聆聽能力",
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


class ReportPartsTests(TestCase):
    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.hhia = Questionnaire.objects.get(code="hhia-s")
        self.ssq = Questionnaire.objects.get(code="ssq12-tw")
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
                "report-ioi-ha": "report-hearing-aid-outcome",
            }
            for section_id, part in expected.items():
                self.assertEqual(outline.parents[section_id], (part,), section_id)
            # Each comparison follows its own questionnaire, not the other HHI.
            life = [
                s for s, parents in outline.parents.items() if parents == ("report-life-impact",)
            ]
            for questionnaire, comparison in (
                ("report-hhie-s", "report-difference"),
                ("report-hhia-s", "report-comparison-hhia-s"),
            ):
                self.assertEqual(life[life.index(questionnaire) + 1], comparison)

    def test_parts_are_level_two_and_their_contents_level_three(self):
        basis = self.save_pair(self.hhie)
        self.save_pair(self.ssq)
        self.record(self.ioi, score=3, norm_group=NormGroup.MILD_MODERATE, norm_basis=basis)
        owner = self.client.get("/report")
        for response in (owner, self.family_report()):
            outline = _outline(response)
            self.assertEqual([level for level, _ in outline.headings].count(1), 1)
            part_titles = {sections[0] for _, sections in outline.headings if len(sections) == 1}
            self.assertLessEqual(set(PARTS), part_titles)
            for level, sections in outline.headings:
                if sections and sections[0] in PARTS:
                    self.assertEqual(level, 2 if len(sections) == 1 else 3, sections)

    def test_parts_without_records_are_left_out(self):
        self.record(self.hhie, wearing=False)
        owner = self.client.get("/report")
        for page in (owner, self.family_report()):
            self.assertContains(page, 'id="report-life-impact"')
            for part in ("report-listening", "report-hearing-aid-outcome"):
                self.assertNotContains(page, f'id="{part}"')

    def test_hhia_s_note_appears_once(self):
        self.record(self.hhia, wearing=False)
        self.assertContains(self.client.get("/report"), HHIA_S_EXPLANATION, count=1)
        self.assertContains(self.family_report(), HHIA_S_EXPLANATION, count=1)
