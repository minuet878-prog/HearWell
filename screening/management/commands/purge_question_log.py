from django.core.management.base import BaseCommand

from screening.models import purge_question_log


class Command(BaseCommand):
    help = (
        "Count each question log entry over 90 days into its month's stats, then delete it "
        "(#401, #452; run every day at 02:30 on the VPS, and also when a question is saved or "
        "the admin is opened)."
    )

    def handle(self, *args, **options):
        purged = purge_question_log()
        self.stdout.write(f"Purged {purged} question(s) older than 90 days.")
