"""#431 (spec #426): 補助檢核. The rules on their own, each answer of batch-2-wording.md section 2
and all 720 combinations, then the page. Filling it in a real browser is in
e2e.main_flow.FamilySubsidyCheckTest."""

import inspect
import re
from datetime import date
from itertools import pairwise, product

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from screening import models
from screening import subsidy_check as rules
from screening.models import Consent, Submission, User
from screening.subsidy_check import check
from screening.tests import test_family_zone, test_pages
from screening.tests.helpers import consented_user
from screening.views import family

# Written out, not read from the module, so a slip in the definition shows.
CAN_APPLY = "可以去申請，是否補助以主管機關核定為準。"
NOTHING_MISSING = "目前沒有看到缺的項目，是否補助以主管機關核定為準。"
SEE_BELOW = "下面這些要先辦好或確認。"
NO_NOTICE_REMINDER = "沒核定就先買的不補助。請向戶籍所在地公所確認實際情況。"
BUY_AFTER_NOTICE = "一定要先拿到核定通知再買，沒核定就先買的不補助。"
REAPPLY = "滿 4 年可再申請（12 歲以下每 2 年）。"
SIMPLE_TYPE_REMINDER = "如果再次申請的是簡易型，不需要重新評估。"
DEADLINES = ("期限試算", "/family/visits/deadlines")


def _answers(**changes):
    """Everything in place and not yet applied: the one case where 可以去申請 shows."""
    return {
        "certificate": rules.HEARING,
        "residence": rules.YES,
        "progress": rules.HAS_FORM,
        "purchase": rules.NOT_BOUGHT,
        "previous": rules.NEVER,
        **changes,
    }


def _words(items):
    return [item.words for item in items]


def _links(items):
    return [(link.words, link.url) for item in items for link in item.links]


def _every_answer_set():
    names = [question.name for question in rules.QUESTIONS]
    for values in product(*(dict(q.choices) for q in rules.QUESTIONS)):
        yield dict(zip(names, values, strict=True))


def _all_words(result):
    return [result.headline, *(words for _, items in result.groups for words in _words(items))]


class SubsidyQuestionsTests(SimpleTestCase):
    def test_five_questions_in_the_reviewed_words(self):
        self.assertEqual(
            [(q.label, [words for _, words in q.choices]) for q in rules.QUESTIONS],
            [
                (
                    "申請的人有哪一種身心障礙證明？",
                    [
                        "聽覺機能（第二類 b230、s260，或舊制 02）",
                        "中度以上視覺障礙",
                        "上面兩種都沒有",
                        "不確定",
                    ],
                ),
                ("最近一年，申請的人在國內住超過 183 天嗎？", ["是", "否", "不確定"]),
                (
                    "九號表和核定通知辦到哪裡了？",
                    [
                        "還沒有九號表",
                        "有九號表，還沒到公所申請",
                        "已經到公所申請，在等核定通知",
                        "已經收到核定通知",
                        "不確定",
                    ],
                ),
                ("助聽器買了嗎？", ["還沒買", "已經買了", "不確定"]),
                (
                    "以前領過這項助聽器補助嗎？",
                    ["沒有", "領過，已滿 4 年（12 歲以下滿 2 年）", "領過，還沒滿", "不確定"],
                ),
            ],
        )


