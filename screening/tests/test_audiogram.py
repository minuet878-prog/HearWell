import json
import re
import uuid
from datetime import date, timedelta
from unittest import mock

from django.db import DatabaseError, connection
from django.test import Client, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from screening.models import User
from screening.tests import test_answering, test_pages


def _point(conduction, ear, frequency, db, no_response):
    return {
        "ear": ear,
        "conduction": conduction,
        "frequency": frequency,
        "db": db,
        "no_response": no_response,
    }


def _air(ear, frequency, db, no_response=False):
    return _point("air", ear, frequency, db, no_response)


def _bone(ear, frequency, db, no_response=False):
    return _point("bone", ear, frequency, db, no_response)


def _four(maker, ear, values):
    return [maker(ear, f, db) for f, db in zip((500, 1000, 2000, 4000), values, strict=True)]


class AudiogramRuleTests(SimpleTestCase):
    """Spec docs/specs/phase5_audiogram.md 4.3, acceptance 18-27 (the rules alone)."""

    def _interpret(self, points):
        from screening.audiogram import interpret

        objects = [mock.Mock(**point) for point in points]
        return interpret(objects)

    def test_pta_and_degree(self):
        right = self._interpret(_four(_air, "right", (40, 45, 50, 55)))["right"]
        self.assertEqual(right["pta"], 47.5)
        self.assertEqual(right["degree"], "中度")

    def test_degree_boundaries(self):
        from screening.audiogram import degree

        expected = {
            25: "正常",
            26.25: "輕度",
            40: "輕度",
            41.25: "中度",
            55: "中度",
            56.25: "中重度",
            70: "中重度",
            71.25: "重度",
            90: "重度",
            91.25: "極重度",
        }
        for value, name in expected.items():
            with self.subTest(value=value):
                self.assertEqual(degree(value), name)

    def test_type(self):
        cases = {(45,) * 4: "感音神經性", (20,) * 4: "傳導性", (30,) * 4: "混合性"}
        for bone, expected in cases.items():
            with self.subTest(bone=bone):
                points = _four(_air, "right", (50,) * 4) + _four(_bone, "right", bone)
                self.assertEqual(self._interpret(points)["right"]["type"], expected)

    def test_type_boundaries(self):
        from screening.audiogram import hearing_type

        self.assertEqual(hearing_type(25, None), "正常")
        self.assertEqual(hearing_type(50, 35.25), "感音神經性")  # gap 14.75
        self.assertEqual(hearing_type(50, 35), "混合性")  # gap 15, bone > 25
        self.assertEqual(hearing_type(40, 25), "傳導性")  # gap 15, bone 25

    def test_normal_air_needs_no_bone(self):
        right = self._interpret(_four(_air, "right", (20,) * 4))["right"]
        self.assertEqual(right["degree"], "正常")
        self.assertEqual(right["type"], "正常")

    def test_missing_air_frequency_is_insufficient(self):
        points = [_air("right", f, 40) for f in (500, 1000, 4000)] + _four(_air, "left", (40,) * 4)
        result = self._interpret(points)
        self.assertIsNone(result["right"]["pta"])
        self.assertIsNone(result["right"]["degree"])
        self.assertEqual(result["left"]["degree"], "輕度")

    def test_incomplete_bone_leaves_type_open(self):
        bone = [_bone("right", f, 45) for f in (500, 2000, 4000)]
        points = _four(_air, "right", (50,) * 4) + bone
        right = self._interpret(points)["right"]
        self.assertEqual(right["degree"], "中度")
        self.assertIsNone(right["type"])

    def test_only_outer_frequencies_is_insufficient(self):
        points = [_air(ear, f, 40) for ear in ("right", "left") for f in (250, 8000)]
        result = self._interpret(points)
        self.assertIsNone(result["right"]["pta"])
        self.assertIsNone(result["left"]["pta"])

    def test_no_response_uses_marked_value(self):
        points = [_air("right", f, db) for f, db in ((500, 90), (1000, 100), (2000, 110))]
        points.append(_air("right", 4000, 120, no_response=True))
        right = self._interpret(points)["right"]
        self.assertEqual(right["pta"], 105)
        self.assertEqual(right["degree"], "極重度")
        self.assertTrue(right["no_response"])

    def test_bone_no_response_uses_80(self):
        points = _four(_air, "right", (100,) * 4)
        points += [_bone("right", f, db) for f, db in ((500, 60), (1000, 70), (2000, 75))]
        points.append(_bone("right", 4000, 80, no_response=True))
        right = self._interpret(points)["right"]
        self.assertEqual(right["type"], "混合性")  # bone 71.25, gap 28.75
        self.assertTrue(right["no_response"])

    def test_bone_no_response_value_decides_type(self):
        # Review 3-3: at an air average of 86.25 only 80 gives a gap of 15 or more.
        points = [_air("right", f, db) for f, db in ((500, 85), (1000, 85), (2000, 85), (4000, 90))]
        points += [_bone("right", f, db) for f, db in ((500, 60), (1000, 70), (2000, 75))]
        points.append(_bone("right", 4000, 80, no_response=True))
        self.assertEqual(self._interpret(points)["right"]["type"], "混合性")

    def test_masked_counts_like_unmasked(self):
        # Acceptance 39: interpretation reads values only.
        points = [{**p, "masked": True} for p in _four(_air, "right", (40, 45, 50, 55))]
        right = self._interpret(points)["right"]
        self.assertEqual(right["pta"], 47.5)
        self.assertEqual(right["degree"], "中度")

    def test_no_response_outside_pta_has_no_note(self):
        points = [*_four(_air, "right", (40,) * 4), _air("right", 8000, 120, no_response=True)]
        self.assertFalse(self._interpret(points)["right"]["no_response"])


