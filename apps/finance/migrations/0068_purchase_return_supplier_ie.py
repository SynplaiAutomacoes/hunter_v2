from django.db import migrations, models

from apps.finance.migrations import _idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0067_repair_webmania_webhook_fingerprint_column"),
    ]

    operations = [
        _idempotent.AddFieldIfMissing(
            model_name="purchasereturnrequest",
            name="supplier_ie",
            field=models.CharField(blank=True, max_length=14, null=True, verbose_name="Inscrição Estadual do fornecedor"),
        ),
    ]
