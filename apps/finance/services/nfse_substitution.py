from __future__ import annotations

import hashlib
from typing import Any

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.finance.models.finance import FiscalEmissionAttempt, FiscalEmissionAttemptStatus, FiscalEmissionDocumentKind, FiscalEmissionOperationType, FiscalProductPreviewStatus, NfseItem, NfseItemStatus, NfseManualEmission, NfseSubstitution, NfseSubstitutionPreview, WebmaniaCompany
from apps.finance.services.fiscal_attempts import FiscalEmissionAttemptBlocked, begin_emission_attempt, build_payload_hash, mark_attempt_failed, mark_attempt_sent, mark_attempt_succeeded, mark_attempt_uncertain, sanitize_fiscal_payload
from apps.finance.services.nfse_capabilities import NfseCapabilityError, validate_nfse_substitution_capability
from apps.core.infrastructure.services.webmania.nfse_consulta import NfseConsultaError, consult_nfse_uuid
from apps.core.infrastructure.services.webmania.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


class NfseSubstitutionError(Exception):
    pass


def _build_substitution_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFSE_SUBSTITUTION_ENDPOINT", ""))
    if custom_endpoint:
        return custom_endpoint.rstrip("/")
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_BASE_URL", "https://api.webmania.com.br/2/")).rstrip("/")
    return f"{base_url}/nfse/substituir"


def _build_headers(*, workshop: Any) -> dict[str, str]:
    try:
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfseSubstitutionError(str(exc)) from exc


def _idempotency_key(*, substitution: NfseSubstitution) -> str:
    raw = f"{substitution.workshop_id}:{substitution.preview_id}:{FiscalEmissionOperationType.NFSE_SUBSTITUTION}:{substitution.pk}:1"
    return f"{FiscalEmissionOperationType.NFSE_SUBSTITUTION}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _attempt_for(substitution: NfseSubstitution) -> FiscalEmissionAttempt | None:
    return FiscalEmissionAttempt.objects.filter(workshop=substitution.workshop, document_kind=FiscalEmissionDocumentKind.NFSE, operation_type=FiscalEmissionOperationType.NFSE_SUBSTITUTION, request_model=NfseSubstitution.__name__, request_id=substitution.pk).order_by("-pk").first()


def _manual_emission_for_item(item: NfseItem) -> NfseManualEmission | None:
    try:
        return item.manual_emission
    except NfseManualEmission.DoesNotExist:
        return None


def _validate_manual_substitution_capability(*, emission: NfseManualEmission) -> None:
    capability = emission.preview.municipal_capability
    if capability.workshop_id != emission.workshop_id or capability.company_id != emission.company_id:
        raise NfseSubstitutionError("A capacidade municipal nao pertence a empresa/oficina da emissao manual.")
    if not capability.is_active or not capability.substitution_enabled:
        raise NfseSubstitutionError("A substituicao NFS-e esta desabilitada para o municipio configurado.")


def _validate_eligibility(*, preview: NfseSubstitutionPreview) -> None:
    if not preview.is_approved or preview.validation_status != FiscalProductPreviewStatus.APPROVED:
        raise NfseSubstitutionError("A substituicao exige preview aprovada.")
    if not WebmaniaCompany.objects.filter(workshop=preview.workshop, nfse_substitution_preview_enabled=True).exists():
        raise NfseSubstitutionError("A substituicao NFS-e esta desabilitada para esta oficina.")
    original = preview.original_nfse
    if original.status == NfseItemStatus.cancelado:
        raise NfseSubstitutionError("NFS-e cancelada nao pode ser substituida.")
    if str(original.status).lower() == "uncertain":
        raise NfseSubstitutionError("NFS-e incerta deve ser reconciliada antes da substituicao.")
    if original.status != NfseItemStatus.aprovado:
        raise NfseSubstitutionError("Substituicao permitida somente para NFS-e autorizada.")
    if not original.uuid or not original.verification_code or not original.xml_url:
        raise NfseSubstitutionError("A NFS-e original exige UUID, codigo de verificacao e XML preservado.")
    if original.cancellations.exclude(status=FiscalEmissionAttemptStatus.FAILED).exists():
        raise NfseSubstitutionError("NFS-e com cancelamento ativo, autorizado ou incerto nao pode ser substituida.")
    if preview.request_payload != {"ambiente": int(preview.environment), "codigo_verificacao": preview.original_verification_code, "motivo": preview.reason_code, "rps": preview.rps_payload}:
        raise NfseSubstitutionError("O payload aprovado da preview esta inconsistente.")
    if "uuid" in preview.request_payload:
        raise NfseSubstitutionError("O contrato validado nao permite payload hibrido com UUID.")
    manual_emission = _manual_emission_for_item(original)
    if original.request_id is None and manual_emission is None:
        raise NfseSubstitutionError("A NFS-e original nao esta vinculada a requisicao legada ou emissao manual valida.")
    if manual_emission is not None:
        if manual_emission.status == FiscalEmissionAttemptStatus.UNCERTAIN or manual_emission.is_uncertain:
            raise NfseSubstitutionError("A emissao manual NFS-e esta incerta e deve ser reconciliada antes da substituicao.")
        _validate_manual_substitution_capability(emission=manual_emission)
    else:
        try:
            validate_nfse_substitution_capability(nfse_request=original.request)
        except NfseCapabilityError as exc:
            raise NfseSubstitutionError(str(exc)) from exc


