from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
import logging
import re
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest

from apps.finance.models.finance import NfeItem, NfeRequest
from apps.finance.nfe_transport import NfeTransportValidationError, build_webmania_transport_payload
from apps.finance.services.fiscal_attempts import FiscalEmissionAttemptBlocked, begin_emission_attempt, mark_attempt_failed, mark_attempt_sent, mark_attempt_succeeded, mark_attempt_uncertain
from apps.finance.services.ibs_cbs import IbsCbsConfigurationError, require_ready_tax_class_for_normal_emission
from apps.finance.services.numbering import EmissionNumberReservationError, reserve_nfe_request_number
from apps.core.infrastructure.services.webmania.emission import build_webmania_webhook_url
from apps.finance.services.pricing import SliderAllocation, build_emission_pricing_snapshot_for_workorder, build_slider_allocation_for_workorder, distribute_total_proportionally
from apps.core.infrastructure.services.webmania.webmania_auth import (
    WebmaniaAuthError,
    build_webmania_headers,
    sanitize_webmania_setting,
    should_use_global_webmania_auth,
)
from apps.core.infrastructure.services.webmania.webmania_documents import DownloadedWebmaniaDocument, WebmaniaDocumentDownloadError, download_webmania_document
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message
from apps.core.infrastructure.services.webmania.webmania_status import normalize_nfe_status
from apps.workorder.models import WorkOrder, WorkOrderDiscountType


logger = logging.getLogger(__name__)


class NfeEmissionError(Exception):
    pass


@dataclass(frozen=True)
class ProductEmissionLine:
    description: str
    code: str
    ncm: str
    cest: str
    unit: str
    origin: int
    quantity: Decimal
    base_total: Decimal


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _distribute_discount_by_quantity(
    *,
    quantities: list[Decimal],
    item_totals: list[Decimal],
    discount_amount: Decimal,
) -> list[Decimal]:
    if not quantities or discount_amount <= 0:
        return [Decimal("0.00")] * len(quantities)

    discounts = [Decimal("0.00")] * len(quantities)
    remaining_discount = _quantize_money(discount_amount)
    remaining_indices = list(range(len(quantities)))

    while remaining_discount > 0 and remaining_indices:
        total_qty = sum(quantities[i] for i in remaining_indices)
        if total_qty <= 0:
            break

        new_discounts = [Decimal("0.00")] * len(quantities)
        distributed_sum = Decimal("0.00")
        for i in remaining_indices:
            share = _quantize_money(remaining_discount * (quantities[i] / total_qty))
            new_discounts[i] = share
            distributed_sum += share

        rounding_diff = _quantize_money(remaining_discount - distributed_sum)
        if rounding_diff != 0:
            new_discounts[remaining_indices[-1]] = _quantize_money(new_discounts[remaining_indices[-1]] + rounding_diff)

        excess = Decimal("0.00")
        next_remaining: list[int] = []
        for i in remaining_indices:
            candidate = _quantize_money(discounts[i] + new_discounts[i])
            cap = item_totals[i]
            if candidate >= cap:
                excess = _quantize_money(excess + (candidate - cap))
                discounts[i] = cap
            else:
                discounts[i] = candidate
                next_remaining.append(i)

        if len(next_remaining) == len(remaining_indices):
            break

        remaining_discount = excess
        remaining_indices = next_remaining

    return discounts


