"""#750 (spec #741 acceptance 49, page grill P11): a level's short name in large type on the result
page; its full name for screen readers there, and on the report, the download and the shared page.
"""

import json
import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening import questionnaires
from screening.models import ReportShare
from screening.questionnaires import hhia_s, hhie_s, thi
from screening.scoring import classify
from screening.tests.helpers import consented_user, submission_with_answers

# The large level on the result page and what a screen reader reads in its place.
LEVEL = re.compile(
    r'<p class="result-level-short" aria-hidden="true">([^<]*)</p>\s*'
    r'<h2 class="result-block-level visually-hidden" aria-describedby="result-score">([^<]*)</h2>'
)


class ShortLevelNameTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())

    def setUp(self):
        self.user = consented_user(username="short_level_user")
        self.client.force_login(self.user)

    def page(self, url):
        return self.client.get(url).content.decode()

    def test_every_graded_level_has_a_short_name(self):
        # The owner's words for HHIE-S and HHIA-S are the canvas's (ProRecords, TrendA).
        for code, short in (
            (hhie_s.CODE, ["極輕微", "輕到中度", "顯著"]),
            (hhia_s.CODE, ["極輕微", "輕到中度", "顯著"]),
            (thi.CODE, ["輕微", "輕度", "中度", "重度", "極重度"]),
        ):
            definition = questionnaires.get(code)
            with self.subTest(code=code):
                self.assertEqual(
                    [classify(upper, code)["short"] for upper, _, _ in definition.thresholds],
                    short,
                )

    def test_the_result_page_writes_the_short_name_large_and_reads_the_full_one(self):
        submission = submission_with_answers(
            self.user, hhie_s.CODE, [4, 4, 4, 0, 0, 0, 0, 0, 0, 0], wearing_hearing_aid=False
        )
        page = self.page(reverse("result", args=[submission.pk]))
        self.assertEqual(LEVEL.findall(page), [("輕到中度", "輕度到中度影響")])

    def test_the_report_the_download_and_the_shared_page_write_the_full_name(self):
        submission_with_answers(
            self.user, hhie_s.CODE, [4, 4, 4, 0, 0, 0, 0, 0, 0, 0], wearing_hearing_aid=False
        )
        share = ReportShare.objects.create(user=self.user)
        export = json.loads(self.client.get(reverse("download_my_data")).content)
        pages = {
            "report": self.page(reverse("health_report")),
            "shared": self.page(reverse("shared_report", args=[share.token])),
            "download": json.dumps(export, ensure_ascii=False),
        }
        for name, page in pages.items():
            with self.subTest(page=name):
                self.assertIn("輕度到中度影響", page)
                self.assertNotIn("輕到中度", page)
