"""#469 (spec #453, the #468 mockup): the family zone redesigned. 怎麼跟他說話 is a page of its own
with a line drawing a tip (H3); the zone's home page keeps its list, 傳給家人 and the red 馬上就醫
box, with 陪伴配戴助聽器 and the sources folded. The reviewed words stay as they were."""

import re

from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from screening.family_deadlines import DEADLINE_CHECKED_ON, DEADLINE_SOURCES
from screening.family_zone import (
    COMMUNICATION_CHECKED_ON,
    COMMUNICATION_SCENARIOS,
    HEARING_AID_CHECKED_ON,
    HEARING_AID_SOURCES,
    RELUCTANT_CHECKED_ON,
    RELUCTANT_SOURCES,
    VISIT_CHECKED_ON,
    VISIT_SOURCES,
)
from screening.models import ReportShare, User
from screening.subsidy_check import SUBSIDY_CHECKED_ON, SUBSIDY_SOURCES
from screening.tests.helpers import consented_user
from screening.tests.test_family_guide import TIPS, TOPICS
from screening.tests.test_family_zone import (
    AID_NOTE,
    ENTRY,
    HEARING_AIDS_NOTE,
    INTRO,
    RELUCTANT_NOTE,
    TALK_NOTE,
    URGENT,
    VISITS_NOTE,
)

TALK_TITLE = "怎麼跟聽損的家人說話"
SCENARIOS_TITLE = "遇到這些情況，您會怎麼做？"
SCENARIOS_LEAD = "選您平常的做法，看看說明。這裡沒有對錯，也不會留下紀錄，可以改選。"
DISCLAIMER = (
    "這些是一般性的建議，不能取代醫師或聽力師的診斷。有任何疑問，請和您的醫師或聽力師討論。"
)
# A tip: its drawing, then its bold point and the rest of its words.
TIP = re.compile(
    r'<li><svg class="care-drawing" viewBox="0 0 240 160" aria-hidden="true" focusable="false">'
    r'.*?</svg>\s*<strong class="tip-point[^"]*">([^<]+)</strong>([^<]+)</li>',
    re.S,
)
# A solid button, its attributes and words.
SOLID = r'<(?:a|button)([^>]*class="btn btn-primary[^"]*"[^>]*)>([^<]*)<'
# 出處 folded into a row like a result page's 看完整說明 (the #468 mockup).
SOURCES_FOLD = re.compile(r'<details class="result-details family-sources">(.*?)</details>', re.S)


def _main(content):
    return content[content.index("<main") : content.index("</main>")]


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))


class FamilyTalkPageTests(TestCase):
    """怎麼跟他說話 on its own page (#469): the nine reviewed tips, each under a line drawing, then
    the scenarios, the disclaimer, back to the zone and the sources."""

    def setUp(self):
        self.url = reverse("family_talk")

    def _page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_its_address_is_under_the_zone(self):
        self.assertEqual(self.url, "/family/talk")

    def test_the_nine_tips_each_under_a_drawing_with_the_reviewed_words(self):
        main = _main(self._page())
        self.assertEqual(re.findall(r"<h1[^>]*>([^<]*)</h1>", main), [TALK_TITLE])
        self.assertIn(INTRO, main)
        self.assertEqual(tuple(TIP.findall(main)), TIPS["talk-title"])
        # Nine drawings, all different, none read out.
        drawings = re.findall(r'<svg class="care-drawing".*?</svg>', main, re.S)
        self.assertEqual(len(drawings), 9)
        self.assertEqual(len(set(drawings)), 9)

    def test_scenarios_follow_the_tips_with_every_explanation(self):
        main = _main(self._page())
        title = re.search(rf'<h2 id="scenarios-title"[^>]*>{SCENARIOS_TITLE}</h2>', main)
        self.assertIsNotNone(title)
        self.assertLess(main.index("耐心，也讓他參與"), title.start())
        text = _text(main)
        self.assertIn(SCENARIOS_LEAD, text)
        for scenario in COMMUNICATION_SCENARIOS:
            with self.subTest(prompt=scenario.prompt):
                self.assertIn(scenario.prompt, text)
                for option in scenario.options:
                    self.assertIn(option.label, text)
                    self.assertIn(option.explanation, text)

    def test_disclaimer_back_button_then_sources_folded_with_the_date_outside(self):
        main = _main(self._page())
        back = re.search(
            r'<a class="btn btn-outline-primary btn-lg w-full" href="/family">回到家人專區</a>',
            main,
        )
        self.assertIsNotNone(back)
        fold = SOURCES_FOLD.search(main)
        self.assertIsNotNone(fold)
        self.assertLess(main.index(DISCLAIMER), back.start())
        self.assertLess(back.start(), fold.start())
        self.assertIn("出處", _text(fold.group(1).split("</summary>")[0]))
        for wording, url in TOPICS[TALK_TITLE]:
            with self.subTest(url=url):
                self.assertIn(f'href="{url}"', fold.group(1))
                self.assertIn(wording, _text(fold.group(1)))
        checked = f"情境題內容查核於 {COMMUNICATION_CHECKED_ON:%Y/%m/%d}。"
        self.assertNotIn(checked, fold.group(1))
        self.assertIn(checked, main[fold.end() :])

    def test_no_solid_button(self):
        self.assertNotIn("btn-primary", _main(self._page()))

    def test_anyone_reads_it_and_it_marks_the_learn_tab(self):
        self._page()
        self.client.force_login(User.objects.create_user(username="talk_no_consent"))
        content = self._page()
        self.assertRegex(content, r"<title>\s*怎麼跟聽損的家人說話｜聽伴\s*</title>")  # noqa: RUF001
        self.assertRegex(content, r'aria-current="page"[^>]*>\s*<svg.*?</svg>\s*<span>了解</span>')


