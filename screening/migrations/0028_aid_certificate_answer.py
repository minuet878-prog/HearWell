# #293: the certificate's yes / not yet becomes spec #291's three answers. #284's 有 is 有;
# its 還沒有 is 正在申請鑑定, which keeps the user at the stop to answer again, rather than
# 不申請身障補助, which would mark the subsidy's stops 不適用 on a guess.

from django.db import migrations, models


def to_answers(apps, schema_editor):
    AidAndSubsidy = apps.get_model("screening", "AidAndSubsidy")
    AidAndSubsidy.objects.filter(has_certificate=True).update(certificate="yes")
    AidAndSubsidy.objects.filter(has_certificate=False).update(certificate="applying")


def to_yes_or_no(apps, schema_editor):
    AidAndSubsidy = apps.get_model("screening", "AidAndSubsidy")
    AidAndSubsidy.objects.filter(certificate="yes").update(has_certificate=True)
    AidAndSubsidy.objects.exclude(certificate__in=("", "yes")).update(has_certificate=False)


class Migration(migrations.Migration):
    dependencies = [
        ("screening", "0027_guide_chapter_view"),
    ]

    operations = [
        migrations.AddField(
            model_name="aidandsubsidy",
            name="certificate",
            field=models.CharField(
                blank=True,
                choices=[
                    ("yes", "有"),
                    ("applying", "還沒有，正在申請鑑定"),
                    ("no_subsidy", "沒有，不申請身障補助"),
                ],
                default="",
                max_length=10,
            ),
        ),
        migrations.RunPython(to_answers, to_yes_or_no),
        migrations.RemoveField(
            model_name="aidandsubsidy",
            name="has_certificate",
        ),
    ]