def compute_product_discount_for_nfe(
    *,
    workorder: WorkOrder,
    products_target: Decimal,
    services_target: Decimal,
    discount_type_override: str = "",
) -> Decimal:
    """
    Calcula o valor de desconto a ser aplicado nos produtos da NF-e,
    levando em consideracao o discount_type da WorkOrder:

    - PRODUCTS: todo o desconto da WorkOrder vai para os produtos.
    - SERVICES: o desconto e inteiramente para servicos; apenas o excesso
      (quando total_discount > raw_services_total) vai para os produtos.
    - BOTH: o desconto e distribuido proporcionalmente entre produtos e
      servicos usando os valores brutos reais do pedido (independente do
      slider de alocacao da NF-e).

    Se discount_type_override for informado, usa ele no lugar do discount_type
    da WorkOrder (para sobrescrita especifica da emissao).
    """
    total_discount = _quantize_money(Decimal(str(workorder.resolved_discount_value.amount)))
    if total_discount <= Decimal("0.00"):
        return Decimal("0.00")

    discount_type = str(discount_type_override or workorder.discount_type)

    if discount_type == WorkOrderDiscountType.PRODUCTS:
        return total_discount

    # Para SERVICES e BOTH, usa os valores brutos reais (pre-slider) do pedido.
    # O slider altera apenas a alocacao de receita para NF-e/NFS-e, mas nao
    # deve afetar a proporcao do desconto entre produtos e servicos.
    snapshot = workorder.pricing_snapshot
    raw_products = _quantize_money(Decimal(str(snapshot.total_products_value.amount)))
    raw_services = _quantize_money(Decimal(str(snapshot.total_services_value.amount)))

    if discount_type == WorkOrderDiscountType.SERVICES:
        # Desconto apenas para servicos; se superar o total de servicos, o excesso vai para produtos
        excess = _quantize_money(max(Decimal("0.00"), total_discount - raw_services))
        return excess

    # BOTH: distribuicao proporcional entre produtos e servicos pelos valores brutos
    raw_total = _quantize_money(raw_products + raw_services)
    if raw_total <= Decimal("0.00"):
        return Decimal("0.00")
    return _quantize_money(total_discount * raw_products / raw_total)


def _build_headers(*, workshop=None) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfeEmissionError(str(exc)) from exc


def _build_emit_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_EMIT_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/emissao/"


def _build_cancel_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_CANCEL_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/cancelar/"


def _build_invalidate_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_INVALIDATE_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/inutilizar/"


def _build_tax_class_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/classe-imposto/"


def _is_nfse_tax_class(payload: dict[str, Any]) -> bool:
    tax_type = str(payload.get("tipo") or payload.get("type") or "").strip().lower()
    if tax_type in {"nfse", "nfs-e", "nsfe"}:
        return True
    return bool(str(payload.get("tipo_emissao") or "").strip()) and bool(str(payload.get("codigo_servico") or "").strip())


