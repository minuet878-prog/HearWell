import json
import uuid
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth.views import redirect_to_login
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening import models
from screening.models import Audiogram, Consent, Questionnaire, Submission, User
from screening.tests.helpers import consented_user, fake_definition, register, step_bar

PASSWORD = "Xk9#mPq2vLw"


def _consent_url(next_url):
    # Same "?next=" format Django uses for the login redirect.
    return redirect_to_login(next_url, reverse("consent")).url


class PrivacyPageTests(TestCase):
    """Spec phase7_consent_privacy.md, acceptance 1 and 2."""

    SECTIONS = (
        "誰在蒐集",
        "為什麼蒐集",
        "蒐集哪些資料",
        "存放在哪裡、保存多久",
        "會交給誰",
        "您可以要求什麼",
        "不提供資料會怎樣",
        "不是醫療診斷",
    )

    def test_anyone_can_read_it_with_version_and_date(self):
        response = self.client.get(reverse("privacy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"第 {models.CONSENT_VERSION} 版")
        self.assertContains(response, models.PRIVACY_UPDATED_ON.strftime("%Y/%m/%d"))
        for section in self.SECTIONS:
            with self.subTest(section=section):
                self.assertContains(response, section)

    def test_no_placeholder_left(self):
        # Acceptance 16: operator, contact and regions are filled in before release.
        response = self.client.get(reverse("privacy"))
        self.assertNotContains(response, "待補")
        self.assertContains(response, "HearWell 開發者")
        # In the notice itself; the site footer adds one more on every page.
        notice = response.content.decode().split('<footer class="site-footer"')[0]
        self.assertEqual(notice.count('href="mailto:hearwellweb@gmail.com"'), 2)
        self.assertContains(response, "美國俄亥俄州", count=2)

    def test_it_names_what_error_monitoring_sends(self):
        response = self.client.get(reverse("privacy"))
        self.assertContains(response, "Sentry")
        self.assertContains(response, "歐盟")

    def test_every_page_links_to_it_in_the_footer(self):
        user = consented_user(username="footer_reader")
        pages = ("index", "login", "register", "privacy")
        for name in pages:
            with self.subTest(page=name, logged_in=False):
                self._assert_footer_link(self.client.get(reverse(name)))
        self.client.force_login(user)
        for name in ("index", "my_hearing", "audiogram_list"):
            with self.subTest(page=name, logged_in=True):
                self._assert_footer_link(self.client.get(reverse(name)))

    def test_register_page_also_links_near_the_button(self):
        response = self.client.get(reverse("register"))
        form_part = response.content.decode().split("<footer")[0]
        self.assertIn(f'href="{reverse("privacy")}"', form_part)

    def _assert_footer_link(self, response):
        footer = response.content.decode().split("<footer", 1)[1]
        self.assertIn(f'href="{reverse("privacy")}"', footer)


class NewUserTests(TestCase):
    """Acceptance 3."""

    def _register(self, next_url=None):
        data = {
            "username": "newcomer",
            "email": "newcomer@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        if next_url:
            data["next"] = next_url
        return self.client.post(reverse("register"), data)

    def test_register_leads_to_consent_without_a_record(self):
        response = self._register()
        self.assertRedirects(response, reverse("consent"))
        self.assertFalse(Consent.objects.exists())

    def test_register_keeps_where_they_were_going(self):
        target = reverse("questionnaire_list")
        self.assertRedirects(self._register(target), _consent_url(target))


class ConsentPageTests(TestCase):
    """Acceptance 4, 5, 6."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="undecided", password=PASSWORD)

    def setUp(self):
        self.client.force_login(self.user)

    def test_page_shows_summary_full_text_link_and_two_buttons(self):
        response = self.client.get(reverse("consent"))
        self.assertContains(response, "重點")
        self.assertContains(response, f'href="{reverse("privacy")}"')
        self.assertContains(response, ">我同意，開始篩檢</button>")
        self.assertContains(response, ">不同意</button>")

    def test_step_two_of_two_with_progress_bar(self):
        # Issue #151.
        response = self.client.get(reverse("consent"))
        self.assertContains(response, "第 2 步／共 2 步：同意隱私權")
        self.assertEqual(step_bar(response), (2, 2))

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        self.assertRedirects(
            self.client.get(reverse("consent")), redirect_to_login(reverse("consent")).url
        )

    def test_agree_records_time_and_version_then_goes_back(self):
        target = reverse("my_hearing")
        before = timezone.now()
        response = self.client.post(reverse("consent"), {"agree": "", "next": target})
        self.assertRedirects(response, target)
        consent = Consent.objects.get(user=self.user)
        self.assertEqual(consent.version, models.CONSENT_VERSION)
        self.assertGreaterEqual(consent.agreed_at, before)

    def test_agree_without_next_goes_home(self):
        response = self.client.post(reverse("consent"), {"agree": ""})
        self.assertRedirects(response, reverse("index"))

    def test_agree_with_external_next_goes_home(self):
        for bad in ("https://evil.example.com", "//evil.example.com"):
            with self.subTest(next=bad):
                Consent.objects.all().delete()
                response = self.client.post(reverse("consent"), {"agree": "", "next": bad})
                self.assertRedirects(response, reverse("index"))

    def test_next_is_kept_on_the_page(self):
        target = reverse("my_hearing")
        response = self.client.get(_consent_url(target))
        self.assertContains(
            response, f'<input type="hidden" name="next" value="{target}">', html=True
        )

    def test_decline_logs_out_and_explains_without_touching_the_account(self):
        questionnaire = Questionnaire.objects.create(questionnaire_name="測試問卷", code="test")
        Submission.objects.create(user=self.user, questionnaire=questionnaire)
        response = self.client.post(reverse("consent"), {"decline": ""}, follow=True)
        self.assertRedirects(response, reverse("index"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "沒有同意就不能使用篩檢功能，您的帳號仍在")
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(Submission.objects.filter(user=self.user).count(), 1)
        self.assertFalse(Consent.objects.exists())

    def test_get_does_not_record_consent(self):
        self.client.get(reverse("consent"))
        self.assertFalse(Consent.objects.exists())

    def test_already_consented_is_sent_on(self):
        Consent.objects.create(user=self.user, version=models.CONSENT_VERSION)
        self.assertRedirects(self.client.get(reverse("consent")), reverse("index"))
        target = reverse("my_hearing")
        self.assertRedirects(self.client.get(_consent_url(target)), target)


class GateTests(TestCase):
    """Acceptance 7, 8, 9, 11."""

    @classmethod
    def setUpTestData(cls):
        # Existed before this release: data but no consent record.
        cls.user = User.objects.create_user(username="old_timer", password=PASSWORD)
        cls.questionnaire = Questionnaire.objects.create(questionnaire_name="測試問卷", code="test")
        cls.submission = Submission.objects.create(user=cls.user, questionnaire=cls.questionnaire)
        cls.audiogram = Audiogram.objects.create(user=cls.user, tested_on=date(2026, 1, 1))

    def setUp(self):
        self.enterContext(register(fake_definition("test")))

    def _health_urls(self):
        return (
            reverse("questionnaire_list"),
            reverse("screening", args=[self.questionnaire.id]),
            reverse("my_hearing"),
            reverse("result", args=[self.submission.id]),
            reverse("audiogram_list"),
            reverse("audiogram_new"),
            reverse("audiogram_compare"),
            reverse("audiogram_detail", args=[self.audiogram.id]),
            reverse("audiogram_edit", args=[self.audiogram.id]),
            reverse("audiogram_delete", args=[self.audiogram.id]),
        )

    def test_existing_account_sees_consent_after_login_and_keeps_data(self):
        response = self.client.post(
            reverse("login"), {"username": "old_timer", "password": PASSWORD}, follow=True
        )
        self.assertEqual(response.request["PATH_INFO"], reverse("consent"))
        self.assertEqual(Submission.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Audiogram.objects.filter(user=self.user).count(), 1)

    def test_health_pages_lead_to_consent_and_back(self):
        self.client.force_login(self.user)
        for url in self._health_urls():
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url), _consent_url(url), fetch_redirect_response=False
                )

    def test_post_to_health_pages_is_blocked_too(self):
        self.client.force_login(self.user)
        url = reverse("audiogram_delete", args=[self.audiogram.id])
        self.client.post(url)
        self.assertTrue(Audiogram.objects.filter(pk=self.audiogram.pk).exists())

    def test_back_to_the_page_after_agreeing(self):
        self.client.force_login(self.user)
        target = reverse("my_hearing")
        response = self.client.post(reverse("consent"), {"agree": "", "next": target})
        self.assertRedirects(response, target)

    def test_open_pages_stay_open(self):
        self.client.force_login(self.user)
        for name in ("index", "privacy", "add_to_home", "consent"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("index"))

    def test_someone_elses_consent_does_not_count(self):
        consented_user(username="agreed")
        self.client.force_login(self.user)
        url = reverse("my_hearing")
        self.assertRedirects(self.client.get(url), _consent_url(url))


class ApiGateTests(TestCase):
    """Acceptance 10, 11."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="api_undecided")
        consented_user(username="api_agreed")

    def _urls(self):
        return (reverse("api:submissions"), reverse("api:questionnaires"))

    def test_blocked_with_403_until_agreed(self):
        self.client.force_login(self.user)
        for url in self._urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        Consent.objects.create(user=self.user, version=models.CONSENT_VERSION)
        for url in self._urls():
            with self.subTest(url=url, agreed=True):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_writes_are_blocked_too(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("api:audiograms"), {}, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Audiogram.objects.exists())

    def test_writes_work_once_agreed(self):
        self.client.force_login(self.user)
        self.user.give_consent()
        body = {
            "tested_on": "2026-10-01",
            "points": [
                {"ear": "right", "conduction": "air", "frequency": f, "db": 40}
                for f in (500, 1000, 2000, 4000)
            ],
        }
        response = self.client.post(
            reverse("api:audiograms"),
            json.dumps(body),
            content_type="application/json",
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Audiogram.objects.get().user, self.user)

    def test_anonymous_unchanged(self):
        for url in self._urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)


class RevisionTests(TestCase):
    """Acceptance 12, 13."""

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="reader")

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("my_hearing")

    def test_major_revision_asks_again_and_keeps_the_old_record(self):
        with mock.patch.object(models, "CONSENT_VERSION", models.CONSENT_VERSION + 1):
            self.assertRedirects(self.client.get(self.url), _consent_url(self.url))
            self.client.post(reverse("consent"), {"agree": "", "next": self.url})
            self.assertEqual(self.client.get(self.url).status_code, 200)
        versions = list(
            Consent.objects.filter(user=self.user).order_by("id").values_list("version", flat=True)
        )
        self.assertEqual(versions, [models.CONSENT_VERSION, models.CONSENT_VERSION + 1])

    def test_minor_revision_does_not_ask_again(self):
        later = models.PRIVACY_UPDATED_ON + timedelta(days=30)
        with mock.patch.object(models, "PRIVACY_UPDATED_ON", later):
            self.assertEqual(self.client.get(self.url).status_code, 200)
            self.assertContains(self.client.get(reverse("privacy")), later.strftime("%Y/%m/%d"))
