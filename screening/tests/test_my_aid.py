"""#286 (spec #284): 我的助聽器與補助, the form and its summary card on 我的選配指引."""

import re
from datetime import date, timedelta

from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening import models
from screening.models import AidAndSubsidy, Consent, User
from screening.tests import test_answering, test_layout
from screening.tests.helpers import consented_user

UNFILLED = "填了這裡，選配路線才知道您有沒有身障證明、什麼時候開始戴助聽器。"
RADIO = r'<input type="radio" name="{}" value="[^"]*"([^>]*)>\s*([^<]*)</label>'


def choices(content, name):
    """(label, checked) of each radio button of one question, in page order."""
    found = re.findall(RADIO.format(name), content)
    return [(label.strip(), " checked" in attrs) for attrs, label in found]


class MyAidFormTests(TestCase):
    """#284 acceptance 1 (the certificate question), 4, 24."""

    def setUp(self):
        self.user = consented_user(username="aid_owner")
        self.client.force_login(self.user)
        self.url = reverse("my_aid")

    def aid(self, user=None):
        return AidAndSubsidy.objects.get(user=user or self.user)

    def post(self, has_certificate):
        return self.client.post(self.url, {"has_certificate": has_certificate})

    def chosen(self):
        content = self.client.get(self.url).content.decode()
        return [label for label, on in choices(content, "has_certificate") if on]

    # 1
    def test_nothing_filled_in_has_not_answering_chosen(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertRegex(content, r"<h1[^>]*>我的助聽器與補助</h1>")
        self.assertRegex(content, r"<legend[^>]*>您有聽覺機能的身心障礙證明嗎？</legend>")
        self.assertIn("第二類 b230、s260，或舊制 02", content)
        self.assertEqual(
            choices(content, "has_certificate"),
            [("不填", True), ("有", False), ("還沒有", False)],
        )

    def test_saving_has_goes_back_to_the_guide(self):
        response = self.post("True")
        self.assertRedirects(response, reverse("guide"), fetch_redirect_response=False)
        self.assertIs(self.aid().has_certificate, True)
        self.assertEqual(self.chosen(), ["有"])

    def test_saving_not_yet(self):
        self.post("False")
        self.assertIs(self.aid().has_certificate, False)
        self.assertEqual(self.chosen(), ["還沒有"])

    # 4
    def test_not_answering_clears_the_answer_and_the_route_with_it(self):
        self.post("True")
        self.post("")
        self.assertIsNone(self.aid().has_certificate)
        self.assertEqual(AidAndSubsidy.objects.filter(user=self.user).count(), 1)
        self.assertEqual(self.chosen(), ["不填"])
        route = self.client.get(reverse("guide")).content.decode()
        self.assertRegex(route, r'data-stop="audiogram" aria-current="step"')

    def test_only_the_users_own_answer_is_read_and_changed(self):
        other = consented_user(username="aid_other")
        AidAndSubsidy.objects.create(user=other, has_certificate=False)
        self.assertEqual(self.chosen(), ["不填"])
        self.post("True")
        self.assertIs(self.aid(other).has_certificate, False)
        self.assertIs(self.aid().has_certificate, True)

    # 24
    def test_signed_out_goes_to_login_and_back(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False
        )
        self.post("True")
        self.assertFalse(AidAndSubsidy.objects.exists())

    def test_without_agreeing_to_this_version_goes_to_consent(self):
        user = User.objects.create_user(username="aid_earlier_version")
        Consent.objects.create(user=user, version=models.CONSENT_VERSION - 1)
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('consent')}?next={self.url}", fetch_redirect_response=False
        )
        self.post("True")
        self.assertFalse(AidAndSubsidy.objects.exists())

    def test_never_cached(self):
        for response in (self.client.get(self.url), self.client.post(self.url, {})):
            with self.subTest(method=response.request["REQUEST_METHOD"]):
                self.assertIn("no-store", response["Cache-Control"])

    def test_other_methods_are_405(self):
        self.assertEqual(self.client.put(self.url).status_code, 405)


