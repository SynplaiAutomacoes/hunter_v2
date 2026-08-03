from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, QuerySet, Sum
from django.utils import timezone

from apps.core.infrastructure.search import apply_text_search
from apps.core.infrastructure.services.webmania.nfe_emission import ProductEmissionLine
from apps.core.infrastructure.services.webmania.webmania_documents import DownloadedWebmaniaDocument
from apps.finance.models import FiscalDocumentStatus, PurchaseReturnRequest, PurchaseReturnRequestItem, PurchaseReturnRequestStatus
from apps.finance.models.finance import FiscalDocumentOrigin, FiscalDocumentPurpose
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.nfe_returns import NfeReturnError, calculate_available_return_quantities, create_nfe_return_draft, download_nfe_return_preview_document, transmit_nfe_return_document
from apps.stock.models import StockImport, StockImportFiscalItem


class PurchaseReturnError(ValueError):
    pass


def normalize_access_key(value: object) -> str:
    return str(value or "").strip()


def find_purchase_by_access_key(*, workshop: Any, access_key: str) -> StockImport:
    normalized_key = normalize_access_key(access_key)
    if len(normalized_key) != 44 or not normalized_key.isdigit():
        raise PurchaseReturnError("Informe uma chave de acesso válida com 44 dígitos.")

    stock_import = (
        StockImport.objects.filter(workshop=workshop, nf_key=normalized_key)
        .select_related("fiscal_document", "workshop")
        .prefetch_related("fiscal_items__stock_product__product")
        .first()
    )
    if stock_import is None:
        raise PurchaseReturnError("Não encontramos uma NF-e de compra válida para esta chave.")
    document = stock_import.fiscal_document
    snapshot = stock_import.fiscal_snapshot if isinstance(stock_import.fiscal_snapshot, dict) else {}
    document_snapshot = snapshot.get("document") if isinstance(snapshot.get("document"), dict) else {}
    if (
        document is None
        or document.origin != FiscalDocumentOrigin.EXTERNAL
        or document.status != FiscalDocumentStatus.APPROVED
        or stock_import.fiscal_validation_status != StockImport.FiscalValidationStatus.VALIDATED
        or bool(document_snapshot.get("cancelled"))
    ):
        raise PurchaseReturnError("A NF-e de compra não está autorizada ou não pode originar uma devolução.")
    if not stock_import.fiscal_items.exists():
        raise PurchaseReturnError("A NF-e de compra não possui itens fiscais disponíveis para devolução.")
    return stock_import


def find_purchase_by_id(*, workshop: Any, stock_import_id: int) -> StockImport:
    access_key = StockImport.objects.filter(workshop=workshop, pk=stock_import_id).values_list("nf_key", flat=True).first()
    if not access_key:
        raise PurchaseReturnError("Não encontramos a NF-e de compra selecionada.")
    return find_purchase_by_access_key(workshop=workshop, access_key=access_key)


def eligible_purchase_imports(*, workshop: Any) -> QuerySet[StockImport]:
    return (
        StockImport.objects.filter(
            workshop=workshop,
            fiscal_document__origin=FiscalDocumentOrigin.EXTERNAL,
            fiscal_document__status=FiscalDocumentStatus.APPROVED,
            fiscal_validation_status=StockImport.FiscalValidationStatus.VALIDATED,
            fiscal_items__isnull=False,
        )
        .exclude(fiscal_snapshot__document__cancelled=True)
        .select_related("fiscal_document")
        .annotate(purchase_total=Sum("fiscal_items__total_value"), product_count=Count("fiscal_items", distinct=True))
        .order_by("-fiscal_issued_at", "-pk")
        .distinct()
    )


