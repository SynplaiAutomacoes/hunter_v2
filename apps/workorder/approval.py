from __future__ import annotations

import logging
from collections import defaultdict

from django.db import transaction

from apps.catalog.product_issues import has_invalid_ncm
from apps.core.infrastructure.kit_prefetch import workorder_kit_overrides_prefetch
from apps.stock.models import StockMovement, StockProduct
from apps.stock.services.workorder_stock import get_consumed_stock_quantities
from apps.workorder.models import WorkOrderItem
from apps.workorder.models import WorkOrder, WorkOrderSignatureStatus


logger = logging.getLogger(__name__)


class WorkOrderApprovalError(Exception):
    pass


def _collect_required_products(workorder: WorkOrder) -> tuple[dict[int, int], dict[int, str], list[str]]:
    required_quantities: defaultdict[int, int] = defaultdict(int)
    product_names: dict[int, str] = {}
    invalid_ncm_products: list[str] = []

    items = list(
        WorkOrderItem.objects.filter(workorder=workorder)
        .select_related("product", "kit")
        .prefetch_related(workorder_kit_overrides_prefetch())
    )

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


def workorder_needs_stock_reconcile(*, workorder: WorkOrder) -> bool:
    """Indica se a O.S. precisa ter o consumo de estoque reconciliado por delta."""
    required_quantities, _, _ = _collect_required_products(workorder)
    consumed_quantities = get_consumed_stock_quantities(workorder=workorder)
    return required_quantities != consumed_quantities


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

        required_quantities, product_names, _ = _collect_required_products(locked_workorder)
        consumed_quantities = get_consumed_stock_quantities(workorder=locked_workorder)

        deltas = {
            product_id: required_quantities.get(product_id, 0) - consumed_quantities.get(product_id, 0)
            for product_id in (set(required_quantities) | set(consumed_quantities))
        }
        to_consume = {product_id: quantity for product_id, quantity in deltas.items() if quantity > 0}
        to_return = {product_id: abs(quantity) for product_id, quantity in deltas.items() if quantity < 0}

        logger.info(
            "workorder_stock_approval_delta_computed",
            extra={
                "workorder_id": locked_workorder.pk,
                "required": required_quantities,
                "consumed": consumed_quantities,
                "to_consume": to_consume,
                "to_return": to_return,
            },
        )

        if to_consume:
            stock_entries = StockProduct.objects.select_for_update().select_related("product").filter(
                workshop=locked_workorder.workshop, product_id__in=list(to_consume.keys())
            )
            stock_by_product_id: dict[int, StockProduct] = {getattr(entry, "product_id"): entry for entry in stock_entries}

            blockers: list[str] = []
            stock_issue_labels: list[str] = []
            ncm_issue_labels: list[str] = []

            for product_id, delta in to_consume.items():
                stock_entry = stock_by_product_id.get(product_id)
                available_quantity = stock_entry.current_quantity if stock_entry is not None else 0
                excess_quantity = max(delta - available_quantity, 0)
                if excess_quantity > 0:
                    product_name = product_names.get(product_id) or (stock_entry.product.name if stock_entry else str(product_id))
                    stock_issue_labels.append(f"{product_name} (+{excess_quantity})")
                elif stock_entry is not None and has_invalid_ncm(stock_entry.product):
                    ncm_issue_labels.append(product_names.get(product_id) or stock_entry.product.name)

            if stock_issue_labels:
                blockers.append(f"Existem pecas com quantidade acima do estoque disponivel: {', '.join(stock_issue_labels)}.")

            if ncm_issue_labels:
                blockers.append(f"Existem produtos com NCM invalido: {', '.join(ncm_issue_labels)}.")

            if blockers:
                logger.warning(
                    "workorder_stock_approval_blocked",
                    extra={
                        "workorder_id": locked_workorder.pk,
                        "blockers": blockers,
                    },
                )
                raise WorkOrderApprovalError(" ".join(blockers))

            for product_id, consume_quantity in to_consume.items():
                stock_entry = stock_by_product_id[product_id]
                logger.info(
                    "workorder_stock_decrementing_product",
                    extra={
                        "workorder_id": locked_workorder.pk,
                        "product_id": product_id,
                        "quantity": consume_quantity,
                        "previous_quantity": stock_entry.current_quantity,
                    },
                )
                stock_entry.current_quantity -= consume_quantity
                stock_entry.save(update_fields=["current_quantity"])

                StockMovement.objects.create(
                    workshop=locked_workorder.workshop,
                    stock_product=stock_entry,
                    workorder=locked_workorder,
                    type=StockMovement.MovementType.EXIT,
                    quantity=consume_quantity,
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
            logger.info("workorder_stock_approval_no_products_to_consume", extra={"workorder_id": locked_workorder.pk})

        if to_return:
            return_stock_entries = StockProduct.objects.select_for_update().select_related("product").filter(
                workshop=locked_workorder.workshop, product_id__in=list(to_return.keys())
            )
            return_stock_by_product_id = {getattr(entry, "product_id"): entry for entry in return_stock_entries}

            for product_id, return_quantity in to_return.items():
                stock_entry = return_stock_by_product_id.get(product_id)
                if stock_entry is None:
                    continue
                logger.info(
                    "workorder_stock_returning_product",
                    extra={
                        "workorder_id": locked_workorder.pk,
                        "product_id": product_id,
                        "quantity": return_quantity,
                        "previous_quantity": stock_entry.current_quantity,
                    },
                )
                stock_entry.current_quantity += return_quantity
                stock_entry.save(update_fields=["current_quantity"])

                StockMovement.objects.create(
                    workshop=locked_workorder.workshop,
                    stock_product=stock_entry,
                    workorder=locked_workorder,
                    type=StockMovement.MovementType.ENTRY,
                    quantity=return_quantity,
                    status=StockMovement.MovementStatus.APPROVED,
                    transcation_by=user,
                    reason="Devolução de excedente por reabertura da O.S.",
                )
        else:
            logger.info("workorder_stock_approval_no_products_to_return", extra={"workorder_id": locked_workorder.pk})

        locked_workorder._skip_stock_consumption_guard = True
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
