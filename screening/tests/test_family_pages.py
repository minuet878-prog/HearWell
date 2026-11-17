import re
from html import unescape

from django.test import TestCase

from screening.qa_assistant import content as qa_content
from screening.tests.test_send_to_him import ADDRESS, LEAD, MESSAGE, block

# The owner's words (#671, docs/planning/found-by-family/family-pages-skeleton.md).
SOURCE = (
    "Communication Health Support Association（美國聽語學會 ASHA 支持）"
    "〈Worried About Hearing Loss? Take the Self-Test〉",
    "https://helpingyoucommunicate.org/article/worried-about-hearing-loss-take-the-self-test",
)
CHECKED = "內容查核於 2026/11/17。"
CLOSING = "這些是一般性的建議，不能取代醫師或聽力師的診斷。有任何疑問，請和您的醫師或聽力師討論。"

SIGNS = {
    "path": "/family/signs",
    "title": "怎麼知道爸媽的聽力變差了",
    "intro": "聽力通常是慢慢變差的，長輩自己常常沒發現，反而是家人先注意到。"
    "下面是日常生活裡常見的情況，可以對照看看。",
    "tip": "若有以下狀況的話，請儘早就醫進行聽力檢查確認",
    "sections": [
        (
            "看電視與聽收音機",
            [
                "電視機的聲音需要開得很大聲才聽得清楚，有時甚至影響到家人",
                "在沒有字幕的狀況下容易無法理解電視內容",
            ],
        ),
        (
            "講電話",
            [
                "講電話都要開很大聲或是擴音",
                "由於手機是經過數位轉化的聲音，聽損會讓這樣的聲音更加聽不清楚",
            ],
        ),
        (
            "吃飯聊天與聚會",
            [
                "聊天時常會有發呆加入不了的狀況(因為聽不清楚話題)",
                "吃飯聚會是一個充滿噪音的場合，有聽損的長輩容易被噪音影響",
            ],
        ),
        (
            "在家裡（門鈴、電話鈴、叫名字）",
            [
                "門鈴、電話響了常常沒聽到，要家人提醒才知道",
                "從另一個房間或從背後叫他，常常沒有反應（看不到說話的人，只能靠耳朵）",
                "微波爐、熱水壺、洗衣機「嗶嗶」的提示聲常常沒注意到（這類高音的聲音通常最先聽不到）",
                "家人說話時，要看著對方的臉才比較聽得懂（無意中在看嘴型幫忙）",
            ],
        ),
    ],
}
LOUD_TV = {
    "path": "/family/loud-tv",
    "title": "爸媽看電視開很大聲，怎麼辦？",
    "intro": "長輩把電視開很大聲，常常不是愛吵，而是開小聲聽不清楚。先了解為什麼，再一起想辦法。",
    "tip": "這些方法只能讓看電視輕鬆一點，不能改善聽力；"
    "如果開了字幕、坐近了還是常聽不清楚，請儘早就醫進行聽力檢查確認。",
    "sections": [
        (
            "開大聲還是聽不清楚？",
            [
                "開大聲只能讓聲音變大，不一定變清楚；所以常常開得很大聲，還是聽不懂在說什麼。",
                "電視節目常有背景音樂和音效，蓋過說話的聲音，聽損的人更難分辨。",
                "聽力是慢慢變差的，自己不容易察覺，會覺得是電視的聲音太小。",
            ],
        ),
        (
            "在家可以先試試",
            [
                "開字幕：大部分電視和網路影音都可以開中文字幕，邊看邊讀比較不吃力。",
                "坐近一點、面向電視，並把冷氣、電扇、抽油煙機等其他聲音關小。",
            ],
        ),
    ],
}
HUH = {
    "path": "/family/huh",
    "title": "跟他講話，他一直說「蛤」？",
    "intro": "長輩一直說「蛤」，很多時候是聽到聲音、卻聽不清楚在說什麼。"
    "這頁說明可能的原因，也帶您聽聽看他聽到的聲音。",
    "tip": "一直「蛤」不一定是聽力退化，耳垢太多、感冒耳朵悶住也可能；"
    "常常這樣的話，請儘早就醫進行聽力檢查確認。",
    "sections": [
        (
            "為什麼聽得到、聽不清楚？",
            [
                "說話裡的子音（像「ㄙ、ㄘ、ㄈ、ㄒ」）多半是高音，聽不到就像字少了一半："
                "知道有人在說話，卻拼不出意思。",
                "電視、炒菜、好幾個人同時說話，聲音混在一起，聽損的人很難挑出要聽的那一句。",
                "從背後、隔一個房間或戴口罩說話，少了嘴型和表情幫忙，就更容易聽錯。",
            ],
        ),
    ],
}


def text(html):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def main_of(content):
    return content[content.index("<main") : content.index("</main>")]


