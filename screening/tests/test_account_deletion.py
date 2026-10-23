from datetime import date
from unittest import mock

from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import reverse

from screening.models import (
    AidAndSubsidy,
    Answer,
    Audiogram,
    AudiogramPoint,
    Category,
    Consent,
    NormGroup,
    Question,
    Questionnaire,
    Submission,
    User,
)
from screening.tests.helpers import consented_user

PASSWORD = "Xk9#mPq2vLw"
DELETED_MESSAGE = "您的帳號和資料已經刪除"
STAFF_MESSAGE = "管理員帳號請先在後台移除管理員權限"


class DeleteAccountTests(TestCase):
    """Spec docs/specs/phase-07/phase7_account_deletion.md, acceptance 1-16."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code="hhie-s")
        cls.question = Question.objects.create(
            questionnaire=cls.hhie_s,
            question_text="假題目一",
            question_number=1,
            category=Category.EMOTIONAL,
        )
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code="ioi-ha")
        cls.ioi_question = Question.objects.create(
            questionnaire=cls.ioi_ha, question_text="假 IOI 題目", question_number=1
        )

    def setUp(self):
        self.url = reverse("delete_account")
        self.user = consented_user(username="delete_a", password=PASSWORD)
        self.other = consented_user(username="delete_b", password=PASSWORD)
        self.client.force_login(self.user)

    def _fill(self, user, submissions=1):
        for _ in range(submissions):
            submission = Submission.objects.create(user=user, questionnaire=self.hhie_s)
            Answer.objects.create(submission=submission, question=self.question, score=4)
        audiogram = Audiogram.objects.create(user=user, tested_on=date(2026, 3, 4))
        AudiogramPoint.objects.create(
            audiogram=audiogram, ear="right", conduction="air", frequency=1000, db=35
        )
        # #284 acceptance 22: 助聽器與補助資料 is PROTECT too.
        AidAndSubsidy.objects.create(user=user, has_certificate=True)

    def _counts(self, user_id):
        return {
            "user": User.objects.filter(pk=user_id).count(),
            "consents": Consent.objects.filter(user_id=user_id).count(),
            "submissions": Submission.objects.filter(user_id=user_id).count(),
            "answers": Answer.objects.filter(submission__user_id=user_id).count(),
            "audiograms": Audiogram.objects.filter(user_id=user_id).count(),
            "points": AudiogramPoint.objects.filter(audiogram__user_id=user_id).count(),
            "aid_and_subsidy": AidAndSubsidy.objects.filter(user_id=user_id).count(),
        }

    def _delete(self, password=PASSWORD, client=None):
        return (client or self.client).post(self.url, {"password": password})

    # 1
    def test_deletes_account_and_all_its_data(self):
        self._fill(self.user, submissions=2)
        user_id = self.user.pk
        before = {"user": 1, "consents": 1, "submissions": 2}
        before |= {"answers": 2, "audiograms": 1, "points": 1, "aid_and_subsidy": 1}
        self.assertEqual(self._counts(user_id), before)
        self._delete()
        self.assertEqual(set(self._counts(user_id).values()), {0})

    # 2
    def test_other_users_data_untouched(self):
        self._fill(self.user)
        self._fill(self.other)
        before = self._counts(self.other.pk)
        self._delete()
        self.assertEqual(self._counts(self.other.pk), before)

    # 3
    def test_logged_out_home_with_message_and_cannot_log_in(self):
        response = self._delete()
        self.assertRedirects(response, reverse("index"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(self.client.get(reverse("index")), DELETED_MESSAGE)
        self.assertFalse(self.client.login(username="delete_a", password=PASSWORD))

    # 4
    def test_other_device_is_signed_out_too(self):
        other_device = Client()
        other_device.force_login(self.user)
        self._delete()
        response = other_device.get(reverse("my_hearing"))
        self.assertTrue(response.url.startswith(reverse("login")))

    # 5
    def test_wrong_or_missing_password_deletes_nothing(self):
        self._fill(self.user)
        before = self._counts(self.user.pk)
        for password in ("wrong-password", ""):
            with self.subTest(password=password):
                response = self._delete(password=password)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="id_password_error"')
                self.assertContains(response, 'aria-invalid="true"')
                self.assertContains(response, 'aria-describedby="id_password_error"')
                self.assertContains(response, "autofocus")
                self.assertEqual(self._counts(self.user.pk), before)
        self.assertContains(self._delete(password="wrong-password"), "密碼不正確")

    def test_error_text_is_marked_as_a_field_error(self):
        # #272: field_messages.html tags each error so site.css puts a warning mark before it,
        # and the message does not rest on the red alone.
        response = self._delete(password="wrong-password")
        self.assertContains(
            response,
            '<div id="id_password_error">'
            '<p class="text-danger field-error mb-0">密碼不正確</p></div>',
            html=True,
        )

    # 6
    def test_signed_out_goes_to_login_and_back(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        response = self.client.post(
            reverse("login"), {"username": "delete_a", "password": PASSWORD, "next": self.url}
        )
        self.assertRedirects(response, self.url)

    # 7
    def test_get_only_shows_confirmation(self):
        self._fill(self.user, submissions=2)
        before = self._counts(self.user.pk)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "問卷紀錄 2 筆")
        self.assertContains(response, "聽力圖 1 張")
        self.assertContains(response, "無法復原")
        self.assertContains(response, f'href="{reverse("download_my_data")}"')
        self.assertContains(response, 'name="password"')
        # logout.js (on every page) clears unfinished answers when this form is sent.
        self.assertContains(response, 'id="delete-account-form"')
        self.assertEqual(self._counts(self.user.pk), before)

    # 8
    def test_post_without_csrf_token_is_403(self):
        self._fill(self.user)
        before = self._counts(self.user.pk)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = self._delete(client=client)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._counts(self.user.pk), before)

    # 9
    def test_database_error_midway_rolls_everything_back(self):
        self._fill(self.user)
        before = self._counts(self.user.pk)
        # The account goes last, so answers and records are already deleted when it fails.
        with (
            mock.patch.object(User, "delete", side_effect=DatabaseError),
            self.assertRaises(DatabaseError),
        ):
            self._delete()
        self.assertEqual(self._counts(self.user.pk), before)

    # 10
    def test_account_without_records_can_be_deleted(self):
        response = self.client.get(self.url)
        self.assertContains(response, "問卷紀錄 0 筆")
        self.assertContains(response, "聽力圖 0 張")
        self._delete()
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    # 11
    def test_ioi_ha_grouped_by_hhie_s_deletes_together(self):
        basis = Submission.objects.create(
            user=self.user, questionnaire=self.hhie_s, wearing_hearing_aid=False
        )
        Answer.objects.create(submission=basis, question=self.question, score=4)
        ioi_ha = Submission.objects.create(
            user=self.user,
            questionnaire=self.ioi_ha,
            norm_group=NormGroup.MILD_MODERATE,
            norm_basis=basis,
        )
        Answer.objects.create(submission=ioi_ha, question=self.ioi_question, score=3)
        self._delete()
        self.assertFalse(Submission.objects.filter(pk__in=[basis.pk, ioi_ha.pk]).exists())
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    # 12
    def test_same_username_can_register_again_with_nothing_old(self):
        self._fill(self.user)
        self._delete()
        response = self.client.post(
            reverse("register"),
            {
                "username": "delete_a",
                "email": "new@example.com",
                "password1": "Zq7!rTn4wPe",
                "password2": "Zq7!rTn4wPe",
            },
        )
        self.assertEqual(response.status_code, 302)
        new_user = User.objects.get(username="delete_a")
        self.assertEqual(new_user.submissions.count(), 0)
        self.assertEqual(new_user.audiograms.count(), 0)
        self.assertEqual(new_user.consents.count(), 0)

    # 13
    def test_user_without_consent_can_delete(self):
        user = User.objects.create_user(username="delete_old", password=PASSWORD)
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self._delete()
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    # 14
    def test_staff_and_superuser_cannot_delete_themselves(self):
        for flag in ("is_staff", "is_superuser"):
            with self.subTest(flag=flag):
                admin = consented_user(username=f"admin_{flag}", password=PASSWORD, **{flag: True})
                self._fill(admin)
                before = self._counts(admin.pk)
                self.client.force_login(admin)
                response = self.client.get(self.url)
                self.assertContains(response, STAFF_MESSAGE)
                self.assertNotContains(response, 'name="password"')
                self.assertEqual(self._delete().status_code, 403)
                self.assertEqual(self._counts(admin.pk), before)

    # 15
    def test_privacy_page_explains_deletion(self):
        self.client.logout()
        response = self.client.get(reverse("privacy"))
        self.assertContains(response, "自己刪除帳號")
        self.assertContains(response, "備份中的資料會在 6 小時內自動清除")
        self.assertContains(response, f'href="{self.url}"')

    # 16
    def test_history_page_links_to_deletion(self):
        for has_records in (False, True):
            if has_records:
                self._fill(self.user)
            with self.subTest(has_records=has_records):
                # The entry moved to account settings (spec phase9_ui_refresh_3_structure.md 4.2).
                response = self.client.get(reverse("account_settings"))
                self.assertContains(response, "刪除帳號")
                self.assertContains(response, f'href="{self.url}"')

    # 5 (review 1): spaces around a password are part of it, as on login and register.
    def test_password_with_surrounding_spaces_works(self):
        user = consented_user(username="delete_spaces", password=" pad Pass9# ")
        self.client.force_login(user)
        self._delete(password=" pad Pass9# ")
        self.assertFalse(User.objects.filter(pk=user.pk).exists())


class AidAndSubsidyDeletionTests(TestCase):
    """#287 (spec #284 acceptance 22, story 31): the 助聽器與補助資料, all four filled in, goes
    with the account, and the page says so first."""

    setUp = DeleteAccountTests.setUp
    _delete = DeleteAccountTests._delete

    def test_the_page_lists_it(self):
        response = self.client.get(self.url)
        self.assertContains(
            response,
            "<li>助聽器與補助資料（有沒有身障證明、開始配戴日期、戴哪一耳、補助方式和等級）</li>",
            html=True,
        )

    def test_all_four_filled_in_go_with_the_account(self):
        fields = {"fitted_on": date(2026, 5, 1), "ear": "both", "subsidy": "disability"}
        AidAndSubsidy.objects.create(user=self.user, has_certificate=True, level="mid", **fields)
        AidAndSubsidy.objects.create(user=self.other, has_certificate=False)
        self._delete()
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(
            list(AidAndSubsidy.objects.values_list("user", flat=True)), [self.other.pk]
        )
