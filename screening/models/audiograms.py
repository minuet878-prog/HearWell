from django.conf import settings
from django.db import models

from screening.audiogram import APPLE_DB_MIN, interpret


class AudiogramSource(models.TextChoices):
    # Spec #702, ADR 0068: who did the test. Only an exam estimates the disability assessment.
    EXAM = "exam", "聽力檢查"
    SELF_TEST = "self_test", "自我測試"


class AudiogramEntry(models.TextChoices):
    # How it came in: marked on the chart, or read from Apple's Health PDF (always a self test).
    MANUAL = "manual", "自己標"
    APPLE_PDF = "apple_pdf", "Apple PDF 匯入"


class Audiogram(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="audiograms"
    )
    tested_on = models.DateField()
    # The defaults are what every audiogram before #704 was; marking asks for the source.
    source = models.CharField(
        max_length=16, choices=AudiogramSource.choices, default=AudiogramSource.EXAM
    )
    entry = models.CharField(
        max_length=16, choices=AudiogramEntry.choices, default=AudiogramEntry.MANUAL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Same retry guard as Submission.idempotency_key.
    idempotency_key = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["user", "idempotency_key"], name="unique_audiogram_idempotency_key"
            ),
        )
        # Saved later on the same test date comes first.
        ordering = ("-tested_on", "-id")

    def __str__(self):
        return f"{self.user} audiogram {self.tested_on}"

    @property
    def is_self_test(self):
        # Spec #702, ADR 0068: pages tag it, and only an exam estimates the disability assessment.
        return self.source == AudiogramSource.SELF_TEST

    def interpretation(self):
        # The only path to an audiogram's result; pages and the API all read it here.
        return interpret(self.points.all())


class Ear(models.TextChoices):
    RIGHT = "right", "右耳"
    LEFT = "left", "左耳"


class Conduction(models.TextChoices):
    AIR = "air", "氣導"
    BONE = "bone", "骨導"


class AudiogramPoint(models.Model):
    # CASCADE, unlike the rest: a point means nothing without its audiogram, and users can
    # delete their audiograms.
    audiogram = models.ForeignKey(Audiogram, on_delete=models.CASCADE, related_name="points")
    ear = models.CharField(max_length=8, choices=Ear.choices)
    conduction = models.CharField(max_length=8, choices=Conduction.choices)
    frequency = models.PositiveSmallIntegerField()
    db = models.SmallIntegerField()
    no_response = models.BooleanField(default=False)
    # Only how the point is drawn; interpretation reads the value either way.
    masked = models.BooleanField(default=False)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["audiogram", "ear", "conduction", "frequency"],
                name="unique_audiogram_point",
            ),
            # The full rules (frequencies, step, bone limit) are checked by the API serializer.
            models.CheckConstraint(
                condition=models.Q(db__gte=APPLE_DB_MIN, db__lte=120), name="audiogram_db_range"
            ),
        )
        ordering = ("ear", "conduction", "frequency")

    def __str__(self):
        return f"{self.ear} {self.conduction} {self.frequency} Hz: {self.db}"
