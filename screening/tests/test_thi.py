"""THI: catalog card, answering and result page (#212, spec #208, ADR 0016)."""

import json
import re
import uuid
from datetime import date, datetime, time
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.models import Answer, Questionnaire, Submission
from screening.tests import test_layout
from screening.tests.helpers import consented_user


class ThiTestCase(TestCase):
    fixtures = ("questions_fixture.json",)

    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.thi = Questionnaire.objects.get(code="thi")
        self.hhie_s = Questionnaire.objects.get(code="hhie-s")
        self.user = consented_user(username="thi_user")
        self.client.force_login(self.user)

    def post_web(self, scores, wearing="False"):
        """Sends the server form; a score or wearing of None leaves that answer out."""
        questions = list(self.thi.questions.all())
        data = {
            "idempotency_key": str(uuid.uuid4()),
            "form-TOTAL_FORMS": len(questions),
            "form-INITIAL_FORMS": 0,
        }
        if wearing is not None:
            data["wearing_hearing_aid"] = wearing
        for index, (question, score) in enumerate(zip(questions, scores, strict=True)):
            data[f"form-{index}-question_id"] = question.pk
            if score is not None:
                data[f"form-{index}-score"] = score
        return self.client.post(reverse("screening", args=[self.thi.pk]), data)

    def post_api(self, scores, **fields):
        """Sends what the React page sends; an item whose score is None is left out."""
        questions = list(self.thi.questions.all())
        body = {
            "questionnaire": self.thi.pk,
            "answers": [
                {"question": question.pk, "score": score}
                for question, score in zip(questions, scores, strict=True)
                if score is not None
            ],
        } | fields
        return self.client.post(
            reverse("api:submissions"),
            json.dumps(body),
            content_type="application/json",
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )


