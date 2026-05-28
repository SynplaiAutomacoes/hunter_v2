from __future__ import annotations

import logging
import re
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
from apps.finance.services.nfe_emission import NfeEmissionError
from apps.finance.services.nfe_events import ensure_fiscal_document_for_nfe_item
from apps.finance.services.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting, should_use_global_webmania_auth
from apps.finance.services.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)

ACCESS_KEY_RE = re.compile(r"^\d{44}$")
RESERVING_RETURN_STATUSES = {
    FiscalDocumentStatus.PROCESSING,
    FiscalDocumentStatus.APPROVED,
    FiscalDocumentStatus.CONTINGENCY,
    FiscalDocumentStatus.UNCERTAIN,
}


class NfeReturnError(NfeEmissionError):
    pass


def _build_headers(*, workshop=None) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfeReturnError(str(exc)) from exc


def _build_return_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_RETURN_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/devolucao/"


def _build_consulta_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_CONSULTA_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/consulta/"


def validate_access_key(access_key: str) -> str:
    normalized = str(access_key or "").strip()
    if not ACCESS_KEY_RE.match(normalized):
        raise NfeReturnError("Informe uma chave de acesso de NF-e com 44 digitos.")
    return normalized


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", "."))
    except InvalidOperation as exc:
        raise NfeReturnError("Informe quantidades validas para os produtos da devolucao.") from exc


def _product_sequence(product: dict[str, Any], *, fallback_index: int | None = None) -> int:
    for key in ("sequencial", "sequencia", "numero_item", "item", "produto"):
        value = str(product.get(key) or "").strip()
        if value.isdigit() and int(value) > 0:
            return int(value)
    if fallback_index is not None:
        return fallback_index
    raise NfeReturnError("Cada produto da devolucao parcial deve informar o sequencial fiscal do item na NF-e original.")


