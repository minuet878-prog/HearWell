"""#648 (spec #644 H4, acceptance 19-26, the #645 mockup's 3A): 我的紀錄's questionnaire side,
the audiogram list, the health report and the share page before there is anything to show, one
look shared by the four: an icon, a title, a sentence and (but on the audiogram list) a solid
做第一份問卷 going where the home page's 照顧旅程 step 1 goes."""

import re
from datetime import date
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.care_journey import care_journey
from screening.models import Questionnaire
from screening.questionnaires import hhia_s, hhie_s
from screening.tests import test_guide_summary
from screening.tests.helpers import consented_user

SOLID = re.compile(r'class="btn btn-primary\b')
FIRST = "做第一份問卷"
QUESTIONNAIRES = f"{reverse('my_hearing')}?view=questionnaires"
NORMAL = (20, 20, 20, 20)


def _empty_state(main):
    """(icon, title, sentence, (button, its address) or None), or None without one."""
    found = re.search(
        r'<div class="empty-state">\s*'
        r'<span class="action-card-icon" aria-hidden="true" data-icon="([^"]*)">.*?</span>\s*'
        r"<h2[^>]*>([^<]*)</h2>\s*<p>([^<]*)</p>\s*"
        r'(?:<a class="btn btn-primary btn-lg w-full" href="([^"]*)">([^<]*)</a>\s*)?</div>',
        main,
        re.S,
    )
    if found is None:
        return None
    icon, title, sentence, href, button = found.groups()
    return icon, title, sentence, (button, href) if button else None


