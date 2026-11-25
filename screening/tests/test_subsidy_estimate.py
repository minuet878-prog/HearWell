"""#775 (spec #774): 補助引導與試算. The rules on their own, then the page at /guide/subsidy.
Walking it in a real browser is in e2e.main_flow.SubsidyEstimateTest."""

import inspect
import re
from itertools import pairwise

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from screening import subsidy_estimate as rules
from screening.models import AidAndSubsidy, Certificate, Consent, GuideChapterView, User
from screening.subsidy_estimate import Question, Result, estimate
from screening.tests import test_family_zone, test_pages
from screening.tests.helpers import consented_user
from screening.views import guide

# Written out, not read from the module, so a slip in the definition shows.
NOTICE_FIRST = "先拿核定公文再買，先買不補助。"
FORM_25 = "中階型以上要在配戴 1 到 3 個月內做二十五號表，核銷時要附上。"
HOSPITALS = ("看各縣市的鑑定醫院", "/guide/assessment#hospitals-title")
MILD_AT_65 = "是不是滿 65 歲以後才第一次鑑定為輕度？"
ELDER = "是不是 65 歲以上（原住民 55 歲以上）的低收入戶？"
WITHOUT_CERTIFICATE = "/guide/form-9#without-certificate"
ELDER_AMOUNTS = "低收入戶老人配戴助聽器補助每只最高 5,500 元、雙耳 11,000 元，同一耳 4 年一次。"


def _mild_at_65_may_lower(cap):
    return (
        f"如果是滿 65 歲以後才第一次鑑定為輕度，進階型的補助總額最多 {cap:,} 元，會比上面的金額少。"
    )


def _answers(**changes):
    """Spec #774 acceptance 12's case: a certificate, the notice in hand, both ears, 中階型,
    一般戶."""
    return {
        "certificate": rules.HAS,
        "progress": rules.NOTICE,
        "grade": rules.MID,
        "ears": rules.BOTH,
        "household": rules.GENERAL,
        # Asked only with 進階型.
        "mild_at_65": rules.NO,
        # Asked only without a certificate.
        "elder": rules.NO,
        **changes,
    }


def _asked(answers):
    """The names of the questions asked one by one, answering each with answers' value."""
    given, asked = {}, []
    while isinstance(step := estimate(given), Question):
        asked.append(step.name)
        given[step.name] = answers[step.name]
    return asked


def _given(answers):
    """answers cut down to the questions asked, as the page would send them."""
    return {name: answers[name] for name in _asked(answers)}


def _estimate(**changes):
    return estimate(_given(_answers(**changes)))


class EstimateQuestionsTests(SimpleTestCase):
    def test_one_question_at_a_time_in_the_specs_order(self):
        self.assertEqual(
            _asked(_answers()), ["certificate", "progress", "grade", "ears", "household"]
        )

    # Spec #774 acceptance 13: a set of 雙對側傳聲型 is never asked one ear or both.
    def test_cros_is_not_asked_one_ear_or_both(self):
        self.assertEqual(
            _asked(_answers(grade=rules.CROS)), ["certificate", "progress", "grade", "household"]
        )

    # Spec #774 acceptance 14: 進階型 alone is asked the 65 mild question, after the
    # household.
    def test_only_the_advanced_type_is_asked_about_mild_at_65(self):
        self.assertEqual(
            _asked(_answers(grade=rules.ADVANCED)),
            ["certificate", "progress", "grade", "ears", "household", "mild_at_65"],
        )
        for grade in (rules.BASIC, rules.MID, rules.CROS):
            with self.subTest(grade=grade):
                self.assertNotIn("mild_at_65", _asked(_answers(grade=grade)))

    def test_the_65_mild_question_is_yes_no_or_not_sure(self):
        answers = _given(_answers(grade=rules.ADVANCED))
        del answers["mild_at_65"]
        question = estimate(answers)
        self.assertEqual(question.label, MILD_AT_65)
        self.assertEqual(
            question.choices, ((rules.YES, "是"), (rules.NO, "否"), (rules.UNSURE, "不確定"))
        )

    # Spec #774, the owner's pick after #775: planning to apply skips how far it has got.
    def test_planning_to_apply_skips_the_progress_and_goes_on_to_the_grade(self):
        self.assertEqual(
            _asked(_answers(certificate=rules.PLANNING)),
            ["certificate", "grade", "ears", "household"],
        )

    # #776: the first question has 沒有 too.
    def test_the_first_question_has_a_certificate_planning_to_apply_or_none(self):
        first = estimate({})
        self.assertEqual(
            first.choices,
            ((rules.HAS, "有"), (rules.PLANNING, "打算申請或正在申請鑑定"), (rules.NONE, "沒有")),
        )

    # Spec #774 acceptance 16: without a certificate, one more question and then the result.
    def test_without_a_certificate_only_the_low_income_elder_question_follows(self):
        for elder in (rules.YES, rules.NO):
            with self.subTest(elder=elder):
                answers = _answers(certificate=rules.NONE, elder=elder)
                self.assertEqual(_asked(answers), ["certificate", "elder"])
                self.assertIsInstance(estimate(_given(answers)), Result)

    def test_the_low_income_elder_question_is_yes_or_no(self):
        question = estimate({"certificate": rules.NONE})
        self.assertEqual(question.label, ELDER)
        self.assertEqual(question.choices, ((rules.YES, "是"), (rules.NO, "不是")))

    def test_every_answer_given_gives_the_result(self):
        self.assertIsInstance(_estimate(), Result)


