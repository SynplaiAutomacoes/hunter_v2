from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.finance.models import FiscalDocumentStatus, TransportRequest, TransportStockStatus
from apps.stock.models import StockMovement, StockProduct


logger = logging.getLogger(__name__)


class TransportStockError(ValueError):
    pass


def _mark_stock_error(*, request_id: int, message: str) -> TransportRequest:
    TransportRequest.objects.filter(pk=request_id).update(
        stock_status=TransportStockStatus.ERROR,
        stock_error=message,
        stock_processed_at=None,
        atualizado_em=timezone.now(),
    )
    return TransportRequest.objects.get(pk=request_id)


@transaction.atomic
def _apply_authorized_transport_stock(*, request_id: int) -> TransportRequest:
    transport_request = (
        TransportRequest.objects.select_for_update(of=("self",))
        .select_related("fiscal_document", "source_stock_import", "requested_by", "supplier")
        .get(pk=request_id)
    )
    if transport_request.stock_status == TransportStockStatus.PROCESSED:
        return transport_request
    if transport_request.fiscal_document_id is None or transport_request.fiscal_document.status != FiscalDocumentStatus.APPROVED:
        return transport_request

    transport_request.stock_status = TransportStockStatus.PENDING
    transport_request.stock_error = ""
    transport_request.save(update_fields=["stock_status", "stock_error", "atualizado_em"])
    items = list(transport_request.items.select_related("source_item__stock_product").order_by("pk"))
    if not items:
        raise TransportStockError("A Nota de Transporte autorizada não possui itens para baixa de estoque.")
    missing_products = [item.source_item.description for item in items if item.source_item.stock_product_id is None]
    if missing_products:
        raise TransportStockError(f"Produtos sem vínculo com estoque: {', '.join(missing_products)}.")

    product_ids = sorted({item.source_item.stock_product_id for item in items if item.source_item.stock_product_id is not None})
    products = {product.pk: product for product in StockProduct.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")}
    existing_movements = {
        movement.transport_item_id: movement
        for movement in StockMovement.objects.filter(transport_item__request=transport_request).select_related("transport_item")
    }
    if existing_movements:
        if len(existing_movements) != len(items) or any(item.pk not in existing_movements for item in items):
            raise TransportStockError("A baixa de estoque da Nota de Transporte está parcialmente processada e exige conferência manual.")
        transport_request.stock_status = TransportStockStatus.PROCESSED
        transport_request.stock_processed_at = transport_request.stock_processed_at or timezone.now()
        transport_request.stock_error = ""
        transport_request.save(update_fields=["stock_status", "stock_processed_at", "stock_error", "atualizado_em"])
        return transport_request

    quantities_by_product: dict[int, Decimal] = {}
    for item in items:
        product = products.get(item.source_item.stock_product_id)
        if product is None or product.workshop_id != transport_request.workshop_id:
            raise TransportStockError(f"O produto {item.source_item.description} não pertence ao estoque da oficina.")
        quantity = Decimal(item.quantity)
        if quantity <= 0:
            raise TransportStockError(f"A quantidade de {item.source_item.description} é inválida para baixa.")
        quantities_by_product[product.pk] = quantities_by_product.get(product.pk, Decimal("0")) + quantity

    for product_id, total_quantity in quantities_by_product.items():
        product = products[product_id]
        if product.current_quantity < total_quantity:
            raise TransportStockError(f"Saldo insuficiente para {product.product.name}: disponível {product.current_quantity}, transporte {total_quantity}.")

    for item in items:
        product = products[item.source_item.stock_product_id]
        quantity = Decimal(item.quantity)
        StockMovement.objects.create(
            workshop=transport_request.workshop,
            stock_product=product,
            source_import_item=item.source_item,
            fiscal_document=transport_request.fiscal_document,
            transport_item=item,
            type=StockMovement.MovementType.EXIT,
            reason=StockMovement.MovementReason.TRANSPORT,
            supplier=transport_request.supplier,
            transcation_by=transport_request.requested_by,
            quantity=quantity,
            status=StockMovement.MovementStatus.APPROVED,
        )
        product.current_quantity -= quantity
        product.save(update_fields=["current_quantity", "atualizado_em"])

    transport_request.stock_status = TransportStockStatus.PROCESSED
    transport_request.stock_processed_at = timezone.now()
    transport_request.stock_error = ""
    transport_request.save(update_fields=["stock_status", "stock_processed_at", "stock_error", "atualizado_em"])
    return transport_request


def apply_authorized_transport_stock(*, request_instance: TransportRequest) -> TransportRequest:
    try:
        return _apply_authorized_transport_stock(request_id=request_instance.pk)
    except TransportStockError as exc:
        logger.warning("transport_stock_update_failed", extra={"transport_request_id": request_instance.pk, "error": str(exc)})
        return _mark_stock_error(request_id=request_instance.pk, message=str(exc))
    except Exception:
        logger.exception("transport_stock_update_unexpected_error", extra={"transport_request_id": request_instance.pk})
        return _mark_stock_error(request_id=request_instance.pk, message="Não foi possível atualizar o estoque. Tente reconciliar novamente ou solicite uma conferência manual.")
