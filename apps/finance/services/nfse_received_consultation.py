from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.finance.models.finance import NfseReceivedDocument, NfseReceivedDocumentConsultation
from apps.core.infrastructure.services.webmania.nfse_consulta import NfseConsultaError, consult_nfse_uuid
from apps.finance.services.nfse_received import normalize_tax_id


class NfseReceivedConsultationError(ValidationError):
    pass


def _select_identifier(document: NfseReceivedDocument) -> tuple[str, str]:
    if str(document.uuid or "").strip():
        return str(document.uuid).strip(), "uuid"
    if str(document.access_key_or_identifier or "").strip():
        return str(document.access_key_or_identifier).strip(), "access_key_or_identifier"
    raise NfseReceivedConsultationError("NFS-e recebida sem UUID ou identificador seguro para consulta.")


def _assert_consultation_eligible(document: NfseReceivedDocument) -> None:
    if document.source != NfseReceivedDocument.Source.XML_UPLOAD:
        raise NfseReceivedConsultationError("Consulta auxiliar exige NFS-e recebida criada por XML.")
    if document.validation_status != NfseReceivedDocument.ValidationStatus.VALIDATED:
        raise NfseReceivedConsultationError("Consulta auxiliar exige NFS-e recebida validada.")
    if not str(document.xml_snapshot or "").strip():
        raise NfseReceivedConsultationError("Consulta auxiliar exige XML recebido preservado.")
    if not str(document.xml_hash or "").strip():
        raise NfseReceivedConsultationError("Consulta auxiliar exige hash do XML recebido.")
    if not getattr(document.company, "nfse_received_consultation_enabled", False):
        raise NfseReceivedConsultationError("Consulta de NFS-e recebida não esta habilitada para esta empresa.")
    _select_identifier(document)


def is_nfse_received_document_eligible_for_consultation(document: NfseReceivedDocument | None) -> bool:
    if document is None:
        return False
    try:
        _assert_consultation_eligible(document)
    except NfseReceivedConsultationError:
        return False
    return True


def nfse_received_document_consultation_block_reason(document: NfseReceivedDocument | None) -> str:
    if document is None:
        return "Documento recebido indisponível."
    try:
        _assert_consultation_eligible(document)
    except NfseReceivedConsultationError as exc:
        return "; ".join(getattr(exc, "messages", [str(exc)]))
    return ""


def _first_payload_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return ""


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_amount(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    normalized = raw.replace(".", "").replace(",", ".") if "," in raw else raw
    try:
        return Decimal(normalized).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _parse_remote_updated_at(payload: dict[str, Any]) -> Any | None:
    raw_value = _first_payload_value(payload, "atualizado_em", "updated_at", "remote_updated_at")
    parsed = parse_datetime(str(raw_value or ""))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed


def _payload_bool(payload: dict[str, Any], *keys: str) -> bool | None:
    value = _first_payload_value(payload, *keys)
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "sim", "yes", "padrao_nacional", "padrão nacional"}:
        return True
    if normalized in {"false", "0", "nao", "não", "no"}:
        return False
    return None


def _append_divergence(divergences: list[dict[str, str]], *, field: str, local: Any, remote: Any, message: str) -> None:
    divergences.append(
        {
            "field": field,
            "local": str(local or ""),
            "remote": str(remote or ""),
            "message": message,
        }
    )