def is_nfse_substitution_eligible(preview: NfseSubstitutionPreview | None) -> bool:
    if preview is None:
        return False
    try:
        _validate_eligibility(preview=preview)
    except NfseSubstitutionError:
        return False
    return not NfseSubstitution.objects.filter(preview=preview).exclude(status=FiscalEmissionAttemptStatus.FAILED).exists()


def _create_intention(*, preview: NfseSubstitutionPreview, requested_by: Any | None) -> tuple[NfseSubstitution, FiscalEmissionAttempt, dict[str, Any]]:
    with transaction.atomic():
        locked_preview = (
            NfseSubstitutionPreview.objects.select_for_update(of=("self",))
            .select_related("original_nfse", "original_nfse__request")
            .get(pk=preview.pk, workshop=preview.workshop)
        )
        locked_original = NfseItem.objects.select_for_update().get(pk=locked_preview.original_nfse_id, workshop=preview.workshop)
        locked_preview.original_nfse = locked_original
        _validate_eligibility(preview=locked_preview)
        existing = NfseSubstitution.objects.filter(preview=locked_preview).first() or NfseSubstitution.objects.filter(original_nfse=locked_original).exclude(status=FiscalEmissionAttemptStatus.FAILED).first()
        if existing is not None:
            if existing.status == FiscalEmissionAttemptStatus.UNCERTAIN:
                raise NfseSubstitutionError("Ja existe substituicao NFS-e incerta; reconcilie antes de qualquer nova acao.")
            raise NfseSubstitutionError("Ja existe substituicao registrada para esta preview ou NFS-e original.")
        payload = sanitize_fiscal_payload(locked_preview.request_payload)
        try:
            substitution = NfseSubstitution.objects.create(
                workshop=locked_preview.workshop,
                preview=locked_preview,
                original_nfse=locked_original,
                uuid_original=locked_preview.original_uuid,
                original_verification_code=locked_preview.original_verification_code,
                reason_code=locked_preview.reason_code,
                request_payload=payload,
                original_xml_snapshot=locked_preview.original_xml_snapshot,
                requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            )
        except IntegrityError as exc:
            raise NfseSubstitutionError("Ja existe substituicao ativa para esta preview ou NFS-e original.") from exc
        try:
            attempt = begin_emission_attempt(
                workshop=locked_preview.workshop,
                document_kind=FiscalEmissionDocumentKind.NFSE,
                operation_type=FiscalEmissionOperationType.NFSE_SUBSTITUTION,
                request_model=NfseSubstitution.__name__,
                request_id=substitution.pk,
                idempotency_key=_idempotency_key(substitution=substitution),
                request_payload=payload,
                payload_hash=build_payload_hash(payload),
            )
        except FiscalEmissionAttemptBlocked as exc:
            raise NfseSubstitutionError(str(exc)) from exc
        return substitution, attempt, payload


def _status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or "").strip().lower()


def _is_success(payload: dict[str, Any]) -> bool:
    return _status(payload) in {"aprovado", "aprovada", "authorized"}


def _is_processing(payload: dict[str, Any]) -> bool:
    return _status(payload) in {"processando", "processing", "contingencia", "agendado"}


def _is_failure(payload: dict[str, Any]) -> bool:
    return _status(payload) in {"reprovado", "rejeitado", "erro", "error", "failed", "falha"} or bool(payload.get("error"))


def _validate_original_reference(*, substitution: NfseSubstitution, payload: dict[str, Any], required: bool) -> None:
    referenced = payload.get("nfse_substituida")
    if not isinstance(referenced, dict):
        if required:
            raise NfseSubstitutionError("A resposta aprovada nao confirmou a NFS-e original substituida.")
        return
    referenced_uuid = str(referenced.get("uuid") or "").strip().lower()
    if referenced_uuid != str(substitution.uuid_original).strip().lower():
        raise NfseSubstitutionError("A resposta de substituicao referencia outra NFS-e original.")


