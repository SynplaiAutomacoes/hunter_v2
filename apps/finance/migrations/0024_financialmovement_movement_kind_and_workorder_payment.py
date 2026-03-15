import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0011_workorderpaymentmethod_due_date"),
        ("finance", "0023_financialmovement_is_paid"),
    ]

    operations = [
        migrations.AddField(
            model_name="financialmovement",
            name="movement_kind",
            field=models.CharField(choices=[("DEFAULT", "Padrão"), ("WORKORDER_PARENT", "OS Pai"), ("WORKORDER_CARD_FEE", "Taxa da Maquininha")], default="DEFAULT", max_length=30),
        ),
        migrations.AddField(
            model_name="financialmovement",
            name="workorder_payment",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="financial_movements", to="workorder.workorderpaymentmethod"),
        ),
    ]
