"""#434 (spec #426): 陪長輩適應 on 助聽器, as the server sends it. Picking a stage in a real browser
is in e2e.main_flow.FamilyAdjustingTest."""

import re

from django.test import TestCase
from django.urls import reverse

from screening.models import Question, Questionnaire
from screening.questionnaires.ioi_ha import CODE as IOI_HA
from screening.tests import test_family_guide, test_family_zone
from screening.tests.helpers import consented_user

YOU_CAN_DO = "您可以做的事"
# Words of batch-3-wording.md section 2, written out so a slip in the definition shows.
STAGES = {
    "剛開始戴": [
        "告訴他前幾週覺得自己的聲音怪、環境很吵是常見的，大腦需要時間適應。",
        "照聽力師的建議，陪他從安靜的地方、短時間開始，再慢慢拉長。",
        "回診時一起學怎麼戴上、拿下、清潔和換電池，回家才幫得上忙。",
    ],
    "戴了不習慣": [
        "一起記下哪些場合聽不清楚、哪裡不舒服，回診時告訴聽力師。",
        "陪他回去調整。適應可能要好幾個月，設定也可能要調整不只一次。",
        "在吵雜的餐廳、多人聊天時還是可能聽不清楚，說話的方法依然有用。",
    ],
    "不想再戴": [
        "先問他是哪裡不舒服：聲音、耳朵、操作，還是覺得沒有幫助。",
        "告訴他這些都可以回去請聽力師調整，不用勉強忍耐。",
        "他不想談的時候，可以看「長輩不肯去怎麼說」。",
    ],
}
STAGE_LINKS = {
    "剛開始戴": [],
    "戴了不習慣": [("/family#talk-title", "怎麼跟聽損的家人說話")],
    "不想再戴": [
        ("/family#urgent-title", "什麼時候要馬上就醫"),
        ("/family/reluctant", "長輩不肯去怎麼說"),
    ],
}