class AudiogramApiTests(TestCase):
    """Spec docs/specs/phase5_audiogram.md, acceptance 12-17 and 30 (API side)."""

    URL = "/api/audiograms/"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="audiogram_api")
        cls.other = User.objects.create_user(username="audiogram_other")

    def setUp(self):
        self.client.force_login(self.user)

    def _body(self, points=None, tested_on="2026-10-01"):
        points = _four(_air, "right", (40, 45, 50, 55)) if points is None else points
        return {"tested_on": tested_on, "points": points}

    def _post(self, body, key="__new__"):
        headers = {"Idempotency-Key": str(uuid.uuid4()) if key == "__new__" else key}
        return self.client.post(
            self.URL, json.dumps(body), content_type="application/json", headers=headers
        )

    def _models(self):
        from screening.models import Audiogram, AudiogramPoint

        return Audiogram, AudiogramPoint

    def assertNothingSaved(self):
        Audiogram, AudiogramPoint = self._models()
        self.assertEqual(Audiogram.objects.count(), 0)
        self.assertEqual(AudiogramPoint.objects.count(), 0)

    def test_create(self):
        response = self._post(self._body())
        self.assertEqual(response.status_code, 201)
        Audiogram, _ = self._models()
        audiogram = Audiogram.objects.get()
        self.assertEqual(audiogram.user, self.user)
        self.assertEqual(audiogram.tested_on, date(2026, 10, 1))
        self.assertEqual(audiogram.points.count(), 4)
        body = response.json()
        self.assertEqual(body["id"], audiogram.id)
        self.assertEqual(body["interpretation"]["right"]["pta"], 47.5)
        self.assertEqual(body["interpretation"]["right"]["degree"], "中度")

    def test_zero_and_minus_ten_are_kept(self):
        points = [_air("right", 500, 0), _air("right", 1000, -10)]
        self.assertEqual(self._post(self._body(points)).status_code, 201)
        Audiogram, _ = self._models()
        saved = {p.frequency: p.db for p in Audiogram.objects.get().points.all()}
        self.assertEqual(saved, {500: 0, 1000: -10})

    def test_no_response_points(self):
        points = [
            _air("left", 4000, 120, no_response=True),
            _bone("left", 1000, 80, no_response=True),
        ]
        self.assertEqual(self._post(self._body(points)).status_code, 201)
        Audiogram, _ = self._models()
        self.assertTrue(all(p.no_response for p in Audiogram.objects.get().points.all()))

    def test_masked(self):
        # Acceptance 41: missing means unmasked; only true/false accepted.
        points = [{**_air("right", 1000, 50), "masked": True}, _air("right", 2000, 50)]
        response = self._post(self._body(points))
        self.assertEqual(response.status_code, 201)
        Audiogram, _ = self._models()
        saved = {p.frequency: p.masked for p in Audiogram.objects.get().points.all()}
        self.assertEqual(saved, {1000: True, 2000: False})
        self.assertIn({**_air("right", 1000, 50), "masked": True}, response.json()["points"])
        Audiogram.objects.all().delete()
        for value in ("yes", 1, None):
            with self.subTest(masked=value):
                bad = [{**_air("right", 1000, 50), "masked": value}]
                self.assertEqual(self._post(self._body(bad)).status_code, 400)
                self.assertNothingSaved()

    def test_same_key_different_masking_is_409(self):
        key = str(uuid.uuid4())
        self._post(self._body([_air("right", 1000, 50)]), key=key)
        masked = [{**_air("right", 1000, 50), "masked": True}]
        self.assertEqual(self._post(self._body(masked), key=key).status_code, 409)

    def test_retry_with_same_key_returns_first(self):
        key = str(uuid.uuid4())
        first = self._post(self._body(), key=key)
        second = self._post(self._body(), key=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["id"], first.json()["id"])
        Audiogram, _ = self._models()
        self.assertEqual(Audiogram.objects.count(), 1)

    def test_same_key_different_content_is_409(self):
        key = str(uuid.uuid4())
        self._post(self._body(), key=key)
        response = self._post(self._body(tested_on="2026-09-01"), key=key)
        self.assertEqual(response.status_code, 409)

    def test_missing_key_is_400(self):
        response = self._post(self._body(), key="")
        self.assertEqual(response.status_code, 400)
        self.assertNothingSaved()

    def test_invalid_points_are_400_and_save_nothing(self):
        invalid = {
            "frequency not listed": [_air("right", 750, 40)],
            "db not multiple of 5": [_air("right", 1000, 42)],
            "air above 120": [_air("right", 1000, 125)],
            "below -10": [_air("right", 1000, -15)],
            "bone above 80": [_bone("right", 1000, 85)],
            "bone at 3000": [_bone("right", 3000, 40)],
            "bone at 8000": [_bone("right", 8000, 40)],
            "air no response not at 120": [_air("right", 1000, 100, no_response=True)],
            "bone no response not at 80": [_bone("right", 1000, 70, no_response=True)],
            "duplicate point": [_air("right", 1000, 40), _air("right", 1000, 60)],
            "bad ear": [{**_air("right", 1000, 40), "ear": "both"}],
            "bad conduction": [{**_air("right", 1000, 40), "conduction": "bc"}],
            "no points": [],
        }
        for name, points in invalid.items():
            with self.subTest(name):
                # A valid point alongside makes sure nothing is saved partially.
                extra = [] if name == "no points" else [_air("left", 500, 30)]
                response = self._post(self._body(points + extra))
                self.assertEqual(response.status_code, 400)
                self.assertNothingSaved()

    def test_no_points_message(self):
        response = self._post(self._body([]))
        self.assertIn("請至少標記一個點", json.dumps(response.json(), ensure_ascii=False))

    def test_date_required_and_not_future(self):
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        for tested_on, message in ((None, "請填寫檢查日期"), (tomorrow, "檢查日期不能是未來")):
            with self.subTest(tested_on=tested_on):
                response = self._post(self._body(tested_on=tested_on))
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, json.dumps(response.json(), ensure_ascii=False))
                self.assertNothingSaved()
        today = timezone.localdate().isoformat()
        self.assertEqual(self._post(self._body(tested_on=today)).status_code, 201)

    def test_detail_is_own_only(self):
        mine = self._post(self._body()).json()["id"]
        self.assertEqual(self.client.get(f"{self.URL}{mine}/").status_code, 200)
        other = Client()
        other.force_login(self.other)
        self.assertEqual(other.get(f"{self.URL}{mine}/").status_code, 404)

    def test_same_key_from_another_user_is_separate(self):
        key = str(uuid.uuid4())
        self._post(self._body(), key=key)
        self.client.force_login(self.other)
        response = self._post(self._body(), key=key)
        self.assertEqual(response.status_code, 201)
        Audiogram, _ = self._models()
        self.assertEqual(Audiogram.objects.filter(user=self.other).count(), 1)

    def test_anonymous_gets_403(self):
        self.client.logout()
        self.assertEqual(self._post(self._body()).status_code, 403)


