from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0081_merge_20260930_1741"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasereturnrequest",
            name="ipi_aliquota",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=7,
                null=True,
                verbose_name="Alíquota do IPI",
            ),
        ),
    ]
