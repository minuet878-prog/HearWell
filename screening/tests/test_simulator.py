"""#487 (spec #484, the #485 mockup E1 + V1): the hearing loss simulator, open to anyone from 了解
and the family zone, its typical degrees and sentences handed to the player as data."""

import json
import re

from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse

from screening.audiogram import degree, pta
from screening.tests import test_family_zone, test_pages

TITLE = "聽損模擬"
# The words the owner approved for #485 (phase-3-grill-decisions.md).
SENTENCES = [
    ("星期四下午三點去看醫生。", "女"),
    ("這個藥飯後吃，一天三次。", "男"),
    ("孫子說下禮拜六要回來吃飯。", "女"),
    ("謝謝你送的水果，很新鮮。", "男"),
]
LEVELS = [
    ("高頻下降", "尖細的聲音大多聽不到", [15, 20, 25, 45, 65, 75]),
    ("輕度", "小聲就漏聽", [25, 30, 30, 35, 40, 40]),
    ("中度", "常聽不完整", [40, 45, 50, 55, 60, 65]),
    ("中重度", "不大聲聽不到", [55, 60, 65, 70, 75, 80]),
]
LIMITS = (
    "這是典型的程度，不是誰真正的聽力。"
    "模擬只把聲音變小聲；真正的聽損還會讓聲音糊在一起，實際可能更吃力。"
)
NO_SOUND = "聽不到聲音？先關掉手機的靜音、把音量調大；戴耳機聽最清楚。"
HIGH_NOTE = (
    "選的是高頻下降：檢查報告上的平均可能只寫「輕度」，可是尖細的聲音大多聽不到，"
    "所以最常「聽得到、聽不清楚」。"
)


def _main(content):
    return content[content.index("<main") : content.index("</main>")]


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))


class SimulatorPageTests(test_family_zone.SignsInWithARecord, TestCase):
    def setUp(self):
        self.url = reverse("hearing_loss_simulator")

    def _page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _data(self, content):
        found = re.search(
            r'<script id="simulator-data" type="application/json">(.*?)</script>', content, re.S
        )
        self.assertIsNotNone(found)
        return json.loads(found.group(1))

    def test_its_address_is_under_learn(self):
        self.assertEqual(self.url, "/learn/simulator")

    def test_anyone_opens_it_and_it_marks_the_learn_tab(self):
        # #484 acceptance 1 and 3: no login asked, and signed in with a graded record it is the
        # same page, none of the record on it.
        anonymous = self._page()
        self.sign_in_with_a_record("simulator_reader")
        signed_in = self._page()
        self.assertEqual(_main(anonymous), _main(signed_in))
        # The player's data is the same as a visitor's (above); leave its escaped characters,
        # whose hex digits can spell the record's 16, out of the look for the record.
        words = re.sub(r'<script id="simulator-data".*?</script>', "", signed_in, flags=re.S)
        self.assert_shows_no_record(words, "simulator_reader")
        self.assertRegex(signed_in, rf"<title>\s*{TITLE}｜聽伴\s*</title>")  # noqa: RUF001
        nav = test_pages.RedesignLayoutTests.NAV.search(signed_in).group()
        self.assertEqual(
            re.findall(r'aria-current="page"[^>]*>.*?<span>([^<]+)</span>', nav, re.S),
            ["了解"],
        )

    def test_one_heading_and_the_player_gets_degrees_and_sentences(self):
        content = self._page()
        main = _main(content)
        self.assertEqual(re.findall(r"<h1[^>]*>([^<]*)</h1>", main), [TITLE])
        self.assertIn('<div id="simulator"', main)
        data = self._data(content)
        self.assertEqual(
            [(level["name"], level["line"], level["thresholds"]) for level in data["levels"]],
            LEVELS,
        )
        self.assertEqual(data["frequencies"], [250, 500, 1000, 2000, 4000, 8000])
        # #484 acceptance 4: 高頻下降 is the first and the one picked on opening.
        self.assertEqual(data["levels"][0]["name"], "高頻下降")
        self.assertEqual(
            [(sentence["text"], sentence["voice"]) for sentence in data["sentences"]], SENTENCES
        )
        self.assertEqual(
            [sentence["audio"] for sentence in data["sentences"]],
            [static(f"screening/simulator/sentence-{n}.m4a") for n in range(1, 5)],
        )
        self.assertEqual(data["limits"], [LIMITS, NO_SOUND])
        self.assertEqual(data["levels"][0]["note"], HIGH_NOTE)
        self.assertTrue(all("note" not in level for level in data["levels"][1:]))

    def test_without_javascript_the_words_are_there_and_it_says_why_nothing_plays(self):
        # #484 acceptance 22.
        main = _main(self._page())
        noscript = re.search(r"<noscript>(.*?)</noscript>", main, re.S)
        self.assertIsNotNone(noscript)
        words = _text(noscript.group(1))
        self.assertIn("需要開啟 JavaScript 才能播放。", words)
        for text, _ in SENTENCES:
            with self.subTest(sentence=text):
                self.assertIn(text, words)
        self.assertIn(LIMITS, words)
        self.assertIn(NO_SOUND, words)

    def test_next_steps_lead_to_talking_and_the_guide_then_back_to_learn(self):
        # #484 acceptance 16.
        main = _main(self._page())
        rows = test_family_zone.ENTRY.findall(main)
        self.assertEqual(
            [(href, title) for href, _, title, _ in rows],
            [(reverse("family_talk"), "怎麼跟他說話"), (reverse("guide"), "了解助聽器選配與補助")],
        )
        self.assertIn(f'<a href="{reverse("learn")}">回到了解</a>', main)


