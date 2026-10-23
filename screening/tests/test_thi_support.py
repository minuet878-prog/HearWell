"""THI: the support message with 1925 when an emotional item is answered often (#213, spec #208
stories 14 and 20)."""

from django.urls import reverse

from screening.models import Submission
from screening.tests import test_thi

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


class ThiSupportResultTests(test_thi.ThiTestCase):
    def _main(self, scores):
        self.post_web(scores)
        submission = Submission.objects.latest("pk")
        content = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def test_item_5_often_shows_the_support_message_under_a_slight_level(self):
        main = self._main(only_often(5))
        self.assertIn("總分 4 分（滿分 100）", main)
        self.assertIn('aria-describedby="result-score">無障礙或輕微障礙</h2>', main)
        self.assertIn(SUPPORT, main)
        # Under the level: after the banner, before the score bar and the steps.
        banner_end = main.index('<div id="result-score"')
        support = main.index(SUPPORT)
        self.assertLess(banner_end, support)
        self.assertLess(support, main.index('<div class="score-bar"'))
        self.assertLess(support, main.index('<h2 class="h4 mt-6">接下來建議您</h2>'))

    def test_item_11_or_item_23_alone_often_shows_the_support_message(self):
        for number in (11, 23):
            with self.subTest(item=number):
                self.assertIn(SUPPORT, self._main(only_often(number)))

    def test_items_5_11_23_sometimes_and_the_rest_often_shows_no_support_message(self):
        scores = [SOMETIMES if number in (5, 11, 23) else OFTEN for number in range(1, 26)]
        main = self._main(scores)
        self.assertIn('aria-describedby="result-score">極重度障礙</h2>', main)
        self.assertNotIn(SUPPORT, main)
        # The catastrophic advice and steps still give the 1925 line.
        self.assertIn(test_thi.LINE_1925, main.split("完整建議", 1)[1])


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
