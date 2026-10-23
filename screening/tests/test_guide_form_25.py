import re
from dataclasses import replace

from django.test import TestCase
from django.urls import reverse

from screening.models import Questionnaire
from screening.questionnaires import hhia_s, hhie_s, ioi_ha, sadl, ssq12_tw, thi
from screening.tests import test_guide
from screening.tests.helpers import register

# Wording finalised in #220 (F1-F7), shortened in the guide chapters tidy-up (2026-10-23, the
# owner's request): labelled facts, the things to bring as chips.
FORM_25 = (
    "「二十五號表」是配戴助聽器後的使用效益驗證報告書（格式編號 25），核銷補助時要附上。",
    # #319 (ADR 0025): the five facts under a title of their own, in its 段落框.
    "誰要做、怎麼做",
    "誰要做",
    "買中階型、進階型或雙對側傳聲型的人。簡易型不需要。",
    "什麼時候",
    "配戴滿 1 個月後、3 個月內。",
    "找誰開",
    "和九號表一樣，聽力師或輔具中心的評估人員。",
    "驗證做什麼",
    "聽力師核對保固書上的序號和廠牌型號，再用儀器測量或聽力測驗確認助聽器的效果。",
    "核銷要帶",
    "購買憑證 保固書影本 二十五號表",
    "保固書要有規格、型號、序號、保固期間、廠商資料和醫療器材許可證字號。",
)
FORM_25_SOURCES = (
    (
        "身心障礙者輔具費用補助辦法",
        "https://law.moj.gov.tw/LawClass/LawAll.aspx?PCODE=D0050060",
    ),
    (
        "身心障礙者輔具費用補助基準表",
        "https://law.moj.gov.tw/LawClass/LawGetFile.ashx?FileId=0000326887&amp;lan=C",
    ),
    (
        "輔具評估報告書（使用效益驗證）格式編號 25",
        "https://atrc.aihsin.ntpc.gov.tw/Download/eform/12/【報告書】編號25-助聽器使用效益驗證.pdf",
    ),
)


# Verification-flow batch F3, reviewed in the chat on 2026-10-23.
PREPARE = (
    "用 HearWell 準備驗證回診",
    "驗證前，可以先戴著助聽器做這些問卷，再印出聽力報告帶去，讓聽力師了解您戴了之後的感受：",
    "戴著再做一次聽力對生活的影響（HHIE-S 或 HHIA-S），和沒戴時的結果比較",
    "助聽器使用成效（IOI-HA）",
    "助聽器滿意度（SADL）",
    "這些結果給聽力師參考，不能取代二十五號表的驗證。",
    "看／印聽力報告",
)


def inline_text(response):
    """Like test_guide.text_of, but links inside a sentence leave no space around them."""
    content = response.content.decode()
    main = content[content.index("<main") : content.index("</main>")]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", main))