def scores_for(total):
    """25 answers adding up to an even total: 經常 (4) first, then 偶爾 (2), then 不會 (0)."""
    scores = [4] * (total // 4) + [2] * (total % 4 // 2)
    return scores + [0] * (25 - len(scores))


class ThiCatalogTests(ThiTestCase):
    def test_production_catalog_lists_thi_last_with_its_audience_and_minutes(self):
        # Tests run with DEBUG=False, as the production site does.
        content = self.client.get(reverse("questionnaire_list"), {"choose": "self"})
        cards = test_layout._cards(content.content.decode())
        self.assertIn(f'href="{reverse("screening", args=[self.thi.pk])}"', cards[-1])
        text = test_layout._text(cards[-1])
        for part in ("耳鳴對生活的影響（THI）", "給有耳鳴的人，不限年齡。", "25 題", "約 5 分鐘"):
            self.assertIn(part, text)
        self.assertIn('data-icon="ear"', cards[-1])


# Word for word from docs/planning/adult-assessment/thi-grill-decisions.md (the hospital form),
# written out here so a changed definition fails instead of being copied into the expectation.
QUESTIONS = (
    "您是否覺得耳鳴無法控制？",
    "耳鳴的聲音大到讓您聽不清楚別人的談話？",
    "耳鳴會使您感到憤怒？",
    "您會認為您的耳鳴是一種可怕的疾病嗎？",
    "您會因為耳鳴而感到絕望？",
    "耳鳴會使您經常感到疲勞？",
    "您會因為耳鳴而晚上無法入睡嗎？",
    "您是否覺得無法擺脫耳鳴？",
    "耳鳴是否已干擾到您的正常社交活動？（例如出去用餐或看電影）",
    "您會因為耳鳴感到挫折嗎？",
    "您會因為耳鳴而感到憂鬱？",
    "耳鳴會使您感到不安嗎？",
    "耳鳴會干擾您的工作或家務嗎？",
    "您會因為耳鳴而經常情緒不穩定嗎？",
    "您會因為耳鳴而閱讀（書報）困難嗎？",
    "您會因為耳鳴而無法專心嗎？",
    "耳鳴會對於您和家人及朋友的關係帶來壓力嗎？",
    "您是否不容易把注意力從耳鳴轉移至別的事務？",
    "您對您的耳鳴會抱怨連連？",
    "耳鳴會使您感到困擾？",
    "受到壓力時，您的耳鳴會變得更嚴重？",
    "耳鳴會使您心情不好嗎？",
    "您是否覺得已無法忍受耳鳴了？",
    "耳鳴會使您感到焦慮嗎？",
    "耳鳴會使您無法享受人生嗎？",
)
THI_WEARING = "您現在有沒有配戴助聽器？"
HHIE_S_WEARING = "這次填答時，您有沒有戴助聽器？"
THI_WEARING_ERROR = "請選擇您現在有沒有配戴助聽器"
HHIE_S_WEARING_ERROR = "請選擇這次有沒有戴助聽器"
THREE_CHOICES = [
    {"value": 4, "label": "經常"},
    {"value": 2, "label": "偶爾"},
    {"value": 0, "label": "不會"},
]


class ThiAnswerPageTests(ThiTestCase):
    def _page(self, questionnaire):
        return self.client.get(reverse("screening", args=[questionnaire.pk])).content.decode()

    def test_web_page_shows_the_intro_wearing_question_and_25_items_word_for_word(self):
        page = self._page(self.thi)
        self.assertIn("請依您最近一個月的耳鳴情況回答。", page)
        self.assertIn(f'<legend class="font-bold text-xl/normal">{THI_WEARING}</legend>', page)
        self.assertNotIn(HHIE_S_WEARING, page)
        legends = re.findall(r'<span class="question-progress">[^<]*</span>([^<]*)</legend>', page)
        self.assertEqual(tuple(legends), QUESTIONS)

    def test_web_page_credits_the_chinese_version(self):
        # The owner's choice after #212: credit the hospital form as HHIA-S credits its source.
        self.assertIn("中文版：黃啟原修訂；信度考驗：李恆惠。", self._page(self.thi))

    def test_every_item_offers_often_sometimes_never_and_no_not_applicable(self):
        page = self._page(self.thi)
        for number in range(1, 26):
            with self.subTest(item=number):
                group = re.search(rf'id="question-{number}".*?</fieldset>', page, re.S).group()
                options = re.findall(
                    r'value="([^"]+)" class="choice-group" id="[^"]+">\n (.*?)</label>', group
                )
                self.assertEqual(options, [("4", "經常"), ("2", "偶爾"), ("0", "不會")])
        self.assertNotIn("不適用", page)

    def test_hhie_s_keeps_its_own_wearing_question(self):
        page = self._page(self.hhie_s)
        self.assertIn(f'<legend class="font-bold text-xl/normal">{HHIE_S_WEARING}</legend>', page)
        self.assertNotIn(THI_WEARING, page)

    def test_api_gives_react_each_questionnaire_its_wearing_question(self):
        for questionnaire, wearing in ((self.thi, THI_WEARING), (self.hhie_s, HHIE_S_WEARING)):
            with self.subTest(questionnaire=questionnaire.code):
                url = reverse("api:questionnaire", args=[questionnaire.pk])
                self.assertEqual(self.client.get(url).json()["wearing_question"], wearing)

    def test_api_gives_react_the_25_items_and_three_choices(self):
        detail = self.client.get(reverse("api:questionnaire", args=[self.thi.pk])).json()
        self.assertEqual(tuple(q["text"] for q in detail["questions"]), QUESTIONS)
        for question in detail["questions"]:
            self.assertEqual(question["choices"], THREE_CHOICES)


class ThiRequiredAnswersTests(ThiTestCase):
    def test_web_lists_the_unanswered_item_and_saves_nothing(self):
        scores = [0] * 25
        scores[6] = None
        response = self.post_web(scores)
        self.assertContains(response, 'href="#question-7">第 7 題</a>')
        self.assertNotContains(response, 'href="#question-6">')
        self.assertFalse(Submission.objects.exists())

    def test_web_lists_the_unanswered_wearing_question_and_saves_nothing(self):
        response = self.post_web([0] * 25, wearing=None)
        self.assertContains(response, 'href="#question-hearing-aid">是否戴助聽器</a>')
        self.assertFalse(Submission.objects.exists())

    def test_unanswered_wearing_message_asks_as_the_question_does(self):
        # The message follows THI's 「您現在有沒有配戴助聽器？」, not HHIE-S's 「這次」.
        for wearing in (None, "maybe"):
            with self.subTest(wearing=wearing):
                content = self.post_web([0] * 25, wearing=wearing).content.decode()
                self.assertRegex(
                    content, rf'id="id_wearing_hearing_aid_error">\s*<p[^>]*>{THI_WEARING_ERROR}<'
                )
                self.assertNotIn(HHIE_S_WEARING_ERROR, content)
        for wearing in ({"wearing_hearing_aid": None}, {"wearing_hearing_aid": "yes"}):
            with self.subTest(api=wearing):
                response = self.post_api([0] * 25, **wearing)
                self.assertEqual(response.json(), {"wearing_hearing_aid": [THI_WEARING_ERROR]})
        self.assertFalse(Submission.objects.exists())

    def test_api_refuses_an_unanswered_item_and_saves_nothing(self):
        scores = [0] * 25
        scores[24] = None
        response = self.post_api(scores, wearing_hearing_aid=False)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"answers": ["有題目沒有作答"]})
        self.assertFalse(Submission.objects.exists())

    def test_api_refuses_an_unanswered_wearing_question_and_saves_nothing(self):
        response = self.post_api([0] * 25)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"wearing_hearing_aid": [THI_WEARING_ERROR]})
        self.assertFalse(Submission.objects.exists())

    def test_wearing_now_is_saved_as_worn(self):
        response = self.post_web([0] * 25, wearing="True")
        submission = Submission.objects.get()
        self.assertRedirects(response, reverse("result", args=[submission.pk]))
        self.assertIs(submission.wearing_hearing_aid, True)


