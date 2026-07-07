from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0031_remove_workorder_observations"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorderitem",
            name="item_benefit_type",
            field=models.CharField(
                choices=[("normal", "Normal"), ("warranty", "Garantia"), ("courtesy", "Cortesia")],
                default="normal",
                max_length=20,
                verbose_name="Tipo de Benefício",
            ),
        ),
    ]