def search_purchase_imports(*, workshop: Any, filters: Mapping[str, Any]) -> QuerySet[StockImport]:
    queryset = eligible_purchase_imports(workshop=workshop)
    supplier = str(filters.get("supplier") or "").strip()
    if supplier:
        queryset = apply_text_search(queryset, search_value=supplier, lookups=("supplier_name",))
    number = str(filters.get("number") or "").strip()
    if number:
        queryset = queryset.filter(nf_number__icontains=number)
    access_key = str(filters.get("access_key") or "").strip()
    if access_key:
        queryset = queryset.filter(nf_key__icontains=access_key)
    issued_from = filters.get("issued_from")
    if issued_from:
        queryset = queryset.filter(fiscal_issued_at__date__gte=issued_from)
    issued_until = filters.get("issued_until")
    if issued_until:
        queryset = queryset.filter(fiscal_issued_at__date__lte=issued_until)
    value_min = filters.get("value_min")
    if value_min is not None:
        queryset = queryset.filter(purchase_total__gte=value_min)
    value_max = filters.get("value_max")
    if value_max is not None:
        queryset = queryset.filter(purchase_total__lte=value_max)
    product = str(filters.get("product") or "").strip()
    if product:
        matching_items = apply_text_search(
            StockImportFiscalItem.objects.filter(stock_import_id=OuterRef("pk")),
            search_value=product,
            lookups=("description", "product_code", "stock_product__product__name"),
        )
        queryset = queryset.annotate(has_matching_product=Exists(matching_items)).filter(has_matching_product=True)
    return queryset


def available_purchase_return_quantities(*, stock_import: StockImport, exclude_request: PurchaseReturnRequest | None = None) -> dict[int, Decimal]:
    if stock_import.fiscal_document_id is None:
        return {}
    available = calculate_available_return_quantities(original_document=stock_import.fiscal_document)
    reservations = PurchaseReturnRequestItem.objects.filter(
        request__source_stock_import=stock_import,
        request__status=PurchaseReturnRequestStatus.READY,
        request__fiscal_document__isnull=True,
    )
    if exclude_request is not None and exclude_request.pk:
        reservations = reservations.exclude(request=exclude_request)
    reserved_by_sequence = {
        row["source_item__sequence"]: row["total"] or Decimal("0")
        for row in reservations.values("source_item__sequence").annotate(total=Sum("quantity"))
    }
    return {sequence: max(Decimal("0"), quantity - reserved_by_sequence.get(sequence, Decimal("0"))) for sequence, quantity in available.items()}


def get_or_create_purchase_return_request(*, stock_import: StockImport, requested_by: Any) -> PurchaseReturnRequest:
    existing = (
        PurchaseReturnRequest.objects.filter(
            workshop=stock_import.workshop,
            source_stock_import=stock_import,
            requested_by=requested_by,
            status=PurchaseReturnRequestStatus.DRAFT,
        )
        .order_by("-pk")
        .first()
    )
    if existing is not None:
        return existing
    return PurchaseReturnRequest.objects.create(
        workshop=stock_import.workshop,
        source_stock_import=stock_import,
        original_document=stock_import.fiscal_document,
        requested_by=requested_by,
    )


def _validated_selection(*, request: PurchaseReturnRequest, quantities: Mapping[int, Decimal]) -> list[tuple[StockImportFiscalItem, Decimal]]:
    source_items = {item.pk: item for item in request.source_stock_import.fiscal_items.all()}
    available = available_purchase_return_quantities(stock_import=request.source_stock_import, exclude_request=request)
    selection: list[tuple[StockImportFiscalItem, Decimal]] = []
    for source_item_id, quantity in quantities.items():
        if quantity <= 0:
            continue
        source_item = source_items.get(source_item_id)
        if source_item is None:
            raise PurchaseReturnError("Um dos produtos selecionados não pertence à NF-e de compra.")
        item_available = available.get(source_item.sequence, Decimal("0"))
        if quantity > item_available:
            raise PurchaseReturnError(f"A quantidade de {source_item.description} excede o saldo disponível de {item_available}.")
        selection.append((source_item, quantity))
    if not selection:
        raise PurchaseReturnError("Selecione ao menos um produto e informe uma quantidade maior que zero.")
    return selection


