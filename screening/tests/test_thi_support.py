"""THI: the support message with 1925 when an emotional item is answered often (#213, spec #208
stories 14 and 20), and at 重度 and 極重度 whatever those answers (the owner, #741 acceptance
2026-11-21)."""

from django.template.loader import render_to_string
from django.urls import reverse

from screening.models import Submission
from screening.tests import test_result_gauge, test_thi

# Draft wording from #211, written out here so a changed definition fails instead of being
# copied into the expectation.
SUPPORT = (
    "如果耳鳴讓您覺得心情低落、很難熬，可以撥 1925 安心專線（24 小時免付費），有專人陪您聊聊。"
    "也可以把這份結果帶給醫師或聽力師，一起討論怎麼減輕耳鳴的困擾。"
)
NEVER, SOMETIMES, OFTEN = 0, 2, 4


def only_often(*numbers):
    """25 answers: 經常 on the given item numbers, 不會 on the rest."""
    return [OFTEN if number in numbers else NEVER for number in range(1, 26)]


EMOTIONAL = (5, 11, 23)


def at_level(others_often):
    """25 answers: 有時 on items 5, 11 and 23, 經常 on the first `others_often` of the other
    items, 不會 on the rest."""
    others = [number for number in range(1, 26) if number not in EMOTIONAL]
    often = set(others[:others_often])
    return [
        SOMETIMES if number in EMOTIONAL else OFTEN if number in often else NEVER
        for number in range(1, 26)
    ]


# Each level's heading, answers with none of items 5, 11, 23 answered 經常 (totals 6, 22, 42,
# 58 and 94, worked out by hand against THI's level borders), and whether the support message
# shows: at 重度 and 極重度 always (the owner at #741 acceptance, 2026-11-21: with 看完整建議 gone
# from result pages, 1925 stays on theirs).
WITHOUT_OFTEN = (
    ("無障礙或輕微障礙", at_level(0), False),
    ("輕度障礙", at_level(4), False),
    ("中度障礙", at_level(9), False),
    ("重度障礙", at_level(13), True),
    ("極重度障礙", at_level(22), True),
)


class ThiSupportResultTests(test_thi.ThiTestCase):
    def _main(self, scores):
        self.post_web(scores)
        submission = Submission.objects.latest("pk")
        content = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def test_item_5_often_shows_the_support_message_under_a_slight_level(self):
        main = self._main(only_often(5))
        self.assertIn('總分 <span class="result-number">4</span> 分（滿分 100）', main)
        self.assertIn('aria-describedby="result-score">無障礙或輕微障礙</h2>', main)
        self.assertIn(SUPPORT, main)
        # Under the level: after the score block and the gauge in it (#750),
        # before the 建議下一步.
        banner_end = main.index('<p id="result-score"')
        support = main.index(SUPPORT)
        self.assertLess(banner_end, support)
        self.assertIn('<div class="gauge"', test_result_gauge.result_box(main))
        self.assertLess(main.index('<div class="gauge"'), support)
        self.assertLess(support, main.index('<section class="hero-card">'))

    def test_item_11_or_item_23_alone_often_shows_the_support_message(self):
        for number in (11, 23):
            with self.subTest(item=number):
                self.assertIn(SUPPORT, self._main(only_often(number)))

    def test_without_often_only_severe_and_catastrophic_show_the_support_message(self):
        for heading, scores, shown in WITHOUT_OFTEN:
            with self.subTest(level=heading):
                main = self._main(scores)
                self.assertIn(f'aria-describedby="result-score">{heading}</h2>', main)
                if shown:
                    self.assertIn(SUPPORT, main)
                    # In the same place as the 經常 rule's: after the score block.
                    self.assertLess(main.index('<p id="result-score"'), main.index(SUPPORT))
                    self.assertLess(main.index(SUPPORT), main.index('<section class="hero-card">'))
                else:
                    self.assertNotIn(SUPPORT, main)
                    self.assertNotIn("1925", main)

    def test_one_often_shows_the_support_message_at_every_level(self):
        for heading, scores, _shown in WITHOUT_OFTEN:
            for number in EMOTIONAL:
                with self.subTest(level=heading, item=number):
                    answers = list(scores)
                    answers[number - 1] = OFTEN
                    main = self._main(answers)
                    self.assertIn(SUPPORT, main)


class ThiSupportGuestSectionTests(test_thi.ThiTestCase):
    """A guest's result section is drawn by the scoring-only API from answers not saved
    (GuestScore: from_answers(), page_context(), graded_result.html), the same rule holding
    there. THI is not open to guests today (test_guest), so the section is drawn that way here."""

    def _section(self, scores):
        questions = list(self.thi.questions.order_by("question_number"))
        result = self.thi.definition.result.from_answers(
            self.thi, list(zip(questions, scores, strict=True)), False
        )
        return render_to_string(
            "screening/graded_result.html",
            {"submission": result.submission} | result.page_context(),
        )

    def test_the_same_rule_as_the_record_page(self):
        for heading, scores, shown in WITHOUT_OFTEN:
            with self.subTest(level=heading):
                html = self._section(scores)
                self.assertIn(f'aria-describedby="result-score">{heading}</h2>', html)
                self.assertEqual(SUPPORT in html, shown)
                answers = list(scores)
                answers[5 - 1] = OFTEN
                self.assertIn(SUPPORT, self._section(answers))


class ThiSupportOnlyOnResultTests(test_thi.ThiTestCase):
    """Spec #208 story 20: the family sees the level, not that 絕望 was answered often."""

    def setUp(self):
        super().setUp()
        self.post_web(only_often(5, 11, 23))
        submission = Submission.objects.latest("pk")
        result = self.client.get(reverse("result", args=[submission.pk]))
        self.assertContains(result, SUPPORT)

    def test_report_and_my_records_show_no_support_message(self):
        for name, params in (
            ("health_report", {}),
            ("my_hearing", {}),
            ("my_hearing", {"questionnaire": "thi"}),
        ):
            with self.subTest(page=name, params=params):
                page = self.client.get(reverse(name), params)
                self.assertEqual(page.status_code, 200)
                self.assertNotContains(page, SUPPORT)
                self.assertNotContains(page, "也可以把這份結果帶給醫師或聽力師")

    def test_family_shared_report_shows_no_support_message(self):
        self.client.post(reverse("report_share_create"), {"confirm": "1"})
        share = self.user.report_shares.get()
        self.client.logout()
        page = self.client.get(reverse("shared_report", args=[share.token]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, SUPPORT)
        self.assertNotContains(page, "也可以把這份結果帶給醫師或聽力師")
