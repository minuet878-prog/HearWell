"""Spec #148 batch 1, ticket #150: the new-user home page.
Spec #148 batch 2, ticket #159: the returning-user home page.
"""

import re
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Audiogram, Category, Question, Questionnaire, Submission
from screening.tests.helpers import consented_user


class NewUserHomeTests(TestCase):
    PASSWORD = "Xk9#mPq2vLw"
    STEPS = (
        "建立帳號，大約 1 分鐘。",
        "回答問題，大約 3 分鐘。",
        "馬上看到結果分級和建議。",
        "隔一段時間再做一次，在「我的紀錄」看分數的變化。",
    )
    OLD_HINT = "第一次使用請先註冊，已有帳號請直接登入。"

    def setUp(self):
        self.list_url = reverse("questionnaire_list")
        self.start_url = f"{reverse('register')}?next={self.list_url}"
        self.login_url = f"{reverse('login')}?next={self.list_url}"

    def _main(self):
        content = self.client.get(reverse("index")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _link(self, main, text):
        """The href of the link in the page body whose whole text is `text`."""
        links = re.findall(r'<a[^>]*href="([^"]*)"[^>]*>\s*([^<]*?)\s*</a>', main)
        hrefs = [href for href, label in links if label == text]
        self.assertEqual(len(hrefs), 1, f"{text}: {links}")
        return hrefs[0]

    def _steps(self, main):
        steps = re.search(r'<ol class="step-cards".*?</ol>', main, re.DOTALL).group(0)
        return re.findall(r"<span>([^<]+)</span>", steps)

    def test_anonymous_sees_start_and_login_buttons_and_four_steps(self):
        main = self._main()
        self.assertEqual(self._link(main, "開始篩檢"), self.start_url)
        self.assertEqual(self._link(main, "我已經有帳號，登入"), self.login_url)
        self.assertEqual(self._steps(main), list(self.STEPS))
        self.assertNotIn(self.OLD_HINT, main)

    def test_login_button_logs_in_then_chooses_a_questionnaire(self):
        consented_user(username="returning", password=self.PASSWORD)
        page = self.client.get(self._link(self._main(), "我已經有帳號，登入"))
        self.assertContains(
            page, f'<input type="hidden" name="next" value="{self.list_url}">', html=True
        )
        response = self.client.post(
            reverse("login"),
            {"username": "returning", "password": self.PASSWORD, "next": self.list_url},
        )
        self.assertRedirects(response, self.list_url)

    def test_start_registers_then_consents_then_chooses_a_questionnaire(self):
        page = self.client.get(self._link(self._main(), "開始篩檢"))
        self.assertTemplateUsed(page, "screening/register.html")
        self.assertContains(
            page, f'<input type="hidden" name="next" value="{self.list_url}">', html=True
        )
        response = self.client.post(
            reverse("register"),
            {
                "username": "newcomer",
                "email": "newcomer@example.com",
                "password1": self.PASSWORD,
                "password2": self.PASSWORD,
                "next": self.list_url,
            },
        )
        consent_url = f"{reverse('consent')}?next={self.list_url}"
        self.assertRedirects(response, consent_url)
        response = self.client.post(consent_url, {"agree": "1", "next": self.list_url})
        # The wizard's first screen greets the new account (#152).
        self.assertRedirects(response, f"{self.list_url}?from=consent")

    def test_other_protected_pages_still_go_to_login_and_back(self):
        consented_user(username="tester", password=self.PASSWORD)
        for url in (self.list_url, reverse("my_hearing"), reverse("audiogram_list")):
            with self.subTest(url=url):
                self.client.logout()
                login_url = f"{reverse('login')}?next={url}"
                self.assertRedirects(self.client.get(url), login_url)
                response = self.client.post(
                    reverse("login"),
                    {"username": "tester", "password": self.PASSWORD, "next": url},
                )
                self.assertRedirects(response, url)

    def test_signed_in_user_without_records_sees_new_user_home(self):
        audiogram_only = consented_user(username="audiogram_only")
        # Spec #148 story 4: an audiogram is not a questionnaire record.
        Audiogram.objects.create(user=audiogram_only, tested_on=date(2026, 10, 1))
        for user in (consented_user(username="no_records"), audiogram_only):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                main = self._main()
                self.assertEqual(self._link(main, "開始篩檢"), self.list_url)
                self.assertNotIn("我已經有帳號，登入", main)
                self.assertEqual(self._steps(main), list(self.STEPS))
                self.assertNotIn(self.OLD_HINT, main)
                self.assertNotIn("請先註冊", main)

    def test_result_preview_uses_the_result_page_level_style(self):
        # 18 points on HHIE-S is mild to moderate; the result page draws its banner the same way.
        self.assertInHTML(
            '<div class="result-banner result-banner-mild_to_moderate">'
            '<div class="result-level">輕度到中度影響</div>'
            "<div>HHIE-S 總分 18 分（滿分 40）</div></div>",
            self._main(),
        )

    def test_anonymous_home_has_no_never_cache_header(self):
        response = self.client.get(reverse("index"))
        self.assertNotIn("no-store", response.get("Cache-Control", ""))


class ReturningUserHomeTests(TestCase):
    """Spec #148 batch 2, ticket #159: the returning-user home page."""

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="returning_tester")
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.hhie_questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhie_s,
                question_text=f"HHIE題{i}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        cls.ioi_questions = Question.objects.bulk_create(
            Question(questionnaire=cls.ioi_ha, question_text=f"IOI題{i}", question_number=i)
            for i in range(1, 8)
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _submit(self, questionnaire, questions, score, days_ago):
        submission = Submission.objects.create(user=self.user, questionnaire=questionnaire)
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score) for question in questions
        )
        Submission.objects.filter(pk=submission.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        submission.refresh_from_db()
        return submission

    def _main(self):
        content = self.client.get(reverse("index")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def test_due_retest_shows_reminder_and_retake_button(self):
        submission = self._submit(self.hhie_s, self.hhie_questions, score=4, days_ago=200)
        response = self.client.get(reverse("index"))
        main = content = response.content.decode()
        main = content[content.index("<main") : content.index("</main>")]
        self.assertIn("已經滿 6 個月", main)
        self.assertIn(
            f'href="{reverse("screening", args=[self.hhie_s.pk])}">再做一次（大約 3 分鐘）</a>',
            main,
        )
        self.assertIn(reverse("result", args=[submission.id]), main)

    def test_not_due_shows_next_date_and_secondary_retake(self):
        self._submit(self.hhie_s, self.hhie_questions, score=4, days_ago=30)
        main = self._main()
        self.assertIn("下次建議", main)
        self.assertIn(f'href="{reverse("my_hearing")}">看我的紀錄與趨勢</a>', main)
        self.assertIn(f'href="{reverse("screening", args=[self.hhie_s.pk])}">再做一次</a>', main)

    def test_only_ioi_ha_shows_its_summary_without_a_reminder(self):
        self._submit(self.ioi_ha, self.ioi_questions, score=3, days_ago=1)
        main = self._main()
        self.assertIn("助聽器使用成效（IOI-HA）", main)
        self.assertNotIn("已經滿 6 個月", main)
        self.assertNotIn("下次建議", main)
        self.assertNotIn("再做一次", main)

    def test_signed_in_home_is_never_cached(self):
        response = self.client.get(reverse("index"))
        self.assertIn("no-store", response["Cache-Control"])

    def test_only_the_logged_in_user_s_records_are_shown(self):
        other = consented_user(username="someone_else")
        other_submission = Submission.objects.create(user=other, questionnaire=self.hhie_s)
        Answer.objects.bulk_create(
            Answer(submission=other_submission, question=question, score=4)
            for question in self.hhie_questions
        )
        main = self._main()
        self.assertNotIn(reverse("result", args=[other_submission.id]), main)
