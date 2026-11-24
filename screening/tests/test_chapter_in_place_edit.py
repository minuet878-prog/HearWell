import re
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import AidAndSubsidy
from screening.tests import test_route_answers
from screening.tests.helpers import consented_user

CARD_TITLE = test_route_answers.CARD_TITLE
CERTIFICATE = test_route_answers.QUESTION
FORM_9 = "/guide/form-9"


def foot(response):
    """The chapter's foot: its stop's question or answer, up to the sources."""
    content = response.content.decode()
    return content[content.index('<section id="stop-question"') : content.index("<footer")]


def legends(markup):
    return re.findall(r'<legend class="font-bold text-xl/normal">([^<]+)</legend>', markup)


class ChapterInPlaceEditTests(TestCase):
    """#777 (spec #774 acceptance 21): 修改 at a chapter's foot opens the stop's questions on the
    same chapter, and answering or an error stays there."""

    def setUp(self):
        self.user = consented_user(username="in_place_edit_user")
        self.client.force_login(self.user)

    def chapter(self, slug="assessment", query=""):
        return self.client.get(reverse("guide_chapter", args=[slug]) + query)

    def test_edit_links_to_the_same_chapter(self):
        AidAndSubsidy.objects.create(user=self.user, certificate="yes", form_9_done=False)
        for slug, title in (
            ("assessment", "身障鑑定與鑑定醫院"),
            ("form-9", "九號表：申請助聽器補助"),
        ):
            with self.subTest(chapter=slug):
                edit = reverse("guide_chapter", args=[slug]) + "?edit=1#stop-question"
                self.assertIn(
                    f'<a href="{edit}" aria-label="修改{title}的回答">修改</a>',
                    foot(self.chapter(slug)),
                )

    def test_edit_opens_the_question_with_the_current_answer(self):
        AidAndSubsidy.objects.create(user=self.user, certificate="yes")
        card = foot(self.chapter(query="?edit=1"))
        self.assertIn(f"{CARD_TITLE}已記下：有身障證明</h2>", card)
        self.assertEqual(legends(card), [CERTIFICATE])
        self.assertEqual(test_route_answers.buttons(card), test_route_answers.offered(filled="yes"))
        chapter = reverse("guide_chapter", args=["assessment"])
        self.assertIn(f'<input type="hidden" name="next" value="{chapter}#stop-question">', card)
        self.assertIn(f'<a href="{chapter}#stop-question">不用改了</a>', card)
        # Open, the answer's own 修改 and the way back to the route give way to the question.
        self.assertNotIn(">修改</a>", card)
        self.assertNotIn("回選配路線看下一站", card)

    def test_a_new_answer_comes_back_to_the_chapter_s_foot(self):
        AidAndSubsidy.objects.create(user=self.user, certificate="yes")
        chapter = reverse("guide_chapter", args=["assessment"]) + "#stop-question"
        data = {"stop": "assessment", "certificate": "applying", "next": chapter}
        response = self.client.post(reverse("route_answer"), data, follow=True)
        self.assertEqual(response.redirect_chain, [(chapter, 302)])
        card = foot(response)
        self.assertIn(f"{CARD_TITLE}已記下：打算申請或正在申請鑑定</h2>", card)
        self.assertEqual(legends(card), [])

    def test_an_error_stays_on_the_chapter_and_sends_back_to_it(self):
        AidAndSubsidy.objects.create(user=self.user, certificate="yes")
        chapter = reverse("guide_chapter", args=["assessment"])
        data = {"stop": "assessment", "certificate": "maybe", "next": f"{chapter}#stop-question"}
        response = self.client.post(reverse("route_answer"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1 class="bird-title">身障鑑定與鑑定醫院</h1>')
        card = foot(response)
        self.assertIn('class="text-danger field-error', card)
        # Drawn at the answer's address, the form and 不用改了 still lead back to the chapter.
        self.assertIn(f'<input type="hidden" name="next" value="{chapter}#stop-question">', card)
        self.assertIn(f'<a href="{chapter}#stop-question">不用改了</a>', card)
        self.assertEqual(AidAndSubsidy.for_user(self.user).certificate, "yes")

    def test_after_fitting_s_edit_opens_its_form_and_a_future_day_stays_there(self):
        AidAndSubsidy.objects.create(
            user=self.user, fitted_on=date(2026, 5, 1), ear="both", subsidy="other"
        )
        chapter = reverse("guide_chapter", args=["after-fitting"])
        card = foot(self.chapter("after-fitting", "?edit=1"))
        self.assertIn('value="2026-05-01"', card)
        self.assertIn(">還沒開始戴</button>", card)
        self.assertIn(f'<a href="{chapter}#stop-question">不用改了</a>', card)
        tomorrow = timezone.localdate() + timedelta(days=1)
        data = {
            "stop": "after-fitting",
            "fitted_on": tomorrow.isoformat(),
            "ear": "both",
            "subsidy": "other",
            "next": f"{chapter}#stop-question",
        }
        card = foot(self.client.post(reverse("route_answer"), data))
        self.assertIn("開始配戴日期不能是未來", card)
        self.assertIn(f'<input type="hidden" name="next" value="{chapter}#stop-question">', card)
        self.assertEqual(AidAndSubsidy.for_user(self.user).fitted_on, date(2026, 5, 1))


class Form9ChapterNoticeTests(TestCase):
    """#777 (spec #774 acceptance 22): form 9 done with the 補助站 shown, its chapter's foot goes
    on to the notice's questions, one at a time, and once answered says so with 修改."""

    NOTICE = "收到核定公文了嗎？"
    EARS = "核定的是單耳還是雙耳？"
    LEVEL = "補助的等級是？"

    def setUp(self):
        self.user = consented_user(username="form_9_notice_user")
        self.client.force_login(self.user)

    def aid(self, **answers):
        AidAndSubsidy.objects.update_or_create(user=self.user, defaults=answers)

    def foot(self, query=""):
        return foot(self.client.get(f"{FORM_9}{query}"))

    def notice(self, query=""):
        card = self.foot(query)
        return card[card.index('id="stop-notice"') :]

    def test_form_9_done_goes_on_to_whether_the_notice_came(self):
        self.aid(certificate="yes", form_9_done=True)
        card = self.foot()
        self.assertIn(f"{CARD_TITLE}已記下：九號表完成了</h2>", card)
        self.assertEqual(legends(card), [self.NOTICE])
        notice = self.notice()
        self.assertIn('<input type="hidden" name="stop" value="notice">', notice)
        self.assertIn(f'<input type="hidden" name="next" value="{FORM_9}#stop-notice">', notice)
        self.assertEqual(
            test_route_answers.answer_buttons(notice, "notice_received"),
            [("True", "收到了", False), ("False", "還沒", False)],
        )

    def test_received_asks_the_ears_then_the_level_saying_what_is_kept(self):
        self.aid(certificate="yes", form_9_done=True, notice_received=True)
        notice = self.notice()
        self.assertIn('<p class="route-answer">收到核定公文</p>', notice)
        self.assertEqual(legends(notice), [self.EARS])
        self.aid(approved_ears="both")
        notice = self.notice()
        self.assertIn('<p class="route-answer">收到核定公文，雙耳</p>', notice)
        self.assertEqual(legends(notice), [self.LEVEL])
        self.assertNotIn(">修改</a>", notice)

    def test_answered_it_says_the_ears_and_level_with_edit(self):
        self.aid(
            certificate="yes",
            form_9_done=True,
            notice_received=True,
            approved_ears="both",
            level="mid",
        )
        notice = self.notice()
        self.assertEqual(legends(notice), [])
        self.assertIn('<h3 id="stop-notice-title" class="h4">核定公文：雙耳、中階型</h3>', notice)
        edit = f"{FORM_9}?edit=notice#stop-notice"
        self.assertIn(f'<a href="{edit}" aria-label="修改核定公文的回答">修改</a>', notice)

    def test_not_yet_says_so_with_edit(self):
        self.aid(certificate="yes", form_9_done=True, notice_received=False)
        notice = self.notice()
        self.assertEqual(legends(notice), [])
        self.assertIn('<h3 id="stop-notice-title" class="h4">還沒收到核定公文</h3>', notice)
        self.assertIn(">修改</a>", notice)

    def test_edit_opens_the_three_questions_with_the_answers(self):
        self.aid(
            certificate="yes",
            form_9_done=True,
            notice_received=True,
            approved_ears="one",
            level="advanced",
        )
        notice = self.notice("?edit=notice")
        self.assertEqual(legends(notice), [self.NOTICE, self.EARS, self.LEVEL])
        self.assertEqual(
            test_route_answers.answer_buttons(notice, "approved_ears"),
            [("one", "單耳", True), ("both", "雙耳", False)],
        )
        self.assertIn(f'<a href="{FORM_9}#stop-notice">不用改了</a>', notice)
        # Form 9's own answer stays as it was, not opened.
        card = self.foot("?edit=notice")
        self.assertEqual(legends(card), [self.NOTICE, self.EARS, self.LEVEL])

    def test_no_notice_until_form_9_is_done(self):
        for answers in ({"certificate": "yes"}, {"certificate": "yes", "form_9_done": False}):
            with self.subTest(answers=answers):
                self.aid(**answers)
                self.assertNotIn('id="stop-notice"', self.foot())

    def test_no_notice_without_a_certificate(self):
        # 沒有 folds the 補助站 away (ADR 0063): form 9's chapter asks nothing at its foot.
        self.aid(certificate="no_subsidy", form_9_done=True, notice_received=True)
        response = self.client.get(FORM_9)
        self.assertNotContains(response, 'id="stop-notice"')
        self.assertNotContains(response, self.NOTICE)

    def test_answering_comes_back_to_the_notice_on_the_chapter(self):
        self.aid(certificate="yes", form_9_done=True)
        back = f"{FORM_9}#stop-notice"
        data = {"stop": "notice", "notice_received": "True", "next": back}
        response = self.client.post(reverse("route_answer"), data, follow=True)
        self.assertEqual(response.redirect_chain, [(back, 302)])
        self.assertEqual(legends(foot(response)), [self.EARS])

    def test_an_error_on_the_notice_stays_on_the_chapter(self):
        self.aid(certificate="yes", form_9_done=True, notice_received=True)
        data = {"stop": "notice", "approved_ears": "three", "next": f"{FORM_9}#stop-notice"}
        response = self.client.post(reverse("route_answer"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1 class="bird-title">九號表：申請助聽器補助</h1>')
        card = foot(response)
        notice = card[card.index('id="stop-notice"') :]
        self.assertEqual(legends(notice), [self.EARS])
        self.assertIn('class="text-danger field-error', notice)
        self.assertIn(f'<input type="hidden" name="next" value="{FORM_9}#stop-notice">', notice)
        self.assertEqual(AidAndSubsidy.for_user(self.user).approved_ears, "")