class FamilyPageChecks:
    """Spec #655 acceptance 1–7 (#675): the three family pages, open to anyone, in the owner's
    words, each with the Q&A assistant's urgent box, its source and the day it was checked. A
    mixin, run by each page's TestCase below."""

    page = None

    def setUp(self):
        response = self.client.get(self.page["path"])
        self.assertEqual(response.status_code, 200)
        self.main = main_of(response.content.decode())

    def test_title_intro_and_tip_in_the_owners_words(self):
        headings = re.findall(r"<h1[^>]*>(.*?)</h1>", self.main, re.S)
        self.assertEqual([text(h) for h in headings], [self.page["title"]])
        self.assertIn(f"<p>{self.page['intro']}</p>", self.main)
        tip = re.search(r'<p class="tip-box">(.*?)</p>', self.main, re.S)
        self.assertEqual(text(tip.group(1)), self.page["tip"])

    def test_each_part_has_a_heading_and_the_owners_items_as_a_list(self):
        parts = re.findall(
            r'<section class="family-part"[^>]*>\s*<h2[^>]*>(.*?)</h2>\s*<ul[^>]*>(.*?)</ul>',
            self.main,
            re.S,
        )
        self.assertEqual(
            [
                (text(h), [text(li) for li in re.findall(r"<li>(.*?)</li>", ul, re.S)])
                for h, ul in parts
            ],
            self.page["sections"],
        )
        # Grill Q1: a list to read, nothing to tick or score.
        self.assertNotIn('type="checkbox"', self.main)

    def test_the_urgent_box_is_the_qa_assistants(self):
        urgent = re.search(r'<a class="[^"]*family-urgent-link[^"]*" href="([^"]+)"', self.main)
        self.assertEqual(urgent.group(1), f"/qa/{qa_content.URGENT_CODE}")
        self.assertIn("突然聽不到、耳朵流血？請盡快就醫", self.main)

    def test_the_closing_words_the_way_back_the_source_and_the_check_date(self):
        self.assertIn(CLOSING, text(self.main))
        self.assertRegex(
            self.main,
            r'<a class="btn btn-outline-primary btn-lg w-full" href="/family">回到家人專區</a>',
        )
        self.assertIn(f'<li><a href="{SOURCE[1]}">{SOURCE[0]}</a></li>', self.main)
        self.assertIn(CHECKED, self.main)

    def test_the_share_button_says_send_to_him_in_its_pages_style(self):
        # Acceptance 3, 4 and 17: the button itself, its words and its kind.
        found = re.findall(
            r'<button id="share-button" type="button" class="([^"]+)"[^>]*>(.*?)</button>',
            self.main,
            re.S,
        )
        self.assertEqual(len(found), 1)
        classes, label = found[0]
        self.assertEqual(text(label), "傳給他做篩檢")
        self.assertIn(self.style, classes.split())

    def test_a_public_page_in_the_sitemap_with_its_line_preview(self):
        # Acceptance 5, at the page: listed in the sitemap, no noindex, the confirmed title in
        # the LINE preview (the shared checks in test_sitemap and test_line_preview cover it too).
        response = self.client.get(self.page["path"])
        self.assertNotIn("X-Robots-Tag", response)
        self.assertRegex(response.content.decode(), r'<meta property="og:title" content="[^"]+">')
        self.assertIn(
            f"https://testserver{self.page['path']}",
            self.client.get("/sitemap.xml").content.decode(),
        )

    def test_send_to_him_with_the_owners_message_and_the_wizards_address(self):
        send = block(self.main)
        self.assertIsNotNone(send)
        self.assertIn(f"會傳出這段話 {MESSAGE} {ADDRESS}", text(send))
        self.assertIn(LEAD, text(send))
        # Acceptance 18: every page sends the same one text, shared or copied.
        for button in ("share-button", "copy-link"):
            with self.subTest(button=button):
                found = re.search(rf'<button id="{button}"([^>]*)>', send)
                self.assertIn(f'data-text="{MESSAGE}\n{ADDRESS}"', unescape(found.group(1)))

    def test_the_parts_come_in_order(self):
        order = [
            self.main.index("<h1"),
            self.main.index('class="family-part"'),
            self.main.index("family-urgent-link"),
            self.main.index('<section class="send-to-him"'),
            self.main.index(CLOSING),
            self.main.index("family-sources"),
        ]
        self.assertEqual(order, sorted(order))


