from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0043_budget_customer_agreed_departure_at_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="budget",
            name="pdf_observation",
            field=models.TextField(blank=True, default="", verbose_name="Observação do PDF"),
        ),
    ]
