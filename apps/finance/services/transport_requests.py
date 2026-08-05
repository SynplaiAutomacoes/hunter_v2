from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Q, QuerySet, Sum
from django.utils import timezone

from apps.core.infrastructure.services.webmania.nfe_emission import (
    NfeEmissionError,
    NfeEmissionUncertainError,
    ProductEmissionLine,
    build_normal_nfe_payload_from_lines,
    download_normal_nfe_preview_payload,
    send_normal_nfe_payload,
    validate_normal_nfe_tax_class,
)
from apps.core.infrastructure.services.webmania.nfe_consulta import NfeConsultaError, consult_nfe_document
from apps.core.infrastructure.services.webmania.webmania_documents import DownloadedWebmaniaDocument
from apps.finance.models import TransportRequest, TransportRequestItem, TransportRequestStatus
from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentLink,
    FiscalDocumentLinkRole,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalEmissionAttemptStatus,
    FiscalEmissionDocumentKind,
    FiscalEmissionOperationType,
)
from apps.finance.services.fiscal_attempts import (
    FiscalEmissionAttemptBlocked,
    begin_emission_attempt,
    build_fiscal_document_operation_idempotency_key,
    build_payload_hash,
    mark_attempt_failed,
    mark_attempt_sent,
    mark_attempt_succeeded,
    mark_attempt_uncertain,
    sanitize_fiscal_payload,
)
from apps.finance.services.purchase_returns import PurchaseReturnError, find_purchase_by_id
from apps.stock.models import StockImport, StockImportFiscalItem, StockProduct
from apps.suppliers.models import Supplier


class TransportRequestError(ValueError):
    pass


RESERVING_TRANSPORT_STATUSES = {
    TransportRequestStatus.READY,
    TransportRequestStatus.PROCESSING,
    TransportRequestStatus.AUTHORIZED,
    TransportRequestStatus.CONTINGENCY,
    TransportRequestStatus.UNCERTAIN,
}
PENDING_STOCK_TRANSPORT_STATUSES = RESERVING_TRANSPORT_STATUSES - {TransportRequestStatus.AUTHORIZED}


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _supplier_for_import(stock_import: StockImport) -> Supplier | None:
    document = _digits(stock_import.supplier_cnpj)
    if not document:
        return None
    return next((supplier for supplier in Supplier.objects.filter(workshop=stock_import.workshop, is_active=True) if _digits(supplier.cnpj) == document), None)


def select_transport_source(*, workshop: Any, stock_import_id: int, requested_by: Any) -> TransportRequest:
    try:
        stock_import = find_purchase_by_id(workshop=workshop, stock_import_id=stock_import_id, requested_by=requested_by)
    except PurchaseReturnError as exc:
        raise TransportRequestError(str(exc).replace("devolução", "transporte")) from exc
    existing = (
        TransportRequest.objects.filter(
            workshop=workshop,
            source_stock_import=stock_import,
            requested_by=requested_by,
            status=TransportRequestStatus.DRAFT,
        )
        .order_by("-pk")
        .first()
    )
    if existing is not None:
        return existing
    return TransportRequest.objects.create(
        workshop=workshop,
        source_stock_import=stock_import,
        original_document=stock_import.fiscal_document,
        supplier=_supplier_for_import(stock_import),
        requested_by=requested_by,
    )


def available_transport_quantities(*, stock_import: StockImport, exclude_request: TransportRequest | None = None) -> dict[int, Decimal]:
    source_items = list(stock_import.fiscal_items.select_related("stock_product"))
    reservations = TransportRequestItem.objects.filter(
        request__source_stock_import=stock_import,
        request__status__in=RESERVING_TRANSPORT_STATUSES,
    )
    if exclude_request is not None and exclude_request.pk:
        reservations = reservations.exclude(request=exclude_request)
    source_reserved = {
        row["source_item_id"]: row["total"] or Decimal("0")
        for row in reservations.values("source_item_id").annotate(total=Sum("quantity"))
    }

    pending = TransportRequestItem.objects.filter(
        source_item__stock_product__isnull=False,
        request__workshop=stock_import.workshop,
        request__status__in=PENDING_STOCK_TRANSPORT_STATUSES,
    )
    if exclude_request is not None and exclude_request.pk:
        pending = pending.exclude(request=exclude_request)
    product_pending = {
        row["source_item__stock_product_id"]: row["total"] or Decimal("0")
        for row in pending.values("source_item__stock_product_id").annotate(total=Sum("quantity"))
    }

    available: dict[int, Decimal] = {}
    for item in source_items:
        source_balance = max(Decimal("0"), item.quantity - source_reserved.get(item.pk, Decimal("0")))
        if item.stock_product_id is None:
            available[item.pk] = Decimal("0")
            continue
        physical_balance = max(
            Decimal("0"),
            item.stock_product.current_quantity - product_pending.get(item.stock_product_id, Decimal("0")),
        )
        available[item.pk] = min(source_balance, physical_balance)
    return available


