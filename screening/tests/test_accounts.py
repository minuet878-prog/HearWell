import re
from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from screening.models import Questionnaire, Submission, User


class SubmissionResultAccessTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="user_a")
        self.user_b = User.objects.create_user(username="user_b")
        self.questionnaire = Questionnaire.objects.create(
            questionnaire_name="測試問卷", code="test"
        )
        self.submission = Submission.objects.create(
            user=self.user_a, questionnaire=self.questionnaire
        )

    def test_user_cannot_view_others_submission(self):
        self.client.force_login(self.user_b)
        url = reverse("result", kwargs={"submission_id": self.submission.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class LoginRequiredTests(TestCase):
    def test_not_login_visit_can_redirect(self):
        protected_url = reverse("my_hearing")
        response = self.client.get(protected_url)
        login_url = reverse("login")
        expected_reversed_url = f"{login_url}?next={protected_url}"
        self.assertRedirects(response, expected_reversed_url)


class LoginNextTests(TestCase):
    NOTE = "請先登入，沒有帳號請按註冊。登入後會帶您回到剛剛的頁面。"
    HINT = "第一次使用請先註冊，已有帳號請直接登入。"
    PASSWORD = "Xk9#mPq2vLw"
    EXTERNAL = (
        "https://evil.example.com",
        "//evil.example.com",
        "/\\evil.example.com",
        "javascript:alert(1)",
    )

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tester", password=cls.PASSWORD)

    def setUp(self):
        self.target = reverse("questionnaire_list")
        self.login_url = f"{reverse('login')}?next={self.target}"
        self.register_url = f"{reverse('register')}?next={self.target}"

    def _login(self, next_url=None, password=None):
        data = {"username": "tester", "password": password or self.PASSWORD}
        if next_url is not None:
            data["next"] = next_url
        return self.client.post(reverse("login"), data)

    def _register(self, next_url=None, username="newcomer", confirmation=None):
        data = {
            "username": username,
            "email": f"{username}@example.com",
            "password1": self.PASSWORD,
            "password2": confirmation or self.PASSWORD,
        }
        if next_url is not None:
            data["next"] = next_url
        return self.client.post(reverse("register"), data)

    def _assert_next_kept(self, response):
        self.assertContains(
            response, f'<input type="hidden" name="next" value="{self.target}">', html=True
        )

    def test_cta_leads_to_login_with_note(self):
        self.assertContains(self.client.get(reverse("index")), f'href="{self.target}"')
        response = self.client.get(self.target, follow=True)
        self.assertRedirects(response, self.login_url)
        self.assertContains(response, self.NOTE)

    def test_plain_login_page_has_no_note(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, self.NOTE)

    def test_login_redirects_to_next(self):
        self.assertRedirects(self._login(self.target), self.target)

    def test_login_without_next_goes_home(self):
        self.assertRedirects(self._login(), reverse("index"))

    def test_next_kept_after_wrong_password(self):
        response = self._login(self.target, password="wrong-password")
        self.assertContains(response, "使用者名稱或密碼錯誤")
        self.assertContains(response, self.NOTE)
        self._assert_next_kept(response)
        self.assertRedirects(self._login(self.target), self.target)

    def test_external_next_is_ignored_on_login(self):
        for bad in self.EXTERNAL:
            with self.subTest(next=bad):
                self.client.logout()
                response = self.client.get(f"{reverse('login')}?next={bad}")
                self.assertNotContains(response, self.NOTE)
                self.assertRedirects(self._login(bad), reverse("index"))

    def test_register_link_carries_next_and_register_redirects(self):
        response = self.client.get(self.login_url)
        self.assertContains(response, f'href="{self.register_url}"')
        self.assertRedirects(self._register(self.target), self.target)

    def test_next_kept_after_register_error(self):
        response = self._register(self.target, confirmation="Different#123")
        self.assertContains(response, "輸入的兩個密碼不一致。")
        self._assert_next_kept(response)
        self.assertRedirects(self._register(self.target), self.target)

    def test_login_link_on_register_page_carries_next(self):
        response = self.client.get(self.register_url)
        self._assert_next_kept(response)
        self.assertContains(response, f'href="{self.login_url}"')
        self.assertContains(self.client.get(self.login_url), self.NOTE)

    def test_external_next_is_ignored_on_register(self):
        for i, bad in enumerate(self.EXTERNAL):
            with self.subTest(next=bad):
                self.client.logout()
                response = self._register(bad, username=f"newcomer{i}")
                self.assertRedirects(response, reverse("index"))

    def test_next_is_escaped_in_html(self):
        response = self.client.get(reverse("login"), {"next": '/x"><script>alert(1)</script>'})
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_home_hint_only_for_anonymous(self):
        self.assertContains(self.client.get(reverse("index")), self.HINT)
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse("index")), self.HINT)

    def test_new_text_uses_readable_style(self):
        self.assertContains(
            self.client.get(self.login_url),
            f'<p class="text-body-emphasis">{self.NOTE}</p>',
            html=True,
        )
        self.assertContains(
            self.client.get(reverse("index")),
            f'<p class="text-body-emphasis mt-2">{self.HINT}</p>',
            html=True,
        )