def _normalized_partial_products(products: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for product in products or []:
        if not isinstance(product, dict):
            raise NfeReturnError("Produtos da devolucao devem ser objetos.")
        quantity = _decimal(product.get("quantidade"))
        if quantity <= 0:
            raise NfeReturnError("A quantidade de cada produto deve ser maior que zero.")
        normalized.append({"sequencial": _product_sequence(product), "quantidade": str(quantity.normalize())})
    return normalized


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


def _original_quantities(document: FiscalDocument) -> dict[int, Decimal]:
    payload_sources = [
        document.request_payload,
        document.response_payload,
    ]
    if document.legacy_nfe_item_id:
        payload_sources.extend([document.legacy_nfe_item.raw_payload, document.legacy_nfe_item.log_payload])

    quantities: dict[int, Decimal] = {}
    for payload in payload_sources:
        for index, product in enumerate(_extract_products_from_payload(payload), start=1):
            try:
                sequence = _product_sequence(product, fallback_index=index)
                quantity = _decimal(product.get("quantidade"))
            except NfeReturnError:
                continue
            quantities[sequence] = quantities.get(sequence, Decimal("0")) + quantity
    return quantities


def _partial_products_from_return_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    products = payload.get("produtos")
    quantities = payload.get("quantidade")
    if not isinstance(products, list) or not isinstance(quantities, list):
        return []
    partial_products: list[dict[str, Any]] = []
    for index, sequence in enumerate(products):
        quantity = quantities[index] if index < len(quantities) else "0"
        partial_products.append({"sequencial": sequence, "quantidade": quantity})
    return partial_products


def _reserved_return_quantities(*, original_document: FiscalDocument) -> dict[int, Decimal]:
    documents = FiscalDocument.objects.filter(
        links_from__related_document=original_document,
        links_from__role__in=[FiscalDocumentLinkRole.RETURNS, FiscalDocumentLinkRole.REVERSES],
        purpose__in=[FiscalDocumentPurpose.RETURN, FiscalDocumentPurpose.REVERSAL],
        status__in=RESERVING_RETURN_STATUSES,
    )
    quantities: dict[int, Decimal] = {}
    for document in documents:
        for product in _partial_products_from_return_payload(document.request_payload):
            try:
                sequence = _product_sequence(product)
                quantity = _decimal(product.get("quantidade"))
            except NfeReturnError:
                continue
            quantities[sequence] = quantities.get(sequence, Decimal("0")) + quantity
    return quantities


def calculate_available_return_quantities(*, original_document: FiscalDocument) -> dict[int, Decimal]:
    original_quantities = _original_quantities(original_document)
    reserved_quantities = _reserved_return_quantities(original_document=original_document)
    return {sequence: quantity - reserved_quantities.get(sequence, Decimal("0")) for sequence, quantity in original_quantities.items()}


def _validate_available_quantities(*, original_document: FiscalDocument, products: list[dict[str, Any]]) -> None:
    if not products:
        return
    original_quantities = _original_quantities(original_document)
    if not original_quantities:
        return
    available_quantities = calculate_available_return_quantities(original_document=original_document)
    for product in products:
        sequence = _product_sequence(product)
        requested = _decimal(product.get("quantidade"))
        available = available_quantities.get(sequence, Decimal("0"))
        if requested > available:
            raise NfeReturnError(f"Quantidade solicitada para devolucao do item fiscal {sequence} excede o saldo disponivel.")


def is_local_nfe_eligible_for_return(item: NfeItem | None) -> bool:
    if item is None:
        return False
    if str(getattr(item, "status", "")).strip().lower() != NfeItemStatus.aprovado:
        return False
    return bool(str(getattr(item, "access_key", "") or "").strip())


def ensure_external_original_document(*, workshop: Any, access_key: str, requested_by: Any | None = None, confirmed_external: bool = False) -> FiscalDocument:
    access_key = validate_access_key(access_key)
    if not confirmed_external:
        raise NfeReturnError("Confirme explicitamente que a NF-e externa nao foi validada remotamente pelo Hunter.")

    existing = FiscalDocument.objects.filter(workshop=workshop, document_type=FiscalDocumentType.NFE, access_key=access_key).first()
    if existing is not None:
        return existing

    return FiscalDocument.objects.create(
        workshop=workshop,
        account=getattr(workshop, "account", None),
        document_type=FiscalDocumentType.NFE,
        origin=FiscalDocumentOrigin.EXTERNAL,
        purpose=FiscalDocumentPurpose.NORMAL,
        access_key=access_key,
        environment=str(getattr(settings, "WEBMANIA_AMBIENT", "2") or "2").strip(),
        status=FiscalDocumentStatus.PROCESSING,
        remote_status="external_unvalidated",
        requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
        external_confirmation=True,
        external_confirmed_at=timezone.now(),
        response_payload=sanitize_fiscal_payload({"origin": "external", "validated_remotely": False}),
    )


def _operation_type_for_purpose(purpose: str) -> str:
    if purpose == FiscalDocumentPurpose.REVERSAL:
        return FiscalEmissionOperationType.REVERSAL
    if purpose == FiscalDocumentPurpose.RETURN:
        return FiscalEmissionOperationType.RETURN
    raise NfeReturnError("Finalidade de documento derivado nao suportada nesta fase.")


def _role_for_purpose(purpose: str) -> str:
    return FiscalDocumentLinkRole.REVERSES if purpose == FiscalDocumentPurpose.REVERSAL else FiscalDocumentLinkRole.RETURNS


def _build_return_payload(
    *,
    original_document: FiscalDocument,
    purpose: str,
    products: list[dict[str, Any]] | None,
    natureza_operacao: str,
    codigo_cfop: str,
    volume: dict[str, Any] | None = None,
    informacoes_fisco: str = "",
    informacoes_complementares: str = "",
    request: HttpRequest | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chave": validate_access_key(original_document.access_key),
        "natureza_operacao": str(natureza_operacao or ("Estorno de NF-e" if purpose == FiscalDocumentPurpose.REVERSAL else "Devolucao de mercadoria")).strip(),
        "ambiente": int(str(original_document.environment or getattr(settings, "WEBMANIA_AMBIENT", "2") or "2")),
        "codigo_cfop": str(codigo_cfop or "").strip(),
    }
    if purpose == FiscalDocumentPurpose.RETURN and products:
        payload["produtos"] = [_product_sequence(product) for product in products]
        payload["quantidade"] = [str(_decimal(product.get("quantidade")).normalize()) for product in products]
    if purpose == FiscalDocumentPurpose.REVERSAL:
        payload["tipo_operacao_hunter"] = "estorno"
    if volume:
        payload["volume"] = volume
    if informacoes_fisco:
        payload["informacoes_fisco"] = str(informacoes_fisco).strip()
    if informacoes_complementares:
        payload["informacoes_complementares"] = str(informacoes_complementares).strip()
    notification_url = build_webmania_webhook_url(request=request)
    if notification_url:
        payload["url_notificacao"] = notification_url
    return payload


def create_nfe_return_draft(
    *,
    original_document: FiscalDocument,
    purpose: str,
    products: list[dict[str, Any]],
    requested_by: Any | None = None,
    natureza_operacao: str = "",
    codigo_cfop: str = "",
    volume: dict[str, Any] | None = None,
    informacoes_fisco: str = "",
    informacoes_complementares: str = "",
    request: HttpRequest | None = None,
) -> FiscalDocument:
    purpose = str(purpose or "").strip()
    operation_type = _operation_type_for_purpose(purpose)
    products = _normalized_partial_products(products)

    with transaction.atomic():
        locked_original = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=original_document.pk)
        if locked_original.workshop_id != original_document.workshop_id:
            raise NfeReturnError("Documento original invalido para a oficina atual.")
        if not locked_original.access_key:
            raise NfeReturnError("Documento original precisa possuir chave de acesso valida.")
        if locked_original.origin == FiscalDocumentOrigin.LOCAL and locked_original.legacy_nfe_item_id and not is_local_nfe_eligible_for_return(locked_original.legacy_nfe_item):
            raise NfeReturnError("Devolucao ou estorno permitidos somente para NF-e local autorizada.")
        if locked_original.origin == FiscalDocumentOrigin.EXTERNAL and products:
            raise NfeReturnError("NF-e externa minima sem itens importados permite somente devolucao total ou estorno; devolucao parcial exige XML/importacao validada.")
        if purpose == FiscalDocumentPurpose.REVERSAL:
            products = []
        _validate_available_quantities(original_document=locked_original, products=products)
        payload = _build_return_payload(
            original_document=locked_original,
            purpose=purpose,
            products=products,
            natureza_operacao=natureza_operacao,
            codigo_cfop=codigo_cfop,
            volume=volume,
            informacoes_fisco=informacoes_fisco,
            informacoes_complementares=informacoes_complementares,
            request=request,
        )
        sanitized_payload = sanitize_fiscal_payload(payload)
        derived_document = FiscalDocument.objects.create(
            workshop=locked_original.workshop,
            account=locked_original.account,
            document_type=FiscalDocumentType.NFE,
            origin=FiscalDocumentOrigin.DERIVED,
            purpose=purpose,
            environment=str(payload["ambiente"]),
            status=FiscalDocumentStatus.PROCESSING,
            remote_status=FiscalEmissionAttemptStatus.STARTED,
            request_payload=sanitized_payload,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
        )
        FiscalDocumentLink.objects.create(
            document=derived_document,
            related_document=locked_original,
            role=_role_for_purpose(purpose),
            metadata=sanitize_fiscal_payload({"operation_type": operation_type}),
        )
        return derived_document