class AudiogramPageTests(TestCase):
    """Spec docs/specs/phase5_audiogram.md, acceptance 12, 18-33 (pages)."""

    INPUT_JS = "screening/frontend/audiogram-input.js"
    VIEW_JS = "screening/frontend/audiogram-view.js"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="audiogram_page")
        cls.other = User.objects.create_user(username="audiogram_page_other")

    def setUp(self):
        self.client.force_login(self.user)

    def _make(self, points, tested_on=date(2026, 10, 1), user=None):
        from screening.models import Audiogram, AudiogramPoint

        audiogram = Audiogram.objects.create(user=user or self.user, tested_on=tested_on)
        AudiogramPoint.objects.bulk_create(AudiogramPoint(audiogram=audiogram, **p) for p in points)
        return audiogram

    def _main(self, response):
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _ear_card(self, response, ear):
        main = self._main(response)
        match = re.search(rf'<section[^>]*data-ear="{ear}"[^>]*>(.*?)</section>', main, re.DOTALL)
        return match.group(1)

    # 新增頁
    def test_new_page_loads_react(self):
        response = self.client.get(reverse("audiogram_new"))
        self.assertContains(response, self.INPUT_JS)
        self.assertContains(response, 'id="audiogram-app"')
        self.assertContains(response, f'data-today="{timezone.localdate().isoformat()}"')
        self.assertContains(response, "需要開啟 JavaScript")

    def test_input_js_only_on_new_page(self):
        for url in (reverse("index"), reverse("my_hearing"), reverse("audiogram_list")):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), self.INPUT_JS)

    # 檢視頁
    def test_detail_shows_interpretation(self):
        points = _four(_air, "right", (40, 45, 50, 55)) + _four(_bone, "right", (40, 45, 50, 55))
        audiogram = self._make(points)
        response = self.client.get(reverse("audiogram_detail", args=[audiogram.id]))
        self.assertContains(response, "2026/10/01")
        right = self._ear_card(response, "right")
        self.assertIn("47.5", right)
        self.assertIn("中度", right)
        self.assertIn("感音神經性", right)
        self.assertContains(response, "這是依固定規則算出的參考結果，不能取代聽力師的判讀。")
        self.assertNotContains(response, "診斷")
        self.assertContains(response, self.VIEW_JS)

    def test_detail_insufficient_and_missing_bone(self):
        points = [_air("right", f, 40) for f in (500, 1000, 4000)] + _four(_air, "left", (50,) * 4)
        response = self.client.get(reverse("audiogram_detail", args=[self._make(points).id]))
        self.assertIn("資料不足，無法判讀", self._ear_card(response, "right"))
        left = self._ear_card(response, "left")
        self.assertIn("中度", left)
        self.assertIn("需要骨導資料才能判斷", left)

    def test_detail_pta_formats(self):
        points = _four(_air, "right", (100,) * 4) + _four(_air, "left", (50,) * 4)
        points += [_bone("right", f, db) for f, db in ((500, 60), (1000, 70), (2000, 75))]
        points.append(_bone("right", 4000, 80, no_response=True))
        response = self.client.get(reverse("audiogram_detail", args=[self._make(points).id]))
        right = self._ear_card(response, "right")
        self.assertIn("混合性", right)
        self.assertIn("含無反應的頻率，實際聽力可能更差", right)
        left = self._ear_card(response, "left")
        self.assertRegex(left, r"\b50 dB HL")
        self.assertNotIn("50.0", left)
        self.assertNotIn("含無反應", left)

    def test_detail_air_no_response_note(self):
        # Acceptance 25 on the page (second review 3-2).
        points = [_air("right", f, db) for f, db in ((500, 90), (1000, 100), (2000, 110))]
        points.append(_air("right", 4000, 120, no_response=True))
        response = self.client.get(reverse("audiogram_detail", args=[self._make(points).id]))
        right = self._ear_card(response, "right")
        self.assertIn("四頻平均：105 dB HL", right)
        self.assertIn("極重度", right)
        self.assertIn("含無反應的頻率，實際聽力可能更差", right)

    def test_detail_table_lists_points(self):
        points = [
            _air("right", 1000, 0),
            _air("right", 2000, -10),
            _air("left", 4000, 120, no_response=True),
        ]
        response = self.client.get(reverse("audiogram_detail", args=[self._make(points).id]))
        self.assertContains(response, 'id="audiogram-points"')  # json_script for the chart
        main = self._main(response)
        self.assertIn("<table", main)
        # Whole cells: "120 dB" alone would also contain "0 dB" (review 3-1).
        self.assertIn("<td>0 dB</td>", main)
        self.assertIn("<td>-10 dB</td>", main)
        self.assertIn("<td>120 dB（無反應）</td>", main)

    def test_detail_shows_masking(self):
        # Acceptance 40.
        points = [
            {**_air("right", 1000, 50), "masked": True},
            {**_bone("left", 1000, 80, no_response=True), "masked": True},
        ]
        response = self.client.get(reverse("audiogram_detail", args=[self._make(points).id]))
        main = self._main(response)
        self.assertIn("<td>50 dB（遮蔽）</td>", main)
        self.assertIn("<td>80 dB（遮蔽、無反應）</td>", main)
        chart = json.loads(re.search(r'id="audiogram-points"[^>]*>(.*?)</script>', main).group(1))
        self.assertTrue(all(p["masked"] for p in chart))

    def test_only_outer_frequencies_render(self):
        points = [_air(ear, f, 40) for ear in ("right", "left") for f in (250, 8000)]
        response = self.client.get(reverse("audiogram_detail", args=[self._make(points).id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("資料不足，無法判讀", self._ear_card(response, "right"))
        self.assertIn("資料不足，無法判讀", self._ear_card(response, "left"))

    # 清單
    def test_list_newest_test_date_first(self):
        old = self._make(_four(_air, "right", (20,) * 4), tested_on=date(2026, 1, 1))
        new = self._make(_four(_air, "right", (50,) * 4), tested_on=date(2026, 9, 1))
        same_day_later = self._make(_four(_air, "right", (80,) * 4), tested_on=date(2026, 9, 1))
        main = self._main(self.client.get(reverse("audiogram_list")))
        links = re.findall(r'href="/audiograms/(\d+)"', main)
        self.assertEqual(links, [str(same_day_later.id), str(new.id), str(old.id)])
        self.assertIn("2026/09/01", main)
        self.assertIn("右耳：重度", main)
        self.assertIn("左耳：資料不足", main)

    def test_empty_list(self):
        main = self._main(self.client.get(reverse("audiogram_list")))
        self.assertIn("還沒有聽力圖", main)
        self.assertIn(f'href="{reverse("audiogram_new")}"', main)

    def test_list_queries_do_not_grow(self):
        self._make(_four(_air, "right", (40,) * 4))
        self._make(_four(_air, "left", (40,) * 4))
        with CaptureQueriesContext(connection) as two:
            self.client.get(reverse("audiogram_list"))
        for _ in range(18):
            self._make(_four(_air, "right", (40,) * 4) + _four(_bone, "right", (40,) * 4))
        with CaptureQueriesContext(connection) as twenty:
            self.client.get(reverse("audiogram_list"))
        self.assertEqual(len(twenty), len(two))

    # 權限
    def test_other_users_audiogram_is_404(self):
        theirs = self._make(_four(_air, "right", (40,) * 4), user=self.other)
        for name in ("audiogram_detail", "audiogram_delete"):
            with self.subTest(name=name):
                url = reverse(name, args=[theirs.id])
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url).status_code, 404)
        listing = self._main(self.client.get(reverse("audiogram_list")))
        self.assertNotIn(f"/audiograms/{theirs.id}", listing)
        from screening.models import Audiogram

        self.assertTrue(Audiogram.objects.filter(pk=theirs.pk).exists())

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        for url in (reverse("audiogram_list"), reverse("audiogram_new")):
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url),
                    f"{reverse('login')}?next={url}",
                    fetch_redirect_response=False,
                )

    # 刪除
    def test_delete_asks_first_then_deletes_with_points(self):
        from screening.models import Audiogram, AudiogramPoint

        audiogram = self._make(_four(_air, "right", (40,) * 4))
        url = reverse("audiogram_delete", args=[audiogram.id])
        response = self.client.get(url)
        self.assertContains(response, "確定要刪除 2026/10/01 的聽力圖嗎？")
        self.assertTrue(Audiogram.objects.filter(pk=audiogram.pk).exists())
        response = self.client.post(url)
        self.assertRedirects(response, reverse("audiogram_list"))
        self.assertFalse(Audiogram.objects.filter(pk=audiogram.pk).exists())
        self.assertEqual(AudiogramPoint.objects.count(), 0)

    def test_detail_links_to_delete(self):
        audiogram = self._make(_four(_air, "right", (40,) * 4))
        response = self.client.get(reverse("audiogram_detail", args=[audiogram.id]))
        self.assertContains(response, f'href="{reverse("audiogram_delete", args=[audiogram.id])}"')

    # 導覽列：聽力圖是獨立的一項，不在我的紀錄的分頁籤裡
    def test_nav_marks_every_audiogram_page(self):
        audiogram = self._make(_four(_air, "right", (40,) * 4))
        urls = (
            reverse("audiogram_list"),
            reverse("audiogram_new"),
            reverse("audiogram_detail", args=[audiogram.id]),
            reverse("audiogram_delete", args=[audiogram.id]),
        )
        for url in urls:
            with self.subTest(url=url):
                nav = test_pages.RedesignLayoutTests.NAV.search(
                    self.client.get(url).content.decode()
                ).group()
                current = re.findall(r'aria-current="page">.*?<span>([^<]+)</span>', nav, re.DOTALL)
                self.assertEqual(current, ["聽力圖"])

    def test_not_a_my_hearing_tab(self):
        main = self._main(self.client.get(reverse("my_hearing")))
        self.assertNotIn(reverse("audiogram_list"), main)

    def test_bundle_entries_in_vite_config(self):
        config = test_answering.ReactAnswerPageTests.VITE_CONFIG.read_text(encoding="utf-8")
        for entry in ('"audiogram-input"', '"audiogram-view"'):
            with self.subTest(entry=entry):
                self.assertIn(entry, config)


