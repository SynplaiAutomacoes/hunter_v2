from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.infrastructure.search import apply_text_search
from apps.core.text_normalization import normalize_search_text
from apps.core.infrastructure.services.webmania.nfe_emission import ProductEmissionLine
from apps.core.infrastructure.services.webmania.webmania_documents import DownloadedWebmaniaDocument
from apps.finance.models import FiscalDocumentStatus, PurchaseReturnItemKind, PurchaseReturnRequest, PurchaseReturnRequestItem, PurchaseReturnRequestStatus
from apps.finance.models.finance import FiscalDocumentOrigin, FiscalDocumentPurpose, FiscalDocumentType
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.nfe_returns import NfeReturnError, calculate_available_return_quantities, create_nfe_return_draft, download_nfe_return_preview_document, transmit_nfe_return_document
from apps.stock.models import StockImport, StockImportFiscalItem
from apps.stock.services.purchase_fiscal import PurchaseNfeValidationError, ensure_legacy_purchase_fiscal_foundation


class PurchaseReturnError(ValueError):
    pass


def normalize_access_key(value: object) -> str:
    return str(value or "").strip()


def legacy_purchase_summary(stock_import: StockImport) -> tuple[Decimal, int]:
    items = stock_import.items_data if isinstance(stock_import.items_data, list) else []
    total = Decimal("0")
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            quantity = Decimal(str(item.get("qtd") or "0"))
            unit_value = Decimal(str(item.get("valor") or "0"))
            item_total = Decimal(str(item.get("valor_total") or quantity * unit_value))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if quantity <= 0:
            continue
        total += item_total
        count += 1
    return total, count


def _is_legacy_purchase(stock_import: StockImport) -> bool:
    return (
        stock_import.fiscal_document_id is None
        and stock_import.method in {StockImport.ImportMethods.XML, StockImport.ImportMethods.KEY, StockImport.ImportMethods.SEFAZ}
        and stock_import.status == StockImport.ImportStatus.COMPLETED
        and len(normalize_access_key(stock_import.nf_key)) == 44
        and _has_legacy_stock_entry_items(stock_import)
    )


