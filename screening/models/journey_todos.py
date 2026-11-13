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
    # Which round the tick is of (#482, spec #478), as journey_todos.current_rounds gives it; a
    # tick of an earlier round is kept. One number with three meanings, by the to-do:
    # - 記錄聽力圖's (step 2's card): always FIRST_ROUND (1), as they never start over;
    # - the other eight stops' and step 4's: the pair of hearing aids (AidAndSubsidy.pair_number,
    #   第幾台, from 1);
    # - step 5's: the id of the latest life-impact record when ticked, 0 before one; no foreign
    #   key to it, so deleting records stays as it was.
    round_key = models.PositiveIntegerField()
    ticked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("user", "key", "round_key"), name="one_tick_per_todo_and_round"
            ),
        )

    def __str__(self):
        return f"{self.user} ticked {self.key} in round {self.round_key}"