def _masked(point):
    return {**point, "masked": True}


class AudiogramCompareRuleTests(SimpleTestCase):
    """Spec docs/specs/phase5_audiogram_2.md 4.2, acceptance 13-17 (the rules alone)."""

    def _compare(self, new, old):
        from screening.audiogram import compare

        def objects(points):
            return [mock.Mock(**{"masked": False, **p}) for p in points]

        return compare(objects(new), objects(old))

    def _row(self, result, ear, conduction, frequency):
        rows = [r for r in result[ear][conduction] if r["frequency"] == frequency]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_difference_is_new_minus_old(self):
        result = self._compare([_air("right", 1000, 45)], [_air("right", 1000, 30)])
        row = self._row(result, "right", "air", 1000)
        self.assertEqual((row["old"].db, row["new"].db, row["diff"]), (30, 45, 15))
        self.assertIsNone(row["reason"])

    def test_zero_and_minus_ten_are_values(self):
        result = self._compare([_air("right", 1000, -10)], [_air("right", 1000, 0)])
        self.assertEqual(self._row(result, "right", "air", 1000)["diff"], -10)
        result = self._compare([_air("right", 1000, 0)], [_air("right", 1000, 0)])
        row = self._row(result, "right", "air", 1000)
        self.assertEqual(row["diff"], 0)
        self.assertIsNone(row["reason"])

    def test_only_one_side_has_a_value(self):
        result = self._compare([_air("right", 6000, 70)], [])
        row = self._row(result, "right", "air", 6000)
        self.assertIsNone(row["old"])
        self.assertIsNone(row["diff"])
        self.assertEqual(row["reason"], "missing")
        result = self._compare([], [_bone("right", 500, 20)])
        self.assertEqual(self._row(result, "right", "bone", 500)["reason"], "missing")

    def test_no_response_cannot_be_compared(self):
        result = self._compare(
            [_air("right", 8000, 120, no_response=True)], [_air("right", 8000, 60)]
        )
        row = self._row(result, "right", "air", 8000)
        self.assertIsNone(row["diff"])
        self.assertEqual(row["reason"], "no_response")
        # A missing side comes first: there is nothing on the other side to compare against.
        result = self._compare([_air("right", 8000, 120, no_response=True)], [])
        self.assertEqual(self._row(result, "right", "air", 8000)["reason"], "missing")

    def test_only_marked_frequencies_listed_in_order(self):
        result = self._compare(
            [_air("right", 4000, 50), _air("right", 500, 20)], [_air("right", 2000, 30)]
        )
        self.assertEqual([r["frequency"] for r in result["right"]["air"]], [500, 2000, 4000])
        self.assertEqual(result["right"]["bone"], [])
        self.assertEqual(result["left"]["air"], [])

    def test_pta_difference(self):
        result = self._compare(
            _four(_air, "right", (40, 45, 50, 55)), _four(_air, "right", (30,) * 4)
        )
        pta = result["right"]["pta"]
        self.assertEqual((pta["old"], pta["new"], pta["diff"]), (30, 47.5, 17.5))
        self.assertEqual((pta["old_degree"], pta["new_degree"]), ("輕度", "中度"))
        self.assertFalse(pta["no_response"])

    def test_pta_difference_needs_both(self):
        result = self._compare(_four(_air, "right", (40,) * 4), [_air("right", 500, 30)])
        pta = result["right"]["pta"]
        self.assertIsNone(pta["old"])
        self.assertEqual(pta["new"], 40)
        self.assertIsNone(pta["diff"])

    def test_pta_with_no_response_is_noted(self):
        new = [*_four(_air, "right", (90, 100, 110, 120))[:3], _air("right", 4000, 120, True)]
        result = self._compare(new, _four(_air, "right", (80,) * 4))
        pta = result["right"]["pta"]
        self.assertEqual(pta["diff"], 25)
        self.assertTrue(pta["no_response"])
        # Same as the detail page: no response outside the four frequencies is not noted.
        result = self._compare(
            [*_four(_air, "right", (40,) * 4), _air("right", 8000, 120, True)],
            _four(_air, "right", (40,) * 4),
        )
        self.assertFalse(result["right"]["pta"]["no_response"])

    def test_bone_no_response_is_not_noted(self):
        # Review 1(a): the difference uses air only, so bone's no response does not touch it.
        new = [
            *_four(_air, "right", (50,) * 4),
            *_four(_bone, "right", (20, 20, 20, 80))[:3],
            _bone("right", 4000, 80, True),
        ]
        result = self._compare(new, _four(_air, "right", (40,) * 4))
        self.assertEqual(result["right"]["pta"]["diff"], 10)
        self.assertFalse(result["right"]["pta"]["no_response"])

    def test_no_note_without_a_difference(self):
        # Review 1(b): no difference shown ("—"), so nothing to warn about.
        new = [_air("right", f, 120, True) for f in (500, 1000, 2000, 4000)]
        result = self._compare(new, [_air("right", 500, 40)])
        self.assertIsNone(result["right"]["pta"]["diff"])
        self.assertFalse(result["right"]["pta"]["no_response"])


