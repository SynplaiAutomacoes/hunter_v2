from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest

from apps.finance.models.finance import (
    FiscalCreditProductPreview,
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
    FiscalProductPreviewStatus,
    FiscalReferencedBasisStatus,
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
from apps.finance.services.fiscal_credit_product_preview import detect_forbidden_groups
from apps.finance.services.fiscal_referenced_basis import is_credit_debit_basis_enabled
from apps.finance.services.nfe_emission import NfeEmissionError, _build_customer_payload, _build_payment_payload
from apps.finance.services.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting, should_use_global_webmania_auth
from apps.finance.services.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)


class NfeCreditError(Exception):
    pass


def _build_headers(*, workshop: Any) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfeCreditError(str(exc)) from exc


def _build_emission_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_EMISSION_ENDPOINT", ""))
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


def _validate_preview(*, preview: FiscalCreditProductPreview, workshop: Any) -> None:
    if not is_credit_debit_basis_enabled(workshop=workshop):
        raise NfeCreditError("A emissao fiscal de credito/debito esta desabilitada para esta oficina.")
    if preview.workshop_id != workshop.pk:
        raise NfeCreditError("A previa pertence a outra oficina.")
    if preview.validation_status != FiscalProductPreviewStatus.APPROVED:
        raise NfeCreditError("Somente previa fiscal aprovada pode emitir NF-e de credito.")
    if preview.operation_type != "credit" or preview.fiscal_purpose_type != "1":
        raise NfeCreditError("Esta fase suporta somente NF-e de credito tipo 1 por multa/juros.")
    if preview.basis.status != FiscalReferencedBasisStatus.APPROVED:
        raise NfeCreditError("A base fiscal referenciada precisa estar aprovada.")
    if preview.basis.workshop_id != workshop.pk or preview.basis_item.basis_id != preview.basis_id:
        raise NfeCreditError("Base fiscal ou item fora do escopo da oficina.")
    if preview.basis.source_document_id is None:
        raise NfeCreditError("A emissao de credito tipo 1 exige NF-e original local vinculada.")
    if len(preview.source_access_key) != 44 or not preview.source_access_key.isdigit():
        raise NfeCreditError("A NF-e referenciada deve possuir chave valida de 44 digitos.")
    if preview.product_total_amount <= 0 or preview.basis_item.credit_debit_base_amount <= 0:
        raise NfeCreditError("O produto fiscal de multa/juros deve possuir total positivo.")
    if not isinstance(preview.ibs_cbs_payload, dict) or not preview.ibs_cbs_payload:
        raise NfeCreditError("A previa aprovada nao possui snapshot IBS/CBS.")
    forbidden = detect_forbidden_groups(dict(preview.product_payload or {}))
    if forbidden or preview.forbidden_tax_groups_detected:
        raise NfeCreditError("A previa aprovada contem grupos tributarios proibidos.")


def _build_credit_payload(*, preview: FiscalCreditProductPreview, request: HttpRequest | None = None) -> dict[str, Any]:
    source_document = preview.basis.source_document
    if source_document is None or source_document.legacy_nfe_item_id is None:
        raise NfeCreditError("A NF-e original local nao possui origem operacional para cliente e pedido.")
    nfe_request = source_document.legacy_nfe_item.request
    try:
        cliente = _build_customer_payload(nfe_request)
        pedido = _build_payment_payload(workorder=nfe_request.workorder, total_value=Decimal(preview.product_total_amount))
    except NfeEmissionError as exc:
        raise NfeCreditError(str(exc)) from exc

    product = sanitize_fiscal_payload(dict(preview.product_payload or {}))
    forbidden = detect_forbidden_groups(product)
    if forbidden:
        raise NfeCreditError(f"Produto fiscal contem campos proibidos: {', '.join(forbidden)}.")
    taxes = product.get("impostos")
    if not isinstance(taxes, dict) or set(taxes) != {"ibs_cbs"}:
        raise NfeCreditError("NF-e de credito tipo 1 deve enviar somente impostos.ibs_cbs.")
    payload: dict[str, Any] = {
        "ID": f"credit-preview-{preview.pk}",
        "operacao": 0,
        "natureza_operacao": "Credito por multa e juros",
        "modelo": 1,
        "finalidade": 5,
        "tipo_credito": 1,
        "ambiente": int(str(getattr(settings, "WEBMANIA_AMBIENT", "2") or "2")),
        "nfe_referenciada": [preview.source_access_key],
        "cliente": sanitize_fiscal_payload(cliente),
        "produtos": [product],
        "pedido": sanitize_fiscal_payload(pedido),
    }
    notification_url = build_webmania_webhook_url(request=request)
    if notification_url:
        payload["url_notificacao"] = notification_url
    return sanitize_fiscal_payload(payload)