class SubsidyRulesTests(SimpleTestCase):
    """Each row of the draft's table, and the three first sentences."""

    def test_everything_in_place_says_one_can_apply_with_the_next_step(self):
        result = check(_answers())
        self.assertEqual(result.headline, CAN_APPLY)
        self.assertEqual(result.missing, ())
        self.assertEqual(result.to_confirm, ())
        self.assertEqual(
            _words(result.next_steps),
            [
                "帶申請表、身分證正本和九號表，到戶籍所在地的公所申請，也可以線上申請。"
                "九號表 3 個月內有效。"
            ],
        )
        self.assertEqual(_links(result.next_steps), [DEADLINES])

    def test_applied_or_notice_with_nothing_missing_says_nothing_is_missing(self):
        for progress in (rules.APPLIED, rules.NOTICE):
            with self.subTest(progress=progress):
                self.assertEqual(check(_answers(progress=progress)).headline, NOTHING_MISSING)

    def test_vision_certificate_is_to_be_confirmed_for_the_better_ear(self):
        result = check(_answers(certificate=rules.VISION))
        self.assertEqual(result.headline, SEE_BELOW)
        self.assertEqual(_words(result.to_confirm), ["好的那一耳聽力損失是否大於 40 dB。"])
        self.assertEqual(result.missing, ())

    def test_no_certificate_is_missing_with_how_to_apply_for_assessment(self):
        result = check(_answers(certificate=rules.NEITHER))
        self.assertEqual(result.headline, SEE_BELOW)
        self.assertEqual(
            _words(result.missing),
            [
                "要有聽覺機能的身心障礙證明，或中度以上視覺障礙且好的那一耳聽力損失大於 40 dB，"
                "才能申請這項補助。"
            ],
        )
        self.assertEqual(
            _words(result.next_steps)[0],
            "到戶籍所在縣市的公所申請身障鑑定，再帶公所給的鑑定表到鑑定醫院。",
        )
        self.assertEqual(
            _links(result.next_steps[:1]),
            [
                ("怎麼申請鑑定", "/guide/assessment#apply-title"),
                ("沒有身障證明時", "/guide/form-9#without-certificate"),
            ],
        )

    def test_unsure_certificate_is_to_be_confirmed(self):
        result = check(_answers(certificate=rules.UNSURE))
        self.assertEqual(result.headline, SEE_BELOW)
        self.assertEqual(
            _words(result.to_confirm), ["有沒有上面兩種身心障礙證明，可以問戶籍所在地公所。"]
        )
        self.assertEqual(result.missing, ())

    def test_residence_no_is_missing_and_unsure_is_to_be_confirmed(self):
        no = check(_answers(residence=rules.NO))
        self.assertEqual(
            _words(no.missing),
            ["最近一年要在國內住超過 183 天。實際情況請向戶籍所在地公所確認。"],
        )
        unsure = check(_answers(residence=rules.UNSURE))
        self.assertEqual(_words(unsure.to_confirm), ["最近一年在國內是否住超過 183 天。"])
        self.assertEqual(unsure.missing, ())

    def test_no_form_9_is_missing_and_never_says_one_can_apply(self):
        result = check(_answers(progress=rules.NO_FORM))
        self.assertEqual(result.headline, SEE_BELOW)
        self.assertEqual(
            _words(result.missing),
            ["九號表：找聽力師或縣市輔具中心做評估。九號表 3 個月內有效。"],
        )
        self.assertEqual(_links(result.missing), [("九號表找誰開", "/guide/form-9#issuer-title")])

    def test_waiting_for_the_notice_says_how_long_it_takes(self):
        result = check(_answers(progress=rules.APPLIED))
        self.assertEqual(_words(result.next_steps), ["主管機關收到評估報告後，10 天內會核定。"])

    def test_with_the_notice_it_gives_the_time_limits_and_their_links(self):
        result = check(_answers(progress=rules.NOTICE))
        self.assertEqual(
            _words(result.next_steps),
            [
                "收到核定通知後 6 個月內購買並請款。"
                "買中階型、進階型或雙對側傳聲型的人，配戴滿 1 個月到 3 個月內要做二十五號表。"
            ],
        )
        self.assertEqual(_links(result.next_steps), [DEADLINES, ("二十五號表", "/guide/form-25")])

    def test_unsure_progress_is_to_be_confirmed(self):
        result = check(_answers(progress=rules.UNSURE))
        self.assertEqual(result.headline, SEE_BELOW)
        self.assertEqual(
            _words(result.to_confirm), ["九號表和核定通知辦到哪裡了，可以問戶籍所在地公所。"]
        )

    def test_not_bought_yet_says_to_get_the_notice_first(self):
        for progress in (rules.NO_FORM, rules.HAS_FORM, rules.APPLIED, rules.NOTICE, rules.UNSURE):
            with self.subTest(progress=progress):
                result = check(_answers(progress=progress))
                self.assertEqual(_words(result.reminders), [BUY_AFTER_NOTICE])

    # No telling someone to go and apply beside 沒核定就先買的不補助: only that reminder stays.
    def test_bought_without_the_notice_leaves_only_the_reminder_of_question_3(self):
        for progress in (rules.NO_FORM, rules.HAS_FORM, rules.APPLIED):
            with self.subTest(progress=progress):
                result = check(_answers(progress=progress, purchase=rules.BOUGHT))
                self.assertEqual(result.headline, SEE_BELOW)
                self.assertEqual(_words(result.reminders), [NO_NOTICE_REMINDER])
                self.assertEqual(result.missing, ())
                self.assertEqual(result.to_confirm, ())
                self.assertEqual(result.next_steps, ())

    # Other questions' items stay: only question 3 goes quiet.
    def test_bought_without_the_notice_keeps_what_the_other_questions_add(self):
        result = check(
            _answers(
                certificate=rules.NEITHER,
                residence=rules.NO,
                progress=rules.NO_FORM,
                purchase=rules.BOUGHT,
                previous=rules.PAST_MINIMUM,
            )
        )
        self.assertEqual(len(result.missing), 2)
        self.assertNotIn("九號表：", "".join(_words(result.missing)))
        self.assertEqual(
            _words(result.next_steps),
            [
                "到戶籍所在縣市的公所申請身障鑑定，再帶公所給的鑑定表到鑑定醫院。",
            ],
        )
        self.assertEqual(_words(result.reminders), [NO_NOTICE_REMINDER])

    def test_bought_with_the_notice_asks_if_it_was_after_the_notice(self):
        result = check(_answers(progress=rules.NOTICE, purchase=rules.BOUGHT))
        self.assertEqual(result.headline, SEE_BELOW)
        self.assertEqual(
            _words(result.to_confirm),
            ["是不是收到核定通知之後才買的，而且在 6 個月內。沒核定就先買的不補助。"],
        )
        self.assertEqual(result.reminders, ())
        # Question 3's own next step still applies.
        self.assertEqual(_links(result.next_steps), [DEADLINES, ("二十五號表", "/guide/form-25")])

    def test_bought_with_progress_unsure_asks_about_the_notice(self):
        result = check(_answers(progress=rules.UNSURE, purchase=rules.BOUGHT))
        self.assertEqual(
            _words(result.to_confirm),
            [
                "九號表和核定通知辦到哪裡了，可以問戶籍所在地公所。",
                "有沒有核定通知，請向戶籍所在地公所確認。沒核定就先買的不補助。",
            ],
        )
        self.assertEqual(result.reminders, ())

    def test_unsure_whether_bought_is_to_be_confirmed(self):
        result = check(_answers(purchase=rules.UNSURE))
        self.assertEqual(result.headline, SEE_BELOW)
        self.assertEqual(
            _words(result.to_confirm),
            ["助聽器買了沒有。一定要先拿到核定通知再買，沒核定就先買的不補助。"],
        )
        self.assertEqual(result.reminders, ())

    def test_past_the_minimum_needs_no_new_assessment_for_the_basic_type(self):
        result = check(_answers(previous=rules.PAST_MINIMUM))
        self.assertEqual(result.headline, CAN_APPLY)
        self.assertEqual(_words(result.reminders)[-1], SIMPLE_TYPE_REMINDER)
        self.assertNotIn(SIMPLE_TYPE_REMINDER, _words(result.next_steps))

    def test_too_soon_since_the_last_subsidy_says_when_one_can_reapply(self):
        result = check(_answers(previous=rules.TOO_SOON))
        self.assertEqual(result.headline, SEE_BELOW)
        self.assertEqual(_words(result.missing), [REAPPLY])

    def test_unsure_about_the_last_subsidy_is_to_be_confirmed(self):
        result = check(_answers(previous=rules.UNSURE))
        self.assertEqual(result.headline, SEE_BELOW)
        self.assertEqual(_words(result.to_confirm), [f"上次領補助是哪一年。{REAPPLY}"])

    def test_groups_leave_out_the_empty_ones_in_the_order_shown(self):
        self.assertEqual([heading for heading, _ in check(_answers()).groups], ["提醒", "下一步"])
        worst = check(
            _answers(
                certificate=rules.NEITHER,
                residence=rules.UNSURE,
                purchase=rules.BOUGHT,
                progress=rules.UNSURE,
            )
        )
        self.assertEqual([heading for heading, _ in worst.groups], ["還缺", "要先確認", "下一步"])

    def test_the_result_cannot_be_changed_afterwards(self):
        result = check(_answers())
        with self.assertRaises(AttributeError):
            result.headline = "符合"


