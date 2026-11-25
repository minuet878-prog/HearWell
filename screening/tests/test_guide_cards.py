import re
from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening.models import AidAndSubsidy
from screening.tests import test_guide_summary
from screening.tests.helpers import consented_user, took_ioi_ha

PTA_55 = test_guide_summary.PTA_55
# #779 (spec #774, ADR 0083): my guide's 引導卡, in order, and the 章節磚 under them.
CARDS = ("記錄聽力圖", "申請助聽器補助", "去找聽力師之前", "助聽器的種類與價格", "配戴與核銷")
SLUGS = ("audiogram", "subsidy", "before-you-go", "types-and-prices", "after-fitting")
TILES = ("assessment", "form-9", "before-you-go", "types-and-prices", "after-fitting", "form-25")
CARD = re.compile(r'<li class="guide-card[^"]*" data-card="([a-z-]+)".*?</li>', re.S)
TILE = re.compile(r'<a class="chapter-tile" href="/guide/([a-z0-9-]+)"')
BUTTON = re.compile(r'<a class="btn btn-hero btn-lg guide-card-button" href="([^"]+)">')
STAMP = "已完成"


def cards(response):
    """Each 引導卡's (slug, markup), in page order."""
    content = response.content.decode()
    return [(match.group(1), match.group(0)) for match in CARD.finditer(content)]


def card_title(markup):
    return re.search(r'<h3 [^>]*class="guide-card-title"[^>]*>(.*?)</h3>', markup).group(1)


def buttons(markup):
    return BUTTON.findall(markup)


class GuideCardsSignedOutTests(TestCase):
    """#774 acceptance 1: signed out, the five cards in order, one button each and none done,
    the six chapter tiles under them, and neither the route nor a question."""

    def setUp(self):
        self.response = self.client.get(reverse("guide"))

    def test_the_five_cards_come_in_order_with_one_button_each_and_none_done(self):
        found = cards(self.response)
        self.assertEqual([card_title(markup) for _, markup in found], list(CARDS))
        for slug, markup in found:
            with self.subTest(card=slug):
                self.assertEqual(len(buttons(markup)), 1)
                self.assertNotIn(STAMP, markup)

    def test_the_six_chapter_tiles_come_after_the_cards_in_reading_order(self):
        content = self.response.content.decode()
        self.assertEqual(TILE.findall(content), list(TILES))
        self.assertLess(content.rindex('class="guide-card'), content.index('class="chapter-tile"'))

    def test_neither_the_route_nor_any_question_is_on_the_page(self):
        content = self.response.content.decode()
        self.assertNotIn('class="route', content)
        self.assertNotIn("<form", content[content.index("<main") : content.index("</main>")])

    def test_the_subsidy_card_leads_to_the_subsidy_estimate(self):
        # #774 acceptance 6.
        self.assertEqual(buttons(dict(cards(self.response))["subsidy"]), [reverse("guide_subsidy")])

    def test_the_old_edit_address_shows_the_page(self):
        # #774 acceptance 24: /guide?edit=form-9, kept from the route, opens the cards.
        response = self.client.get(reverse("guide"), {"edit": "form-9"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([slug for slug, _ in cards(response)], list(SLUGS))


class GuideCardStampTests(TestCase):
    """#774 acceptance 2–5, 7: signed in, each card 已完成 by the 選配路線 stops behind it, and
    the same five cards whatever is answered."""

    def setUp(self):
        self.user = consented_user(username="card_stamps")
        self.client.force_login(self.user)

    make = test_guide_summary.GuideSummaryTests.make

    def stamped(self, **query):
        """The slugs of the cards stamped 已完成, in page order."""
        response = self.client.get(reverse("guide"), query)
        return [slug for slug, markup in cards(response) if STAMP in markup]

    def card(self, slug):
        return dict(cards(self.client.get(reverse("guide"))))[slug]

    def aid(self, **answers):
        AidAndSubsidy.objects.update_or_create(user=self.user, defaults=answers)

    def test_signed_in_without_records_no_card_is_stamped(self):
        self.assertEqual(self.stamped(), [])

    def test_a_readable_audiogram_stamps_the_audiogram_card(self):
        self.make(PTA_55, PTA_55)
        self.assertEqual(self.stamped(), ["audiogram"])
        self.assertEqual(buttons(self.card("audiogram")), [reverse("audiogram_new")])

    def test_an_audiogram_with_too_little_data_is_not_stamped_and_its_button_edits_it(self):
        audiogram = self.make((20, 20, 20, 20), (20, 20, 20, 20))
        audiogram.points.filter(ear="left", frequency=4000).delete()
        self.assertEqual(self.stamped(), [])
        markup = self.card("audiogram")
        self.assertEqual(buttons(markup), [reverse("audiogram_edit", args=[audiogram.pk])])
        self.assertIn(">修改這張聽力圖</a>", markup)

    def test_the_two_chapters_viewed_stamp_their_cards(self):
        for chapter in ("before-you-go", "types-and-prices"):
            self.client.get(reverse("guide_chapter", args=[chapter]))
        self.assertEqual(self.stamped(), ["before-you-go", "types-and-prices"])

    def test_the_notice_with_its_ears_and_level_stamps_the_subsidy_card(self):
        self.aid(certificate="yes", form_9_done=True, notice_received=True, approved_ears="both")
        self.assertEqual(self.stamped(), [])  # the level not yet answered
        self.aid(level="mid")
        self.assertEqual(self.stamped(), ["subsidy"])

    def test_no_certificate_never_stamps_the_subsidy_card(self):
        self.aid(
            certificate="no_subsidy",
            form_9_done=True,
            notice_received=True,
            approved_ears="both",
            level="mid",
        )
        self.assertEqual(self.stamped(), [])

    def fitted(self, **answers):
        """配戴之後 done: the fitting date, the subsidy answered and an IOI-HA from that day."""
        day = date(2026, 5, 1)
        self.aid(fitted_on=day, ear="both", **answers)
        took_ioi_ha(self.user, day)

    def test_after_fitting_done_with_form_25_done_stamps_the_last_card(self):
        self.fitted(certificate="yes", subsidy="disability", level="mid", form_25_done=True)
        self.assertEqual(self.stamped(), ["after-fitting"])

    def test_after_fitting_done_with_form_25_not_applicable_stamps_the_last_card(self):
        for answers in ({"subsidy": "other"}, {"subsidy": "disability", "level": "basic"}):
            with self.subTest(answers=answers):
                self.fitted(certificate="yes", form_25_done=None, **answers)
                self.assertEqual(self.stamped(), ["after-fitting"])

    def test_after_fitting_done_with_form_25_still_to_do_is_not_stamped(self):
        self.fitted(certificate="yes", subsidy="disability", level="mid", form_25_done=False)
        self.assertEqual(self.stamped(), [])

    def test_form_25_done_without_after_fitting_done_is_not_stamped(self):
        # No IOI-HA since the fitting date: 配戴之後 is not done.
        self.aid(
            certificate="yes",
            fitted_on=date(2026, 5, 1),
            subsidy="disability",
            level="mid",
            form_25_done=True,
        )
        self.assertEqual(self.stamped(), [])

    def test_the_same_five_cards_whatever_the_certificate_answer(self):
        # #774 acceptance 7: 沒有 folds the 補助站, 有 unfolds them; the cards stay five.
        for certificate in ("no_subsidy", "yes", "applying"):
            with self.subTest(certificate=certificate):
                self.aid(certificate=certificate)
                found = cards(self.client.get(reverse("guide")))
                self.assertEqual([slug for slug, _ in found], list(SLUGS))
