"""#261 (spec #257): 建議您下一步 and the grouped cards on the returning user's home page."""

import re
from dataclasses import replace
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.fitting_route import fitting_state
from screening.models import (
    AidAndSubsidy,
    Answer,
    Category,
    GuideChapterView,
    Question,
    Questionnaire,
    ReportShare,
    Submission,
)
from screening.questionnaires import hhie_s
from screening.tests import test_guide_summary
from screening.tests.helpers import consented_user

# The 「因為」 sentences of spec #257's table (★ ones are drafts the owner settles on review).
NO_AUDIOGRAM = "因為：您還沒有記錄聽力圖，選配指引要用聽力圖才能整理下一步。"
TOO_LITTLE_DATA = "因為：這張聽力圖缺少頻率，資料不足，無法判斷。"
SHARE = "因為：讓家人也知道您的聽力狀況，家人不用登入就能看。"
REPORT = "因為：看診時把報告帶給醫師，一張紙看完所有紀錄。"
# Spec #291's drafts, one for each stop of the nine-stop route but form 25 (#296).
BEFORE_YOU_GO = "因為：先看看第一次去找聽力師要準備什麼。"
ASSESSMENT = "因為：先確認有沒有身障證明，才知道能不能申請補助。"
FORM_9 = "因為：您已經有身障證明，可以準備申請九號表的助聽器補助。"
NOTICE = "因為：九號表送出後，等公所的核定公文。"
TYPES_AND_PRICES = "因為：可以看看助聽器的種類與價格，比較之後再買。"
AFTER_FITTING = "因為：開始戴助聽器後，記下哪一天開始戴。"
PAYOUT = "因為：接下來等補助發放。"

RECORD = ("/audiograms/new", "記錄醫院的聽力圖")
PRINT = ("/report", "印聽力報告給醫師看")
FAMILY = ("/share", "分享報告給家人")
GUIDE = ("/guide", "了解助聽器選配與補助")
ADD_HOME = ("/add_to_home", "加到手機主畫面")

NEXT_STEP = re.compile(
    r'<div class="next-step">\s*<p class="next-step-label">([^<]*)</p>.*?'
    r'<h3 class="next-step-title">([^<]*)</h3>\s*</div>\s*'
    r'<p class="next-step-because">([^<]*)</p>\s*'
    r'<a class="btn btn-primary btn-lg w-full" href="([^"]*)">([^<]*)</a>\s*</div>',
    re.S,
)
GROUP = re.compile(
    r'<div class="more-group"([^>]*)>\s*<h3 class="more-group-title">([^<]*)</h3>(.*?)</ul>',
    re.S,
)
CARD = re.compile(
    r'<li><a class="link-card action-card" href="([^"]*)">\s*'
    r'<span class="action-card-icon" aria-hidden="true" data-icon="([^"]*)">(.*?)</span>\s*'
    r'<span class="link-card-body">\s*<span class="link-card-title">([^<]*)</span>\s*</span>',
    re.S,
)


class HomeNextStepTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)
        cls.questions = Question.objects.bulk_create(
            Question(
                questionnaire=cls.hhie_s,
                question_text=f"HHIE-S題{i}",
                question_number=i,
                category=Category.EMOTIONAL if i <= 5 else Category.SOCIAL,
            )
            for i in range(1, 11)
        )

    def setUp(self):
        self.user = consented_user(username="next_step_user")
        self.client.force_login(self.user)

    make = test_guide_summary.GuideSummaryTests.make

    def answer(self, wearing=False):
        submission = Submission.objects.create(
            user=self.user, questionnaire=self.hhie_s, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=0) for question in self.questions
        )

    def section(self):
        content = self.client.get(reverse("index")).content.decode()
        found = re.search(
            r'<section[^>]*aria-labelledby="more-title".*?</section>', content, re.DOTALL
        )
        self.assertIsNotNone(found, "no 您還可以 section")
        return found.group(0)

    def next_step(self, section=None):
        """(title, because, button href, button text) of the 建議您下一步 card."""
        found = NEXT_STEP.findall(section or self.section())
        self.assertEqual(len(found), 1, "not one 建議您下一步 card")
        label, *rest = found[0]
        self.assertEqual(label, "建議您下一步")
        return tuple(rest)

    def groups(self, section=None):
        """[(group title, [(href, card title)])] in page order."""
        return [
            (title, [(href, card_title) for href, _, _, card_title in CARD.findall(cards)])
            for _, title, cards in GROUP.findall(section or self.section())
        ]

    def test_without_an_audiogram_it_suggests_recording_one(self):
        # Acceptance 1.
        self.answer()
        self.assertEqual(
            self.next_step(), ("記錄醫院的聽力圖", NO_AUDIOGRAM, "/audiograms/new", "去記錄")
        )

    def test_a_stop_on_the_guide_suggests_my_guide_saying_why(self):
        # Acceptance 2, with spec #291 acceptance 21: the stops records reach in #292.
        for stop, wearing, ears, read, because in (
            ("before-you-go", False, (30, 20), (), BEFORE_YOU_GO),
            ("assessment", False, (55, 55), ("before-you-go",), ASSESSMENT),
            ("after-fitting", True, None, (), AFTER_FITTING),
        ):
            with self.subTest(stop=stop):
                self.user.audiograms.all().delete()
                self.user.guide_views.all().delete()
                self.answer(wearing=wearing)
                if ears:
                    self.make(*((pta,) * 4 for pta in ears))
                for chapter in read:
                    GuideChapterView.objects.create(user=self.user, chapter=chapter)
                self.assertEqual(
                    self.next_step(), ("了解助聽器選配與補助", because, "/guide", "看我的選配指引")
                )

    def test_an_audiogram_missing_a_frequency_suggests_editing_it(self):
        # Acceptance 3; the 記錄醫院的聽力圖 card stays in its group, for another audiogram.
        self.answer()
        audiogram = self.make((20, 20, 20, 20), (20, 20, 20, 20))
        audiogram.points.filter(ear="left", frequency=4000).delete()
        section = self.section()
        edit = reverse("audiogram_edit", args=[audiogram.pk])
        self.assertEqual(
            self.next_step(section), ("修改這張聽力圖", TOO_LITTLE_DATA, edit, "修改這張聽力圖")
        )
        self.assertEqual(self.groups(section)[0], ("記錄", [RECORD]))

    def test_without_a_stop_and_never_shared_it_suggests_sharing(self):
        # Acceptance 4: both ears within 25 dB HL, so no 目前這一站. Another account's link
        # does not count for this one.
        self.answer()
        self.make((20, 20, 20, 20), (20, 20, 20, 20))
        ReportShare.objects.create(user=consented_user(username="someone_else"))
        self.assertEqual(self.next_step(), ("分享報告給家人", SHARE, "/share", "去分享"))

    def test_without_a_stop_any_link_ever_shared_suggests_printing(self):
        # Acceptance 4: an expired or revoked link counts as shared.
        self.answer()
        self.make((20, 20, 20, 20), (20, 20, 20, 20))
        for ended in (
            {"expires_at": timezone.now() - timedelta(days=1)},
            {"revoked_at": timezone.now()},
        ):
            with self.subTest(ended=list(ended)):
                self.user.report_shares.all().delete()
                ReportShare.objects.create(user=self.user, **ended)
                self.assertEqual(
                    self.next_step(), ("印聽力報告給醫師看", REPORT, "/report", "去印報告")
                )

    def suggest(self, suggestion):
        """Records that make the home page suggest `suggestion` (a card title)."""
        self.answer()
        if suggestion == "記錄醫院的聽力圖":
            return
        if suggestion == "修改這張聽力圖":
            audiogram = self.make((20, 20, 20, 20), (20, 20, 20, 20))
            audiogram.points.filter(ear="left", frequency=4000).delete()
        elif suggestion == "了解助聽器選配與補助":
            self.make(test_guide_summary.PTA_55, test_guide_summary.PTA_55)
        else:
            self.make((20, 20, 20, 20), (20, 20, 20, 20))
            if suggestion == "印聽力報告給醫師看":
                ReportShare.objects.create(user=self.user, revoked_at=timezone.now())

    def test_the_suggested_card_leaves_its_group_and_an_empty_group_has_no_title(self):
        # Acceptance 5.
        for suggestion, groups in (
            (
                "記錄醫院的聽力圖",
                [("給別人看", [PRINT, FAMILY]), ("了解", [GUIDE]), ("方便使用", [ADD_HOME])],
            ),
            (
                "修改這張聽力圖",
                [
                    ("記錄", [RECORD]),
                    ("給別人看", [PRINT, FAMILY]),
                    ("了解", [GUIDE]),
                    ("方便使用", [ADD_HOME]),
                ],
            ),
            (
                "了解助聽器選配與補助",
                [("記錄", [RECORD]), ("給別人看", [PRINT, FAMILY]), ("方便使用", [ADD_HOME])],
            ),
            (
                "分享報告給家人",
                [
                    ("記錄", [RECORD]),
                    ("給別人看", [PRINT]),
                    ("了解", [GUIDE]),
                    ("方便使用", [ADD_HOME]),
                ],
            ),
            (
                "印聽力報告給醫師看",
                [
                    ("記錄", [RECORD]),
                    ("給別人看", [FAMILY]),
                    ("了解", [GUIDE]),
                    ("方便使用", [ADD_HOME]),
                ],
            ),
        ):
            with self.subTest(suggestion=suggestion):
                self.user = consented_user(username=f"suggested {suggestion}")
                self.client.force_login(self.user)
                self.suggest(suggestion)
                section = self.section()
                self.assertEqual(self.next_step(section)[0], suggestion)
                self.assertEqual(self.groups(section), groups)
                # No title without cards: every group title is one the list above expects.
                self.assertEqual(section.count('class="more-group-title"'), len(groups))

    def test_every_small_card_has_an_icon(self):
        # Acceptance 5: each card's icon tile draws something, the audiogram and
        # add-to-home icons included, and is hidden from screen readers.
        self.suggest("修改這張聽力圖")  # every small card shows
        cards = CARD.findall(self.section())
        self.assertEqual(
            [(href, icon) for href, icon, _, _ in cards],
            [
                ("/audiograms/new", "audiogram"),
                ("/report", "report"),
                ("/share", "share"),
                ("/guide", "guide"),
                ("/add_to_home", "add-home"),
            ],
        )
        for href, _, svg, _ in cards:
            with self.subTest(card=href):
                self.assertRegex(
                    svg, r'^<svg viewBox="0 0 24 24" focusable="false"><(path|rect|circle)'
                )

    def test_the_suggestion_is_a_box_with_one_button_not_a_card_link(self):
        # ADR 0006: only clickable cards lift, so the box itself is no link; its button is.
        self.answer()
        section = self.section()
        box = section[
            section.index('<div class="next-step">') : section.index('class="more-group"')
        ]
        self.assertEqual(box.count("<a "), 1)
        self.assertNotIn("link-card", box)
        self.assertRegex(
            box, r'<span class="action-card-icon" aria-hidden="true" data-icon="audiogram">'
        )

    def test_only_the_convenience_group_is_marked_for_hiding_in_the_app(self):
        # Acceptance 6: pwa-nav.js hides [data-hide-in-app] in the home-screen app, so the
        # whole group, its title too, goes there; the page itself hides nothing, so
        # without JavaScript it shows.
        self.answer()
        section = self.section()
        marked = [
            title for attrs, title, _ in GROUP.findall(section) if attrs == " data-hide-in-app"
        ]
        self.assertEqual(marked, ["方便使用"])
        self.assertEqual(section.count("data-hide-in-app"), 1)
        self.assertNotRegex(section, r"\shidden[\s=>]")  # the HTML attribute, not aria-hidden

    def test_a_new_user_s_home_has_no_suggestion_or_groups(self):
        # Acceptance 7, with test_home's NewUserHomeTests and test_guide_home_entry's
        # NewUserGuideEntryTests for the rest of the page.
        for signed_in in (True, False):
            with self.subTest(signed_in=signed_in):
                if not signed_in:
                    self.client.logout()
                content = self.client.get(reverse("index")).content.decode()
                self.assertIn("開始篩檢", content)
                for part in ("建議您下一步", "next-step", "more-group", "您還可以"):
                    self.assertNotIn(part, content)


