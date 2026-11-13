from django.db import models
from django.db.models import F
from django.utils import timezone


class GuestMonth(models.Model):
    # 訪客月計數 (spec #492, #500): how many guests finished HHIE-S or HHIA-S each month and how
    # many of those results were saved into an account. Only the month and the two counts: no IP,
    # account or answers, so it is not in 下載我的資料 and stays when an account is deleted.
    month = models.DateField("月份", unique=True)  # the month's first day, Taipei time
    completed = models.PositiveIntegerField("訪客完成", default=0)
    saved = models.PositiveIntegerField("保存", default=0)

    class Meta:
        verbose_name = verbose_name_plural = "訪客月計數"

    def __str__(self):
        return f"{self.month.year}/{self.month.month:02d}"


def count_guest(field):
    """Add one to this month's completed or saved, as the 提問紀錄's month stats count."""
    month = timezone.localdate().replace(day=1)
    GuestMonth.objects.get_or_create(month=month)
    # F(): added in the database, so two guests at the same moment both count.
    GuestMonth.objects.filter(month=month).update(**{field: F(field) + 1})
