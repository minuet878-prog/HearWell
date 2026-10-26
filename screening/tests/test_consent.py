import json
import re
import uuid
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth.views import redirect_to_login
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening import models
from screening.models import Audiogram, Consent, Questionnaire, Submission, User
from screening.tests import test_layout
from screening.tests.helpers import consented_user, fake_definition, register, step_bar

PASSWORD = "Xk9#mPq2vLw"
TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "screening"
HIGHLIGHTS = (
    "只用來算分數、給建議、保存您的紀錄，不拿去賣或做廣告。",
    "資料存在網站主機和資料庫；網站出錯時送去錯誤監控的內容，不包含您的名稱、作答或分數。",
    "您可以隨時要求查詢、更正或刪除您的資料。",
    "結果只是參考，不是醫療診斷。",
)


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

    def test_lists_only_services_the_site_still_uses(self):
        # #181, ADR 0014: cdnjs went with Bootstrap and the font comes from our own host, so
        # neither is listed; one fewer service was a minor fix that kept version 1 (#286 then
        # raised it to 2 for the 助聽器與補助資料).
        response = self.client.get(reverse("privacy"))
        self.assertNotContains(response, "cdnjs")
        self.assertNotContains(response, "Google")
        for service in ("Render", "Neon", "Sentry"):
            with self.subTest(service=service):
                self.assertContains(response, service)
        self.assertEqual(models.CONSENT_VERSION, 2)

    def test_no_placeholder_left(self):
        # Acceptance 16: operator, contact and regions are filled in before release.
        response = self.client.get(reverse("privacy"))
        self.assertNotContains(response, "待補")
        self.assertContains(response, "HearWell 開發者")
        # In the notice itself (who, requests, the contact card at the bottom since #197); the
        # site footer adds one more on every page.
        notice = response.content.decode().split('<footer class="site-footer"')[0]
        self.assertEqual(notice.count('href="mailto:hearwellweb@gmail.com"'), 3)
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


