"""Public-page accessibility regressions for issues #70–#74."""

import re
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Questionnaire, Submission
from screening.tests.helpers import consented_user


class AccessibilityPageTests(TestCase):
    fixtures = ("questions_fixture.json",)

    def setUp(self):
        self.user = consented_user(username="a11y_user")
        self.client.force_login(self.user)

    def record(self, questionnaire):
        record = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=False
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=q, score=4) for q in questionnaire.questions.all()
        )
        return record

    def test_hhi_result_level_is_a_heading_with_its_score_description(self):
        call_command("seed_questionnaires", stdout=StringIO())
        for questionnaire in Questionnaire.objects.filter(code__in=("hhie-s", "hhia-s")):
            with self.subTest(code=questionnaire.code):
                record = self.record(questionnaire)
                page = self.client.get(reverse("result", args=[record.pk]))
                self.assertRegex(page.content.decode(), r"<h2\b[^>]*>顯著影響</h2>")
                self.assertContains(page, 'aria-describedby="result-score"')
                self.assertContains(page, 'id="result-score"')
                self.assertContains(page, "總分 40 分")

    def test_login_fields_identify_username_and_current_password(self):
        self.client.logout()
        page = self.client.get(reverse("login"))
        for name, purpose in (("username", "username"), ("password", "current-password")):
            with self.subTest(field=name):
                self.assertRegex(
                    page.content.decode(),
                    rf'<input\b[^>]*name="{name}"[^>]*autocomplete="{purpose}"',
                )

    def test_pages_have_one_primary_heading_inside_main(self):
        questionnaire = Questionnaire.objects.get(code="hhie-s")
        record = self.record(questionnaire)
        pages = [
            reverse("index"),
            reverse("my_hearing"),
            reverse("questionnaire_list"),
            reverse("screening", args=[questionnaire.pk]),
            reverse("result", args=[record.pk]),
        ]
        self.client.logout()
        for url in (reverse("login"), reverse("register")):
            with self.subTest(url=url):
                page = self.client.get(url).content.decode()
                self.assertEqual(len(re.findall(r"<h1\b", page)), 1)
        self.client.force_login(self.user)
        for url in pages:
            with self.subTest(url=url):
                page = self.client.get(url).content.decode()
                main = page[page.index("<main") : page.index("</main>")]
                self.assertEqual(len(re.findall(r"<h1\b", page)), 1)
                self.assertEqual(len(re.findall(r"<h1\b", main)), 1)

    def test_skip_link_is_the_first_link_and_targets_focusable_main(self):
        for url in (reverse("index"), reverse("login"), reverse("my_hearing")):
            with self.subTest(url=url):
                page = self.client.get(url).content.decode()
                body = page[page.index("<body>") :]
                first_link = re.search(r"<a\b[^>]*>.*?</a>", body, re.S).group()
                self.assertIn('href="#main-content"', first_link)
                self.assertIn("跳到主要內容", first_link)
                self.assertRegex(page, r'<main\b[^>]*id="main-content"[^>]*tabindex="-1"')

    def test_history_exposes_every_date_and_score_beyond_chart_page_limit(self):
        questionnaire = Questionnaire.objects.get(code="hhie-s")
        expected = []
        for offset in range(23):
            record = self.record(questionnaire)
            when = timezone.now() - timedelta(days=offset)
            Submission.objects.filter(pk=record.pk).update(created_at=when)
            expected.append((record.pk, timezone.localtime(when).strftime("%Y/%m/%d")))
        page = self.client.get(reverse("my_hearing"), {"questionnaire": "hhie-s"})
        cards = re.findall(r'<a\b[^>]*class="link-card"[^>]*>.*?</a>', page.content.decode(), re.S)
        self.assertEqual(len(cards), 23)
        for (record_id, date_text), card in zip(expected, cards, strict=True):
            with self.subTest(record=record_id):
                self.assertIn(reverse("result", args=[record_id]), card)
                self.assertIn(date_text, card)
                self.assertIn("總分：40", card)
                self.assertNotIn(
                    'aria-hidden="true"',
                    card.replace(
                        '<span class="link-card-arrow" aria-hidden="true">\u203a</span>', ""
                    ),
                )