def create_nfe_return_draft_from_item(
    *,
    item: NfeItem,
    purpose: str,
    products: list[dict[str, Any]],
    requested_by: Any | None = None,
    natureza_operacao: str = "",
    codigo_cfop: str = "",
    volume: dict[str, Any] | None = None,
    informacoes_fisco: str = "",
    informacoes_complementares: str = "",
    request: HttpRequest | None = None,
) -> FiscalDocument:
    if not is_local_nfe_eligible_for_return(item):
        raise NfeReturnError("Devolucao ou estorno permitidos somente para NF-e autorizada com chave de acesso valida.")
    original_document = ensure_fiscal_document_for_nfe_item(item=item)
    return create_nfe_return_draft(
        original_document=original_document,
        purpose=purpose,
        products=products,
        requested_by=requested_by,
        natureza_operacao=natureza_operacao,
        codigo_cfop=codigo_cfop,
        volume=volume,
        informacoes_fisco=informacoes_fisco,
        informacoes_complementares=informacoes_complementares,
        request=request,
    )


def create_nfe_return_draft_from_external(
    *,
    workshop: Any,
    access_key: str,
    purpose: str,
    products: list[dict[str, Any]],
    requested_by: Any | None = None,
    confirmed_external: bool = False,
    natureza_operacao: str = "",
    codigo_cfop: str = "",
    volume: dict[str, Any] | None = None,
    informacoes_fisco: str = "",
    informacoes_complementares: str = "",
    request: HttpRequest | None = None,
) -> FiscalDocument:
    original_document = ensure_external_original_document(workshop=workshop, access_key=access_key, requested_by=requested_by, confirmed_external=confirmed_external)
    return create_nfe_return_draft(
        original_document=original_document,
        purpose=purpose,
        products=products,
        requested_by=requested_by,
        natureza_operacao=natureza_operacao,
        codigo_cfop=codigo_cfop,
        volume=volume,
        informacoes_fisco=informacoes_fisco,
        informacoes_complementares=informacoes_complementares,
        request=request,
    )


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


