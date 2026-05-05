from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0014_workorder_collaborators"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Aprovado"),
                    ("approved", "Veículo Entregue"),
                    ("rejected", "Rejeitado"),
                    ("cancelled", "Cancelado"),
                ],
                default="draft",
                max_length=20,
                verbose_name="Status",
            ),
        ),
    ]
