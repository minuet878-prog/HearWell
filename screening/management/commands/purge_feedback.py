from django.core.management.base import BaseCommand

from screening.models import purge_feedback


class Command(BaseCommand):
    help = (
        "Delete each 意見回饋 over 90 days (spec #633, #639; run every day at 02:30 on the VPS, "
        "beside purge_question_log, and also when the admin list is opened)."
    )

    def handle(self, *args, **options):
        purged = purge_feedback()
        self.stdout.write(f"Purged {purged} feedback older than 90 days.")
