from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentComplementaryType,
    FiscalDocumentLink,
    FiscalDocumentLinkRole,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalEmissionAttemptStatus,
    FiscalEmissionDocumentKind,
    FiscalEmissionOperationType,
    NfeItem,
    NfeItemStatus,
)
from apps.finance.services.emission import build_webmania_webhook_url
from apps.finance.services.fiscal_attempts import FiscalEmissionAttemptBlocked, begin_emission_attempt, build_fiscal_document_operation_idempotency_key, build_payload_hash, mark_attempt_failed, mark_attempt_sent, mark_attempt_succeeded, mark_attempt_uncertain, sanitize_fiscal_payload
from apps.finance.services.ibs_cbs import IbsCbsConfigurationError, build_ibs_cbs_payload_from_values
from apps.finance.services.nfe_events import ensure_fiscal_document_for_nfe_item
from apps.finance.services.nfe_returns import validate_access_key
from apps.finance.services.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting, should_use_global_webmania_auth
from apps.finance.services.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)
IBS_CBS_CONSERVATIVE_CUTOFF_DATE = date(2026, 1, 1)


class NfeComplementaryError(Exception):
    pass


def _build_headers(*, workshop=None) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfeComplementaryError(str(exc)) from exc


def _build_complementary_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_COMPLEMENTARY_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/complementar/"


def _build_consulta_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_CONSULTA_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/consulta/"


def _decimal(value: Any, *, field_name: str) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", "."))
    except InvalidOperation as exc:
        raise NfeComplementaryError(f"Informe valor valido para {field_name}.") from exc


