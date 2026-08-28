from django.db import migrations, models
import djmoney.models.fields


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0062_merge_ticket240_discounts_and_homol"),
    ]

    operations = [
        migrations.AlterField(
            model_name="financialmovement",
            name="discount_mode",
            field=models.CharField(
                choices=[
                    ("NONE", "Sem desconto ou acréscimo"),
                    ("AMOUNT", "Desconto"),
                    ("SURCHARGE", "Acréscimo"),
                    ("PERCENTAGE", "Desconto percentual (legado)"),
                ],
                default="NONE",
                max_length=12,
                verbose_name="Desconto ou Acréscimo",
            ),
        ),
        migrations.AlterField(
            model_name="financialmovement",
            name="discount_value",
            field=djmoney.models.fields.MoneyField(decimal_places=2, default=0, max_digits=14, verbose_name="Ajuste (R$)"),
        ),
    ]
