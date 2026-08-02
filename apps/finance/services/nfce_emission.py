from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest

from apps.catalog.models.products import Product
from apps.finance.models.finance import FiscalDocument, FiscalDocumentOrigin, FiscalDocumentPurpose, FiscalDocumentStatus, FiscalDocumentType, FiscalEmissionAttemptStatus, FiscalEmissionDocumentKind, FiscalEmissionOperationType, WebmaniaCompany
from apps.core.infrastructure.services.webmania.emission import build_webmania_webhook_url
from apps.finance.services.fiscal_attempts import FiscalEmissionAttemptBlocked, begin_emission_attempt, build_fiscal_document_operation_idempotency_key, build_payload_hash, mark_attempt_failed, mark_attempt_sent, mark_attempt_succeeded, mark_attempt_uncertain, sanitize_fiscal_payload
from apps.finance.services.ibs_cbs import IbsCbsConfigurationError, require_ready_tax_class_for_normal_emission
from apps.core.infrastructure.services.webmania.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting, should_use_global_webmania_auth
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message
from apps.core.infrastructure.services.webmania.webmania_secrets import decrypt_secret


logger = logging.getLogger(__name__)


class NfceEmissionError(Exception):
    pass


def _build_headers(*, workshop=None) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfceEmissionError(str(exc)) from exc


def _build_emit_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFCE_EMIT_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/emissao/"


def _build_consulta_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_CONSULTA_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/consulta/"


def _company_for_workshop(*, workshop: Any) -> WebmaniaCompany | None:
    return WebmaniaCompany.objects.filter(workshop=workshop).first()


def _require_company_field(company: WebmaniaCompany, field_name: str, label: str) -> Any:
    value = getattr(company, field_name, None)
    if field_name in {"nfce_id_csc", "nfce_codigo_csc", "nfce_id_csc_dev", "nfce_codigo_csc_dev"}:
        value = decrypt_secret(value)
    if value in (None, ""):
        raise NfceEmissionError(f"Configure {label} da NFC-e antes de emitir.")
    return value


def validate_nfce_configuration(*, workshop: Any, environment: int) -> WebmaniaCompany:
    company = _company_for_workshop(workshop=workshop)
    if company is None:
        raise NfceEmissionError("Configure a empresa emissora da oficina antes de emitir NFC-e.")
    if not str(company.webmania_company_id or "").strip():
        raise NfceEmissionError("Vincule a empresa emissora da oficina antes de emitir NFC-e.")
    if not company.nfce_enabled:
        raise NfceEmissionError("Habilite a NFC-e na configuração fiscal da oficina antes de emitir.")

    _build_headers(workshop=workshop)

    _require_company_field(company, "nfce_serie", "a serie")
    if int(environment) == 1:
        _require_company_field(company, "nfce_numero", "o proximo número de producao")
        _require_company_field(company, "nfce_id_csc", "o ID CSC de producao")
        _require_company_field(company, "nfce_codigo_csc", "o código CSC de producao")
    else:
        _require_company_field(company, "nfce_numero_dev", "o proximo número de homologação")
        _require_company_field(company, "nfce_id_csc_dev", "o ID CSC de homologação")
        _require_company_field(company, "nfce_codigo_csc_dev", "o código CSC de homologação")
    return company


