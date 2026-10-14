from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0079_purchasereturnrequest_soft_delete"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasereturnrequest",
            name="ipi_situacao_tributaria",
            field=models.CharField(blank=True, default="", max_length=2, verbose_name="Situação tributária do IPI"),
        ),
        migrations.AddField(
            model_name="purchasereturnrequest",
            name="ipi_codigo_enquadramento",
            field=models.CharField(blank=True, default="", max_length=3, verbose_name="Código de enquadramento do IPI"),
        ),
    ]
