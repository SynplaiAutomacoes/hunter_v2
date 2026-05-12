from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("stock", "0011_stocktransfer_operation_type_stocktransfer_reason_and_more"),
        ("workorder", "0019_workorder_reopen_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockmovement",
            name="reversal_of",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reversal_entry", to="stock.stockmovement"),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="workorder",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_movements", to="workorder.workorder"),
        ),
    ]
