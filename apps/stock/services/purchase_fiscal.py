from __future__ import annotations

import base64
import gzip
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from lxml import etree

from apps.finance.models.finance import FiscalDocument, FiscalDocumentOrigin, FiscalDocumentPurpose, FiscalDocumentStatus, FiscalDocumentType
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.stock.models import StockImport, StockImportFiscalItem, StockProduct


NFE_NAMESPACE = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
AUTHORIZED_PROTOCOL_STATUS = "100"
CANCELLATION_EVENT_CODE = "110111"
AUTHORIZED_CANCELLATION_STATUSES = {"135", "136", "155"}


class PurchaseNfeValidationError(ValueError):
    pass


def _parse_issued_at(value: object) -> datetime | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    parsed_datetime = parse_datetime(raw_value)
    if parsed_datetime is not None:
        return parsed_datetime if timezone.is_aware(parsed_datetime) else timezone.make_aware(parsed_datetime)
    parsed_date = parse_date(raw_value)
    if parsed_date is None:
        return None
    return timezone.make_aware(datetime.combine(parsed_date, time.min))


def _digits(value: object) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def _parse_xml(content: bytes | str) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False, remove_blank_text=True)
    try:
        payload = content.encode("utf-8") if isinstance(content, str) else content
        return etree.fromstring(payload, parser=parser)
    except (etree.XMLSyntaxError, TypeError, ValueError) as exc:
        raise PurchaseNfeValidationError("O XML da NF-e de compra é inválido.") from exc


def _expanded_documents(root: etree._Element) -> list[etree._Element]:
    documents = [root]
    for node in root.xpath("//*[local-name()='docZip']"):
        encoded = str(node.text or "").strip()
        if not encoded:
            continue
        try:
            decoded = gzip.decompress(base64.b64decode(encoded))
            documents.append(_parse_xml(decoded))
        except (OSError, ValueError) as exc:
            raise PurchaseNfeValidationError("A distribuição da SEFAZ contém um documento compactado inválido.") from exc
    return documents


def _first_text(element: etree._Element, xpath: str) -> str:
    values = element.xpath(xpath, namespaces=NFE_NAMESPACE)
    if not values:
        return ""
    value = values[0]
    if isinstance(value, etree._Element):
        value = value.text
    return str(value or "").strip()


def _element_snapshot(element: etree._Element | None) -> dict[str, Any]:
    if element is None:
        return {}
    snapshot: dict[str, Any] = {}
    for child in element:
        key = etree.QName(child).localname
        value: Any = _element_snapshot(child) if len(child) else str(child.text or "").strip()
        existing = snapshot.get(key)
        if existing is None:
            snapshot[key] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            snapshot[key] = [existing, value]
    return snapshot


def _find_nfe_document(documents: list[etree._Element]) -> etree._Element:
    for document in documents:
        if document.xpath("//*[local-name()='infNFe']"):
            return document
    raise PurchaseNfeValidationError("O XML informado não contém uma NF-e completa modelo 55.")


def _is_cancelled(documents: list[etree._Element]) -> bool:
    for document in documents:
        event_codes = {str(value).strip() for value in document.xpath("//*[local-name()='tpEvento']/text()")}
        if CANCELLATION_EVENT_CODE not in event_codes:
            continue
        statuses = {str(value).strip() for value in document.xpath("//*[local-name()='retEvento']//*[local-name()='cStat']/text()")}
        if statuses & AUTHORIZED_CANCELLATION_STATUSES:
            return True
    return False