class EveryStopNextStepTests(TestCase):
    """#292 (spec #291 acceptance 21): a reason for every stop of the nine, so the home page
    never fails on one. Stops 4, 5, 6, 8 and 9 need answers the later tickets add, so the
    route's stop is set here on the state the records give."""

    def setUp(self):
        self.user = consented_user(username="every_stop_user")
        self.client.force_login(self.user)
        real_localdate = timezone.localdate

        def localdate(value=None, timezone=None):
            return date(2026, 6, 15) if value is None else real_localdate(value, timezone)

        self.enterContext(patch("django.utils.timezone.localdate", localdate))
        self.answer()

    setUpTestData = classmethod(HomeNextStepTests.setUpTestData.__func__)
    answer = HomeNextStepTests.answer
    section = HomeNextStepTests.section
    next_step = HomeNextStepTests.next_step

    def at(self, stop):
        def state_at(user, today):
            return replace(fitting_state(user, today), stop=stop)

        return patch("screening.main_flow.fitting_state", state_at)

    def test_each_stop_on_the_guide_says_why(self):
        for stop, because in (
            ("before-you-go", BEFORE_YOU_GO),
            ("assessment", ASSESSMENT),
            ("form-9", FORM_9),
            ("notice", NOTICE),
            ("types-and-prices", TYPES_AND_PRICES),
            ("after-fitting", AFTER_FITTING),
            ("payout", PAYOUT),
        ):
            with self.subTest(stop=stop), self.at(stop):
                self.assertEqual(
                    self.next_step(), ("了解助聽器選配與補助", because, "/guide", "看我的選配指引")
                )

    def test_form_25_says_its_deadline(self):
        # Fitted 2026/05/01 with 身障補助 at 中階型: form 25 is due by 2026/08/01.
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 5, 1), subsidy="disability", level="mid"
        )
        with self.at("form-25"):
            self.assertEqual(
                self.next_step(),
                (
                    "了解助聽器選配與補助",
                    "因為：您的助聽器要在 2026/08/01 前做使用效益驗證（二十五號表），"
                    "才能核銷補助。",
                    "/guide",
                    "看我的選配指引",
                ),
            )

    def test_form_25_done_says_the_payout_comes_next(self):
        # #296 (spec #291 acceptance 16, 21): on the records alone, not a set stop.
        AidAndSubsidy.objects.create(
            user=self.user,
            fitted_on=date(2026, 5, 1),
            subsidy="disability",
            level="mid",
            form_25_done=True,
        )
        self.assertEqual(
            self.next_step(), ("了解助聽器選配與補助", PAYOUT, "/guide", "看我的選配指引")
        )

    def test_basic_at_the_payout_says_it_comes_next_without_form_25(self):
        # 簡易型 passes form 25 by (#296): the reason does not say form 25 was done.
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 5, 1), subsidy="disability", level="basic"
        )
        self.assertEqual(
            self.next_step(), ("了解助聽器選配與補助", PAYOUT, "/guide", "看我的選配指引")
        )

    def test_form_25_with_the_subsidy_unanswered_says_its_deadline_too(self):
        # #296 (coordinator's decision): without the notice or the subsidy answered, form 25
        # may be needed, so the reason dates it as for 不知道.
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 5, 1))
        self.assertEqual(
            self.next_step(),
            (
                "了解助聽器選配與補助",
                "因為：您的助聽器要在 2026/08/01 前做使用效益驗證（二十五號表），才能核銷補助。",
                "/guide",
                "看我的選配指引",
            ),
        )
