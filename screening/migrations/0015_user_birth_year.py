from django.db import migrations, models


def copy_birth_year(apps, schema_editor):
    User = apps.get_model("screening", "User")
    for user in User.objects.filter(birth_date__isnull=False):
        user.birth_year = user.birth_date.year
        user.save(update_fields=["birth_year"])


class Migration(migrations.Migration):
    dependencies = [
        ("screening", "0014_submission_wearing_hearing_aid"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="birth_year",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        # Reverse is a no-op on purpose: month and day are dropped in 0016 and
        # must not be invented. Rolling back past this migration therefore loses
        # all birth data (birth_date comes back empty, birth_year is dropped).
        migrations.RunPython(copy_birth_year, migrations.RunPython.noop),
    ]