def _decimal(value: str, *, field_name: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PurchaseNfeValidationError(f"O item da NF-e possui {field_name} inválido.") from exc


def _build_product_snapshot(detail: etree._Element, *, fallback_sequence: int) -> dict[str, Any]:
    product_nodes = detail.xpath("./nfe:prod", namespaces=NFE_NAMESPACE)
    if not product_nodes:
        raise PurchaseNfeValidationError("A NF-e contém item sem dados de produto.")
    product = product_nodes[0]
    sequence_raw = str(detail.get("nItem") or fallback_sequence).strip()
    if not sequence_raw.isdigit() or int(sequence_raw) <= 0:
        raise PurchaseNfeValidationError("A NF-e contém item sem sequencial fiscal válido.")

    quantity = _decimal(_first_text(product, "./nfe:qCom/text()"), field_name="quantidade")
    unit_value = _decimal(_first_text(product, "./nfe:vUnCom/text()"), field_name="valor unitário")
    total_value_raw = _first_text(product, "./nfe:vProd/text()")
    total_value = _decimal(total_value_raw, field_name="valor total") if total_value_raw else quantity * unit_value
    if quantity <= 0:
        raise PurchaseNfeValidationError("A quantidade dos itens da NF-e deve ser maior que zero.")

    tax_nodes = detail.xpath("./nfe:imposto", namespaces=NFE_NAMESPACE)
    return {
        "sequence": int(sequence_raw),
        "product_code": _first_text(product, "./nfe:cProd/text()"),
        "description": _first_text(product, "./nfe:xProd/text()"),
        "quantity": str(quantity),
        "unit": _first_text(product, "./nfe:uCom/text()"),
        "unit_value": str(unit_value),
        "total_value": str(total_value),
        "ncm": _first_text(product, "./nfe:NCM/text()"),
        "cfop": _first_text(product, "./nfe:CFOP/text()"),
        "taxes": _element_snapshot(tax_nodes[0] if tax_nodes else None),
    }


def parse_and_validate_purchase_nfe(*, workshop: Any, xml_content: bytes | str) -> dict[str, Any]:
    root = _parse_xml(xml_content)
    documents = _expanded_documents(root)
    nfe_document = _find_nfe_document(documents)
    inf_nfe_nodes = nfe_document.xpath("//*[local-name()='infNFe']")
    inf_nfe = inf_nfe_nodes[0]

    access_key = str(inf_nfe.get("Id") or "").removeprefix("NFe")
    if len(access_key) != 44 or not access_key.isdigit():
        raise PurchaseNfeValidationError("A NF-e de compra não possui chave de acesso válida.")

    model = _first_text(inf_nfe, ".//nfe:ide/nfe:mod/text()")
    if model != "55":
        raise PurchaseNfeValidationError("Somente NF-e de produto modelo 55 pode originar uma compra.")

    protocol_status = ""
    protocol_number = ""
    environment = ""
    for document in documents:
        protocol_keys = {str(value).strip() for value in document.xpath("//*[local-name()='protNFe']//*[local-name()='chNFe']/text()")}
        if access_key not in protocol_keys:
            continue
        protocol_status = _first_text(document, "//*[local-name()='protNFe']//*[local-name()='cStat']/text()")
        protocol_number = _first_text(document, "//*[local-name()='protNFe']//*[local-name()='nProt']/text()")
        environment = _first_text(document, "//*[local-name()='protNFe']//*[local-name()='tpAmb']/text()")
        break
    if protocol_status != AUTHORIZED_PROTOCOL_STATUS or not protocol_number:
        raise PurchaseNfeValidationError("A NF-e de compra não possui protocolo de autorização válido.")
    if _is_cancelled(documents):
        raise PurchaseNfeValidationError("A NF-e de compra está cancelada.")

    issuer_document = _digits(_first_text(inf_nfe, ".//nfe:emit/nfe:CNPJ/text()") or _first_text(inf_nfe, ".//nfe:emit/nfe:CPF/text()"))
    recipient_document = _digits(_first_text(inf_nfe, ".//nfe:dest/nfe:CNPJ/text()") or _first_text(inf_nfe, ".//nfe:dest/nfe:CPF/text()"))
    workshop_document = _digits(getattr(workshop, "cnpj", ""))
    if not issuer_document or issuer_document == workshop_document:
        raise PurchaseNfeValidationError("A NF-e informada foi emitida pela própria oficina e não representa uma compra recebida.")
    if not recipient_document or recipient_document != workshop_document:
        raise PurchaseNfeValidationError("O destinatário da NF-e não corresponde à oficina atual.")

    detail_nodes = inf_nfe.xpath("./nfe:det", namespaces=NFE_NAMESPACE)
    if not detail_nodes:
        raise PurchaseNfeValidationError("A NF-e de compra não possui itens de produto.")
    products = [_build_product_snapshot(detail, fallback_sequence=index) for index, detail in enumerate(detail_nodes, start=1)]

    return {
        "schema_version": 1,
        "document": {
            "model": model,
            "access_key": access_key,
            "number": _first_text(inf_nfe, ".//nfe:ide/nfe:nNF/text()"),
            "series": _first_text(inf_nfe, ".//nfe:ide/nfe:serie/text()"),
            "issued_at": _first_text(inf_nfe, ".//nfe:ide/nfe:dhEmi/text()") or _first_text(inf_nfe, ".//nfe:ide/nfe:dEmi/text()"),
            "operation_type": _first_text(inf_nfe, ".//nfe:ide/nfe:tpNF/text()"),
            "purpose": _first_text(inf_nfe, ".//nfe:ide/nfe:finNFe/text()"),
            "environment": environment,
            "protocol_status": protocol_status,
            "protocol_number": protocol_number,
            "cancelled": False,
        },
        "issuer": {
            "document": issuer_document,
            "name": _first_text(inf_nfe, ".//nfe:emit/nfe:xNome/text()"),
        },
        "recipient": {
            "document": recipient_document,
            "name": _first_text(inf_nfe, ".//nfe:dest/nfe:xNome/text()"),
        },
        "products": products,
    }


def _linked_stock_products(*, stock_import: StockImport, snapshot_products: list[dict[str, Any]]) -> dict[int, StockProduct]:
    linked_product_ids_by_sequence: dict[int, int] = {}
    for index, raw_item in enumerate(stock_import.items_data or [], start=1):
        sequence = int(raw_item.get("nitem") or raw_item.get("sequence") or index)
        product_id = raw_item.get("linked_product_id")
        if product_id:
            linked_product_ids_by_sequence[sequence] = int(product_id)
    stock_products = StockProduct.objects.filter(workshop=stock_import.workshop, product_id__in=linked_product_ids_by_sequence.values())
    by_product_id = {stock_product.product_id: stock_product for stock_product in stock_products}
    return {
        int(product["sequence"]): by_product_id[linked_product_ids_by_sequence[int(product["sequence"])]]
        for product in snapshot_products
        if int(product["sequence"]) in linked_product_ids_by_sequence and linked_product_ids_by_sequence[int(product["sequence"])] in by_product_id
    }


def _legacy_purchase_snapshot(stock_import: StockImport) -> dict[str, Any]:
    access_key = _digits(stock_import.nf_key)
    if stock_import.status != StockImport.ImportStatus.COMPLETED or len(access_key) != 44:
        raise PurchaseNfeValidationError("A importação histórica precisa estar concluída e possuir chave de acesso válida.")
    raw_items = stock_import.items_data if isinstance(stock_import.items_data, list) else []
    if not raw_items:
        raise PurchaseNfeValidationError("A importação histórica não possui itens para materialização fiscal.")

    products: list[dict[str, Any]] = []
    sequences: set[int] = set()
    for index, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            raise PurchaseNfeValidationError("A importação histórica possui item inválido.")
        try:
            sequence = int(raw_item.get("nitem") or raw_item.get("sequence") or index)
            quantity = Decimal(str(raw_item.get("qtd") or "0"))
            unit_value = Decimal(str(raw_item.get("valor") or "0"))
            total_value = Decimal(str(raw_item.get("valor_total") or quantity * unit_value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PurchaseNfeValidationError("A importação histórica possui quantidade ou valor inválido.") from exc
        if sequence <= 0 or sequence in sequences or quantity <= 0 or unit_value < 0 or total_value < 0:
            raise PurchaseNfeValidationError("A importação histórica possui sequencial, quantidade ou valor inválido.")
        sequences.add(sequence)
        description = str(raw_item.get("desc") or raw_item.get("description") or "").strip()
        if not description:
            raise PurchaseNfeValidationError("A importação histórica possui item sem descrição.")
        taxes = raw_item.get("tributos") if isinstance(raw_item.get("tributos"), dict) else {}
        products.append(
            {
                "sequence": sequence,
                "product_code": str(raw_item.get("ref") or raw_item.get("product_code") or ""),
                "description": description,
                "quantity": str(quantity),
                "unit": str(raw_item.get("unidade") or raw_item.get("unit") or "UN"),
                "unit_value": str(unit_value),
                "total_value": str(total_value),
                "ncm": str(raw_item.get("ncm") or ""),
                "cfop": str(raw_item.get("cfop") or ""),
                "taxes": taxes,
            }
        )

    issued_at = stock_import.fiscal_issued_at or stock_import.criado_em
    return {
        "schema_version": 1,
        "source": "historical_stock_import",
        "document": {
            "model": "55",
            "access_key": access_key,
            "number": stock_import.nf_number_display,
            "series": "",
            "issued_at": issued_at.isoformat() if issued_at else "",
            "environment": "",
            "protocol_status": "historical_import",
            "protocol_number": "",
            "cancelled": False,
        },
        "issuer": {"document": _digits(stock_import.supplier_cnpj), "name": str(stock_import.supplier_name or "")},
        "recipient": {"document": _digits(stock_import.workshop.cnpj), "name": str(stock_import.workshop.name)},
        "products": products,
    }


def _persist_purchase_fiscal_foundation(
    *,
    locked_import: StockImport,
    snapshot: dict[str, Any],
    requested_by: Any | None,
    remote_status: str,
    response_payload: dict[str, Any],
    externally_confirmed_at: datetime | None,
) -> dict[int, StockImportFiscalItem]:
    document_snapshot = snapshot.get("document") if isinstance(snapshot.get("document"), dict) else {}
    products = snapshot.get("products") if isinstance(snapshot.get("products"), list) else []
    access_key = str(document_snapshot.get("access_key") or "")
    if access_key != locked_import.nf_key or len(access_key) != 44:
        raise PurchaseNfeValidationError("O snapshot fiscal não corresponde à chave da importação de estoque.")
    if not products:
        raise PurchaseNfeValidationError("O snapshot fiscal da compra não possui itens.")

    existing_document = FiscalDocument.objects.filter(workshop=locked_import.workshop, document_type=FiscalDocumentType.NFE, access_key=access_key).first()
    if existing_document is not None and existing_document.origin != FiscalDocumentOrigin.EXTERNAL:
        raise PurchaseNfeValidationError("A chave da compra já está associada a um documento fiscal local ou derivado.")
    if existing_document is not None:
        linked_import = StockImport.objects.filter(fiscal_document=existing_document).exclude(pk=locked_import.pk).first()
        if linked_import is not None:
            raise PurchaseNfeValidationError("A chave da compra já está vinculada a outra importação de estoque.")

    issued_at = _parse_issued_at(document_snapshot.get("issued_at"))
    document_defaults = {
        "account": getattr(locked_import.workshop, "account", None),
        "origin": FiscalDocumentOrigin.EXTERNAL,
        "purpose": FiscalDocumentPurpose.NORMAL,
        "complementary_type": "",
        "environment": str(document_snapshot.get("environment") or ""),
        "status": FiscalDocumentStatus.APPROVED,
        "remote_status": remote_status,
        "series": str(document_snapshot.get("series") or ""),
        "number": str(document_snapshot.get("number") or locked_import.nf_number or ""),
        "receipt": str(document_snapshot.get("protocol_number") or ""),
        "request_payload": sanitize_fiscal_payload(snapshot),
        "response_payload": sanitize_fiscal_payload(response_payload),
        "requested_by": requested_by if getattr(requested_by, "is_authenticated", False) else None,
        "external_confirmation": externally_confirmed_at is not None,
        "external_confirmed_at": externally_confirmed_at,
    }
    if existing_document is None:
        fiscal_document = FiscalDocument.objects.create(workshop=locked_import.workshop, document_type=FiscalDocumentType.NFE, access_key=access_key, **document_defaults)
    else:
        fiscal_document = existing_document
        for field_name, value in document_defaults.items():
            setattr(fiscal_document, field_name, value)
        fiscal_document.save(update_fields=[*document_defaults.keys(), "atualizado_em"])

    locked_import.fiscal_document = fiscal_document
    locked_import.fiscal_snapshot = snapshot
    locked_import.fiscal_issued_at = issued_at
    import_update_fields = ["fiscal_document", "fiscal_snapshot", "fiscal_issued_at", "atualizado_em"]
    if externally_confirmed_at is not None:
        locked_import.fiscal_validated_at = externally_confirmed_at
        import_update_fields.append("fiscal_validated_at")
    locked_import.save(update_fields=import_update_fields)

    stock_products = _linked_stock_products(stock_import=locked_import, snapshot_products=products)
    fiscal_items: dict[int, StockImportFiscalItem] = {}
    active_sequences: set[int] = set()
    for product in products:
        sequence = int(product["sequence"])
        active_sequences.add(sequence)
        fiscal_item, _ = StockImportFiscalItem.objects.update_or_create(
            stock_import=locked_import,
            sequence=sequence,
            defaults={
                "stock_product": stock_products.get(sequence),
                "product_code": str(product.get("product_code") or ""),
                "description": str(product.get("description") or f"Item {sequence}"),
                "quantity": Decimal(str(product.get("quantity") or "0")),
                "unit": str(product.get("unit") or ""),
                "unit_value": Decimal(str(product.get("unit_value") or "0")),
                "total_value": Decimal(str(product.get("total_value") or "0")),
                "ncm": str(product.get("ncm") or ""),
                "cfop": str(product.get("cfop") or ""),
                "tax_snapshot": product.get("taxes") if isinstance(product.get("taxes"), dict) else {},
            },
        )
        fiscal_items[sequence] = fiscal_item

    stale_items = locked_import.fiscal_items.exclude(sequence__in=active_sequences)
    if stale_items.filter(stock_movements__isnull=False).exists():
        raise PurchaseNfeValidationError("A importação possui itens fiscais rastreados que não existem mais no snapshot validado.")
    stale_items.delete()
    return fiscal_items


@transaction.atomic
def ensure_purchase_fiscal_foundation(*, stock_import: StockImport, requested_by: Any | None = None) -> dict[int, StockImportFiscalItem]:
    locked_import = StockImport.objects.select_for_update(of=("self",)).select_related("workshop").get(pk=stock_import.pk)
    if locked_import.method == StockImport.ImportMethods.MANUAL:
        return {}
    if locked_import.fiscal_validation_status != StockImport.FiscalValidationStatus.VALIDATED:
        raise PurchaseNfeValidationError("A importação precisa possuir XML de compra validado antes de gerar rastreabilidade fiscal.")

    snapshot = locked_import.fiscal_snapshot if isinstance(locked_import.fiscal_snapshot, dict) else {}
    validated_at = locked_import.fiscal_validated_at or timezone.now()
    fiscal_items = _persist_purchase_fiscal_foundation(
        locked_import=locked_import,
        snapshot=snapshot,
        requested_by=requested_by,
        remote_status="validated_purchase_xml",
        response_payload={"source": "purchase_xml", "validated": True, "validated_at": validated_at.isoformat()},
        externally_confirmed_at=validated_at,
    )
    stock_import.fiscal_document = locked_import.fiscal_document
    stock_import.fiscal_validated_at = validated_at
    return fiscal_items


@transaction.atomic
def ensure_legacy_purchase_fiscal_foundation(*, stock_import: StockImport, requested_by: Any | None = None) -> dict[int, StockImportFiscalItem]:
    locked_import = StockImport.objects.select_for_update(of=("self",)).select_related("workshop").get(pk=stock_import.pk)
    if locked_import.fiscal_document_id and locked_import.fiscal_items.exists():
        stock_import.fiscal_document = locked_import.fiscal_document
        return {item.sequence: item for item in locked_import.fiscal_items.all()}
    snapshot = _legacy_purchase_snapshot(locked_import)
    fiscal_items = _persist_purchase_fiscal_foundation(
        locked_import=locked_import,
        snapshot=snapshot,
        requested_by=requested_by,
        remote_status="historical_stock_import",
        response_payload={"source": "historical_stock_import", "validated": False},
        externally_confirmed_at=None,
    )
    stock_import.fiscal_document = locked_import.fiscal_document
    stock_import.fiscal_snapshot = snapshot
    stock_import.fiscal_issued_at = locked_import.fiscal_issued_at
    return fiscal_items