class FamilyZoneHomeRedesignTests(TestCase):
    """The zone's home page (the #468 mockup A): the list with 陪伴配戴助聽器 folded among its
    rows, then 傳給家人, then the red 馬上就醫 box, never folded; the sources folded at the end."""

    def setUp(self):
        response = self.client.get(reverse("family_guide"))
        self.assertEqual(response.status_code, 200)
        self.main = _main(response.content.decode())

    def _entries(self):
        start = self.main.index('aria-label="專區內容"')
        return self.main[start : self.main.index("</nav>", start)]

    def test_list_rows_with_talk_on_its_own_page_and_no_urgent_row(self):
        self.assertEqual(
            ENTRY.findall(self._entries()),
            [
                ("/family/talk", "family", "怎麼跟他說話", TALK_NOTE),
                ("/family/visits", "clipboard", "陪診與代辦", VISITS_NOTE),
                ("/family/reluctant", "question", "長輩不肯去怎麼說", RELUCTANT_NOTE),
                ("/family/hearing-aids", "ear", "助聽器", HEARING_AIDS_NOTE),
            ],
        )
        self.assertNotIn('href="#urgent-title"', self.main)
        # The nine tips and the scenarios moved to their own page.
        for point, _ in TIPS["talk-title"]:
            with self.subTest(point=point):
                self.assertNotIn(point, self.main)
        self.assertNotIn('id="scenarios-title"', self.main)
        self.assertNotIn('id="talk-title"', self.main)

    def test_aid_tips_folded_in_the_last_row_with_the_reviewed_words(self):
        fold = re.search(
            r'<details id="aid-title" class="result-details" data-jump-box>(.*?)</details>',
            self._entries(),
            re.S,
        )
        self.assertIsNotNone(fold)
        summary, body = fold.group(1).split("</summary>")
        self.assertIn('data-icon="ear"', summary)
        self.assertEqual(
            re.findall(r'<span class="[^"]*">([^<]+)</span>', summary), ["陪伴配戴助聽器", AID_NOTE]
        )
        found = re.findall(r'<li><strong class="tip-point[^"]*">([^<]+)</strong>([^<]+)</li>', body)
        self.assertEqual(tuple(found), TIPS["aid-title"])
        self.assertNotIn("<details", self.main[: self.main.index('aria-label="專區內容"')])

    def test_share_then_the_urgent_box_open_then_the_rest_in_order(self):
        markers = (
            "<h1",
            INTRO,
            'aria-label="專區內容"',
            'id="share-button"',
            'id="copy-link"',
            'id="urgent-title"',
            DISCLAIMER,
            "可以複製這個網址傳給家人：",
            '<details class="result-details family-sources">',
        )
        positions = [self.main.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))
        start = self.main.index('id="urgent-title"')
        box = self.main[
            self.main.rindex("<section", 0, start) : self.main.index("</section>", start)
        ]
        self.assertNotIn("<details", box)
        for words in URGENT:
            with self.subTest(words=words):
                self.assertIn(words, _text(box))

    # 傳給家人 is the page's one solid button; 複製網址 takes its place where there is no share
    # sheet, so the two never show together (copy-link.js, share-button.js).
    def test_the_only_solid_buttons_are_share_and_its_stand_in(self):
        solid = re.findall(
            r'<(?:a|button)([^>]*class="btn btn-primary[^"]*"[^>]*)>([^<]*)<', self.main
        )
        self.assertEqual(
            [(re.search(r'id="([^"]+)"', attrs).group(1), words) for attrs, words in solid],
            [("share-button", "傳給家人"), ("copy-link", "複製網址")],
        )

    def test_sources_of_what_stays_on_the_page_folded(self):
        fold = SOURCES_FOLD.search(self.main)
        self.assertIsNotNone(fold)
        for topic in ("陪伴配戴助聽器", "什麼時候要馬上就醫"):
            for wording, url in TOPICS[topic]:
                with self.subTest(url=url):
                    self.assertIn(f'href="{url}"', fold.group(1))
                    self.assertIn(wording, _text(fold.group(1)))
        for _, url in TOPICS[TALK_TITLE]:
            self.assertNotIn(url, self.main)