def apply_nfe_return_document_payload(*, document: FiscalDocument, response_payload: dict[str, Any]) -> FiscalDocument:
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
    if document.origin != FiscalDocumentOrigin.DERIVED or document.purpose not in {FiscalDocumentPurpose.RETURN, FiscalDocumentPurpose.REVERSAL}:
        raise NfeReturnError("Documento fiscal derivado invalido para transmissao de devolucao ou estorno.")
    existing_attempt = document.emission_attempts.filter(operation_type__in=[FiscalEmissionOperationType.RETURN, FiscalEmissionOperationType.REVERSAL]).order_by("-pk").first()
    if existing_attempt is None:
        return
    if existing_attempt.status == FiscalEmissionAttemptStatus.UNCERTAIN:
        raise NfeReturnError("Ja existe tentativa de devolucao ou estorno em estado remoto incerto. Reconcilie antes de tentar novamente.")
    if existing_attempt.status in {FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.SUCCEEDED}:
        raise NfeReturnError("Esta intencao de devolucao ou estorno ja possui envio remoto registrado.")
    raise NfeReturnError("Esta intencao de devolucao ou estorno ja possui tentativa fiscal registrada.")


def transmit_nfe_return_document(*, document: FiscalDocument) -> FiscalDocument:
    with transaction.atomic():
        locked_document = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=document.pk)
        _assert_transmittable(document=locked_document)
        operation_type = _operation_type_for_purpose(locked_document.purpose)
        payload = dict(locked_document.request_payload or {})
        idempotency_key = build_fiscal_document_operation_idempotency_key(
            workshop_id=locked_document.workshop_id,
            derived_document_id=locked_document.pk,
            operation_type=operation_type,
            request_generation=1,
        )
        try:
            attempt = begin_emission_attempt(
                workshop=locked_document.workshop,
                document_kind=FiscalEmissionDocumentKind.NFE,
                operation_type=operation_type,
                request_model=FiscalDocument.__name__,
                request_id=locked_document.pk,
                fiscal_document=locked_document,
                idempotency_key=idempotency_key,
                request_payload=payload,
                payload_hash=build_payload_hash(payload),
            )
        except FiscalEmissionAttemptBlocked as exc:
            raise NfeReturnError(str(exc)) from exc

    headers = _build_headers(workshop=locked_document.workshop)
    mark_attempt_sent(attempt=attempt)

    try:
        response = requests.post(_build_return_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao emitir devolucao ou estorno; estado remoto incerto."
        logger.warning("nfe_return_timeout", extra={"fiscal_document_id": locked_document.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_document_uncertain(document=locked_document, error_message=message)
        raise NfeReturnError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao emitir devolucao ou estorno", scope="nfe")
        logger.warning("nfe_return_request_failed", extra={"fiscal_document_id": locked_document.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_failed(attempt=attempt, error_message=message)
        locked_document.status = FiscalDocumentStatus.REPROVED
        locked_document.response_payload = sanitize_fiscal_payload({"error": message})
        locked_document.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfeReturnError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida da Webmania ao emitir devolucao ou estorno; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_document_uncertain(document=locked_document, error_message=message)
        raise NfeReturnError(message) from exc

    if not isinstance(response_payload, dict):
        message = "Resposta invalida da Webmania ao emitir devolucao ou estorno; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_document_uncertain(document=locked_document, error_message=message)
        raise NfeReturnError(message)

    locked_document = apply_nfe_return_document_payload(document=locked_document, response_payload=response_payload)
    if _is_failed_response(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or "Devolucao ou estorno rejeitado pela Webmania."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfeReturnError(message)

    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    return locked_document


def create_and_emit_nfe_return_from_item(**kwargs: Any) -> FiscalDocument:
    document = create_nfe_return_draft_from_item(**kwargs)
    return transmit_nfe_return_document(document=document)


def create_and_emit_nfe_return_from_external(**kwargs: Any) -> FiscalDocument:
    document = create_nfe_return_draft_from_external(**kwargs)
    return transmit_nfe_return_document(document=document)


def consult_nfe_return_document(*, document: FiscalDocument) -> dict[str, Any]:
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
        raise NfeReturnError("Nao foi possivel consultar a devolucao ou estorno sem UUID ou chave de acesso.")

    try:
        response = requests.get(_build_consulta_url(), params=params, headers=_build_headers(workshop=document.workshop), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao consultar devolucao ou estorno", scope="nfe")
        raise NfeReturnError(message) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise NfeReturnError("Resposta invalida da API de consulta de devolucao ou estorno.") from exc
    if not isinstance(payload, dict):
        raise NfeReturnError("Resposta invalida da API de consulta de devolucao ou estorno.")
    error_message = extract_webmania_error_message(payload.get("error") or payload.get("msg") or payload.get("message"), scope="nfe")
    if error_message:
        raise NfeReturnError(error_message)
    return payload


def reconcile_nfe_return_document(*, document: FiscalDocument) -> FiscalDocument:
    payload = consult_nfe_return_document(document=document)
    document = apply_nfe_return_document_payload(document=document, response_payload=payload)
    document.refresh_from_db()
    return document


def resolve_nfe_return_document_for_webhook(*, payload: dict[str, Any]) -> FiscalDocument | None:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    queryset = FiscalDocument.objects.filter(origin=FiscalDocumentOrigin.DERIVED, purpose__in=[FiscalDocumentPurpose.RETURN, FiscalDocumentPurpose.REVERSAL])
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(access_key=access_key)
    if not event_uuid and not access_key:
        return None
    candidates = queryset.filter(filters).distinct().order_by("-pk")[:2]
    matches = list(candidates)
    if len(matches) != 1:
        return None
    return matches[0]


def is_ambiguous_nfe_return_webhook(*, payload: dict[str, Any]) -> bool:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    if not event_uuid and not access_key:
        return False
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(access_key=access_key)
    count = (
        FiscalDocument.objects.filter(origin=FiscalDocumentOrigin.DERIVED, purpose__in=[FiscalDocumentPurpose.RETURN, FiscalDocumentPurpose.REVERSAL])
        .filter(filters)
        .distinct()
        .values("pk")[:2]
        .count()
    )
    return count > 1