class EstimateRulesTests(SimpleTestCase):
    def test_the_notice_both_ears_mid_general_estimates_10000_and_buying_in_6_months(self):
        result = _estimate()
        self.assertIsInstance(result, Result)
        self.assertEqual(result.amount, 10000)
        self.assertEqual(result.amount_words, "10,000 元")
        self.assertEqual(result.next_step.title, "6 個月內購買")

    # Spec #774 acceptance 13 and the testing decisions: four grades times three households,
    # one ear and both. Written out from research.md's table, not worked out the module's way.
    def test_every_grade_and_household_for_one_ear_and_both(self):
        one_ear = {
            (rules.BASIC, rules.LOW): 2000,
            (rules.BASIC, rules.NEAR_LOW): 1500,
            (rules.BASIC, rules.GENERAL): 1000,
            (rules.MID, rules.LOW): 10000,
            (rules.MID, rules.NEAR_LOW): 7500,
            (rules.MID, rules.GENERAL): 5000,
            (rules.ADVANCED, rules.LOW): 20000,
            (rules.ADVANCED, rules.NEAR_LOW): 15000,
            (rules.ADVANCED, rules.GENERAL): 10000,
        }
        for (grade, household), amount in one_ear.items():
            for ears, times in ((rules.ONE, 1), (rules.BOTH, 2)):
                with self.subTest(grade=grade, household=household, ears=ears):
                    answers = _answers(grade=grade, household=household, ears=ears)
                    self.assertEqual(estimate(_given(answers)).amount, amount * times)

    def test_cros_counts_as_one_set_whatever_the_household(self):
        for household, amount in (
            (rules.LOW, 30000),
            (rules.NEAR_LOW, 22500),
            (rules.GENERAL, 15000),
        ):
            with self.subTest(household=household):
                answers = _answers(grade=rules.CROS, household=household)
                del answers["ears"]
                self.assertEqual(estimate(answers).amount, amount)

    # Spec #774 acceptance 14 and #776: 進階型 first assessed mild at 65 or over has a cap on
    # the total (research.md, 基準表 special rules), the smaller of it and the usual amount.
    def test_advanced_mild_at_65_both_ears_by_household(self):
        for household, yes, usual in (
            (rules.GENERAL, 10000, 20000),
            (rules.NEAR_LOW, 15000, 30000),
            (rules.LOW, 20000, 40000),
        ):
            for answer, amount in ((rules.YES, yes), (rules.NO, usual), (rules.UNSURE, usual)):
                with self.subTest(household=household, mild_at_65=answer):
                    result = _estimate(grade=rules.ADVANCED, household=household, mild_at_65=answer)
                    self.assertEqual(result.amount, amount)

    def test_advanced_mild_at_65_one_ear_is_already_within_the_cap(self):
        for household, amount in (
            (rules.GENERAL, 10000),
            (rules.NEAR_LOW, 15000),
            (rules.LOW, 20000),
        ):
            for answer in (rules.YES, rules.NO, rules.UNSURE):
                with self.subTest(household=household, mild_at_65=answer):
                    result = _estimate(
                        grade=rules.ADVANCED, ears=rules.ONE, household=household, mild_at_65=answer
                    )
                    self.assertEqual(result.amount, amount)

    def test_not_sure_says_the_cap_may_make_it_less(self):
        for household, cap in ((rules.GENERAL, 10000), (rules.NEAR_LOW, 15000), (rules.LOW, 20000)):
            with self.subTest(household=household):
                result = _estimate(
                    grade=rules.ADVANCED, household=household, mild_at_65=rules.UNSURE
                )
                words = [item.words for item in result.reminders]
                self.assertIn(_mild_at_65_may_lower(cap), words)

    def test_yes_no_and_a_cap_that_changes_nothing_say_nothing_of_it(self):
        for changes in (
            {"mild_at_65": rules.YES},
            {"mild_at_65": rules.NO},
            {"mild_at_65": rules.UNSURE, "ears": rules.ONE},
        ):
            with self.subTest(**changes):
                result = _estimate(grade=rules.ADVANCED, **changes)
                self.assertFalse([i for i in result.reminders if "65 歲" in i.words])

    def test_one_ear_basic_low_income_is_2000(self):
        result = _estimate(grade=rules.BASIC, ears=rules.ONE, household=rules.LOW)
        self.assertEqual(result.amount_words, "2,000 元")

    def test_cros_near_low_income_is_22500(self):
        answers = _answers(grade=rules.CROS, household=rules.NEAR_LOW)
        del answers["ears"]
        self.assertEqual(estimate(answers).amount_words, "22,500 元")