class SubsidyInvariantsTests(SimpleTestCase):
    """Over all 720 combinations, what must hold whatever the answers."""

    def test_there_are_720_combinations(self):
        self.assertEqual(sum(1 for _ in _every_answer_set()), 720)

    def test_no_result_ever_says_one_qualifies_or_names_a_family_member(self):
        for answers in _every_answer_set():
            text = "".join(_all_words(check(answers)))
            for words in ("符合", "可領", "一定拿得到", "您的家人"):
                self.assertNotIn(words, text, answers)

    def test_can_apply_shows_only_when_every_condition_is_in_place(self):
        seen = []
        for answers in _every_answer_set():
            if CAN_APPLY in _all_words(check(answers)):
                seen.append(answers)
        self.assertEqual(seen, [_answers(), _answers(previous=rules.PAST_MINIMUM)])

    def test_any_unsure_answer_keeps_the_first_sentence_at_see_below(self):
        for answers in _every_answer_set():
            if rules.UNSURE in answers.values():
                self.assertEqual(check(answers).headline, SEE_BELOW, answers)

    def test_each_unsure_question_adds_its_own_item(self):
        own_words = {
            "certificate": "有沒有上面兩種身心障礙證明",
            "residence": "最近一年在國內是否住超過 183 天",
            "progress": "九號表和核定通知辦到哪裡了",
            "purchase": "助聽器買了沒有",
            "previous": "上次領補助是哪一年",
        }
        for answers in _every_answer_set():
            to_confirm = "".join(_words(check(answers).to_confirm))
            for name, words in own_words.items():
                if answers[name] == rules.UNSURE:
                    self.assertIn(words, to_confirm, answers)

    def test_every_combination_has_a_first_sentence_from_the_three(self):
        for answers in _every_answer_set():
            self.assertIn(check(answers).headline, (CAN_APPLY, NOTHING_MISSING, SEE_BELOW), answers)

    def test_nothing_missing_shows_only_with_nothing_listed_to_do(self):
        for answers in _every_answer_set():
            result = check(answers)
            if result.headline in (CAN_APPLY, NOTHING_MISSING):
                self.assertEqual((result.missing, result.to_confirm), ((), ()), answers)
            else:
                self.assertTrue(result.missing or result.to_confirm or result.reminders, answers)

    # Owner, 2026-11-06: what is still missing comes first; applying or buying waits for it.
    def test_anything_missing_holds_back_applying_and_buying(self):
        for answers in _every_answer_set():
            result = check(answers)
            if result.missing:
                text = "".join(_words(result.next_steps))
                self.assertNotIn("帶申請表", text, answers)
                self.assertNotIn("購買並請款", text, answers)

    def test_steps_to_apply_and_buy_show_with_nothing_missing(self):
        for progress, words in ((rules.HAS_FORM, "帶申請表"), (rules.NOTICE, "購買並請款")):
            with self.subTest(progress=progress):
                self.assertIn(words, "".join(_words(check(_answers(progress=progress)).next_steps)))
                held = check(_answers(progress=progress, previous=rules.TOO_SOON))
                self.assertNotIn(words, "".join(_words(held.next_steps)))
                self.assertEqual(_words(held.missing), [REAPPLY])

    def test_past_the_minimum_with_no_form_9_says_if_for_the_simple_type(self):
        result = check(_answers(progress=rules.NO_FORM, previous=rules.PAST_MINIMUM))
        self.assertIn("九號表：", "".join(_words(result.missing)))
        self.assertEqual(_words(result.reminders)[-1], SIMPLE_TYPE_REMINDER)

    def test_bought_without_a_notice_has_no_simple_type_reminder(self):
        result = check(
            _answers(progress=rules.HAS_FORM, purchase=rules.BOUGHT, previous=rules.PAST_MINIMUM)
        )
        self.assertEqual(_words(result.reminders), [NO_NOTICE_REMINDER])

    def test_bought_without_a_notice_never_offers_question_3s_steps(self):
        for answers in _every_answer_set():
            if answers["purchase"] != rules.BOUGHT:
                continue
            if answers["progress"] not in (rules.NO_FORM, rules.HAS_FORM, rules.APPLIED):
                continue
            result = check(answers)
            self.assertEqual(result.headline, SEE_BELOW, answers)
            self.assertEqual(_words(result.reminders), [NO_NOTICE_REMINDER], answers)
            text = "".join(_all_words(result))
            for words in ("九號表：", "帶申請表", "10 天內會核定", "6 個月內購買"):
                self.assertNotIn(words, text, answers)