def build_received_consultation_divergences(*, document: NfseReceivedDocument, payload: dict[str, Any], national_standard_confirmed: bool | None) -> list[dict[str, str]]:
    divergences: list[dict[str, str]] = []
    payload_uuid = str(_first_payload_value(payload, "uuid", "chave", "chave_acesso") or "").strip()
    if document.uuid and payload_uuid and payload_uuid.lower() != str(document.uuid).lower():
        _append_divergence(divergences, field="uuid", local=document.uuid, remote=payload_uuid, message="UUID remoto diverge do XML validado.")

    remote_status = str(_first_payload_value(payload, "status", "situacao", "situacao_nfse") or "").strip()
    if document.remote_status and remote_status and _normalize_text(remote_status) != _normalize_text(document.remote_status):
        _append_divergence(divergences, field="remote_status", local=document.remote_status, remote=remote_status, message="Status remoto consultado diverge do status extraido do XML.")
    if any(marker in _normalize_text(remote_status) for marker in ("cancelad", "substituid", "anulad")):
        _append_divergence(divergences, field="remote_status", local=document.remote_status, remote=remote_status, message="Consulta indica documento remoto cancelado, substituido ou anulado.")

    provider_tax_id = normalize_tax_id(str(_first_payload_value(payload, "provider_tax_id", "prestador_cnpj", "cnpj_prestador", "prestador") or ""))
    if document.provider_tax_id and provider_tax_id and provider_tax_id != document.provider_tax_id:
        _append_divergence(divergences, field="provider_tax_id", local=document.provider_tax_id, remote=provider_tax_id, message="CNPJ do prestador diverge do XML validado.")

    taker_tax_id = normalize_tax_id(str(_first_payload_value(payload, "taker_tax_id", "tomador_cnpj", "cnpj_tomador", "tomador") or ""))
    if document.taker_tax_id and taker_tax_id and taker_tax_id != document.taker_tax_id:
        _append_divergence(divergences, field="taker_tax_id", local=document.taker_tax_id, remote=taker_tax_id, message="CNPJ do tomador diverge do XML validado.")

    municipality_code = str(_first_payload_value(payload, "municipality_code", "codigo_municipio", "codigo_municipio_prestacao") or "").strip()
    if document.municipality_code and municipality_code and municipality_code != document.municipality_code:
        _append_divergence(divergences, field="municipality_code", local=document.municipality_code, remote=municipality_code, message="Município diverge do XML validado.")

    environment = str(_first_payload_value(payload, "ambiente", "environment") or "").strip()
    if document.environment and environment and environment != document.environment:
        _append_divergence(divergences, field="environment", local=document.environment, remote=environment, message="Ambiente diverge do XML validado.")

    remote_amount = _normalize_amount(_first_payload_value(payload, "service_amount", "valor_servicos", "valor_servico", "valor"))
    if document.service_amount is not None and remote_amount is not None and remote_amount != document.service_amount:
        _append_divergence(divergences, field="service_amount", local=document.service_amount, remote=remote_amount, message="Valor do serviço diverge do XML validado.")

    if national_standard_confirmed is False:
        _append_divergence(divergences, field="national_standard", local="required_for_manifestation", remote="false", message="Consulta não confirmou Padrão Nacional.")

    return divergences


def consult_nfse_received_document(*, document: NfseReceivedDocument, consulted_by: Any | None = None) -> NfseReceivedDocumentConsultation:
    loaded_document = NfseReceivedDocument.objects.select_related("company").get(pk=document.pk, workshop=document.workshop)
    _assert_consultation_eligible(loaded_document)
    identifier, identifier_source = _select_identifier(loaded_document)
    try:
        payload = consult_nfse_uuid(workshop=loaded_document.workshop, event_uuid=identifier)
    except NfseConsultaError as exc:
        raise NfseReceivedConsultationError(str(exc)) from exc

    with transaction.atomic():
        locked_document = NfseReceivedDocument.objects.select_for_update().select_related("company").get(pk=document.pk, workshop=document.workshop)
        _assert_consultation_eligible(locked_document)
        remote_uuid = str(_first_payload_value(payload, "uuid", "chave", "chave_acesso") or "").strip()
        remote_status = str(_first_payload_value(payload, "status", "situacao", "situacao_nfse") or "").strip()
        national_standard_confirmed = _payload_bool(payload, "padrao_nacional", "padrão_nacional", "national_standard", "national_standard_enabled")
        divergences = build_received_consultation_divergences(document=locked_document, payload=payload, national_standard_confirmed=national_standard_confirmed)

        return NfseReceivedDocumentConsultation.objects.create(
            workshop=locked_document.workshop,
            received_document=locked_document,
            identifier=identifier,
            identifier_source=identifier_source,
            request_metadata={
                "method": "GET",
                "endpoint": "/2/nfse/consulta/{identifier}",
                "identifier_source": identifier_source,
            },
            response_payload=payload,
            remote_status=remote_status,
            remote_uuid=remote_uuid,
            remote_updated_at=_parse_remote_updated_at(payload),
            national_standard_confirmed=national_standard_confirmed,
            divergences=divergences,
            validation_errors=[],
            consulted_by=consulted_by if getattr(consulted_by, "is_authenticated", False) else None,
        )