class TalkLinksTests(TestCase):
    """Every link that went to the guide's #talk-title now goes to the page of its own (#469)."""

    def test_no_page_links_to_the_old_anchor(self):
        share = ReportShare.objects.create(user=consented_user(username="talk_sharer"))
        pages = (
            reverse("family_guide"),
            reverse("learn"),
            reverse("privacy"),
            reverse("shared_report", args=[share.token]),
            reverse("family_hearing_aids"),
        )
        for url in pages:
            with self.subTest(url=url):
                content = self.client.get(url).content.decode()
                self.assertNotIn("#talk-title", content)
                self.assertNotIn("#scenarios-title", content)

    def test_shared_report_sends_family_to_the_talk_page(self):
        share = ReportShare.objects.create(user=consented_user(username="talk_sharer2"))
        content = self.client.get(reverse("shared_report", args=[share.token])).content.decode()
        self.assertIn(f'href="{reverse("family_talk")}"', content)

    def test_hearing_aids_page_sends_family_to_the_talk_page(self):
        content = self.client.get(reverse("family_hearing_aids")).content.decode()
        self.assertIn(f'href="{reverse("family_talk")}"', content)


class FamilySubpagesTests(TestCase):
    """The zone's other pages (the #468 mockup): the sources folded with their check date outside,
    and 點選看說明's 可以試的說法 and the like bold labels, not section titles."""

    # (page, its sources, its check date)
    PAGES = (
        ("family_reluctant", RELUCTANT_SOURCES, RELUCTANT_CHECKED_ON),
        ("family_hearing_aids", HEARING_AID_SOURCES, HEARING_AID_CHECKED_ON),
        ("family_visits", VISIT_SOURCES, VISIT_CHECKED_ON),
        ("family_deadlines", DEADLINE_SOURCES, DEADLINE_CHECKED_ON),
        ("family_subsidy_check", SUBSIDY_SOURCES, SUBSIDY_CHECKED_ON),
    )

    def _main(self, name):
        response = self.client.get(reverse(name))
        self.assertEqual(response.status_code, 200)
        return _main(response.content.decode())

    def test_sources_folded_and_the_check_date_under_them(self):
        for name, sources, day in self.PAGES:
            with self.subTest(page=name):
                main = self._main(name)
                fold = SOURCES_FOLD.search(main)
                self.assertIsNotNone(fold)
                self.assertNotIn('id="sources-title"', main)
                for title, url in sources:
                    self.assertIn(f'<li><a href="{escape(url)}">{title}</a></li>', fold.group(1))
                checked = f'<p class="guide-checked">內容查核於 {day:%Y/%m/%d}。</p>'
                self.assertNotIn(checked, fold.group(1))
                self.assertIn(checked, main[fold.end() :])

    def test_pick_explain_parts_are_labels_under_the_one_page_title(self):
        main = self._main("family_reluctant")
        self.assertEqual(re.findall(r"<h\d[^>]*>([^<]*)</h\d>", main), ["長輩不肯去怎麼說"])
        for label in ("可以試的說法", "容易有反效果的說法", "下一步"):
            with self.subTest(label=label):
                self.assertIn(f'<p class="part-label">{label}</p>', main)