def _validate_nfe_tax_class(*, nfe_request: NfeRequest, headers: dict[str, str]) -> dict[str, Any]:
    reference = str(nfe_request.tax_class or "").strip()
    if not reference:
        raise NfeEmissionError("Selecione uma classe de imposto para emitir a Nota Fiscal.")

    try:
        response = requests.get(_build_tax_class_url(), headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao validar classe de imposto para emissao", scope="tax_class")
        raise NfeEmissionError(message) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise NfeEmissionError("Resposta invalida da API ao validar classe de imposto.") from exc

    if not isinstance(payload, list):
        if isinstance(payload, dict):
            error_message = extract_webmania_error_message(payload.get("error") or payload.get("message") or payload.get("msg"), scope="tax_class")
            if error_message:
                raise NfeEmissionError(error_message)
        raise NfeEmissionError("Resposta invalida da API ao validar classe de imposto.")

    for item in payload:
        if not isinstance(item, dict):
            continue
        if str(item.get("referencia") or "").strip() != reference:
            continue
        if _is_nfse_tax_class(item):
            raise NfeEmissionError("A classe de imposto selecionada nao e do tipo Nota Fiscal.")
        return item

    raise NfeEmissionError("A classe de imposto selecionada nao esta disponivel para estas credenciais da Webmania.")


def _validate_local_ibs_cbs_tax_class(*, nfe_request: NfeRequest) -> None:
    try:
        require_ready_tax_class_for_normal_emission(
            workshop=nfe_request.workshop,
            reference=str(nfe_request.tax_class or ""),
            product_label="Nota Fiscal normal",
        )
    except IbsCbsConfigurationError as exc:
        raise NfeEmissionError(str(exc)) from exc


def _normalize_document(value: str) -> str:
    return "".join(char for char in value if char.isdigit())


def _require_customer_field(*, value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise NfeEmissionError(f"Campo obrigatorio do cliente ausente para Nota Fiscal: {field_name}.")
    return normalized


def _build_customer_payload(nfe_request: NfeRequest) -> dict[str, Any]:
    customer = nfe_request.workorder.budget.customer
    if customer is None:
        raise NfeEmissionError("A OS selecionada nao possui cliente vinculado.")

    document = _normalize_document(customer.cpf_or_cnpj or "")
    payload: dict[str, Any] = {
        "endereco": _require_customer_field(value=customer.logradouro, field_name="endereco"),
        "numero": _require_customer_field(value=customer.numero, field_name="numero"),
        "bairro": _require_customer_field(value=customer.bairro, field_name="bairro"),
        "cidade": _require_customer_field(value=customer.cidade, field_name="cidade"),
        "uf": _require_customer_field(value=customer.estado, field_name="uf"),
        "cep": _require_customer_field(value=customer.cep, field_name="cep"),
    }

    if customer.complemento:
        payload["complemento"] = str(customer.complemento).strip()
    if customer.phone:
        payload["telefone"] = str(customer.phone)
    if customer.email:
        payload["email"] = str(customer.email).strip()

    if len(document) == 11:
        payload["cpf"] = customer.cpf_or_cnpj
        payload["nome_completo"] = _require_customer_field(value=customer.name, field_name="nome_completo")
        return payload

    if len(document) == 14:
        payload["cnpj"] = customer.cpf_or_cnpj
        payload["razao_social"] = _require_customer_field(value=customer.name, field_name="razao_social")
        state_registration = str(customer.state_registration or "").strip()
        payload["ie"] = state_registration or "ISENTO"
        return payload

    raise NfeEmissionError("Documento do cliente invalido para emissao de Nota Fiscal.")


def _normalize_ncm(raw_value: str) -> str:
    return re.sub(r"\D", "", str(raw_value or ""))


def _unit_for_api(raw_unit: str) -> str:
    unit_map = {
        "UND": "UN",
    }
    normalized = str(raw_unit or "").strip().upper()
    if not normalized:
        return "UN"
    return unit_map.get(normalized, normalized)


def _build_snapshot_product_line(line: Any) -> ProductEmissionLine:
    product = getattr(line, "source_object", None)
    if product is None:
        raise NfeEmissionError("A OS possui item de peca local sem cadastro fiscal completo. Cadastre o produto para emitir Nota Fiscal.")

    ncm = _normalize_ncm(product.ncm)
    if len(ncm) != 8:
        raise NfeEmissionError(f"Produto '{product.name}' sem NCM valido para emissao de Nota Fiscal.")

    code = str(product.code or "").strip()
    if not code:
        raise NfeEmissionError(f"Produto '{product.name}' sem codigo para emissao de Nota Fiscal.")

    quantity = Decimal(line.quantity)
    base_total = _quantize_money(Decimal(line.raw_total.amount))
    return ProductEmissionLine(
        description=str(line.description or product.name or "Produto")[:120],
        code=code[:60],
        ncm=ncm,
        cest=str(product.cest or "").strip(),
        unit=_unit_for_api(str(product.unit or "")),
        origin=int(product.origin_cst or 0),
        quantity=quantity,
        base_total=base_total,
    )


def _extract_product_lines(*, workorder: WorkOrder) -> list[ProductEmissionLine]:
    snapshot = build_emission_pricing_snapshot_for_workorder(workorder=workorder)
    lines = [_build_snapshot_product_line(line) for line in snapshot.product_lines]
    return [line for line in lines if line.quantity > 0 and line.base_total > 0]


def _build_snapshot_preview_product_line(line: Any) -> ProductEmissionLine | None:
    quantity = Decimal(getattr(line, "quantity", 0) or 0)
    base_total = _quantize_money(Decimal(getattr(getattr(line, "raw_total", None), "amount", 0) or 0))
    if quantity <= 0 or base_total <= 0:
        return None

    product = getattr(line, "source_object", None)
    raw_ncm = getattr(product, "ncm", "") if product is not None else ""
    raw_code = getattr(product, "code", "") if product is not None else getattr(line, "code", "")
    raw_unit = getattr(product, "unit", "") if product is not None else ""
    raw_origin = getattr(product, "origin_cst", 0) if product is not None else 0
    raw_cest = getattr(product, "cest", "") if product is not None else ""
    description = str(getattr(line, "description", "") or getattr(product, "name", "") or "Produto")[:120]

    return ProductEmissionLine(
        description=description,
        code=str(raw_code or "").strip()[:60],
        ncm=_normalize_ncm(raw_ncm),
        cest=str(raw_cest or "").strip(),
        unit=_unit_for_api(str(raw_unit or "")),
        origin=int(raw_origin or 0),
        quantity=quantity,
        base_total=base_total,
    )


def _build_preview_validation_message(line: Any) -> str | None:
    quantity = Decimal(getattr(line, "quantity", 0) or 0)
    base_total = _quantize_money(Decimal(getattr(getattr(line, "raw_total", None), "amount", 0) or 0))
    if quantity <= 0 or base_total <= 0:
        return None

    product = getattr(line, "source_object", None)
    if product is None:
        return "A OS possui item de peca local sem cadastro fiscal completo. Cadastre o produto para emitir Nota Fiscal."

    product_name = str(getattr(product, "name", "") or getattr(line, "description", "") or "Produto").strip() or "Produto"
    ncm = _normalize_ncm(getattr(product, "ncm", ""))
    if len(ncm) != 8:
        return f"Produto '{product_name}' sem NCM valido para emissao de Nota Fiscal."

    code = str(getattr(product, "code", "") or "").strip()
    if not code:
        return f"Produto '{product_name}' sem codigo para emissao de Nota Fiscal."

    return None


def build_nfe_preview_warning_messages(*, workorder: WorkOrder, persisted_slider: int | None = None, slider_override: int | None = None) -> list[str]:
    snapshot = build_emission_pricing_snapshot_for_workorder(
        workorder=workorder,
        persisted_slider=persisted_slider,
        slider_override=slider_override,
    )
    warnings: list[str] = []
    seen_messages: set[str] = set()

    for line in snapshot.product_lines:
        warning_message = _build_preview_validation_message(line)
        if not warning_message or warning_message in seen_messages:
            continue
        seen_messages.add(warning_message)
        warnings.append(warning_message)

    return warnings


def build_nfe_preview_warning_message(*, workorder: WorkOrder) -> str:
    preview_warnings = build_nfe_preview_warning_messages(workorder=workorder)
    return preview_warnings[0] if preview_warnings else ""


def _format_decimal(value: Decimal, *, places: int) -> str:
    quant = Decimal("1") if places == 0 else Decimal(f"0.{'0' * (places - 1)}1")
    normalized = value.quantize(quant, rounding=ROUND_HALF_UP)
    return f"{normalized:.{places}f}"


def _format_quantity(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return _format_decimal(value, places=4)


def _build_unit_price_for_api(*, allocated_total: Decimal, quantity: Decimal) -> Decimal:
    if quantity <= 0:
        raise NfeEmissionError("Quantidade invalida ao montar item da Nota Fiscal.")

    return (allocated_total / quantity).quantize(Decimal("0.01"), rounding=ROUND_UP)


def _build_payment_payload(*, workorder: WorkOrder, total_value: Decimal, discount_value: Decimal) -> dict[str, Any]:
    payment = workorder.payments.order_by("id").first()

    payment_indicator = 0
    if payment is not None:
        payment_indicator = 1 if int(payment.installments_count or 1) > 1 else 0

    return {
        "pagamento": payment_indicator,
        "presenca": 2,
        "modalidade_frete": 9,
        "desconto": _format_decimal(discount_value, places=2),
        "total": _format_decimal(_quantize_money(total_value), places=2),
    }


def _apply_additional_information_to_nfe_payload(*, payload: dict[str, Any], nfe_request: NfeRequest) -> None:
    additional_information = str(getattr(nfe_request, "additional_information", "") or "").strip()
    if not additional_information:
        return

    pedido_payload = payload.get("pedido")
    if not isinstance(pedido_payload, dict):
        pedido_payload = {}
        payload["pedido"] = pedido_payload
    pedido_payload["informacoes_complementares"] = additional_information


def _apply_transport_to_nfe_payload(*, payload: dict[str, Any], nfe_request: NfeRequest) -> None:
    try:
        freight_mode, transport_payload = build_webmania_transport_payload(
            freight_mode=getattr(nfe_request, "freight_mode", 9),
            snapshot=getattr(nfe_request, "transport_snapshot", {}),
        )
    except NfeTransportValidationError as exc:
        raise NfeEmissionError(str(exc)) from exc

    if freight_mode == 9:
        return

    pedido_payload = payload.get("pedido")
    if not isinstance(pedido_payload, dict):
        raise NfeEmissionError("Pedido invalido ao aplicar dados de transporte na Nota Fiscal.")
    pedido_payload["modalidade_frete"] = freight_mode
    if transport_payload:
        payload["transporte"] = transport_payload


def _build_nfe_products_payload(*, nfe_request: NfeRequest, slider_override: int | None = None) -> tuple[list[dict[str, Any]], Decimal, SliderAllocation, Decimal]:
    workorder = nfe_request.workorder
    allocation = build_slider_allocation_for_workorder(
        workorder=workorder,
        persisted_slider=getattr(nfe_request, "pricing_slider", None),
        slider_override=slider_override,
    )

    if allocation.products_target <= 0:
        raise NfeEmissionError("A configuracao atual do slider direciona 100% da venda para servicos. Utilize Nota Fiscal de Servico para esta emissao.")

    lines = _extract_product_lines(workorder=workorder)
    if not lines:
        raise NfeEmissionError("A OS selecionada nao possui pecas elegiveis para emissao de Nota Fiscal.")

    try:
        allocated_totals = distribute_total_proportionally(base_values=[line.base_total for line in lines], target_total=allocation.products_target)
    except ValueError as exc:
        raise NfeEmissionError("Nao foi possivel distribuir o valor da Nota Fiscal proporcionalmente entre as pecas.") from exc

    # Calcula o desconto proporcional para produtos conforme o discount_type da WorkOrder
    # (usado apenas no pedido.desconto; os valores unitários dos produtos permanecem brutos)
    product_discount = compute_product_discount_for_nfe(
        workorder=workorder,
        products_target=allocation.products_target,
        services_target=allocation.services_target,
        discount_type_override=str(getattr(nfe_request, "discount_type_override", "") or ""),
    )

    products_payload: list[dict[str, Any]] = []
    tax_class_reference = str(nfe_request.tax_class or "").strip()
    for line, allocated_total in zip(lines, allocated_totals, strict=False):
        if allocated_total <= 0:
            continue

        if line.quantity <= 0:
            continue

        unit_price = _build_unit_price_for_api(allocated_total=allocated_total, quantity=line.quantity)
        product_payload: dict[str, Any] = {
            "nome": line.description,
            "codigo": line.code,
            "ncm": line.ncm,
            "quantidade": _format_quantity(line.quantity),
            "unidade": line.unit,
            "origem": line.origin,
            "subtotal": _format_decimal(unit_price, places=2),
            "total": _format_decimal(allocated_total, places=2),
            "classe_imposto": tax_class_reference,
        }
        if line.cest:
            product_payload["cest"] = line.cest
        products_payload.append(product_payload)

    if not products_payload:
        raise NfeEmissionError("Nao foi possivel montar itens de produto para emissao de Nota Fiscal.")

    return products_payload, allocation.products_target, allocation, product_discount


def build_nfe_payload(*, nfe_request: NfeRequest, request: HttpRequest | None = None, slider_override: int | None = None) -> dict[str, Any]:
    products_payload, _total_products_gross, allocation, product_discount = _build_nfe_products_payload(nfe_request=nfe_request, slider_override=slider_override)

    ambiente = int(getattr(settings, "WEBMANIA_AMBIENT", "2"))

    payload = {
        "ID": str(nfe_request.pk),
        "operacao": 1,
        "natureza_operacao": sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_NATUREZA_OPERACAO", "Venda de mercadoria")) or "Venda de mercadoria",
        "modelo": 1,
        "finalidade": 1,
        "ambiente": ambiente,
        "url_notificacao": build_webmania_webhook_url(request=request),
        "cliente": _build_customer_payload(nfe_request),
        "produtos": products_payload,
        "pedido": _build_payment_payload(workorder=nfe_request.workorder, total_value=Decimal(allocation.products_target), discount_value=product_discount),
    }

    _apply_additional_information_to_nfe_payload(payload=payload, nfe_request=nfe_request)
    _apply_transport_to_nfe_payload(payload=payload, nfe_request=nfe_request)

    logger.info(
        "nfe_payload_built nfe_request_id=%s workshop_id=%s workorder_id=%s slider=%s products_target=%s services_target=%s product_discount=%s discount_type=%s",
        getattr(nfe_request, "pk", None),
        getattr(nfe_request.workshop, "pk", None),
        getattr(nfe_request.workorder, "pk", None),
        allocation.slider,
        str(allocation.products_target),
        str(allocation.services_target),
        str(product_discount),
        nfe_request.workorder.discount_type,
    )
    return payload


def _extract_nfe_preview_url(data: dict[str, Any]) -> str:
    for key in ("danfe", "danfe_simples", "danfe_etiqueta", "pdf", "url"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return ""


def _is_json_content_type(content_type: str) -> bool:
    normalized_content_type = content_type.lower()
    return "application/json" in normalized_content_type or "text/json" in normalized_content_type


def preview_nfe_request(*, nfe_request: NfeRequest, request: HttpRequest | None = None, slider_override: int | None = None) -> dict[str, Any]:
    headers = _build_headers(workshop=nfe_request.workshop)
    emit_url = _build_emit_url()

    _validate_nfe_tax_class(nfe_request=nfe_request, headers=headers)
    _validate_local_ibs_cbs_tax_class(nfe_request=nfe_request)

    payload = build_nfe_payload(nfe_request=nfe_request, request=request, slider_override=slider_override)
    payload["previa_danfe"] = True

    try:
        response = requests.post(emit_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao gerar previa da Nota Fiscal", scope="nfe")
        raise NfeEmissionError(message) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise NfeEmissionError("Resposta invalida da API de previa da Nota Fiscal.") from exc

    if not isinstance(data, dict):
        raise NfeEmissionError("Resposta invalida da API de previa da Nota Fiscal.")

    error_message = extract_webmania_error_message(data.get("error") or data.get("msg") or data.get("message"), scope="nfe")
    if error_message:
        raise NfeEmissionError(error_message)

    preview_url = _extract_nfe_preview_url(data)
    if not preview_url:
        raise NfeEmissionError("A API da Webmania nao retornou a URL da previa da Nota Fiscal.")

    return {**data, "preview_url": preview_url}


def download_nfe_preview_document(*, nfe_request: NfeRequest, request: HttpRequest | None = None, slider_override: int | None = None) -> DownloadedWebmaniaDocument:
    headers = _build_headers(workshop=nfe_request.workshop)
    emit_url = _build_emit_url()

    _validate_nfe_tax_class(nfe_request=nfe_request, headers=headers)
    _validate_local_ibs_cbs_tax_class(nfe_request=nfe_request)

    payload = build_nfe_payload(nfe_request=nfe_request, request=request, slider_override=slider_override)
    payload["previa_danfe"] = True

    try:
        response = requests.post(emit_url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao gerar previa da Nota Fiscal", scope="nfe")
        raise NfeEmissionError(message) from exc

    content_type = str(response.headers.get("Content-Type") or "application/pdf")
    if not _is_json_content_type(content_type):
        return DownloadedWebmaniaDocument(
            content=response.content,
            content_type=content_type,
            content_disposition=str(response.headers.get("Content-Disposition") or ""),
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise NfeEmissionError("Resposta invalida da API de previa da Nota Fiscal.") from exc

    if not isinstance(data, dict):
        raise NfeEmissionError("Resposta invalida da API de previa da Nota Fiscal.")

    error_message = extract_webmania_error_message(data.get("error") or data.get("msg") or data.get("message"), scope="nfe")
    if error_message:
        raise NfeEmissionError(error_message)

    preview_url = _extract_nfe_preview_url(data)
    if not preview_url:
        raise NfeEmissionError("A API da Webmania nao retornou o PDF da previa da Nota Fiscal.")

    try:
        return download_webmania_document(workshop=nfe_request.workshop, url=preview_url)
    except WebmaniaDocumentDownloadError as exc:
        raise NfeEmissionError(str(exc)) from exc


def emit_nfe_request(*, nfe_request: NfeRequest, request: HttpRequest | None = None, slider_override: int | None = None) -> dict[str, Any]:
    headers = _build_headers(workshop=nfe_request.workshop)
    emit_url = _build_emit_url()

    _validate_nfe_tax_class(nfe_request=nfe_request, headers=headers)
    _validate_local_ibs_cbs_tax_class(nfe_request=nfe_request)

    try:
        reserve_nfe_request_number(nfe_request=nfe_request)
    except EmissionNumberReservationError as exc:
        raise NfeEmissionError(str(exc)) from exc

    payload = build_nfe_payload(nfe_request=nfe_request, request=request, slider_override=slider_override)
    try:
        attempt = begin_emission_attempt(
            workshop=nfe_request.workshop,
            document_kind="nfe",
            request_model="NfeRequest",
            request_id=int(nfe_request.pk),
            request_payload=payload,
        )
    except FiscalEmissionAttemptBlocked as exc:
        raise NfeEmissionError(str(exc)) from exc

    try:
        mark_attempt_sent(attempt=attempt)
        response = requests.post(emit_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = build_webmania_request_exception_message(exc, default="Timeout ao emitir Nota Fiscal; estado remoto incerto", scope="nfe")
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        logger.warning("nfe_emission_uncertain nfe_request_id=%s workshop_id=%s error=%s", nfe_request.pk, nfe_request.workshop_id, message)
        raise NfeEmissionError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao emitir Nota Fiscal", scope="nfe")
        mark_attempt_failed(attempt=attempt, error_message=message)
        raise NfeEmissionError(message) from exc

    try:
        data = response.json()
    except ValueError as exc:
        mark_attempt_uncertain(attempt=attempt, error_message="Resposta invalida da API de emissao de Nota Fiscal.")
        raise NfeEmissionError("Resposta invalida da API de emissao de Nota Fiscal.") from exc

    if not isinstance(data, dict):
        mark_attempt_uncertain(attempt=attempt, error_message="Resposta invalida da API de emissao de Nota Fiscal.")
        raise NfeEmissionError("Resposta invalida da API de emissao de Nota Fiscal.")

    error_message = extract_webmania_error_message(data.get("error") or data.get("msg") or data.get("message"), scope="nfe")
    if error_message:
        mark_attempt_failed(attempt=attempt, error_message=error_message, response_payload=data)
        raise NfeEmissionError(error_message)

    if not data.get("uuid") and str(data.get("modelo") or "").lower() != "nfe":
        message = extract_webmania_error_message(data, scope="nfe")
        mark_attempt_uncertain(attempt=attempt, error_message=message or "Resposta da API sem dados de identificacao da Nota Fiscal.")
        raise NfeEmissionError(message or "Resposta da API sem dados de identificacao da Nota Fiscal.")

    mark_attempt_succeeded(attempt=attempt, response_payload=data)
    return data


def cancel_nfe_document(*, workshop, access_key: str, event_uuid: str, reason: str) -> dict[str, Any]:
    headers = _build_headers(workshop=workshop)
    cancel_url = _build_cancel_url()

    payload: dict[str, str] = {"motivo": str(reason or "").strip()}
    access_key_value = str(access_key or "").strip()
    event_uuid_value = str(event_uuid or "").strip()

    if access_key_value:
        payload["chave"] = access_key_value
    elif event_uuid_value:
        payload["uuid"] = event_uuid_value
    else:
        raise NfeEmissionError("Nao foi possivel identificar a Nota Fiscal para cancelamento.")

    try:
        response = requests.put(cancel_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao cancelar Nota Fiscal", scope="nfe")
        raise NfeEmissionError(message) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise NfeEmissionError("Resposta invalida da API de cancelamento de Nota Fiscal.") from exc

    if not isinstance(data, dict):
        raise NfeEmissionError("Resposta invalida da API de cancelamento de Nota Fiscal.")

    error_message = extract_webmania_error_message(data.get("error") or data.get("msg") or data.get("message"), scope="nfe")
    if error_message:
        raise NfeEmissionError(error_message)

    return data


def invalidate_nfe_number(*, workshop, number: int, reason: str, series: int, model: int = 1) -> dict[str, Any]:
    headers = _build_headers(workshop=workshop)
    invalidate_url = _build_invalidate_url()

    payload: dict[str, Any] = {
        "sequencia": f"{int(number)}-{int(number)}",
        "motivo": str(reason or "").strip(),
        "ambiente": int(getattr(settings, "WEBMANIA_AMBIENT", "2") or 2),
        "serie": str(series),
        "modelo": int(model),
    }

    try:
        response = requests.put(invalidate_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao inutilizar numeracao da Nota Fiscal", scope="nfe")
        raise NfeEmissionError(message) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise NfeEmissionError("Resposta invalida da API de inutilizacao da Nota Fiscal.") from exc

    if not isinstance(data, dict):
        raise NfeEmissionError("Resposta invalida da API de inutilizacao da Nota Fiscal.")

    error_message = extract_webmania_error_message(data.get("error") or data.get("msg") or data.get("message"), scope="nfe")
    if error_message:
        raise NfeEmissionError(error_message)

    return data


def _ensure_log_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"raw": value}


def map_nfe_item_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "uuid": payload.get("uuid"),
        "model": payload.get("modelo") or "nfe",
        "status": normalize_nfe_status(payload.get("status") or "processando"),
        "reason": payload.get("motivo") or "",
        "number": str(payload.get("nfe") or ""),
        "series": str(payload.get("serie") or ""),
        "receipt": str(payload.get("recibo") or ""),
        "access_key": str(payload.get("chave") or ""),
        "xml_url": str(payload.get("xml") or ""),
        "danfe_url": str(payload.get("danfe") or ""),
        "danfe_simple_url": str(payload.get("danfe_simples") or ""),
        "danfe_label_url": str(payload.get("danfe_etiqueta") or ""),
        "log_payload": _ensure_log_payload(payload.get("log")),
    }


def apply_nfe_item_payload(
    *,
    item: NfeItem,
    response_payload: dict[str, Any],
    webhook_received_at=None,
    reconciled_at=None,
) -> NfeItem:
    mapped_payload = map_nfe_item_payload(response_payload)
    for key, value in mapped_payload.items():
        if key == "uuid":
            continue
        setattr(item, key, value)
    item.raw_payload = response_payload
    if webhook_received_at is not None:
        item.last_webhook_at = webhook_received_at
    if reconciled_at is not None:
        item.last_reconciled_at = reconciled_at
    item.last_sync_error = ""
    item.save()

    if item.request:
        item.request.update_status_based_on_request(response_payload.get("status"))

    return item


def _replay_pending_nfe_webhooks_for_uuid(*, event_uuid: str) -> None:
    if not event_uuid:
        return

    from apps.core.infrastructure.services.webmania.webmania_webhooks import process_pending_webhook_events

    process_pending_webhook_events(model="nfe", event_uuid=event_uuid)


def sync_nfe_emission_response(*, nfe_request: NfeRequest, response_payload: dict[str, Any]) -> None:
    mapped_payload = map_nfe_item_payload(response_payload)
    if not str(mapped_payload.get("number") or "").strip() and nfe_request.reserved_number is not None:
        mapped_payload["number"] = str(nfe_request.reserved_number)
    if not str(mapped_payload.get("series") or "").strip() and nfe_request.reserved_series is not None:
        mapped_payload["series"] = str(nfe_request.reserved_series)
    nfe_uuid = mapped_payload.pop("uuid", None)
    if not nfe_uuid:
        return

    with transaction.atomic():
        NfeItem.objects.update_or_create(
            workorder=nfe_request.workorder,
            uuid=nfe_uuid,
            defaults={
                "workshop": nfe_request.workshop,
                "request": nfe_request,
                "raw_payload": response_payload,
                "last_sync_error": "",
                **mapped_payload,
            },
        )

    _replay_pending_nfe_webhooks_for_uuid(event_uuid=str(nfe_uuid))


def build_nfe_preview_rows(
    *,
    workorder: WorkOrder,
    persisted_slider: int | None = None,
    slider_override: int | None = None,
) -> tuple[list[dict[str, Any]], SliderAllocation]:
    snapshot = build_emission_pricing_snapshot_for_workorder(
        workorder=workorder,
        persisted_slider=persisted_slider,
        slider_override=slider_override,
    )
    lines = [preview_line for line in snapshot.product_lines if (preview_line := _build_snapshot_preview_product_line(line)) is not None]
    allocation = build_slider_allocation_for_workorder(
        workorder=workorder,
        persisted_slider=persisted_slider,
        slider_override=slider_override,
    )

    target_totals = distribute_total_proportionally(base_values=[line.base_total for line in lines], target_total=allocation.products_target) if lines and allocation.products_target > 0 else [Decimal("0.00") for _ in lines]

    preview_rows: list[dict[str, Any]] = []
    for line, target_total in zip(lines, target_totals, strict=False):
        target_unit_value = (target_total / Decimal(line.quantity)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if line.quantity > 0 else Decimal("0.00")
        preview_rows.append(
            {
                "description": line.description,
                "code": line.code,
                "ncm": line.ncm,
                "quantity": line.quantity,
                "base_total": line.base_total,
                "target_unit_value": target_unit_value,
                "target_total": target_total,
            }
        )

    return preview_rows, allocation
