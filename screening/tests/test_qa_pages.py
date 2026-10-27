import re
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.models import User
from screening.tests import test_guide
from screening.tests.helpers import consented_user

REFERRALS = ("my-results", "diagnosis-and-medication", "brands-and-shops", "sudden-hearing-loss")


def answer_part(response):
    """The answer itself: from the page's h1 to the footer of sources."""
    content = response.content.decode()
    return content[content.index("<h1") : content.index("<footer")]


class QaHomeTests(TestCase):
    """#397 (spec #396): the Q&A assistant's home page."""

    def test_urgent_answer_then_popular_then_the_four_topics(self):
        response = self.client.get(reverse("qa_home"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        main = content[content.index("<main") :]
        self.assertRegex(main, r"<h1[^>]*>問答小助手</h1>")
        order = [
            f'href="{reverse("qa_answer", args=["sudden-hearing-loss"])}"',
            ">大家常問</h2>",
            ">依主題找</h2>",
            "網站怎麼用",
            "問卷是什麼",
            "助聽器選配與補助",
            "聽力保健常識",
        ]
        places = [main.find(text) for text in order]
        self.assertNotIn(-1, places, dict(zip(order, places, strict=True)))
        self.assertEqual(places, sorted(places))

    def test_the_urgent_answer_sits_in_the_family_page_urgent_box(self):
        # The owner's call (2026-10-27): the family page's 馬上就醫 look, blue, not red (ADR 0007).
        content = self.client.get(reverse("qa_home")).content.decode()
        box = re.search(
            r'<section class="[^"]*\bqa-urgent\b[^"]*"[^>]*>(.*?)</section>', content, re.S
        )
        self.assertIsNotNone(box)
        self.assertIn("請盡快就醫", box[1])
        self.assertIn(f'href="{reverse("qa_answer", args=["sudden-hearing-loss"])}"', box[1])

    def test_popular_follows_the_definition_order(self):
        for popular in (
            ("my-results", "brands-and-shops", "diagnosis-and-medication"),
            ("diagnosis-and-medication", "my-results"),
        ):
            with (
                self.subTest(popular=popular),
                patch("screening.qa_assistant.content.POPULAR", popular),
            ):
                content = self.client.get(reverse("qa_home")).content.decode()
                section = content[content.index(">大家常問</h2>") : content.index(">依主題找</h2>")]
                links = re.findall(r'href="/qa/([^"]+)"', section)
                self.assertEqual(tuple(links), popular)

    def test_the_topics_are_not_links_yet(self):
        # #398 makes each topic a page; until then nothing leads anywhere unfinished.
        content = self.client.get(reverse("qa_home")).content.decode()
        topics = content[content.index(">依主題找</h2>") : content.index("</main>")]
        self.assertNotIn("<a ", topics)

    def test_headings_do_not_skip_a_level(self):
        response = self.client.get(reverse("qa_home"))
        test_guide.assert_levels_without_skipping(self, test_guide.heading_levels(response))


class QaAnswerTests(TestCase):
    """#397 (spec #396): one question a page."""

    def test_question_answer_reminder_sources_and_check_date(self):
        response = self.client.get(reverse("qa_answer", args=["brands-and-shops"]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertRegex(content, r"<h1[^>]*>哪個牌子的助聽器比較好？去哪家店買？</h1>")
        text = test_guide.text_of(response)
        self.assertIn("小助手不推薦品牌、型號或店家。", text)
        self.assertIn("以上是一般說明，您的情況請以醫師、聽力師為準。", text)
        footer = content[content.index("<footer") : content.index("</footer>")]
        self.assertIn('<details class="dropdown-box mb-2">', footer)
        self.assertIn("<summary>資料來源</summary>", footer)
        self.assertIn(f'href="{reverse("guide_chapter", args=["types-and-prices"])}"', footer)
        self.assertIn(f'href="{reverse("guide_chapter", args=["assessment"])}"', footer)
        self.assertIn('<p class="guide-checked">本頁資料查核於 2026/10/27。</p>', footer)

    def test_a_code_never_used_is_not_found(self):
        response = self.client.get(reverse("qa_answer", args=["no-such-question"]))
        self.assertEqual(response.status_code, 404)

    def test_headings_do_not_skip_a_level(self):
        for code in REFERRALS:
            with self.subTest(code=code):
                response = self.client.get(reverse("qa_answer", args=[code]))
                levels = test_guide.heading_levels(response)
                test_guide.assert_levels_without_skipping(self, levels)


class QaSameForEveryoneTests(TestCase):
    """#397 (ADR 0032): signed in or not, the same answer; nobody's records are read."""

    PAGES = (("qa_home", ()), *(("qa_answer", (code,)) for code in REFERRALS))

    def test_signed_in_sees_what_a_visitor_sees(self):
        for name, args in self.PAGES:
            with self.subTest(page=name, args=args):
                self.client.logout()
                visitor = test_guide.text_of(self.client.get(reverse(name, args=args)))
                self.client.force_login(consented_user(username=f"qa_{name}_{args}"))
                signed_in = test_guide.text_of(self.client.get(reverse(name, args=args)))
                self.assertEqual(signed_in, visitor)

    def test_no_questionnaire_or_audiogram_is_read(self):
        self.client.force_login(consented_user(username="qa_reader"))
        for name, args in self.PAGES:
            with self.subTest(page=name, args=args):
                with CaptureQueriesContext(connection) as queries:
                    self.client.get(reverse(name, args=args))
                tables = " ".join(query["sql"] for query in queries.captured_queries)
                self.assertNotIn("screening_submission", tables)
                self.assertNotIn("screening_answer", tables)
                self.assertNotIn("screening_audiogram", tables)

    def test_signed_in_before_agreeing_to_the_privacy_notice(self):
        # The owner's call (2026-10-27): open like the family page; family share the links.
        self.client.force_login(User.objects.create_user(username="qa_not_consented"))
        for name, args in self.PAGES:
            with self.subTest(page=name, args=args):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)


class QaReferralTests(TestCase):
    """#397 (ADR 0032): the four referral answers say where to go instead."""

    def answer(self, code):
        return answer_part(self.client.get(reverse("qa_answer", args=[code])))

    def test_my_results_leads_to_my_records(self):
        answer = self.answer("my-results")
        self.assertIn("不解讀個人的結果", answer)
        self.assertIn(f'<a href="{reverse("my_hearing")}">到「我的紀錄」看結果</a>', answer)
        self.assertIn("帶給聽力師看", answer)

    def test_diagnosis_and_medication_sends_to_an_ear_nose_and_throat_doctor(self):
        answer = self.answer("diagnosis-and-medication")
        self.assertIn("不回答個人的診斷和用藥", answer)
        self.assertIn("耳鼻喉科醫師", answer)

    def test_brands_and_shops_lead_to_types_and_prices_and_the_hospital_search(self):
        answer = self.answer("brands-and-shops")
        self.assertIn("不推薦品牌、型號或店家", answer)
        types = reverse("guide_chapter", args=["types-and-prices"])
        self.assertIn(f'<a href="{types}">「助聽器的種類與價格」</a>', answer)
        hospitals = f"{reverse('guide_chapter', args=['assessment'])}#hospitals-title"
        self.assertIn(f'<a href="{hospitals}">「找鑑定醫院」</a>', answer)

    def test_sudden_hearing_loss_says_to_see_a_doctor_soon(self):
        answer = self.answer("sudden-hearing-loss")
        self.assertIn("請盡快到耳鼻喉科就醫", answer)
        urgent = f"{reverse('family_guide')}#urgent-title"
        self.assertIn(f'<a href="{urgent}">「什麼時候要馬上就醫」</a>', answer)