class RegisterFormTests(TestCase):
    PASSWORD = "Xk9#mPq2vLw"
    NOTE = "選填。用來推薦適合您年齡的問卷，不會公開。"

    def setUp(self):
        self.url = reverse("register")
        self.max_roc = date.today().year - 18 - 1911
        self.range_error = f"請輸入民國 1 到 {self.max_roc} 年之間的數字"

    def _post(self, **overrides):
        data = {
            "username": "newcomer",
            "email": "newcomer@example.com",
            "password1": self.PASSWORD,
            "password2": self.PASSWORD,
            "roc_birth_year": "",
            **overrides,
        }
        return self.client.post(self.url, data)

    def test_register_page_fields(self):
        response = self.client.get(self.url)
        for name in ("username", "email", "password1", "password2", "roc_birth_year"):
            self.assertContains(response, f'name="{name}"')
        self.assertContains(response, "民國")
        self.assertContains(response, self.NOTE)
        self.assertContains(response, "<li>你的密碼必須包含至少 8 個字元。</li>", html=True)

    def test_register_without_birth_year(self):
        response = self._post()
        self.assertRedirects(response, reverse("index"))
        user = User.objects.get(username="newcomer")
        self.assertIsNone(user.birth_year)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_roc_year_is_stored_as_western_year(self):
        self._post(roc_birth_year="44")
        self.assertEqual(User.objects.get(username="newcomer").birth_year, 1955)

    def test_roc_year_boundaries_accepted(self):
        for i, roc in enumerate((1, self.max_roc)):
            with self.subTest(roc=roc):
                self.client.logout()
                self._post(
                    username=f"edge{i}", email=f"edge{i}@example.com", roc_birth_year=str(roc)
                )
                self.assertEqual(User.objects.get(username=f"edge{i}").birth_year, roc + 1911)

    def test_invalid_roc_year_rejected(self):
        for value in ("0", str(self.max_roc + 1), "abc", "1955", "²"):
            with self.subTest(value=value):
                response = self._post(roc_birth_year=value)
                self.assertFalse(User.objects.exists())
                self.assertIn(self.range_error, response.context["form"].errors["roc_birth_year"])
                self.assertContains(response, self.range_error)

    def test_password_mismatch_keeps_input(self):
        response = self._post(password2="Different#123", roc_birth_year="44")
        self.assertFalse(User.objects.exists())
        self.assertIn("輸入的兩個密碼不一致。", response.context["form"].errors["password2"])
        self.assertContains(response, 'value="newcomer"')
        self.assertContains(response, 'value="newcomer@example.com"')
        self.assertContains(response, 'value="44"')
        self.assertNotContains(response, self.PASSWORD)
        self.assertContains(response, "你的密碼必須包含至少 8 個字元。")

    def test_duplicate_username_rejected(self):
        User.objects.create_user(username="newcomer")
        response = self._post()
        self.assertEqual(User.objects.count(), 1)
        for error in response.context["form"].errors["username"]:
            self.assertContains(response, error)

    def test_required_fields(self):
        for field in ("username", "email", "password1"):
            with self.subTest(field=field):
                response = self._post(**{field: ""})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(User.objects.exists())
                self.assertIn("這個欄位是必須的。", response.context["form"].errors[field])

    def test_password_similar_to_username_rejected(self):
        response = self._post(
            username="hearwellsenior", password1="hearwellsenior1", password2="hearwellsenior1"
        )
        self.assertFalse(User.objects.exists())
        errors = response.context["form"].errors["password2"]
        self.assertTrue(any("使用者名稱太相近" in error for error in errors), errors)

    def test_age_from_birth_year(self):
        self.assertEqual(User(birth_year=1955).age, date.today().year - 1955)
        self.assertIsNone(User().age)

    def test_note_uses_readable_style(self):
        self.assertContains(
            self.client.get(self.url),
            f'<div id="id_roc_birth_year_helptext" class="text-body-emphasis mt-1">'
            f"{self.NOTE}</div>",
            html=True,
        )

    def test_password_rules_use_rem_size(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, "form-text")
        self.assertContains(response, 'id="id_password1_helptext" class="text-body-emphasis mt-1"')

    def test_aria_describedby_targets_exist(self):
        response = self._post(username="", password2="Different#123", roc_birth_year="abc")
        content = response.content.decode()
        targets = re.findall(r'aria-describedby="([^"]+)"', content)
        self.assertTrue(targets)
        for ids in targets:
            for target in ids.split():
                with self.subTest(target=target):
                    self.assertIn(f'id="{target}"', content)


class BirthYearMigrationTests(TransactionTestCase):
    before = (("screening", "0014_submission_wearing_hearing_aid"),)
    after = (("screening", "0016_remove_user_birth_date"),)

    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(list(targets))
        return executor.loader.project_state(list(targets)).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_birth_date_year_is_kept(self):
        old_user = self._migrate(self.before).get_model("screening", "User")
        old_user.objects.create(username="with_date", birth_date=date(1955, 6, 1))
        old_user.objects.create(username="without_date")
        new_user = self._migrate(self.after).get_model("screening", "User")
        self.assertEqual(new_user.objects.get(username="with_date").birth_year, 1955)
        self.assertIsNone(new_user.objects.get(username="without_date").birth_year)
