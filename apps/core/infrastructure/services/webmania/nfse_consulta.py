from __future__ import annotations

from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.finance.models.finance import NfseItem
from apps.core.infrastructure.services.webmania.emission import apply_nfse_item_payload
from apps.core.infrastructure.services.webmania.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


class NfseConsultaError(Exception):
    pass


def _build_headers(*, workshop=None) -> dict[str, str]:
    try:
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfseConsultaError(str(exc)) from exc


def _build_consulta_url(*, event_uuid: str) -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFSE_CONSULTA_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/{event_uuid}"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_BASE_URL", "https://api.webmania.com.br/2/")).rstrip("/")
    return f"{base_url}/nfse/consulta/{event_uuid}"


def consult_nfse_uuid(*, workshop: Any, event_uuid: str) -> dict[str, Any]:
    normalized_uuid = str(event_uuid or "").strip()
    if not normalized_uuid:
        raise NfseConsultaError("Nao foi possivel consultar a NFS-e ou lote sem UUID.")

    try:
        response = requests.get(
            _build_consulta_url(event_uuid=normalized_uuid),
            headers=_build_headers(workshop=workshop),
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao consultar status da Nota Fiscal de Servico", scope="nfse")
        raise NfseConsultaError(message) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise NfseConsultaError("Resposta invalida da API de consulta da Nota Fiscal de Servico.") from exc

    if not isinstance(payload, dict):
        raise NfseConsultaError("Resposta invalida da API de consulta da Nota Fiscal de Servico.")

    sanitized_payload = sanitize_fiscal_payload(payload)
    error_message = extract_webmania_error_message(sanitized_payload.get("error") or sanitized_payload.get("msg") or sanitized_payload.get("message"), scope="nfse")
    if error_message:
        raise NfseConsultaError(error_message)

    return sanitized_payload


def consult_nfse_item(*, item: NfseItem) -> dict[str, Any]:
    if item.request_id:
        try:
            validate_nfse_query_capability(nfse_request=item.request)
        except NfseCapabilityError as exc:
            raise NfseConsultaError(str(exc)) from exc
    return consult_nfse_uuid(workshop=item.workshop, event_uuid=str(item.uuid or ""))


def consult_nfse_batch(*, batch: NfseBatch) -> dict[str, Any]:
    if batch.request_id:
        try:
            validate_nfse_query_capability(nfse_request=batch.request)
        except NfseCapabilityError as exc:
            raise NfseConsultaError(str(exc)) from exc
    return consult_nfse_uuid(workshop=batch.workshop, event_uuid=str(batch.uuid or ""))


def _validate_query_identity(*, payload: dict[str, Any], expected_uuid: str, expected_model: str) -> None:
    payload_uuid = str(payload.get("uuid") or "").strip().lower()
    if not payload_uuid or payload_uuid != str(expected_uuid).strip().lower():
        raise NfseConsultaError("A consulta retornou UUID diferente do registro local; nenhuma atualizacao foi aplicada.")

    payload_model = str(payload.get("modelo") or "").strip().lower()
    if payload_model != expected_model:
        raise NfseConsultaError("A consulta retornou modelo fiscal diferente do registro local; nenhuma atualizacao foi aplicada.")


def _ensure_unique_item_uuid(*, item: NfseItem) -> None:
    if NfseItem.objects.filter(uuid=item.uuid).exclude(pk=item.pk).exists():
        raise NfseConsultaError("UUID NFS-e ambiguo entre registros locais; nenhuma atualizacao foi aplicada.")


def _ensure_unique_batch_uuid(*, batch: NfseBatch) -> None:
    if NfseBatch.objects.filter(uuid=batch.uuid).exclude(pk=batch.pk).exists():
        raise NfseConsultaError("UUID de lote RPS ambiguo entre registros locais; nenhuma atualizacao foi aplicada.")


def reconcile_nfse_item(*, item: NfseItem) -> NfseItem:
    try:
        payload = consult_nfse_item(item=item)
        with transaction.atomic():
            locked_item = NfseItem.objects.select_for_update().get(pk=item.pk, workshop=item.workshop)
            _ensure_unique_item_uuid(item=locked_item)
            _validate_query_identity(payload=payload, expected_uuid=str(locked_item.uuid), expected_model="nfse")
            reconciled_at = timezone.now()
            applied_item = apply_nfse_item_payload(
                item=locked_item,
                response_payload=payload,
                reconciled_at=reconciled_at,
                update_source="query",
            )
            if applied_item.last_reconciled_at != reconciled_at:
                applied_item.last_reconciled_at = reconciled_at
                applied_item.last_sync_error = ""
                applied_item.save(update_fields=["last_reconciled_at", "last_sync_error"])
        item.refresh_from_db()
        return item
    except NfseConsultaError as exc:
        item.last_sync_error = str(exc)
        item.save(update_fields=["last_sync_error"])
        raise


def _reconcile_batch_items(*, batch: NfseBatch, payload: dict[str, Any], reconciled_at: Any) -> None:
    raw_items = payload.get("info_nfse") or []
    if not isinstance(raw_items, list):
        raise NfseConsultaError("O retorno do lote possui info_nfse invalido; nenhuma atualizacao foi aplicada.")

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise NfseConsultaError("O retorno do lote possui item invalido; nenhuma atualizacao foi aplicada.")

        item_uuid = str(raw_item.get("uuid") or "").strip()
        if not item_uuid:
            raise NfseConsultaError("O retorno do lote possui item sem UUID; nenhuma atualizacao foi aplicada.")

        matches = list(NfseItem.objects.select_for_update().filter(uuid=item_uuid).order_by("pk")[:2])
        if len(matches) > 1:
            raise NfseConsultaError("UUID de item NFS-e ambiguo no retorno do lote; nenhuma atualizacao foi aplicada.")

        if matches:
            nfse_item = matches[0]
            if nfse_item.workshop_id != batch.workshop_id or nfse_item.request_id != batch.request_id:
                raise NfseConsultaError("Item NFS-e do lote pertence a outro escopo; nenhuma atualizacao foi aplicada.")
        else:
            nfse_item = NfseItem.objects.create(
                workshop=batch.workshop,
                workorder=batch.workorder,
                request=batch.request,
                batch=batch,
                uuid=item_uuid,
            )

        nfse_item.batch = batch
        nfse_item.request = batch.request
        apply_nfse_item_payload(
            item=nfse_item,
            response_payload=raw_item,
            reconciled_at=reconciled_at,
            update_source="query",
        )


def reconcile_nfse_batch(*, batch: NfseBatch) -> NfseBatch:
    try:
        payload = consult_nfse_batch(batch=batch)
        reconciled_at = timezone.now()
        with transaction.atomic():
            locked_batch = NfseBatch.objects.select_for_update().get(pk=batch.pk, workshop=batch.workshop)
            _ensure_unique_batch_uuid(batch=locked_batch)
            _validate_query_identity(payload=payload, expected_uuid=str(locked_batch.uuid), expected_model="lote_rps")
            applied_batch = apply_nfse_batch_payload(
                batch=locked_batch,
                response_payload=payload,
                reconciled_at=reconciled_at,
                update_source="query",
            )
            if applied_batch.last_reconciled_at != reconciled_at:
                applied_batch.last_reconciled_at = reconciled_at
                applied_batch.last_sync_error = ""
                applied_batch.save(update_fields=["last_reconciled_at", "last_sync_error"])
            _reconcile_batch_items(batch=locked_batch, payload=payload, reconciled_at=reconciled_at)
        batch.refresh_from_db()
        return batch
    except NfseConsultaError as exc:
        batch.last_sync_error = str(exc)
        batch.save(update_fields=["last_sync_error"])
        raise