class FamilyAdjustingTests(TestCase):
    fixtures = ("questions_fixture.json",)

    def setUp(self):
        self.url = reverse("family_hearing_aids")

    def _section(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        main = test_family_zone._main(response.content.decode())
        start = main.index('<h2 id="adjusting-title"')
        return main[start : main.index("</section>", start)]

    def _options(self):
        """{label: the HTML under it} for each stage's explanation, as the server sends them."""
        section = self._section()
        start = section.index("data-pick-explanations")
        explanations = section[start : section.index("data-pick-live", start)]
        chunks = explanations.split('<strong class="tint-subhead block">')[1:]
        return {chunk.split("</strong>")[0]: chunk.split("</strong>", 1)[1] for chunk in chunks}

    def test_the_question_and_its_stages_in_order(self):
        section = self._section()
        self.assertRegex(section, r'^<h2 id="adjusting-title"[^>]*>陪長輩適應</h2>')
        self.assertRegex(section, r"<legend[^>]*>他現在是哪個階段？</legend>")
        self.assertEqual(
            re.findall(
                r'<input type="radio" name="hearing-aid-stage" autocomplete="off">'
                r"<span>([^<]+)</span>",
                section,
            ),
            list(STAGES),
        )

    # Acceptance 32: each stage, what the family can do and nothing else.
    def test_each_stage_lists_what_the_family_can_do(self):
        options = self._options()
        for label, lines in STAGES.items():
            with self.subTest(label=label):
                groups = re.findall(
                    r"<h3[^>]*>([^<]+)</h3>\s*<ul[^>]*>(.*?)</ul>", options[label], re.S
                )
                self.assertEqual(
                    [(title, re.findall(r"<li>([^<]+)</li>", items)) for title, items in groups],
                    [(YOU_CAN_DO, lines)],
                )

    def test_stages_link_to_the_pages_that_say_more_instead_of_repeating_them(self):
        options = self._options()
        for label, links in STAGE_LINKS.items():
            with self.subTest(label=label):
                self.assertEqual(
                    re.findall(
                        r'<a [^>]*href="([^"]+)"[^>]*>.*?link-card-title">([^<]+)<',
                        options[label],
                        re.S,
                    ),
                    links,
                )

    def test_those_links_land_where_they_say(self):
        self.assertRegex(
            self.client.get("/family").content.decode(),
            r'<h2 id="talk-title"[^>]*>(<svg.*?</svg>)?怎麼跟聽損的家人說話</h2>',
        )
        self.assertContains(
            self.client.get("/family/reluctant"), "長輩不肯去怎麼說</h1>", status_code=200
        )

    def test_jump_link_comes_after_the_problems_and_lands_on_the_section(self):
        main = test_family_zone._main(self.client.get(self.url).content.decode())
        self.assertRegex(main, r'(?s)<a [^>]*href="#adjusting-title"[^>]*>.*?陪長輩適應.*?</a>')
        self.assertLess(main.index('href="#problems-title"'), main.index('href="#adjusting-title"'))
        self.assertLess(main.index('id="problems-title"'), main.index('id="adjusting-title"'))

    def _survey_address(self):
        return reverse("screening", args=[Questionnaire.objects.get(code=IOI_HA).pk])

    # Acceptance 32: once, under the options, so it shows whichever stage is picked.
    def test_survey_link_shows_once_under_the_stages(self):
        section = self._section()
        self.assertRegex(
            section[section.index("</fieldset>") :],
            rf'<p[^>]*>想記錄戴起來的效果，可以做<a [^>]*href="{self._survey_address()}"[^>]*>'
            r"配戴效果問卷</a>（要先註冊或登入）。</p>",
        )
        self.assertEqual(section.count("配戴效果問卷"), 1)

    # 要先註冊或登入 is true of the address: a visitor is sent to log in and on to the survey.
    def test_survey_link_asks_a_visitor_to_log_in_and_opens_for_an_account(self):
        address = self._survey_address()
        self.assertRedirects(
            self.client.get(address), f"{reverse('login')}?next={address}", status_code=302
        )
        self.client.force_login(consented_user(username="adjusting_family"))
        self.assertEqual(self.client.get(address).status_code, 200)

    def test_without_the_survey_in_the_database_the_page_opens_with_no_link(self):
        Question.objects.filter(questionnaire__code=IOI_HA).delete()
        Questionnaire.objects.filter(code=IOI_HA).delete()
        section = self._section()
        self.assertNotIn("配戴效果問卷", section)
        self.assertIn("他現在是哪個階段？", section)

    # Looks up the survey and no one: a visitor's page takes that one query.
    def test_a_visitors_page_only_looks_up_the_survey(self):
        with self.assertNumQueries(1) as queries:
            self.client.get(self.url)
        self.assertIn('"screening_questionnaire"', queries[0]["sql"])

    # Acceptance 32: 陪伴配戴助聽器 on /family, tip by tip, with nothing of this ticket's added.
    def test_family_page_keeps_its_wording_on_wearing_hearing_aids(self):
        content = self.client.get("/family").content.decode()
        start = content.index('<h2 id="aid-title"')
        section = content[start : content.index("</section>", start)]
        self.assertIn("</svg>陪伴配戴助聽器</h2>", section)
        self.assertEqual(
            re.findall(
                r'<li><strong class="tip-point tint-subhead">([^<]+)</strong>([^<]+)</li>', section
            ),
            list(test_family_guide.TIPS["aid-title"]),
        )
        self.assertEqual(section.count("<li>"), len(test_family_guide.TIPS["aid-title"]))
        self.assertNotIn(YOU_CAN_DO, content)

    # The owner, 2026-11-06: an ear that hurts is not one for adjusting first.
    def test_not_wanting_to_wear_them_says_when_to_see_a_doctor(self):
        content = self.client.get(reverse("family_hearing_aids")).content.decode()
        start = content.index("<strong>如果是耳朵痛或流膿，請盡快就醫。</strong>")
        self.assertGreater(start, content.index('id="adjusting-title"'))
        self.assertRegex(
            content[start:], r'<a [^>]*href="/family#urgent-title"[^>]*>.*?什麼時候要馬上就醫'
        )