GREEN, ORANGE, RED = "normal", "mild_to_moderate", "severe"


class ThiScoringTests(ThiTestCase):
    def _web_result(self, scores):
        response = self.post_web(scores)
        submission = Submission.objects.latest("pk")
        self.assertRedirects(response, reverse("result", args=[submission.pk]))
        return submission, self.client.get(reverse("result", args=[submission.pk]))

    def _api_result(self, submission):
        return self.client.get(reverse("api:submission", args=[submission.pk])).json()

    def assert_graded(self, scores, total, code, text, color):
        submission, page = self._web_result(scores)
        self.assertContains(page, f'<div class="result-banner result-banner-{color}">')
        self.assertContains(page, f'aria-describedby="result-score">{text}</h2>')
        self.assertContains(page, f"總分 {total} 分（滿分 100）")
        record = self._api_result(submission)
        self.assertEqual(record["scores"]["total"], total)
        self.assertEqual(record["level"], {"code": code, "text": text})

    def test_all_never_is_0_none_or_slight_in_green(self):
        self.assert_graded([0] * 25, 0, "none_or_slight", "無障礙或輕微障礙", GREEN)

    def test_all_sometimes_is_50_moderate_in_orange(self):
        self.assert_graded([2] * 25, 50, "moderate", "中度障礙", ORANGE)

    def test_all_often_is_100_catastrophic_in_red(self):
        self.assert_graded([4] * 25, 100, "catastrophic", "極重度障礙", RED)

    def test_levels_either_side_of_each_threshold(self):
        expected = (
            (16, "none_or_slight", "無障礙或輕微障礙", GREEN),
            (18, "mild", "輕度障礙", ORANGE),
            (36, "mild", "輕度障礙", ORANGE),
            (38, "moderate", "中度障礙", ORANGE),
            (56, "moderate", "中度障礙", ORANGE),
            (58, "severe", "重度障礙", RED),
            (76, "severe", "重度障礙", RED),
            (78, "catastrophic", "極重度障礙", RED),
        )
        for total, code, text, color in expected:
            with self.subTest(total=total):
                self.assert_graded(scores_for(total), total, code, text, color)

    def test_result_page_shows_no_emotional_or_social_subscores(self):
        # Spec #208 Q5: THI shows its total and level only, no subscales of any kind.
        _, page = self._web_result([4] * 25)
        self.assertNotContains(page, "情緒分數")
        self.assertNotContains(page, "社交分數")


