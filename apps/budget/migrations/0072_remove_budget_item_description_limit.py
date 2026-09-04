from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0071_merge_excluded_composition_and_freight"),
    ]

    operations = [
        migrations.AlterField(
            model_name="budgetitem",
            name="description",
            field=models.TextField(default="", verbose_name="Descrição"),
        ),
    ]
