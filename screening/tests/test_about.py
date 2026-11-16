import re

from django.test import TestCase
from django.urls import reverse

from screening.models import User
from screening.tests import test_layout


def main_of(response):
    page = response.content.decode()
    return page[page.index("<main") : page.index("</main>")]


class AboutPageTests(TestCase):
    """Spec #633 (#640, acceptance 1, 2, 4, the #634 mockup's A): 關於聽伴 in four parts laid
    out in turn, open to everyone."""

    def test_four_parts_under_their_titles_without_logging_in(self):
        response = self.client.get(reverse("about"))
        self.assertEqual(response.status_code, 200)
        headings = re.findall(r"<h(\d)[^>]*>(.*?)</h\d>", main_of(response), re.S)
        self.assertEqual(
            [(level, test_layout._text(words)) for level, words in headings if level in "12"],
            [
                ("1", "關於聽伴"),
                ("2", "誰做的"),
                ("2", "內容怎麼查核"),
                ("2", "資料怎麼處理"),
                ("2", "不能取代檢查"),
            ],
        )

    def test_the_data_part_is_the_privacy_notices_highlights_and_leads_there(self):
        about = main_of(self.client.get(reverse("about")))
        privacy = main_of(self.client.get(reverse("privacy")))
        highlights = re.compile(
            r"<h3 class=\"tint-subhead\">用來做什麼</h3>.*?</ul>\s*</div>", re.S
        )
        self.assertEqual(highlights.search(about).group(0), highlights.search(privacy).group(0))
        self.assertIn(f'href="{reverse("privacy")}"', about)
        self.assertLess(about.index("用來做什麼"), about.index(f'href="{reverse("privacy")}"'))

    def test_it_says_when_it_was_checked(self):
        self.assertRegex(
            test_layout._text(main_of(self.client.get(reverse("about")))),
            r"本頁資料查核於 \d{4}/\d{2}/\d{2}",
        )

    def test_one_who_has_not_agreed_to_the_new_version_can_still_read_it(self):
        self.client.force_login(User.objects.create_user("about_new_version", password="x"))
        self.assertEqual(self.client.get(reverse("about")).status_code, 200)

    def test_feedback_from_it_names_it(self):
        response = self.client.get(reverse("feedback"), {"page": "about"})
        self.assertContains(response, "您是從「關於聽伴」過來的。")


# Spec #633 (#642): the owner's three parts from #635.
PARTS = {
    "誰做的": (
        "聽伴由一位台灣的執業聽力師設計與審定。在門診常聽到家屬問同樣的問題，"
        "所以做了這個網站，讓長輩和家人在家也能先了解聽力。"
    ),
    "內容怎麼查核": (
        "衛教內容和問答小助手的答案，都由執業聽力師審定，並附上出處。"
        "法規、補助金額這類會變動的資料，每年對照官方公告重新查核一次，"
        "頁面最下面寫著上次查核的日期。"
    ),
    "不能取代檢查": (
        "聽伴的篩檢結果只是參考，不能取代醫師或聽力師的檢查和診斷。"
        "覺得聽力有問題，請找耳鼻喉科或聽力師。"
    ),
}


class AboutWordsTests(TestCase):
    """Spec #633 (#642, acceptance 3, 48): the owner's three parts from #635, under their titles."""

    def test_each_part_says_the_owners_words(self):
        main = main_of(self.client.get(reverse("about")))
        for title, words in PARTS.items():
            with self.subTest(title=title):
                start = main.index(f">{title}</h2>")
                end = main.find("<h2", start)
                self.assertIn(f"<p>{words}</p>", main[start : end if end > 0 else None])

    def test_no_name_or_workplace(self):
        part = main_of(self.client.get(reverse("about")))
        # Only the title and the owner's words: no name or workplace slipped in around them.
        start = part.index(">誰做的</h2>") + 1
        who = part[start : part.index("<h2", start)]
        self.assertEqual(test_layout._text(who), f"誰做的 {PARTS['誰做的']}")
