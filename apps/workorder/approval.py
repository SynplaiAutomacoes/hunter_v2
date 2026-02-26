from __future__ import annotations

from collections import defaultdict

from django.db import transaction

from apps.stock.models import StockMovement, StockProduct
from apps.workorder.models import WorkOrder, WorkOrderStatus


class WorkOrderApprovalError(Exception):
    pass


def _collect_required_products(workorder: WorkOrder) -> tuple[dict[int, int], dict[int, str]]:
    required_quantities: dict[int, int] = defaultdict(int)
    product_names: dict[int, str] = {}

    items = (
        workorder.items.select_related("product", "kit")
        .prefetch_related(
            "kit_overrides",
            "kit__kit_products__product",
        )
        .all()
    )

    for item in items:
        if item.product_id and item.quantity > 0:
            required_quantities[item.product_id] += item.quantity
            product_names[item.product_id] = item.product.name if item.product else str(item.product_id)
            continue

        if item.kit_id and item.quantity > 0:
            for kit_product in item.effective_kit_products:
                product_id = int(kit_product.get("id") or 0)
                base_quantity = int(kit_product.get("quantity") or 0)
                if product_id <= 0 or base_quantity <= 0:
                    continue

                required_quantity = base_quantity * item.quantity
                if required_quantity <= 0:
                    continue

                required_quantities[product_id] += required_quantity
                product_names[product_id] = str(kit_product.get("name") or product_id)

    return dict(required_quantities), product_names


def approve_workorder_with_stock(*, workorder: WorkOrder, user=None) -> None:
    if workorder.status == WorkOrderStatus.APPROVED:
        return

    required_quantities, product_names = _collect_required_products(workorder)

    with transaction.atomic():
        if required_quantities:
            stock_entries = StockProduct.objects.select_for_update().select_related("product").filter(workshop=workorder.workshop, product_id__in=list(required_quantities.keys()))
            stock_by_product_id = {entry.product_id: entry for entry in stock_entries}

            for product_id, required_quantity in required_quantities.items():
                stock_entry = stock_by_product_id.get(product_id)
                if stock_entry is None or stock_entry.current_quantity < required_quantity:
                    product_name = product_names.get(product_id) or (stock_entry.product.name if stock_entry else str(product_id))
                    raise WorkOrderApprovalError(f"Peça {product_name} não tem saldo no estoque")

            for product_id, required_quantity in required_quantities.items():
                stock_entry = stock_by_product_id[product_id]
                stock_entry.current_quantity -= required_quantity
                stock_entry.save(update_fields=["current_quantity"])

                StockMovement.objects.create(
                    workshop=workorder.workshop,
                    stock_product=stock_entry,
                    type=StockMovement.MovementType.EXIT,
                    quantity=required_quantity,
                    status=StockMovement.MovementStatus.APPROVED,
                    transcation_by=user,
                )

        workorder.status = WorkOrderStatus.APPROVED
        workorder.save(update_fields=["status"])