class SignsPageTests(FamilyPageChecks, TestCase):
    page = SIGNS
    style = "btn-primary"

    def test_no_score_and_no_verdict(self):
        # Acceptance 2 (ADR 0017): it lists what to watch for and judges nobody.
        for word in ("分數", "level-badge", "可能有聽損", "有聽損嗎", "您的家人"):
            with self.subTest(word=word):
                self.assertNotIn(word, self.main)

    def test_the_tip_comes_before_the_first_group(self):
        # The owner's 若有以下狀況 speaks of what follows (2026-11-17).
        self.assertLess(self.main.index("tip-box"), self.main.index('class="family-part"'))

    def test_the_one_solid_button_is_send_to_him(self):
        send = block(self.main)
        outside = self.main.replace(send, "")
        self.assertNotIn("btn-primary", outside)
        self.assertRegex(send, r"<h2[^>]*>先在家做個簡單的篩檢</h2>")
        self.assertIn("btn-primary", send)


class LoudTvPageTests(FamilyPageChecks, TestCase):
    page = LOUD_TV
    style = "btn-primary"

    def test_the_tip_comes_after_the_parts(self):
        self.assertGreater(self.main.index("tip-box"), self.main.rindex('class="family-part"'))

    def test_the_one_solid_button_is_send_to_him(self):
        send = block(self.main)
        self.assertNotIn("btn-primary", self.main.replace(send, ""))
        self.assertRegex(send, r"<h2[^>]*>先在家做個簡單的篩檢</h2>")
        self.assertIn("btn-primary", send)


class HuhPageTests(FamilyPageChecks, TestCase):
    page = HUH
    style = "btn-outline-primary"

    def test_the_tip_comes_after_the_reasons(self):
        self.assertGreater(self.main.index("tip-box"), self.main.index('class="family-part"'))

    def test_it_leads_to_the_simulator_then_how_to_talk_before_send_to_him(self):
        # Grill Q6 and the #669 mockup's 3-3 A: the two rows first, 傳給他 in outline after.
        listen = self.main.index("<h2")  # the reasons' heading comes first
        rows = re.search(
            r"<h2[^>]*>聽聽他聽到的聲音</h2>\s*<p>(.*?)</p>\s*<ul[^>]*>(.*?)</ul>", self.main, re.S
        )
        self.assertIsNotNone(rows)
        self.assertGreater(rows.start(), listen)
        self.assertEqual(
            text(rows.group(1)),
            "戴上耳機，聽聽看聽損的人聽到的家常話。您會比較知道，為什麼大聲重講不一定有用。",
        )
        links = re.findall(r'<a class="link-card action-card" href="([^"]+)">', rows.group(2))
        self.assertEqual(links, ["/learn/simulator", "/family/talk"])
        self.assertLess(rows.end(), self.main.index('<section class="send-to-him"'))

    def test_send_to_him_is_the_outline_kind_under_its_own_heading(self):
        send = block(self.main)
        self.assertRegex(send, r"<h2[^>]*>也可以先在家做個簡單的篩檢</h2>")
        self.assertNotIn("btn-primary", self.main)
        self.assertIn("btn-outline-primary", send)


class FamilyZoneHomeGroupsTests(TestCase):
    """Acceptance 8 and 9: the zone's home in two groups with the owner's subheadings, the three
    pages on top; its 傳給家人, urgent box and sources as they were, and no 傳給他."""

    def test_two_groups_with_their_rows_in_order(self):
        main = main_of(self.client.get("/family").content.decode())
        groups = re.findall(
            r'<h2 class="[^"]*">([^<]+)</h2>\s*<ul class="list-unstyled family-entries">(.*?)</ul>',
            main,
            re.S,
        )
        rows = [
            (
                heading,
                [
                    (href, text(title), text(note))
                    for href, title, note in re.findall(
                        r'<a class="link-card action-card" href="([^"]+)">.*?'
                        r'<span class="link-card-title">(.*?)</span>\s*<span>(.*?)</span>',
                        entries,
                        re.S,
                    )
                ],
            )
            for heading, entries in groups
        ]
        self.assertEqual(
            rows,
            [
                (
                    "先看看是不是聽力的問題",
                    [
                        (
                            "/family/signs",
                            "怎麼知道爸媽的聽力變差了",
                            "看電視、講電話、吃飯聊天時的情況",
                        ),
                        ("/family/loud-tv", "爸媽看電視開很大聲", "為什麼會這樣、在家可以先試試"),
                        ("/family/huh", "他一直說「蛤」", "為什麼聽得到、聽不清楚"),
                    ],
                ),
                (
                    "確定聽力不好之後",
                    [
                        ("/learn/simulator", "先聽聽看他聽到的聲音", "選程度，聽同一句話怎麼變"),
                        ("/family/talk", "怎麼跟他說話", "情境題與溝通重點"),
                        (
                            "/family/visits",
                            "陪診與代辦",
                            "要帶什麼、想問什麼、補助還缺什麼、期限到哪天",
                        ),
                        ("/family/reluctant", "長輩不肯去怎麼說", "不想檢查、不想戴時可以試的說法"),
                        ("/family/hearing-aids", "助聽器", "怪怪的怎麼辦、怎麼陪他適應、日常保養"),
                    ],
                ),
            ],
        )
