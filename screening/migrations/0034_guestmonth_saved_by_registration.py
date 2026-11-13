# Spec #505 Q13 (#513): 保存 split by how the saving account was registered. The one count there
# was is renamed, not dropped, so every month's saves so far stay as the password column's: no
# account had registered with anything else before this.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0033_signinmethod'),
    ]

    operations = [
        migrations.RenameField(
            model_name='guestmonth',
            old_name='saved',
            new_name='saved_password',
        ),
        migrations.AlterField(
            model_name='guestmonth',
            name='saved_password',
            field=models.PositiveIntegerField(default=0, verbose_name='保存（帳號密碼）'),
        ),
        migrations.AddField(
            model_name='guestmonth',
            name='saved_google',
            field=models.PositiveIntegerField(default=0, verbose_name='保存（Google）'),
        ),
        migrations.AddField(
            model_name='guestmonth',
            name='saved_line',
            field=models.PositiveIntegerField(default=0, verbose_name='保存（LINE）'),
        ),
    ]
