"""Public-page accessibility regressions for issues #70–#74."""

import re
from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Audiogram, AudiogramPoint, Questionnaire, Submission
from screening.tests.helpers import consented_user, read_site_css
from screening.views.common import SIGN_IN_ERROR


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
                self.assertContains(page, '總分 <span class="result-number">40</span> 分')

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
            # #397: the Q&A assistant's home and an answer.
            reverse("qa_home"),
            reverse("qa_answer", args=["my-results"]),
            # #398: a topic page.
            reverse("qa_topic", args=["hearing-aids"]),
        ]
        self.client.logout()
        for url in (reverse("login"), reverse("register"), reverse("password_reset")):
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

    def test_report_fold_summaries_do_not_nest_headings(self):
        # <summary> carries an implicit button role; nesting <h2> inside it strips heading
        # semantics in Safari/VoiceOver and duplicates the section's real heading outline.
        call_command("seed_questionnaires", stdout=StringIO())
        hhie_s = Questionnaire.objects.get(code="hhie-s")
        self.record(hhie_s)
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 9, 28))
        AudiogramPoint.objects.create(
            audiogram=audiogram, ear="right", conduction="air", frequency=1000, db=40
        )
        content = self.client.get(reverse("health_report")).content.decode()
        summaries = re.findall(
            r'<details class="report-fold">\s*<summary>(.*?)</summary>', content, re.S
        )
        self.assertGreaterEqual(len(summaries), 2)
        for summary in summaries:
            with self.subTest(summary=summary[:60]):
                self.assertNotRegex(summary, r"<h[1-6]\b")
                self.assertIn('class="report-fold-title"', summary)

    def test_sign_in_error_box_is_focusable_on_login_and_register(self):
        self.client.logout()
        for name in ("login", "register"):
            with self.subTest(page=name):
                session = self.client.session
                session[SIGN_IN_ERROR] = "登入取消，請再試一次。"
                session.save()
                content = self.client.get(reverse(name)).content.decode()
                self.assertRegex(
                    content,
                    r'class="error-box"[^>]*role="alert"[^>]*tabindex="-1"[^>]*autofocus'
                    r"[^>]*>登入取消，請再試一次。",
                )


class StylesheetAccessibilityTests(SimpleTestCase):
    def _css(self):
        return re.sub(r"/\*.*?\*/", "", read_site_css(), flags=re.S)

    def test_no_legacy_bootstrap_blues_remain_in_site_css(self):
        css = self._css()
        for legacy in ("#0d6efd", "#86b7fe", "rgba(13, 110, 253", "rgba(49, 132, 253"):
            with self.subTest(legacy=legacy):
                self.assertNotIn(legacy, css)

    def test_global_focus_visible_and_focus_scroll_margins_exist(self):
        css = self._css()
        self.assertRegex(css, r":focus-visible\s*\{[^}]*outline\s*:\s*3px solid")
        self.assertRegex(css, r"scroll-margin-top\s*:")
        self.assertRegex(css, r"scroll-margin-bottom\s*:")

    def test_form_controls_and_checks_meet_touch_height(self):
        css = self._css()
        self.assertRegex(
            css,
            r"\.form-control,\s*\.form-select\s*\{[^}]*min-height\s*:\s*var\(--spacing-touch\)",
        )
        self.assertRegex(
            css,
            r"\.form-check\s*\{[^}]*min-height\s*:\s*var\(--spacing-touch\)",
        )
        self.assertIn(".form-select-lg", css)
