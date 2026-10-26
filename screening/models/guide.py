from django.conf import settings
from django.db import models


class GuideChapterView(models.Model):
    # 看過 (spec #291, ADR 0021): a chapter the user opened signed in, one row each, kept from
    # the first time. Some chapters' views make their stop on the 選配路線 已完成.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="guide_views"
    )
    chapter = models.CharField(max_length=20)  # a guide chapter's slug
    first_viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=("user", "chapter"), name="one_view_per_chapter"),
        )

    def __str__(self):
        return f"{self.user} viewed {self.chapter}"