class EmptyStateTestCase(TestCase):
    fixtures = ("questions_fixture.json",)

    @classmethod
    def setUpTestData(cls):
        call_command("seed_questionnaires", stdout=StringIO())

    def setUp(self):
        self.sign_in("empty_states", birth_year=date.today().year - 70)

    make = test_guide_summary.GuideSummaryTests.make

    def sign_in(self, username, birth_year):
        self.user = consented_user(username=username, birth_year=birth_year)
        self.client.force_login(self.user)

    def main(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def step_one(self):
        """Where the home page's 照顧旅程 step 1 goes for this user."""
        journey = care_journey(self.user, timezone.localdate())
        self.assertEqual(journey.current, 1)
        return journey.card.button[1]

    def home_step_one(self):
        """The address of the home page's 去做問卷, on its journey card."""
        main = self.main(reverse("index"))
        found = re.search(r'<a class="btn btn-hero btn-lg" href="([^"]*)">去做問卷</a>', main)
        self.assertIsNotNone(found)
        return found.group(1)


class MyRecordsEmptyTests(EmptyStateTestCase):
    def test_no_records_shows_the_empty_state(self):
        # Acceptance 19.
        hhie = Questionnaire.objects.get(code=hhie_s.CODE)
        main = self.main(reverse("my_hearing"))
        self.assertEqual(
            _empty_state(main),
            (
                "records",
                "還沒有紀錄",
                "做完第一份問卷，分數和變化會出現在這裡。",
                (FIRST, reverse("screening", args=[hhie.pk])),
            ),
        )
        self.assertNotIn("您還沒有做過篩檢紀錄", main)

    def test_the_report_is_a_list_row_and_the_page_has_one_solid_button(self):
        # Acceptance 21: as when the retest reminder is up; 傳給家人看 as before.
        main = self.main(reverse("my_hearing"))
        self.assertEqual(len(SOLID.findall(main)), 1)
        self.assertRegex(
            main,
            rf'<a class="link-card action-card" href="{reverse("health_report")}">\s*'
            r'<span class="action-card-icon" aria-hidden="true" data-icon="report">.*?</span>\s*'
            r'<span class="link-card-body">\s*<span class="link-card-title">看／印聽力報告</span>',
        )
        self.assertIn('<span class="link-card-title">傳給家人看</span>', main)
        self.assertLess(main.index("看／印聽力報告"), main.index("傳給家人看"))

    def test_with_only_audiograms_the_questionnaire_side_is_empty_too(self):
        # Acceptance 19: opened on the questionnaire side.
        self.make(NORMAL, NORMAL)
        main = self.main(QUESTIONNAIRES)
        self.assertEqual(_empty_state(main)[1], "還沒有紀錄")
        self.assertEqual(len(SOLID.findall(main)), 1)

    def test_first_questionnaire_goes_where_the_home_page_step_one_goes(self):
        # Acceptance 20: by age, the catalogue when unknown or exactly 65. With an audiogram the
        # home page shows the journey, so its 去做問卷 is there to compare.
        this_year = date.today().year
        hhie = reverse("screening", args=[Questionnaire.objects.get(code=hhie_s.CODE).pk])
        hhia = reverse("screening", args=[Questionnaire.objects.get(code=hhia_s.CODE).pk])
        catalogue = reverse("questionnaire_list")
        for name, birth_year, expected in (
            ("seventy", this_year - 70, hhie),
            ("forty", this_year - 40, hhia),
            ("sixty_five", this_year - 65, catalogue),
            ("unknown", None, catalogue),
        ):
            with self.subTest(name):
                self.sign_in(f"empty_records_{name}", birth_year)
                self.make(NORMAL, NORMAL)
                _, _, _, (_, href) = _empty_state(self.main(QUESTIONNAIRES))
                self.assertEqual(href, expected)
                self.assertEqual(href, self.home_step_one())

    def test_records_leave_the_empty_state(self):
        hhie = Questionnaire.objects.get(code=hhie_s.CODE)
        self.user.submissions.create(questionnaire=hhie, wearing_hearing_aid=False)
        main = self.main(reverse("my_hearing"))
        self.assertIsNone(_empty_state(main))
        self.assertIn(
            f'<a class="btn btn-primary btn-lg w-full mt-4 mb-4" href="{reverse("health_report")}">'
            "看／印聽力報告</a>",
            main,
        )


class AudiogramListEmptyTests(EmptyStateTestCase):
    def test_no_audiograms_shows_the_empty_state_without_a_button(self):
        # Acceptance 22: the sentence as before, 記錄聽力圖 above the page's one solid button.
        main = self.main(reverse("audiogram_list"))
        self.assertEqual(
            _empty_state(main),
            (
                "audiogram",
                "還沒有聽力圖",
                "拿著醫院的聽力檢查報告，按上面的「記錄聽力圖」把它描進來。",
                None,
            ),
        )
        self.assertEqual(len(SOLID.findall(main)), 1)
        self.assertRegex(
            main, rf'<a class="btn btn-primary btn-lg w-full" href="{reverse("audiogram_new")}">'
        )
        self.assertLess(main.index("記錄聽力圖"), main.index("還沒有聽力圖"))

    def test_an_audiogram_leaves_the_empty_state(self):
        self.make(NORMAL, NORMAL)
        self.assertIsNone(_empty_state(self.main(reverse("audiogram_list"))))


class ReportAndShareEmptyTests(EmptyStateTestCase):
    PAGES = (
        (
            "health_report",
            "report",
            "還沒有報告",
            "做完第一份問卷或記錄聽力圖，報告就會有內容，可以印出來給醫師看。",
        ),
        (
            "share_report",
            "share",
            "還沒有可以分享的紀錄",
            "做完第一份問卷或記錄聽力圖，就能傳給家人看。",
        ),
    )

    def test_without_any_record_each_page_shows_its_empty_state(self):
        # Acceptance 23 and 24: no print button, no step making a link.
        for name, icon, title, sentence in self.PAGES:
            with self.subTest(name):
                main = self.main(reverse(name))
                self.assertEqual(
                    _empty_state(main), (icon, title, sentence, (FIRST, self.step_one()))
                )
                self.assertEqual(len(SOLID.findall(main)), 1)
                for absent in (
                    "還沒有可以放進報告的紀錄",
                    "開始篩檢",
                    'id="print-button"',
                    "產生連結",
                ):
                    self.assertNotIn(absent, main)

    def test_first_questionnaire_goes_where_the_home_page_step_one_goes(self):
        # Acceptance 20 on both pages.
        this_year = date.today().year
        hhie = reverse("screening", args=[Questionnaire.objects.get(code=hhie_s.CODE).pk])
        hhia = reverse("screening", args=[Questionnaire.objects.get(code=hhia_s.CODE).pk])
        catalogue = reverse("questionnaire_list")
        for who, birth_year, expected in (
            ("seventy", this_year - 70, hhie),
            ("forty", this_year - 40, hhia),
            ("sixty_five", this_year - 65, catalogue),
            ("unknown", None, catalogue),
        ):
            self.sign_in(f"empty_report_{who}", birth_year)
            for name, *_ in self.PAGES:
                with self.subTest(who=who, page=name):
                    _, _, _, (_, href) = _empty_state(self.main(reverse(name)))
                    self.assertEqual(href, expected)
                    self.assertEqual(href, self.step_one())

    def test_only_an_audiogram_shows_the_report_and_the_share_steps(self):
        # Acceptance 25: as now, not empty.
        self.make(NORMAL, NORMAL)
        report = self.main(reverse("health_report"))
        self.assertIsNone(_empty_state(report))
        self.assertIn('id="print-button"', report)
        share = self.main(reverse("share_report"))
        self.assertIsNone(_empty_state(share))
        self.assertIn("我知道了，產生連結", share)

    def test_the_title_is_a_heading_and_the_icon_is_not_read(self):
        # Acceptance 26: a heading of its own under the page's h1; the icon aria-hidden (as
        # _empty_state reads it) on all four.
        self.make(NORMAL, NORMAL)
        self.sign_in("empty_headings", date.today().year - 70)
        for url in (
            reverse("my_hearing"),
            reverse("audiogram_list"),
            reverse("health_report"),
            reverse("share_report"),
        ):
            with self.subTest(url):
                main = self.main(url)
                self.assertIsNotNone(_empty_state(main))
                self.assertEqual(len(re.findall(r"<h1[\s>]", main)), 1)
                self.assertRegex(main, r'<div class="empty-state">\s*<span[^>]*aria-hidden="true"')

    def test_the_three_buttons_ask_one_place_where_to_go(self):
        # 做第一份問卷 on 我的紀錄, the report and the share page: care_journey's one function.
        for module, url in (
            ("my_hearing", QUESTIONNAIRES),
            ("reports", reverse("health_report")),
            ("reports", reverse("share_report")),
        ):
            target = f"screening.views.{module}.first_questionnaire_url"
            with self.subTest(url), patch(target, return_value="/stand-in/") as asked:
                _, _, _, (_, href) = _empty_state(self.main(url))
                self.assertEqual(href, "/stand-in/")
                asked.assert_called_once_with(self.user, timezone.localdate())
