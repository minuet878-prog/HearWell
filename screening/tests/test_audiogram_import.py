"""從 iPhone 匯入 an Apple hearing test PDF (spec #702, ticket #707): the readable path, on
made-up PDFs drawn like the real one (apple_pdf.py)."""

import json
import re
from datetime import date, datetime
from io import StringIO

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from screening.apple_hearing_test import MAX_BYTES
from screening.models import Audiogram
from screening.tests import test_layout
from screening.tests.apple_pdf import FREQUENCIES, LEFT, RIGHT, apple_pdf
from screening.tests.helpers import consented_user

WHO = "要存進「王大明」的紀錄"
PDF_NAME = "PDF 上印的是 iPhone 主人的名字，不一定是做測試的人。"
CHECK = "請跟 PDF 對一下，數字都一樣再按「存下來」。"


def _upload(data=None, name="聽力測試.pdf"):
    return SimpleUploadedFile(name, apple_pdf() if data is None else data, "application/pdf")


class AudiogramImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="王大明")

    def setUp(self):
        self.client.force_login(self.user)

    def _main(self, response):
        content = response.content.decode()
        return content[content.index("<main") : content.index("</main>")]

    def _preview(self, data=None):
        return self.client.post(reverse("audiogram_import"), {"pdf": _upload(data)})

    def _reading(self, preview):
        return re.search(r'name="reading" value="([^"]+)"', preview.content.decode())[1]

    def test_the_page_has_the_steps_and_a_pdf_picker(self):
        """#703 mockup 2A: numbered steps first, then the file at the bottom."""
        main = self._main(self.client.get(reverse("audiogram_import")))
        self.assertIn("<h1", main)
        self.assertIn("從 iPhone 匯入", main)
        steps = re.findall(r'<span class="step-list-body">(.*?)</span>', main, re.S)
        self.assertEqual(
            [test_layout._text(step) for step in steps],
            [
                "打開「健康」app，點下面的「瀏覽」",
                "點「聽力」",
                "點「聽力測試結果」，選要匯入的那一次",
                "往下滑，點「輸出 PDF」",
                "點分享，選「儲存到檔案」",
                "回到這裡，選剛剛存的 PDF",
            ],
        )
        self.assertIn('enctype="multipart/form-data"', main)
        self.assertRegex(
            main, r'<input type="file" name="pdf" accept="application/pdf"[^>]*required'
        )
        self.assertLess(main.rindex("step-list-body"), main.index('type="file"'))

    def test_reading_shows_what_was_read_and_saves_nothing(self):
        """Spec #702 acceptance 1, 4 (#703 mockup 3A): who it goes to, the check, the test's
        date, the chart and both ears' eight values; nothing saved yet."""
        main = self._main(self._preview())
        order = [main.index(words) for words in (WHO, PDF_NAME, CHECK, "測試日期：2026/11/10")]
        self.assertEqual(order, sorted(order))
        self.assertIn('id="audiogram-chart"', main)
        points = json.loads(
            re.search(
                r'<script id="audiogram-points" type="application/json">(.*?)</script>', main, re.S
            )[1]
        )
        self.assertEqual(len(points), 16)
        rows = re.findall(r'<th scope="row">(\d+) Hz</th><td>(-?\d+)</td><td>(-?\d+)</td>', main)
        self.assertEqual(
            rows,
            [tuple(map(str, row)) for row in zip(FREQUENCIES, RIGHT, LEFT, strict=True)],
        )
        self.assertIn("存下來", main)
        self.assertEqual(Audiogram.objects.count(), 0)

    def test_saving_keeps_what_was_read(self):
        """Spec #702 acceptance 2, 3: a self test from Apple's PDF, its values as read (not
        multiples of 5, below -10 too), then its own page."""
        right = (3, -2, 1, -6, -4, 2, -14, -8)
        left = (6, 4, 0, -3, -1, 5, -11, -20)
        preview = self._preview(
            apple_pdf(right=right, left=left, tested_at=datetime(2026, 1, 5, 9))
        )
        response = self.client.post(
            reverse("audiogram_import_save"), {"reading": self._reading(preview)}
        )
        audiogram = Audiogram.objects.get()
        self.assertRedirects(response, reverse("audiogram_detail", args=[audiogram.id]))
        self.assertEqual((audiogram.user, audiogram.tested_on), (self.user, date(2026, 1, 5)))
        self.assertEqual((audiogram.source, audiogram.entry), ("self_test", "apple_pdf"))
        saved = {
            (p.ear, p.frequency): p.db
            for p in audiogram.points.all()
            if (p.conduction, p.no_response, p.masked) == ("air", False, False)
        }
        self.assertEqual(
            saved,
            {("right", f): db for f, db in zip(FREQUENCIES, right, strict=True)}
            | {("left", f): db for f, db in zip(FREQUENCIES, left, strict=True)},
        )

    def test_signed_out_goes_to_sign_in(self):
        """Spec #702 acceptance 10."""
        self.client.logout()
        for url in (reverse("audiogram_import"), reverse("audiogram_import_save")):
            with self.subTest(url):
                response = self.client.post(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)
        self.assertEqual(Audiogram.objects.count(), 0)

    def test_the_pdf_and_its_name_are_not_kept(self):
        """Spec #702 acceptance 8: a readable PDF is read in memory (never a temporary file),
        and nothing on it but the date and the values reaches the database."""
        self.assertGreaterEqual(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, MAX_BYTES)
        preview = self._preview()
        self.client.post(reverse("audiogram_import_save"), {"reading": self._reading(preview)})
        out = StringIO()
        call_command("dumpdata", "screening", stdout=out)
        for words in ("王小明", "1950", "76歲"):
            self.assertNotIn(words, out.getvalue())

    def test_an_imported_audiogram_cannot_be_changed(self):
        """Spec #702 acceptance 13: no 修改 on its page; its edit page and the API refuse."""
        preview = self._preview()
        self.client.post(reverse("audiogram_import_save"), {"reading": self._reading(preview)})
        audiogram = Audiogram.objects.get()
        main = self._main(self.client.get(reverse("audiogram_detail", args=[audiogram.id])))
        self.assertNotIn(reverse("audiogram_edit", args=[audiogram.id]), main)
        self.assertIn(reverse("audiogram_delete", args=[audiogram.id]), main)
        self.assertEqual(
            self.client.get(reverse("audiogram_edit", args=[audiogram.id])).status_code, 404
        )
        body = {
            "tested_on": "2026-11-10",
            "source": "self_test",
            "points": [{"ear": "right", "conduction": "air", "frequency": 1000, "db": 40}],
        }
        response = self.client.put(
            f"/api/audiograms/{audiogram.id}/", json.dumps(body), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"], "從 iPhone 匯入的聽力圖不能修改，可以刪掉重新匯入"
        )
        self.assertEqual(audiogram.points.count(), 16)