def _decimal(value: Any, *, field_name: str, required_positive: bool = True) -> Decimal:
    raw_value = str(value if value is not None else "").strip()
    if not raw_value:
        raise NfceEmissionError(f"Informe {field_name}.")
    try:
        decimal_value = Decimal(raw_value.replace(",", "."))
    except InvalidOperation as exc:
        raise NfceEmissionError(f"Informe {field_name} válido.") from exc
    if required_positive and decimal_value <= 0:
        raise NfceEmissionError(f"{field_name} deve ser maior que zero.")
    if decimal_value < 0:
        raise NfceEmissionError(f"{field_name} não pode ser negativo.")
    return decimal_value


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _quantity(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")


def _normalize_ncm(raw_value: Any) -> str:
    return "".join(char for char in str(raw_value or "") if char.isdigit())


def _unit_for_api(raw_unit: Any) -> str:
    normalized = str(raw_unit or "").strip().upper()
    return {"UND": "UN"}.get(normalized, normalized or "UN")


def _build_product_payload(*, workshop: Any, item: dict[str, Any]) -> tuple[dict[str, Any], Decimal]:
    product_id = item.get("product_id") or item.get("produto_id") or item.get("id")
    if not product_id:
        raise NfceEmissionError("Informe o produto da NFC-e.")
    try:
        product = Product.objects.get(pk=int(product_id), workshop=workshop, is_active=True)
    except Product.DoesNotExist as exc:
        raise NfceEmissionError("Produto não encontrado na oficina ativa para NFC-e.") from exc
    quantity = _decimal(item.get("quantidade") or item.get("quantity"), field_name="quantidade")
    unit_value = _decimal(item.get("valor_unitario") or item.get("unit_value") or item.get("subtotal"), field_name="valor unitário")
    total_value = (quantity * unit_value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    ncm = _normalize_ncm(product.ncm)
    if len(ncm) != 8:
        raise NfceEmissionError(f"Produto '{product.name}' sem NCM válido para NFC-e.")
    product_code = str(product.code or "").strip()
    if not product_code:
        raise NfceEmissionError(f"Produto '{product.name}' sem código para NFC-e.")
    tax_class = str(item.get("classe_imposto") or item.get("tax_class") or "").strip()
    if not tax_class:
        raise NfceEmissionError(f"Informe classe de imposto para o produto '{product.name}'.")
    try:
        require_ready_tax_class_for_normal_emission(workshop=workshop, reference=tax_class, product_label=f"produto '{product.name}'")
    except IbsCbsConfigurationError as exc:
        raise NfceEmissionError(str(exc)) from exc
    payload: dict[str, Any] = {
        "nome": str(product.name or "Produto")[:120],
        "codigo": product_code[:60],
        "ncm": ncm,
        "quantidade": _quantity(quantity),
        "unidade": _unit_for_api(product.unit),
        "origem": int(product.origin_cst or 0),
        "subtotal": _money(unit_value),
        "total": _money(total_value),
        "classe_imposto": tax_class,
    }
    if product.cest:
        payload["cest"] = str(product.cest).strip()
    return payload, total_value


def _build_products_payload(*, workshop: Any, products: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Decimal]:
    if not products:
        raise NfceEmissionError("Informe ao menos um produto para emitir NFC-e.")
    payloads: list[dict[str, Any]] = []
    total = Decimal("0.00")
    for item in products:
        if not isinstance(item, dict):
            raise NfceEmissionError("Produtos da NFC-e devem ser objetos JSON.")
        product_payload, product_total = _build_product_payload(workshop=workshop, item=item)
        payloads.append(product_payload)
        total += product_total
    return payloads, total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _build_payment_payload(*, total_value: Decimal, payment_method: str) -> dict[str, Any]:
    normalized_method = str(payment_method or "01").strip()
    allowed_methods = {"01", "03", "04", "17", "99"}
    if normalized_method not in allowed_methods:
        raise NfceEmissionError("Forma de pagamento inválida para NFC-e simples.")
    payload: dict[str, Any] = {
        "pagamento": 0,
        "forma_pagamento": normalized_method,
        "valor_pagamento": _money(total_value),
        "presenca": 1,
        "modalidade_frete": 9,
        "total": _money(total_value),
    }
    if normalized_method == "99":
        payload["desc_pagamento"] = "Outros"
    return payload


def _normalize_customer_payload(customer: dict[str, Any] | None) -> dict[str, Any]:
    if not customer:
        return {}
    if not isinstance(customer, dict):
        raise NfceEmissionError("Consumidor deve ser um objeto JSON.")
    return sanitize_fiscal_payload(customer)


def build_nfce_payload(
    *,
    workshop: Any,
    environment: int,
    natureza_operacao: str,
    products: list[dict[str, Any]],
    customer: dict[str, Any] | None = None,
    payment_method: str = "01",
    request: HttpRequest | None = None,
) -> dict[str, Any]:
    validate_nfce_configuration(workshop=workshop, environment=int(environment))
    products_payload, total_value = _build_products_payload(workshop=workshop, products=products)
    payload: dict[str, Any] = {
        "ID": "",
        "operacao": 1,
        "natureza_operacao": str(natureza_operacao or "").strip() or "Venda ao consumidor",
        "modelo": 2,
        "finalidade": 1,
        "ambiente": int(environment),
        "url_notificacao": build_webmania_webhook_url(request=request),
        "produtos": products_payload,
        "pedido": _build_payment_payload(total_value=total_value, payment_method=payment_method),
    }
    customer_payload = _normalize_customer_payload(customer)
    if customer_payload:
        payload["cliente"] = customer_payload
    for forbidden_key in ("chave", "uuid", "impostos", "ibs", "cbs", "agropecuario", "dfe_referenciado", "tipo_credito", "tipo_debito", "nfce_referenciada", "contingencia", "offline"):
        payload.pop(forbidden_key, None)
    return payload


def create_nfce_draft(
    *,
    workshop: Any,
    requested_by: Any | None = None,
    environment: int,
    natureza_operacao: str,
    products: list[dict[str, Any]],
    customer: dict[str, Any] | None = None,
    payment_method: str = "01",
    legal_confirmation: bool = False,
    request: HttpRequest | None = None,
) -> FiscalDocument:
    if not legal_confirmation:
        raise NfceEmissionError("Confirme explicitamente a emissão da NFC-e.")
    payload = build_nfce_payload(workshop=workshop, environment=environment, natureza_operacao=natureza_operacao, products=products, customer=customer, payment_method=payment_method, request=request)
    with transaction.atomic():
        document = FiscalDocument.objects.create(
            workshop=workshop,
            account=getattr(workshop, "account", None),
            document_type=FiscalDocumentType.NFCE,
            origin=FiscalDocumentOrigin.MANUAL,
            purpose=FiscalDocumentPurpose.NORMAL,
            environment=str(int(environment)),
            status=FiscalDocumentStatus.PROCESSING,
            remote_status=FiscalEmissionAttemptStatus.STARTED,
            request_payload=sanitize_fiscal_payload(payload),
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
        )
        document.request_payload["ID"] = f"nfce:{document.pk}"
        document.save(update_fields=["request_payload", "atualizado_em"])
        return document


def _is_failed_response(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    return status in {"erro", "error", "falha", "failed", "reprovado", "rejeitado"}


def _status_from_payload(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip().lower()
    if status in {FiscalDocumentStatus.APPROVED, FiscalDocumentStatus.REPROVED, FiscalDocumentStatus.CANCELED, FiscalDocumentStatus.DENIED, FiscalDocumentStatus.CONTINGENCY, FiscalDocumentStatus.PROCESSING}:
        return status
    if _is_failed_response(payload):
        return FiscalDocumentStatus.REPROVED
    return FiscalDocumentStatus.APPROVED if str(payload.get("uuid") or payload.get("chave") or "").strip() else FiscalDocumentStatus.PROCESSING


def apply_nfce_document_payload(*, document: FiscalDocument, response_payload: dict[str, Any]) -> FiscalDocument:
    document.response_payload = sanitize_fiscal_payload(response_payload)
    document.status = _status_from_payload(response_payload)
    document.remote_status = str(response_payload.get("status") or document.remote_status or "").strip()
    document.remote_uuid = str(response_payload.get("uuid") or document.remote_uuid or "").strip()
    document.access_key = str(response_payload.get("chave") or document.access_key or "").strip()
    document.number = str(response_payload.get("nfe") or response_payload.get("numero") or document.number or "").strip()
    document.series = str(response_payload.get("serie") or document.series or "").strip()
    document.receipt = str(response_payload.get("recibo") or document.receipt or "").strip()
    document.xml_url = str(response_payload.get("xml") or document.xml_url or "").strip()
    document.danfe_url = str(response_payload.get("danfe") or response_payload.get("danfe_simples") or response_payload.get("danfe_etiqueta") or document.danfe_url or "").strip()
    document.save(update_fields=["response_payload", "status", "remote_status", "remote_uuid", "access_key", "number", "series", "receipt", "xml_url", "danfe_url", "atualizado_em"])
    return document


def _mark_document_uncertain(*, document: FiscalDocument, error_message: str) -> None:
    document.status = FiscalDocumentStatus.UNCERTAIN
    document.response_payload = sanitize_fiscal_payload({"error": error_message})
    document.remote_status = FiscalDocumentStatus.UNCERTAIN
    document.save(update_fields=["status", "response_payload", "remote_status", "atualizado_em"])


def _assert_transmittable(*, document: FiscalDocument) -> None:
    if document.document_type != FiscalDocumentType.NFCE or document.origin != FiscalDocumentOrigin.MANUAL or document.purpose != FiscalDocumentPurpose.NORMAL:
        raise NfceEmissionError("Documento fiscal inválido para transmissão de NFC-e.")
    existing_attempt = document.emission_attempts.filter(operation_type=FiscalEmissionOperationType.NFCE_EMISSION).order_by("-pk").first()
    if existing_attempt is None:
        return
    if existing_attempt.status == FiscalEmissionAttemptStatus.UNCERTAIN:
        raise NfceEmissionError("Já existe tentativa de NFC-e em estado remoto incerto. Reconcilie antes de tentar novamente.")
    if existing_attempt.status in {FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.SUCCEEDED}:
        raise NfceEmissionError("Esta intencao de NFC-e já possui envio remoto registrado.")
    raise NfceEmissionError("Esta intencao de NFC-e já possui tentativa fiscal registrada.")


def transmit_nfce_document(*, document: FiscalDocument) -> FiscalDocument:
    with transaction.atomic():
        locked_document = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=document.pk)
        _assert_transmittable(document=locked_document)
        validate_nfce_configuration(workshop=locked_document.workshop, environment=int(locked_document.environment or 2))
        payload = dict(locked_document.request_payload or {})
        idempotency_key = build_fiscal_document_operation_idempotency_key(workshop_id=locked_document.workshop_id, derived_document_id=locked_document.pk, operation_type=FiscalEmissionOperationType.NFCE_EMISSION, request_generation=1)
        try:
            attempt = begin_emission_attempt(
                workshop=locked_document.workshop,
                document_kind=FiscalEmissionDocumentKind.NFCE,
                operation_type=FiscalEmissionOperationType.NFCE_EMISSION,
                request_model=FiscalDocument.__name__,
                request_id=locked_document.pk,
                fiscal_document=locked_document,
                idempotency_key=idempotency_key,
                request_payload=payload,
                payload_hash=build_payload_hash(payload),
            )
        except FiscalEmissionAttemptBlocked as exc:
            raise NfceEmissionError(str(exc)) from exc

    headers = _build_headers(workshop=locked_document.workshop)
    mark_attempt_sent(attempt=attempt)
    try:
        response = requests.post(_build_emit_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao emitir NFC-e; estado remoto incerto."
        logger.warning("nfce_emission_timeout", extra={"fiscal_document_id": locked_document.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_document_uncertain(document=locked_document, error_message=message)
        raise NfceEmissionError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao emitir NFC-e", scope="nfe")
        mark_attempt_failed(attempt=attempt, error_message=message)
        locked_document.status = FiscalDocumentStatus.REPROVED
        locked_document.response_payload = sanitize_fiscal_payload({"error": message})
        locked_document.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfceEmissionError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta inválida ao emitir NFC-e; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_document_uncertain(document=locked_document, error_message=message)
        raise NfceEmissionError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta inválida ao emitir NFC-e; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_document_uncertain(document=locked_document, error_message=message)
        raise NfceEmissionError(message)

    locked_document = apply_nfce_document_payload(document=locked_document, response_payload=response_payload)
    if _is_failed_response(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or "NFC-e rejeitada."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfceEmissionError(message)
    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    return locked_document


def create_and_emit_nfce(**kwargs: Any) -> FiscalDocument:
    document = create_nfce_draft(**kwargs)
    return transmit_nfce_document(document=document)


def consult_nfce_document(*, document: FiscalDocument) -> dict[str, Any]:
    params: dict[str, str] = {}
    if str(document.remote_uuid or "").strip():
        params["uuid"] = str(document.remote_uuid).strip()
    elif str(document.access_key or "").strip():
        params["chave"] = str(document.access_key).strip()
    else:
        attempt = document.emission_attempts.exclude(remote_uuid="").order_by("-pk").first()
        if attempt is not None:
            params["uuid"] = str(attempt.remote_uuid).strip()
    if not params:
        raise NfceEmissionError("Não foi possível consultar a NFC-e sem UUID ou chave de acesso.")
    try:
        response = requests.get(_build_consulta_url(), params=params, headers=_build_headers(workshop=document.workshop), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao consultar NFC-e", scope="nfe")
        raise NfceEmissionError(message) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise NfceEmissionError("Resposta inválida da API de consulta da NFC-e.") from exc
    if not isinstance(payload, dict):
        raise NfceEmissionError("Resposta inválida da API de consulta da NFC-e.")
    error_message = extract_webmania_error_message(payload.get("error") or payload.get("msg") or payload.get("message"), scope="nfe")
    if error_message:
        raise NfceEmissionError(error_message)
    return payload


def reconcile_nfce_document(*, document: FiscalDocument) -> FiscalDocument:
    payload = consult_nfce_document(document=document)
    document = apply_nfce_document_payload(document=document, response_payload=payload)
    document.refresh_from_db()
    return document


def resolve_nfce_document_for_webhook(*, payload: dict[str, Any]) -> FiscalDocument | None:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    queryset = FiscalDocument.objects.filter(document_type=FiscalDocumentType.NFCE, origin=FiscalDocumentOrigin.MANUAL, purpose=FiscalDocumentPurpose.NORMAL)
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(access_key=access_key) | Q(emission_attempts__remote_key=access_key)
    if not event_uuid and not access_key:
        return None
    matches = list(queryset.filter(filters).distinct().order_by("-pk")[:2])
    if len(matches) != 1:
        return None
    return matches[0]


def is_ambiguous_nfce_webhook(*, payload: dict[str, Any]) -> bool:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    if not event_uuid and not access_key:
        return False
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(access_key=access_key) | Q(emission_attempts__remote_key=access_key)
    return FiscalDocument.objects.filter(document_type=FiscalDocumentType.NFCE, origin=FiscalDocumentOrigin.MANUAL, purpose=FiscalDocumentPurpose.NORMAL).filter(filters).distinct().values("pk")[:2].count() > 1
