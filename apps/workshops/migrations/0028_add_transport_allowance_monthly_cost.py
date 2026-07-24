from __future__ import annotations

from django.db import migrations

TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME = "Valor Total do Vale Transporte"


def ensure_transport_allowance_monthly_costs(apps, schema_editor) -> None:
    Workshop = apps.get_model("workshops", "Workshop")
    MonthlyCost = apps.get_model("workshops", "MonthlyCost")

    for workshop in Workshop.objects.all().iterator():
        exists = MonthlyCost.objects.filter(workshop_id=workshop.pk, name=TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME).exists()
        if exists:
            continue
        MonthlyCost.objects.create(
            workshop_id=workshop.pk,
            name=TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME,
            is_active=True,
            is_editable=False,
        )


def noop_reverse(apps, schema_editor) -> None:
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0027_workshop_whatsapp_phone"),
    ]

    operations = [
        migrations.RunPython(ensure_transport_allowance_monthly_costs, noop_reverse),
    ]