@transaction.atomic
def save_purchase_return_items(*, request: PurchaseReturnRequest, quantities: Mapping[int, Decimal]) -> PurchaseReturnRequest:
    locked_request = PurchaseReturnRequest.objects.select_for_update(of=("self",)).select_related("source_stock_import__fiscal_document").get(pk=request.pk)
    if locked_request.status != PurchaseReturnRequestStatus.DRAFT:
        raise PurchaseReturnError("A intenção já foi finalizada e não pode mais ser alterada.")
    StockImport.objects.select_for_update().get(pk=locked_request.source_stock_import_id)
    list(PurchaseReturnRequest.objects.select_for_update().filter(source_stock_import=locked_request.source_stock_import, status=PurchaseReturnRequestStatus.READY))
    selection = _validated_selection(request=locked_request, quantities=quantities)
    locked_request.items.all().delete()
    PurchaseReturnRequestItem.objects.bulk_create(
        [PurchaseReturnRequestItem(request=locked_request, source_item=source_item, quantity=quantity, unit_value=source_item.unit_value) for source_item, quantity in selection]
    )
    locked_request.current_step = max(locked_request.current_step, 3)
    locked_request.save(update_fields=["current_step", "atualizado_em"])
    return locked_request


@transaction.atomic
def finalize_purchase_return_request(*, request: PurchaseReturnRequest) -> PurchaseReturnRequest:
    locked_request = PurchaseReturnRequest.objects.select_for_update(of=("self",)).select_related("source_stock_import__fiscal_document").get(pk=request.pk)
    if locked_request.status == PurchaseReturnRequestStatus.READY:
        return locked_request
    StockImport.objects.select_for_update().get(pk=locked_request.source_stock_import_id)
    list(PurchaseReturnRequest.objects.select_for_update().filter(source_stock_import=locked_request.source_stock_import, status=PurchaseReturnRequestStatus.READY))
    quantities = {item.source_item_id: item.quantity for item in locked_request.items.select_related("source_item")}
    _validated_selection(request=locked_request, quantities=quantities)
    locked_request.status = PurchaseReturnRequestStatus.READY
    locked_request.current_step = 4
    locked_request.ready_at = timezone.now()
    locked_request.save(update_fields=["status", "current_step", "ready_at", "atualizado_em"])
    return locked_request


def build_purchase_return_product_lines(*, request: PurchaseReturnRequest) -> list[ProductEmissionLine]:
    lines: list[ProductEmissionLine] = []
    for selected in request.items.select_related("source_item").order_by("source_item__sequence"):
        source = selected.source_item
        snapshot = source.tax_snapshot if isinstance(source.tax_snapshot, dict) else {}
        origin_value = snapshot.get("orig", snapshot.get("origin", 0))
        try:
            origin = int(origin_value)
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
        raise PurchaseReturnError("A devolução não possui produtos selecionados.")
    return lines


def _selected_products(request: PurchaseReturnRequest) -> list[dict[str, Any]]:
    build_purchase_return_product_lines(request=request)
    return [
        {"sequencia": item.source_item.sequence, "quantidade": str(item.quantity)}
        for item in request.items.select_related("source_item").order_by("source_item__sequence")
    ]


def preview_purchase_return(*, request_instance: PurchaseReturnRequest, http_request: Any | None = None) -> DownloadedWebmaniaDocument:
    if request_instance.status != PurchaseReturnRequestStatus.READY:
        raise PurchaseReturnError("Finalize a revisão antes de gerar a prévia fiscal.")
    products = _selected_products(request_instance)
    try:
        return download_nfe_return_preview_document(
            original_document=request_instance.original_document,
            products=products,
            natureza_operacao=request_instance.operation_nature,
            codigo_cfop=request_instance.cfop,
            classe_imposto=request_instance.tax_class,
            informacoes_complementares=request_instance.additional_information,
            request=http_request,
        )
    except NfeReturnError as exc:
        raise PurchaseReturnError(str(exc)) from exc