class AidSummaryCardTests(TestCase):
    """#286: the 我的助聽器與補助 card above the route on 我的選配指引 (#284 acceptance 25)."""

    def setUp(self):
        self.user = consented_user(username="aid_card_reader")
        self.client.force_login(self.user)

    def page(self):
        return self.client.get(reverse("guide")).content.decode()

    def card(self):
        found = re.search(
            r'<section [^>]*aria-labelledby="aid-title".*?</section>', self.page(), re.S
        )
        return found and found.group(0)

    def assert_link(self, card, text):
        self.assertRegex(card, rf'<a [^>]*href="{reverse("my_aid")}"[^>]*>{text}</a>')

    def test_nothing_filled_in_says_why_and_links_to_fill_it_in(self):
        card = self.card()
        self.assertRegex(card, r">我的助聽器與補助</h2>")
        self.assertIn(UNFILLED, test_layout._text(card))
        self.assert_link(card, "去填")
        self.assertNotIn("身障證明：", card)

    def test_a_row_with_nothing_answered_is_nothing_filled_in(self):
        AidAndSubsidy.objects.create(user=self.user, has_certificate=None)
        self.assertIn(UNFILLED, test_layout._text(self.card()))

    def test_the_certificate_answer_with_a_link_to_change_it(self):
        for has_certificate, said in ((True, "身障證明：有"), (False, "身障證明：還沒有")):
            with self.subTest(said=said):
                AidAndSubsidy.objects.update_or_create(
                    user=self.user, defaults={"has_certificate": has_certificate}
                )
                card = self.card()
                self.assertIn(said, test_layout._text(card))
                self.assertNotIn(UNFILLED, test_layout._text(card))
                self.assert_link(card, "修改")

    def test_the_card_comes_just_before_the_route(self):
        page = self.page()
        card = page.index('aria-labelledby="aid-title"')
        self.assertLess(card, page.index('id="contents-title"'))

    # 25
    def test_signed_out_has_no_card(self):
        self.client.logout()
        self.assertIsNone(self.card())


class HearingAidCardTests(TestCase):
    """#287 (spec #284 acceptance 2): the hearing aids and the subsidy on the summary card,
    a line left blank not shown."""

    def setUp(self):
        self.user = consented_user(username="aid_card_wearer")
        self.client.force_login(self.user)

    card = AidSummaryCardTests.card
    page = AidSummaryCardTests.page

    def text(self, **fields):
        AidAndSubsidy.objects.update_or_create(user=self.user, defaults=fields)
        return test_layout._text(self.card())

    def test_everything_filled_in(self):
        text = self.text(
            has_certificate=True,
            fitted_on=date(2026, 5, 1),
            ear="both",
            subsidy="disability",
            level="mid",
        )
        for line in ("身障證明：有", "助聽器：雙耳，2026/05/01 開始戴", "補助：用身障補助，中階型"):
            with self.subTest(line=line):
                self.assertIn(line, text)

    def test_only_what_is_filled_in(self):
        for fields, shown, hidden in (
            ({"ear": "left"}, "助聽器：左耳", ("身障證明：", "補助：", "開始戴")),
            ({"fitted_on": date(2026, 5, 1)}, "助聽器：2026/05/01 開始戴", ("補助：", "耳")),
            ({"subsidy": "other"}, "補助：自費或其他補助", ("助聽器：", "，")),
            ({"subsidy": "disability"}, "補助：用身障補助", ("助聽器：", "，")),
            ({"subsidy": "disability", "level": "unknown"}, "補助：用身障補助，等級不知道", ()),
        ):
            with self.subTest(fields=fields):
                AidAndSubsidy.objects.filter(user=self.user).delete()
                text = self.text(**fields)
                self.assertIn(shown, text)
                self.assertNotIn(UNFILLED, text)
                for words in hidden:
                    self.assertNotIn(words, text)

    def test_with_nothing_answered_the_card_asks_to_fill_it_in(self):
        self.assertIn(UNFILLED, self.text(has_certificate=None, ear="", subsidy=""))


