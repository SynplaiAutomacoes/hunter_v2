from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.product_issues import normalize_ncm
from apps.finance.models.finance import NfeRequest, NfeRequestStatus, NfseRequest, NfseRequestStatus, StandaloneNfeLine, StandaloneNfseLine
from apps.finance.services.fiscal_recipient import recipient_name_from_snapshot, recipient_snapshot_from_form_data


def refresh_standalone_nfe_lines_from_catalog(*, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-read NCM/CEST/unit/origin from catalog products so edits apply without re-adding lines."""
    product_ids = [int(line["product_id"]) for line in lines if line.get("product_id")]
    products_by_id = Product.objects.in_bulk(product_ids) if product_ids else {}
    refreshed: list[dict[str, Any]] = []
    for line in lines:
        updated = dict(line)
        product_id = line.get("product_id")
        if product_id:
            product = products_by_id.get(int(product_id))
            if product is not None:
                updated["description"] = product.name
                updated["product_code"] = product.code
                updated["ncm"] = product.ncm
                updated["cest"] = product.cest or ""
                updated["unit"] = product.unit
                updated["origin"] = int(product.origin_cst or 0)
        refreshed.append(updated)
    return refreshed


def line_has_valid_ncm(*, line: dict[str, Any]) -> bool:
    return len(normalize_ncm(line.get("ncm"))) == 8


def _coerce_consumidor_final(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if normalized in {"false", "0", "nao", "não", "no"}:
        return False
    if normalized in {"true", "1", "sim", "yes"}:
        return True
    return None


def default_standalone_state() -> dict[str, Any]:
    return {
        "current_step": 1,
        "max_reached_step": 1,
        "note_mode": "",
        "recipient": {},
        "nfe_lines": [],
        "nfse_lines": [],
        "nfe_config": {"tax_class": "", "additional_information": "", "freight_mode": "9", "transport_snapshot": {}},
        "nfse_config": {"tax_class": "", "service_description": "", "additional_information": "", "codigo_nbs": "", "consumidor_final": None},
        "nfe_request_id": None,
        "nfse_request_id": None,
        "nfe_done": False,
        "nfse_done": False,
    }


def normalize_note_mode(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"nfe", "nfse", "both"}:
        return normalized
    return ""


def product_line_from_catalog(
    *,
    product: Product,
    quantity: Decimal,
    unit_value: Decimal | None = None,
    cost_value: Decimal | None = None,
) -> dict[str, Any]:
    resolved_unit_value = unit_value if unit_value is not None else Decimal(str(product.selling_price.amount))
    resolved_cost = cost_value if cost_value is not None else Decimal(str(getattr(product.cost_price, "amount", 0) or 0))
    total_value = (quantity * resolved_unit_value).quantize(Decimal("0.01"))
    return {
        "product_id": product.pk,
        "description": product.name,
        "product_code": product.code,
        "ncm": product.ncm,
        "cest": product.cest or "",
        "unit": product.unit,
        "origin": int(product.origin_cst or 0),
        "quantity": str(int(quantity)),
        "cost_value": str(resolved_cost),
        "unit_value": str(resolved_unit_value),
        "total_value": str(total_value),
    }


def service_line_from_catalog(
    *,
    service: Service,
    quantity: Decimal,
    unit_value: Decimal | None = None,
    cost_value: Decimal | None = None,
) -> dict[str, Any]:
    resolved_unit_value = unit_value if unit_value is not None else Decimal(str(service.selling_price.amount))
    if cost_value is not None:
        resolved_cost = cost_value
    elif service.suggested_cost is not None:
        resolved_cost = Decimal(str(service.suggested_cost.amount))
    else:
        resolved_cost = Decimal("0")
    total_value = (quantity * resolved_unit_value).quantize(Decimal("0.01"))
    return {
        "service_id": service.pk,
        "description": service.name,
        "quantity": str(int(quantity)),
        "cost_value": str(resolved_cost),
        "unit_value": str(resolved_unit_value),
        "total_value": str(total_value),
    }


def persist_nfe_lines(*, nfe_request: NfeRequest, lines: list[dict[str, Any]]) -> None:
    nfe_request.standalone_lines.all().delete()
    for index, line in enumerate(lines):
        StandaloneNfeLine.objects.create(
            nfe_request=nfe_request,
            product_id=line.get("product_id") or None,
            description=str(line.get("description") or ""),
            product_code=str(line.get("product_code") or ""),
            ncm=str(line.get("ncm") or ""),
            cest=str(line.get("cest") or ""),
            unit=str(line.get("unit") or "UN"),
            origin=int(line.get("origin") or 0),
            quantity=Decimal(str(line.get("quantity") or "0")),
            unit_value=Decimal(str(line.get("unit_value") or "0")),
            sort_order=index,
        )


def persist_nfse_lines(*, nfse_request: NfseRequest, lines: list[dict[str, Any]]) -> None:
    nfse_request.standalone_lines.all().delete()
    for index, line in enumerate(lines):
        StandaloneNfseLine.objects.create(
            nfse_request=nfse_request,
            service_id=line.get("service_id") or None,
            description=str(line.get("description") or ""),
            quantity=Decimal(str(line.get("quantity") or "1")),
            unit_value=Decimal(str(line.get("unit_value") or "0")),
            sort_order=index,
        )


@transaction.atomic
def get_or_create_standalone_nfe_request(*, workshop: Any, state: dict[str, Any]) -> NfeRequest:
    request_id = state.get("nfe_request_id")
    nfe_request = None
    if request_id:
        nfe_request = NfeRequest.objects.filter(pk=request_id, workshop=workshop).first()

    recipient = state.get("recipient") or {}
    if nfe_request is None:
        nfe_request = NfeRequest(workshop=workshop)

    nfe_request.workorder = None
    nfe_request.recipient_snapshot = recipient
    nfe_request.recipient_name = recipient_name_from_snapshot(recipient)
    nfe_request.current_step = 3
    nfe_request.status = NfeRequestStatus.CHECKING_PRODUCTS
    nfe_config = state.get("nfe_config") or {}
    nfe_request.tax_class = str(nfe_config.get("tax_class") or "")
    nfe_request.additional_information = str(nfe_config.get("additional_information") or "")
    nfe_request.freight_mode = int(nfe_config.get("freight_mode") or 9)
    nfe_request.transport_snapshot = dict(nfe_config.get("transport_snapshot") or {})
    nfe_request.pricing_slider = 0
    nfe_request.discount_type_override = ""
    nfe_request.save()

    refreshed_lines = refresh_standalone_nfe_lines_from_catalog(lines=list(state.get("nfe_lines") or []))
    state["nfe_lines"] = refreshed_lines
    persist_nfe_lines(nfe_request=nfe_request, lines=refreshed_lines)
    state["nfe_request_id"] = nfe_request.pk
    return nfe_request


@transaction.atomic
def get_or_create_standalone_nfse_request(*, workshop: Any, state: dict[str, Any]) -> NfseRequest:
    request_id = state.get("nfse_request_id")
    nfse_request = None
    if request_id:
        nfse_request = NfseRequest.objects.filter(pk=request_id, workshop=workshop).first()

    recipient = state.get("recipient") or {}
    if nfse_request is None:
        nfse_request = NfseRequest(workshop=workshop)

    nfse_request.workorder = None
    nfse_request.recipient_snapshot = recipient
    nfse_request.recipient_name = recipient_name_from_snapshot(recipient)
    nfse_request.current_step = 3
    nfse_request.status = NfseRequestStatus.CHECKING_SERVICES
    nfse_config = state.get("nfse_config") or {}
    nfse_request.tax_class = str(nfse_config.get("tax_class") or "")
    nfse_request.service_description = str(nfse_config.get("service_description") or "")
    nfse_request.additional_information = str(nfse_config.get("additional_information") or "")
    nfse_request.codigo_nbs = str(nfse_config.get("codigo_nbs") or "")
    nfse_request.consumidor_final = _coerce_consumidor_final(nfse_config.get("consumidor_final"))
    nfse_request.pricing_slider = 0
    nfse_request.discount_type_override = ""
    nfse_request.save()

    persist_nfse_lines(nfse_request=nfse_request, lines=list(state.get("nfse_lines") or []))
    state["nfse_request_id"] = nfse_request.pk
    return nfse_request


def recipient_snapshot_from_post(post_data: dict[str, Any]) -> dict[str, str | int]:
    return recipient_snapshot_from_form_data(post_data)
