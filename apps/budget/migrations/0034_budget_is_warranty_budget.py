from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0033_budgetitem_is_customer_supplied"),
    ]

    operations = [
        migrations.AddField(
            model_name="budget",
            name="is_warranty_budget",
            field=models.BooleanField(default=False, verbose_name="Orçamento de Garantia"),
        ),
    ]