def _status_from_payload(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip().lower()
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
    return FiscalDocumentStatus.PROCESSING


def apply_nfe_credit_document_payload(*, document: FiscalDocument, response_payload: dict[str, Any]) -> FiscalDocument:
    document.response_payload = sanitize_fiscal_payload(response_payload)
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


def _is_failed_response(payload: dict[str, Any]) -> bool:
    return _status_from_payload(payload) in {FiscalDocumentStatus.REPROVED, FiscalDocumentStatus.DENIED}


def create_and_emit_nfe_credit_type_one(*, preview: FiscalCreditProductPreview, workshop: Any, requested_by: Any, legal_confirmation: bool, request: HttpRequest | None = None) -> FiscalDocument:
    if not legal_confirmation:
        raise NfeCreditError("Confirme explicitamente a emissao da NF-e de credito tipo 1.")
    with transaction.atomic():
        locked_preview = FiscalCreditProductPreview.objects.select_for_update(of=("self",)).select_related("basis__source_document__legacy_nfe_item__request__workorder__budget__customer", "basis_item").get(pk=preview.pk, workshop=workshop)
        _validate_preview(preview=locked_preview, workshop=workshop)
        if FiscalDocument.objects.filter(credit_product_preview=locked_preview).exists():
            raise NfeCreditError("Esta previa ja possui uma emissao fiscal ativa ou concluida.")
        payload = _build_credit_payload(preview=locked_preview, request=request)
        source_document = locked_preview.basis.source_document
        assert source_document is not None
        document = FiscalDocument.objects.create(
            workshop=workshop,
            account=getattr(workshop, "account", None),
            document_type=FiscalDocumentType.NFE,
            origin=FiscalDocumentOrigin.DERIVED,
            purpose=FiscalDocumentPurpose.CREDIT,
            fiscal_purpose_type="1",
            referenced_basis=locked_preview.basis,
            credit_product_preview=locked_preview,
            environment=str(payload["ambiente"]),
            status=FiscalDocumentStatus.PROCESSING,
            remote_status=FiscalEmissionAttemptStatus.STARTED,
            request_payload=payload,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
        )
        FiscalDocumentLink.objects.create(document=document, related_document=source_document, role=FiscalDocumentLinkRole.CREDITS, metadata={"fiscal_purpose_type": "1", "preview_id": locked_preview.pk, "basis_id": locked_preview.basis_id})
        idempotency_key = build_fiscal_document_operation_idempotency_key(workshop_id=workshop.pk, derived_document_id=document.pk, operation_type=FiscalEmissionOperationType.NFE_CREDIT_EMISSION)
        try:
            attempt = begin_emission_attempt(
                workshop=workshop,
                document_kind=FiscalEmissionDocumentKind.NFE,
                operation_type=FiscalEmissionOperationType.NFE_CREDIT_EMISSION,
                request_model=FiscalDocument.__name__,
                request_id=document.pk,
                fiscal_document=document,
                idempotency_key=idempotency_key,
                request_payload=payload,
                payload_hash=build_payload_hash(payload),
            )
        except FiscalEmissionAttemptBlocked as exc:
            raise NfeCreditError(str(exc)) from exc

    headers = _build_headers(workshop=workshop)
    mark_attempt_sent(attempt=attempt)
    try:
        response = requests.post(_build_emission_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao emitir NF-e de credito; estado remoto incerto."
        logger.warning("nfe_credit_timeout", extra={"fiscal_document_id": document.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        document.status = FiscalDocumentStatus.UNCERTAIN
        document.remote_status = FiscalEmissionAttemptStatus.UNCERTAIN
        document.response_payload = {"error": message}
        document.save(update_fields=["status", "remote_status", "response_payload", "atualizado_em"])
        raise NfeCreditError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao emitir NF-e de credito", scope="nfe")
        mark_attempt_failed(attempt=attempt, error_message=message)
        document.status = FiscalDocumentStatus.REPROVED
        document.response_payload = {"error": message}
        document.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfeCreditError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida da Webmania ao emitir NF-e de credito; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        document.status = FiscalDocumentStatus.UNCERTAIN
        document.remote_status = FiscalEmissionAttemptStatus.UNCERTAIN
        document.save(update_fields=["status", "remote_status", "atualizado_em"])
        raise NfeCreditError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta invalida da Webmania ao emitir NF-e de credito; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        document.status = FiscalDocumentStatus.UNCERTAIN
        document.remote_status = FiscalEmissionAttemptStatus.UNCERTAIN
        document.save(update_fields=["status", "remote_status", "atualizado_em"])
        raise NfeCreditError(message)
    document = apply_nfe_credit_document_payload(document=document, response_payload=response_payload)
    if _is_failed_response(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or "NF-e de credito rejeitada pela Webmania."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfeCreditError(message)
    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    return document


def consult_nfe_credit_document(*, document: FiscalDocument) -> dict[str, Any]:
    identifier = str(document.remote_uuid or document.access_key or "").strip()
    if not identifier:
        attempt = document.emission_attempts.exclude(remote_uuid="").order_by("-pk").first()
        identifier = str(attempt.remote_uuid if attempt else "").strip()
    if not identifier:
        raise NfeCreditError("Nao foi possivel consultar a NF-e de credito sem UUID ou chave.")
    params = {"uuid": identifier} if len(identifier) != 44 else {"chave": identifier}
    try:
        response = requests.get(_build_consulta_url(), params=params, headers=_build_headers(workshop=document.workshop), timeout=30)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise NfeCreditError("Falha ao consultar NF-e de credito na Webmania.") from exc
    if not isinstance(payload, dict):
        raise NfeCreditError("Resposta invalida da consulta da NF-e de credito.")
    return payload


def reconcile_nfe_credit_document(*, document: FiscalDocument) -> FiscalDocument:
    return apply_nfe_credit_document_payload(document=document, response_payload=consult_nfe_credit_document(document=document))


def _credit_webhook_queryset(payload: dict[str, Any]):
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(access_key=access_key) | Q(emission_attempts__remote_key=access_key)
    return FiscalDocument.objects.filter(purpose=FiscalDocumentPurpose.CREDIT, fiscal_purpose_type="1").filter(filters).distinct() if filters else FiscalDocument.objects.none()


def resolve_nfe_credit_document_for_webhook(*, payload: dict[str, Any]) -> FiscalDocument | None:
    matches = list(_credit_webhook_queryset(payload).order_by("-pk")[:2])
    return matches[0] if len(matches) == 1 else None


def is_ambiguous_nfe_credit_webhook(*, payload: dict[str, Any]) -> bool:
    return _credit_webhook_queryset(payload).values("pk")[:2].count() > 1