class PrivacyNoticeTests(TestCase):
    def test_says_imported_audiograms_and_that_the_pdf_is_dropped(self):
        """Spec #702 acceptance 23: the owner's sentence; the consent version stays."""
        from screening.models import accounts

        content = self.client.get(reverse("privacy")).content.decode()
        self.assertIn(
            "您自己輸入或從 iPhone 匯入的聽力圖（匯入用的 PDF 讀完就丟，不保存）", content
        )
        self.assertNotIn("您自己輸入的聽力圖、", content)
        self.assertEqual(accounts.CONSENT_VERSION, 8)


class ImportEntryTests(TestCase):
    """#703 mockup 1C (docs/verification/issue-703.md): beside each 記錄聽力圖, an outlined
    從 iPhone 匯入 under it; the family zone's signed-out sentence stays as it is."""

    IMPORT = f'href="{reverse("audiogram_import")}"'

    @classmethod
    def setUpTestData(cls):
        from screening.models import Questionnaire
        from screening.questionnaires import hhie_s

        cls.hhie_s = Questionnaire.objects.create(questionnaire_name="HHIE-S", code=hhie_s.CODE)

    def setUp(self):
        self.user = consented_user(username="import_entry")
        self.client.force_login(self.user)

    def _after_record(self, content, record_href):
        """The 從 iPhone 匯入 that comes right after this 記錄聽力圖, outlined or a link."""
        start = content.index(f'href="{record_href}"')
        found = re.search(
            r"<a [^>]*" + re.escape(self.IMPORT) + r"[^>]*>從 iPhone 匯入</a>", content[start:]
        )
        self.assertIsNotNone(found)
        return found[0]

    def test_the_audiogram_list(self):
        content = self.client.get(reverse("audiogram_list")).content.decode()
        button = self._after_record(content, reverse("audiogram_new"))
        self.assertIn('class="btn btn-outline-primary btn-lg w-full mt-3"', button)

    def test_the_guide_without_records(self):
        content = self.client.get(reverse("guide")).content.decode()
        self.assertIn("btn-outline-primary", self._after_record(content, reverse("audiogram_new")))

    def test_the_guide_with_a_questionnaire_and_no_audiogram(self):
        """The 您在這裡 stop's 記錄聽力圖 and the audiogram part's link both have it."""
        from screening.models import Submission

        Submission.objects.create(user=self.user, questionnaire=self.hhie_s)
        content = self.client.get(reverse("guide")).content.decode()
        stop = content[content.index('data-stop="audiogram"') :]
        self.assertIn("btn-outline-primary", self._after_record(stop, reverse("audiogram_new")))
        part = content[content.index('id="audiogram-title"') :]
        self._after_record(part, reverse("audiogram_new"))
