from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.finance.models import FiscalDocumentStatus, PurchaseReturnRequest, PurchaseReturnStockStatus
from apps.stock.models import StockMovement, StockProduct


logger = logging.getLogger(__name__)


class PurchaseReturnStockError(ValueError):
    pass


def _mark_stock_error(*, request_id: int, message: str) -> PurchaseReturnRequest:
    PurchaseReturnRequest.objects.filter(pk=request_id).update(
        stock_status=PurchaseReturnStockStatus.ERROR,
        stock_error=message,
        stock_processed_at=None,
        atualizado_em=timezone.now(),
    )
    return PurchaseReturnRequest.objects.get(pk=request_id)


@transaction.atomic
def _apply_authorized_purchase_return_stock(*, request_id: int) -> PurchaseReturnRequest:
    return_request = (
        PurchaseReturnRequest.objects.select_for_update(of=("self",))
        .select_related("fiscal_document", "source_stock_import", "requested_by")
        .get(pk=request_id)
    )
    if return_request.stock_status == PurchaseReturnStockStatus.PROCESSED:
        return return_request
    if return_request.fiscal_document_id is None or return_request.fiscal_document.status != FiscalDocumentStatus.APPROVED:
        return return_request

    return_request.stock_status = PurchaseReturnStockStatus.PENDING
    return_request.stock_error = ""
    return_request.save(update_fields=["stock_status", "stock_error", "atualizado_em"])

    items = list(return_request.items.select_related("source_item__stock_product", "source_item__stock_product__supplier").order_by("pk"))
    if not items:
        raise PurchaseReturnStockError("A devolução autorizada não possui itens para baixa de estoque.")
    missing_products = [item.source_item.description for item in items if item.source_item.stock_product_id is None]
    if missing_products:
        raise PurchaseReturnStockError(f"Produtos sem vínculo com estoque: {', '.join(missing_products)}.")

    product_ids = sorted({item.source_item.stock_product_id for item in items if item.source_item.stock_product_id is not None})
    products = {product.pk: product for product in StockProduct.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")}
    existing_movements = {
        movement.purchase_return_item_id: movement
        for movement in StockMovement.objects.filter(purchase_return_item__request=return_request).select_related("purchase_return_item")
    }
    if existing_movements:
        if len(existing_movements) != len(items) or any(item.pk not in existing_movements for item in items):
            raise PurchaseReturnStockError("A baixa de estoque da devolução está parcialmente processada e exige conferência manual.")
        return_request.stock_status = PurchaseReturnStockStatus.PROCESSED
        return_request.stock_processed_at = return_request.stock_processed_at or timezone.now()
        return_request.stock_error = ""
        return_request.save(update_fields=["stock_status", "stock_processed_at", "stock_error", "atualizado_em"])
        return return_request

    for item in items:
        product = products.get(item.source_item.stock_product_id)
        if product is None or product.workshop_id != return_request.workshop_id:
            raise PurchaseReturnStockError(f"O produto {item.source_item.description} não pertence ao estoque da oficina.")
        quantity = Decimal(item.quantity)
        if quantity <= 0:
            raise PurchaseReturnStockError(f"A quantidade de {item.source_item.description} é inválida para baixa.")
        if product.current_quantity < quantity:
            raise PurchaseReturnStockError(
                f"Saldo insuficiente para {item.source_item.description}: disponível {product.current_quantity}, devolução {quantity}."
            )

    for item in items:
        product = products[item.source_item.stock_product_id]
        quantity = Decimal(item.quantity)
        StockMovement.objects.create(
            workshop=return_request.workshop,
            stock_product=product,
            source_import_item=item.source_item,
            fiscal_document=return_request.fiscal_document,
            purchase_return_item=item,
            type=StockMovement.MovementType.EXIT,
            reason=StockMovement.MovementReason.PURCHASE_RETURN,
            supplier=product.supplier,
            transcation_by=return_request.requested_by,
            quantity=quantity,
            status=StockMovement.MovementStatus.APPROVED,
        )
        product.current_quantity -= quantity
        product.save(update_fields=["current_quantity", "atualizado_em"])

    return_request.stock_status = PurchaseReturnStockStatus.PROCESSED
    return_request.stock_processed_at = timezone.now()
    return_request.stock_error = ""
    return_request.save(update_fields=["stock_status", "stock_processed_at", "stock_error", "atualizado_em"])
    return return_request


def apply_authorized_purchase_return_stock(*, request_instance: PurchaseReturnRequest) -> PurchaseReturnRequest:
    try:
        return _apply_authorized_purchase_return_stock(request_id=request_instance.pk)
    except PurchaseReturnStockError as exc:
        logger.warning("purchase_return_stock_update_failed", extra={"purchase_return_request_id": request_instance.pk, "error": str(exc)})
        return _mark_stock_error(request_id=request_instance.pk, message=str(exc))
    except Exception:
        logger.exception("purchase_return_stock_update_unexpected_error", extra={"purchase_return_request_id": request_instance.pk})
        return _mark_stock_error(request_id=request_instance.pk, message="Não foi possível atualizar o estoque. Tente reconciliar novamente ou solicite uma conferência manual.")