class HearingAidQuestionsTests(TestCase):
    """#287 (spec #284 acceptance 1-3, 5, 6): the fitting date, the ear, the subsidy and its
    level."""

    def setUp(self):
        self.user = consented_user(username="aid_wearer")
        self.client.force_login(self.user)
        self.url = reverse("my_aid")

    def aid(self):
        return AidAndSubsidy.objects.get(user=self.user)

    def content(self):
        return self.client.get(self.url).content.decode()

    def post(self, **fields):
        data = {"has_certificate": "", "fitted_on": "", "ear": "", "subsidy": "", "level": ""}
        return self.client.post(self.url, data | fields)

    # 1
    def test_nothing_filled_in_has_not_answering_chosen_everywhere(self):
        content = self.content()
        self.assertRegex(content, r"<legend[^>]*>戴哪一耳？</legend>")
        self.assertEqual(
            choices(content, "ear"),
            [("不填", True), ("左耳", False), ("右耳", False), ("雙耳", False)],
        )
        self.assertRegex(content, r"<legend[^>]*>這副助聽器有沒有用身障補助買？</legend>")
        self.assertEqual(
            choices(content, "subsidy"),
            [("不填", True), ("用身障補助（有九號表）", False), ("自費或其他補助", False)],
        )
        self.assertRegex(content, r"<legend[^>]*>補助的等級是？</legend>")
        self.assertIn("選了用身障補助才需要填", content)
        self.assertEqual(
            choices(content, "level"),
            [
                ("不填", True),
                ("簡易型", False),
                ("中階型", False),
                ("進階型", False),
                ("雙對側傳聲型", False),
                ("不知道", False),
            ],
        )

    def test_the_fitting_date_is_a_date_field_up_to_today(self):
        content = self.content()
        label = re.search(
            r'<label for="([^"]+)"[^>]*>目前這副助聽器哪一天開始戴？</label>', content
        )
        self.assertIsNotNone(label)
        field = re.search(rf'<input [^>]*id="{label.group(1)}"[^>]*>', content).group(0)
        self.assertIn('type="date"', field)
        self.assertIn(f'max="{timezone.localdate().isoformat()}"', field)
        self.assertNotIn("value=", field)
        self.assertIn("可以看購買收據或保固書上的日期。", content)

    # 2
    def test_saving_all_five_goes_back_to_the_guide_and_shows_them_again(self):
        response = self.post(
            has_certificate="True",
            fitted_on="2026-05-01",
            ear="both",
            subsidy="disability",
            level="mid",
        )
        self.assertRedirects(response, reverse("guide"), fetch_redirect_response=False)
        aid = self.aid()
        self.assertEqual(
            (aid.has_certificate, aid.fitted_on, aid.ear, aid.subsidy, aid.level),
            (True, date(2026, 5, 1), "both", "disability", "mid"),
        )
        content = self.content()
        self.assertRegex(content, r'<input type="date" name="fitted_on" value="2026-05-01"')
        for name, label in (
            ("ear", "雙耳"),
            ("subsidy", "用身障補助（有九號表）"),
            ("level", "中階型"),
        ):
            with self.subTest(name=name):
                self.assertEqual([c for c, on in choices(content, name) if on], [label])

    # 3
    def test_changing_to_paying_otherwise_clears_the_level(self):
        self.post(subsidy="disability", level="mid")
        self.post(subsidy="other", level="mid")
        self.assertEqual((self.aid().subsidy, self.aid().level), ("other", ""))

    def test_not_answering_the_subsidy_clears_the_level_too(self):
        self.post(subsidy="disability", level="advanced")
        self.post(subsidy="", level="advanced")
        self.assertEqual((self.aid().subsidy, self.aid().level), ("", ""))

    def test_not_answering_clears_the_date_and_the_ear(self):
        self.post(fitted_on="2026-05-01", ear="left")
        self.post()
        self.assertEqual((self.aid().fitted_on, self.aid().ear), (None, ""))

    # 5
    def test_a_date_after_today_is_not_saved_and_marked_on_the_field(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        response = self.post(fitted_on=tomorrow.isoformat(), ear="left")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AidAndSubsidy.objects.filter(user=self.user).exists())
        content = response.content.decode()
        field = re.search(r'<input type="date" name="fitted_on"[^>]*>', content).group(0)
        self.assertIn('aria-invalid="true"', field)
        self.assertIn("id_fitted_on_error", field)
        self.assertRegex(content, r'<div id="id_fitted_on_error">\s*<p class="text-danger')
        self.assertIn("開始配戴日期不能是未來", content)

    def test_today_is_saved(self):
        self.post(fitted_on=timezone.localdate().isoformat())
        self.assertEqual(self.aid().fitted_on, timezone.localdate())

    # 6
    def test_without_javascript_the_level_shows_and_paying_otherwise_drops_it(self):
        content = self.content()
        level = re.search(r"<fieldset[^>]*data-aid-level[^>]*>", content).group(0)
        self.assertNotIn("hidden", level)
        self.assertIn(f'src="{static("screening/frontend/my-aid.js")}"', content)
        self.post(subsidy="other", level="basic")
        self.assertEqual(self.aid().level, "")

    def test_the_script_is_built(self):
        config = test_answering.ReactAnswerPageTests.VITE_CONFIG.read_text(encoding="utf-8")
        self.assertIn('"my-aid": "src/my-aid.js"', config)


