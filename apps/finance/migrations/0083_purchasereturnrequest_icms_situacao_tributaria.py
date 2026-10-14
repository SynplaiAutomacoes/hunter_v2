from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0082_purchasereturnrequest_ipi_aliquota"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasereturnrequest",
            name="icms_situacao_tributaria",
            field=models.CharField(
                blank=True,
                default="",
                max_length=3,
                verbose_name="Situação tributária do ICMS (CST/CSOSN)",
            ),
        ),
    ]