def _has_legacy_stock_entry_items(stock_import: StockImport) -> bool:
    items = stock_import.items_data if isinstance(stock_import.items_data, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            quantity = Decimal(str(item.get("qtd") or "0"))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if quantity <= 0:
            continue
        if item.get("linked_product_id"):
            return True
    return False


def _validate_stock_purchase_document(*, stock_import: StockImport) -> None:
    document = stock_import.fiscal_document
    snapshot = stock_import.fiscal_snapshot if isinstance(stock_import.fiscal_snapshot, dict) else {}
    document_snapshot = snapshot.get("document") if isinstance(snapshot.get("document"), dict) else {}
    if (
        stock_import.status != StockImport.ImportStatus.COMPLETED
        or document is None
        or document.document_type != FiscalDocumentType.NFE
        or document.origin != FiscalDocumentOrigin.EXTERNAL
        or document.purpose != FiscalDocumentPurpose.NORMAL
        or document.status != FiscalDocumentStatus.APPROVED
        or document.legacy_nfe_item_id is not None
        or bool(document_snapshot.get("cancelled"))
    ):
        raise PurchaseReturnError("A NF-e de compra não está autorizada ou não pode originar uma devolução.")
    if not stock_import.fiscal_items.filter(stock_product__isnull=False).exists():
        raise PurchaseReturnError("A NF-e de compra não possui itens de estoque disponíveis para devolução.")


def find_purchase_by_access_key(*, workshop: Any, access_key: str, requested_by: Any | None = None) -> StockImport:
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
    if _is_legacy_purchase(stock_import):
        try:
            ensure_legacy_purchase_fiscal_foundation(stock_import=stock_import, requested_by=requested_by)
        except PurchaseNfeValidationError as exc:
            raise PurchaseReturnError(str(exc)) from exc
        stock_import = (
            StockImport.objects.select_related("fiscal_document", "workshop")
            .prefetch_related("fiscal_items__stock_product__product")
            .get(pk=stock_import.pk)
        )
    _validate_stock_purchase_document(stock_import=stock_import)
    return stock_import


def find_purchase_by_id(*, workshop: Any, stock_import_id: int, requested_by: Any | None = None) -> StockImport:
    access_key = StockImport.objects.filter(workshop=workshop, pk=stock_import_id).values_list("nf_key", flat=True).first()
    if not access_key:
        raise PurchaseReturnError("Não encontramos a NF-e de compra selecionada.")
    return find_purchase_by_access_key(workshop=workshop, access_key=access_key, requested_by=requested_by)


def eligible_purchase_imports(*, workshop: Any) -> QuerySet[StockImport]:
    normalized_purchase = Q(
        status=StockImport.ImportStatus.COMPLETED,
        fiscal_document__document_type=FiscalDocumentType.NFE,
        fiscal_document__origin=FiscalDocumentOrigin.EXTERNAL,
        fiscal_document__purpose=FiscalDocumentPurpose.NORMAL,
        fiscal_document__status=FiscalDocumentStatus.APPROVED,
        fiscal_document__legacy_nfe_item__isnull=True,
        fiscal_items__stock_product__isnull=False,
    ) & (Q(fiscal_snapshot__document__cancelled=False) | Q(fiscal_snapshot__document__cancelled__isnull=True))
    legacy_purchase = Q(
        fiscal_document__isnull=True,
        status=StockImport.ImportStatus.COMPLETED,
        method__in=[StockImport.ImportMethods.XML, StockImport.ImportMethods.KEY, StockImport.ImportMethods.SEFAZ],
    ) & ~Q(nf_key="") & ~Q(items_data=[])
    legacy_ids = [
        stock_import.pk
        for stock_import in StockImport.objects.filter(workshop=workshop).filter(legacy_purchase).only("pk", "items_data")
        if _has_legacy_stock_entry_items(stock_import)
    ]
    return (
        StockImport.objects.filter(workshop=workshop)
        .filter(normalized_purchase | Q(pk__in=legacy_ids))
        .select_related("fiscal_document")
        .annotate(
            purchase_total=Sum("fiscal_items__total_value"),
            product_count=Count("fiscal_items", distinct=True),
            purchase_issued_at=Coalesce("fiscal_issued_at", "criado_em"),
        )
        .order_by("-purchase_issued_at", "-pk")
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
        queryset = queryset.filter(purchase_issued_at__date__gte=issued_from)
    issued_until = filters.get("issued_until")
    if issued_until:
        queryset = queryset.filter(purchase_issued_at__date__lte=issued_until)
    value_min = filters.get("value_min")
    value_max = filters.get("value_max")
    product = str(filters.get("product") or "").strip()
    if not product and value_min is None and value_max is None:
        return queryset

    normalized = queryset.filter(fiscal_document__isnull=False)
    if product:
        matching_items = apply_text_search(
            StockImportFiscalItem.objects.filter(stock_import_id=OuterRef("pk")),
            search_value=product,
            lookups=("description", "product_code", "stock_product__product__name"),
        )
        normalized = normalized.annotate(has_matching_product=Exists(matching_items)).filter(has_matching_product=True)
    if value_min is not None:
        normalized = normalized.filter(purchase_total__gte=value_min)
    if value_max is not None:
        normalized = normalized.filter(purchase_total__lte=value_max)

    normalized_product = normalize_search_text(product)
    legacy_ids: list[int] = []
    legacy_candidates = queryset.filter(fiscal_document__isnull=True).select_related(None).only("pk", "items_data")
    for legacy in legacy_candidates:
        total, _count = legacy_purchase_summary(legacy)
        if value_min is not None and total < value_min:
            continue
        if value_max is not None and total > value_max:
            continue
        if normalized_product:
            legacy_items = legacy.items_data if isinstance(legacy.items_data, list) else []
            searchable_values = [
                normalize_search_text(value)
                for item in legacy_items
                if isinstance(item, dict)
                for value in (item.get("desc"), item.get("ref"))
            ]
            if not any(normalized_product in value for value in searchable_values):
                continue
        legacy_ids.append(legacy.pk)
    return queryset.filter(Q(pk__in=normalized.values("pk")) | Q(pk__in=legacy_ids))


def available_purchase_return_quantities(*, stock_import: StockImport, exclude_request: PurchaseReturnRequest | None = None) -> dict[int, Decimal]:
    if stock_import.fiscal_document_id is None:
        return {}
    available = calculate_available_return_quantities(original_document=stock_import.fiscal_document)
    reservations = PurchaseReturnRequestItem.objects.filter(
        request__source_stock_import=stock_import,
        request__status=PurchaseReturnRequestStatus.READY,
        request__fiscal_document__isnull=True,
        source_item__isnull=False,
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
    return selection


def _manual_snapshot_payload(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    try:
        quantity = Decimal(str(snapshot.get("quantity") or "0"))
        unit_value = Decimal(str(snapshot.get("unit_value") or "0"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PurchaseReturnError("Produto avulso possui quantidade ou valor inválido.") from exc
    if quantity <= 0:
        raise PurchaseReturnError("Produto avulso exige quantidade maior que zero.")
    if unit_value < 0:
        raise PurchaseReturnError("Produto avulso possui valor unitário inválido.")

    description = str(snapshot.get("description") or "").strip()
    ncm = str(snapshot.get("ncm") or "").strip()
    unit = str(snapshot.get("unit") or "").strip()
    if not description:
        raise PurchaseReturnError("Produto avulso exige descrição.")
    if not ncm:
        raise PurchaseReturnError("Produto avulso exige NCM.")
    if not unit:
        raise PurchaseReturnError("Produto avulso exige unidade.")

    try:
        origin = int(str(snapshot.get("origin") or "0").strip() or "0")
    except (TypeError, ValueError) as exc:
        raise PurchaseReturnError("Produto avulso possui origem tributária inválida.") from exc

    total_value = Decimal(str(snapshot.get("total_value") or quantity * unit_value))
    return {
        "description": description,
        "product_code": str(snapshot.get("product_code") or "").strip(),
        "ncm": ncm,
        "cest": str(snapshot.get("cest") or "").strip(),
        "unit": unit,
        "origin": origin,
        "quantity": quantity,
        "unit_value": unit_value,
        "total_value": total_value,
        "cfop": str(snapshot.get("cfop") or "").strip(),
        "tax_class": str(snapshot.get("tax_class") or "").strip(),
    }


@transaction.atomic
def save_purchase_return_items(*, request: PurchaseReturnRequest, quantities: Mapping[int, Decimal], manual_items: list[Mapping[str, Any]] | None = None) -> PurchaseReturnRequest:
    locked_request = PurchaseReturnRequest.objects.select_for_update(of=("self",)).select_related("source_stock_import__fiscal_document").get(pk=request.pk)
    if locked_request.status != PurchaseReturnRequestStatus.DRAFT:
        raise PurchaseReturnError("A intenção já foi finalizada e não pode mais ser alterada.")
    StockImport.objects.select_for_update().get(pk=locked_request.source_stock_import_id)
    list(PurchaseReturnRequest.objects.select_for_update().filter(source_stock_import=locked_request.source_stock_import, status=PurchaseReturnRequestStatus.READY))
    selection = _validated_selection(request=locked_request, quantities=quantities)
    manual_payloads = [_manual_snapshot_payload(snapshot) for snapshot in manual_items or []]
    if not selection and not manual_payloads:
        raise PurchaseReturnError("Selecione ao menos um produto ou adicione um produto avulso com quantidade maior que zero.")
    locked_request.items.all().delete()
    items = [
        PurchaseReturnRequestItem(
            request=locked_request,
            kind=PurchaseReturnItemKind.STOCK,
            source_item=source_item,
            quantity=quantity,
            unit_value=source_item.unit_value,
        )
        for source_item, quantity in selection
    ]
    items.extend(
        PurchaseReturnRequestItem(
            request=locked_request,
            kind=PurchaseReturnItemKind.MANUAL,
            source_item=None,
            manual_snapshot={key: str(value) for key, value in snapshot.items()},
            description=str(snapshot["description"]),
            product_code=str(snapshot.get("product_code") or ""),
            ncm=str(snapshot["ncm"]),
            cest=str(snapshot.get("cest") or ""),
            unit=str(snapshot["unit"]),
            cfop=str(snapshot.get("cfop") or ""),
            origin=int(snapshot["origin"]),
            tax_class=str(snapshot.get("tax_class") or ""),
            quantity=Decimal(snapshot["quantity"]),
            unit_value=Decimal(snapshot["unit_value"]),
        )
        for snapshot in manual_payloads
    )
    PurchaseReturnRequestItem.objects.bulk_create(items)
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
    quantities = {item.source_item_id: item.quantity for item in locked_request.items.select_related("source_item") if item.source_item_id is not None}
    stock_selection = _validated_selection(request=locked_request, quantities=quantities)
    if not stock_selection and not locked_request.items.filter(kind=PurchaseReturnItemKind.MANUAL).exists():
        raise PurchaseReturnError("A devolução não possui produtos selecionados.")
    locked_request.status = PurchaseReturnRequestStatus.READY
    locked_request.current_step = 4
    locked_request.ready_at = timezone.now()
    locked_request.save(update_fields=["status", "current_step", "ready_at", "atualizado_em"])
    return locked_request


def build_purchase_return_product_lines(*, request: PurchaseReturnRequest) -> list[ProductEmissionLine]:
    lines: list[ProductEmissionLine] = []
    for selected in request.items.select_related("source_item").order_by("kind", "source_item__sequence", "pk"):
        if selected.kind == PurchaseReturnItemKind.MANUAL:
            lines.append(
                ProductEmissionLine(
                    description=selected.description,
                    code=selected.product_code or f"AVULSO-{selected.pk or 'NOVO'}",
                    ncm=selected.ncm,
                    cest=selected.cest,
                    unit=selected.unit or "UN",
                    origin=selected.origin,
                    quantity=selected.quantity,
                    base_total=selected.total_value,
                )
            )
            continue
        source = selected.source_item
        snapshot = source.tax_snapshot if source is not None and isinstance(source.tax_snapshot, dict) else {}
        origin_value = snapshot.get("orig", snapshot.get("origin", 0))
        try:
            origin = int(origin_value)
        except (TypeError, ValueError):
            origin = 0
        if source is not None:
            description = source.description
            code = source.product_code or str(source.pk)
            ncm = source.ncm
            unit = source.unit or "UN"
        else:
            description = selected.description
            code = selected.product_code
            ncm = selected.ncm
            unit = selected.unit or "UN"
        lines.append(
            ProductEmissionLine(
                description=description,
                code=code,
                ncm=ncm,
                cest=str(snapshot.get("cest") or ""),
                unit=unit,
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
    products: list[dict[str, Any]] = []
    for item in request.items.select_related("source_item").order_by("kind", "source_item__sequence", "pk"):
        if item.kind == PurchaseReturnItemKind.MANUAL:
            products.append(
                {
                    "manual": True,
                    "nome": item.description,
                    "codigo": item.product_code or f"AVULSO-{item.pk}",
                    "ncm": item.ncm,
                    "cest": item.cest,
                    "unidade": item.unit or "UN",
                    "origem": item.origin,
                    "quantidade": str(item.quantity),
                    "valor_unitario": str(item.unit_value),
                    "total": str(item.total_value),
                    "codigo_cfop": item.cfop,
                    "classe_imposto": item.tax_class or request.tax_class,
                }
            )
            continue
        if item.source_item_id is not None:
            products.append({"sequencia": item.source_item.sequence, "quantidade": str(item.quantity)})
    return products


def build_purchase_return_emission_extras(*, request: PurchaseReturnRequest) -> dict[str, Any]:
    return {
        "freight_mode": request.freight_mode,
        "freight_amount": request.freight_amount,
        "discount_amount": request.discount_amount,
        "accessory_expenses": request.accessory_expenses,
        "insurance_amount": request.insurance_amount,
        "customs_expenses": request.customs_expenses,
        "total_override": request.total_override,
        "presence": request.presence,
        "intermediary": request.intermediary,
        "intermediary_cnpj": request.intermediary_cnpj,
        "intermediary_id": request.intermediary_id,
        "purchase_order": request.purchase_order,
        "contract": request.contract,
        "commitment_note": request.commitment_note,
        "payment_indicator": request.payment_indicator,
        "payment_method": request.payment_method,
        "payment_description": request.payment_description,
        "payment_value": request.payment_value,
        "payment_date": request.payment_date,
        "issue_at": request.issue_at,
        "departure_at": request.departure_at,
        "delivery_forecast": request.delivery_forecast,
        "transport_snapshot": request.transport_snapshot or {},
    }


def save_purchase_return_fiscal_data(*, request: PurchaseReturnRequest, cleaned_data: Mapping[str, Any]) -> PurchaseReturnRequest:
    for field_name in PurchaseReturnRequest.FISCAL_CONFIGURATION_FIELDS:
        if field_name in cleaned_data:
            setattr(request, field_name, cleaned_data[field_name])
    request.save(update_fields=[*PurchaseReturnRequest.FISCAL_CONFIGURATION_FIELDS, "atualizado_em"])
    return request


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
            volume=request_instance.volume,
            informacoes_fisco=request_instance.fisco_information,
            informacoes_complementares=request_instance.additional_information,
            extras=build_purchase_return_emission_extras(request=request_instance),
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
    draft_creation_error = ""
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
                    volume=locked.volume,
                    informacoes_fisco=locked.fisco_information,
                    informacoes_complementares=locked.additional_information,
                    extras=build_purchase_return_emission_extras(request=locked),
                    request=http_request,
                )
            except NfeReturnError as exc:
                draft_creation_error = str(exc)
            else:
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
                                "kind": item.kind,
                                "sequence": item.source_item.sequence if item.source_item_id else None,
                                "quantity": str(item.quantity),
                                "manual_snapshot": item.manual_snapshot,
                                "tax_snapshot": item.source_item.tax_snapshot if item.source_item_id else {},
                            }
                            for item in locked.items.select_related("source_item").order_by("kind", "source_item__sequence", "pk")
                        ],
                    }
                )
                link.save(update_fields=["metadata", "atualizado_em"])
        else:
            document = locked.fiscal_document
            if document.emission_attempts.exists():
                return sync_purchase_return_status(request_instance=locked)

    if draft_creation_error:
        # The local draft and its remote attempt were never created, so this
        # reservation can be released for a new review/transmission.
        PurchaseReturnRequest.objects.filter(
            pk=locked.pk,
            fiscal_document__isnull=True,
            status=PurchaseReturnRequestStatus.READY,
        ).update(
            status=PurchaseReturnRequestStatus.DRAFT,
            current_step=3,
            ready_at=None,
            atualizado_em=timezone.now(),
        )
        raise PurchaseReturnError(draft_creation_error)

    try:
        transmit_nfe_return_document(document=document)
    except NfeReturnError as exc:
        sync_purchase_return_status(request_instance=locked)
        raise PurchaseReturnError(str(exc)) from exc
    return sync_purchase_return_status(request_instance=locked)