class NotAnsweringRouteTests(TestCase):
    """#284 acceptance 4 (cross-review): choosing 不填 again puts the route back as if it had
    never been filled in, deadlines included."""

    def setUp(self):
        self.user = consented_user(username="aid_unanswerer")
        self.client.force_login(self.user)
        # Over a month and under three before today, whatever today is: inside the form 25 window.
        self.fitted_on = (timezone.localdate() - timedelta(days=40)).isoformat()

    def post(self, **fields):
        data = {"has_certificate": "", "fitted_on": "", "ear": "", "subsidy": "", "level": ""}
        return self.client.post(reverse("my_aid"), data | fields)

    def route(self):
        return self.client.get(reverse("guide")).content.decode()

    def here(self):
        return re.findall(r'data-stop="([^"]+)" aria-current="step"', self.route())

    def wearing_with_the_subsidy(self, **changes):
        fields = {"fitted_on": self.fitted_on, "subsidy": "disability", "level": "mid"}
        self.post(**fields)
        self.assertEqual(self.here(), ["form-25"])
        self.post(**(fields | changes))

    def test_not_answering_the_date_is_no_longer_wearing(self):
        self.wearing_with_the_subsidy(fitted_on="")
        # No questionnaire or audiogram either: back to recording one.
        self.assertEqual(self.here(), ["audiogram"])
        route = self.route()
        self.assertNotIn("前要做完", route)
        self.assertNotIn("起可以再申請補助", route)

    def test_not_answering_the_subsidy_leaves_form_25(self):
        self.wearing_with_the_subsidy(subsidy="")
        self.assertEqual(self.here(), ["after-fitting"])
        route = self.route()
        self.assertNotIn("前要做完", route)
        self.assertNotIn("起可以再申請補助", route)

    def test_not_answering_only_the_level_leaves_form_25(self):
        self.wearing_with_the_subsidy(level="")
        aid = AidAndSubsidy.objects.get(user=self.user)
        self.assertEqual((aid.subsidy, aid.level), ("disability", ""))
        self.assertEqual(self.here(), ["after-fitting"])
        route = self.route()
        self.assertNotIn("前要做完", route)
        # Still bought with 身障補助, so reapplying keeps its date.
        self.assertIn("起可以再申請補助", route)
