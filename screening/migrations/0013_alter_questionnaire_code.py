from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("screening", "0012_questionnaire_code"),
    ]

    operations = [
        migrations.AlterField(
            model_name="questionnaire",
            name="code",
            field=models.SlugField(max_length=32, unique=True),
        ),
    ]