class EstimateWithoutCertificateTests(SimpleTestCase):
    """Spec #774 acceptance 16 (#776): 低收入戶老人配戴助聽器補助, or a fitting without waiting."""

    def test_a_low_income_elder_has_5500_an_aid(self):
        result = _estimate(certificate=rules.NONE, elder=rules.YES)
        self.assertEqual(result.amount, 5500)
        self.assertEqual(result.amount_words, "每只 5,500 元")
        self.assertIn(ELDER_AMOUNTS, [item.words for item in result.reminders])
        self.assertEqual(result.next_step.link.url, WITHOUT_CERTIFICATE)

    def test_anyone_else_can_book_a_fitting_without_waiting(self):
        result = _estimate(certificate=rules.NONE, elder=rules.NO)
        self.assertIsNone(result.amount)
        self.assertEqual(result.next_step.title, "直接預約聽力師試戴")
        self.assertIn("不用等公文", result.next_step.words)
        link = result.next_step.link
        self.assertEqual((link.words, link.url), ("看沒有身障證明時", WITHOUT_CERTIFICATE))

    def test_neither_is_told_to_wait_for_a_notice(self):
        for elder in (rules.YES, rules.NO):
            with self.subTest(elder=elder):
                result = _estimate(certificate=rules.NONE, elder=elder)
                words = [item.words for item in result.reminders]
                self.assertNotIn(NOTICE_FIRST, words)
                self.assertNotIn(FORM_25, words)


