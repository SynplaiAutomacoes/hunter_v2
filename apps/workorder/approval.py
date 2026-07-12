from __future__ import annotations

import logging
from collections import defaultdict

from django.db import transaction

from apps.catalog.product_issues import has_invalid_ncm
from apps.stock.models import StockMovement, StockProduct
from apps.workorder.models import WorkOrderItem
from apps.workorder.models import WorkOrder, WorkOrderSignatureStatus, WorkOrderStatus


logger = logging.getLogger(__name__)


class WorkOrderApprovalError(Exception):
    pass


def _collect_required_products(workorder: WorkOrder) -> tuple[dict[int, int], dict[int, str], list[str]]:
    required_quantities: defaultdict[int, int] = defaultdict(int)
    product_names: dict[int, str] = {}
    invalid_ncm_products: list[str] = []

    items = list(WorkOrderItem.objects.filter(workorder=workorder).select_related("product", "kit").prefetch_related("kit_overrides__product"))

    logger.info(
        "workorder_stock_collection_started",
        extra={
            "workorder_id": workorder.pk,
            "items_count": len(items),
            "budget_type": workorder.budget_type,
        },
    )

    for item in items:
        if item.quantity <= 0:
            continue

        if getattr(item, "is_customer_supplied", False):
            continue

        product_id = getattr(item, "product_id", None)
        kit_id = getattr(item, "kit_id", None)

        if product_id is not None:
            required_quantities[product_id] += item.quantity
            product_names[product_id] = item.description or item.product.name

            if has_invalid_ncm(item.product):
                invalid_ncm_products.append(item.description or item.product.name)
            continue

        if kit_id is None:
            continue

        for override in item._iter_frozen_kit_product_overrides():
            if override.quantity <= 0 or override.product_id is None:
                continue

            total_required_quantity = override.quantity * item.quantity
            required_quantities[override.product_id] += total_required_quantity
            product_names[override.product_id] = override.product.name

            if has_invalid_ncm(override.product):
                invalid_ncm_products.append(override.product.name)

    logger.info(
        "workorder_stock_collection_finished",
        extra={
            "workorder_id": workorder.pk,
            "required_quantities": dict(required_quantities),
            "invalid_ncm_products": list(dict.fromkeys(invalid_ncm_products)),
        },
    )

    return dict(required_quantities), product_names, list(dict.fromkeys(invalid_ncm_products))


def approve_workorder_with_stock(*, workorder: WorkOrder, user: object | None = None, signature_approved: bool = False) -> None:
    logger.info(
        "workorder_stock_approval_started",
        extra={
            "workorder_id": workorder.pk,
            "status": workorder.status,
            "signature_approved": signature_approved,
            "user_id": getattr(user, "pk", None),
        },
    )

    with transaction.atomic():
        locked_workorder = WorkOrder.objects.select_for_update().select_related("workshop", "budget").get(pk=workorder.pk)

        logger.info(
            "workorder_stock_approval_locked",
            extra={
                "workorder_id": locked_workorder.pk,
                "status": locked_workorder.status,
                "signature_request_status": locked_workorder.signature_request_status,
                "budget_type": locked_workorder.budget_type,
            },
        )

        if locked_workorder.status == WorkOrderStatus.APPROVED:
            if signature_approved and locked_workorder.signature_request_status != WorkOrderSignatureStatus.APPROVED:
                locked_workorder.signature_request_status = WorkOrderSignatureStatus.APPROVED
                locked_workorder.save(update_fields=["signature_request_status"])
                logger.info("workorder_stock_approval_signature_updated_for_approved_workorder", extra={"workorder_id": locked_workorder.pk})
            workorder.refresh_from_db(fields=["status", "delivered_at", "signature_request_status"])
            logger.info("workorder_stock_approval_skipped_already_approved", extra={"workorder_id": locked_workorder.pk})
            return

        required_quantities, product_names, invalid_ncm_products = _collect_required_products(locked_workorder)

        blockers: list[str] = []
        stock_by_product_id: dict[int, StockProduct] = {}

        if required_quantities:
            stock_entries = StockProduct.objects.select_for_update().select_related("product").filter(workshop=locked_workorder.workshop, product_id__in=list(required_quantities.keys()))
            stock_by_product_id = {getattr(entry, "product_id"): entry for entry in stock_entries}
            logger.info(
                "workorder_stock_entries_loaded",
                extra={
                    "workorder_id": locked_workorder.pk,
                    "stock_entries_count": len(stock_by_product_id),
                    "required_product_ids": list(required_quantities.keys()),
                },
            )
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
            logger.warning(
                "workorder_stock_approval_blocked",
                extra={
                    "workorder_id": locked_workorder.pk,
                    "blockers": blockers,
                },
            )
            raise WorkOrderApprovalError(" ".join(blockers))

        if required_quantities:
            for product_id, required_quantity in required_quantities.items():
                stock_entry = stock_by_product_id[product_id]
                logger.info(
                    "workorder_stock_decrementing_product",
                    extra={
                        "workorder_id": locked_workorder.pk,
                        "product_id": product_id,
                        "required_quantity": required_quantity,
                        "previous_quantity": stock_entry.current_quantity,
                    },
                )
                stock_entry.current_quantity -= required_quantity
                stock_entry.save(update_fields=["current_quantity"])

                StockMovement.objects.create(
                    workshop=locked_workorder.workshop,
                    stock_product=stock_entry,
                    workorder=locked_workorder,
                    type=StockMovement.MovementType.EXIT,
                    quantity=required_quantity,
                    status=StockMovement.MovementStatus.APPROVED,
                    transcation_by=user,
                )

                logger.info(
                    "workorder_stock_decremented_product",
                    extra={
                        "workorder_id": locked_workorder.pk,
                        "product_id": product_id,
                        "current_quantity": stock_entry.current_quantity,
                    },
                )
        else:
            logger.info("workorder_stock_approval_no_products_to_decrement", extra={"workorder_id": locked_workorder.pk})

        locked_workorder.approve()
        logger.info("workorder_stock_approval_workorder_approved", extra={"workorder_id": locked_workorder.pk, "status": locked_workorder.status})

        if signature_approved and locked_workorder.signature_request_status != WorkOrderSignatureStatus.APPROVED:
            locked_workorder.signature_request_status = WorkOrderSignatureStatus.APPROVED
            locked_workorder.save(update_fields=["signature_request_status"])
            logger.info("workorder_stock_approval_signature_marked_approved", extra={"workorder_id": locked_workorder.pk})

    workorder.refresh_from_db(fields=["status", "delivered_at", "signature_request_status"])
    logger.info(
        "workorder_stock_approval_finished",
        extra={
            "workorder_id": workorder.pk,
            "status": workorder.status,
            "signature_request_status": workorder.signature_request_status,
        },
    )
