"""#471 (mockup #470 groups 4-7, 9): account settings, deleting the account, login, register,
consent, the privacy notice and adding to the home screen, restyled.

Picks (grill-decisions #470): no brand banner on login, register and consent (D1 B); account A
with two section titles; danger in red (D4); the login error in a red box (D6); the privacy
notice's sections folded into rows (B). Flows and fields are unchanged.
"""

import re
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from screening.forms import RegisterForm
from screening.models import User
from screening.tests.helpers import consented_user

TAG = re.compile(r"<[^>]+>")
PRIVACY_SECTIONS = [
    ("who-title", "誰在蒐集"),
    ("why-title", "為什麼蒐集"),
    ("collected-title", "蒐集哪些資料"),
    ("google-title", "用 Google 登入時"),  # spec #505
    ("question-log-title", "問答小助手的提問紀錄"),
    ("storage-title", "存放在哪裡、保存多久"),
    ("recipients-title", "會交給誰"),
    ("sharing-title", "您主動分享時"),
    ("rights-title", "您可以要求什麼"),
    ("refuse-title", "不提供資料會怎樣"),
    ("diagnosis-title", "不是醫療診斷"),
    ("changes-title", "說明改版"),
]


def _main(response):
    content = response.content.decode()
    return content[content.index("<main") : content.index("</main>")]


def _text(html):
    return re.sub(r"\s+", " ", TAG.sub("", html)).strip()


class AccountSettingsTests(TestCase):
    def setUp(self):
        self.client.force_login(consented_user(username="settings_redesign"))

    def _main(self):
        return _main(self.client.get(reverse("account_settings")))

    def test_two_section_titles_and_the_rows_in_one_group(self):
        main = self._main()
        headings = [_text(h) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", main, re.S)]
        group = main[main.index("家人與資料</h2>") : main.index("刪除帳號")]
        titles = re.findall(r'<span class="link-card-title">([^<]+)</span>', group)

        self.assertEqual(headings, ["我的帳號", "家人與資料"])
        self.assertEqual(
            titles,
            [
                "分享報告給家人",
                "家人專區：溝通與陪伴",
                "加到手機主畫面",
                "下載我的資料",
                "隱私權說明",
            ],
        )
        self.assertNotIn("btn-primary", main)

    def test_deleting_is_a_red_row_with_a_red_icon(self):
        main = self._main()

        self.assertRegex(
            main,
            r'<a class="link-card action-card settings-card-danger" href="/account/delete">\s*'
            r'<span class="action-card-icon"',
        )


class DeleteAccountPageTests(TestCase):
    def test_delete_is_the_red_solid_button_and_cancel_the_blue_frame(self):
        self.client.force_login(
            consented_user(username="delete_redesign", password="redesign-pass")
        )
        main = _main(self.client.get(reverse("delete_account")))

        self.assertIn(
            '<p class="tip-box">想留一份紀錄的話，請先<a class="inline-link" href="'
            f'{reverse("download_my_data")}" download>下載我的資料</a>。</p>',
            main,
        )
        self.assertIn(
            '<button type="submit" class="btn btn-danger btn-lg w-full">刪除帳號</button>', main
        )
        self.assertIn(
            '<a class="btn btn-outline-primary btn-lg w-full" '
            f'href="{reverse("account_settings")}">取消</a>',
            main,
        )
        self.assertEqual(main.count("btn-primary"), 0)


class SignInPagesTests(TestCase):
    """D1 B: the title on the white page, no banner and no card laid over it."""

    def test_login_register_and_consent_have_a_plain_page_title(self):
        new_user = User.objects.create_user(username="consent_redesign")
        for name, title, user in (
            ("login", "登入", None),
            ("register", "註冊", None),
            ("consent", "開始使用之前", new_user),
        ):
            if user:
                self.client.force_login(user)
            with self.subTest(page=name):
                main = _main(self.client.get(reverse(name)))
                self.assertIn(f'<h1 class="h3 mt-4">{title}</h1>', main)
                self.assertNotIn("auth-hero", main)
                self.assertNotIn("auth-card", main)

    def test_the_login_error_is_in_a_red_box(self):
        User.objects.create_user(username="login_redesign", password="Xk9#mPq2vLw")

        main = _main(
            self.client.post(reverse("login"), {"username": "login_redesign", "password": "wrong"})
        )

        self.assertIn(
            '<div id="login_error" class="error-box" role="alert">使用者名稱或密碼錯誤</div>', main
        )

    def test_a_register_error_for_the_whole_form_is_in_a_red_box(self):
        def clean(form):
            raise ValidationError("假的整份表單錯誤")

        with patch.object(RegisterForm, "clean", clean):
            main = _main(self.client.post(reverse("register"), {"username": "whole_form"}))

        self.assertIn('<p class="error-box" role="alert">假的整份表單錯誤</p>', main)


class PrivacyNoticeTests(TestCase):
    def _main(self):
        return _main(self.client.get(reverse("privacy")))

    def test_the_highlights_stay_open_and_each_other_section_is_a_folded_row(self):
        main = self._main()
        folds = re.findall(
            r'<details class="fold-row">\s*<summary><h2 id="([\w-]+)"[^>]*>([^<]+)</h2>',
            main,
        )

        self.assertEqual(folds, PRIVACY_SECTIONS)
        self.assertNotIn("<details open", main)
        highlights = main[main.index("先看重點</h2>") : main.index("</section>")]
        self.assertIn('<ul class="tip-box">', highlights)
        self.assertNotIn("這一頁的段落", main)

    def test_the_contact_section_stays_open_at_the_end(self):
        main = self._main()

        self.assertGreater(main.index('id="contact-title"'), main.rindex("</details>"))
        self.assertIn('<h2 id="contact-title" class="h4">有問題或要刪除資料？</h2>', main)


class AddToHomeTests(TestCase):
    def test_each_phone_is_a_folded_row_and_its_steps_are_numbered_dots(self):
        main = _main(self.client.get(reverse("add_to_home")))
        rows = re.findall(r'<details class="fold-row">.*?</details>', main, re.S)

        self.assertEqual(len(rows), 2)
        for row, first_step in zip(
            rows, ("用 Safari 打開聽伴網站。", "用 Chrome 打開聽伴網站。"), strict=True
        ):
            with self.subTest(step=first_step):
                self.assertIn('<ol class="step-list" role="list">', row)
                self.assertIn(
                    '<li><span class="step-list-number">1</span>'
                    f'<span class="step-list-body">{first_step}</span></li>',
                    row,
                )