def _decimal_to_payload(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def is_local_nfe_eligible_for_complementary(item: NfeItem | None) -> bool:
    if item is None:
        return False
    if str(getattr(item, "status", "")).strip().lower() != NfeItemStatus.aprovado:
        return False
    return bool(str(getattr(item, "access_key", "") or "").strip() or str(getattr(item, "uuid", "") or "").strip())


def _extract_products_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    products = payload.get("produtos")
    if isinstance(products, list):
        return [product for product in products if isinstance(product, dict)]
    nested = payload.get("pedido") if isinstance(payload.get("pedido"), dict) else {}
    nested_products = nested.get("produtos") if isinstance(nested, dict) else None
    if isinstance(nested_products, list):
        return [product for product in nested_products if isinstance(product, dict)]
    return []


def _product_sequence(product: dict[str, Any], *, fallback_index: int | None = None) -> int:
    for key in ("sequencial", "sequencia", "numero_item", "item", "produto", "item_original"):
        value = str(product.get(key) or "").strip()
        if value.isdigit() and int(value) > 0:
            return int(value)
    if fallback_index is not None:
        return fallback_index
    raise NfeComplementaryError("Cada item complementar deve informar o sequencial fiscal original.")


def _original_product_by_sequence(document: FiscalDocument, sequence: int) -> dict[str, Any]:
    payload_sources: list[Any] = []
    if document.legacy_nfe_item_id:
        payload_sources.extend([document.legacy_nfe_item.raw_payload, document.legacy_nfe_item.log_payload])
    payload_sources.extend([document.request_payload, document.response_payload])
    for payload in payload_sources:
        products = _extract_products_from_payload(payload)
        for index, product in enumerate(products, start=1):
            try:
                product_sequence = _product_sequence(product, fallback_index=index)
            except NfeComplementaryError:
                continue
            if product_sequence == sequence:
                return dict(product)
    raise NfeComplementaryError("NF-e original nao possui itens fiscais conhecidos para complementar preco/quantidade.")


def _normalize_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        raise NfeComplementaryError("Informe ao menos um item para a nota complementar.")
    normalized: list[dict[str, Any]] = []
    for item in items:
        sequence_value = str(item.get("sequencial") or item.get("item") or "").strip()
        if not sequence_value.isdigit() or int(sequence_value) <= 0:
            raise NfeComplementaryError("Cada item complementar deve informar o sequencial fiscal original.")
        quantity = _decimal(item.get("quantidade_complementar"), field_name="quantidade complementar")
        value = _decimal(item.get("valor_complementar"), field_name="valor complementar")
        if quantity <= 0 and value <= 0:
            raise NfeComplementaryError("Informe quantidade ou valor complementar maior que zero.")
        cfop = str(item.get("codigo_cfop") or "").strip()
        tax_situation = str(item.get("situacao_tributaria") or "").strip()
        if not cfop or not tax_situation:
            raise NfeComplementaryError("CFOP e situacao tributaria sao obrigatorios para cada item complementar.")
        normalized_item: dict[str, Any] = {
            "sequencial": int(sequence_value),
            "codigo_cfop": cfop,
            "situacao_tributaria": tax_situation,
        }
        if quantity > 0:
            normalized_item["quantidade_complementar"] = _decimal_to_payload(quantity)
        if value > 0:
            normalized_item["valor_complementar"] = _decimal_to_payload(value)
        normalized.append(normalized_item)
    return normalized


def _complementary_requires_ibs_cbs(*, original_document: FiscalDocument) -> bool:
    if str(original_document.environment or "").strip() != "1":
        return False
    return timezone.localdate() >= IBS_CBS_CONSERVATIVE_CUTOFF_DATE


def _extract_ibs_cbs_payload_from_product(product: dict[str, Any], *, sequence: int) -> dict[str, Any]:
    raw_ibs_cbs = product.get("ibs_cbs")
    taxes = product.get("impostos")
    if raw_ibs_cbs in (None, "", {}) and isinstance(taxes, dict):
        raw_ibs_cbs = taxes.get("ibs_cbs")
    if not isinstance(raw_ibs_cbs, dict):
        raise NfeComplementaryError(f"Item fiscal {sequence} nao possui snapshot IBS/CBS confiavel para Nota Fiscal Complementar.")

    base_calculo = raw_ibs_cbs.get("base_calculo")
    if base_calculo in (None, ""):
        raise NfeComplementaryError(f"Item fiscal {sequence} possui snapshot IBS/CBS incompleto: base_calculo e obrigatorio na Nota Fiscal Complementar.")
    try:
        formatted_base_calculo = _decimal_to_payload(Decimal(str(base_calculo).replace(",", ".")))
    except InvalidOperation as exc:
        raise NfeComplementaryError(f"Item fiscal {sequence} possui snapshot IBS/CBS incompleto: base_calculo invalido.") from exc

    details = {key: value for key, value in raw_ibs_cbs.items() if key not in {"situacao_tributaria", "classificacao_tributaria", "situacao_tributaria_regular", "classificacao_tributaria_regular", "base_calculo"}}
    try:
        payload = build_ibs_cbs_payload_from_values(
            enabled=True,
            situacao_tributaria=str(raw_ibs_cbs.get("situacao_tributaria") or ""),
            classificacao_tributaria=str(raw_ibs_cbs.get("classificacao_tributaria") or ""),
            situacao_tributaria_regular=str(raw_ibs_cbs.get("situacao_tributaria_regular") or ""),
            classificacao_tributaria_regular=str(raw_ibs_cbs.get("classificacao_tributaria_regular") or ""),
            details=details,
        )
    except IbsCbsConfigurationError as exc:
        raise NfeComplementaryError(f"Item fiscal {sequence} possui snapshot IBS/CBS incompleto: {exc}") from exc
    payload["base_calculo"] = formatted_base_calculo
    return payload


def _build_product_payload(*, original_product: dict[str, Any], complementary_item: dict[str, Any], include_ibs_cbs: bool) -> dict[str, Any]:
    ibs_cbs_payload: dict[str, Any] | None = None
    if include_ibs_cbs:
        ibs_cbs_payload = _extract_ibs_cbs_payload_from_product(original_product, sequence=int(complementary_item["sequencial"]))
    product = dict(original_product)
    for original_amount_key in ("quantidade", "subtotal", "total", "valor", "preco", "valor_unitario", "preco_unitario", "total_item"):
        product.pop(original_amount_key, None)
    product["codigo_cfop"] = complementary_item["codigo_cfop"]
    product["situacao_tributaria"] = complementary_item["situacao_tributaria"]
    product["item_original"] = complementary_item["sequencial"]
    if "quantidade_complementar" in complementary_item:
        product["quantidade"] = complementary_item["quantidade_complementar"]
    if "valor_complementar" in complementary_item:
        product["subtotal"] = complementary_item["valor_complementar"]
        product["total"] = complementary_item["valor_complementar"]
    for forbidden_key in ("impostos", "ibs", "cbs", "icms_st", "ipi", "issqn", "agropecuario", "importacao", "adicao", "adicoes"):
        product.pop(forbidden_key, None)
    if ibs_cbs_payload is not None:
        product["impostos"] = {"ibs_cbs": ibs_cbs_payload}
    return product


def _build_client_payload(original_document: FiscalDocument) -> dict[str, Any]:
    for payload in (original_document.request_payload, original_document.response_payload, getattr(original_document.legacy_nfe_item, "raw_payload", {}), getattr(original_document.legacy_nfe_item, "log_payload", {})):
        if isinstance(payload, dict) and isinstance(payload.get("cliente"), dict):
            return sanitize_fiscal_payload(payload["cliente"])
    return {}


def _build_complementary_payload(*, original_document: FiscalDocument, items: list[dict[str, Any]], operacao: str, natureza_operacao: str, codigo_cfop: str, request: HttpRequest | None = None) -> dict[str, Any]:
    requires_ibs_cbs = _complementary_requires_ibs_cbs(original_document=original_document)
    payload: dict[str, Any] = {
        "operacao": str(operacao or "1").strip(),
        "natureza_operacao": str(natureza_operacao or "Nota Fiscal Complementar").strip(),
        "codigo_cfop": str(codigo_cfop or "").strip(),
        "ambiente": int(str(original_document.environment or getattr(settings, "WEBMANIA_AMBIENT", "2") or "2")),
        "cliente": _build_client_payload(original_document),
        "produtos": [],
    }
    if str(original_document.access_key or "").strip():
        payload["chave"] = validate_access_key(original_document.access_key)
    elif str(original_document.remote_uuid or "").strip():
        payload["uuid"] = str(original_document.remote_uuid).strip()
    else:
        raise NfeComplementaryError("NF-e original precisa possuir chave ou UUID valido.")
    for item in items:
        original_product = _original_product_by_sequence(original_document, int(item["sequencial"]))
        payload["produtos"].append(_build_product_payload(original_product=original_product, complementary_item=item, include_ibs_cbs=requires_ibs_cbs))
    notification_url = build_webmania_webhook_url(request=request)
    if notification_url:
        payload["url_notificacao"] = notification_url
    return payload


def create_nfe_complementary_price_quantity_draft(
    *,
    original_document: FiscalDocument,
    items: list[dict[str, Any]],
    requested_by: Any | None = None,
    operacao: str = "1",
    natureza_operacao: str = "Nota Fiscal Complementar",
    codigo_cfop: str = "",
    legal_confirmation: bool = False,
    request: HttpRequest | None = None,
) -> FiscalDocument:
    if not legal_confirmation:
        raise NfeComplementaryError("Confirme explicitamente a emissao da Nota Fiscal Complementar.")
    items = _normalize_items(items)
    with transaction.atomic():
        locked_original = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=original_document.pk)
        if locked_original.origin != FiscalDocumentOrigin.LOCAL or not locked_original.legacy_nfe_item_id:
            raise NfeComplementaryError("Complementar de preco/quantidade permitida somente para NF-e original local com itens fiscais conhecidos.")
        if not is_local_nfe_eligible_for_complementary(locked_original.legacy_nfe_item):
            raise NfeComplementaryError("Complementar permitida somente para NF-e autorizada/elegivel.")
        payload = _build_complementary_payload(original_document=locked_original, items=items, operacao=operacao, natureza_operacao=natureza_operacao, codigo_cfop=codigo_cfop, request=request)
        sanitized_payload = sanitize_fiscal_payload(payload)
        document = FiscalDocument.objects.create(
            workshop=locked_original.workshop,
            account=locked_original.account,
            document_type=FiscalDocumentType.NFE,
            origin=FiscalDocumentOrigin.LOCAL,
            purpose=FiscalDocumentPurpose.COMPLEMENTARY,
            complementary_type=FiscalDocumentComplementaryType.PRICE_QUANTITY,
            environment=str(payload["ambiente"]),
            status=FiscalDocumentStatus.PROCESSING,
            remote_status=FiscalEmissionAttemptStatus.STARTED,
            request_payload=sanitized_payload,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
        )
        FiscalDocumentLink.objects.create(document=document, related_document=locked_original, role=FiscalDocumentLinkRole.COMPLEMENTS, metadata=sanitize_fiscal_payload({"complementary_type": FiscalDocumentComplementaryType.PRICE_QUANTITY}))
        return document


