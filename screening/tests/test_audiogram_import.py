"""從 iPhone 匯入 an Apple hearing test PDF (spec #702, ticket #707): the readable path, on
made-up PDFs drawn like the real one (apple_pdf.py)."""

import json
import re
import time
from datetime import date, datetime
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from screening.admin import ImportFailureMonthAdmin
from screening.apple_hearing_test import MAX_BYTES
from screening.models import Audiogram, ImportFailureMonth, Unreadable, User
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
            # The words before each step's drawing (#709), whose own words are the picture's.
            [test_layout._text(step.split("<svg")[0]) for step in steps],
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

    def test_each_step_has_its_phone_drawing(self):
        """#709 (#709 mockup A): under each step's words, a drawing of the phone in the site's
        blue lines, read out by its own words."""
        main = self._main(self.client.get(reverse("audiogram_import")))
        steps = re.findall(r"<li>(.*?)</li>", main.split('class="step-list"')[1], re.S)
        self.assertEqual(len(steps), 6)
        for number, step in enumerate(steps, 1):
            with self.subTest(step=number):
                drawing = re.search(r'<svg class="import-drawing"[^>]*>', step)
                self.assertIsNotNone(drawing)
                self.assertIn('role="img"', drawing[0])
                self.assertRegex(drawing[0], r'aria-label="手機畫面示意：[^"]+"')
                self.assertLess(step.index("step-list-body"), step.index("<svg"))

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
        for method, url in (
            ("get", reverse("audiogram_import")),
            ("post", reverse("audiogram_import")),
            ("post", reverse("audiogram_import_save")),
        ):
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url)
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
        audiogram.refresh_from_db()
        self.assertEqual(audiogram.tested_on, date(2026, 11, 10))
        kept = {(p.ear, p.frequency): p.db for p in audiogram.points.all()}
        self.assertEqual(
            kept,
            {("right", f): db for f, db in zip(FREQUENCIES, RIGHT, strict=True)}
            | {("left", f): db for f, db in zip(FREQUENCIES, LEFT, strict=True)},
        )


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

    def test_the_home_card_offers_it_under_recording_one(self):
        """#703 mockup 1C: the 照顧旅程's 記錄聽力圖 card has it too, outlined."""
        from screening.models import Submission

        Submission.objects.create(user=self.user, questionnaire=self.hhie_s)
        content = self.client.get(reverse("index")).content.decode()
        card = content[content.index('class="journey-card"') :]
        button = self._after_record(card, reverse("audiogram_new") + "?next=/")
        self.assertIn("btn-outline-primary", button)
        self.assertLess(card.index("從 iPhone 匯入"), card.index("還沒，看要去哪裡檢查"))


UNREADABLE = (
    "這份 PDF 讀不出來。請確認是「健康」app 的聽力測試結果；也可以照著 PDF 自己把數字標上去。"
)
NOT_SAVED = "沒有存到，請重新選一次 PDF。"
ALREADY = "這份已經匯入過了。"
NOISE = "測試時周圍有點吵，有些點可能比實際差。"
CONGESTED = "鼻塞時測的，結果可能偏差。"
LOUD = "剛聽過大聲音，結果可能偏差。"


