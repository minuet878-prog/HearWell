"""#286 (spec #284): 我的助聽器與補助, the form and its summary card on 我的選配指引."""

import re

from django.test import TestCase
from django.urls import reverse

from screening import models
from screening.models import AidAndSubsidy, Consent, User
from screening.tests import test_layout
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
