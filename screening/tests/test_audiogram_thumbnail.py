from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from screening.audiogram_thumbnail import _y, thumbnail
from screening.models import Audiogram, AudiogramPoint
from screening.tests import test_layout
from screening.tests.helpers import consented_user


def _point(ear, frequency, db, conduction="air", no_response=False):
    return AudiogramPoint(
        ear=ear, conduction=conduction, frequency=frequency, db=db, no_response=no_response
    )


def _xy(text):
    return [tuple(float(n) for n in pair.split(",")) for pair in text.split()]


class ThumbnailDrawingTests(TestCase):
    """Spec docs/specs/phase9_ui_refresh_4c_audiogram_thumbnails.md, acceptance 2-5."""

    # 2
    def test_right_ear_goes_down_as_hearing_gets_worse(self):
        drawing = thumbnail(
            [_point("right", f, db) for f, db in ((500, 20), (1000, 40), (2000, 60))]
        )
        [line] = drawing["lines"]
        self.assertEqual(line["ear"], "right")
        corners = _xy(line["points"])
        self.assertEqual(len(corners), 3)
        xs, ys = zip(*corners, strict=True)
        self.assertEqual(list(xs), sorted(xs))  # higher frequency further right
        self.assertEqual(list(ys), sorted(ys))  # more dB further down
        self.assertEqual([m["ear"] for m in drawing["marks"]], ["right"] * 3)

    # 3
    def test_left_ear_marked_and_bone_left_out(self):
        drawing = thumbnail(
            [
                _point("left", 500, 30),
                _point("left", 1000, 35),
                _point("left", 500, 10, conduction="bone"),
            ]
        )
        self.assertEqual([line["ear"] for line in drawing["lines"]], ["left"])
        self.assertEqual(len(drawing["marks"]), 2)
        self.assertEqual({m["ear"] for m in drawing["marks"]}, {"left"})

    # 4
    def test_missing_frequency_skipped_and_no_response_breaks_the_line(self):
        skipped = thumbnail([_point("right", 500, 20), _point("right", 2000, 40)])
        self.assertEqual(len(_xy(skipped["lines"][0]["points"])), 2)

        broken = thumbnail(
            [
                _point("right", 500, 20),
                _point("right", 1000, 30),
                _point("right", 2000, 120, no_response=True),
                _point("right", 4000, 50),
                _point("right", 8000, 60),
            ]
        )
        self.assertEqual([len(_xy(line["points"])) for line in broken["lines"]], [2, 2])
        self.assertEqual(len(broken["marks"]), 5)  # the no-response point is still drawn

    # 4: a piece left with a single point gets no line, as on the full chart
    def test_single_points_get_no_line(self):
        drawing = thumbnail(
            [
                _point("right", 500, 20),
                _point("right", 1000, 120, no_response=True),
                _point("right", 2000, 40),
            ]
        )
        self.assertEqual(drawing["lines"], [])
        self.assertEqual(len(drawing["marks"]), 3)

    # 5
    def test_no_air_points_gives_an_empty_grid(self):
        drawing = thumbnail([_point("right", 500, 10, conduction="bone")])
        self.assertEqual(drawing["lines"], [])
        self.assertEqual(drawing["marks"], [])
        self.assertTrue(drawing["grid"])
        self.assertIn("height", drawing["normal"])


class ThumbnailListTests(TestCase):
    """Acceptance 1 and 6-8 on the audiogram list."""

    def setUp(self):
        self.user = consented_user(username="thumb_a")
        self.client.force_login(self.user)

    def _audiogram(self, user, day=1, levels=(20, 40, 60)):
        audiogram = Audiogram.objects.create(user=user, tested_on=date(2026, 9, day))
        AudiogramPoint.objects.bulk_create(
            AudiogramPoint(audiogram=audiogram, ear=ear, conduction="air", frequency=f, db=db)
            for ear in ("right", "left")
            for f, db in zip((500, 1000, 2000), levels, strict=True)
        )
        return audiogram

    def _main(self):
        content = self.client.get(reverse("audiogram_list")).content.decode()
        return content[content.index("<main") : content.index("</main>")]

    # 1
    def test_each_card_has_a_hidden_thumbnail(self):
        self._audiogram(self.user)
        [card] = test_layout._cards(self._main())
        self.assertEqual(card.count("<a"), 1)
        self.assertRegex(card, r'<svg class="audiogram-thumbnail"[^>]*aria-hidden="true"')
        self.assertEqual(card.count("<polyline"), 2)

    # 6
    def test_query_count_does_not_grow(self):
        self._audiogram(self.user, 1)
        with CaptureQueriesContext(connection) as one:
            self._main()
        for day in range(2, 11):
            self._audiogram(self.user, day)
        with CaptureQueriesContext(connection) as ten:
            self._main()
        self.assertEqual(len(ten), len(one))

    # 7 (review A): A has an audiogram too, so B's points could show up inside A's thumbnail
    def test_other_users_audiograms_not_shown(self):
        self._audiogram(self.user, 1)
        other = consented_user(username="thumb_b")
        theirs = self._audiogram(other, 5, levels=(90, 100, 110))
        main = self._main()
        self.assertNotIn(reverse("audiogram_detail", args=[theirs.pk]), main)
        self.assertEqual(main.count('class="audiogram-thumbnail"'), 1)
        for db in (90, 100, 110):
            self.assertNotIn(f'cy="{_y(db)}"', main)

    # 8
    def test_each_ear_on_its_own_line(self):
        self._audiogram(self.user)
        [card] = test_layout._cards(self._main())
        # Each ear starts its own block; the text after each marker begins with that ear.
        lines = card.split('<span class="audiogram-ear">')[1:]
        self.assertEqual(len(lines), 2)
        self.assertTrue(test_layout._text(lines[0]).startswith("右耳"))
        self.assertTrue(test_layout._text(lines[1]).startswith("左耳"))
