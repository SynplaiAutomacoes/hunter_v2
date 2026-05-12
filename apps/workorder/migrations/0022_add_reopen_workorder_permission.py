from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0021_workorderhistory"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="workorder",
            options={
                "verbose_name": "Ordem de Serviço",
                "verbose_name_plural": "Ordens de Serviço",
                "permissions": [("reopen_workorder", "Can Reopen Ordem de Serviço")],
            },
        ),
    ]
