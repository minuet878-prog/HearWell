import dataclasses
import re
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from screening.models import User
from screening.qa_assistant import content
from screening.tests import test_guide, test_pages
from screening.tests.helpers import consented_user

NOT_FOUND = "沒有找到相符的題目，我們會參考您的問題補充。可以換個說法再試，或從下面的主題找。"


def main_of(response):
    page = response.content.decode()
    return page[page.index("<main") : page.index("</main>")]


def question_links(html):
    return re.findall(r'href="/qa/([^"/#]+)"', html)


class QaSearchFormTests(TestCase):
    """#399 (spec #396): the home page's 找不到？打字問, below everything else."""

    def test_the_form_comes_last_and_posts_to_search(self):
        main = main_of(self.client.get(reverse("qa_home")))
        title = re.search(r'<h2 id="qa-ask-title"[^>]*>找不到？打字問</h2>', main)
        self.assertIsNotNone(title)
        self.assertGreater(title.start(), main.index(">依主題找</h2>"))
        form = main[title.end() :]
        self.assertIn(f'<form method="post" action="{reverse("qa_search")}"', form)
        self.assertIn("csrfmiddlewaretoken", form)
        self.assertIn('<label for="id_question" class="form-label', form)
        self.assertRegex(form, r'<input [^>]*id="id_question"[^>]*name="question"')
        self.assertRegex(form, r'<input [^>]*maxlength="200"')
        self.assertIn('<button type="submit" class="btn btn-primary', form)
        self.assertIn(">找答案</button>", form)


