from django.conf import settings
from django.db import models

# #481: every tick is in this round until #482 sets when a step's or a stop's 手動待辦 start over
# (spec #478: the latest life-impact record for step 5, the pair of hearing aids for step 4 and
# the eight stops after 記錄聽力圖, one round for that one).
FIRST_ROUND = 1


class TodoTick(models.Model):
    # A 手動待辦 ticked (spec #478, ADR 0047), one row a tick; unticking deletes it. An 自動待辦
    # is never kept, being judged from the records each time.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="todo_ticks"
    )
    key = models.CharField(max_length=40)  # a JourneyTodo's key
    round = models.PositiveIntegerField()
    ticked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("user", "key", "round"), name="one_tick_per_todo_and_round"
            ),
        )

    def __str__(self):
        return f"{self.user} ticked {self.key} in round {self.round}"
