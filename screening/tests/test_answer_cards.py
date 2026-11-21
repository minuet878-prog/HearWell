"""#745 (spec #741 acceptance 11-16, 20-23, 58): step 5's card on the home page by the 目前這一站,
the canvas's 照顧旅程展開. The certificate, form 9 and the notice are answer cards sent through
the route's own form and checks (route_answer), request.user's own record only; an answer that
finishes the stop comes back home with the stamp and 「接著往下一站」, pressed to move on."""

import re
from datetime import date

from django.test import Client
from django.urls import reverse

from screening.fitting_route import GUIDE_PAGE, fitting_state
from screening.models import (
    AidAndSubsidy,
    AidLevel,
    Certificate,
    GuideChapterView,
    Subsidy,
)
from screening.questionnaires import ioi_ha
from screening.tests import test_home_journey
from screening.tests.helpers import consented_user

PTA_55 = test_home_journey.PTA_55
STAMP = test_home_journey.STAMP
TODAY = test_home_journey.TODAY
HERO_BUTTON = re.compile(r'<a class="btn btn-hero btn-lg" href="([^"]*)">([^<]*)</a>')


class AnswerCardTestCase(test_home_journey.HomeJourneyTestCase):
    """HHIE-S answered, an audiogram past the threshold and my guide opened: step 5 is the
    現在這一步, at the certificate until it is answered."""

    def setUp(self):
        super().setUp()
        self.answer()
        self.make(PTA_55, PTA_55)
        GuideChapterView.objects.create(user=self.user, chapter=GUIDE_PAGE)

    def aid(self, **fields):
        AidAndSubsidy.objects.update_or_create(user=self.user, defaults=fields)

    def send(self, stop, field, value, client=None):
        """Press a box on the home page's answer card, as its form sends it."""
        client = client or self.client
        data = {"stop": stop, field: value, "next": reverse("index")}
        return client.post(reverse("route_answer"), data)

    def home_card(self):
        return self.card(self.main())

    def choices(self, card):
        """Each box's (name, value, pressed, words)."""
        return [
            (name, value, pressed == ' aria-pressed="true"', self.text(words))
            for name, value, pressed, words in re.findall(
                r'<button type="submit" name="([^"]*)" value="([^"]*)" class="answer-choice[^"]*"'
                r'( aria-pressed="true")?>(.*?)</button>',
                card,
                re.S,
            )
        ]

    def links(self, card):
        """Each link's (href, words), but the answer card's form."""
        return [
            (href, self.text(words))
            for href, words in re.findall(r'<a [^>]*href="([^"]*)"[^>]*>(.*?)</a>', card, re.S)
        ]


class CertificateCardTests(AnswerCardTestCase):
    def test_unanswered_the_card_is_the_question_and_its_three_boxes_only(self):
        # Acceptance 11.
        card = self.home_card()
        self.assertEqual(
            self.text(card), "現在這一步 身障鑑定與鑑定醫院 您有身心障礙證明嗎？ 有 正在申請 沒有"
        )
        self.assertEqual(
            self.choices(card),
            [
                ("certificate", "yes", False, "有"),
                ("certificate", "applying", False, "正在申請"),
                ("certificate", "no_subsidy", False, "沒有"),
            ],
        )
        self.assertIn(f'<form method="post" action="{reverse("route_answer")}"', card)
        self.assertEqual(self.links(card), [])
        self.assertNotIn(STAMP, card)

    def test_yes_is_kept_stamped_and_moves_on_only_when_pressed(self):
        # Acceptance 12.
        response = self.send("assessment", "certificate", "yes")
        self.assertRedirects(response, reverse("index"), fetch_redirect_response=False)
        self.assertEqual(AidAndSubsidy.objects.get(user=self.user).certificate, Certificate.YES)
        card = self.home_card()
        self.assertIn('<h3 class="hero-card-title">身障鑑定與鑑定醫院</h3>', card)
        self.assertIn(("certificate", "yes", True, "有"), self.choices(card))
        self.assertIn(STAMP, card)
        self.assertEqual(self.links(card), [(reverse("index"), "接著往下一站：九號表")])
        # The stamp is shown once: the home page again is at the next stop.
        card = self.home_card()
        self.assertIn('<h3 class="hero-card-title">九號表：申請助聽器補助</h3>', card)
        self.assertNotIn(STAMP, card)

    def test_applying_shows_it_chosen_with_finding_a_hospital_and_stays(self):
        # Acceptance 13.
        self.send("assessment", "certificate", "applying")
        card = self.home_card()
        self.assertIn('<h3 class="hero-card-title">身障鑑定與鑑定醫院</h3>', card)
        self.assertIn(("certificate", "applying", True, "正在申請"), self.choices(card))
        self.assertEqual(
            HERO_BUTTON.findall(card), [("/guide/assessment#hospitals-title", "查詢鑑定醫院")]
        )
        self.assertNotIn(STAMP, card)
        self.assertNotIn("assessment", fitting_state(self.user, TODAY).done)

    def test_none_is_done_folds_the_subsidy_stops_and_goes_on_to_before_you_go(self):
        # Acceptance 14.
        self.send("assessment", "certificate", "no_subsidy")
        card = self.home_card()
        self.assertIn(STAMP, card)
        self.assertEqual(self.links(card), [(reverse("index"), "接著往下一站：去找聽力師之前")])
        self.assertFalse(fitting_state(self.user, TODAY).subsidy_shown)
        self.assertIn('<h3 class="hero-card-title">去找聽力師之前</h3>', self.home_card())


