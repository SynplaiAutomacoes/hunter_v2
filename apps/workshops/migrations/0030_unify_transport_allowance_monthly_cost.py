from __future__ import annotations

from django.db import migrations

TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME = "Total do Vale Transporte"
TRANSPORT_ALLOWANCE_ALIASES = ("Valor Total do Vale Transporte",)


def _normalize_cost_name(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold().strip()


def unify_transport_allowance_monthly_costs(apps, schema_editor) -> None:
    Workshop = apps.get_model("workshops", "Workshop")
    MonthlyCost = apps.get_model("workshops", "MonthlyCost")
    WorkshopCostItem = apps.get_model("workshops", "WorkshopCostItem")

    canonical_normalized = _normalize_cost_name(TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME)
    alias_normalized = {_normalize_cost_name(alias) for alias in TRANSPORT_ALLOWANCE_ALIASES}

    for workshop in Workshop.objects.all().iterator():
        candidates = list(MonthlyCost.objects.filter(workshop_id=workshop.pk).order_by("id"))
        canonical = None
        extras: list[object] = []

        for monthly_cost in candidates:
            normalized = _normalize_cost_name(monthly_cost.name)
            if normalized == canonical_normalized:
                if canonical is None:
                    canonical = monthly_cost
                else:
                    extras.append(monthly_cost)
            elif normalized in alias_normalized:
                extras.append(monthly_cost)

        if canonical is None and extras:
            canonical = extras.pop(0)
            canonical.name = TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME
            canonical.is_active = True
            canonical.is_editable = False
            canonical.save(update_fields=["name", "is_active", "is_editable"])

        if canonical is None:
            MonthlyCost.objects.create(
                workshop_id=workshop.pk,
                name=TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME,
                is_active=True,
                is_editable=False,
            )
            continue

        update_fields: list[str] = []
        if canonical.name != TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME:
            canonical.name = TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME
            update_fields.append("name")
        if not canonical.is_active:
            canonical.is_active = True
            update_fields.append("is_active")
        if canonical.is_editable:
            canonical.is_editable = False
            update_fields.append("is_editable")
        if update_fields:
            canonical.save(update_fields=update_fields)

        for extra in extras:
            for item in WorkshopCostItem.objects.filter(monthly_cost_id=extra.pk):
                existing = WorkshopCostItem.objects.filter(
                    workshop_cost_id=item.workshop_cost_id,
                    monthly_cost_id=canonical.pk,
                ).first()
                if existing is None:
                    item.monthly_cost_id = canonical.pk
                    item.save(update_fields=["monthly_cost"])
                    continue

                source_amount = getattr(item.amount, "amount", None)
                existing_amount = getattr(existing.amount, "amount", None)
                if (existing_amount is None or existing_amount == 0) and source_amount not in (None, 0):
                    existing.amount = item.amount
                    existing.save(update_fields=["amount"])
                item.delete()
            extra.delete()


def noop_reverse(apps, schema_editor) -> None:
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0029_unify_pro_labore_monthly_cost"),
    ]

    operations = [
        migrations.RunPython(unify_transport_allowance_monthly_costs, noop_reverse),
    ]
