from django.conf import settings
from django.db import models

# 記錄聽力圖's one round, and the first pair of hearing aids' (#482); journey_todos.current_rounds
# says which round each 手動待辦 is in now.
FIRST_ROUND = 1


class TodoTick(models.Model):
    # A 手動待辦 ticked (spec #478, ADR 0047), one row a tick; unticking deletes it. An 自動待辦
    # is never kept, being judged from the records each time.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="todo_ticks"
    )
    key = models.CharField(max_length=40)  # a JourneyTodo's key
    # The pair's number, or step 5's life-impact record's id (0 before one), with no foreign key
    # to it (spec #478); an earlier round's tick is kept.
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
