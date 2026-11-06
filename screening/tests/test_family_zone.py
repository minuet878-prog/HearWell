"""Spec #426 (家人專區): the zone's home page and ways to reach it (#427), its scenarios (#428),
what to say when an elder refuses (#429)."""

import inspect
import re
from dataclasses import replace
from datetime import date
from itertools import pairwise
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.family_zone import (
    COMMUNICATION_CHECKED_ON,
    COMMUNICATION_SCENARIOS,
    COMMUNICATION_SOURCES,
    RELUCTANT_CHECKED_ON,
    RELUCTANT_SITUATIONS,
    RELUCTANT_SOURCES,
)
from screening.models import Questionnaire, ReportShare, Submission, User
from screening.questionnaires import hhie_s
from screening.tests import test_pages
from screening.tests.helpers import consented_user, submission_with_answers
from screening.views import family

FAMILY_CARD = "我是家人：怎麼陪伴聽損的家人"
LEARN_CARD = "家人專區：溝通與陪伴"
# The footer's words stay as they were (#427).
FOOTER_LINK = "給家人看：怎麼跟聽損的家人溝通"
# As reviewed on 2026-10-17 (spec appendix A).
INTRO = (
    "家人有聽力困難時，日常對話常常要講好幾次，雙方都容易累、容易誤會。"
    "下面幾個小方法，可以讓溝通輕鬆一點。"
)
URGENT = (
    "出現下面任何一種情況，不要等下次回診，請盡快到耳鼻喉科就醫：",
    "突然聽不到或聽力變差（一耳或兩耳，幾小時到幾天內發生），"
    "可能伴隨耳鳴、耳悶或暈眩。這可能是突發性聽力損失，越早治療效果越好。",
    "耳朵痛、流膿或流血。",
    "嚴重暈眩、天旋地轉，或走路不穩。",
    "頭部受傷後聽力改變。",
    "如果同時出現臉歪嘴斜、單側手腳無力、說話不清楚，可能是中風，請立刻撥打 119。",
)
# Drafts for the owner's review, like the card above.
TALK_NOTE = "情境題與溝通重點"
AID_NOTE = "剛開始不習慣、回診和保養時可以怎麼陪"
RELUCTANT_NOTE = "不想檢查、不想戴時可以試的說法"
# (href, title) of each card in a part of a page, in page order.
CARD = re.compile(
    r'<a class="link-card[^"]*" href="([^"]*)">.*?<span class="link-card-title">([^<]*)</span>',
    re.S,
)
# (href, icon or nothing, title, the line under it or nothing) of each of the zone's entries.
ENTRY = re.compile(
    r'<a class="link-card[^"]*" href="([^"]*)">\s*'
    r'(?:<span class="action-card-icon" aria-hidden="true" data-icon="([^"]+)">.*?</span>\s*)?'
    r'<span class="link-card-body">\s*<span class="link-card-title">([^<]*)</span>\s*'
    r"(?:<span>([^<]*)</span>\s*)?</span>",
    re.S,
)
# What SignsInWithARecord's answers come to on HHIE-S, worked out by hand: 16 of 40.
RECORD_LEVEL = "輕度到中度影響"
RECORD_TOTAL = r"(?<!\d)16(?!\d)"


def _main(content):
    return content[content.index("<main") : content.index("</main>")]


class SignsInWithARecord:
    """For pages that read nobody's records: an account with a graded record to prove it on."""

    def sign_in_with_a_record(self, username):
        call_command("loaddata", "questions_fixture.json", verbosity=0)
        user = consented_user(username=username, email=f"{username}@example.com")
        record = submission_with_answers(
            user, hhie_s.CODE, [4, 4, 2, 0, 0, 0, 4, 0, 0, 2], wearing_hearing_aid=False
        )
        self.client.force_login(user)
        # The account's own result page does show these, so their absence elsewhere means something.
        own_result = self.client.get(reverse("result", args=[record.pk])).content.decode()
        self.assertIn(RECORD_LEVEL, own_result)
        self.assertRegex(own_result, RECORD_TOTAL)

    def assert_shows_no_record(self, content, username):
        self.assertNotIn(RECORD_LEVEL, content)
        main = _main(content)
        self.assertNotRegex(re.sub(r"<[^>]+>", " ", main), RECORD_TOTAL)
        self.assertNotIn(username, main)