class SimulatorDegreeTests(TestCase):
    """#484 acceptance 17: each typical degree's four-frequency average falls in the site's own
    degree, the way an entered audiogram is judged."""

    def test_averages_fall_in_their_degrees(self):
        data = json.loads(
            re.search(
                r'<script id="simulator-data" type="application/json">(.*?)</script>',
                self.client.get(reverse("hearing_loss_simulator")).content.decode(),
                re.S,
            ).group(1)
        )
        frequencies = data["frequencies"]
        judged = {
            level["name"]: degree(pta(dict(zip(frequencies, level["thresholds"], strict=True))))
            for level in data["levels"]
        }
        # 高頻下降 averages 38.75, so the site calls it 輕度: the point the page makes.
        self.assertEqual(
            judged, {"高頻下降": "輕度", "輕度": "輕度", "中度": "中度", "中重度": "中重度"}
        )
        high = dict(zip(frequencies, data["levels"][0]["thresholds"], strict=True))
        self.assertTrue(all(high[f] <= 25 for f in (250, 500, 1000)))
        self.assertTrue(all(high[f] >= 60 for f in (4000, 8000)))


class SimulatorEntryTests(TestCase):
    """#484 acceptance 1 and 2: a row on 了解 and the first row of the family zone."""

    def test_learn_lists_it_after_the_family_zone(self):
        main = _main(self.client.get(reverse("learn")).content.decode())
        rows = [(href, title) for href, _, title, _ in test_family_zone.ENTRY.findall(main)]
        self.assertEqual(
            rows[1:3],
            [
                (reverse("family_guide"), "家人專區：溝通與陪伴"),
                (reverse("hearing_loss_simulator"), "聽損模擬：聽聽看他聽到的聲音"),
            ],
        )

    def test_family_zone_opens_with_it(self):
        content = self.client.get(reverse("family_guide")).content.decode()
        start = content.index('aria-label="專區內容"')
        entries = content[start : content.index("</nav>", start)]
        self.assertEqual(
            test_family_zone.ENTRY.findall(entries)[0],
            (
                reverse("hearing_loss_simulator"),
                "sound",
                "先聽聽看他聽到的聲音",
                "選程度，聽同一句話怎麼變",
            ),
        )
