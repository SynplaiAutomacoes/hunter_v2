from __future__ import annotations

import hashlib
import logging
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentEvent,
    FiscalDocumentEventStatus,
    FiscalDocumentEventType,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalEmissionAttempt,
    FiscalEmissionDocumentKind,
    FiscalEmissionOperationType,
)
from apps.finance.services.emission import build_webmania_webhook_url
from apps.finance.services.fiscal_attempts import (
    FiscalEmissionAttemptBlocked,
    begin_emission_attempt,
    build_payload_hash,
    mark_attempt_failed,
    mark_attempt_sent,
    mark_attempt_succeeded,
    mark_attempt_uncertain,
    sanitize_fiscal_payload,
)
from apps.finance.services.nfe_emission import NfeEmissionError
from apps.finance.services.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting, should_use_global_webmania_auth
from apps.finance.services.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)

IBS_CBS_EVENT_112110 = "112110"
IBS_CBS_EVENT_112130 = "112130"
IBS_CBS_EVENT_112150 = "112150"
IBS_CBS_EVENT_MAX_SEQUENCE = 20
IBS_CBS_EVENT_CANCELLATION_REMOTE_CODE = "110001"
IBS_CBS_EVENT_112130_DECIMAL_PLACES = Decimal("0.01")
IBS_CBS_EVENT_112130_QUANTITY_PLACES = Decimal("0.0001")


class NfeIbsCbsEventError(NfeEmissionError):
    pass


def _build_headers(*, workshop=None) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfeIbsCbsEventError(str(exc)) from exc


def _build_event_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_IBS_CBS_EVENT_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/evento-ibs-cbs/"


def _build_event_cancellation_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_IBS_CBS_EVENT_CANCELLATION_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/evento-ibs-cbs/cancelar/"


def is_document_eligible_for_ibs_cbs_event_112110(document: FiscalDocument | None) -> bool:
    if document is None:
        return False
    if document.document_type == FiscalDocumentType.NFE:
        if document.origin != FiscalDocumentOrigin.LOCAL or document.purpose != FiscalDocumentPurpose.NORMAL:
            return False
    elif document.document_type == FiscalDocumentType.NFCE:
        if document.origin != FiscalDocumentOrigin.MANUAL or document.purpose != FiscalDocumentPurpose.NORMAL:
            return False
    else:
        return False
    if document.status != FiscalDocumentStatus.APPROVED:
        return False
    return bool(str(document.access_key or "").strip())


def is_document_eligible_for_ibs_cbs_event_112150(document: FiscalDocument | None) -> bool:
    if document is None:
        return False
    if document.document_type != FiscalDocumentType.NFE:
        return False
    if document.origin != FiscalDocumentOrigin.LOCAL or document.purpose != FiscalDocumentPurpose.NORMAL:
        return False
    if document.status != FiscalDocumentStatus.APPROVED:
        return False
    return bool(str(document.access_key or "").strip())


def is_document_eligible_for_ibs_cbs_event_112130(document: FiscalDocument | None) -> bool:
    if document is None:
        return False
    if document.document_type != FiscalDocumentType.NFE:
        return False
    if document.origin != FiscalDocumentOrigin.LOCAL or document.purpose != FiscalDocumentPurpose.NORMAL:
        return False
    if document.status != FiscalDocumentStatus.APPROVED:
        return False
    return bool(str(document.access_key or "").strip())


def _assert_document_eligible_for_112110(*, document: FiscalDocument) -> None:
    if document.document_type == FiscalDocumentType.NFE:
        if document.origin != FiscalDocumentOrigin.LOCAL or document.purpose != FiscalDocumentPurpose.NORMAL:
            raise NfeIbsCbsEventError("Evento IBS/CBS 112110 permitido somente para NF-e normal local nesta fase.")
    elif document.document_type == FiscalDocumentType.NFCE:
        if document.origin != FiscalDocumentOrigin.MANUAL or document.purpose != FiscalDocumentPurpose.NORMAL:
            raise NfeIbsCbsEventError("Evento IBS/CBS 112110 permitido somente para NFC-e normal manual nesta fase.")
    else:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112110 permitido somente para NF-e ou NFC-e.")

    if document.status == FiscalDocumentStatus.CANCELED:
        raise NfeIbsCbsEventError("Documento cancelado nao pode receber evento IBS/CBS 112110.")
    if document.status == FiscalDocumentStatus.DENIED:
        raise NfeIbsCbsEventError("Documento denegado nao pode receber evento IBS/CBS 112110.")
    if document.status == FiscalDocumentStatus.UNCERTAIN:
        raise NfeIbsCbsEventError("Documento em estado incerto deve ser reconciliado antes do evento IBS/CBS.")
    if document.status != FiscalDocumentStatus.APPROVED:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112110 permitido somente para documento autorizado.")
    if not str(document.access_key or "").strip():
        raise NfeIbsCbsEventError("Evento IBS/CBS 112110 exige chave de acesso valida.")


def _assert_document_eligible_for_112150(*, document: FiscalDocument) -> None:
    if document.document_type != FiscalDocumentType.NFE:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112150 permitido somente para NF-e nesta fase.")
    if document.origin != FiscalDocumentOrigin.LOCAL or document.purpose != FiscalDocumentPurpose.NORMAL:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112150 permitido somente para NF-e normal local nesta fase.")
    if document.status == FiscalDocumentStatus.CANCELED:
        raise NfeIbsCbsEventError("Documento cancelado nao pode receber evento IBS/CBS 112150.")
    if document.status == FiscalDocumentStatus.DENIED:
        raise NfeIbsCbsEventError("Documento denegado nao pode receber evento IBS/CBS 112150.")
    if document.status == FiscalDocumentStatus.UNCERTAIN:
        raise NfeIbsCbsEventError("Documento em estado incerto deve ser reconciliado antes do evento IBS/CBS.")
    if document.status != FiscalDocumentStatus.APPROVED:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112150 permitido somente para documento autorizado.")
    if not str(document.access_key or "").strip():
        raise NfeIbsCbsEventError("Evento IBS/CBS 112150 exige chave de acesso valida.")


