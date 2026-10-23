"""Result pages tidy-up: one header, one closing row and one dropdown style on every result page."""

import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, NormGroup, Questionnaire, Submission
from screening.tests.helpers import consented_user

# A valid score for every item of each questionnaire, and what its header names.
QUESTIONNAIRES = {
    "hhie-s": (2, "聽力對生活的影響", "HHIE-S"),
    "hhia-s": (2, "聽力對生活的影響", "HHIA-S"),
    "thi": (2, "耳鳴對生活的影響", "THI"),
    "ssq12-tw": (6, "日常聆聽能力", "SSQ12-TW"),
    "ioi-ha": (3, "助聽器使用成效", "IOI-HA"),
    "sadl": (4, "助聽器滿意度", "SADL"),
}
TREND_CHART = ("hhie-s", "thi")  # HHIA-S has no trend chart
ALWAYS_AIDED = ("ioi-ha", "sadl")
ENDS = "<span>較差</span><span>較好</span>"


class ResultPagesTests(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())
        cls.user = consented_user(username="result_pages_user")
        cls.submissions = {}
        for code, (score, _, _) in QUESTIONNAIRES.items():
            questionnaire = Questionnaire.objects.get(code=code)
            submission = Submission.objects.create(
                user=cls.user,
                questionnaire=questionnaire,
                wearing_hearing_aid=True if code in ALWAYS_AIDED else False,
                # IOI-HA compared with the norms of the HHIE-S record above: 「其他 n 項」 shows.
                norm_group=NormGroup.MILD_MODERATE if code == "ioi-ha" else "",
                norm_basis=cls.submissions.get("hhie-s"),
            )
            Answer.objects.bulk_create(
                Answer(submission=submission, question=question, score=score)
                for question in questionnaire.questions.all()
            )
            cls.submissions[code] = submission

    def setUp(self):
        self.client.force_login(self.user)

    def _main(self, code):
        response = self.client.get(reverse("result", args=[self.submissions[code].pk]))
        html = response.content.decode()
        return html[html.index("<main") : html.index("</main>")]

    def _text(self, html):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()

    def test_every_result_page_is_headed_by_its_topic_then_name_date_and_wearing(self):
        for code, (_, topic, name) in QUESTIONNAIRES.items():
            with self.subTest(code=code):
                main = self._main(code)
                day = timezone.localtime(self.submissions[code].created_at).strftime("%Y/%m/%d")
                header = re.search(r"<h1[^>]*>(.*?)</h1>\s*<p[^>]*>(.*?)</p>", main, re.S)
                self.assertEqual(self._text(header.group(1)), topic)
                # IOI-HA and SADL are always answered wearing hearing aids: not said again.
                wearing = "" if code in ALWAYS_AIDED else "・沒戴助聽器"
                self.assertEqual(self._text(header.group(2)), f"{name}・{day} 作答{wearing}")

    def test_no_result_page_is_titled_screening_result(self):
        # THI is not a screening (GLOSSARY): the page says which questionnaire it is.
        response = self.client.get(reverse("result", args=[self.submissions["thi"].pk]))
        self.assertContains(response, "<title>THI 結果\uff5cHearWell</title>", html=True)
        self.assertNotContains(response, "篩檢結果")

    def test_every_result_page_ends_with_records_report_and_home(self):
        for code in QUESTIONNAIRES:
            with self.subTest(code=code):
                main = self._main(code)
                row = re.search(r'<div class="result-actions[^"]*">(.*?)</div>', main, re.S)
                links = re.findall(r'<a class="([^"]+)" href="([^"]+)">(.*?)</a>', row.group(1))
                records = "看我的紀錄與趨勢" if code in TREND_CHART else "看我的紀錄"
                self.assertEqual(
                    links,
                    [
                        (
                            "btn btn-primary btn-lg",
                            f"{reverse('my_hearing')}?questionnaire={code}",
                            records,
                        ),
                        (
                            "btn btn-outline-primary btn-lg",
                            reverse("health_report"),
                            "看／印聽力報告",
                        ),
                        ("btn btn-outline-primary btn-lg", reverse("index"), "回首頁"),
                    ],
                )
                self.assertEqual(main.count('class="result-actions'), 1)

    def test_every_dropdown_on_a_result_page_is_the_framed_kind(self):
        # The site-wide dropdown box (.dropdown-box), not a bare ▶ line of small text.
        for code in QUESTIONNAIRES:
            with self.subTest(code=code):
                for details in re.findall(r"<details[^>]*>", self._main(code)):
                    self.assertIn("dropdown-box", details)

    def test_ssq12_says_higher_is_better_once(self):
        # 「比上一次」's line already says it, so the line under it does not repeat it.
        earlier = self.submissions["ssq12-tw"]
        Submission.objects.filter(pk=earlier.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=1)
        )
        newer = Submission.objects.create(
            user=self.user, questionnaire=earlier.questionnaire, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=newer, question=question, score=8)
            for question in newer.questionnaire.questions.all()
        )
        main = self.client.get(reverse("result", args=[newer.pk])).content.decode()
        self.assertIn("（分數越高越好）", main)
        self.assertNotIn("分數越高，代表您回報的聆聽能力越好。", main)

    def test_ssq12_without_an_earlier_record_still_says_which_way_is_better(self):
        self.assertIn("分數越高，代表您回報的聆聽能力越好。", self._main("ssq12-tw"))

    def test_ioi_ha_scale_names_its_two_ends(self):
        # Left is 1, the worst answer, on every item; the words already say which it is.
        main = self._main("ioi-ha")
        ends = re.findall(
            r'<div class="ioi-scale" aria-hidden="true">.*?</div>\s*(<div[^>]*>.*?</div>)',
            main,
            re.S,
        )
        self.assertEqual(
            ends,
            ['<div class="ioi-scale-ends" aria-hidden="true">' + ENDS + "</div>"] * 7,
        )

    def test_the_page_s_own_comparison_comes_before_the_closing_row(self):
        unaided = self.submissions["hhia-s"]
        aided = Submission.objects.create(
            user=self.user, questionnaire=unaided.questionnaire, wearing_hearing_aid=True
        )
        Answer.objects.bulk_create(
            Answer(submission=aided, question=question, score=0)
            for question in unaided.questionnaire.questions.all()
        )
        main = self._main("hhia-s")
        self.assertLess(main.index("比較戴與不戴助聽器</a>"), main.index('class="result-actions'))
