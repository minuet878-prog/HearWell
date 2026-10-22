"""Spec #218, ticket #230: the hearing-aid guide entry on the audiogram result page."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from screening.models import Audiogram, AudiogramPoint
from screening.tests import test_audiogram
from screening.tests.helpers import consented_user

# Wording finalised in #220 (E3), written out so a changed template fails.
GUIDE_LINK = 'href="/guide">看我的選配指引</a>'


def ear(side, values):
    return test_audiogram._four(test_audiogram._air, side, values)


class GuideAudiogramEntryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="guide_audiogram_user")

    def setUp(self):
        self.client.force_login(self.user)

    def _main(self, points):
        audiogram = Audiogram.objects.create(user=self.user, tested_on=date(2026, 10, 1))
        AudiogramPoint.objects.bulk_create(AudiogramPoint(audiogram=audiogram, **p) for p in points)
        content = self.client.get(reverse("audiogram_detail", args=[audiogram.id])).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def test_one_ear_over_25_links_to_the_guide_in_what_comes_next(self):
        # Right 26.25 dB HL, left 10: one side is enough.
        main = self._main([*ear("right", (25, 25, 25, 30)), *ear("left", (10, 10, 10, 10))])
        self.assertEqual(main.count(GUIDE_LINK), 1)
        next_steps = main[main.index('aria-labelledby="next-title"') :]
        self.assertIn(GUIDE_LINK, next_steps[: next_steps.index("</section>")])

    def test_both_ears_at_or_under_25_have_no_guide_link(self):
        # Right exactly 25 dB HL (not over), left 10.
        main = self._main([*ear("right", (25, 25, 25, 25)), *ear("left", (10, 10, 10, 10))])
        self.assertIn("看／印聽力報告", main)
        self.assertNotIn('href="/guide"', main)

    def test_without_enough_data_there_is_no_guide_link(self):
        three = [test_audiogram._air("left", f, 60) for f in (500, 1000, 2000)]
        cases = {
            # Neither ear has all four average frequencies.
            "both unknown": [*three, test_audiogram._air("right", 500, 60)],
            # The unknown left ear could still be over 25.
            "one normal, one unknown": [*ear("right", (10, 10, 10, 10)), *three],
        }
        for name, points in cases.items():
            with self.subTest(name):
                self.assertNotIn('href="/guide"', self._main(points))

    def test_one_ear_over_25_is_enough_even_if_the_other_is_unknown(self):
        three = [test_audiogram._air("left", f, 10) for f in (500, 1000, 2000)]
        main = self._main([*ear("right", (40, 40, 40, 40)), *three])
        self.assertEqual(main.count(GUIDE_LINK), 1)
