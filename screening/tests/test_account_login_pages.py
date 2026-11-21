"""#757 (spec #741 acceptance 52, 53; page grill P19, P20): account settings and login in the
canvas's new look (ProAccount, ProLogin), keeping what the pages say now and the LINE and Google
buttons as they are."""

import re

from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse

from screening.models import User
from screening.tests.helpers import consented_user

TAG = re.compile(r"<[^>]+>")
KEYS = {
    "GOOGLE_CLIENT_ID": "test-client-id",
    "GOOGLE_CLIENT_SECRET": "test-secret",
    "LINE_CLIENT_ID": "1234567890",
    "LINE_CLIENT_SECRET": "line-secret",
}


def _main(response):
    content = response.content.decode()
    return content[content.index("<main") : content.index("</main>")]


def _text(html):
    return re.sub(r"\s+", " ", TAG.sub("", html)).strip()


@override_settings(**KEYS)
class AccountSettingsLookTests(TestCase):
    def setUp(self):
        self.user = consented_user(username="jason", birth_year=1950)
        self.client.force_login(self.user)

    def _main(self):
        return _main(self.client.get(reverse("account_settings")))

    def test_the_account_card_has_the_initial_in_a_round_avatar_and_the_name(self):
        main = self._main()

        self.assertRegex(
            main,
            r'<div class="account-card">\s*'
            r'<span class="account-avatar" aria-hidden="true">J</span>\s*'
            r'<dl class="account-card-name">\s*<dt>使用者名稱</dt>\s*<dd>jason</dd>\s*</dl>',
        )

    def test_the_card_comes_under_my_account_and_before_the_email_and_birth_year(self):
        main = self._main()

        self.assertLess(main.index("我的帳號</h2>"), main.index('class="account-card"'))
        self.assertLess(main.index('class="account-card"'), main.index("電子郵件"))
        self.assertIn("民國 39 年（1950）", _text(main))

    def test_the_reminder_is_a_bell_beside_its_title_in_a_grey_box(self):
        # Spec #741 (the owner's pick at acceptance, compare-reminder.html C): no long purpose.
        main = self._main()
        section = main[main.index('id="retest-reminder"') : main.index('id="sign-in-methods"')]

        self.assertRegex(
            section,
            r'<div class="reminder-box">\s*<div class="reminder-head">\s*'
            r'<span class="reminder-bell" aria-hidden="true"><svg[^>]*>.*?</svg></span>\s*'
            r'<div>\s*<h2 id="retest-reminder-title" class="reminder-title">email 重測提醒</h2>',
        )
        self.assertNotIn("打開後，上次做完滿半年", section)

    def test_adding_an_email_or_a_way_to_sign_in_is_a_small_round_ended_button(self):
        main = self._main()

        self.assertIn(
            f'<a class="btn btn-outline-primary btn-pill" href="{reverse("add_email")}" '
            'aria-label="補上電子郵件">補上</a>',
            main,
        )
        self.assertIn(
            'btn btn-outline-primary btn-pill" href="/account/sign-in-methods/line/add"', main
        )
        self.assertIn(
            'btn btn-outline-primary btn-pill" href="/account/sign-in-methods/google/add"', main
        )

    def test_every_item_of_the_page_stays(self):
        text = _text(self._main())

        for words in (
            "出生年",
            "還沒有新增",
            "目前沒有分享",
            "把您在聽伴的所有資料下載成一個檔案保存。",
            "刪除後，帳號和所有紀錄都會消失，無法復原。",
        ):
            with self.subTest(words=words):
                self.assertIn(words, text)

    def test_the_red_delete_row_then_logout_last(self):
        main = self._main()

        self.assertIn("settings-card-danger", main)
        self.assertLess(main.index("settings-card-danger"), main.index('id="logout-form"'))
        self.assertTrue(_text(main).endswith("登出"))


@override_settings(**KEYS)
class LoginLookTests(TestCase):
    def test_the_line_and_google_buttons_are_their_own_partials_untouched(self):
        main = _main(self.client.get(reverse("login")))

        for partial in ("screening/line_button.html", "screening/google_button.html"):
            with self.subTest(partial=partial):
                self.assertIn(render_to_string(partial, {"label": "登入"}).strip(), main)
        self.assertIn("使用 LINE 帳號登入", main)
        self.assertIn("使用 Google 帳戶登入", main)

    def test_the_bird_says_welcome_back(self):
        main = _main(self.client.get(reverse("login")))

        self.assertIn('<p class="bird-lead">歡迎回來。</p>', main)

    def test_each_field_has_its_icon_inside(self):
        main = _main(self.client.get(reverse("login")))

        self.assertEqual(main.count('<div class="auth-input">'), 2)

    def test_forgot_password_is_bold_and_registering_is_its_own_grey_block(self):
        User.objects.create_user(username="someone")
        main = _main(self.client.get(reverse("login")))

        self.assertIn(
            f'<a class="inline-link font-bold" href="{reverse("password_reset")}">忘記密碼？</a>',
            main,
        )
        self.assertRegex(
            main,
            r'<div class="auth-alt">\s*<p>還沒有帳號？</p>\s*'
            rf'<a href="{reverse("register")}" class="w-full btn btn-lg btn-outline-primary">'
            r"註冊新帳號</a>",
        )