class QaSearchTests(TestCase):
    """#399: typing a question, Post/Redirect/Get to the results."""

    def ask(self, question, **kwargs):
        return self.client.post(reverse("qa_search"), {"question": question}, **kwargs)

    def test_posting_redirects_to_the_results_without_the_question_in_the_address(self):
        response = self.ask("耳機補助怎麼申請")
        self.assertRedirects(response, reverse("qa_results"), fetch_redirect_response=False)
        self.assertNotIn("耳機", response["Location"])
        self.assertNotIn("?", response["Location"])

    def test_the_session_keeps_the_codes_not_the_question(self):
        self.ask("耳機補助怎麼申請")
        self.assertEqual(self.client.session["qa_results"], ["hearing-aid-subsidy"])
        values = " ".join(str(value) for value in self.client.session.values())
        self.assertNotIn("耳機", values)
        self.assertNotIn("申請", values)

    def test_the_results_list_the_matching_questions(self):
        response = self.ask("集音器是助聽器嗎", follow=True)
        self.assertEqual(response.redirect_chain, [(reverse("qa_results"), 302)])
        main = main_of(response)
        self.assertEqual(question_links(main)[0], "sound-amplifier-vs-hearing-aid")
        self.assertIn("集音器和助聽器有什麼不同？", main)
        self.assertNotIn("集音器是助聽器嗎", main)
        self.assertNotIn(NOT_FOUND, main)

    def test_the_results_list_the_best_first_and_at_most_five(self):
        faqs = tuple(
            dataclasses.replace(content.FAQS[0], code=f"q{n}", question="助聽器" + "補助" * n)
            for n in range(1, 8)
        )
        with (
            patch.object(content, "FAQS", faqs),
            patch.dict(content.BY_CODE, {faq.code: faq for faq in faqs}),
        ):
            self.ask("助聽器補助")
            links = question_links(main_of(self.client.get(reverse("qa_results"))))
        self.assertEqual(links[:5], ["q1", "q2", "q3", "q4", "q5"])
        self.assertEqual(self.client.session["qa_results"], ["q1", "q2", "q3", "q4", "q5"])

    def test_reloading_or_going_back_to_the_results_shows_them_again(self):
        # Back to a GET page, so the browser never asks to send the form again (#399).
        self.ask("突然聽不到")
        for _ in range(2):
            response = self.client.get(reverse("qa_results"))
            self.assertEqual(response.status_code, 200)
            self.assertIn("sudden-hearing-loss", question_links(main_of(response)))

    def test_nothing_found_says_so_and_lists_the_topics_and_popular(self):
        main = main_of(self.ask("今天天氣如何", follow=True))
        self.assertIn(NOT_FOUND, main)
        for slug, name in content.TOPICS:
            with self.subTest(topic=name):
                self.assertIn(f'<a href="{reverse("qa_topic", args=[slug])}">{name}</a>', main)
        popular = main[main.index(">大家常問</h2>") :]
        self.assertEqual(question_links(popular), list(content.POPULAR))
        self.assertNotIn("mailto:", main)
        self.assertNotIn("@", main)

    def test_the_results_link_back_to_ask_again(self):
        main = main_of(self.ask("今天天氣如何", follow=True))
        self.assertIn(f'href="{reverse("qa_home")}#qa-ask-title"', main)

    def test_the_results_page_without_a_question_goes_to_the_home_page(self):
        response = self.client.get(reverse("qa_results"))
        self.assertRedirects(response, reverse("qa_home"), fetch_redirect_response=False)

    def test_blank_stays_on_the_home_page_with_a_hint(self):
        for question in ("", "   "):
            with self.subTest(question=question):
                response = self.ask(question)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "screening/qa/home.html")
                main = main_of(response)
                self.assertIn("請輸入您想問的事，再按「找答案」", main)
                self.assertIn(
                    'aria-invalid="true" aria-describedby="id_question_error id_question_helptext"',
                    main,
                )
                self.assertNotIn("qa_results", self.client.session)

    def test_too_long_stays_on_the_home_page_with_a_hint(self):
        response = self.ask("耳" * 201)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "screening/qa/home.html")
        main = main_of(response)
        self.assertIn("請縮短到 200 字以內，現在是 201 字", main)
        self.assertIn("耳" * 201, main)
        self.assertNotIn("qa_results", self.client.session)

    def test_two_hundred_characters_are_fine(self):
        response = self.ask("耳" * 200)
        self.assertRedirects(response, reverse("qa_results"), fetch_redirect_response=False)

    def test_only_a_post_with_its_token(self):
        self.assertEqual(self.client.get(reverse("qa_search")).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("qa_search"), {"question": "x"}).status_code, 403)

    def test_signed_in_before_agreeing_to_the_privacy_notice(self):
        # The owner's call (2026-10-27): the Q&A assistant is open like its answers.
        self.client.force_login(User.objects.create_user(username="qa_search_not_consented"))
        response = self.ask("突然聽不到")
        self.assertRedirects(response, reverse("qa_results"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("qa_results")).status_code, 200)

    def test_signed_in_sees_what_a_visitor_sees(self):
        visitor = test_guide.text_of(self.ask("耳機補助", follow=True))
        self.client.force_login(consented_user(username="qa_search_reader"))
        signed_in = test_guide.text_of(self.ask("耳機補助", follow=True))
        self.assertEqual(signed_in, visitor)

    def test_the_results_are_not_kept_by_the_browser(self):
        # They come from this browser's session; the next question changes them.
        self.ask("突然聽不到")
        response = self.client.get(reverse("qa_results"))
        self.assertIn("no-store", response["Cache-Control"])


class QaResultsLayoutTests(TestCase):
    """#399: the results page in the 了解 tab, its headings in order."""

    def results(self, question):
        return self.client.post(reverse("qa_search"), {"question": question}, follow=True)

    def test_learn_is_the_current_tab(self):
        page = self.results("突然聽不到").content.decode()
        nav = test_pages.RedesignLayoutTests.NAV.search(page).group()
        self.assertEqual(
            re.findall(r'aria-current="page"[^>]*>.*?<span>([^<]+)</span>', nav, re.S),
            ["了解"],
        )

    def test_one_h1_and_headings_do_not_skip_a_level(self):
        for question in ("突然聽不到", "今天天氣如何"):
            with self.subTest(question=question):
                response = self.results(question)
                self.assertEqual(response.content.decode().count("<h1"), 1)
                levels = test_guide.heading_levels(response)
                test_guide.assert_levels_without_skipping(self, levels)