class PrivacyHighlightsTests(TestCase):
    """#197 (spec #183 stories 75-79): highlights on top, contact card at the bottom."""

    def _list_items(self, html):
        return [test_layout._text(item) for item in re.findall(r"<li>(.*?)</li>", html, re.S)]

    def _privacy_main(self):
        content = self.client.get(reverse("privacy")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def test_highlights_on_top_match_the_consent_page(self):
        main = self._privacy_main()
        # #361: the folded list of sections names them first; the sections come after it.
        main = main[main.index("</details>") :]
        top = main[main.index("先看重點") : main.index("誰在蒐集")]
        self.assertEqual(self._list_items(top), list(HIGHLIGHTS))
        self.client.force_login(User.objects.create_user(username="highlights_reader"))
        consent = self.client.get(reverse("consent")).content.decode()
        summary = consent[consent.index("重點") : consent.index("閱讀完整的隱私權說明")]
        self.assertEqual(self._list_items(summary), list(HIGHLIGHTS))

    def test_highlights_are_written_in_one_place(self):
        files = [
            path.name
            for path in TEMPLATES.rglob("*.html")
            if HIGHLIGHTS[1] in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(files, ["consent_highlights.html"])

    def test_full_text_stays_open_with_the_share_page_wording(self):
        main = self._privacy_main()
        # #361: only the list of sections on top folds (PrivacyPageT361Tests); the text is open.
        self.assertEqual(main.count("<details"), 1)
        main = main[main.index("</details>") :]
        sharing = main[main.index("您主動分享時") : main.index("您可以要求什麼")]
        self.assertIn("在「分享報告給家人」頁產生分享連結後", test_layout._text(sharing))
        self.assertNotIn("「聽力報告」頁", sharing)

    def test_contact_card_comes_last(self):
        main = self._privacy_main()
        last = main[main.index("有問題或要刪除資料？") :]
        self.assertGreater(main.index("有問題或要刪除資料？"), main.index("說明改版"))
        self.assertIn('href="mailto:hearwellweb@gmail.com"', last)
        self.assertIn("到「帳號設定」自己下載、刪除", test_layout._text(last))

    def test_aid_and_subsidy_is_listed_with_the_health_data(self):
        # #292 (spec #291 acceptance 25): every answer on the route and the chapters read,
        # written in once for the whole feature (spec #291's draft).
        main = self._privacy_main()
        main = main[main.index("</details>") :]
        collected = main[main.index("蒐集哪些資料") : main.index("存放在哪裡、保存多久")]
        # #361: the answers on the route are a list of their own (PrivacyPageT361Tests).
        self.assertIn(
            "健康資料：每一次篩檢問卷的作答和分數、作答時有沒有戴助聽器、您自己輸入的聽力圖、"
            "您在選配路線上的回答 有沒有聽覺機能的身心障礙證明 九號表與核定公文的進度 "
            "核定單耳或雙耳與補助等級 助聽器開始配戴的日期與戴哪一耳 有沒有用身障補助買 "
            "二十五號表完成了沒 以及您看過哪幾個選配指引章節。",
            test_layout._text(collected),
        )

    def test_spec_354_wording_is_a_minor_fix_that_moves_only_the_date(self):
        # #354 (owner, 2026-10-25): a minor fix, so the date moves and nobody agrees again.
        self.assertEqual(models.PRIVACY_UPDATED_ON, date(2026, 10, 25))
        self.assertEqual(models.CONSENT_VERSION, 2)

    def test_aid_and_subsidy_raises_the_version_so_everyone_agrees_again(self):
        # #286 (spec #284 acceptance 23): what is collected changed, so version 2.
        self.assertEqual(models.CONSENT_VERSION, 2)
        user = User.objects.create_user(username="agreed_to_version_1")
        Consent.objects.create(user=user, version=1)
        self.client.force_login(user)
        url = reverse("my_hearing")
        self.assertRedirects(self.client.get(url), _consent_url(url))
        self.client.post(reverse("consent"), {"agree": "", "next": url})
        self.assertEqual(self.client.get(url).status_code, 200)


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

    # #360 (spec #354): the title and step in the register page's blue banner, the rest below it
    # as flat blocks with no card (ADR 0022).
    def test_title_and_step_sit_in_the_register_banner_and_the_rest_below(self):
        main = self.client.get(reverse("consent")).content.decode()
        main = main.split('id="main-content"', 1)[1].split("</main>", 1)[0]
        start = main.index('<div class="auth-hero')
        end, depth = start, 0
        for tag in re.finditer(r"<(/?)div\b", main[start:]):
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                end = start + tag.end()
                break
        hero, below = main[start:end], main[end:]
        self.assertIn('<h1 class="auth-hero-title">開始使用之前</h1>', hero)
        self.assertIn("第 2 步／共 2 步：同意隱私權", hero)
        self.assertIn('class="auth-hero-bars"', hero)
        self.assertIn("HearWell 會保存您的篩檢作答", below)
        self.assertIn(">我同意，開始篩檢</button>", below)
        self.assertNotIn("card", below)

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
        bumped = models.CONSENT_VERSION + 1
        # User reads its own module's copy; the views read the package's (#380).
        with (
            mock.patch("screening.models.accounts.CONSENT_VERSION", bumped),
            mock.patch.object(models, "CONSENT_VERSION", bumped),
        ):
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


class PrivacyPageT361Tests(TestCase):
    """#361 (spec #354): a folded list of the sections on top, links that say where they go, the
    health data's answers as a list of their own, and the last heading like the others."""

    def setUp(self):
        content = self.client.get(reverse("privacy")).content.decode()
        self.main = content[content.index("<main") : content.index("</main>")]

    def _headings(self):
        return re.findall(r'<h2 id="([^"]+)" class="([^"]+)">(.*?)</h2>', self.main)

    def test_folded_list_of_sections_on_top_jumps_to_each(self):
        toc = re.search(
            r"<details([^>]*)>\s*<summary>(.*?)</summary>(.*?)</details>", self.main, re.S
        )
        self.assertIsNotNone(toc)
        attrs, summary, body = toc.groups()
        self.assertEqual(summary, "這一頁的段落")
        self.assertNotRegex(attrs, r"\bopen\b")
        # On top: before the first section, right under the title and version line.
        self.assertLess(self.main.index("<details"), self.main.index("<h2"))
        links = re.findall(r'<a href="#([^"]+)">(.*?)</a>', body)
        headings = self._headings()
        self.assertEqual(len(headings), 12)
        self.assertEqual(links, [(anchor, words) for anchor, _, words in headings])
        self.assertEqual(links[0], ("highlights-title", "先看重點"))
        self.assertEqual(links[-1], ("contact-title", "有問題或要刪除資料？"))

    def test_links_say_where_they_go(self):
        download = re.search(
            rf'<a [^>]*href="{reverse("download_my_data")}"[^>]*>(.*?)</a>', self.main
        )
        delete = re.search(rf'<a [^>]*href="{reverse("delete_account")}"[^>]*>(.*?)</a>', self.main)
        self.assertEqual(download.group(1), "下載我的資料")
        self.assertEqual(delete.group(1), "刪除帳號")
        for vague in ("這裡下載", "這裡刪除"):
            self.assertNotIn(vague, self.main)

    def test_route_answers_are_a_second_level_list_in_the_same_words(self):
        item = re.search(r"<li>(健康資料：.*?)</li>\s*<li>同意紀錄", self.main, re.S).group(1)
        inner = re.search(r"<ul>(.*?)</ul>", item, re.S).group(1)
        self.assertEqual(
            re.findall(r"<li>(.*?)</li>", inner),
            [
                "有沒有聽覺機能的身心障礙證明",
                "九號表與核定公文的進度",
                "核定單耳或雙耳與補助等級",
                "助聽器開始配戴的日期與戴哪一耳",
                "有沒有用身障補助買",
                "二十五號表完成了沒",
            ],
        )
        outer = re.sub(r"\s+", "", re.sub(r"<ul>.*?</ul>", "", item, flags=re.S))
        self.assertEqual(
            outer,
            "健康資料：每一次篩檢問卷的作答和分數、作答時有沒有戴助聽器、您自己輸入的聽力圖、"
            "您在選配路線上的回答以及您看過哪幾個選配指引章節。",
        )

    def test_every_section_heading_is_the_same_level(self):
        sizes = {
            tuple(c for c in classes.split() if c in ("h4", "h5", "heading-bar"))
            for _, classes, _ in self._headings()
        }
        self.assertEqual(sizes, {("h4",)})
