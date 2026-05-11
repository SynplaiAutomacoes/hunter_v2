from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0038_remove_financialgroup_dre_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="financialmovement",
            name="reversal_of",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reversal_entry", to="finance.financialmovement"),
        ),
    ]