def _solid(main):
    """The words of each solid (filled) button on the page."""
    return [words for _, words in re.findall(SOLID, main)]


class VisitsRedesignTests(TestCase):
    """陪診與代辦 (the #468 mockup A): the checklist first with 列印或存成 PDF under 要帶的東西,
    the two tools below the list."""

    def test_checklist_then_print_then_questions_then_tools(self):
        response = self.client.get(reverse("family_visits"))
        main = _main(response.content.decode())
        markers = (
            "<h1",
            'id="checklist-title"',
            "勾選不會留下，可以列印帶去。",
            "要帶的東西",
            'id="print-button"',
            "想問聽力師的問題",
            "提醒：要申請身障補助",
            f'href="{reverse("family_subsidy_check")}"',
            f'href="{reverse("family_deadlines")}"',
            "回到家人專區",
            '<details class="result-details family-sources">',
        )
        positions = [main.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(_solid(main), ["列印或存成 PDF"])


class SubsidyCheckRedesignTests(TestCase):
    """補助檢核 (the #468 mockup): sent, the result comes first with the page's one solid button;
    the five questions fold into 改答案，再檢核一次 (a draft), their 送出 a blue outline."""

    ANSWERS = {  # noqa: RUF012
        "certificate": "neither",
        "residence": "yes",
        "progress": "no_form",
        "purchase": "not_bought",
        "previous": "unsure",
    }

    def setUp(self):
        self.url = reverse("family_subsidy_check")

    def test_before_sending_the_questions_are_open_and_send_is_solid(self):
        main = _main(self.client.get(self.url).content.decode())
        self.assertNotIn("改答案，再檢核一次", main)
        self.assertEqual(_solid(main), ["送出"])

    def test_sent_the_questions_fold_under_the_result_and_print_is_the_one_solid_button(self):
        response = self.client.post(self.url, self.ANSWERS)
        main = _main(response.content.decode())
        self.assertIn('id="result-title"', main)
        fold = re.search(r'<details class="result-details no-print">(.*?)</details>', main, re.S)
        self.assertIsNotNone(fold)
        summary, body = fold.group(1).split("</summary>", 1)
        self.assertIn("改答案，再檢核一次", summary)
        self.assertIn("<form", body)
        self.assertRegex(body, r'<button class="btn btn-outline-primary[^"]*" type="submit">送出')
        self.assertEqual(_solid(main), ["列印或存成 PDF"])
        markers = ('id="result-title"', 'id="print-button"', "改答案，再檢核一次", "出處")
        positions = [main.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))
        # The result's groups are bold labels, not section titles.
        self.assertIn('<p class="part-label">還缺</p>', main)
        self.assertNotRegex(main, r"<h3[^>]*>還缺</h3>")

    def test_unanswered_the_questions_stay_open(self):
        response = self.client.post(self.url, {**self.ANSWERS, "previous": ""})
        main = _main(response.content.decode())
        self.assertIn('id="error-summary"', main)
        self.assertNotIn("改答案，再檢核一次", main)
        self.assertEqual(_solid(main), ["送出"])


class DeadlinesRedesignTests(TestCase):
    """期限試算: 試算 is the one solid button until there are dates; then 列印或存成 PDF is, and
    試算 turns a blue outline (the #468 mockup's notes)."""

    def setUp(self):
        self.url = reverse("family_deadlines")

    def test_before_working_out_only_the_submit_is_solid(self):
        main = _main(self.client.get(self.url).content.decode())
        self.assertEqual(_solid(main), ["試算"])

    def test_with_dates_print_is_solid_and_the_submit_an_outline(self):
        main = _main(self.client.post(self.url, {"fitted_on": "2026-01-31"}).content.decode())
        self.assertEqual(_solid(main), ["列印或存成 PDF"])
        self.assertRegex(main, r'<button class="btn btn-outline-primary[^"]*"[^>]*>試算</button>')
