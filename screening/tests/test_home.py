"""Spec #148 batch 1, ticket #150: the new-user home page."""

import re
from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening.models import Audiogram
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