def create_nfe_complementary_price_quantity_draft_from_item(*, item: NfeItem, **kwargs: Any) -> FiscalDocument:
    if not is_local_nfe_eligible_for_complementary(item):
        raise NfeComplementaryError("Complementar permitida somente para NF-e autorizada/elegivel.")
    original_document = ensure_fiscal_document_for_nfe_item(item=item)
    return create_nfe_complementary_price_quantity_draft(original_document=original_document, **kwargs)


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


def apply_nfe_complementary_document_payload(*, document: FiscalDocument, response_payload: dict[str, Any]) -> FiscalDocument:
    sanitized_payload = sanitize_fiscal_payload(response_payload)
    document.response_payload = sanitized_payload
    document.status = _status_from_payload(response_payload)
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


def _mark_document_uncertain(*, document: FiscalDocument, error_message: str) -> None:
    document.status = FiscalDocumentStatus.UNCERTAIN
    document.response_payload = sanitize_fiscal_payload({"error": error_message})
    document.remote_status = FiscalDocumentStatus.UNCERTAIN
    document.save(update_fields=["status", "response_payload", "remote_status", "atualizado_em"])


def _assert_transmittable(*, document: FiscalDocument) -> None:
    if document.origin != FiscalDocumentOrigin.LOCAL or document.purpose != FiscalDocumentPurpose.COMPLEMENTARY or document.complementary_type != FiscalDocumentComplementaryType.PRICE_QUANTITY:
        raise NfeComplementaryError("Documento complementar invalido para transmissao de preco/quantidade.")
    existing_attempt = document.emission_attempts.filter(operation_type=FiscalEmissionOperationType.COMPLEMENTARY_PRICE_QUANTITY).order_by("-pk").first()
    if existing_attempt is None:
        return
    if existing_attempt.status == FiscalEmissionAttemptStatus.UNCERTAIN:
        raise NfeComplementaryError("Ja existe tentativa complementar em estado remoto incerto. Reconcilie antes de tentar novamente.")
    if existing_attempt.status in {FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.SUCCEEDED}:
        raise NfeComplementaryError("Esta intencao complementar ja possui envio remoto registrado.")
    raise NfeComplementaryError("Esta intencao complementar ja possui tentativa fiscal registrada.")


