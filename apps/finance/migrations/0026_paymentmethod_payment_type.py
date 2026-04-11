from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0025_financialmovement_dre_topic"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentmethod",
            name="payment_type",
            field=models.CharField(
                choices=[
                    ("CREDIT", "Crédito"),
                    ("DEBIT", "Débito"),
                    ("BOTH", "Ambos"),
                ],
                default="BOTH",
                max_length=10,
                verbose_name="Tipo",
            ),
        ),
    ]