def _validated_selection(*, request: TransportRequest, quantities: Mapping[int, Decimal]) -> list[tuple[StockImportFiscalItem, Decimal]]:
    source_items = {item.pk: item for item in request.source_stock_import.fiscal_items.select_related("stock_product")}
    available = available_transport_quantities(stock_import=request.source_stock_import, exclude_request=request)
    selection: list[tuple[StockImportFiscalItem, Decimal]] = []
    requested_by_product: dict[int, Decimal] = {}
    for source_item_id, quantity in quantities.items():
        if quantity <= 0:
            continue
        source_item = source_items.get(source_item_id)
        if source_item is None:
            raise TransportRequestError("Um dos produtos selecionados não pertence à NF-e de entrada.")
        if source_item.stock_product_id is None:
            raise TransportRequestError(f"O produto {source_item.description} não possui vínculo com o estoque.")
        item_available = available.get(source_item_id, Decimal("0"))
        if quantity > item_available:
            raise TransportRequestError(f"A quantidade de {source_item.description} excede o estoque disponível de {item_available}.")
        selection.append((source_item, quantity))
        assert source_item.stock_product_id is not None
        requested_by_product[source_item.stock_product_id] = requested_by_product.get(source_item.stock_product_id, Decimal("0")) + quantity
    if not selection:
        raise TransportRequestError("Selecione ao menos um produto e informe uma quantidade maior que zero.")
    pending = TransportRequestItem.objects.filter(
        source_item__stock_product_id__in=requested_by_product,
        request__workshop=request.workshop,
        request__status__in=PENDING_STOCK_TRANSPORT_STATUSES,
    )
    if request.pk:
        pending = pending.exclude(request=request)
    product_pending = {
        row["source_item__stock_product_id"]: row["total"] or Decimal("0")
        for row in pending.values("source_item__stock_product_id").annotate(total=Sum("quantity"))
    }
    for stock_product_id, total_requested in requested_by_product.items():
        same_product_items = [item for item, _quantity in selection if item.stock_product_id == stock_product_id]
        physical_available = max(Decimal("0"), same_product_items[0].stock_product.current_quantity - product_pending.get(stock_product_id, Decimal("0")))
        if total_requested > physical_available:
            product_name = same_product_items[0].stock_product.product.name
            raise TransportRequestError(f"A soma das quantidades de {product_name} excede o estoque físico disponível de {physical_available}.")
    return selection


@transaction.atomic
def save_transport_items(*, request: TransportRequest, quantities: Mapping[int, Decimal]) -> TransportRequest:
    locked = TransportRequest.objects.select_for_update(of=("self",)).select_related("source_stock_import").get(pk=request.pk)
    if locked.status != TransportRequestStatus.DRAFT:
        raise TransportRequestError("A intenção já foi finalizada e não pode mais ser alterada.")
    StockImport.objects.select_for_update().get(pk=locked.source_stock_import_id)
    list(TransportRequest.objects.select_for_update().filter(workshop=locked.workshop, status__in=RESERVING_TRANSPORT_STATUSES))
    selection = _validated_selection(request=locked, quantities=quantities)
    locked.items.all().delete()
    TransportRequestItem.objects.bulk_create(
        [TransportRequestItem(request=locked, source_item=item, quantity=quantity, unit_value=item.unit_value) for item, quantity in selection]
    )
    locked.current_step = max(locked.current_step, 3)
    locked.save(update_fields=["current_step", "atualizado_em"])
    return locked


@transaction.atomic
def save_transport_data(*, request: TransportRequest, freight_mode: int, transport_snapshot: dict[str, Any], additional_information: str = "") -> TransportRequest:
    locked = TransportRequest.objects.select_for_update(of=("self",)).get(pk=request.pk)
    if locked.status != TransportRequestStatus.DRAFT:
        raise TransportRequestError("A intenção já foi finalizada e não pode mais ser alterada.")
    locked.freight_mode = freight_mode
    locked.transport_snapshot = transport_snapshot
    locked.additional_information = str(additional_information or "").strip()
    locked.current_step = max(locked.current_step, 4)
    locked.save(update_fields=["freight_mode", "transport_snapshot", "additional_information", "current_step", "atualizado_em"])
    return locked