class EstimateNextStepTests(SimpleTestCase):
    """Spec #774 acceptance 12 and 15: one thing to do now, by how far the application has got."""

    def _step(self, **changes):
        return _estimate(**changes).next_step

    def _reminders(self, **changes):
        return [item.words for item in _estimate(**changes).reminders]

    def test_each_progress_has_its_own_next_step(self):
        for progress, title in (
            (rules.NO_FORM, "找聽力師做九號表"),
            (rules.HAS_FORM, "3 個月內送件"),
            (rules.APPLIED, "等核定公文"),
            (rules.NOTICE, "6 個月內購買"),
        ):
            with self.subTest(progress=progress):
                self.assertEqual(self._step(progress=progress).title, title)

    def test_planning_to_apply_leads_to_the_assessment_hospitals(self):
        step = self._step(certificate=rules.PLANNING)
        self.assertEqual(step.title, "先找醫院做身障鑑定")
        self.assertEqual((step.link.words, step.link.url), HOSPITALS)

    def test_before_the_notice_every_result_says_to_get_it_before_buying(self):
        for changes in (
            {"progress": rules.NO_FORM},
            {"progress": rules.HAS_FORM},
            {"progress": rules.APPLIED},
            {"certificate": rules.PLANNING},
        ):
            with self.subTest(**changes):
                self.assertIn(NOTICE_FIRST, self._reminders(**changes))

    def test_with_the_notice_it_no_longer_says_to_wait_for_it(self):
        self.assertNotIn(NOTICE_FIRST, self._reminders())

    def test_with_the_notice_mid_and_up_are_reminded_of_form_25(self):
        for grade in (rules.MID, rules.ADVANCED, rules.CROS):
            with self.subTest(grade=grade):
                self.assertIn(FORM_25, self._reminders(grade=grade))

    def test_the_basic_type_has_no_form_25_reminder(self):
        self.assertNotIn(FORM_25, self._reminders(grade=rules.BASIC, ears=rules.ONE))

    def test_form_25_waits_for_the_notice(self):
        for progress in (rules.NO_FORM, rules.HAS_FORM, rules.APPLIED):
            with self.subTest(progress=progress):
                self.assertNotIn(FORM_25, self._reminders(progress=progress))


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