class Form9AndNoticeCardTests(AnswerCardTestCase):
    def test_form_9_yes_stamps_and_offers_the_notice(self):
        # Acceptance 15.
        self.aid(certificate=Certificate.YES)
        card = self.home_card()
        self.assertEqual(
            self.text(card),
            "現在這一步 九號表：申請助聽器補助 您的九號表完成了嗎？ 是 已經完成 否 還沒有",
        )
        self.send("form-9", "form_9_done", "True")
        card = self.home_card()
        self.assertIn(("form_9_done", "True", True, "是 已經完成"), self.choices(card))
        self.assertIn(STAMP, card)
        self.assertEqual(self.links(card), [(reverse("index"), "接著往下一站：等待核定公文")])

    def test_form_9_no_offers_its_steps(self):
        # Acceptance 15.
        self.aid(certificate=Certificate.YES)
        self.send("form-9", "form_9_done", "False")
        card = self.home_card()
        self.assertIn(("form_9_done", "False", True, "否 還沒有"), self.choices(card))
        self.assertEqual(HERO_BUTTON.findall(card), [("/guide/form-9", "看九號表的流程")])
        self.assertNotIn(STAMP, card)

    def test_notice_yes_asks_for_the_ears_and_level_and_only_then_is_done(self):
        # Acceptance 16.
        self.aid(certificate=Certificate.YES, form_9_done=True)
        self.assertEqual(
            self.text(self.home_card()),
            "現在這一步 等待核定公文 您收到核定公文了嗎？ 是 已經收到 否 還沒收到",
        )
        self.send("notice", "notice_received", "True")
        card = self.home_card()
        self.assertIn(("notice_received", "True", True, "是 已經收到"), self.choices(card))
        self.assertEqual(
            HERO_BUTTON.findall(card), [("/guide#stop-notice", "記下核定的耳朵與等級")]
        )
        self.assertNotIn(STAMP, card)
        self.aid(approved_ears="both", level=AidLevel.MID)
        self.assertIn('<h3 class="hero-card-title">去找聽力師之前</h3>', self.home_card())

    def test_notice_no_offers_types_and_prices(self):
        # Acceptance 16.
        self.aid(certificate=Certificate.YES, form_9_done=True)
        self.send("notice", "notice_received", "False")
        card = self.home_card()
        self.assertIn(("notice_received", "False", True, "否 還沒收到"), self.choices(card))
        self.assertEqual(
            HERO_BUTTON.findall(card), [("/guide/types-and-prices", "先了解助聽器種類與價格")]
        )