class SubsidyCheckPageTests(test_family_zone.SignsInWithARecord, TestCase):
    def setUp(self):
        self.url = reverse("family_subsidy_check")

    def _main(self, response):
        self.assertEqual(response.status_code, 200)
        return test_family_zone._main(response.content.decode())

    def _post(self, **answers):
        return self.client.post(self.url, answers)

    def _text(self, main):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", main))

    def _checked(self, main):
        """(name, value) of each radio that comes back chosen."""
        found = []
        for tag in re.findall(r"<input [^>]*>", main):
            if 'type="radio"' in tag and " checked" in tag:
                name = re.search(r'name="([^"]+)"', tag).group(1)
                found.append((name, re.search(r'value="([^"]+)"', tag).group(1)))
        return found

    def _result(self, main):
        return main[main.index('id="result-title"') : main.index("<form")]

    def test_address_is_under_the_visits_page(self):
        self.assertEqual(self.url, "/family/visits/subsidy")

    def test_page_has_one_heading_its_title_and_the_learn_tab(self):
        content = self.client.get(self.url).content.decode()
        self.assertEqual(re.findall(r"<h1[^>]*>([^<]*)</h1>", content), ["補助檢核"])
        self.assertRegex(content, r"<title>\s*補助檢核｜聽伴\s*</title>")  # noqa: RUF001
        nav = test_pages.RedesignLayoutTests.NAV.search(content).group()
        self.assertEqual(
            re.findall(r'aria-current="page"[^>]*>.*?<span>([^<]+)</span>', nav, re.S),
            ["了解"],
        )

    def test_opening_it_shows_the_questions_and_no_result_or_print_button(self):
        response = self.client.get(self.url)
        main = self._main(response)
        self.assertIn(
            "回答幾題，看申請助聽器補助還缺什麼。這裡不判斷能不能拿到補助，"
            "是否補助以主管機關核定為準。回答不會留下來。",
            main,
        )
        self.assertEqual(main.count("<fieldset"), 5)
        for question in rules.QUESTIONS:
            with self.subTest(question=question.name):
                self.assertRegex(main, rf"<legend[^>]*>.*?{re.escape(question.label)}</legend>")
                for _, words in question.choices:
                    self.assertIn(words, main)
        self.assertNotIn('id="result-title"', main)
        self.assertNotIn("print-button", response.content.decode())
        self.assertNotIn('id="error-summary"', main)

    def test_the_words_are_for_whoever_is_applying(self):
        text = self._text(self._main(self.client.get(self.url)))
        self.assertIn("申請的人", text)
        self.assertNotIn("您的家人", text)

    def test_the_answers_go_by_post_with_a_csrf_token_and_the_form_keeps_nothing(self):
        main = self._main(self.client.get(self.url))
        self.assertRegex(
            main, rf'<form [^>]*method="post" action="{self.url}" autocomplete="off"[^>]*>'
        )
        self.assertIn("csrfmiddlewaretoken", main)

    # Unanswered questions reach the page's own summary: a browser's required bubble would stop
    # the form from being sent, and differs from browser to browser.
    def test_no_radio_is_marked_required(self):
        self.assertNotIn(" required", self._main(self.client.get(self.url)))

    def test_sending_all_answers_shows_the_result_on_the_same_page(self):
        main = self._main(self._post(**_answers()))
        result = self._result(main)
        self.assertIn(CAN_APPLY, result)
        self.assertRegex(main, r"<h2[^>]*>檢核結果</h2>")
        self.assertIn('<p class="part-label">提醒</p>', result)
        self.assertIn('<p class="part-label">下一步</p>', result)
        self.assertNotIn(">還缺</p>", result)
        self.assertIn("一定要先拿到核定通知再買", result)
        self.assertIn("到戶籍所在地的公所申請", result)
        self.assertRegex(result, r'<a [^>]*href="/guide/form-9"')

    def test_missing_items_and_their_links_are_listed(self):
        main = self._main(self._post(**_answers(certificate=rules.NEITHER)))
        result = self._result(main)
        self.assertIn(SEE_BELOW, result)
        self.assertIn('<p class="part-label">還缺</p>', result)
        self.assertIn("才能申請這項補助", result)
        self.assertRegex(
            result, r'<a [^>]*href="/guide/assessment#apply-title"[^>]*>怎麼申請鑑定</a>'
        )
        self.assertRegex(
            result, r'<a [^>]*href="/guide/form-9#without-certificate"[^>]*>沒有身障證明時</a>'
        )

    # #469 (the #468 mockup): the sources follow the folded questions.
    def test_the_result_foot_has_the_form_9_link_sources_and_checked_date(self):
        main = self._main(self._post(**_answers(progress=rules.UNSURE)))
        self.assertRegex(
            self._result(main), r'<a [^>]*href="/guide/form-9"[^>]*>看九號表的流程</a>'
        )
        result = main[main.index("改答案，再檢核一次") :]
        self.assertIn("內容查核於 2026/10/23。", result)
        for url in (
            "https://law.moj.gov.tw/LawClass/LawAll.aspx?PCODE=D0050060",
            "https://law.moj.gov.tw/LawClass/LawGetFile.ashx?FileId=0000326887&amp;lan=C",
        ):
            with self.subTest(url=url):
                self.assertIn(f'<a href="{url}">', result)

    def test_sources_also_show_before_anything_is_sent(self):
        main = self._main(self.client.get(self.url))
        self.assertIn("內容查核於 2026/10/23。", main)
        self.assertIn("身心障礙者輔具費用補助辦法", main)

    def test_the_form_stays_under_the_result_with_the_answers_chosen(self):
        answers = _answers(residence=rules.UNSURE, previous=rules.TOO_SOON)
        main = self._main(self._post(**answers))
        self.assertLess(main.index('id="result-title"'), main.index("<form"))
        self.assertCountEqual(self._checked(main), answers.items())

    def test_every_answer_shown_on_the_page_keeps_clear_of_the_words_ruled_out(self):
        for question in rules.QUESTIONS:
            for value, _ in question.choices:
                with self.subTest(question=question.name, value=value):
                    text = self._text(self._main(self._post(**_answers(**{question.name: value}))))
                    for words in ("符合", "可領", "一定拿得到", "您的家人"):
                        self.assertNotIn(words, text)

    def test_links_in_the_results_lead_somewhere_real(self):
        seen = {rules.FORM_9_LINK}
        for answers in _every_answer_set():
            result = check(answers)
            seen.update(link for _, items in result.groups for item in items for link in item.links)
        self.assertEqual(len(seen), 6)
        for link in seen:
            with self.subTest(url=link.url):
                path, _, anchor = link.url.partition("#")
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                if anchor:
                    self.assertIn(f'id="{anchor}"', response.content.decode())

    def test_headings_never_skip_a_level_with_a_result(self):
        main = self._main(self._post(**_answers(certificate=rules.NEITHER)))
        levels = [int(level) for level in re.findall(r"<h([1-6])[\s>]", main)]
        self.assertEqual(levels[0], 1)
        for previous, level in pairwise(levels):
            self.assertLessEqual(level, previous + 1)

    def test_a_way_back_to_the_zone(self):
        for response in (self.client.get(self.url), self._post(**_answers())):
            self.assertRegex(self._main(response), r'<a [^>]*href="/family"[^>]*>回到家人專區</a>')

    # Only with a result, as there is nothing to print before.
    def test_print_button_and_its_script_come_with_a_result(self):
        response = self._post(**_answers())
        self.assertRegex(
            self._main(response),
            r'<p class="[^"]*no-print[^"]*">\s*'
            r'<button id="print-button" type="button"[^>]*>列印或存成 PDF</button>',
        )
        self.assertIn("screening/print-button.js", response.content.decode())

    # A question left out: the answer page's own way of pointing them out.
    def test_unanswered_questions_are_pointed_out_with_the_answers_kept(self):
        chosen = {"certificate": rules.VISION, "purchase": rules.BOUGHT}
        response = self._post(**chosen)
        main = self._main(response)
        summary = re.search(r'<div id="error-summary"[^>]*>.*?</div>', main, re.S).group()
        self.assertRegex(summary, r'^<div id="error-summary"[^>]*role="alert"')
        self.assertRegex(summary, r'^<div [^>]*tabindex="-1"[^>]*autofocus')
        self.assertIn("還有 3 題沒有回答，請看標示紅字的題目。", summary)
        self.assertEqual(
            re.findall(r'<a [^>]*href="#([^"]+)"[^>]*>([^<]+)</a>', summary),
            [
                ("question-2", "第 2 題"),
                ("question-3", "第 3 題"),
                ("question-5", "第 5 題"),
            ],
        )
        self.assertCountEqual(self._checked(main), chosen.items())
        self.assertEqual(main.count("這一題還沒有回答"), 3)
        for number in (2, 3, 5):
            self.assertRegex(main, rf'<fieldset id="question-{number}"[^>]*tabindex="-1"')
        self.assertNotIn('id="result-title"', main)
        self.assertNotIn("print-button", response.content.decode())

    def test_each_marked_question_names_its_error_for_screen_readers(self):
        main = self._main(self._post(certificate=rules.VISION))
        self.assertRegex(
            main, r'<fieldset id="question-2"[^>]*aria-describedby="id_residence_error"'
        )
        self.assertIn('id="id_residence_error"', main)
        self.assertNotRegex(main, r'<fieldset id="question-1"[^>]*aria-describedby')

    def test_an_answer_not_on_the_list_counts_as_unanswered(self):
        main = self._main(self._post(**_answers(previous="eligible")))
        self.assertIn("還有 1 題沒有回答", main)
        self.assertNotIn('id="result-title"', main)

    def test_every_response_is_marked_never_to_be_stored(self):
        for response in (
            self.client.get(self.url),
            self._post(**_answers()),
            self._post(certificate=rules.VISION),
        ):
            self.assertIn("no-store", response.get("Cache-Control", ""))

    # Nothing of the answers is kept: no database at all for a visitor, no session, nothing in the
    # address.
    def test_sending_keeps_nothing(self):
        before = (Submission.objects.count(), User.objects.count())
        with self.assertNumQueries(0):
            response = self._post(**_answers(certificate=rules.NEITHER))
        self.assertEqual((Submission.objects.count(), User.objects.count()), before)
        self.assertEqual(response.request["QUERY_STRING"], "")
        self.assertEqual(response.request["PATH_INFO"], self.url)
        self.assertNotIn("sessionid", response.cookies)
        self.assertEqual(dict(self.client.session), {})

    def test_a_visitor_can_send_it_through_the_csrf_check(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url, _answers()).status_code, 403)
        page = client.get(self.url).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
        response = client.post(self.url, {**_answers(), "csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 200)
        self.assertIn(CAN_APPLY, response.content.decode())

    def test_user_without_consent_can_open_and_send_it(self):
        self.client.force_login(User.objects.create_user(username="subsidy_old"))
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertIn(CAN_APPLY, self._post(**_answers()).content.decode())

    def test_signed_in_user_gets_the_same_result_without_their_data(self):
        visitor = self._post(**_answers()).content.decode()
        self.sign_in_with_a_record("subsidy_private")
        content = self._post(**_answers()).content.decode()
        token = re.compile(r'name="csrfmiddlewaretoken" value="[^"]+"')
        self.assertEqual(
            token.sub("", test_family_zone._main(content)),
            token.sub("", test_family_zone._main(visitor)),
        )
        self.assert_shows_no_record(content, "subsidy_private")

    # Reads no one's data, so it can stay public: nothing in the view touches request.user.
    def test_view_never_reads_the_user(self):
        source = inspect.getsource(family.family_subsidy_check)
        self.assertNotIn("request.user", source)
        self.assertNotIn("login_required", source)


class SubsidyCheckEntriesTests(TestCase):
    # #469 (the #468 mockup A): under the checklist, which comes first.
    def test_visits_page_has_a_card_under_the_checklist(self):
        main = test_family_zone._main(self.client.get(reverse("family_visits")).content.decode())
        self.assertIn(
            ("/family/visits/subsidy", "clipboard", "補助檢核", "回答幾題，看還缺什麼"),
            test_family_zone.ENTRY.findall(main),
        )
        self.assertLess(main.index('id="checklist-title"'), main.index("/family/visits/subsidy"))

    def test_the_form_9_chapter_links_to_it_after_its_first_paragraph(self):
        main = test_family_zone._main(
            self.client.get(reverse("guide_chapter", args=["form-9"])).content.decode()
        )
        self.assertRegex(
            main,
            r"帶著它向戶籍所在地的公所申請助聽器補助。</p>\s*"
            r'<p>想知道還缺什麼？可以用<a [^>]*href="/family/visits/subsidy"[^>]*>'
            r"補助檢核</a>。</p>",
        )


class PrivacyCookieSentenceTests(TestCase):
    """#431: the visitor's form needs Django's CSRF cookie, so the note says so. A minor fix as in
    ADR 0014: the date moves and nobody agrees again."""

    def test_it_names_the_cookie_the_form_needs(self):
        response = self.client.get(reverse("privacy"))
        self.assertContains(
            response, "本站只用登入和送出表單需要的 cookie（小型的瀏覽器紀錄），沒有追蹤或廣告。"
        )
        self.assertNotContains(response, "本站只用登入需要的 cookie")

    def test_the_date_moved(self):
        self.assertGreaterEqual(models.PRIVACY_UPDATED_ON, date(2026, 11, 6))

    def test_someone_who_agreed_to_this_version_is_not_asked_again(self):
        user = consented_user(username="agreed_already")
        self.assertEqual(Consent.objects.get(user=user).version, models.CONSENT_VERSION)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("questionnaire_list")).status_code, 200)