@transaction.atomic
def finalize_transport_request(
    *,
    request: TransportRequest,
    operation_nature: str,
    cfop: str,
    tax_class: str,
) -> TransportRequest:
    locked = TransportRequest.objects.select_for_update(of=("self",)).select_related("source_stock_import").get(pk=request.pk)
    if locked.status == TransportRequestStatus.READY:
        return locked
    StockImport.objects.select_for_update().get(pk=locked.source_stock_import_id)
    list(TransportRequest.objects.select_for_update().filter(workshop=locked.workshop, status__in=RESERVING_TRANSPORT_STATUSES))
    _validated_selection(request=locked, quantities={item.source_item_id: item.quantity for item in locked.items.all()})
    if locked.supplier_id is None:
        raise TransportRequestError("Cadastre o fornecedor da NF-e de entrada com CPF/CNPJ e endereço completos antes de emitir a Nota de Transporte.")
    if len(str(cfop or "").strip()) != 4 or not str(cfop).strip().isdigit():
        raise TransportRequestError("Informe um CFOP válido com 4 dígitos.")
    if not str(tax_class or "").strip():
        raise TransportRequestError("Selecione uma classe de imposto para a Nota de Transporte.")
    locked.operation_nature = str(operation_nature or "Remessa para transporte").strip()
    locked.cfop = str(cfop).strip()
    locked.tax_class = str(tax_class).strip()
    locked.status = TransportRequestStatus.READY
    locked.current_step = 5
    locked.ready_at = timezone.now()
    locked.save(update_fields=["operation_nature", "cfop", "tax_class", "status", "current_step", "ready_at", "atualizado_em"])
    return locked


def build_transport_product_lines(*, request: TransportRequest) -> list[ProductEmissionLine]:
    lines: list[ProductEmissionLine] = []
    for selected in request.items.select_related("source_item").order_by("source_item__sequence"):
        source = selected.source_item
        snapshot = source.tax_snapshot if isinstance(source.tax_snapshot, dict) else {}
        try:
            origin = int(snapshot.get("orig", snapshot.get("origin", 0)))
        except (TypeError, ValueError):
            origin = 0
        lines.append(
            ProductEmissionLine(
                description=source.description,
                code=source.product_code or str(source.pk),
                ncm=source.ncm,
                cest=str(snapshot.get("cest") or ""),
                unit=source.unit or "UN",
                origin=origin,
                quantity=selected.quantity,
                base_total=selected.total_value,
            )
        )
    if not lines:
        raise TransportRequestError("A Nota de Transporte não possui produtos selecionados.")
    return lines


def build_transport_payload(*, request_instance: TransportRequest, http_request: Any | None = None) -> dict[str, Any]:
    if request_instance.supplier_id is None:
        raise TransportRequestError("Cadastre o fornecedor da NF-e de entrada antes de emitir a Nota de Transporte.")
    try:
        return build_normal_nfe_payload_from_lines(
            workshop=request_instance.workshop,
            request_id=request_instance.pk,
            recipient=request_instance.supplier,
            lines=build_transport_product_lines(request=request_instance),
            operation_nature=request_instance.operation_nature,
            cfop=request_instance.cfop,
            tax_class=request_instance.tax_class,
            freight_mode=request_instance.freight_mode,
            transport_snapshot=request_instance.transport_snapshot,
            reference_access_key=request_instance.original_document.access_key,
            additional_information=request_instance.additional_information,
            request=http_request,
        )
    except NfeEmissionError as exc:
        raise TransportRequestError(str(exc)) from exc


def preview_transport(*, request_instance: TransportRequest, http_request: Any | None = None) -> DownloadedWebmaniaDocument:
    if request_instance.status != TransportRequestStatus.READY:
        raise TransportRequestError("Finalize a revisão antes de gerar a prévia fiscal.")
    payload = build_transport_payload(request_instance=request_instance, http_request=http_request)
    try:
        validate_normal_nfe_tax_class(workshop=request_instance.workshop, tax_class=request_instance.tax_class)
        return download_normal_nfe_preview_payload(workshop=request_instance.workshop, payload=payload)
    except NfeEmissionError as exc:
        raise TransportRequestError(str(exc)) from exc


