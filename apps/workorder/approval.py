from __future__ import annotations

from django.db import transaction

from apps.catalog.product_issues import has_invalid_ncm
from apps.stock.models import StockMovement, StockProduct
from apps.workorder.models import WorkOrder, WorkOrderStatus


class WorkOrderApprovalError(Exception):
    pass


def _collect_required_products(workorder: WorkOrder) -> tuple[dict[int, int], dict[int, str], list[str]]:
    required_quantities: dict[int, int] = {}
    product_names: dict[int, str] = {}
    invalid_ncm_products: list[str] = []

    for line in workorder.pricing_snapshot.product_lines:
        if line.entity_id is None or line.quantity <= 0:
            continue

        required_quantities[line.entity_id] = required_quantities.get(line.entity_id, 0) + line.quantity
        product_names[line.entity_id] = line.description

        if has_invalid_ncm(getattr(line, "source_object", None)):
            invalid_ncm_products.append(line.description)

    return dict(required_quantities), product_names, list(dict.fromkeys(invalid_ncm_products))


def approve_workorder_with_stock(*, workorder: WorkOrder, user: object | None = None) -> None:
    if workorder.status == WorkOrderStatus.APPROVED:
        return

    required_quantities, product_names, invalid_ncm_products = _collect_required_products(workorder)

    with transaction.atomic():
        blockers: list[str] = []
        stock_by_product_id: dict[int, StockProduct] = {}

        if required_quantities:
            stock_entries = StockProduct.objects.select_for_update().select_related("product").filter(workshop=workorder.workshop, product_id__in=list(required_quantities.keys()))
            stock_by_product_id = {entry.product_id: entry for entry in stock_entries}
            stock_issue_labels: list[str] = []

            for product_id, required_quantity in required_quantities.items():
                stock_entry = stock_by_product_id.get(product_id)
                available_quantity = stock_entry.current_quantity if stock_entry is not None else 0
                excess_quantity = max(required_quantity - available_quantity, 0)
                if excess_quantity > 0:
                    product_name = product_names.get(product_id) or (stock_entry.product.name if stock_entry else str(product_id))
                    stock_issue_labels.append(f"{product_name} (+{excess_quantity})")

            if stock_issue_labels:
                blockers.append(f"Existem pecas com quantidade acima do estoque disponivel: {', '.join(stock_issue_labels)}.")

        if invalid_ncm_products:
            blockers.append(f"Existem produtos com NCM invalido: {', '.join(invalid_ncm_products)}.")

        if blockers:
            raise WorkOrderApprovalError(" ".join(blockers))

        if required_quantities:
            for product_id, required_quantity in required_quantities.items():
                stock_entry = stock_by_product_id[product_id]
                stock_entry.current_quantity -= required_quantity
                stock_entry.save(update_fields=["current_quantity"])

                StockMovement.objects.create(
                    workshop=workorder.workshop,
                    stock_product=stock_entry,
                    workorder=workorder,
                    type=StockMovement.MovementType.EXIT,
                    quantity=required_quantity,
                    status=StockMovement.MovementStatus.APPROVED,
                    transcation_by=user,
                )

        workorder.status = WorkOrderStatus.APPROVED
        workorder.save(update_fields=["status"])