class ImportEdgeCaseTests(TestCase):
    """Spec #702 acceptance 5-7, 9, 24 (ticket #708); messages on the import page itself, the
    file again under them (#703 mockup 4A)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = consented_user(username="王大明")
        cls.other = consented_user(username="王二明")

    def setUp(self):
        self.client.force_login(self.user)

    _main = AudiogramImportTests._main
    _reading = AudiogramImportTests._reading

    def _post(self, data, name="聽力測試.pdf"):
        upload = SimpleUploadedFile(name, data, "application/pdf")
        return self.client.post(reverse("audiogram_import"), {"pdf": upload})

    def _counts(self):
        month = ImportFailureMonth.objects.get()
        # Counted in this month, Taipei time.
        self.assertEqual(month.month, timezone.localdate().replace(day=1))
        return {reason: getattr(month, reason) for reason in Unreadable.values}

    def test_each_unreadable_file_says_so_and_is_counted(self):
        missing = (*RIGHT[:7], None)
        off = (RIGHT[0] + 10, *RIGHT[1:])
        files = (
            (b"%PDF" + b"0" * MAX_BYTES, "not_a_pdf"),
            ("不是 PDF".encode(), "not_a_pdf"),
            (apple_pdf(source="Source: Apple Hearing Test"), "not_apple"),
            (apple_pdf(printed={"right": missing}), "layout"),
            (apple_pdf(printed={"right": off}), "cross_check"),
        )
        for data, _ in files:
            main = self._main(self._post(data))
            with self.subTest(main=main[:60]):
                self.assertIn(UNREADABLE, main)
                # 自己標 right under the message, then the file once more.
                self.assertLess(main.index(UNREADABLE), main.index(">自己標</a>"))
                self.assertIn(f'href="{reverse("audiogram_new")}"', main)
                self.assertLess(main.index(">自己標</a>"), main.index('type="file"'))
                self.assertNotIn("存下來", main)
        self.assertEqual(
            self._counts(), {"not_a_pdf": 2, "not_apple": 1, "layout": 1, "cross_check": 1}
        )
        self.assertEqual(Audiogram.objects.count(), 0)

    def test_the_same_test_again_links_to_the_one_kept(self):
        """Same person, imported, same day, same 16 values: no second one, from either page."""
        preview = self._post(apple_pdf())
        reading = self._reading(preview)
        self.client.post(reverse("audiogram_import_save"), {"reading": reading})
        kept = Audiogram.objects.get()
        main = self._main(self._post(apple_pdf()))
        self.assertIn(ALREADY, main)
        self.assertRegex(
            main,
            rf'<a [^>]*href="{reverse("audiogram_detail", args=[kept.id])}"[^>]*>看那張聽力圖</a>',
        )
        self.assertNotIn("存下來", main)
        self.assertIn('type="file"', main)
        response = self.client.post(reverse("audiogram_import_save"), {"reading": reading})
        self.assertRedirects(response, reverse("audiogram_detail", args=[kept.id]))
        self.assertEqual(Audiogram.objects.count(), 1)

    def test_another_day_or_value_is_not_the_same(self):
        for data in (
            apple_pdf(),
            apple_pdf(tested_at=datetime(2026, 11, 11, 9)),
            apple_pdf(right=(12, *RIGHT[1:])),
        ):
            preview = self._post(data)
            self.client.post(reverse("audiogram_import_save"), {"reading": self._reading(preview)})
        self.assertEqual(Audiogram.objects.count(), 3)

    def test_a_preview_too_old_changed_or_someone_elses_saves_nothing(self):
        with mock.patch("django.core.signing.time.time", return_value=time.time() - 31 * 60):
            old = self._reading(self._post(apple_pdf()))
        mine = self._reading(self._post(apple_pdf()))
        changed = mine[:-3] + ("AAA" if not mine.endswith("AAA") else "BBB")
        self.client.force_login(self.other)
        theirs = self._reading(self._post(apple_pdf()))
        self.client.force_login(self.user)
        for name, reading in (("old", old), ("changed", changed), ("theirs", theirs)):
            with self.subTest(name):
                response = self.client.post(reverse("audiogram_import_save"), {"reading": reading})
                main = self._main(response)
                self.assertIn(NOT_SAVED, main)
                self.assertIn('type="file"', main)
        # Nobody's: not this person's, and not the other's either.
        self.assertEqual(Audiogram.objects.count(), 0)

    def test_the_preview_reminds_only_of_what_the_pdf_says(self):
        """Spec #702 acceptance 5: one sentence each, only when so; nothing of it is saved."""
        for name, pdf, said in (
            ("all", dict(stars=True, congested=True, loud_noise=True), {NOISE, CONGESTED, LOUD}),
            ("none", dict(stars=False), set()),
            ("asterisk", dict(stars=True), {NOISE}),
            ("congested", dict(stars=False, congested=True), {CONGESTED}),
            ("loud noise", dict(stars=False, loud_noise=True), {LOUD}),
        ):
            with self.subTest(name):
                main = self._main(self._post(apple_pdf(**pdf)))
                self.assertEqual({w for w in (NOISE, CONGESTED, LOUD) if w in main}, said)
        preview = self._post(apple_pdf(stars=True, congested=True, loud_noise=True))
        self.client.post(reverse("audiogram_import_save"), {"reading": self._reading(preview)})
        out = StringIO()
        call_command("dumpdata", "screening.audiogram", "screening.audiogrampoint", stdout=out)
        for kept in ("noise", "congest", "loud"):
            self.assertNotIn(kept, out.getvalue())


class ImportFailureMonthAdminTests(TestCase):
    """Spec #702 acceptance 24: the owner reads each month's reasons, and only reads them."""

    def test_each_reason_has_its_count_and_its_column(self):
        """A reason added to Unreadable needs its field here and its column in the admin."""
        fields = {f.name: f.verbose_name for f in ImportFailureMonth._meta.fields}
        self.assertEqual(
            {name: fields[name] for name in Unreadable.values}, dict(Unreadable.choices)
        )
        self.assertEqual(set(fields) - {"id", "month"}, set(Unreadable.values))
        self.assertEqual(ImportFailureMonthAdmin.list_display[1:], tuple(Unreadable.values))

    def test_the_owner_reads_each_reason_and_cannot_change_them(self):
        october = ImportFailureMonth.objects.create(month=date(2026, 10, 1), layout=3)
        self.client.force_login(User.objects.create_superuser(username="owner", password="pw"))
        page = self.client.get(reverse("admin:screening_importfailuremonth_changelist"))
        content = page.content.decode()
        for heading in (
            "月份",
            "檔案太大或不是 PDF",
            "不是 Apple 聽力測試",
            "版面認不得",
            "交叉驗證不符",
        ):
            self.assertIn(heading, content)
        self.assertIn(">2026/10<", content)
        self.assertIn('<td class="field-layout">3</td>', content)
        add = reverse("admin:screening_importfailuremonth_add")
        change = reverse("admin:screening_importfailuremonth_change", args=[october.pk])
        self.assertEqual(
            self.client.post(change, {"month": "2026-10-01", "layout": 0}).status_code, 403
        )
        delete = reverse("admin:screening_importfailuremonth_delete", args=[october.pk])
        self.assertEqual(self.client.get(add).status_code, 403)
        self.assertEqual(self.client.post(delete, {"post": "yes"}).status_code, 403)
        october.refresh_from_db()
        self.assertEqual(october.layout, 3)