def _assert_document_eligible_for_112130(*, document: FiscalDocument) -> None:
    if document.document_type != FiscalDocumentType.NFE:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112130 permitido somente para NF-e nesta fase.")
    if document.origin != FiscalDocumentOrigin.LOCAL or document.purpose != FiscalDocumentPurpose.NORMAL:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112130 permitido somente para NF-e normal local nesta fase.")
    if document.status == FiscalDocumentStatus.CANCELED:
        raise NfeIbsCbsEventError("Documento cancelado nao pode receber evento IBS/CBS 112130.")
    if document.status == FiscalDocumentStatus.DENIED:
        raise NfeIbsCbsEventError("Documento denegado nao pode receber evento IBS/CBS 112130.")
    if document.status == FiscalDocumentStatus.UNCERTAIN:
        raise NfeIbsCbsEventError("Documento em estado incerto deve ser reconciliado antes do evento IBS/CBS.")
    if document.status != FiscalDocumentStatus.APPROVED:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112130 permitido somente para documento autorizado.")
    if not str(document.access_key or "").strip():
        raise NfeIbsCbsEventError("Evento IBS/CBS 112130 exige chave de acesso valida.")


def _assert_no_existing_112110(*, document: FiscalDocument) -> None:
    blocking_statuses = [
        FiscalDocumentEventStatus.STARTED,
        FiscalDocumentEventStatus.SENT,
        FiscalDocumentEventStatus.PROCESSING,
        FiscalDocumentEventStatus.APPROVED,
        FiscalDocumentEventStatus.SUCCEEDED,
        FiscalDocumentEventStatus.UNCERTAIN,
    ]
    if document.events.filter(event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112110, status__in=blocking_statuses).exists():
        raise NfeIbsCbsEventError("Ja existe evento IBS/CBS 112110 ativo, aprovado ou incerto para este documento.")


def _assert_no_incompatible_112150(*, document: FiscalDocument, delivery_date: date) -> None:
    blocking_statuses = [
        FiscalDocumentEventStatus.STARTED,
        FiscalDocumentEventStatus.SENT,
        FiscalDocumentEventStatus.PROCESSING,
        FiscalDocumentEventStatus.APPROVED,
        FiscalDocumentEventStatus.SUCCEEDED,
        FiscalDocumentEventStatus.UNCERTAIN,
    ]
    if document.events.filter(event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112150, status__in=blocking_statuses, request_payload__data_previsao_entrega=delivery_date.isoformat()).exists():
        raise NfeIbsCbsEventError("Ja existe evento IBS/CBS 112150 ativo, aprovado ou incerto para esta data de previsao de entrega.")


def _assert_no_incompatible_112130(*, document: FiscalDocument, items_payload: list[dict[str, Any]]) -> None:
    blocking_statuses = [
        FiscalDocumentEventStatus.STARTED,
        FiscalDocumentEventStatus.SENT,
        FiscalDocumentEventStatus.PROCESSING,
        FiscalDocumentEventStatus.APPROVED,
        FiscalDocumentEventStatus.SUCCEEDED,
        FiscalDocumentEventStatus.UNCERTAIN,
    ]
    if document.events.filter(event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112130, status__in=blocking_statuses, request_payload__itens=items_payload).exists():
        raise NfeIbsCbsEventError("Ja existe evento IBS/CBS 112130 ativo, aprovado ou incerto com os mesmos itens e valores.")


def _next_event_sequence(*, document: FiscalDocument, event_code: str) -> int:
    latest = document.events.filter(event_type=FiscalDocumentEventType.IBS_CBS).order_by("-event_sequence").first()
    next_sequence = int(latest.event_sequence if latest is not None else 0) + 1
    if next_sequence > IBS_CBS_EVENT_MAX_SEQUENCE:
        raise NfeIbsCbsEventError("Limite de 20 eventos IBS/CBS atingido para este documento e codigo.")
    return next_sequence


def _build_112110_payload(*, document: FiscalDocument, event_sequence: int, request: HttpRequest | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chave": str(document.access_key or "").strip(),
        "ambiente": int(str(document.environment or getattr(settings, "WEBMANIA_AMBIENT", "2") or "2")),
        "cod_evento": IBS_CBS_EVENT_112110,
        "evento": event_sequence,
    }
    notification_url = build_webmania_webhook_url(request=request)
    if notification_url:
        payload["url_notificacao"] = notification_url
    return payload


def _coerce_delivery_forecast_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    normalized = str(value or "").strip()
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise NfeIbsCbsEventError("Data de previsao de entrega invalida. Use o formato YYYY-MM-DD.") from exc


def _build_112150_payload(*, document: FiscalDocument, event_sequence: int, delivery_date: date, request: HttpRequest | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chave": str(document.access_key or "").strip(),
        "ambiente": int(str(document.environment or getattr(settings, "WEBMANIA_AMBIENT", "2") or "2")),
        "cod_evento": IBS_CBS_EVENT_112150,
        "evento": event_sequence,
        "data_previsao_entrega": delivery_date.isoformat(),
    }
    notification_url = build_webmania_webhook_url(request=request)
    if notification_url:
        payload["url_notificacao"] = notification_url
    return payload


def _coerce_positive_decimal(*, value: Any, label: str, places: Decimal) -> Decimal:
    try:
        normalized = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, ValueError) as exc:
        raise NfeIbsCbsEventError(f"{label} invalido para evento IBS/CBS 112130.") from exc
    if normalized <= 0:
        raise NfeIbsCbsEventError(f"{label} deve ser positivo para evento IBS/CBS 112130.")
    return normalized.quantize(places, rounding=ROUND_HALF_UP)


def _decimal_to_payload_string(value: Decimal) -> str:
    return format(value, "f")


