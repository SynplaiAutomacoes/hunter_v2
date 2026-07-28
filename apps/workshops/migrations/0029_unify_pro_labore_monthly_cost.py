from __future__ import annotations

from django.db import migrations

PRO_LABORE_MONTHLY_COST_NAME = "Total de salários Pró Labore"
PRO_LABORE_ALIASES = ("Pró Labore", "Pro Labore")


def _normalize_cost_name(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold().strip()


def unify_pro_labore_monthly_costs(apps, schema_editor) -> None:
    Workshop = apps.get_model("workshops", "Workshop")
    MonthlyCost = apps.get_model("workshops", "MonthlyCost")
    WorkshopCostItem = apps.get_model("workshops", "WorkshopCostItem")

    canonical_normalized = _normalize_cost_name(PRO_LABORE_MONTHLY_COST_NAME)
    alias_normalized = {_normalize_cost_name(alias) for alias in PRO_LABORE_ALIASES}

    for workshop in Workshop.objects.all().iterator():
        candidates = list(MonthlyCost.objects.filter(workshop_id=workshop.pk).order_by("id"))
        canonical = None
        aliases: list[object] = []

        for monthly_cost in candidates:
            normalized = _normalize_cost_name(monthly_cost.name)
            if normalized == canonical_normalized:
                if canonical is None:
                    canonical = monthly_cost
                else:
                    aliases.append(monthly_cost)
            elif normalized in alias_normalized:
                aliases.append(monthly_cost)

        if canonical is None and aliases:
            canonical = aliases.pop(0)
            canonical.name = PRO_LABORE_MONTHLY_COST_NAME
            canonical.is_active = True
            canonical.is_editable = False
            canonical.save(update_fields=["name", "is_active", "is_editable"])

        if canonical is None:
            MonthlyCost.objects.create(
                workshop_id=workshop.pk,
                name=PRO_LABORE_MONTHLY_COST_NAME,
                is_active=True,
                is_editable=False,
            )
            continue

        update_fields: list[str] = []
        if canonical.name != PRO_LABORE_MONTHLY_COST_NAME:
            canonical.name = PRO_LABORE_MONTHLY_COST_NAME
            update_fields.append("name")
        if not canonical.is_active:
            canonical.is_active = True
            update_fields.append("is_active")
        if canonical.is_editable:
            canonical.is_editable = False
            update_fields.append("is_editable")
        if update_fields:
            canonical.save(update_fields=update_fields)

        for alias in aliases:
            for item in WorkshopCostItem.objects.filter(monthly_cost_id=alias.pk):
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
            alias.delete()


def noop_reverse(apps, schema_editor) -> None:
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0028_add_transport_allowance_monthly_cost"),
    ]

    operations = [
        migrations.RunPython(unify_pro_labore_monthly_costs, noop_reverse),
    ]