# Draft wording from #211, written out here so a changed definition fails instead of being
# copied into the expectation.
LINE_1925 = "1925 安心專線（24 小時免付費）"
RETAKE = ("3 個月後，或開始新的處置（例如配戴助聽器）3 個月後再做一次。", None)
AUDIOGRAM = ("記錄聽力圖", "/audiograms/new")
REPORT = ("看／印聽力報告", "/report")
STEPS = {
    0: (
        ("耳鳴目前對您的生活影響不大。", None),
        (
            "避免待在太安靜的環境，可以開著柔和的背景聲音；若耳鳴突然變大聲、只有一邊耳朵有，"
            "或同時聽力變差、頭暈，請盡快就醫。",
            None,
        ),
        RETAKE,
    ),
    18: (
        (
            "耳鳴已經對您的生活有些影響。大部分的耳鳴不是嚴重的疾病，越在意、越緊張，"
            "越容易覺得它大聲。",
            None,
        ),
        (
            "注意睡眠、放鬆心情，避免太安靜的環境；如果也覺得聽不清楚，建議做一次聽力檢查。",
            AUDIOGRAM,
        ),
        RETAKE,
    ),
    38: (
        ("耳鳴對您的睡眠、專心或心情已經有明顯影響。", None),
        ("建議到醫院耳鼻喉科檢查，並請聽力師評估，可以帶著聽力報告去。", REPORT),
        (
            "如果您也有聽力損失，配戴助聽器常能讓耳鳴比較不明顯；也可以和聽力師討論聲音治療等方式。",
            None,
        ),
        RETAKE,
    ),
    58: (
        ("耳鳴已經嚴重影響您的生活，請盡快到醫院耳鼻喉科就診，並請聽力師評估。", REPORT),
        ("可以和聽力師討論助聽器、聲音治療等處理方式。", None),
        (
            "如果耳鳴讓您心情低落、很難熬，可以撥 1925 安心專線（24 小時免付費），有專人陪您聊聊。",
            None,
        ),
        RETAKE,
    ),
    78: (
        (
            "耳鳴已經非常嚴重地影響您的生活和心情，請盡快到醫院耳鼻喉科就診，並請聽力師評估。",
            REPORT,
        ),
        ("如果同時有失眠、焦慮或心情低落，也可以請身心科一起協助。", None),
        ("覺得撐不下去時，請撥 1925 安心專線（24 小時免付費），有專人陪您聊聊。", None),
        RETAKE,
    ),
}
ADVICE = {
    0: (
        "耳鳴目前對您的生活影響不大。耳鳴在安靜的環境比較明顯，可以讓身邊保持一些柔和的聲音，"
        "例如開著收音機或風扇。若耳鳴突然變大聲、只有一邊耳朵有，或同時聽力變差、頭暈，"
        "請盡快就醫。"
    ),
    18: (
        "耳鳴已經對您的生活有些影響。大部分的耳鳴不是嚴重的疾病，越在意、越緊張，"
        "越容易覺得它大聲。注意睡眠、放鬆心情、避免太安靜的環境都有幫助；"
        "如果也覺得聽不清楚，建議做一次聽力檢查。"
    ),
    38: (
        "耳鳴對您的睡眠、專心或心情已經有明顯影響。建議到醫院耳鼻喉科檢查，並請聽力師評估。"
        "如果您也有聽力損失，配戴助聽器常能讓耳鳴比較不明顯；也可以和聽力師討論聲音治療等方式。"
    ),
    58: (
        "耳鳴已經嚴重影響您的生活。請盡快到醫院耳鼻喉科就診，並請聽力師評估，"
        "討論助聽器、聲音治療等處理方式。耳鳴讓人心情低落、睡不好是很常見的，"
        "如果覺得很難熬，可以撥 1925 安心專線（24 小時免付費），有專人陪您聊聊。"
    ),
    78: (
        "耳鳴已經非常嚴重地影響您的生活和心情。請盡快到醫院耳鼻喉科就診，並請聽力師評估；"
        "如果同時有失眠、焦慮或心情低落，也可以請身心科一起協助。覺得撐不下去時，"
        "請撥 1925 安心專線（24 小時免付費），有專人陪您聊聊。"
    ),
}


