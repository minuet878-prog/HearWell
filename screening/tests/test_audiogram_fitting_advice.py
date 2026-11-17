"""#698 (spec #693 acceptance 14, 15, ADR 0067): the audiogram page's solid button and the speech
banana's guide card follow 建議評估選配 for the audiogram opened, judged with its owner's latest
life-impact record."""

from datetime import date

from django.urls import reverse

from screening.models import AidAndSubsidy, Audiogram, AudiogramPoint, Submission
from screening.questionnaires import hhie_s, ioi_ha
from screening.tests import test_audiogram, test_fitting_advice, test_records_redesign
from screening.tests.helpers import consented_user

GUIDE = "看助聽器選配與補助"
BANANA = "看語言香蕉區"
GUIDE_CARD = "依您的聽力圖整理下一步"


class FittingAdviceAudiogramPageTests(test_fitting_advice.LifeImpactTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = consented_user(username="fitting_advice_audiogram_page")
        cls.other = consented_user(username="fitting_advice_audiogram_other")

    def setUp(self):
        self.client.force_login(self.user)

    def make(self, right, left, tested_on=date(2026, 11, 1)):
        """An audiogram with each ear's four PTA frequencies flat at a value, so its PTA."""
        audiogram = Audiogram.objects.create(user=self.user, tested_on=tested_on)
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, **point)
            for side, value in (("right", right), ("left", left))
            for point in test_audiogram._four(test_audiogram._air, side, (value,) * 4)
        )
        return audiogram

    def record(self, scores, user=None, on=date(2026, 11, 1)):
        test_fitting_advice.record(user or self.user, scores, on=on)

    def main(self, name, audiogram):
        content = self.client.get(reverse(name, args=[audiogram.id])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def pages(self, audiogram):
        """(the audiogram page's solid buttons, whether the speech banana has the guide card)."""
        detail = self.main("audiogram_detail", audiogram)
        banana = self.main("audiogram_speech_banana", audiogram)
        return test_records_redesign.solid_buttons(detail), GUIDE_CARD in banana

    def assert_recommends(self, audiogram):
        buttons, card = self.pages(audiogram)
        self.assertEqual(buttons, [GUIDE])
        self.assertTrue(card)

    def assert_does_not_recommend(self, audiogram):
        buttons, card = self.pages(audiogram)
        self.assertEqual(buttons, [BANANA])
        self.assertFalse(card)
        self.assertNotIn(GUIDE, self.main("audiogram_speech_banana", audiogram))

    def test_over_40_recommends_on_both_pages_without_a_questionnaire(self):
        # Right 45 dB HL (中度), left 10: one ear is enough, no life-impact record needed.
        self.assert_recommends(self.make(45, 10))

    def test_mild_with_life_impact_recommends_on_both_pages(self):
        for scores in (test_fitting_advice.MILD_SCORES, test_fitting_advice.SEVERE_SCORES):
            with self.subTest(scores=scores):
                self.record(scores)
                self.assert_recommends(self.make(30, 10))

    def test_normal_tracked_and_questionnaire_first_show_the_speech_banana(self):
        # 正常 (both at 25), 先做問卷 (輕度 with no record), 追蹤 (輕度, 無／極輕微影響).
        self.assert_does_not_recommend(self.make(25, 25))
        self.assert_does_not_recommend(self.make(40, 10))
        self.record(test_fitting_advice.NORMAL_SCORES)
        self.assert_does_not_recommend(self.make(40, 10))

    def test_the_latest_life_impact_record_decides(self):
        audiogram = self.make(30, 10)
        self.record(test_fitting_advice.MILD_SCORES, on=date(2026, 10, 1))
        self.record(test_fitting_advice.NORMAL_SCORES, on=date(2026, 11, 1))
        self.assert_does_not_recommend(audiogram)
        self.record(test_fitting_advice.MILD_SCORES, on=date(2026, 11, 10))
        self.assert_recommends(audiogram)

    def test_the_audiogram_opened_decides_not_the_latest_one(self):
        older = self.make(45, 45, tested_on=date(2026, 9, 1))
        newer = self.make(20, 20, tested_on=date(2026, 11, 1))
        self.assert_recommends(older)
        self.assert_does_not_recommend(newer)

    def test_the_questionnaire_is_the_audiogram_owners(self):
        # Spec #693 acceptance 15: the owner's own record, never someone else's.
        audiogram = self.make(30, 10)
        self.record(test_fitting_advice.MILD_SCORES, user=self.other)
        self.assert_does_not_recommend(audiogram)
        self.record(test_fitting_advice.MILD_SCORES)
        self.assert_recommends(audiogram)


class SelfReview693WearingAudiogramPageTests(test_fitting_advice.LifeImpactTestCase):
    """The self review on #693: someone wearing hearing aids sees the guide on both pages
    whatever the advice, as my guide keeps the route for them; 'wearing' as the route judges it."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = consented_user(username="fitting_advice_wearing")

    def setUp(self):
        self.client.force_login(self.user)

    make = FittingAdviceAudiogramPageTests.make
    main = FittingAdviceAudiogramPageTests.main
    pages = FittingAdviceAudiogramPageTests.pages
    assert_recommends = FittingAdviceAudiogramPageTests.assert_recommends
    assert_does_not_recommend = FittingAdviceAudiogramPageTests.assert_does_not_recommend

    def record(self, scores, wearing, code=hhie_s.CODE):
        submission = test_fitting_advice.record(self.user, scores, code=code)
        Submission.objects.filter(pk=submission.pk).update(wearing_hearing_aid=wearing)

    def test_the_latest_record_answered_wearing_them_shows_the_guide(self):
        # Within the normal range and 無／極輕微影響: 正常, yet wearing.
        audiogram = self.make(20, 20)
        self.record(test_fitting_advice.NORMAL_SCORES, wearing=False)
        self.assert_does_not_recommend(audiogram)
        self.record(test_fitting_advice.NORMAL_SCORES, wearing=True)
        self.assert_recommends(audiogram)

    def test_ioi_ha_as_the_latest_record_shows_the_guide(self):
        audiogram = self.make(20, 20)
        self.record((1,) * 7 + (0,) * 3, wearing=None, code=ioi_ha.CODE)
        self.assert_recommends(audiogram)

    def test_a_fitting_date_shows_the_guide(self):
        audiogram = self.make(30, 10)  # 輕度 without a questionnaire: 先做問卷
        AidAndSubsidy.objects.create(user=self.user, fitted_on=date(2026, 10, 1))
        self.assert_recommends(audiogram)