def _event_item_sequence(value: Any) -> int:
    try:
        sequence = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise NfeIbsCbsEventError("Item do evento IBS/CBS 112130 deve informar sequencial fiscal valido.") from exc
    if sequence <= 0 or sequence > 999:
        raise NfeIbsCbsEventError("Item do evento IBS/CBS 112130 deve estar entre 1 e 999.")
    return sequence


def _document_payload_sources(document: FiscalDocument) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for payload in (document.request_payload, document.response_payload):
        if isinstance(payload, dict):
            sources.append(payload)
    legacy_item = getattr(document, "legacy_nfe_item", None)
    if legacy_item is not None:
        for payload in (getattr(legacy_item, "raw_payload", None), getattr(legacy_item, "log_payload", None)):
            if isinstance(payload, dict):
                sources.append(payload)
    return sources


def _extract_products_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    products = payload.get("produtos")
    if isinstance(products, list):
        return [product for product in products if isinstance(product, dict)]
    nfe_payload = payload.get("nfe")
    if isinstance(nfe_payload, dict):
        nested_products = nfe_payload.get("produtos")
        if isinstance(nested_products, list):
            return [product for product in nested_products if isinstance(product, dict)]
    return []


def _product_sequence(product: dict[str, Any], fallback_sequence: int) -> int:
    for key in ("item", "sequencial", "sequencia", "numero_item", "nItem"):
        raw_value = product.get(key)
        if raw_value not in (None, ""):
            return _event_item_sequence(raw_value)
    return fallback_sequence


def _product_ibs_cbs_payload(product: dict[str, Any]) -> dict[str, Any]:
    direct_payload = product.get("ibs_cbs")
    if isinstance(direct_payload, dict) and direct_payload:
        return direct_payload
    taxes_payload = product.get("impostos")
    if isinstance(taxes_payload, dict):
        nested_payload = taxes_payload.get("ibs_cbs")
        if isinstance(nested_payload, dict) and nested_payload:
            return nested_payload
    return {}


def _find_product_snapshot_for_sequence(*, document: FiscalDocument, sequence: int) -> dict[str, Any] | None:
    for payload in _document_payload_sources(document):
        for index, product in enumerate(_extract_products_from_payload(payload), start=1):
            if _product_sequence(product, index) == sequence:
                return product
    return None


def _assert_product_has_ibs_cbs_snapshot(*, product: dict[str, Any], sequence: int) -> None:
    ibs_cbs_payload = _product_ibs_cbs_payload(product)
    if not ibs_cbs_payload:
        raise NfeIbsCbsEventError(f"Item fiscal {sequence} nao possui snapshot IBS/CBS no documento original.")
    if not str(ibs_cbs_payload.get("situacao_tributaria") or "").strip() or not str(ibs_cbs_payload.get("classificacao_tributaria") or "").strip():
        raise NfeIbsCbsEventError(f"Item fiscal {sequence} nao possui situacao/classificacao IBS/CBS no snapshot original.")


def _normalize_112130_items(*, document: FiscalDocument, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112130 exige ao menos um item.")
    normalized_items: list[dict[str, Any]] = []
    seen_sequences: set[int] = set()
    for item in items:
        if not isinstance(item, dict):
            raise NfeIbsCbsEventError("Itens do evento IBS/CBS 112130 devem ser objetos.")
        sequence = _event_item_sequence(item.get("item"))
        if sequence in seen_sequences:
            raise NfeIbsCbsEventError("Evento IBS/CBS 112130 nao permite item fiscal duplicado no mesmo payload.")
        snapshot_product = _find_product_snapshot_for_sequence(document=document, sequence=sequence)
        if snapshot_product is None:
            raise NfeIbsCbsEventError(f"Item fiscal {sequence} nao encontrado no snapshot da NF-e original.")
        _assert_product_has_ibs_cbs_snapshot(product=snapshot_product, sequence=sequence)
        unit = str(item.get("unidade_perecimento") or "").strip().upper()
        if not 1 <= len(unit) <= 6:
            raise NfeIbsCbsEventError("Unidade de perecimento deve possuir entre 1 e 6 caracteres.")
        normalized_items.append(
            {
                "item": sequence,
                "valor_ibs": _decimal_to_payload_string(_coerce_positive_decimal(value=item.get("valor_ibs"), label="Valor IBS", places=IBS_CBS_EVENT_112130_DECIMAL_PLACES)),
                "valor_cbs": _decimal_to_payload_string(_coerce_positive_decimal(value=item.get("valor_cbs"), label="Valor CBS", places=IBS_CBS_EVENT_112130_DECIMAL_PLACES)),
                "controle_estoque": {
                    "quantidade_perecimento": _decimal_to_payload_string(_coerce_positive_decimal(value=item.get("quantidade_perecimento"), label="Quantidade de perecimento", places=IBS_CBS_EVENT_112130_QUANTITY_PLACES)),
                    "unidade_perecimento": unit,
                    "valor_ibs_estorno": _decimal_to_payload_string(_coerce_positive_decimal(value=item.get("valor_ibs_estorno"), label="Valor IBS de estorno", places=IBS_CBS_EVENT_112130_DECIMAL_PLACES)),
                    "valor_cbs_estorno": _decimal_to_payload_string(_coerce_positive_decimal(value=item.get("valor_cbs_estorno"), label="Valor CBS de estorno", places=IBS_CBS_EVENT_112130_DECIMAL_PLACES)),
                },
            }
        )
        seen_sequences.add(sequence)
    return normalized_items


def _build_112130_payload(*, document: FiscalDocument, event_sequence: int, items_payload: list[dict[str, Any]], request: HttpRequest | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chave": str(document.access_key or "").strip(),
        "ambiente": int(str(document.environment or getattr(settings, "WEBMANIA_AMBIENT", "2") or "2")),
        "cod_evento": IBS_CBS_EVENT_112130,
        "evento": event_sequence,
        "itens": items_payload,
    }
    notification_url = build_webmania_webhook_url(request=request)
    if notification_url:
        payload["url_notificacao"] = notification_url
    return payload


def _build_ibs_cbs_event_idempotency_key(*, workshop_id: int, document_id: int, event_code: str, event_sequence: int, request_generation: int = 1) -> str:
    raw_value = f"{workshop_id}:{document_id}:{FiscalDocumentEventType.IBS_CBS}:{event_code}:{event_sequence}:{request_generation}"
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
    return f"{FiscalEmissionOperationType.NFE_IBS_CBS_EVENT}:{digest}"


def create_112110_event_attempt(*, document: FiscalDocument, requested_by: Any | None, request: HttpRequest | None = None) -> tuple[FiscalDocumentEvent, FiscalEmissionAttempt, dict[str, Any]]:
    with transaction.atomic():
        locked_document = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=document.pk)
        _assert_document_eligible_for_112110(document=locked_document)
        _assert_no_existing_112110(document=locked_document)
        event_sequence = _next_event_sequence(document=locked_document, event_code=IBS_CBS_EVENT_112110)
        payload = _build_112110_payload(document=locked_document, event_sequence=event_sequence, request=request)
        sanitized_payload = sanitize_fiscal_payload(payload)
        event = FiscalDocumentEvent.objects.create(
            document=locked_document,
            event_type=FiscalDocumentEventType.IBS_CBS,
            event_code=IBS_CBS_EVENT_112110,
            event_sequence=event_sequence,
            event_payload_type="no_specific_fields",
            status=FiscalDocumentEventStatus.STARTED,
            remote_model="ibs_cbs",
            request_payload=sanitized_payload,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            legal_confirmation=True,
            confirmed_at=timezone.now(),
        )
        idempotency_key = _build_ibs_cbs_event_idempotency_key(
            workshop_id=locked_document.workshop_id,
            document_id=locked_document.pk,
            event_code=IBS_CBS_EVENT_112110,
            event_sequence=event_sequence,
        )
        document_kind = FiscalEmissionDocumentKind.NFCE if locked_document.document_type == FiscalDocumentType.NFCE else FiscalEmissionDocumentKind.NFE
        attempt = begin_emission_attempt(
            workshop=locked_document.workshop,
            document_kind=document_kind,
            operation_type=FiscalEmissionOperationType.NFE_IBS_CBS_EVENT,
            request_model=FiscalDocumentEvent.__name__,
            request_id=event.pk,
            fiscal_document=locked_document,
            fiscal_document_event=event,
            idempotency_key=idempotency_key,
            request_payload=sanitized_payload,
            payload_hash=build_payload_hash(sanitized_payload),
        )
        return event, attempt, payload


