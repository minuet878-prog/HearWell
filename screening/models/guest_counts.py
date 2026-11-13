from django.db import models
from django.db.models import F
from django.utils import timezone


class GuestMonth(models.Model):
    # 訪客月計數 (spec #492, #500): how many guests finished HHIE-S or HHIA-S each month and how
    # many of those results were saved into an account, by how that account was registered (spec
    # #505 Q13, #513). Only the month and the counts: no IP, account or answers, so it is not in
    # 下載我的資料 and stays when an account is deleted.
    month = models.DateField("月份", unique=True)  # the month's first day, Taipei time
    completed = models.PositiveIntegerField("訪客完成", default=0)
    # Before #513 there was one 保存 count; migration 0034 kept it as the password column's.
    saved_password = models.PositiveIntegerField("保存（帳號密碼）", default=0)
    saved_google = models.PositiveIntegerField("保存（Google）", default=0)
    saved_line = models.PositiveIntegerField("保存（LINE）", default=0)  # 0 until LINE (#506)

    class Meta:
        verbose_name = verbose_name_plural = "訪客月計數"

    def __str__(self):
        return f"{self.month.year}/{self.month.month:02d}"


def count_guest_saved(user):
    """Add one to this month's 保存 in the column of how this account was registered: the sign-in
    method it registered with, or none, a password (Q13). A method added later does not count."""
    provider = (
        user.sign_in_methods.filter(used_to_register=True)
        .values_list("provider", flat=True)
        .first()
    )
    count_guest(f"saved_{provider or 'password'}")


def count_guest(field):
    """Add one to this month's field, as the 提問紀錄's month stats count."""
    month = timezone.localdate().replace(day=1)
    GuestMonth.objects.get_or_create(month=month)
    # F(): added in the database, so two guests at the same moment both count.
    GuestMonth.objects.filter(month=month).update(**{field: F(field) + 1})