class OtherStopCardTests(AnswerCardTestCase):
    def test_before_you_go_is_one_button_to_its_chapter_and_reading_it_is_done(self):
        # Acceptance 20.
        self.aid(certificate=Certificate.NO_SUBSIDY)
        card = self.home_card()
        self.assertEqual(self.text(card), "現在這一步 去找聽力師之前 了解須知")
        self.assertEqual(HERO_BUTTON.findall(card), [("/guide/before-you-go", "了解須知")])
        self.client.get(reverse("guide_chapter", args=["before-you-go"]))
        self.assertIn('<h3 class="hero-card-title">配戴助聽器之後</h3>', self.home_card())

    def test_after_fitting_is_its_sentence_and_two_cards_until_an_ioi_ha(self):
        # Acceptance 21, 22.
        self.aid(certificate=Certificate.NO_SUBSIDY)
        GuideChapterView.objects.create(user=self.user, chapter="before-you-go")
        ioi = reverse("screening", args=[self.questionnaires[ioi_ha.CODE].pk])
        for fields in ({}, {"fitted_on": date(2026, 11, 1), "subsidy": Subsidy.OTHER}):
            with self.subTest(fields=fields):
                self.aid(**fields)
                card = self.home_card()
                self.assertIn('<h3 class="hero-card-title">配戴助聽器之後</h3>', card)
                self.assertIn(
                    "<p>配戴一個月後才能做二十五號表，配合問卷使用更能知道助聽器的效果。</p>", card
                )
                self.assertEqual(
                    self.links(card),
                    [
                        ("/guide/after-fitting#stop-question", "記下開始配戴的日期"),
                        (ioi, "填問卷 建議先戴一週再寫"),
                    ],
                )
        self.answer(code=ioi_ha.CODE, on=date(2026, 11, 8))
        self.assertIn('<h3 class="hero-card-title">戴滿 3 個月做效益問卷</h3>', self.home_card())

    def test_form_25_is_a_calendar_date_card_its_deadline_and_what_to_bring(self):
        # Acceptance 23: fitted 10 days ago with the subsidy, the first IOI-HA done.
        self.aid(fitted_on=date(2026, 11, 2), subsidy=Subsidy.DISABILITY, level=AidLevel.MID)
        self.answer(code=ioi_ha.CODE, on=date(2026, 11, 9))
        card = self.home_card()
        # The calendar sheet is a picture of the day, which a screen reader hears as Y/m/d.
        sheet = re.compile(r'<span class="date-card-sheet" aria-hidden="true">.*?</span></span>')
        self.assertEqual(
            self.text(sheet.sub("", card)),
            "現在這一步 二十五號表：使用效益驗證 2026/12/02 起可以做二十五號表 "
            "2027/02/02 前要完成，才能核銷補助 看二十五號表要帶什麼",
        )
        self.assertIn(
            '<span class="date-card-sheet" aria-hidden="true"><span class="date-card-month">12 月'
            '</span><span class="date-card-day">2</span><span class="date-card-year">2026</span>'
            "</span>",
            card,
        )
        self.assertEqual(HERO_BUTTON.findall(card), [("/guide/form-25", "看二十五號表要帶什麼")])


class AnswerCardFormTests(AnswerCardTestCase):
    def test_the_card_s_own_form_sends_the_answer_without_javascript(self):
        # Acceptance 58: what the page holds, its fields, its token and the box pressed, alone.
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        page = client.get(reverse("index")).content.decode()
        form = re.search(
            r'<form method="post" action="([^"]*)" class="answer-card-form">(.*?)</form>',
            page,
            re.S,
        )
        self.assertIsNotNone(form)
        data = dict(
            re.findall(r'<input type="hidden" name="([^"]*)" value="([^"]*)"', form.group(2))
        )
        data["certificate"] = "yes"
        response = client.post(form.group(1), data)
        self.assertRedirects(response, reverse("index"), fetch_redirect_response=False)
        self.assertEqual(AidAndSubsidy.objects.get(user=self.user).certificate, Certificate.YES)

    def test_only_the_signed_in_user_s_record_changes(self):
        other = consented_user(username="someone_else")
        AidAndSubsidy.objects.create(user=other, certificate=Certificate.APPLYING)
        self.send("assessment", "certificate", "no_subsidy")
        self.assertEqual(AidAndSubsidy.objects.get(user=other).certificate, Certificate.APPLYING)
        self.assertEqual(
            AidAndSubsidy.objects.get(user=self.user).certificate, Certificate.NO_SUBSIDY
        )
        # Naming the other account changes nothing: there is no field for it.
        self.client.post(
            reverse("route_answer"),
            {"stop": "assessment", "certificate": "yes", "user": other.pk, "next": "/"},
        )
        self.assertEqual(AidAndSubsidy.objects.get(user=other).certificate, Certificate.APPLYING)

    def test_signed_out_it_is_refused_and_nothing_is_kept(self):
        self.client.logout()
        response = self.send("assessment", "certificate", "yes")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))
        self.assertFalse(AidAndSubsidy.objects.exists())

    def test_the_stamp_is_only_for_the_stop_just_finished_here(self):
        # Answered on my guide, the stamp is the route's (#336), not the home page's.
        guide = reverse("guide")
        self.client.post(
            reverse("route_answer"), {"stop": "assessment", "certificate": "yes", "next": guide}
        )
        card = self.home_card()
        self.assertNotIn(STAMP, card)
        self.assertIn('<h3 class="hero-card-title">九號表：申請助聽器補助</h3>', card)
