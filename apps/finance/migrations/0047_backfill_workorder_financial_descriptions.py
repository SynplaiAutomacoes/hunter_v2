# Generated manually for OS revenue description backfill

from __future__ import annotations

from django.db import migrations


_REVENUE_DESCRIPTION_PREFIX = "Receita proveniente de ordem de serviço"
_BATCH_SIZE = 500


def _build_workorder_revenue_description(*, workorder_id: int, brand: str, model: str, plate: str, has_vehicle: bool) -> str:
    if not has_vehicle:
        return f"{_REVENUE_DESCRIPTION_PREFIX} OS Nº {workorder_id}"

    mid = " ".join(part for part in (brand.strip(), model.strip()) if part)
    plate_value = plate.strip()

    if mid and plate_value:
        return f"{_REVENUE_DESCRIPTION_PREFIX} {mid} - {plate_value}"
    if mid:
        return f"{_REVENUE_DESCRIPTION_PREFIX} {mid}"
    if plate_value:
        return f"{_REVENUE_DESCRIPTION_PREFIX} {plate_value}"
    return f"{_REVENUE_DESCRIPTION_PREFIX} OS Nº {workorder_id}"


def _backfill_workorder_financial_descriptions(apps, schema_editor) -> None:
    FinancialMovement = apps.get_model("finance", "FinancialMovement")

    queryset = (
        FinancialMovement.objects.filter(
            movement_kind="WORKORDER_PARENT",
            workorder_id__isnull=False,
            reversal_of_id__isnull=True,
        )
        .select_related("workorder__budget__vehicle")
        .order_by("pk")
        .iterator(chunk_size=_BATCH_SIZE)
    )

    pending: list[object] = []
    for movement in queryset:
        workorder = getattr(movement, "workorder", None)
        if workorder is None:
            continue

        budget = getattr(workorder, "budget", None)
        vehicle = getattr(budget, "vehicle", None) if budget is not None else None
        new_description = _build_workorder_revenue_description(
            workorder_id=workorder.pk,
            brand=str(getattr(vehicle, "brand", "") or "") if vehicle is not None else "",
            model=str(getattr(vehicle, "model", "") or "") if vehicle is not None else "",
            plate=str(getattr(vehicle, "plate", "") or "") if vehicle is not None else "",
            has_vehicle=vehicle is not None,
        )
        if movement.description == new_description:
            continue

        movement.description = new_description
        pending.append(movement)
        if len(pending) >= _BATCH_SIZE:
            FinancialMovement.objects.bulk_update(pending, ["description"])
            pending.clear()

    if pending:
        FinancialMovement.objects.bulk_update(pending, ["description"])


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0046_revert_staging_merge"),
    ]

    operations = [
        migrations.RunPython(_backfill_workorder_financial_descriptions, migrations.RunPython.noop),
    ]
