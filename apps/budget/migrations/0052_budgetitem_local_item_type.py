from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0051_budgetitem_item_benefit_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgetitem",
            name="local_item_type",
            field=models.CharField(
                blank=True,
                choices=[("product", "Produto"), ("service", "Serviço")],
                default="",
                max_length=20,
                verbose_name="Tipo do Item Local",
            ),
        ),
    ]
