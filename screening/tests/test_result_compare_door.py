"""A result page's 戴上助聽器，差多少？ (the owner's 2026-11-27 walkthrough, the mockup's B)."""

import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from screening.models import Answer, Questionnaire, Submission
from screening.tests.helpers import consented_user

DOOR = re.compile(
    r'<a class="link-card action-card result-compare-door" href="([^"]*)">(.*?)</a>', re.S
)


class ResultCompareDoorTests(TestCase):
    def setUp(self):
        call_command("seed_questionnaires", stdout=StringIO())
        self.questionnaire = Questionnaire.objects.get(code="hhia-s")
        self.user = consented_user(username="door_user")
        self.client.force_login(self.user)

    def record(self, wearing, score):
        # HHIA-S takes 0, 2 or 4 an item; any other is not a complete record.
        record = Submission.objects.create(
            user=self.user, questionnaire=self.questionnaire, wearing_hearing_aid=wearing
        )
        Answer.objects.bulk_create(
            Answer(submission=record, question=q, score=score)
            for q in self.questionnaire.questions.all()
        )
        return record

    def door(self, record):
        page = self.client.get(f"/submission/{record.pk}").content.decode()
        found = DOOR.search(page)
        return page, found

    def test_with_both_kinds_the_block_pairs_this_record_with_the_newest_other(self):
        self.record(False, 4)  # 40 分, older
        newest_unaided = self.record(False, 2)  # 20 分
        aided = self.record(True, 0)  # 0 分
        page, found = self.door(aided)
        self.assertIsNotNone(found)
        href, body = found.groups()
        self.assertIn("戴上助聽器，差多少？", body)
        text = re.sub(r"<[^>]+>", "", body)
        self.assertIn("沒戴 20 分", text)
        self.assertIn("有戴 0 分", text)
        self.assertEqual(
            href,
            f"/comparisons/{self.questionnaire.pk}"
            f"?unaided={newest_unaided.pk}&amp;aided={aided.pk}&amp;action=preview",
        )
        # It sits over the 建議下一步 card, and the row it replaces is not in the list too.
        self.assertLess(found.start(), page.index("建議您下一步"))
        self.assertNotIn('<span class="link-card-title">比較戴與不戴助聽器</span>', page)

    def test_an_unaided_record_pairs_with_the_newest_aided(self):
        unaided = self.record(False, 4)
        self.record(True, 0)
        newest_aided = self.record(True, 2)
        _, found = self.door(unaided)
        self.assertIn(f"?unaided={unaided.pk}&amp;aided={newest_aided.pk}", found.group(1))

    def test_without_the_other_kind_there_is_no_block_or_row(self):
        page, found = self.door(self.record(False, 4))
        self.assertIsNone(found)
        self.assertNotIn("比較戴與不戴助聽器", page)

    def test_the_page_it_opens_shows_that_pair(self):
        unaided = self.record(False, 4)
        aided = self.record(True, 2)
        _, found = self.door(aided)
        page = self.client.get(found.group(1).replace("&amp;", "&"))
        preview = page.context["preview"]
        self.assertEqual((preview.unaided_id, preview.aided_id), (unaided.pk, aided.pk))