class Form25ChapterTests(TestCase):
    """#225: the form 25 chapter, open to anyone."""

    @classmethod
    def setUpTestData(cls):
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)
        cls.hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code=hhia_s.CODE)
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code=ioi_ha.CODE)
        cls.ssq12 = Questionnaire.objects.create(questionnaire_name="SSQ12-TW", code=ssq12_tw.CODE)
        cls.sadl = Questionnaire.objects.create(questionnaire_name="SADL", code=sadl.CODE)

    def setUp(self):
        self.url = reverse("guide_chapter", args=["form-25"])

    def test_logged_out_visitor_reads_when_and_what_to_bring(self):
        # One read of the questionnaire table for the preparation card's links; no user data.
        with self.assertNumQueries(1):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1 class="h3 mt-4">二十五號表：使用效益驗證</h1>')
        text = test_guide.text_of(response)
        positions = [text.index(sentence) for sentence in FORM_25]
        self.assertEqual(positions, sorted(positions))

    def test_footer_has_the_check_date_and_official_sources(self):
        response = self.client.get(self.url)
        test_guide.assert_footer(self, response, "2026-10-22", FORM_25_SOURCES)

    # #319: the five facts are a part titled 誰要做、怎麼做, read out as a region by that name.
    def test_the_five_facts_are_a_titled_part(self):
        part = test_guide.part(self.client.get(self.url), "誰要做、怎麼做")
        for label in ("誰要做", "什麼時候", "找誰開", "驗證做什麼", "核銷要帶"):
            with self.subTest(label=label):
                self.assertIn(f"<dt>{label}</dt>", part)

    def test_preparation_card_after_the_list_links_the_questionnaires_and_report(self):
        response = self.client.get(self.url)
        text = inline_text(response)
        positions = [text.index(sentence) for sentence in (FORM_25[-1], *PREPARE)]
        self.assertEqual(positions, sorted(positions))
        content = response.content.decode()
        for questionnaire, wording in (
            (self.hhie_s, "HHIE-S"),
            (self.hhia_s, "HHIA-S"),
            (self.ioi_ha, "助聽器使用成效（IOI-HA）"),
            (self.sadl, "助聽器滿意度（SADL）"),
        ):
            with self.subTest(questionnaire=wording):
                href = reverse("screening", args=[questionnaire.pk])
                self.assertRegex(content, rf'<a href="{href}">\s*{wording}\s*</a>')
        self.assertIn(f'href="{reverse("health_report")}">看／印聽力報告</a>', content)
        # SSQ12-TW is the after-fitting chapter's, not this card's.
        self.assertNotIn(f'href="{reverse("screening", args=[self.ssq12.pk])}"', content)


# Wording finalised in #220 (H2-H7, H10; H8 and H9 come from the questionnaire definitions),
# shortened in the guide chapters tidy-up (2026-10-23, the owner's request): each point's gist
# as a label.
AFTER_FITTING = (
    # #319 (ADR 0025): the four points under a title of their own, in its 段落框.
    "剛開始戴助聽器",
    "剛開始不習慣是正常的",
    "前幾週可能覺得自己的聲音怪怪的、環境很吵，大腦需要時間重新適應聲音。",
    "每天戴，慢慢拉長",
    "照聽力師的建議，從安靜的地方、短時間開始。",
    "不舒服就回去調整",
    "太吵、太小聲或不舒服，都可以請聽力師調整，不用勉強忍耐。記下哪些場合聽不清楚，回診時告訴聽力師。",
    "不會跟以前完全一樣",
    "在吵雜的餐廳、多人聊天時，還是可能聽不清楚。",
    "記錄配戴的效果",
    "戴一段時間後，可以用 HearWell 的問卷記錄感受，印出聽力報告給聽力師看。",
    # F4 (verification-flow batch): the two life-impact questionnaires named and linked.
    "也可以戴著助聽器再做一次生活影響問卷（HHIE-S 或 HHIA-S），和沒戴時比較。",
)
# The family guide's sources for the same reviewed wording (its 「陪伴配戴助聽器」 section).
AFTER_FITTING_SOURCES = (
    (
        "Hearing Aids for Adults",
        "https://www.asha.org/practice-portal/professional-issues/hearing-aids-for-adults/",
    ),
    ("Hearing Aids", "https://www.nidcd.nih.gov/sites/default/files/hearing-aids.pdf"),
)