def transmit_nfe_complementary_document(*, document: FiscalDocument) -> FiscalDocument:
    with transaction.atomic():
        locked_document = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=document.pk)
        _assert_transmittable(document=locked_document)
        payload = dict(locked_document.request_payload or {})
        idempotency_key = build_fiscal_document_operation_idempotency_key(workshop_id=locked_document.workshop_id, derived_document_id=locked_document.pk, operation_type=FiscalEmissionOperationType.COMPLEMENTARY_PRICE_QUANTITY, request_generation=1)
        try:
            attempt = begin_emission_attempt(
                workshop=locked_document.workshop,
                document_kind=FiscalEmissionDocumentKind.NFE,
                operation_type=FiscalEmissionOperationType.COMPLEMENTARY_PRICE_QUANTITY,
                request_model=FiscalDocument.__name__,
                request_id=locked_document.pk,
                fiscal_document=locked_document,
                idempotency_key=idempotency_key,
                request_payload=payload,
                payload_hash=build_payload_hash(payload),
            )
        except FiscalEmissionAttemptBlocked as exc:
            raise NfeComplementaryError(str(exc)) from exc

    headers = _build_headers(workshop=locked_document.workshop)
    mark_attempt_sent(attempt=attempt)
    try:
        response = requests.post(_build_complementary_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao emitir Nota Fiscal Complementar; estado remoto incerto."
        logger.warning("nfe_complementary_timeout", extra={"fiscal_document_id": locked_document.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_document_uncertain(document=locked_document, error_message=message)
        raise NfeComplementaryError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao emitir Nota Fiscal Complementar", scope="nfe")
        mark_attempt_failed(attempt=attempt, error_message=message)
        locked_document.status = FiscalDocumentStatus.REPROVED
        locked_document.response_payload = sanitize_fiscal_payload({"error": message})
        locked_document.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfeComplementaryError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida da Webmania ao emitir Nota Fiscal Complementar; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_document_uncertain(document=locked_document, error_message=message)
        raise NfeComplementaryError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta invalida da Webmania ao emitir Nota Fiscal Complementar; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_document_uncertain(document=locked_document, error_message=message)
        raise NfeComplementaryError(message)

    locked_document = apply_nfe_complementary_document_payload(document=locked_document, response_payload=response_payload)
    if _is_failed_response(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or "Nota Fiscal Complementar rejeitada pela Webmania."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfeComplementaryError(message)
    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    return locked_document


def create_and_emit_nfe_complementary_price_quantity_from_item(**kwargs: Any) -> FiscalDocument:
    document = create_nfe_complementary_price_quantity_draft_from_item(**kwargs)
    return transmit_nfe_complementary_document(document=document)


def consult_nfe_complementary_document(*, document: FiscalDocument) -> dict[str, Any]:
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
        raise NfeComplementaryError("Nao foi possivel consultar a Nota Fiscal Complementar sem UUID ou chave de acesso.")
    try:
        response = requests.get(_build_consulta_url(), params=params, headers=_build_headers(workshop=document.workshop), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao consultar Nota Fiscal Complementar", scope="nfe")
        raise NfeComplementaryError(message) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise NfeComplementaryError("Resposta invalida da API de consulta da Nota Fiscal Complementar.") from exc
    if not isinstance(payload, dict):
        raise NfeComplementaryError("Resposta invalida da API de consulta da Nota Fiscal Complementar.")
    error_message = extract_webmania_error_message(payload.get("error") or payload.get("msg") or payload.get("message"), scope="nfe")
    if error_message:
        raise NfeComplementaryError(error_message)
    return payload


def reconcile_nfe_complementary_document(*, document: FiscalDocument) -> FiscalDocument:
    payload = consult_nfe_complementary_document(document=document)
    document = apply_nfe_complementary_document_payload(document=document, response_payload=payload)
    document.refresh_from_db()
    return document


def resolve_nfe_complementary_document_for_webhook(*, payload: dict[str, Any]) -> FiscalDocument | None:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    queryset = FiscalDocument.objects.filter(origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.COMPLEMENTARY, complementary_type=FiscalDocumentComplementaryType.PRICE_QUANTITY)
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


def is_ambiguous_nfe_complementary_webhook(*, payload: dict[str, Any]) -> bool:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    if not event_uuid and not access_key:
        return False
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(access_key=access_key) | Q(emission_attempts__remote_key=access_key)
    return (
        FiscalDocument.objects.filter(origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.COMPLEMENTARY, complementary_type=FiscalDocumentComplementaryType.PRICE_QUANTITY)
        .filter(filters)
        .distinct()
        .values("pk")[:2]
        .count()
        > 1
    )