class SubsidyEstimatePageTests(TestCase):
    def setUp(self):
        self.url = reverse("guide_subsidy")

    def _main(self, response):
        self.assertEqual(response.status_code, 200)
        return test_family_zone._main(response.content.decode())

    def _post(self, shown, **answers):
        """Sends the page as if the question shown was answered with answers: those before it as
        the page carries them, its own as its radio."""
        return self.client.post(self.url, {"shown": shown, **answers})

    def _result(self, **changes):
        """The result page, every question asked sent with its answer, the last one shown."""
        answers = _given(_answers(**changes))
        return self._main(self._post(list(answers)[-1], **answers))

    def _legend(self, main):
        return _text(re.search(r"<legend[^>]*>(.*?)</legend>", main, re.S).group(1)).strip()

    def _checked(self, main):
        return [
            re.search(r'value="([^"]+)"', tag).group(1)
            for tag in re.findall(r"<input [^>]*>", main)
            if 'type="radio"' in tag and " checked" in tag
        ]

    def _hidden(self, main):
        """The answers the page carries along, by name."""
        found = re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', main)
        return {
            name: value for name, value in found if name not in ("csrfmiddlewaretoken", "shown")
        }

    def _card(self, main):
        start = main.index('class="hero-card"')
        return main[start : main.index("</section>", start)]

    def test_address_is_under_the_guide(self):
        self.assertEqual(self.url, "/guide/subsidy")

    def test_page_has_one_heading_its_title_and_the_learn_tab(self):
        content = self.client.get(self.url).content.decode()
        self.assertEqual(re.findall(r"<h1[^>]*>([^<]*)</h1>", content), ["補助引導與試算"])
        nav = test_pages.RedesignLayoutTests.NAV.search(content).group()
        self.assertEqual(
            re.findall(r'aria-current="page"[^>]*>.*?<span>([^<]+)</span>', nav, re.S),
            ["了解"],
        )

    # Spec #774 acceptance 11, 20: one question, a group of radios its title names.
    def test_opening_it_shows_the_first_question_alone_without_a_way_back(self):
        main = self._main(self.client.get(self.url))
        self.assertIn(rules.INTRO, main)
        self.assertEqual(main.count("<fieldset"), 1)
        self.assertEqual(self._legend(main), "第 1 題 有聽覺機能的身心障礙證明嗎？")
        self.assertEqual(
            re.findall(r'<input type="radio" name="([^"]+)" value="([^"]+)"', main),
            [
                ("certificate", rules.HAS),
                ("certificate", rules.PLANNING),
                ("certificate", rules.NONE),
            ],
        )
        for words in ("有", "打算申請或正在申請鑑定", "沒有"):
            self.assertRegex(main, rf"<label[^>]*>\s*<input[^>]*>\s*{words}\s*</label>")
        self.assertNotIn("上一題", main)
        self.assertNotIn("autofocus", main)

    def test_the_answers_go_by_post_with_a_csrf_token_and_nothing_required(self):
        main = self._main(self.client.get(self.url))
        self.assertRegex(
            main, rf'<form [^>]*method="post" action="{self.url}" autocomplete="off"[^>]*>'
        )
        self.assertIn("csrfmiddlewaretoken", main)
        self.assertNotIn(" required", main)

    # Spec #774 acceptance 11, 20: each answer brings the next question alone, focus on its title,
    # the answers so far carried along in the page.
    def test_each_answer_brings_the_next_question_with_focus_on_its_title(self):
        main = self._main(self._post("certificate", certificate=rules.HAS))
        self.assertEqual(main.count("<fieldset"), 1)
        self.assertEqual(self._legend(main), "第 2 題 補助申請辦到哪一步了？")
        self.assertRegex(
            main, r'<legend[^>]*>.*<h2 id="question-title"[^>]*tabindex="-1"[^>]*autofocus'
        )
        self.assertEqual(self._hidden(main), {"certificate": rules.HAS})
        self.assertIn("上一題", main)

    def test_the_questions_follow_one_another_to_the_result(self):
        steps = (
            ("certificate", "第 2 題 補助申請辦到哪一步了？"),
            ("progress", "第 3 題 預計買哪一級的助聽器？"),
            ("grade", "第 4 題 預計配單耳還是雙耳？"),
            ("ears", "第 5 題 戶籍的福利身分是哪一種？"),
        )
        answers = _answers()
        given = {}
        for shown, legend in steps:
            given[shown] = answers[shown]
            with self.subTest(shown=shown):
                self.assertEqual(self._legend(self._main(self._post(shown, **given))), legend)
        main = self._main(self._post("household", **answers))
        self.assertNotIn("<fieldset", main)
        self.assertIn("10,000 元", main)

    # Spec #774 acceptance 11: 上一題 goes back one question with its answer still chosen.
    def test_back_shows_the_question_before_with_its_answer(self):
        given = {"certificate": rules.HAS, "progress": rules.APPLIED}
        main = self._main(self._post("grade", **given, back="grade"))
        self.assertEqual(self._legend(main), "第 2 題 補助申請辦到哪一步了？")
        self.assertEqual(self._checked(main), [rules.APPLIED])
        self.assertEqual(self._hidden(main), {"certificate": rules.HAS})
        self.assertIn("autofocus", main)

    def test_back_ignores_an_answer_chosen_on_the_question_shown(self):
        given = {"certificate": rules.HAS, "progress": rules.APPLIED, "grade": rules.MID}
        main = self._main(self._post("grade", **given, back="grade"))
        self.assertEqual(self._legend(main), "第 2 題 補助申請辦到哪一步了？")

    def test_back_from_the_result_shows_the_last_question(self):
        main = self._main(self._post("household", **_answers(), back="result"))
        self.assertEqual(self._legend(main), "第 5 題 戶籍的福利身分是哪一種？")
        self.assertEqual(self._checked(main), [rules.GENERAL])

    def test_back_to_the_first_question_has_no_way_further_back(self):
        main = self._main(self._post("progress", certificate=rules.HAS, back="progress"))
        self.assertEqual(self._legend(main), "第 1 題 有聽覺機能的身心障礙證明嗎？")
        self.assertEqual(self._checked(main), [rules.HAS])
        self.assertNotIn("上一題", main)

    def test_sending_without_an_answer_asks_again_and_says_so(self):
        main = self._main(self._post("progress", certificate=rules.HAS))
        self.assertEqual(self._legend(main), "第 2 題 補助申請辦到哪一步了？")
        self.assertIn("請選一個答案", main)
        self.assertRegex(main, r'<fieldset [^>]*aria-describedby="id_progress_error"')

    def test_an_answer_not_on_the_list_is_asked_again(self):
        main = self._main(self._post("certificate", certificate="maybe"))
        self.assertEqual(self._legend(main), "第 1 題 有聽覺機能的身心障礙證明嗎？")
        self.assertIn("請選一個答案", main)

    # The answer just given brings the next question unmarked, not an error.
    def test_the_next_question_comes_without_an_error(self):
        main = self._main(self._post("certificate", certificate=rules.HAS))
        self.assertNotIn("請選一個答案", main)
        self.assertNotIn("aria-describedby", main)

    # Spec #774 acceptance 12.
    def test_the_notice_both_ears_mid_general_result(self):
        main = self._result()
        text = _text(self._card(main))
        self.assertIn("預估最高補助 10,000 元", text)
        self.assertIn("以實際購買金額為上限，是否補助以主管機關核定為準。", text)
        self.assertIn("現在要做的事 6 個月內購買", text)
        self.assertIn(FORM_25, text)
        self.assertNotIn(NOTICE_FIRST, text)
        self.assertRegex(main, r'<h2 id="result-title"[^>]*tabindex="-1"[^>]*autofocus')

    # Spec #774 acceptance 13.
    def test_one_ear_basic_low_income_has_no_form_25_reminder(self):
        text = _text(self._result(grade=rules.BASIC, ears=rules.ONE, household=rules.LOW))
        self.assertIn("預估最高補助 2,000 元", text)
        self.assertNotIn("二十五號表", text)

    def test_cros_skips_one_ear_or_both_and_counts_a_set(self):
        given = {"certificate": rules.HAS, "progress": rules.NOTICE, "grade": rules.CROS}
        main = self._main(self._post("grade", **given))
        self.assertEqual(self._legend(main), "第 4 題 戶籍的福利身分是哪一種？")
        self.assertNotIn("單耳", main)
        text = _text(self._result(grade=rules.CROS, household=rules.NEAR_LOW))
        self.assertIn("預估最高補助 22,500 元", text)

    # Spec #774 acceptance 15.
    def test_before_the_notice_each_step_says_to_get_it_before_buying(self):
        for progress, title in (
            (rules.NO_FORM, "找聽力師做九號表"),
            (rules.HAS_FORM, "3 個月內送件"),
            (rules.APPLIED, "等核定公文"),
        ):
            with self.subTest(progress=progress):
                text = _text(self._card(self._result(progress=progress)))
                self.assertIn(f"現在要做的事 {title}", text)
                self.assertIn(NOTICE_FIRST, text)

    # Spec #774 acceptance 14 (#776): 進階型 is asked one more question after the household.
    def test_the_advanced_type_is_asked_about_mild_at_65_last(self):
        given = _given(_answers(grade=rules.ADVANCED))
        del given["mild_at_65"]
        main = self._main(self._post("household", **given))
        self.assertEqual(self._legend(main), f"第 6 題 {MILD_AT_65}")
        for words in ("是", "否", "不確定"):
            self.assertRegex(main, rf"<label[^>]*>\s*<input[^>]*>\s*{words}\s*</label>")

    def test_mild_at_65_caps_the_amount_and_not_sure_says_it_may_be_less(self):
        for changes, amount in (
            ({"mild_at_65": rules.YES}, "10,000 元"),
            ({"mild_at_65": rules.YES, "household": rules.NEAR_LOW}, "15,000 元"),
            ({"mild_at_65": rules.UNSURE}, "20,000 元"),
        ):
            with self.subTest(**changes):
                text = _text(self._card(self._result(grade=rules.ADVANCED, **changes)))
                self.assertIn(f"預估最高補助 {amount}", text)
                self.assertEqual(
                    _mild_at_65_may_lower(10000) in text, changes["mild_at_65"] == rules.UNSURE
                )

    # The owner's pick after #775: planning to apply goes from the first question to the grade.
    def test_planning_to_apply_is_asked_the_grade_next(self):
        main = self._main(self._post("certificate", certificate=rules.PLANNING))
        self.assertEqual(self._legend(main), "第 2 題 預計買哪一級的助聽器？")
        self.assertNotIn("辦到哪一步", main)

    def test_planning_to_apply_links_to_the_assessment_hospitals(self):
        card = self._card(self._result(certificate=rules.PLANNING))
        self.assertIn("現在要做的事 先找醫院做身障鑑定", _text(card))
        self.assertRegex(card, rf'<a class="btn btn-hero btn-lg[^"]*" href="{HOSPITALS[1]}"')
        self.assertIn(HOSPITALS[0], card)

    # Spec #774 acceptance 16.
    def test_without_a_certificate_the_low_income_elder_question_comes_next(self):
        main = self._main(self._post("certificate", certificate=rules.NONE))
        self.assertEqual(self._legend(main), f"第 2 題 {ELDER}")
        for words in ("是", "不是"):
            self.assertRegex(main, rf"<label[^>]*>\s*<input[^>]*>\s*{words}\s*</label>")

    def test_a_low_income_elder_result(self):
        main = self._result(certificate=rules.NONE, elder=rules.YES)
        text = _text(self._card(main))
        self.assertIn("預估最高補助 每只 5,500 元", text)
        self.assertIn(ELDER_AMOUNTS, text)
        self.assertNotIn(NOTICE_FIRST, text)
        self.assertRegex(main, r'<h2 id="result-title"[^>]*tabindex="-1"[^>]*autofocus')

    def test_not_a_low_income_elder_result_books_a_fitting_and_has_no_amount(self):
        main = self._result(certificate=rules.NONE, elder=rules.NO)
        card = self._card(main)
        text = _text(card)
        self.assertNotIn("預估最高補助", text)
        self.assertNotIn(" 元", text)
        self.assertIn("現在要做的事 直接預約聽力師試戴", text)
        self.assertIn("不用等公文", text)
        self.assertRegex(card, rf'<a class="btn btn-hero btn-lg[^"]*" href="{WITHOUT_CERTIFICATE}"')
        self.assertIn("看沒有身障證明時", card)
        self.assertRegex(main, r'<h2 id="result-title"[^>]*tabindex="-1"[^>]*autofocus')

    def test_links_in_the_results_lead_somewhere_real(self):
        mains = [
            self._result(certificate=rules.PLANNING),
            self._result(certificate=rules.NONE, elder=rules.NO),
            *(self._result(progress=progress) for progress in (rules.NO_FORM, rules.NOTICE)),
        ]
        links = {link for main in mains for link in re.findall(r'href="(/guide/[^"]+)"', main)}
        self.assertLessEqual(
            {HOSPITALS[1], "/guide/form-9#issuer-title", "/guide/form-25", WITHOUT_CERTIFICATE},
            links,
        )
        for link in links:
            path, _, anchor = link.partition("#")
            with self.subTest(link=link):
                page = self.client.get(path)
                self.assertEqual(page.status_code, 200)
                if anchor:
                    self.assertIn(f'id="{anchor}"', page.content.decode())

    # Spec #774 acceptance 17.
    def test_every_result_says_the_young_have_rules_of_their_own(self):
        for changes in (
            {},
            {"certificate": rules.PLANNING},
            {"grade": rules.CROS},
            {"certificate": rules.NONE, "elder": rules.YES},
            {"certificate": rules.NONE, "elder": rules.NO},
        ):
            with self.subTest(**changes):
                card = self._card(self._result(**changes))
                self.assertIn("18 歲以下或 25 歲以下在學的人另有規定", card)

    def test_the_foot_has_sources_and_the_checked_date_before_and_after(self):
        for main in (self._main(self.client.get(self.url)), self._result()):
            foot = main[main.index('class="mt-6 wrap-anywhere guide-sources"') :]
            self.assertIn("資料來源", foot)
            self.assertIn("身心障礙者輔具費用補助辦法", foot)
            self.assertIn("身心障礙者輔具費用補助基準表", foot)
            self.assertIn("本頁資料查核於 2026/10/23。", foot)

    def test_the_result_has_one_hero_card_and_no_solid_button(self):
        main = self._result()
        self.assertEqual(main.count('class="hero-card"'), 1)
        self.assertNotIn("btn-primary", main)
        self.assertIn("上一題", main)
        self.assertRegex(main, rf'<a class="btn btn-outline-primary[^"]*" href="{self.url}">')

    def test_headings_never_skip_a_level(self):
        for main in (self._main(self.client.get(self.url)), self._result()):
            levels = [int(level) for level in re.findall(r"<h([1-6])\b", main)]
            for before, after in pairwise(levels):
                self.assertLessEqual(after, before + 1, levels)

    # Spec #774 acceptance 11: never stored, never in the address, nothing kept.
    def test_every_response_is_marked_never_to_be_stored(self):
        for response in (
            self.client.get(self.url),
            self._post("certificate", certificate=rules.HAS),
            self._post("household", **_answers()),
        ):
            self.assertIn("no-store", response.get("Cache-Control", ""))

    def test_sending_keeps_nothing(self):
        with self.assertNumQueries(0):
            response = self._post("household", **_answers())
        self.assertEqual(response.request["QUERY_STRING"], "")
        self.assertEqual(response.request["PATH_INFO"], self.url)
        self.assertNotIn("sessionid", response.cookies)
        self.assertEqual(dict(self.client.session), {})

    def test_a_visitor_can_send_it_through_the_csrf_check(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url, {"certificate": rules.HAS}).status_code, 403)
        page = client.get(self.url).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
        sent = {"shown": "certificate", "certificate": rules.HAS, "csrfmiddlewaretoken": token}
        self.assertIn("補助申請辦到哪一步了？", client.post(self.url, sent).content.decode())

    # Spec #774 acceptance 19.
    def test_it_is_a_public_page_in_the_sitemap_with_its_own_title(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertNotIn("X-Robots-Tag", response)
        title = "助聽器補助可以拿多少？回答幾題算算看｜聽伴"  # noqa: RUF001
        self.assertRegex(content, rf"<title>\s*{title}\s*</title>")
        description = (
            "回答有沒有身障證明、辦到哪一步、助聽器等級和福利身分，"
            "算算看補助最多有多少，以及現在要做什麼。不用登入，回答不會留下來。"
        )
        self.assertIn(f'<meta name="description" content="{description}">', content)
        sitemap = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("<loc>https://testserver/guide/subsidy</loc>", sitemap)

    # Reads no one's data, so it can stay public: nothing in the view touches request.user.
    def test_view_never_reads_the_user(self):
        source = inspect.getsource(guide.guide_subsidy)
        self.assertNotIn("request.user", source)
        self.assertNotIn("login_required", source)


class SubsidyEstimateSignedInTests(TestCase):
    """Spec #774 acceptance 18: an estimate signed in changes none of the user's records."""

    def setUp(self):
        self.user = consented_user(username="estimate_private")
        AidAndSubsidy.objects.create(user=self.user, certificate=Certificate.YES, form_9_done=False)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        self.client.force_login(self.user)

    def _records(self):
        return (
            list(AidAndSubsidy.objects.filter(user=self.user).values()),
            list(GuideChapterView.objects.filter(user=self.user).values()),
            list(Consent.objects.filter(user=self.user).values()),
        )

    def _home(self):
        token = re.compile(r'name="csrfmiddlewaretoken" value="[^"]+"')
        main = test_family_zone._main(self.client.get(reverse("index")).content.decode())
        return token.sub("", main)

    def test_walking_it_through_changes_no_record_and_not_the_home_page(self):
        before, home = self._records(), self._home()
        url = reverse("guide_subsidy")
        self.assertEqual(self.client.get(url).status_code, 200)
        answers = _given(
            _answers(certificate=rules.PLANNING, grade=rules.ADVANCED, household=rules.LOW)
        )
        given = {}
        for name, value in answers.items():
            given[name] = value
            self.assertEqual(self.client.post(url, {"shown": name, **given}).status_code, 200)
        self.assertEqual(self.client.post(url, {**answers, "back": "result"}).status_code, 200)
        self.assertEqual(self._records(), before)
        self.assertEqual(self._home(), home)

    def test_a_user_who_has_not_agreed_yet_can_use_it(self):
        self.client.force_login(User.objects.create_user(username="estimate_old"))
        self.assertEqual(self.client.get(reverse("guide_subsidy")).status_code, 200)