def _request_status_for_document(request_instance: PurchaseReturnRequest) -> str:
    document = request_instance.fiscal_document
    if document is None:
        return request_instance.status
    status_map: dict[str, str] = {
        str(FiscalDocumentStatus.PROCESSING): str(PurchaseReturnRequestStatus.PROCESSING),
        str(FiscalDocumentStatus.APPROVED): str(PurchaseReturnRequestStatus.AUTHORIZED),
        str(FiscalDocumentStatus.CONTINGENCY): str(PurchaseReturnRequestStatus.CONTINGENCY),
        str(FiscalDocumentStatus.UNCERTAIN): str(PurchaseReturnRequestStatus.UNCERTAIN),
        str(FiscalDocumentStatus.CANCELED): str(PurchaseReturnRequestStatus.CANCELED),
        str(FiscalDocumentStatus.DENIED): str(PurchaseReturnRequestStatus.REJECTED),
    }
    if document.status == FiscalDocumentStatus.REPROVED:
        attempt = document.emission_attempts.order_by("-pk").first()
        return str(PurchaseReturnRequestStatus.COMMUNICATION_ERROR if attempt is not None and not attempt.response_payload else PurchaseReturnRequestStatus.REJECTED)
    return status_map.get(str(document.status), str(request_instance.status))


def sync_purchase_return_status(*, request_instance: PurchaseReturnRequest) -> PurchaseReturnRequest:
    if request_instance.fiscal_document_id is None:
        return request_instance
    request_instance.fiscal_document.refresh_from_db()
    next_status = _request_status_for_document(request_instance)
    if request_instance.status != next_status:
        request_instance.status = next_status
        request_instance.save(update_fields=["status", "atualizado_em"])
    if next_status == PurchaseReturnRequestStatus.AUTHORIZED:
        from apps.stock.services.purchase_return import apply_authorized_purchase_return_stock

        request_instance = apply_authorized_purchase_return_stock(request_instance=request_instance)
    return request_instance


def transmit_purchase_return(*, request_instance: PurchaseReturnRequest, http_request: Any | None = None) -> PurchaseReturnRequest:
    with transaction.atomic():
        locked = (
            PurchaseReturnRequest.objects.select_for_update(of=("self",))
            .select_related("source_stock_import", "original_document", "fiscal_document")
            .get(pk=request_instance.pk)
        )
        if locked.status not in {PurchaseReturnRequestStatus.READY, PurchaseReturnRequestStatus.PROCESSING}:
            if locked.fiscal_document_id:
                return sync_purchase_return_status(request_instance=locked)
            raise PurchaseReturnError("A devolução não está pronta para transmissão.")
        products = _selected_products(locked)
        if locked.fiscal_document_id is None:
            try:
                document = create_nfe_return_draft(
                    original_document=locked.original_document,
                    purpose=FiscalDocumentPurpose.RETURN,
                    products=products,
                    requested_by=locked.requested_by,
                    natureza_operacao=locked.operation_nature,
                    codigo_cfop=locked.cfop,
                    classe_imposto=locked.tax_class,
                    informacoes_complementares=locked.additional_information,
                    request=http_request,
                )
            except NfeReturnError as exc:
                raise PurchaseReturnError(str(exc)) from exc
            locked.fiscal_document = document
            locked.status = PurchaseReturnRequestStatus.PROCESSING
            locked.save(update_fields=["fiscal_document", "status", "atualizado_em"])
            link = document.links_from.get(related_document=locked.original_document)
            link.metadata = sanitize_fiscal_payload(
                {
                    **(link.metadata or {}),
                    "purchase_return_request_id": locked.pk,
                    "source_stock_import_id": locked.source_stock_import_id,
                    "items": [
                        {
                            "source_item_id": item.source_item_id,
                            "sequence": item.source_item.sequence,
                            "quantity": str(item.quantity),
                            "tax_snapshot": item.source_item.tax_snapshot,
                        }
                        for item in locked.items.select_related("source_item").order_by("source_item__sequence")
                    ],
                }
            )
            link.save(update_fields=["metadata", "atualizado_em"])
        else:
            document = locked.fiscal_document
            if document.emission_attempts.exists():
                return sync_purchase_return_status(request_instance=locked)

    try:
        transmit_nfe_return_document(document=document)
    except NfeReturnError as exc:
        sync_purchase_return_status(request_instance=locked)
        raise PurchaseReturnError(str(exc)) from exc
    return sync_purchase_return_status(request_instance=locked)
