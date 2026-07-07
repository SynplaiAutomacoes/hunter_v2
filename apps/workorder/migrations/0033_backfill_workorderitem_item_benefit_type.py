from django.db import migrations


def backfill_item_benefit_type(apps, schema_editor):
    WorkOrderItem = apps.get_model("workorder", "WorkOrderItem")
    BudgetItem = apps.get_model("budget", "BudgetItem")

    workorder_items = list(
        WorkOrderItem.objects.select_related("workorder").only(
            "id", "workorder_id", "item_benefit_type",
            "product_id", "service_id", "kit_id",
            "description", "quantity",
        )
    )

    budget_ids = {item.workorder.budget_id for item in workorder_items if item.workorder_id and hasattr(item.workorder, "budget_id")}

    if not budget_ids:
        return

    budget_items = list(
        BudgetItem.objects.filter(budget_id__in=budget_ids).only(
            "id", "budget_id", "item_benefit_type",
            "product_id", "service_id", "kit_id",
            "description", "quantity",
        )
    )

    budget_items_by_budget: dict[int, list] = {}
    for bi in budget_items:
        budget_items_by_budget.setdefault(bi.budget_id, []).append(bi)

    for wo_item in workorder_items:
        budget_id = getattr(wo_item.workorder, "budget_id", None)
        if budget_id is None:
            continue

        matched_budget_items = budget_items_by_budget.get(budget_id, [])
        if not matched_budget_items:
            continue

        for bi in matched_budget_items:
            if (bi.product_id is not None and bi.product_id == wo_item.product_id and bi.description == wo_item.description):
                wo_item.item_benefit_type = bi.item_benefit_type
                break
            if (bi.service_id is not None and bi.service_id == wo_item.service_id and bi.description == wo_item.description):
                wo_item.item_benefit_type = bi.item_benefit_type
                break
            if (bi.kit_id is not None and bi.kit_id == wo_item.kit_id):
                wo_item.item_benefit_type = bi.item_benefit_type
                break

    WorkOrderItem.objects.bulk_update(workorder_items, ["item_benefit_type"])


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0032_workorderitem_item_benefit_type"),
        ("budget", "0052_budgetitem_local_item_type"),
    ]

    operations = [
        migrations.RunPython(backfill_item_benefit_type, migrations.RunPython.noop),
    ]