@transaction.atomic
def apply_nfse_substitution_payload(*, substitution: NfseSubstitution, payload: dict[str, Any], update_source: str, require_original_reference: bool = False) -> NfseSubstitution:
    locked = NfseSubstitution.objects.select_for_update().select_related("original_nfse", "preview").get(pk=substitution.pk, workshop=substitution.workshop)
    sanitized = sanitize_fiscal_payload(payload)
    replacement_uuid = str(sanitized.get("uuid") or "").strip()
    if locked.uuid_replacement and replacement_uuid and str(locked.uuid_replacement).lower() != replacement_uuid.lower():
        raise NfseSubstitutionError("O retorno pertence a outra NFS-e substituta.")
    locked.response_payload = sanitized
    if replacement_uuid:
        locked.uuid_replacement = replacement_uuid
    locked.replacement_xml_url = str(sanitized.get("xml") or locked.replacement_xml_url or "").strip()
    locked.replacement_pdf_url = str(sanitized.get("pdf") or sanitized.get("pdf_nfse") or locked.replacement_pdf_url or "").strip()
    if _is_success(sanitized):
        if not replacement_uuid:
            raise NfseSubstitutionError("A resposta aprovada nao possui UUID da NFS-e substituta.")
        _validate_original_reference(substitution=locked, payload=sanitized, required=require_original_reference)
        if NfseItem.objects.filter(uuid=replacement_uuid).exclude(pk=locked.replacement_nfse_id).exists():
            raise NfseSubstitutionError("UUID da NFS-e substituta esta ambiguo no Hunter.")
        original = locked.original_nfse
        replacement, _ = NfseItem.objects.get_or_create(
            workorder=original.workorder,
            uuid=replacement_uuid,
            defaults={"workshop": locked.workshop, "request": original.request, "status": NfseItemStatus.aprovado},
        )
        if replacement.workshop_id != locked.workshop_id or replacement.request_id != original.request_id:
            raise NfseSubstitutionError("A NFS-e substituta pertence a outro escopo operacional.")
        replacement.status = NfseItemStatus.aprovado
        replacement.number = str(sanitized.get("numero") or replacement.number or "")
        replacement.verification_code = str(sanitized.get("codigo_verificacao") or replacement.verification_code or "")
        replacement.rps_series = str(sanitized.get("serie_rps") or replacement.rps_series or "")
        replacement.rps_number = str(sanitized.get("numero_rps") or replacement.rps_number or "")
        replacement.xml_url = locked.replacement_xml_url
        replacement.pdf_nfse_url = locked.replacement_pdf_url
        replacement.raw_payload = sanitized
        replacement.last_update_source = update_source
        replacement.save(update_fields=["status", "number", "verification_code", "rps_series", "rps_number", "xml_url", "pdf_nfse_url", "raw_payload", "last_update_source"])
        original.status = NfseItemStatus.substituido
        original.reason = f"Substituida pela NFS-e {replacement_uuid}"
        original.last_update_source = update_source
        original.save(update_fields=["status", "reason", "last_update_source"])
        locked.replacement_nfse = replacement
        locked.status = FiscalEmissionAttemptStatus.SUCCEEDED
        locked.is_uncertain = False
        locked.completed_at = timezone.now()
    elif _is_failure(sanitized):
        locked.status = FiscalEmissionAttemptStatus.FAILED
        locked.is_uncertain = False
        locked.completed_at = timezone.now()
    elif _is_processing(sanitized):
        locked.status = FiscalEmissionAttemptStatus.SENT
        locked.is_uncertain = False
    else:
        locked.status = FiscalEmissionAttemptStatus.UNCERTAIN
        locked.is_uncertain = True
    locked.save(update_fields=["response_payload", "uuid_replacement", "replacement_xml_url", "replacement_pdf_url", "replacement_nfse", "status", "is_uncertain", "completed_at", "atualizado_em"])
    return locked


def _mark_uncertain(*, substitution: NfseSubstitution, message: str) -> None:
    substitution.status = FiscalEmissionAttemptStatus.UNCERTAIN
    substitution.is_uncertain = True
    substitution.response_payload = sanitize_fiscal_payload({"error": message})
    substitution.save(update_fields=["status", "is_uncertain", "response_payload", "atualizado_em"])