def create_112150_event_attempt(*, document: FiscalDocument, delivery_forecast_date: date | str, requested_by: Any | None, request: HttpRequest | None = None) -> tuple[FiscalDocumentEvent, FiscalEmissionAttempt, dict[str, Any]]:
    delivery_date = _coerce_delivery_forecast_date(delivery_forecast_date)
    with transaction.atomic():
        locked_document = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=document.pk)
        _assert_document_eligible_for_112150(document=locked_document)
        _assert_no_incompatible_112150(document=locked_document, delivery_date=delivery_date)
        event_sequence = _next_event_sequence(document=locked_document, event_code=IBS_CBS_EVENT_112150)
        payload = _build_112150_payload(document=locked_document, event_sequence=event_sequence, delivery_date=delivery_date, request=request)
        sanitized_payload = sanitize_fiscal_payload(payload)
        event = FiscalDocumentEvent.objects.create(
            document=locked_document,
            event_type=FiscalDocumentEventType.IBS_CBS,
            event_code=IBS_CBS_EVENT_112150,
            event_sequence=event_sequence,
            event_payload_type="delivery_forecast",
            status=FiscalDocumentEventStatus.STARTED,
            remote_model="ibs_cbs",
            request_payload=sanitized_payload,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            legal_confirmation=True,
            confirmed_at=timezone.now(),
        )
        idempotency_key = _build_ibs_cbs_event_idempotency_key(
            workshop_id=locked_document.workshop_id,
            document_id=locked_document.pk,
            event_code=IBS_CBS_EVENT_112150,
            event_sequence=event_sequence,
        )
        attempt = begin_emission_attempt(
            workshop=locked_document.workshop,
            document_kind=FiscalEmissionDocumentKind.NFE,
            operation_type=FiscalEmissionOperationType.NFE_IBS_CBS_EVENT,
            request_model=FiscalDocumentEvent.__name__,
            request_id=event.pk,
            fiscal_document=locked_document,
            fiscal_document_event=event,
            idempotency_key=idempotency_key,
            request_payload=sanitized_payload,
            payload_hash=build_payload_hash(sanitized_payload),
        )
        return event, attempt, payload


def create_112130_event_attempt(*, document: FiscalDocument, items: list[dict[str, Any]], requested_by: Any | None, request: HttpRequest | None = None) -> tuple[FiscalDocumentEvent, FiscalEmissionAttempt, dict[str, Any]]:
    with transaction.atomic():
        locked_document = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=document.pk)
        _assert_document_eligible_for_112130(document=locked_document)
        items_payload = _normalize_112130_items(document=locked_document, items=items)
        _assert_no_incompatible_112130(document=locked_document, items_payload=items_payload)
        event_sequence = _next_event_sequence(document=locked_document, event_code=IBS_CBS_EVENT_112130)
        payload = _build_112130_payload(document=locked_document, event_sequence=event_sequence, items_payload=items_payload, request=request)
        sanitized_payload = sanitize_fiscal_payload(payload)
        event = FiscalDocumentEvent.objects.create(
            document=locked_document,
            event_type=FiscalDocumentEventType.IBS_CBS,
            event_code=IBS_CBS_EVENT_112130,
            event_sequence=event_sequence,
            event_payload_type="supplier_transport_loss",
            status=FiscalDocumentEventStatus.STARTED,
            remote_model="ibs_cbs",
            request_payload=sanitized_payload,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            legal_confirmation=True,
            confirmed_at=timezone.now(),
        )
        idempotency_key = _build_ibs_cbs_event_idempotency_key(
            workshop_id=locked_document.workshop_id,
            document_id=locked_document.pk,
            event_code=IBS_CBS_EVENT_112130,
            event_sequence=event_sequence,
        )
        attempt = begin_emission_attempt(
            workshop=locked_document.workshop,
            document_kind=FiscalEmissionDocumentKind.NFE,
            operation_type=FiscalEmissionOperationType.NFE_IBS_CBS_EVENT,
            request_model=FiscalDocumentEvent.__name__,
            request_id=event.pk,
            fiscal_document=locked_document,
            fiscal_document_event=event,
            idempotency_key=idempotency_key,
            request_payload=sanitized_payload,
            payload_hash=build_payload_hash(sanitized_payload),
        )
        return event, attempt, payload