class ThiResultAdviceTests(ThiTestCase):
    def _main(self, total):
        self.post_web(scores_for(total))
        submission = Submission.objects.latest("pk")
        content = self.client.get(reverse("result", args=[submission.pk])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def test_each_level_shows_its_draft_advice(self):
        for total, advice in ADVICE.items():
            with self.subTest(total=total):
                self.assertIn(f"<p>{advice}</p>", self._main(total))

    def test_severe_and_catastrophic_advice_mention_the_1925_line(self):
        for total in (58, 78):
            with self.subTest(total=total):
                advice = self._main(total).split("完整建議", 1)[1]
                self.assertIn(LINE_1925, advice)

    def test_each_level_shows_its_steps_ending_with_the_three_month_retake(self):
        for total, expected in STEPS.items():
            with self.subTest(total=total):
                main = self._main(total)
                start = main.index('<ol class="next-steps">')
                items = main[start : main.index("</ol>", start)].split("<li>")[1:]
                self.assertEqual(len(items), len(expected))
                for item, (text, action) in zip(items, expected, strict=True):
                    self.assertIn(f"<span>{text}</span>", item)
                    if action is None:
                        self.assertNotIn("<a ", item)
                    else:
                        label, url = action
                        self.assertIn(f'href="{url}">{label}</a>', item)
                self.assertIn(f"<span>{RETAKE[0]}</span>", items[-1])
                self.assertNotIn("半年後", main)
                self.assertNotIn("首頁會提醒您", main)


class ThiNotLifeImpactTests(ThiTestCase):
    """Spec #208 stories 22–24 (ADR 0016): THI leaves the home page and IOI-HA to HHIE-S/HHIA-S."""

    def _record(self, questionnaire, score, day, wearing=False):
        submission = Submission.objects.create(
            user=self.user, questionnaire=questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=submission, question=question, score=score)
            for question in questionnaire.questions.all()
        )
        noon = timezone.make_aware(datetime.combine(day, time(12)))
        Submission.objects.filter(pk=submission.pk).update(created_at=noon)
        return submission

    def _home(self, today):
        real_localdate = timezone.localdate

        def localdate(value=None, timezone=None):
            return today if value is None else real_localdate(value, timezone)

        with patch("django.utils.timezone.localdate", localdate):
            content = self.client.get(reverse("index")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def test_retest_reminder_follows_hhie_s_not_a_later_thi(self):
        self._record(self.hhie_s, 0, date(2026, 3, 1))
        self._record(self.thi, 2, date(2026, 5, 1))
        main = self._home(date(2026, 9, 1))
        self.assertIn("距離上次的生活影響評估已經滿 6 個月，建議再做一次追蹤。", main)
        retake = reverse("screening", args=[self.hhie_s.pk])
        self.assertIn(f'href="{retake}">再做一次（大約 3 分鐘）</a>', main)
        self.assertNotIn(f'href="{reverse("screening", args=[self.thi.pk])}"', main)

    def test_next_suggested_date_follows_hhie_s_not_a_later_thi(self):
        self._record(self.hhie_s, 0, date(2026, 3, 1))
        self._record(self.thi, 2, date(2026, 5, 1))
        main = self._home(date(2026, 8, 1))
        self.assertIn('<p class="mt-4">下次建議 2026/09/01 再做</p>', main)

    def test_only_thi_is_a_returning_user_without_a_retest_reminder(self):
        self._record(self.thi, 2, date(2026, 3, 1))
        main = self._home(date(2026, 10, 1))
        self.assertIn("歡迎回來", main)
        self.assertIn("耳鳴對生活的影響（THI）", main)
        self.assertNotIn("距離上次的生活影響評估", main)
        self.assertNotIn("下次建議", main)
        self.assertNotIn("再做一次", main)

    def test_an_unaided_thi_changes_neither_the_wizard_nor_the_ioi_ha_norm(self):
        ioi_ha = Questionnaire.objects.get(code="ioi-ha")
        params = {"age_group": "older", "hearing_aid": "yes"}
        before = self.client.get(reverse("questionnaire_list"), params).context
        self._record(self.thi, 0, date(2026, 3, 1))
        after = self.client.get(reverse("questionnaire_list"), params).context
        self.assertEqual(after["recommended"], before["recommended"])
        self.assertEqual(after["recommended"], self.hhie_s)
        self.assertEqual(after["reason"], before["reason"])
        self.assertEqual(after["reason"], "needs_norm_basis")
        page = self.client.get(reverse("screening", args=[ioi_ha.pk]))
        self.assertEqual(page.context["ioi_norm"], {"norm_group": "ungrouped", "norm_basis": None})


class ThiOtherPagesTests(ThiTestCase):
    """Pages that list every graded record still open with a THI record (their THI parts are
    #214 and #215)."""

    def test_my_records_report_and_export_open(self):
        self.post_web(scores_for(38))
        self.post_web(scores_for(58), wearing="True")
        for name, params in (
            ("my_hearing", {}),
            ("my_hearing", {"questionnaire": "thi"}),
            ("health_report", {}),
            ("download_my_data", {}),
        ):
            with self.subTest(page=name, params=params):
                self.assertEqual(self.client.get(reverse(name), params).status_code, 200)
