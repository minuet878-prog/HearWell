from django.db import migrations, models
from django.db.models import F


def confirm_existing_emails(apps, schema_editor):
    # The owner's pick (security check 2026-11-19): emails kept before 確認信 came in count as
    # confirmed, so nobody already registered is shut out of the 重設密碼信 or the 重測提醒.
    User = apps.get_model("screening", "User")
    User.objects.exclude(email="").update(confirmed_email=F("email"))


class Migration(migrations.Migration):
    dependencies = [
        ("screening", "0043_merge_doors_and_apple_import"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="confirmed_email",
            field=models.EmailField(
                blank=True, default="", max_length=254, verbose_name="確認過的電子郵件"
            ),
        ),
        # Back is the column dropped: nothing to undo.
        migrations.RunPython(confirm_existing_emails, migrations.RunPython.noop),
    ]