class AfterFittingChapterTests(TestCase):
    """#225: the after-fitting chapter, open to anyone."""

    @classmethod
    def setUpTestData(cls):
        cls.ioi_ha = Questionnaire.objects.create(questionnaire_name="IOI-HA", code=ioi_ha.CODE)
        cls.ssq12 = Questionnaire.objects.create(questionnaire_name="SSQ12-TW", code=ssq12_tw.CODE)
        cls.sadl = Questionnaire.objects.create(questionnaire_name="SADL", code=sadl.CODE)
        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)
        cls.hhia_s = Questionnaire.objects.create(questionnaire_name="HHIA-S", code=hhia_s.CODE)
        cls.others = (Questionnaire.objects.create(questionnaire_name="THI", code=thi.CODE),)

    def setUp(self):
        self.url = reverse("guide_chapter", args=["after-fitting"])

    def test_logged_out_visitor_reads_that_getting_used_to_it_takes_time(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1 class="h3 mt-4">配戴助聽器之後</h1>')
        text = inline_text(response)
        positions = [text.index(sentence) for sentence in AFTER_FITTING]
        self.assertEqual(positions, sorted(positions))

    def test_footer_has_the_check_date_and_official_sources(self):
        response = self.client.get(self.url)
        test_guide.assert_footer(self, response, "2026-10-22", AFTER_FITTING_SOURCES)

    # #319: the four points are a part titled 剛開始戴助聽器, read out as a region by that name.
    def test_the_four_points_are_a_titled_part(self):
        part = test_guide.part(self.client.get(self.url), "剛開始戴助聽器")
        for point in AFTER_FITTING[1:9:2]:
            with self.subTest(point=point):
                self.assertIn(f"<dt>{point}</dt>", part)

    def test_links_only_the_follow_up_questionnaires_in_the_catalogue_wording(self):
        # One read of the questionnaire table for their addresses; no user data.
        with self.assertNumQueries(1):
            response = self.client.get(self.url)
        content = response.content.decode()
        text = inline_text(response)
        # H8, H9, then SADL (added by the owner after #220): the catalogue's own wording for
        # each card (topic, name, audience).
        follow_ups = (
            (self.ioi_ha, "助聽器使用成效（IOI-HA）：適合已配戴助聽器的人。"),
            (self.ssq12, "日常聆聽能力（SSQ12-TW）：了解您目前生活中的聆聽能力。"),
            (self.sadl, "助聽器滿意度（SADL）：給正在戴或最近戴過助聽器的人。"),
        )
        for questionnaire, wording in follow_ups:
            with self.subTest(questionnaire=questionnaire.questionnaire_name):
                href = reverse("screening", args=[questionnaire.pk])
                self.assertRegex(content, rf'<a href="{href}">\s*{wording}\s*</a>')
        positions = [text.index(wording) for _, wording in follow_ups]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(text.index(AFTER_FITTING[-2]), positions[0])
        self.assertLess(positions[-1], text.index(AFTER_FITTING[-1]))
        # Only these three: not every questionnaire on the site.
        for questionnaire in self.others:
            with self.subTest(questionnaire=questionnaire.questionnaire_name):
                href = f'href="{reverse("screening", args=[questionnaire.pk])}"'
                self.assertNotIn(href, content)

    def test_the_aided_retake_sentence_links_both_life_impact_questionnaires(self):
        content = self.client.get(self.url).content.decode()
        for questionnaire in (self.hhie_s, self.hhia_s):
            with self.subTest(questionnaire=questionnaire.questionnaire_name):
                href = reverse("screening", args=[questionnaire.pk])
                self.assertIn(f'<a href="{href}">{questionnaire}</a>', content)

    def test_a_follow_up_missing_from_the_database_is_left_out(self):
        Questionnaire.objects.filter(pk=self.ioi_ha.pk).delete()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn(f'href="{reverse("screening", args=[self.ioi_ha.pk])}"', content)
        for questionnaire in (self.ssq12, self.sadl):
            with self.subTest(questionnaire=questionnaire.questionnaire_name):
                self.assertIn(f'href="{reverse("screening", args=[questionnaire.pk])}"', content)

    def test_an_unlisted_follow_up_is_not_linked(self):
        with register(replace(sadl.DEFINITION, listed=False)), self.assertNumQueries(1):
            response = self.client.get(self.url)
        content = response.content.decode()
        self.assertNotIn(f'href="{reverse("screening", args=[self.sadl.pk])}"', content)
        for questionnaire in (self.ioi_ha, self.ssq12):
            with self.subTest(questionnaire=questionnaire.questionnaire_name):
                self.assertIn(f'href="{reverse("screening", args=[questionnaire.pk])}"', content)
