from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("finance", "0067_financialtransfer")]

    operations = [
        migrations.AddField(
            model_name="financialtransfer",
            name="reversal_of",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reversal_entry", to="finance.financialtransfer"),
        ),
    ]
