from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0056_remove_workorder_item_description_limit"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="workorder",
            options={
                "permissions": [
                    ("reopen_workorder", "Can Reopen Ordem de Serviço"),
                    ("change_delivery_date", "Editar data de entrega do veículo"),
                ],
                "verbose_name": "Ordem de Serviço",
                "verbose_name_plural": "Ordens de Serviço",
            },
        ),
    ]