def _is_failed_event_response(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    return status in {"erro", "error", "falha", "failed", "reprovado", "rejeitado"}


def _status_from_event_payload(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip().lower()
    if status in {FiscalDocumentEventStatus.APPROVED, FiscalDocumentEventStatus.REPROVED, FiscalDocumentEventStatus.PROCESSING, FiscalDocumentEventStatus.SUCCEEDED, FiscalDocumentEventStatus.FAILED, FiscalDocumentEventStatus.CANCELED}:
        return status
    if _is_failed_event_response(payload):
        return FiscalDocumentEventStatus.FAILED
    return FiscalDocumentEventStatus.APPROVED if str(payload.get("uuid") or "").strip() else FiscalDocumentEventStatus.PROCESSING


def apply_ibs_cbs_event_payload(*, event: FiscalDocumentEvent, response_payload: dict[str, Any]) -> FiscalDocumentEvent:
    sanitized_payload = sanitize_fiscal_payload(response_payload)
    event.response_payload = sanitized_payload
    event.status = _status_from_event_payload(response_payload)
    event.remote_uuid = str(response_payload.get("uuid") or event.remote_uuid or "").strip()
    event.remote_event_id = str(response_payload.get("protocolo_evento") or response_payload.get("protocolo") or response_payload.get("id_evento") or event.remote_event_id or "").strip()
    event.remote_model = str(response_payload.get("modelo") or response_payload.get("model") or event.remote_model or "ibs_cbs").strip().lower()
    event.xml_url = str(response_payload.get("xml") or event.xml_url or "").strip()
    event.save(update_fields=["response_payload", "status", "remote_uuid", "remote_event_id", "remote_model", "xml_url", "atualizado_em"])
    return event


def mark_ibs_cbs_event_uncertain(*, event: FiscalDocumentEvent, error_message: str) -> None:
    event.status = FiscalDocumentEventStatus.UNCERTAIN
    event.response_payload = sanitize_fiscal_payload({"error": error_message})
    event.save(update_fields=["status", "response_payload", "atualizado_em"])


def _replay_pending_ibs_cbs_webhooks_for_uuid(*, event_uuid: str) -> None:
    if not event_uuid:
        return
    from apps.finance.services.webmania_webhooks import process_pending_webhook_events

    process_pending_webhook_events(model="ibs_cbs", event_uuid=event_uuid)


def _transmit_ibs_cbs_event(*, event: FiscalDocumentEvent, attempt: FiscalEmissionAttempt, payload: dict[str, Any], event_code: str) -> FiscalDocumentEvent:
    headers = _build_headers(workshop=event.document.workshop)
    mark_attempt_sent(attempt=attempt)
    event.status = FiscalDocumentEventStatus.SENT
    event.save(update_fields=["status", "atualizado_em"])

    try:
        response = requests.post(_build_event_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = f"Timeout ao registrar evento IBS/CBS {event_code}; estado remoto incerto."
        logger.warning("nfe_ibs_cbs_event_timeout", extra={"fiscal_document_event_id": event.pk, "fiscal_attempt_id": attempt.pk, "event_code": event_code})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_ibs_cbs_event_uncertain(event=event, error_message=message)
        raise NfeIbsCbsEventError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default=f"Falha ao registrar evento IBS/CBS {event_code}", scope="nfe")
        logger.warning("nfe_ibs_cbs_event_request_failed", extra={"fiscal_document_event_id": event.pk, "fiscal_attempt_id": attempt.pk, "event_code": event_code})
        mark_attempt_failed(attempt=attempt, error_message=message)
        event.status = FiscalDocumentEventStatus.FAILED
        event.response_payload = sanitize_fiscal_payload({"error": message})
        event.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfeIbsCbsEventError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = f"Resposta invalida da Webmania ao registrar evento IBS/CBS {event_code}; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_ibs_cbs_event_uncertain(event=event, error_message=message)
        raise NfeIbsCbsEventError(message) from exc
    if not isinstance(response_payload, dict):
        message = f"Resposta invalida da Webmania ao registrar evento IBS/CBS {event_code}; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_ibs_cbs_event_uncertain(event=event, error_message=message)
        raise NfeIbsCbsEventError(message)

    event = apply_ibs_cbs_event_payload(event=event, response_payload=response_payload)
    if _is_failed_event_response(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or f"Evento IBS/CBS {event_code} rejeitado pela Webmania."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfeIbsCbsEventError(message)

    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    if event.remote_uuid:
        _replay_pending_ibs_cbs_webhooks_for_uuid(event_uuid=event.remote_uuid)
    return event


def emit_ibs_cbs_event_112110(*, document: FiscalDocument, requested_by: Any | None = None, request: HttpRequest | None = None) -> FiscalDocumentEvent:
    try:
        event, attempt, payload = create_112110_event_attempt(document=document, requested_by=requested_by, request=request)
    except FiscalEmissionAttemptBlocked as exc:
        raise NfeIbsCbsEventError(str(exc)) from exc

    return _transmit_ibs_cbs_event(event=event, attempt=attempt, payload=payload, event_code=IBS_CBS_EVENT_112110)


def emit_ibs_cbs_event_112130(*, document: FiscalDocument, items: list[dict[str, Any]], requested_by: Any | None = None, request: HttpRequest | None = None) -> FiscalDocumentEvent:
    try:
        event, attempt, payload = create_112130_event_attempt(document=document, items=items, requested_by=requested_by, request=request)
    except FiscalEmissionAttemptBlocked as exc:
        raise NfeIbsCbsEventError(str(exc)) from exc

    return _transmit_ibs_cbs_event(event=event, attempt=attempt, payload=payload, event_code=IBS_CBS_EVENT_112130)


def emit_ibs_cbs_event_112150(*, document: FiscalDocument, delivery_forecast_date: date | str, requested_by: Any | None = None, request: HttpRequest | None = None) -> FiscalDocumentEvent:
    try:
        event, attempt, payload = create_112150_event_attempt(document=document, delivery_forecast_date=delivery_forecast_date, requested_by=requested_by, request=request)
    except FiscalEmissionAttemptBlocked as exc:
        raise NfeIbsCbsEventError(str(exc)) from exc

    return _transmit_ibs_cbs_event(event=event, attempt=attempt, payload=payload, event_code=IBS_CBS_EVENT_112150)


def resolve_ibs_cbs_event_for_webhook(*, payload: dict[str, Any]) -> FiscalDocumentEvent | None:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    event_sequence = payload.get("evento")
    event_code = str(payload.get("cod_evento") or IBS_CBS_EVENT_112110).strip()
    queryset = FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.IBS_CBS, event_code=event_code).select_related("document")
    filters = Q()
    has_filter = False
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
        has_filter = True
    if access_key and str(event_sequence or "").isdigit():
        filters |= Q(document__access_key=access_key, event_sequence=int(event_sequence))
        has_filter = True
    if not has_filter:
        return None
    matches = list(queryset.filter(filters).distinct().order_by("-pk")[:2])
    if len(matches) != 1:
        return None
    return matches[0]


def is_ambiguous_ibs_cbs_event_webhook(*, payload: dict[str, Any]) -> bool:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    event_sequence = payload.get("evento")
    event_code = str(payload.get("cod_evento") or IBS_CBS_EVENT_112110).strip()
    filters = Q()
    has_filter = False
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
        has_filter = True
    if access_key and str(event_sequence or "").isdigit():
        filters |= Q(document__access_key=access_key, event_sequence=int(event_sequence))
        has_filter = True
    if not has_filter:
        return False
    return FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.IBS_CBS, event_code=event_code).filter(filters).distinct().values("pk")[:2].count() > 1


def is_ibs_cbs_event_112110_cancelable(event: FiscalDocumentEvent | None) -> bool:
    if event is None:
        return False
    return (
        event.event_type == FiscalDocumentEventType.IBS_CBS
        and event.event_code == IBS_CBS_EVENT_112110
        and event.status in {FiscalDocumentEventStatus.APPROVED, FiscalDocumentEventStatus.SUCCEEDED}
        and bool(str(event.remote_uuid or "").strip())
    )


def is_ibs_cbs_event_112150_cancelable(event: FiscalDocumentEvent | None) -> bool:
    if event is None:
        return False
    return (
        event.event_type == FiscalDocumentEventType.IBS_CBS
        and event.event_code == IBS_CBS_EVENT_112150
        and event.status in {FiscalDocumentEventStatus.APPROVED, FiscalDocumentEventStatus.SUCCEEDED}
        and bool(str(event.remote_uuid or "").strip())
    )


def _assert_event_cancelable(*, event: FiscalDocumentEvent, event_code: str) -> None:
    if event.event_type != FiscalDocumentEventType.IBS_CBS or event.event_code != event_code:
        raise NfeIbsCbsEventError(f"Cancelamento permitido somente para evento IBS/CBS {event_code} nesta fase.")
    if event.status == FiscalDocumentEventStatus.CANCELED:
        raise NfeIbsCbsEventError(f"Evento IBS/CBS {event_code} ja esta cancelado.")
    if event.status == FiscalDocumentEventStatus.UNCERTAIN:
        raise NfeIbsCbsEventError(f"Evento IBS/CBS {event_code} incerto deve ser reconciliado antes do cancelamento.")
    if event.status not in {FiscalDocumentEventStatus.APPROVED, FiscalDocumentEventStatus.SUCCEEDED}:
        raise NfeIbsCbsEventError(f"Cancelamento permitido somente para evento IBS/CBS {event_code} autorizado.")
    if not str(event.remote_uuid or "").strip():
        raise NfeIbsCbsEventError(f"Cancelamento do evento IBS/CBS {event_code} exige UUID remoto confirmado.")

    document = event.document
    if document.status in {FiscalDocumentStatus.CANCELED, FiscalDocumentStatus.DENIED, FiscalDocumentStatus.REPROVED}:
        raise NfeIbsCbsEventError("Documento fiscal base em estado final invalido nao permite cancelar evento IBS/CBS nesta fase.")

    blocking_statuses = [
        FiscalDocumentEventStatus.STARTED,
        FiscalDocumentEventStatus.SENT,
        FiscalDocumentEventStatus.PROCESSING,
        FiscalDocumentEventStatus.APPROVED,
        FiscalDocumentEventStatus.SUCCEEDED,
        FiscalDocumentEventStatus.CANCELED,
        FiscalDocumentEventStatus.UNCERTAIN,
    ]
    if event.related_cancellations.filter(event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION, status__in=blocking_statuses).exists():
        raise NfeIbsCbsEventError(f"Ja existe cancelamento ativo, aprovado ou incerto para este evento IBS/CBS {event_code}.")


def _assert_event_cancelable_112110(*, event: FiscalDocumentEvent) -> None:
    _assert_event_cancelable(event=event, event_code=IBS_CBS_EVENT_112110)


def _assert_event_cancelable_112150(*, event: FiscalDocumentEvent) -> None:
    _assert_event_cancelable(event=event, event_code=IBS_CBS_EVENT_112150)


def _build_event_cancellation_payload(*, event: FiscalDocumentEvent, request: HttpRequest | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "uuid": str(event.remote_uuid or "").strip(),
    }
    environment = str(event.document.environment or "").strip()
    if environment:
        payload["ambiente"] = int(environment)
    notification_url = build_webmania_webhook_url(request=request)
    if notification_url:
        payload["url_notificacao"] = notification_url
    return payload


def _build_112110_cancellation_payload(*, event: FiscalDocumentEvent, request: HttpRequest | None = None) -> dict[str, Any]:
    return _build_event_cancellation_payload(event=event, request=request)


def _build_112150_cancellation_payload(*, event: FiscalDocumentEvent, request: HttpRequest | None = None) -> dict[str, Any]:
    return _build_event_cancellation_payload(event=event, request=request)


def _build_ibs_cbs_event_cancellation_idempotency_key(*, workshop_id: int, original_event_id: int, cancellation_event_id: int, request_generation: int = 1) -> str:
    raw_value = f"{workshop_id}:{original_event_id}:{FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION}:{cancellation_event_id}:{request_generation}"
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
    return f"{FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION}:{digest}"


def create_112110_event_cancellation_attempt(*, event: FiscalDocumentEvent, requested_by: Any | None, request: HttpRequest | None = None) -> tuple[FiscalDocumentEvent, FiscalEmissionAttempt, dict[str, Any]]:
    with transaction.atomic():
        locked_event = FiscalDocumentEvent.objects.select_for_update().select_related("document", "document__workshop").get(pk=event.pk)
        _assert_event_cancelable_112110(event=locked_event)
        payload = _build_112110_cancellation_payload(event=locked_event, request=request)
        sanitized_payload = sanitize_fiscal_payload(payload)
        cancellation_event = FiscalDocumentEvent.objects.create(
            document=locked_event.document,
            related_event=locked_event,
            event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION,
            event_code=IBS_CBS_EVENT_112110,
            event_sequence=locked_event.event_sequence,
            event_payload_type="cancellation",
            status=FiscalDocumentEventStatus.STARTED,
            remote_model="ibs_cbs_cancellation",
            request_payload=sanitized_payload,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            legal_confirmation=True,
            confirmed_at=timezone.now(),
        )
        document_kind = FiscalEmissionDocumentKind.NFCE if locked_event.document.document_type == FiscalDocumentType.NFCE else FiscalEmissionDocumentKind.NFE
        idempotency_key = _build_ibs_cbs_event_cancellation_idempotency_key(workshop_id=locked_event.document.workshop_id, original_event_id=locked_event.pk, cancellation_event_id=cancellation_event.pk)
        attempt = begin_emission_attempt(
            workshop=locked_event.document.workshop,
            document_kind=document_kind,
            operation_type=FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION,
            request_model=FiscalDocumentEvent.__name__,
            request_id=cancellation_event.pk,
            fiscal_document=locked_event.document,
            fiscal_document_event=cancellation_event,
            idempotency_key=idempotency_key,
            request_payload=sanitized_payload,
            payload_hash=build_payload_hash(sanitized_payload),
        )
        return cancellation_event, attempt, payload


def create_112150_event_cancellation_attempt(*, event: FiscalDocumentEvent, requested_by: Any | None, request: HttpRequest | None = None) -> tuple[FiscalDocumentEvent, FiscalEmissionAttempt, dict[str, Any]]:
    with transaction.atomic():
        locked_event = FiscalDocumentEvent.objects.select_for_update().select_related("document", "document__workshop").get(pk=event.pk)
        _assert_event_cancelable_112150(event=locked_event)
        payload = _build_112150_cancellation_payload(event=locked_event, request=request)
        sanitized_payload = sanitize_fiscal_payload(payload)
        cancellation_event = FiscalDocumentEvent.objects.create(
            document=locked_event.document,
            related_event=locked_event,
            event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION,
            event_code=IBS_CBS_EVENT_112150,
            event_sequence=locked_event.event_sequence,
            event_payload_type="cancellation",
            status=FiscalDocumentEventStatus.STARTED,
            remote_model="ibs_cbs_cancellation",
            request_payload=sanitized_payload,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            legal_confirmation=True,
            confirmed_at=timezone.now(),
        )
        idempotency_key = _build_ibs_cbs_event_cancellation_idempotency_key(workshop_id=locked_event.document.workshop_id, original_event_id=locked_event.pk, cancellation_event_id=cancellation_event.pk)
        attempt = begin_emission_attempt(
            workshop=locked_event.document.workshop,
            document_kind=FiscalEmissionDocumentKind.NFE,
            operation_type=FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION,
            request_model=FiscalDocumentEvent.__name__,
            request_id=cancellation_event.pk,
            fiscal_document=locked_event.document,
            fiscal_document_event=cancellation_event,
            idempotency_key=idempotency_key,
            request_payload=sanitized_payload,
            payload_hash=build_payload_hash(sanitized_payload),
        )
        return cancellation_event, attempt, payload


def _is_successful_cancellation_response(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    return status in {"aprovado", "cancelado", "cancelada", "canceled", "succeeded"}


def apply_ibs_cbs_event_cancellation_payload(*, event: FiscalDocumentEvent, response_payload: dict[str, Any]) -> FiscalDocumentEvent:
    sanitized_payload = sanitize_fiscal_payload(response_payload)
    with transaction.atomic():
        event = FiscalDocumentEvent.objects.select_for_update().get(pk=event.pk)
        event.response_payload = sanitized_payload
        event.status = _status_from_event_payload(response_payload)
        event.remote_uuid = str(response_payload.get("uuid") or event.remote_uuid or "").strip()
        event.remote_event_id = str(response_payload.get("protocolo_evento") or response_payload.get("protocolo") or response_payload.get("id_evento") or event.remote_event_id or "").strip()
        event.remote_model = str(response_payload.get("modelo") or response_payload.get("model") or event.remote_model or "ibs_cbs_cancellation").strip().lower()
        event.xml_url = str(response_payload.get("xml") or event.xml_url or "").strip()
        event.save(update_fields=["response_payload", "status", "remote_uuid", "remote_event_id", "remote_model", "xml_url", "atualizado_em"])

        if _is_successful_cancellation_response(response_payload) and event.related_event_id:
            original_event = FiscalDocumentEvent.objects.select_for_update().get(pk=event.related_event_id)
            original_event.status = FiscalDocumentEventStatus.CANCELED
            original_event.save(update_fields=["status", "atualizado_em"])
    return event


def mark_ibs_cbs_event_cancellation_uncertain(*, event: FiscalDocumentEvent, error_message: str) -> None:
    event.status = FiscalDocumentEventStatus.UNCERTAIN
    event.response_payload = sanitize_fiscal_payload({"error": error_message})
    event.save(update_fields=["status", "response_payload", "atualizado_em"])


def _transmit_ibs_cbs_event_cancellation(*, cancellation_event: FiscalDocumentEvent, attempt: FiscalEmissionAttempt, payload: dict[str, Any], event_code: str) -> FiscalDocumentEvent:
    headers = _build_headers(workshop=cancellation_event.document.workshop)
    mark_attempt_sent(attempt=attempt)
    cancellation_event.status = FiscalDocumentEventStatus.SENT
    cancellation_event.save(update_fields=["status", "atualizado_em"])

    try:
        response = requests.put(_build_event_cancellation_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = f"Timeout ao cancelar evento IBS/CBS {event_code}; estado remoto incerto."
        logger.warning("nfe_ibs_cbs_event_cancellation_timeout", extra={"fiscal_document_event_id": cancellation_event.pk, "fiscal_attempt_id": attempt.pk, "event_code": event_code})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_ibs_cbs_event_cancellation_uncertain(event=cancellation_event, error_message=message)
        raise NfeIbsCbsEventError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default=f"Falha ao cancelar evento IBS/CBS {event_code}", scope="nfe")
        logger.warning("nfe_ibs_cbs_event_cancellation_request_failed", extra={"fiscal_document_event_id": cancellation_event.pk, "fiscal_attempt_id": attempt.pk, "event_code": event_code})
        mark_attempt_failed(attempt=attempt, error_message=message)
        cancellation_event.status = FiscalDocumentEventStatus.FAILED
        cancellation_event.response_payload = sanitize_fiscal_payload({"error": message})
        cancellation_event.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfeIbsCbsEventError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = f"Resposta invalida da Webmania ao cancelar evento IBS/CBS {event_code}; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_ibs_cbs_event_cancellation_uncertain(event=cancellation_event, error_message=message)
        raise NfeIbsCbsEventError(message) from exc
    if not isinstance(response_payload, dict):
        message = f"Resposta invalida da Webmania ao cancelar evento IBS/CBS {event_code}; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_ibs_cbs_event_cancellation_uncertain(event=cancellation_event, error_message=message)
        raise NfeIbsCbsEventError(message)

    cancellation_event = apply_ibs_cbs_event_cancellation_payload(event=cancellation_event, response_payload=response_payload)
    if _is_failed_event_response(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or f"Cancelamento do evento IBS/CBS {event_code} rejeitado pela Webmania."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        cancellation_event.status = FiscalDocumentEventStatus.FAILED
        cancellation_event.save(update_fields=["status", "atualizado_em"])
        raise NfeIbsCbsEventError(message)

    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    if cancellation_event.remote_uuid:
        _replay_pending_ibs_cbs_webhooks_for_uuid(event_uuid=cancellation_event.remote_uuid)
    return cancellation_event


def cancel_ibs_cbs_event_112110(*, event: FiscalDocumentEvent, requested_by: Any | None = None, request: HttpRequest | None = None) -> FiscalDocumentEvent:
    try:
        cancellation_event, attempt, payload = create_112110_event_cancellation_attempt(event=event, requested_by=requested_by, request=request)
    except FiscalEmissionAttemptBlocked as exc:
        raise NfeIbsCbsEventError(str(exc)) from exc

    return _transmit_ibs_cbs_event_cancellation(cancellation_event=cancellation_event, attempt=attempt, payload=payload, event_code=IBS_CBS_EVENT_112110)


def cancel_ibs_cbs_event_112150(*, event: FiscalDocumentEvent, requested_by: Any | None = None, request: HttpRequest | None = None) -> FiscalDocumentEvent:
    try:
        cancellation_event, attempt, payload = create_112150_event_cancellation_attempt(event=event, requested_by=requested_by, request=request)
    except FiscalEmissionAttemptBlocked as exc:
        raise NfeIbsCbsEventError(str(exc)) from exc

    return _transmit_ibs_cbs_event_cancellation(cancellation_event=cancellation_event, attempt=attempt, payload=payload, event_code=IBS_CBS_EVENT_112150)


def resolve_ibs_cbs_event_cancellation_for_webhook(*, payload: dict[str, Any]) -> FiscalDocumentEvent | None:
    event_uuid = str(payload.get("uuid") or "").strip()
    if not event_uuid:
        return None
    matches = list(
        FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION)
        .filter(Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid))
        .select_related("document", "related_event")
        .distinct()
        .order_by("-pk")[:2]
    )
    if len(matches) != 1:
        return None
    return matches[0]


def is_ambiguous_ibs_cbs_event_cancellation_webhook(*, payload: dict[str, Any]) -> bool:
    event_uuid = str(payload.get("uuid") or "").strip()
    if not event_uuid:
        return False
    return (
        FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION)
        .filter(Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid))
        .distinct()
        .values("pk")[:2]
        .count()
        > 1
    )