class AudiogramEditApiTests(TestCase):
    """Spec docs/specs/phase5_audiogram_2.md 4.1, acceptance 2-4, 6, 7 (API side)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="audiogram_edit_api")
        cls.other = User.objects.create_user(username="audiogram_edit_other")

    def setUp(self):
        self.client.force_login(self.user)
        self.audiogram = self._make(self.user)

    def _make(self, user):
        from screening.models import Audiogram, AudiogramPoint

        audiogram = Audiogram.objects.create(user=user, tested_on=date(2026, 1, 10))
        points = [_masked(_air("right", 1000, 40)), _air("right", 2000, 120, no_response=True)]
        AudiogramPoint.objects.bulk_create(AudiogramPoint(audiogram=audiogram, **p) for p in points)
        return audiogram

    def _url(self, audiogram=None):
        return f"/api/audiograms/{(audiogram or self.audiogram).id}/"

    def _put(self, body, audiogram=None):
        return self.client.put(
            self._url(audiogram), json.dumps(body), content_type="application/json"
        )

    def _snapshot(self, audiogram=None):
        from screening.models import Audiogram

        fresh = Audiogram.objects.get(pk=(audiogram or self.audiogram).pk)
        fields = ("ear", "conduction", "frequency", "db", "no_response", "masked")
        return fresh.tested_on, sorted(fresh.points.values_list(*fields))

    def test_replaces_points_and_date(self):
        points = [
            _air("right", 500, 40),
            _masked(_air("right", 1000, 60)),
            _air("right", 2000, 50),
            _air("right", 4000, 55),
        ]
        body = {"tested_on": "2026-01-12", "points": points}
        response = self._put(body)
        self.assertEqual(response.status_code, 200)
        tested_on, points = self._snapshot()
        self.assertEqual(tested_on, date(2026, 1, 12))
        self.assertEqual(
            points,
            [
                ("right", "air", 500, 40, False, False),
                ("right", "air", 1000, 60, False, True),
                ("right", "air", 2000, 50, False, False),
                ("right", "air", 4000, 55, False, False),
            ],
        )
        self.assertEqual(response.json()["interpretation"]["right"]["pta"], 51.25)
        self.assertEqual(response.json()["tested_on"], "2026-01-12")

    def test_invalid_leaves_everything_unchanged(self):
        before = self._snapshot()
        future = (timezone.localdate() + timedelta(days=1)).isoformat()
        cases = {
            "future": {"tested_on": future, "points": [_air("right", 500, 40)]},
            "no date": {"points": [_air("right", 500, 40)]},
            "no points": {"tested_on": "2026-01-12", "points": []},
            "bad frequency": {"tested_on": "2026-01-12", "points": [_air("right", 750, 40)]},
            "bad step": {"tested_on": "2026-01-12", "points": [_air("right", 500, 42)]},
            "bone too loud": {"tested_on": "2026-01-12", "points": [_bone("right", 500, 85)]},
            "bone at 3000": {"tested_on": "2026-01-12", "points": [_bone("right", 3000, 40)]},
            "no response not at max": {
                "tested_on": "2026-01-12",
                "points": [_air("right", 500, 100, no_response=True)],
            },
            "duplicate": {
                "tested_on": "2026-01-12",
                "points": [_air("right", 500, 40), _air("right", 500, 50)],
            },
            "masked not boolean": {
                "tested_on": "2026-01-12",
                "points": [{**_air("right", 500, 40), "masked": "yes"}],
            },
        }
        for name, body in cases.items():
            with self.subTest(name):
                self.assertEqual(self._put(body).status_code, 400)
                self.assertEqual(self._snapshot(), before)

    def test_failure_while_saving_rolls_back(self):
        from screening.models import AudiogramPoint

        before = self._snapshot()
        body = {"tested_on": "2026-01-12", "points": [_air("right", 500, 40)]}
        with (
            mock.patch.object(AudiogramPoint.objects, "bulk_create", side_effect=DatabaseError),
            self.assertRaises(DatabaseError),
        ):
            self._put(body)
        self.assertEqual(self._snapshot(), before)

    def test_someone_elses_is_404_and_unchanged(self):
        theirs = self._make(self.other)
        before = self._snapshot(theirs)
        body = {"tested_on": "2026-01-12", "points": [_air("right", 500, 40)]}
        self.assertEqual(self._put(body, theirs).status_code, 404)
        self.assertEqual(self._snapshot(theirs), before)

    def test_putting_twice_gives_the_same_result(self):
        body = {
            "tested_on": "2026-01-12",
            "points": [_air("right", 500, 40), _air("left", 500, 50)],
        }
        self.assertEqual(self._put(body).status_code, 200)
        once = self._snapshot()
        self.assertEqual(self._put(body).status_code, 200)
        self.assertEqual(self._snapshot(), once)
        self.assertEqual(len(once[1]), 2)

    def test_no_partial_update(self):
        response = self.client.patch(
            self._url(), json.dumps({"tested_on": "2026-01-12"}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 405)

    def test_anonymous_cannot_edit(self):
        self.client.logout()
        before = self._snapshot()
        body = {"tested_on": "2026-01-12", "points": [_air("right", 500, 40)]}
        self.assertIn(self._put(body).status_code, (401, 403))
        self.assertEqual(self._snapshot(), before)


class AudiogramEditPageTests(TestCase):
    """Spec docs/specs/phase5_audiogram_2.md 4.1, acceptance 1, 2, 4, 5, 8 (pages)."""

    INPUT_JS = AudiogramPageTests.INPUT_JS

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="audiogram_edit_page")
        cls.other = User.objects.create_user(username="audiogram_edit_page_other")

    def setUp(self):
        self.client.force_login(self.user)

    # Borrow the batch-1 helpers without inheriting (and rerunning) its tests.
    _make = AudiogramPageTests._make
    _main = AudiogramPageTests._main
    _ear_card = AudiogramPageTests._ear_card

    def _initial(self, response):
        match = re.search(
            r'<script id="audiogram-initial" type="application/json">(.*?)</script>',
            response.content.decode(),
            re.DOTALL,
        )
        return json.loads(match.group(1))

    def test_edit_page_prefills(self):
        audiogram = self._make(
            [_masked(_air("right", 1000, 40)), _air("right", 2000, 120, True)],
            tested_on=date(2026, 1, 10),
        )
        response = self.client.get(reverse("audiogram_edit", args=[audiogram.id]))
        self.assertContains(response, "修改聽力圖")
        self.assertContains(response, self.INPUT_JS)
        self.assertContains(response, f'data-audiogram-id="{audiogram.id}"')
        initial = self._initial(response)
        self.assertEqual(initial["tested_on"], "2026-01-10")
        self.assertCountEqual(
            initial["points"],
            [
                {
                    "ear": "right",
                    "conduction": "air",
                    "frequency": 1000,
                    "db": 40,
                    "no_response": False,
                    "masked": True,
                },
                {
                    "ear": "right",
                    "conduction": "air",
                    "frequency": 2000,
                    "db": 120,
                    "no_response": True,
                    "masked": False,
                },
            ],
        )

    def test_new_page_has_no_initial_data(self):
        response = self.client.get(reverse("audiogram_new"))
        self.assertContains(response, "新增聽力圖")
        self.assertNotContains(response, "audiogram-initial")
        self.assertNotContains(response, "data-audiogram-id")

    def test_detail_links_to_edit(self):
        audiogram = self._make(_four(_air, "right", (40,) * 4))
        response = self.client.get(reverse("audiogram_detail", args=[audiogram.id]))
        self.assertContains(response, f'href="{reverse("audiogram_edit", args=[audiogram.id])}"')

    def test_someone_elses_edit_page_is_404(self):
        theirs = self._make(_four(_air, "right", (40,) * 4), user=self.other)
        self.assertEqual(
            self.client.get(reverse("audiogram_edit", args=[theirs.id])).status_code, 404
        )

    def test_anonymous_edit_page_redirects_to_login(self):
        audiogram = self._make(_four(_air, "right", (40,) * 4))
        self.client.logout()
        url = reverse("audiogram_edit", args=[audiogram.id])
        self.assertRedirects(
            self.client.get(url), f"{reverse('login')}?next={url}", fetch_redirect_response=False
        )

    def test_edit_page_marks_nav(self):
        audiogram = self._make(_four(_air, "right", (40,) * 4))
        nav = test_pages.RedesignLayoutTests.NAV.search(
            self.client.get(reverse("audiogram_edit", args=[audiogram.id])).content.decode()
        ).group()
        current = re.findall(r'aria-current="page">.*?<span>([^<]+)</span>', nav, re.DOTALL)
        self.assertEqual(current, ["聽力圖"])

    def test_after_edit_detail_and_list_follow(self):
        first = self._make(_four(_air, "right", (40,) * 4), tested_on=date(2026, 1, 10))
        second = self._make(_four(_air, "right", (40,) * 4), tested_on=date(2026, 5, 1))
        body = {"tested_on": "2026-09-10", "points": _four(_air, "right", (60,) * 4)}
        response = self.client.put(
            f"/api/audiograms/{first.id}/", json.dumps(body), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        detail = self.client.get(reverse("audiogram_detail", args=[first.id]))
        self.assertContains(detail, "2026/09/10")
        self.assertIn("中重度", self._ear_card(detail, "right"))
        listing = self._main(self.client.get(reverse("audiogram_list")))
        self.assertLess(
            listing.index(f'/audiograms/{first.id}"'), listing.index(f'/audiograms/{second.id}"')
        )


class AudiogramComparePageTests(TestCase):
    """Spec docs/specs/phase5_audiogram_2.md 4.2, acceptance 9-22 (page)."""

    @property
    def URL(self):
        return reverse("audiogram_compare")

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="audiogram_compare")
        cls.other = User.objects.create_user(username="audiogram_compare_other")

    def setUp(self):
        self.client.force_login(self.user)

    _make = AudiogramPageTests._make
    _main = AudiogramPageTests._main

    def _three(self):
        return (
            self._make(_four(_air, "right", (30,) * 4), tested_on=date(2026, 1, 10)),
            self._make(_four(_air, "right", (35,) * 4), tested_on=date(2026, 5, 1)),
            self._make(_four(_air, "right", (40,) * 4), tested_on=date(2026, 9, 10)),
        )

    def _get(self, **params):
        return self.client.get(self.URL, params)

    def _row(self, response, section, key):
        main = self._main(response)
        table = re.search(
            rf'<table[^>]*data-section="{section}"[^>]*>(.*?)</table>', main, re.DOTALL
        )
        self.assertIsNotNone(table, section)
        row = re.search(rf'<tr data-row="{key}">(.*?)</tr>', table.group(1), re.DOTALL)
        self.assertIsNotNone(row, key)
        return [
            re.sub(r"<[^>]+>", "", cell).strip()
            for cell in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row.group(1), re.DOTALL)
        ]

    def _chart(self, response, name):
        match = re.search(
            rf'<script id="{name}" type="application/json">(.*?)</script>',
            response.content.decode(),
            re.DOTALL,
        )
        return json.loads(match.group(1))

    def _legend(self, response):
        return re.search(
            r'<p class="[^"]*compare-legend[^"]*">(.*?)</p>', self._main(response), re.DOTALL
        ).group(1)

    # 清單頁的入口
    def test_list_button_needs_two(self):
        self._make(_four(_air, "right", (30,) * 4))
        main = self._main(self.client.get(reverse("audiogram_list")))
        self.assertIn("要有兩張聽力圖才能比較", main)
        self.assertNotIn(f'href="{self.URL}"', main)
        self.assertRegex(main, r"<button[^>]*disabled[^>]*>比較聽力圖</button>")
        self._make(_four(_air, "right", (30,) * 4))
        main = self._main(self.client.get(reverse("audiogram_list")))
        self.assertIn(f'href="{self.URL}"', main)
        self.assertNotIn("要有兩張聽力圖才能比較", main)

    def test_compare_page_with_fewer_than_two(self):
        self._make(_four(_air, "right", (30,) * 4))
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "要有兩張聽力圖才能比較")
        self.assertNotContains(response, 'data-section="pta"')

    # 選哪兩張
    def test_defaults_to_latest_two(self):
        _, middle, latest = self._three()
        response = self._get()
        self.assertEqual(self._legend(response).count("2026/09/10"), 1)
        legend = self._legend(response)
        self.assertLess(legend.index("2026/09/10"), legend.index("2026/05/01"))
        self.assertNotIn("2026/01/10", legend)
        self.assertEqual(self._row(response, "pta", "pta")[1:3], ["35 dB（輕度）", "40 dB（輕度）"])
        main = self._main(response)
        self.assertRegex(main, rf'<option value="{latest.id}" selected>')
        self.assertRegex(main, rf'<option value="{middle.id}" selected>')

    def test_new_and_old_follow_dates_not_selects(self):
        oldest, _, latest = self._three()
        for a, b in ((oldest, latest), (latest, oldest)):
            with self.subTest(a=a.tested_on):
                response = self._get(a=a.id, b=b.id)
                # Header: old date first, then new.
                header = self._row(response, "pta", "head")
                self.assertEqual(header[1:3], ["2026/01/10", "2026/09/10"])
                self.assertEqual(self._row(response, "pta", "pta")[3], "+10")
                self.assertEqual(self._chart(response, "audiogram-points")[0]["db"], 40)
                self.assertEqual(self._chart(response, "audiogram-old-points")[0]["db"], 30)

    def test_same_day_later_saved_is_new(self):
        first = self._make(_four(_air, "right", (30,) * 4), tested_on=date(2026, 5, 1))
        second = self._make(_four(_air, "right", (50,) * 4), tested_on=date(2026, 5, 1))
        response = self._get(a=first.id, b=second.id)
        self.assertEqual(self._row(response, "pta", "pta")[3], "+20")

    def test_same_audiogram_twice(self):
        _, _, latest = self._three()
        response = self._get(a=latest.id, b=latest.id)
        self.assertContains(response, "請選兩張不同的聽力圖")
        self.assertNotContains(response, 'data-section="pta"')
        self.assertNotContains(response, 'id="audiogram-points"')

    # 對照表
    def test_table_values(self):
        old = self._make(
            [
                *_four(_air, "right", (30,) * 4),
                _air("right", 8000, 60),
                _masked(_bone("right", 1000, 20)),
            ],
            tested_on=date(2026, 5, 1),
        )
        new = self._make(
            [
                _air("right", 500, 30),
                _air("right", 1000, 45),
                _air("right", 2000, 50),
                _air("right", 4000, 65),
                _air("right", 6000, 70),
                _air("right", 8000, 120, True),
                _masked(_bone("right", 1000, 25)),
            ],
            tested_on=date(2026, 9, 10),
        )
        response = self._get(a=new.id, b=old.id)
        self.assertEqual(self._row(response, "air", "1000"), ["1000 Hz", "30 dB", "45 dB", "+15"])
        self.assertEqual(self._row(response, "air", "6000"), ["6000 Hz", "", "70 dB", "—"])
        self.assertEqual(
            self._row(response, "air", "8000"), ["8000 Hz", "60 dB", "120 dB（無反應）", "無法比較"]
        )
        self.assertEqual(
            self._row(response, "bone", "1000"), ["1000 Hz", "20 dB（遮蔽）", "25 dB（遮蔽）", "+5"]
        )
        self.assertEqual(
            self._row(response, "pta", "pta"),
            ["四頻平均", "30 dB（輕度）", "47.5 dB（中度）", "+17.5"],
        )
        main = self._main(response)
        self.assertIn("差值＝新 − 舊，正數＝要更大聲才聽得到", main)  # noqa: RUF001
        self.assertIn("兩次檢查的條件（機器、地點、耳機）不同，數字也會有幾 dB 的差異。", main)
        self.assertIn("這只是數字的對照，不能取代聽力師的判讀。", main)

    def test_zero_minus_and_equal(self):
        old = self._make(
            [_air("right", 500, 0), _air("right", 1000, 20)], tested_on=date(2026, 5, 1)
        )
        new = self._make(
            [_air("right", 500, -10), _air("right", 1000, 20)], tested_on=date(2026, 9, 1)
        )
        response = self._get(a=new.id, b=old.id)
        self.assertEqual(self._row(response, "air", "500")[1:], ["0 dB", "-10 dB", "-10"])
        self.assertEqual(self._row(response, "air", "1000")[3], "0")
        self.assertEqual(self._row(response, "pta", "pta")[1:], ["資料不足", "資料不足", "—"])

    def test_pta_no_response_note(self):
        old = self._make(_four(_air, "right", (80,) * 4), tested_on=date(2026, 5, 1))
        new = self._make(
            [*_four(_air, "right", (90, 100, 110, 0))[:3], _air("right", 4000, 120, True)],
            tested_on=date(2026, 9, 1),
        )
        response = self._get(a=new.id, b=old.id)
        self.assertEqual(self._row(response, "pta", "pta")[3], "+25")
        self.assertContains(response, "含無反應的頻率，實際差距可能不同")
        plain = self._get(a=old.id, b=self._make(_four(_air, "right", (70,) * 4)).id)
        self.assertNotContains(plain, "含無反應的頻率，實際差距可能不同")

    def test_no_judgement_words_or_colours(self):
        old = self._make(_four(_air, "right", (20,) * 4), tested_on=date(2026, 1, 1))
        new = self._make(_four(_air, "right", (50,) * 4), tested_on=date(2026, 9, 1))
        main = self._main(self._get(a=new.id, b=old.id))
        for word in ("變差", "進步", "惡化", "改善", "診斷"):
            with self.subTest(word=word):
                self.assertNotIn(word, main)
        tables = "".join(re.findall(r"<table.*?</table>", main, re.DOTALL))
        self.assertNotRegex(tables, r"(text|bg|table)-(danger|success|warning)")
        self.assertNotIn("style=", tables)

    # 左右耳
    def test_ear_switch(self):
        old = self._make(
            [*_four(_air, "right", (30,) * 4), *_four(_air, "left", (60,) * 4)],
            tested_on=date(2026, 1, 1),
        )
        new = self._make(
            [*_four(_air, "right", (40,) * 4), *_four(_air, "left", (65,) * 4)],
            tested_on=date(2026, 9, 1),
        )
        right = self._get(a=new.id, b=old.id)
        self.assertEqual(self._row(right, "pta", "pta")[3], "+10")
        self.assertEqual({p["ear"] for p in self._chart(right, "audiogram-points")}, {"right"})
        main = self._main(right)
        self.assertRegex(main, r'<a[^>]*aria-current="true"[^>]*>右耳</a>')
        left_link = (
            re.search(r'<a[^>]*href="([^"]+)"[^>]*>左耳</a>', main).group(1).replace("&amp;", "&")
        )
        left = self.client.get(self.URL + left_link)
        self.assertEqual(self._row(left, "pta", "pta")[3], "+5")
        self.assertEqual({p["ear"] for p in self._chart(left, "audiogram-points")}, {"left"})
        self.assertEqual({p["ear"] for p in self._chart(left, "audiogram-old-points")}, {"left"})
        self.assertRegex(self._main(left), r'<a[^>]*aria-current="true"[^>]*>左耳</a>')
        # Unknown ear falls back to the right ear.
        self.assertEqual(self._row(self._get(a=new.id, b=old.id, ear="x"), "pta", "pta")[3], "+10")

    def test_bone_in_chart_and_table(self):
        old = self._make(_four(_bone, "right", (20,) * 4), tested_on=date(2026, 1, 1))
        new = self._make(_four(_bone, "right", (30,) * 4), tested_on=date(2026, 9, 1))
        response = self._get(a=new.id, b=old.id)
        self.assertEqual(self._row(response, "bone", "500")[1:], ["20 dB", "30 dB", "+10"])
        self.assertEqual(len(self._chart(response, "audiogram-old-points")), 4)
        legend = self._legend(response)
        self.assertIn("2026/09/01", legend)
        self.assertIn("2026/01/01", legend)
        self.assertContains(response, AudiogramPageTests.VIEW_JS)

    # 權限
    def test_someone_elses_audiogram_is_404(self):
        _, _, latest = self._three()
        theirs = self._make(_four(_air, "right", (30,) * 4), user=self.other)
        for params in ({"a": latest.id, "b": theirs.id}, {"a": theirs.id, "b": latest.id}):
            with self.subTest(params=params):
                self.assertEqual(self._get(**params).status_code, 404)
        main = self._main(self._get())
        self.assertNotIn(f'value="{theirs.id}"', main)

    def test_bad_ids_are_404(self):
        _, _, latest = self._three()
        for params in ({"a": latest.id, "b": 999999}, {"a": "x", "b": latest.id}, {"a": latest.id}):
            with self.subTest(params=params):
                self.assertEqual(self._get(**params).status_code, 404)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        self.assertRedirects(
            self.client.get(self.URL),
            f"{reverse('login')}?next={self.URL}",
            fetch_redirect_response=False,
        )

    def test_nav_marks_compare_page(self):
        nav = test_pages.RedesignLayoutTests.NAV.search(self._get().content.decode()).group()
        current = re.findall(r'aria-current="page">.*?<span>([^<]+)</span>', nav, re.DOTALL)
        self.assertEqual(current, ["聽力圖"])

    def test_query_count_does_not_grow(self):
        def queries():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self._get().status_code, 200)
            return len(ctx)

        from screening.models import Audiogram

        for _ in range(2):
            self._make([_air("right", 500, 30)])
        few = queries()
        Audiogram.objects.all().delete()
        for _ in range(20):
            self._make([*_four(_air, "right", (30,) * 4), *_four(_bone, "left", (20,) * 4)])
        self.assertEqual(queries(), few)

    def test_header_dates_can_wrap_on_narrow_screens(self):
        # Spec phase6_a11y_remeasure.md acceptance 7: at 320 px the table must fit without
        # page scrolling, so each date header may break after the year.
        first, _, last = self._three()
        main = self._main(self._get(a=first.id, b=last.id))
        headers = re.findall(r'<tr data-row="head">(.*?)</tr>', main, re.DOTALL)
        self.assertTrue(headers)
        for header in headers:
            with self.subTest(header=header):
                self.assertIn('<th scope="col">2026/<wbr>01/10</th>', header)
                self.assertIn('<th scope="col">2026/<wbr>09/10</th>', header)
