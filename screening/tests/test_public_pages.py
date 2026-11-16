"""公開頁面 (GLOSSARY.md, ADR 0062): only they may be indexed by search engines (spec #583)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from screening import public_pages
from screening.qa_assistant import content
from screening.views import guide


class NotIndexedByDefaultTests(TestCase):
    def test_a_page_outside_the_list_is_kept_out_of_search(self):
        # Open without logging in, yet a step of signing in: not a 公開頁面.
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("noindex", response["X-Robots-Tag"])

    def test_pages_open_without_logging_in_are_not_all_public(self):
        # Steps of a flow, not content: the guest's wizard, signing up, the forgotten password,
        # adding to the home screen, and what the uptime monitor opens.
        pages = ("questionnaire_list", "register", "password_reset", "add_to_home", "uptime_check")
        for name in pages:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertIn("noindex", response["X-Robots-Tag"])

    def test_a_typed_question_and_its_results_are_kept_out_of_search(self):
        refused = self.client.get(reverse("qa_search"))
        self.assertEqual(refused.status_code, 405)
        self.assertIn("noindex", refused["X-Robots-Tag"])
        sent_back = self.client.get(reverse("qa_results"))
        self.assertEqual(sent_back.status_code, 302)
        self.assertIn("noindex", sent_back["X-Robots-Tag"])
        self.client.post(reverse("qa_search"), {"question": "助聽器補助"})
        results = self.client.get(reverse("qa_results"))
        self.assertEqual(results.status_code, 200)
        self.assertIn("noindex", results["X-Robots-Tag"])

    def test_a_page_that_sends_to_log_in_is_kept_out_of_search(self):
        response = self.client.get(reverse("my_hearing"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("noindex", response["X-Robots-Tag"])

    def test_an_address_that_does_not_exist_is_kept_out_of_search(self):
        response = self.client.get("/no-such-page")
        self.assertEqual(response.status_code, 404)
        self.assertIn("noindex", response["X-Robots-Tag"])

    def test_an_answer_that_never_existed_is_kept_out_of_search(self):
        # Under the address every answer page shares.
        response = self.client.get(reverse("qa_answer", args=["no-such-question"]))
        self.assertEqual(response.status_code, 404)
        self.assertIn("noindex", response["X-Robots-Tag"])

    def test_a_public_page_answering_with_a_redirect_is_kept_out_of_search(self):
        # Signed in without having agreed to the privacy notice, 了解 sends to the consent page.
        self.client.force_login(get_user_model().objects.create_user("not-agreed"))
        response = self.client.get(reverse("learn"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("noindex", response["X-Robots-Tag"])

    def test_the_admin_and_the_api_are_kept_out_of_search(self):
        for url in (reverse("admin:index"), reverse("api:submissions")):
            with self.subTest(url=url):
                self.assertIn("noindex", self.client.get(url)["X-Robots-Tag"])


class PublicPageTests(TestCase):
    def test_the_list_is_the_pages_the_spec_names(self):
        # Spec #583 acceptance 5. Chapters, topics and answers come from their definitions.
        fixed = {
            "/",
            "/learn",
            "/learn/simulator",
            "/privacy",
            "/family",
            "/family/talk",
            "/family/reluctant",
            "/family/hearing-aids",
            "/family/visits",
            "/family/visits/subsidy",
            "/family/visits/deadlines",
            "/guide",
            "/qa",
        }
        chapters = {f"/guide/{chapter.slug}" for chapter in guide.GUIDE_CHAPTERS}
        topics = {
            f"/qa/topic/{slug}"
            for slug, _name in content.TOPICS
            if self.client.get(f"/qa/topic/{slug}").context["faqs"]
        }
        answers = {f"/qa/{faq.code}" for faq in content.FAQS}
        self.assertEqual(len(chapters), 6)
        self.assertEqual(set(public_pages.public_urls()), fixed | chapters | topics | answers)

    def test_each_answer_may_be_indexed_a_referral_answer_too(self):
        referral = next(faq for faq in content.FAQS if faq.referral)
        answered = next(faq for faq in content.FAQS if not faq.referral)
        for faq in (referral, answered):
            with self.subTest(code=faq.code):
                response = self.client.get(reverse("qa_answer", args=[faq.code]))
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("X-Robots-Tag", response)

    def test_a_topic_page_may_be_indexed_only_when_it_lists_a_question(self):
        listing = {}
        for slug, _name in content.TOPICS:
            response = self.client.get(reverse("qa_topic", args=[slug]))
            self.assertEqual(response.status_code, 200)
            listing[slug] = bool(response.context["faqs"])
            with self.subTest(topic=slug):
                self.assertEqual("X-Robots-Tag" not in response, listing[slug])
        # 網站怎麼用 has no question yet (2026-11-16): the topic that checks the empty side.
        self.assertIn(False, listing.values())