def _document_status(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip().lower()
    if status in {"processando", "processing", "started", "sent"}:
        return FiscalDocumentStatus.PROCESSING
    if status in {"uncertain", "incerto"}:
        return FiscalDocumentStatus.UNCERTAIN
    if status in {"aprovado", "autorizado", "succeeded"}:
        return FiscalDocumentStatus.APPROVED
    if status in {"denegado", "denied"}:
        return FiscalDocumentStatus.DENIED
    if status in {"cancelado", "canceled"}:
        return FiscalDocumentStatus.CANCELED
    if status in {"reprovado", "rejeitado", "erro", "error", "failed"}:
        return FiscalDocumentStatus.REPROVED
    if status in {"contingencia", "contingency"}:
        return FiscalDocumentStatus.CONTINGENCY
    return FiscalDocumentStatus.APPROVED if payload.get("uuid") or payload.get("chave") else FiscalDocumentStatus.PROCESSING


def apply_transport_document_payload(*, document: FiscalDocument, response_payload: dict[str, Any]) -> FiscalDocument:
    document.response_payload = sanitize_fiscal_payload(response_payload)
    document.status = _document_status(response_payload)
    document.remote_status = str(response_payload.get("status") or document.remote_status or "").strip()
    document.remote_uuid = str(response_payload.get("uuid") or document.remote_uuid or "").strip()
    document.access_key = str(response_payload.get("chave") or document.access_key or "").strip()
    document.number = str(response_payload.get("nfe") or response_payload.get("numero") or document.number or "").strip()
    document.series = str(response_payload.get("serie") or document.series or "").strip()
    document.receipt = str(response_payload.get("recibo") or document.receipt or "").strip()
    document.xml_url = str(response_payload.get("xml") or document.xml_url or "").strip()
    document.danfe_url = str(response_payload.get("danfe") or document.danfe_url or "").strip()
    document.save(update_fields=["response_payload", "status", "remote_status", "remote_uuid", "access_key", "number", "series", "receipt", "xml_url", "danfe_url", "atualizado_em"])
    return document


def _request_status_for_document(document: FiscalDocument) -> str:
    status_map = {
        FiscalDocumentStatus.PROCESSING: TransportRequestStatus.PROCESSING,
        FiscalDocumentStatus.APPROVED: TransportRequestStatus.AUTHORIZED,
        FiscalDocumentStatus.CONTINGENCY: TransportRequestStatus.CONTINGENCY,
        FiscalDocumentStatus.UNCERTAIN: TransportRequestStatus.UNCERTAIN,
        FiscalDocumentStatus.CANCELED: TransportRequestStatus.CANCELED,
        FiscalDocumentStatus.DENIED: TransportRequestStatus.REJECTED,
        FiscalDocumentStatus.REPROVED: TransportRequestStatus.REJECTED,
    }
    if document.status == FiscalDocumentStatus.REPROVED:
        attempt = document.emission_attempts.order_by("-pk").first()
        if attempt is not None and not attempt.response_payload:
            return str(TransportRequestStatus.COMMUNICATION_ERROR)
    return str(status_map.get(document.status, TransportRequestStatus.PROCESSING))


def sync_transport_status(*, request_instance: TransportRequest) -> TransportRequest:
    if request_instance.fiscal_document_id is None:
        return request_instance
    request_instance.fiscal_document.refresh_from_db()
    next_status = _request_status_for_document(request_instance.fiscal_document)
    if request_instance.status != next_status:
        request_instance.status = next_status
        request_instance.save(update_fields=["status", "atualizado_em"])
    if next_status == TransportRequestStatus.AUTHORIZED:
        from apps.stock.services.transport import apply_authorized_transport_stock

        request_instance = apply_authorized_transport_stock(request_instance=request_instance)
    return request_instance


def transmit_transport(*, request_instance: TransportRequest, http_request: Any | None = None) -> TransportRequest:
    with transaction.atomic():
        locked = (
            TransportRequest.objects.select_for_update(of=("self",))
            .select_related("workshop", "supplier", "original_document", "fiscal_document", "source_stock_import")
            .get(pk=request_instance.pk)
        )
        if locked.status not in {TransportRequestStatus.READY, TransportRequestStatus.PROCESSING}:
            if locked.fiscal_document_id:
                return sync_transport_status(request_instance=locked)
            raise TransportRequestError("A Nota de Transporte não está pronta para transmissão.")
        if locked.fiscal_document_id is None:
            StockImport.objects.select_for_update().get(pk=locked.source_stock_import_id)
            product_ids = list(locked.items.filter(source_item__stock_product__isnull=False).values_list("source_item__stock_product_id", flat=True))
            list(StockProduct.objects.select_for_update().filter(pk__in=product_ids).order_by("pk"))
            _validated_selection(request=locked, quantities={item.source_item_id: item.quantity for item in locked.items.all()})
        payload = build_transport_payload(request_instance=locked, http_request=http_request)
        if locked.fiscal_document_id is None:
            document = FiscalDocument.objects.create(
                workshop=locked.workshop,
                account=getattr(locked.workshop, "account", None),
                document_type=FiscalDocumentType.NFE,
                origin=FiscalDocumentOrigin.DERIVED,
                purpose=FiscalDocumentPurpose.NORMAL,
                environment=str(payload["ambiente"]),
                status=FiscalDocumentStatus.PROCESSING,
                remote_status=FiscalEmissionAttemptStatus.STARTED,
                request_payload=sanitize_fiscal_payload(payload),
                requested_by=locked.requested_by,
            )
            FiscalDocumentLink.objects.create(
                document=document,
                related_document=locked.original_document,
                role=FiscalDocumentLinkRole.TRANSPORTS,
                metadata=sanitize_fiscal_payload(
                    {
                        "transport_request_id": locked.pk,
                        "source_stock_import_id": locked.source_stock_import_id,
                        "items": [
                            {"source_item_id": item.source_item_id, "sequence": item.source_item.sequence, "quantity": str(item.quantity), "tax_snapshot": item.source_item.tax_snapshot}
                            for item in locked.items.select_related("source_item").order_by("source_item__sequence")
                        ],
                    }
                ),
            )
            locked.fiscal_document = document
            locked.status = TransportRequestStatus.PROCESSING
            locked.save(update_fields=["fiscal_document", "status", "atualizado_em"])
        else:
            document = locked.fiscal_document
            if document.emission_attempts.exists():
                return sync_transport_status(request_instance=locked)
        idempotency_key = build_fiscal_document_operation_idempotency_key(
            workshop_id=locked.workshop_id,
            derived_document_id=document.pk,
            operation_type=FiscalEmissionOperationType.TRANSPORT,
        )
        try:
            attempt = begin_emission_attempt(
                workshop=locked.workshop,
                document_kind=FiscalEmissionDocumentKind.NFE,
                operation_type=FiscalEmissionOperationType.TRANSPORT,
                request_model=TransportRequest.__name__,
                request_id=locked.pk,
                fiscal_document=document,
                idempotency_key=idempotency_key,
                request_payload=payload,
                payload_hash=build_payload_hash(payload),
            )
        except FiscalEmissionAttemptBlocked as exc:
            raise TransportRequestError(str(exc)) from exc

    try:
        validate_normal_nfe_tax_class(workshop=locked.workshop, tax_class=locked.tax_class)
        mark_attempt_sent(attempt=attempt)
        response_payload = send_normal_nfe_payload(workshop=locked.workshop, payload=payload)
    except NfeEmissionUncertainError as exc:
        mark_attempt_uncertain(attempt=attempt, error_message=str(exc))
        document.status = FiscalDocumentStatus.UNCERTAIN
        document.remote_status = FiscalEmissionAttemptStatus.UNCERTAIN
        document.response_payload = {"error": str(exc)}
        document.save(update_fields=["status", "remote_status", "response_payload", "atualizado_em"])
        sync_transport_status(request_instance=locked)
        raise TransportRequestError(str(exc)) from exc
    except NfeEmissionError as exc:
        mark_attempt_failed(attempt=attempt, error_message=str(exc))
        document.status = FiscalDocumentStatus.REPROVED
        document.response_payload = {"error": str(exc)}
        document.save(update_fields=["status", "response_payload", "atualizado_em"])
        sync_transport_status(request_instance=locked)
        raise TransportRequestError(str(exc)) from exc

    document = apply_transport_document_payload(document=document, response_payload=response_payload)
    if document.status in {FiscalDocumentStatus.REPROVED, FiscalDocumentStatus.DENIED}:
        message = str(response_payload.get("error") or response_payload.get("message") or "Nota de Transporte rejeitada.")
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        sync_transport_status(request_instance=locked)
        raise TransportRequestError(message)
    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    return sync_transport_status(request_instance=locked)


def confirm_transport_document_from_payload(*, document: FiscalDocument, response_payload: dict[str, Any]) -> FiscalDocument:
    validate_transport_payload_identity(document=document, payload=response_payload)
    document = apply_transport_document_payload(document=document, response_payload=response_payload)
    attempt = document.emission_attempts.filter(operation_type=FiscalEmissionOperationType.TRANSPORT).order_by("-pk").first()
    if attempt is not None:
        if document.status == FiscalDocumentStatus.APPROVED:
            mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
        elif document.status in {FiscalDocumentStatus.REPROVED, FiscalDocumentStatus.DENIED}:
            mark_attempt_failed(attempt=attempt, error_message="Nota de Transporte rejeitada.", response_payload=response_payload)
    if hasattr(document, "transport_request"):
        sync_transport_status(request_instance=document.transport_request)
    return document


def validate_transport_payload_identity(*, document: FiscalDocument, payload: dict[str, Any]) -> None:
    model = str(payload.get("modelo") or payload.get("model") or "").strip().lower()
    if model and model != "nfe":
        raise TransportRequestError("A resposta remota não pertence a uma NF-e de transporte.")
    payload_uuid = str(payload.get("uuid") or "").strip()
    payload_key = str(payload.get("chave") or "").strip()
    remote_id = str(payload.get("ID") or payload.get("id") or "").strip()
    if payload_uuid:
        try:
            UUID(payload_uuid)
        except ValueError as exc:
            raise TransportRequestError("A resposta remota possui UUID inválido para a Nota de Transporte.") from exc
    if payload_key and (len(payload_key) != 44 or not payload_key.isdigit()):
        raise TransportRequestError("A resposta remota possui chave inválida para a Nota de Transporte.")
    if document.remote_uuid and payload_uuid != document.remote_uuid:
        raise TransportRequestError("A resposta remota pertence a uma Nota de Transporte diferente.")
    if document.access_key and payload_key != document.access_key:
        raise TransportRequestError("A resposta remota pertence a uma Nota de Transporte diferente.")
    if not document.remote_uuid and not document.access_key:
        expected_id = f"transport-{document.transport_request.pk}"
        if remote_id != expected_id:
            raise TransportRequestError("A resposta remota não possui identificador seguro da intenção de transporte.")


def reconcile_transport_document(*, document: FiscalDocument) -> FiscalDocument:
    attempt = document.emission_attempts.filter(operation_type=FiscalEmissionOperationType.TRANSPORT).order_by("-pk").first()
    remote_uuid = str(document.remote_uuid or (attempt.remote_uuid if attempt else "") or "").strip()
    access_key = str(document.access_key or (attempt.remote_key if attempt else "") or "").strip()
    try:
        payload = consult_nfe_document(workshop=document.workshop, remote_uuid=remote_uuid, access_key=access_key)
    except NfeConsultaError as exc:
        raise TransportRequestError(str(exc)) from exc
    payload_uuid = str(payload.get("uuid") or "").strip()
    payload_key = str(payload.get("chave") or "").strip()
    if remote_uuid and payload_uuid != remote_uuid:
        raise TransportRequestError("A consulta retornou uma NF-e diferente da Nota de Transporte esperada.")
    if not remote_uuid and access_key and payload_key != access_key:
        raise TransportRequestError("A consulta retornou uma chave diferente da Nota de Transporte esperada.")
    return confirm_transport_document_from_payload(document=document, response_payload=payload)


def _transport_webhook_queryset(payload: dict[str, Any]) -> QuerySet[FiscalDocument]:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    remote_id = str(payload.get("ID") or payload.get("id") or "").strip()
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(access_key=access_key) | Q(emission_attempts__remote_key=access_key)
    if remote_id.startswith("transport-") and remote_id.removeprefix("transport-").isdigit():
        filters |= Q(transport_request__pk=int(remote_id.removeprefix("transport-")))
    if not filters:
        return FiscalDocument.objects.none()
    return FiscalDocument.objects.filter(transport_request__isnull=False).filter(filters).distinct()


def resolve_transport_document_for_webhook(*, payload: dict[str, Any]) -> FiscalDocument | None:
    matches = list(_transport_webhook_queryset(payload).order_by("-pk")[:2])
    return matches[0] if len(matches) == 1 else None


def is_ambiguous_transport_webhook(*, payload: dict[str, Any]) -> bool:
    return _transport_webhook_queryset(payload).values("pk")[:2].count() > 1