def substitute_nfse_from_preview(*, preview: NfseSubstitutionPreview, requested_by: Any | None = None) -> NfseSubstitution:
    substitution, attempt, payload = _create_intention(preview=preview, requested_by=requested_by)
    mark_attempt_sent(attempt=attempt)
    substitution.status = FiscalEmissionAttemptStatus.SENT
    substitution.sent_at = timezone.now()
    substitution.save(update_fields=["status", "sent_at", "atualizado_em"])
    try:
        response = requests.post(_build_substitution_url(), json=payload, headers=_build_headers(workshop=preview.workshop), timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao substituir NFS-e; estado remoto incerto. Consulte antes de qualquer nova tentativa."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(substitution=substitution, message=message)
        raise NfseSubstitutionError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao substituir Nota Fiscal de Servico", scope="nfse")
        mark_attempt_failed(attempt=attempt, error_message=message)
        substitution.status = FiscalEmissionAttemptStatus.FAILED
        substitution.response_payload = sanitize_fiscal_payload({"error": message})
        substitution.completed_at = timezone.now()
        substitution.save(update_fields=["status", "response_payload", "completed_at", "atualizado_em"])
        raise NfseSubstitutionError(message) from exc
    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida ao substituir NFS-e; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(substitution=substitution, message=message)
        raise NfseSubstitutionError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta invalida ao substituir NFS-e; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(substitution=substitution, message=message)
        raise NfseSubstitutionError(message)
    try:
        substitution = apply_nfse_substitution_payload(substitution=substitution, payload=response_payload, update_source="substitution", require_original_reference=_is_success(response_payload))
    except NfseSubstitutionError as exc:
        mark_attempt_uncertain(attempt=attempt, error_message=str(exc))
        _mark_uncertain(substitution=substitution, message=str(exc))
        raise
    if substitution.status == FiscalEmissionAttemptStatus.FAILED:
        message = extract_webmania_error_message(response_payload, scope="nfse") or "Substituicao NFS-e rejeitada."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfseSubstitutionError(message)
    if substitution.status == FiscalEmissionAttemptStatus.SUCCEEDED:
        mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    else:
        attempt.response_payload = sanitize_fiscal_payload(response_payload)
        attempt.remote_uuid = str(response_payload.get("uuid") or "")
        attempt.save(update_fields=["response_payload", "remote_uuid", "atualizado_em"])
    return substitution


def resolve_nfse_substitution_for_webhook(*, payload: dict[str, Any]) -> NfseSubstitution | None:
    event_uuid = str(payload.get("uuid") or "").strip()
    queryset = NfseSubstitution.objects.exclude(status=FiscalEmissionAttemptStatus.FAILED)
    if event_uuid:
        direct = list(queryset.filter(uuid_replacement=event_uuid).order_by("pk")[:2])
        if len(direct) == 1:
            return direct[0]
        if len(direct) > 1:
            return None
    referenced = payload.get("nfse_substituida")
    original_uuid = str(referenced.get("uuid") or "").strip() if isinstance(referenced, dict) else ""
    if not original_uuid:
        return None
    matches = list(queryset.filter(uuid_original=original_uuid, status__in=[FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.UNCERTAIN]).order_by("pk")[:2])
    return matches[0] if len(matches) == 1 else None


def is_ambiguous_nfse_substitution_webhook(*, payload: dict[str, Any]) -> bool:
    event_uuid = str(payload.get("uuid") or "").strip()
    queryset = NfseSubstitution.objects.exclude(status=FiscalEmissionAttemptStatus.FAILED)
    if event_uuid and queryset.filter(uuid_replacement=event_uuid).count() > 1:
        return True
    referenced = payload.get("nfse_substituida")
    original_uuid = str(referenced.get("uuid") or "").strip() if isinstance(referenced, dict) else ""
    return bool(original_uuid and queryset.filter(uuid_original=original_uuid, status__in=[FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.UNCERTAIN]).count() > 1)


def confirm_nfse_substitution_from_payload(*, substitution: NfseSubstitution, payload: dict[str, Any], update_source: str) -> NfseSubstitution:
    applied = apply_nfse_substitution_payload(substitution=substitution, payload=payload, update_source=update_source)
    attempt = _attempt_for(applied)
    if attempt is not None and applied.status == FiscalEmissionAttemptStatus.SUCCEEDED and attempt.status != FiscalEmissionAttemptStatus.SUCCEEDED:
        mark_attempt_succeeded(attempt=attempt, response_payload=payload)
    return applied


def reconcile_nfse_substitution(*, substitution: NfseSubstitution) -> NfseSubstitution:
    if substitution.status == FiscalEmissionAttemptStatus.SUCCEEDED:
        return substitution
    if not substitution.uuid_replacement:
        raise NfseSubstitutionError("Substituicao incerta sem UUID remoto exige decisao administrativa; nenhum POST sera repetido.")
    try:
        payload = consult_nfse_uuid(workshop=substitution.workshop, event_uuid=str(substitution.uuid_replacement))
    except NfseConsultaError as exc:
        raise NfseSubstitutionError(str(exc)) from exc
    return confirm_nfse_substitution_from_payload(substitution=substitution, payload=payload, update_source="query")
