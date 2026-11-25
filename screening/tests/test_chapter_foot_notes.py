from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import AidAndSubsidy
from screening.tests.helpers import consented_user, took_ioi_ha

# #779 (the owner's pick of 2026-11-24, written back to #774): what the 選配路線 said under its
# stops, said at the chapter's foot now my guide no longer draws the route.
WITHOUT = '<a href="/guide/form-9#without-certificate">看沒有身障證明時</a>'
PURCHASE = "收到核定通知後 6 個月內要買。"


class ChapterFootNotesTestCase(TestCase):
    def setUp(self):
        self.user = consented_user(username="foot_notes")
        self.client.force_login(self.user)

    def aid(self, **answers):
        AidAndSubsidy.objects.update_or_create(user=self.user, defaults=answers)

    def main(self, slug):
        content = self.client.get(reverse("guide_chapter", args=[slug])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def foot(self, slug):
        main = self.main(slug)
        return main[main.index('<section id="stop-question"') : main.index("<footer")]


class CertificateNoteTests(ChapterFootNotesTestCase):
    """#597 (spec #593 acceptance 21): 沒有 always leads on to the help there is without a
    certificate, under the answer."""

    def test_no_certificate_links_to_the_help_under_the_answer(self):
        self.aid(certificate="no_subsidy")
        foot = self.foot("assessment")
        self.assertEqual(foot.count(WITHOUT), 1)
        self.assertGreater(foot.index(WITHOUT), foot.index("已記下：沒有身障證明"))

    def test_other_answers_have_no_link(self):
        for certificate in ("yes", "applying"):
            with self.subTest(certificate=certificate):
                self.aid(certificate=certificate)
                self.assertNotIn(WITHOUT, self.foot("assessment"))


class PurchaseNoteTests(ChapterFootNotesTestCase):
    """#294 (spec #291 Q12): 種類與價格 says the six months to buy in, to everyone the 補助站 are
    shown to; folded or signed out, nothing of a notice (#596)."""

    def test_shown_the_subsidy_s_stops_the_chapter_s_foot_says_it(self):
        self.aid(certificate="yes")
        main = self.main("types-and-prices")
        self.assertIn(f'<p class="mt-6 mb-0">{PURCHASE}</p>', main)
        self.assertLess(main.index("</article>"), main.index(PURCHASE))

    def test_folded_or_signed_out_it_says_nothing(self):
        for certificate in (None, "no_subsidy"):
            with self.subTest(certificate=certificate):
                if certificate:
                    self.aid(certificate=certificate)
                self.assertNotIn(PURCHASE, self.main("types-and-prices"))
        self.client.logout()
        self.assertNotIn(PURCHASE, self.main("types-and-prices"))


class Form25DateNoteTests(ChapterFootNotesTestCase):
    """#296 (spec #291 acceptance 14): form 25's chapter says from when it can be done, by when
    while open, and once closed its deadline, never that it is overdue."""

    def setUp(self):
        super().setUp()
        self.today = date(2026, 5, 20)
        real_localdate = timezone.localdate

        def localdate(value=None, timezone=None):
            return self.today if value is None else real_localdate(value, timezone)

        self.enterContext(patch("django.utils.timezone.localdate", localdate))

    def fit(self, subsidy="disability", level="mid"):
        self.aid(fitted_on=date(2026, 5, 1), subsidy=subsidy, level=level)
        took_ioi_ha(self.user, date(2026, 5, 1))

    def test_the_wording_turns_on_the_boundary_days(self):
        self.fit()
        for today, wording in (
            (date(2026, 5, 31), "2026/06/01 起可以做"),
            (date(2026, 6, 1), "2026/08/01 前要做完"),
            (date(2026, 8, 1), "2026/08/01 前要做完"),
            (date(2026, 8, 2), "期限是 2026/08/01"),
        ):
            with self.subTest(today=today):
                self.today = today
                foot = self.foot("form-25")
                self.assertIn(f'<p class="mt-2 mb-0">{wording}</p>', foot)
                self.assertNotIn("過期", foot)

    def test_basic_or_paying_otherwise_has_no_date(self):
        for subsidy, level in (("disability", "basic"), ("other", "")):
            with self.subTest(subsidy=subsidy):
                self.fit(subsidy=subsidy, level=level)
                self.assertNotIn("2026/0", self.main("form-25"))


class ReapplyNoteTests(ChapterFootNotesTestCase):
    """#288 (spec #284 acceptance 17): form 9's chapter says when 身障補助 can be applied for
    again (FittingState.reapply_on)."""

    def test_the_subsidy_and_a_fitting_date_say_when_to_apply_again(self):
        self.aid(fitted_on=date(2026, 5, 1), subsidy="disability", level="mid")
        self.assertIn('<p class="mt-2 mb-0">2030/05/01 起可以再申請補助</p>', self.foot("form-9"))

    def test_paying_otherwise_has_no_date(self):
        self.aid(fitted_on=date(2026, 5, 1), subsidy="other")
        self.assertNotIn("起可以再申請補助", self.main("form-9"))
