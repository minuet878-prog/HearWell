from django.db import migrations, models
from django.utils.text import slugify


def fill_code(apps, schema_editor):
    Questionnaire = apps.get_model("screening", "Questionnaire")
    for questionnaire in Questionnaire.objects.all():
        slug = slugify(questionnaire.questionnaire_name)[:32]
        questionnaire.code = slug or f"questionnaire-{questionnaire.pk}"
        questionnaire.save(update_fields=["code"])


class Migration(migrations.Migration):
    dependencies = [
        ("screening", "0011_meta_options_to_tuples"),
    ]

    operations = [
        migrations.AddField(
            model_name="questionnaire",
            name="code",
            field=models.SlugField(max_length=32, null=True),
        ),
        migrations.RunPython(fill_code, migrations.RunPython.noop),
    ]