class FamilyZoneHomeTests(SignsInWithARecord, TestCase):
    def setUp(self):
        self.url = reverse("family_guide")

    def _home(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        return _main(response.content.decode())

    def assert_family_card_under_the_guide_card(self):
        main = self._home()
        self.assertEqual(
            CARD.findall(main),
            [(reverse("guide"), "了解助聽器選配與補助"), (self.url, FAMILY_CARD)],
        )
        # The main buttons keep their place above the cards.
        self.assertLess(main.index("開始篩檢"), main.index("了解助聽器選配與補助"))
        self.assertLess(main.index(FAMILY_CARD), main.index("結果長這樣"))

    def test_visitor_sees_the_family_card_under_the_guide_card(self):
        self.assert_family_card_under_the_guide_card()
        main = self._home()
        self.assertLess(main.index("開始篩檢"), main.index("我已經有帳號，登入"))
        self.assertLess(main.index("我已經有帳號，登入"), main.index("了解助聽器選配與補助"))

    def test_new_user_without_records_sees_the_family_card(self):
        self.client.force_login(consented_user(username="zone_new"))
        self.assert_family_card_under_the_guide_card()

    def test_returning_user_home_has_no_family_card_and_the_same_tabs(self):
        user = consented_user(username="zone_returning")
        questionnaire = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        Submission.objects.create(user=user, questionnaire=questionnaire)
        self.client.force_login(user)
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("您還可以", content)  # really the returning user's page
        self.assertNotIn(FAMILY_CARD, content)
        nav = test_pages.RedesignLayoutTests.NAV.search(content).group()
        self.assertEqual(
            re.findall(r"<span>([^<]+)</span>", nav),
            ["首頁", "篩檢", "紀錄", "了解"],
        )

    # The zone's home page: picked on the comparison page, option A.
    def _zone(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _entries(self, content):
        start = content.index('aria-label="專區內容"')
        return content[start : content.index("</nav>", start)]

    def assert_zone_home(self):
        content = self._zone()
        self.assertEqual(re.findall(r"<h1[^>]*>([^<]*)</h1>", content), ["家人專區"])
        self.assertRegex(content, r"<title>\s*家人專區｜聽伴\s*</title>")  # noqa: RUF001
        self.assertEqual(
            ENTRY.findall(self._entries(content)),
            [
                ("#talk-title", "family", "怎麼跟他說話", TALK_NOTE),
                ("/family/reluctant", "question", "長輩不肯去怎麼說", RELUCTANT_NOTE),
                ("#aid-title", "ear", "陪伴配戴助聽器", AID_NOTE),
                ("#urgent-title", "", "什麼時候要馬上就醫", ""),
            ],
        )
        nav = test_pages.RedesignLayoutTests.NAV.search(content).group()
        self.assertEqual(
            re.findall(r'aria-current="page"[^>]*>.*?<span>([^<]+)</span>', nav, re.S),
            ["了解"],
        )

    def test_visitor_sees_the_zone_home_without_logging_in(self):
        self.assert_zone_home()

    def test_signed_in_user_sees_the_same_zone_home_without_their_data(self):
        visitor_main = _main(self._zone())
        self.sign_in_with_a_record("zone_private")
        self.assert_zone_home()
        content = self._zone()
        self.assertEqual(_main(content), visitor_main)
        self.assert_shows_no_record(content, "zone_private")

    def test_entries_only_for_what_is_live(self):
        entries = self._entries(self._zone())
        for later in ("陪診", "代辦", "/family/visits", "/family/hearing-aids"):
            with self.subTest(later=later):
                self.assertNotIn(later, entries)

    # Old links and the reviewed words (the talk and aid tips word by word: test_family_guide).
    def test_old_anchors_land_on_their_original_sections_with_the_reviewed_words(self):
        content = self._zone()
        self.assertIn(INTRO, content)
        for anchor, heading in (
            ("talk-title", "怎麼跟聽損的家人說話"),
            ("aid-title", "陪伴配戴助聽器"),
            ("urgent-title", "什麼時候要馬上就醫"),
        ):
            with self.subTest(anchor=anchor):
                self.assertEqual(content.count(f'id="{anchor}"'), 1)
                self.assertRegex(content, rf'<h2 id="{anchor}"[^>]*>(<svg.*?</svg>)?{heading}</h2>')
        start = content.index('id="urgent-title"')
        urgent = re.sub(r"<[^>]+>", "", content[start : content.index("</section>", start)])
        for words in URGENT:
            with self.subTest(words=words):
                self.assertIn(words, urgent)

    # Each way in, followed: the page answers, and a jump's section is on it.
    def test_entries_from_learn_footer_and_shared_report_reach_the_zone(self):
        user = consented_user(username="zone_sharer")
        share = ReportShare.objects.create(user=user)
        zone = self._zone()
        pages = {
            "了解": (reverse("learn"), LEARN_CARD),
            "頁尾": (reverse("privacy"), FOOTER_LINK),
            "分享報告": (reverse("shared_report", args=[share.token]), "怎麼跟聽損的家人說話"),
        }
        for name, (url, words) in pages.items():
            with self.subTest(page=name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                content = response.content.decode()
                self.assertIn(words, content)
                links = re.findall(rf'href="({self.url}(?:#[^"]*)?)"', content)
                self.assertTrue(links)
                for link in links:
                    path, _, anchor = link.partition("#")
                    self.assertEqual(self.client.get(path).status_code, 200)
                    if anchor:
                        self.assertIn(f'id="{anchor}"', zone)


class FamilyContentDefinitionTests(TestCase):
    """#428 (spec #426): the scenarios' words live in one definition, for review in one place."""

    def _words(self):
        for scenario in COMMUNICATION_SCENARIOS:
            yield scenario.prompt
            for option in scenario.options:
                yield option.label
                yield option.explanation

    def test_five_scenarios_of_three_options_each_with_an_explanation(self):
        self.assertEqual(len(COMMUNICATION_SCENARIOS), 5)
        for scenario in COMMUNICATION_SCENARIOS:
            with self.subTest(code=scenario.code):
                self.assertTrue(scenario.prompt.strip())
                self.assertEqual(len(scenario.options), 3)
                for option in scenario.options:
                    self.assertTrue(option.label.strip())
                    self.assertTrue(option.explanation.strip())

    # The code names the radio group, so two alike would become one question on the page.
    def test_codes_differ(self):
        codes = [scenario.code for scenario in COMMUNICATION_SCENARIOS]
        self.assertEqual(len(set(codes)), len(codes))

    # The talk section's two sources, spelled out here so a typo in either place shows.
    def test_sources_and_checked_date(self):
        self.assertEqual(
            [url for _, url in COMMUNICATION_SOURCES],
            [
                "https://www.asha.org/about/press-room/articles/"
                "tips-for-communicating-with-someone-who-has-hearing-loss/",
                "https://www.hearingloss.org/managing-hearing-loss/hearing-loss-101/"
                "communication-tips/",
            ],
        )
        for title, _ in COMMUNICATION_SOURCES:
            self.assertTrue(title.strip())
        self.assertEqual(COMMUNICATION_CHECKED_ON, date(2026, 11, 6))

    # No verdict and nothing beyond the reviewed tips: no numbers, and 「您」 not 「你」.
    def test_words_never_judge_or_add_numbers(self):
        for words in self._words():
            with self.subTest(words=words):
                self.assertNotRegex(words, r"對錯|答對|答錯|正確|錯誤|分數|總分|得分|幾分")
                self.assertNotRegex(words, r"\d")
                self.assertNotIn("你", words)

    # The options the scenarios use stay plain: only 長輩不肯去 has more than a paragraph.
    def test_scenarios_carry_only_their_explanation(self):
        for scenario in COMMUNICATION_SCENARIOS:
            for option in scenario.options:
                with self.subTest(option=option.label):
                    self.assertEqual(option.try_saying, ())
                    self.assertEqual(option.avoid_saying, ())
                    self.assertEqual(option.next_steps, ())

    # #429: the three situations, each with 2-3 things to try, 1-2 that backfire, and a next step.
    def test_reluctant_situations_are_complete(self):
        options = RELUCTANT_SITUATIONS.options
        self.assertEqual(len(options), 3)
        self.assertTrue(RELUCTANT_SITUATIONS.prompt.strip())
        for option in options:
            with self.subTest(option=option.label):
                self.assertTrue(option.explanation.strip())
                self.assertIn(len(option.try_saying), (2, 3))
                self.assertIn(len(option.avoid_saying), (1, 2))
                self.assertGreaterEqual(len(option.next_steps), 1)
                for words, url_name in option.next_steps:
                    self.assertTrue(words.strip())
                    self.assertTrue(reverse(url_name))

    # Reviewed sources only, each spelled out so a typo in either place shows.
    def test_reluctant_sources_and_checked_date(self):
        self.assertEqual(
            [url for _, url in RELUCTANT_SOURCES],
            [
                "https://www.ncoa.org/article/how-to-talk-about-hearing-loss/",
                "https://www.asha.org/siteassets/ais/ais-support-for-caregivers.pdf",
                "https://www.asha.org/siteassets/ais/ais-hearing-loss-helping-others-cope.pdf",
                "https://health.clevelandclinic.org/"
                "what-to-do-when-a-loved-one-needs-help-for-their-hearing",
                "https://www.nidcd.nih.gov/health/hearing-aids",
                "https://www.uhcw.nhs.uk/download/clientfiles/files/Patient%20Information%20Leaflets/"
                "Clinical%20Diagnostic%20Services/Audiology/"
                "Living%20with%20someone%20who%20has%20a%20gradual%20hearing%20loss.pdf",
            ],
        )
        for title, _ in RELUCTANT_SOURCES:
            self.assertTrue(title.strip())
        self.assertEqual(RELUCTANT_CHECKED_ON, date(2026, 11, 6))

    # 您 for the reader, no diagnosis, no promise, no fright (ADR 0013): no numbers, no dementia,
    # risk, cure or guarantee, even as an example of what not to say.
    def test_reluctant_words_never_frighten_diagnose_or_promise(self):
        for option in RELUCTANT_SITUATIONS.options:
            for words in (
                option.label,
                option.explanation,
                *option.try_saying,
                *option.avoid_saying,
                *(step for step, _ in option.next_steps),
            ):
                with self.subTest(words=words):
                    self.assertNotRegex(words, r"\d")
                    self.assertNotIn("你", words)
                    self.assertNotRegex(words, r"失智|風險|治好|治癒|保證|診斷|百分")


class FamilyScenarioTests(TestCase):
    """#428 (spec #426): the scenarios on /family, as the server sends them. What the script does
    with them is in pick-explain.test.js and e2e.main_flow.FamilyScenarioTest."""

    def setUp(self):
        self.url = reverse("family_guide")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.content = response.content.decode()
        start = self.content.index('<section class="mb-6" aria-labelledby="scenarios-title"')
        self.section = self.content[start : self.content.index("</section>", start)]

    def _sources(self):
        start = self.content.index('id="sources-title"')
        return self.content[start : self.content.index("</section>", start)]

    def _fieldsets(self):
        return re.findall(r"<fieldset.*?</fieldset>", self.section, re.S)

    def test_section_sits_between_the_talk_and_aid_sections(self):
        self.assertRegex(
            self.section,
            r'<h2 id="scenarios-title"[^>]*>(<svg.*?</svg>)?遇到這些情況，您會怎麼做？</h2>',
        )
        positions = [
            self.content.index(f'id="{anchor}"')
            for anchor in ("talk-title", "scenarios-title", "aid-title")
        ]
        self.assertEqual(positions, sorted(positions))

    # Fieldset, legend and native radios: the keyboard and screen readers get a radio group.
    def test_each_scenario_is_a_group_of_radios_named_by_its_code(self):
        fieldsets = self._fieldsets()
        self.assertEqual(len(fieldsets), len(COMMUNICATION_SCENARIOS))
        for fieldset, scenario in zip(fieldsets, COMMUNICATION_SCENARIOS, strict=True):
            with self.subTest(code=scenario.code):
                self.assertIn(f">{scenario.prompt}</legend>", fieldset)
                labels = re.findall(
                    rf'<label><input type="radio" name="{scenario.code}">'
                    r"<span>([^<]+)</span></label>",
                    fieldset,
                )
                self.assertEqual(labels, [option.label for option in scenario.options])

    # JavaScript off: all of it is already there and nothing hides it. Each explanation sits under
    # its own option's words.
    def test_server_sends_every_explanation_with_its_option_and_hides_none(self):
        for fieldset, scenario in zip(self._fieldsets(), COMMUNICATION_SCENARIOS, strict=True):
            with self.subTest(code=scenario.code):
                found = re.findall(
                    r"<li><strong[^>]*>([^<]+)</strong><p[^>]*>([^<]+)</p></li>", fieldset
                )
                self.assertEqual(
                    found, [(option.label, option.explanation) for option in scenario.options]
                )
                self.assertNotRegex(fieldset, r"\shidden[\s>]")

    # One live region a question, empty at first, to read the new explanation out.
    def test_each_scenario_has_one_polite_live_region(self):
        for fieldset in self._fieldsets():
            self.assertRegex(fieldset, r'<div [^>]*aria-live="polite"[^>]*></div>')
            self.assertEqual(fieldset.count("aria-live"), 1)

    def test_script_loads_deferred(self):
        self.assertRegex(self.content, r'<script defer src="[^"]*screening/pick-explain\.js')

    # Today's scenarios have no subheads; one that did would sit at h3, under this section's h2.
    def test_a_scenario_subhead_would_be_an_h3(self):
        scenario = COMMUNICATION_SCENARIOS[0]
        option = replace(scenario.options[0], try_saying=("一句話",))
        with patch(
            "screening.views.home.COMMUNICATION_SCENARIOS",
            (replace(scenario, options=(option,)),),
        ):
            content = self.client.get(self.url).content.decode()
        self.assertIn(">可以試的說法</h3>", content)

    # Nothing is scored and nothing is sent: no form to submit, no verdict on the page.
    def test_no_form_score_or_verdict(self):
        self.assertNotIn("<form", self.section)
        self.assertNotIn("<button", self.section)
        text = re.sub(r"<[^>]+>", "", self.section)
        self.assertNotRegex(text, r"答對|答錯|正確|錯誤|分數|總分|得分")

    def test_sources_and_checked_date_under_the_page_sources(self):
        sources = self._sources()
        start = sources.index("<h3>遇到這些情況，您會怎麼做？</h3>")
        group = sources[start : sources.index("<h3>", start + 1)]
        self.assertIn(
            '<a href="https://www.asha.org/about/press-room/articles/'
            'tips-for-communicating-with-someone-who-has-hearing-loss/">'
            "美國聽語學會（ASHA）〈Tips for Communicating With Someone Who Has Hearing Loss〉</a>",
            group,
        )
        self.assertIn(
            '<a href="https://www.hearingloss.org/managing-hearing-loss/hearing-loss-101/'
            'communication-tips/">美國聽損協會（HLAA）〈Communication Tips〉</a>',
            group,
        )
        self.assertIn("情境題內容查核於 2026/11/06。", group)

    def test_visitor_and_signed_in_user_get_the_same_section(self):
        self.client.force_login(consented_user(username="scenario_user"))
        content = self.client.get(self.url).content.decode()
        self.assertIn(self.section, content)


class FamilyReluctantTests(SignsInWithARecord, TestCase):
    """#429 (spec #426): 長輩不肯去怎麼說, as the server sends it. What the script does with it is
    in pick-explain.test.js and e2e.main_flow.FamilyReluctantTest."""

    # Written out: each situation's next steps, independent of the definition.
    NEXT_STEPS = (
        ["/questionnaire_list"],
        ["/questionnaire_list", "/audiograms/new"],
        ["/guide"],
    )

    def setUp(self):
        self.url = reverse("family_reluctant")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.content = response.content.decode()
        self.main = _main(self.content)

    def _items(self):
        start = self.main.index("<ul", self.main.index("<fieldset"))
        return re.findall(
            r"<li><strong.*?</li>\s*(?=<li><strong|</ul>\s*<div)", self.main[start:], re.S
        )

    def test_address_is_family_reluctant(self):
        self.assertEqual(self.url, "/family/reluctant")

    def test_page_has_one_heading_its_title_and_the_learn_tab(self):
        self.assertEqual(re.findall(r"<h1[^>]*>([^<]*)</h1>", self.content), ["長輩不肯去怎麼說"])
        self.assertRegex(self.content, r"<title>\s*長輩不肯去怎麼說｜聽伴\s*</title>")  # noqa: RUF001
        nav = test_pages.RedesignLayoutTests.NAV.search(self.content).group()
        self.assertEqual(
            re.findall(r'aria-current="page"[^>]*>.*?<span>([^<]+)</span>', nav, re.S),
            ["了解"],
        )

    # Radios to pick a situation, with its words all there and nothing hiding them: without
    # JavaScript they all show. One live region to read the picked one out.
    def test_server_sends_every_situation_in_full_with_a_live_region(self):
        self.assertEqual(
            re.findall(
                r'<label><input type="radio" name="[^"]+"><span>([^<]+)</span></label>', self.main
            ),
            ["他不承認聽不到", "他不想去檢查", "他不想戴助聽器"],
        )
        self.assertNotRegex(self.main, r"\shidden[\s>]")
        self.assertEqual(self.main.count('aria-live="polite"'), 1)
        self.assertRegex(self.content, r'<script defer src="[^"]*screening/pick-explain\.js')
        items = self._items()
        self.assertEqual(len(items), 3)
        for item, option in zip(items, RELUCTANT_SITUATIONS.options, strict=True):
            with self.subTest(option=option.label):
                self.assertIn(f">{option.label}</strong>", item)
                self.assertIn(option.explanation, item)
                self.assertIn(">可以試的說法</h2>", item)
                self.assertIn(">容易有反效果的說法</h2>", item)
                self.assertIn(">下一步</h2>", item)
                for words in option.try_saying + option.avoid_saying:
                    self.assertIn(f"<li>{words}</li>", item)

    # Screen readers walk a page by its headings, so none may skip a level under the h1.
    def test_headings_never_skip_a_level(self):
        levels = [int(level) for level in re.findall(r"<h([1-6])[\s>]", self.main)]
        self.assertEqual(levels[0], 1)
        for previous, level in pairwise(levels):
            self.assertLessEqual(level, previous + 1)

    # Each next step goes to a page that exists: open, or asking a visitor to log in first.
    def test_next_steps_link_to_pages_that_exist(self):
        items = self._items()
        for item, expected in zip(items, self.NEXT_STEPS, strict=True):
            hrefs = re.findall(r'<a class="link-card[^"]*" href="([^"]*)"', item)
            self.assertEqual(hrefs, expected)
        self.assertEqual(self.client.get("/guide").status_code, 200)
        for path in ("/questionnaire_list", "/audiograms/new"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login", response["Location"])

    def test_foot_has_sources_checked_date_and_the_way_back(self):
        foot = self.main[self.main.index("</fieldset>") :]
        self.assertIn('id="sources-title"', foot)
        for title, url in RELUCTANT_SOURCES:
            with self.subTest(url=url):
                self.assertIn(f'<a href="{url}">{title}</a>', foot)
        self.assertIn("內容查核於 2026/11/06。", foot)
        self.assertRegex(foot, r'<a [^>]*href="/family"[^>]*>回到家人專區</a>')

    def test_signed_in_user_gets_the_same_page_without_their_data(self):
        self.sign_in_with_a_record("reluctant_private")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertEqual(_main(content), self.main)
        self.assert_shows_no_record(content, "reluctant_private")

    def test_user_without_consent_can_read_it(self):
        self.client.force_login(User.objects.create_user(username="reluctant_old"))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    # Reads no one's data, so it can stay public: nothing in the view touches request.user.
    def test_view_never_reads_the_user(self):
        source = inspect.getsource(family.family_reluctant)
        self.assertNotIn("request.user", source)
        self.assertNotIn("login_required", source)
        self.assertEqual(self.client.get(self.url).status_code, 200)
