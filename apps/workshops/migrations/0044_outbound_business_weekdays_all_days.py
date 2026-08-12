# Generated manually — default outbound weekdays to all days

from django.db import migrations, models


def update_default_weekdays(apps, schema_editor):
    Workshop = apps.get_model("workshops", "Workshop")
    Workshop.objects.filter(outbound_business_weekdays="0,1,2,3,4").update(outbound_business_weekdays="0,1,2,3,4,5,6")


def revert_default_weekdays(apps, schema_editor):
    Workshop = apps.get_model("workshops", "Workshop")
    Workshop.objects.filter(outbound_business_weekdays="0,1,2,3,4,5,6").update(outbound_business_weekdays="0,1,2,3,4")


class Migration(migrations.Migration):

    dependencies = [
        ("workshops", "0042_merge_synplaisign_and_cost_leaves"),
        ("workshops", "0041_alter_workshopcost_gross_revenue_target_and_more"),
        ("workshops", "0031_alter_workshopcost_total_monthly_costs_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workshop",
            name="outbound_business_weekdays",
            field=models.CharField(
                default="0,1,2,3,4,5,6",
                help_text="Dias da semana (Python: Mon=0 … Sun=6), separados por vírgula.",
                max_length=32,
                verbose_name="Dias de disparo",
            ),
        ),
        migrations.RunPython(update_default_weekdays, revert_default_weekdays),
    ]
