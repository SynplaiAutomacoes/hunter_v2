from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.finance.models.finance import FiscalEmissionAttemptStatus, FiscalProductPreviewStatus, NfseItem, NfseItemStatus, NfseManualEmission, NfseMunicipalCapability, NfseSubstitution, NfseSubstitutionPreview, WebmaniaCompany
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload


FORBIDDEN_RPS_FIELDS = {"uuid", "substituicao", "manifestacao", "cancelamento", "url_notificacao"}


def is_nfse_substitution_preview_enabled(*, workshop: Any) -> bool:
    return WebmaniaCompany.objects.filter(workshop=workshop, nfse_substitution_preview_enabled=True).exists()


def _validate_taker(taker: dict[str, Any]) -> None:
    document = str(taker.get("cpf") or taker.get("cnpj") or "").strip()
    name = str(taker.get("nome_completo") or taker.get("razao_social") or "").strip()
    if not document or not name:
        raise ValidationError("O novo RPS exige tomador com documento e nome/razao social.")


def _validate_service(service: dict[str, Any]) -> None:
    if not str(service.get("discriminacao") or "").strip():
        raise ValidationError("O novo RPS exige discriminacao do serviço.")
    try:
        value = Decimal(str(service.get("valor_servicos") or "0"))
    except InvalidOperation as exc:
        raise ValidationError("Valor de serviços inválido no novo RPS.") from exc
    if value <= 0:
        raise ValidationError("O valor de serviços do novo RPS deve ser positivo.")
    if not str(service.get("classe_imposto") or "").strip() and not isinstance(service.get("impostos"), dict):
        raise ValidationError("O novo RPS exige classe de imposto ou tributação/retenções explicitas.")


def _manual_emission_for_item(item: NfseItem) -> NfseManualEmission | None:
    try:
        return item.manual_emission
    except NfseManualEmission.DoesNotExist:
        return None


def _validate_capability(*, workshop: Any) -> None:
    capabilities = NfseMunicipalCapability.objects.filter(workshop=workshop, is_active=True)
    if capabilities.exists() and not capabilities.filter(substitution_enabled=True).exists():
        raise ValidationError("A capacidade municipal ativa não permite preparar substituição NFS-e.")


def _validate_manual_capability(*, emission: NfseManualEmission) -> None:
    capability = emission.preview.municipal_capability
    if capability.workshop_id != emission.workshop_id or capability.company_id != emission.company_id:
        raise ValidationError("A capacidade municipal não pertence a empresa/oficina da emissão manual.")
    if not capability.is_active or not capability.substitution_enabled:
        raise ValidationError("A capacidade municipal ativa não permite preparar substituição NFS-e.")


def validate_nfse_substitution_original(original_nfse: NfseItem, *, workshop: Any) -> NfseManualEmission | None:
    if original_nfse.workshop_id != workshop.pk:
        raise ValidationError("A NFS-e original pertence a outra oficina.")
    if original_nfse.status != NfseItemStatus.aprovado:
        raise ValidationError("A preview exige NFS-e original autorizada.")
    if not original_nfse.uuid:
        raise ValidationError("A NFS-e original não possui UUID remoto.")
    verification_code = str(original_nfse.verification_code or "").strip()
    if not verification_code:
        raise ValidationError("A NFS-e original não possui código de verificacao.")
    xml_url = str(original_nfse.xml_url or "").strip()
    if not xml_url:
        raise ValidationError("A NFS-e original não possui XML disponível para snapshot.")
    if original_nfse.cancellations.exclude(status=FiscalEmissionAttemptStatus.FAILED).exists():
        raise ValidationError("NFS-e com cancelamento ativo, autorizado ou incerto não pode ser substituida.")
    if NfseSubstitution.objects.filter(original_nfse=original_nfse).exclude(status=FiscalEmissionAttemptStatus.FAILED).exists():
        raise ValidationError("Já existe substituição ativa, autorizada ou incerta para esta NFS-e original.")
    manual_emission = _manual_emission_for_item(original_nfse)
    if manual_emission is not None:
        if manual_emission.status == FiscalEmissionAttemptStatus.UNCERTAIN or manual_emission.is_uncertain:
            raise ValidationError("A emissão manual NFS-e esta incerta e deve ser reconciliada antes da substituição.")
        _validate_manual_capability(emission=manual_emission)
        return manual_emission
    _validate_capability(workshop=workshop)
    return None


def is_nfse_item_eligible_for_substitution_preview(item: NfseItem | None, *, workshop: Any | None = None) -> bool:
    if item is None:
        return False
    try:
        validate_nfse_substitution_original(original_nfse=item, workshop=workshop or item.workshop)
    except ValidationError:
        return False
    return True


@transaction.atomic
def create_nfse_substitution_preview(
    *,
    workshop: Any,
    original_nfse: NfseItem,
    environment: str,
    reason_code: int,
    rps_number: int,
    rps_series: str,
    service_payload: dict[str, Any],
    taker_payload: dict[str, Any],
    created_by: Any,
) -> NfseSubstitutionPreview:
    if not is_nfse_substitution_preview_enabled(workshop=workshop):
        raise ValidationError("A prévia de substituição NFS-e esta desabilitada para esta oficina.")
    locked = NfseItem.objects.select_for_update(of=("self",)).get(pk=original_nfse.pk, workshop=workshop)
    validate_nfse_substitution_original(original_nfse=locked, workshop=workshop)
    verification_code = str(locked.verification_code or "").strip()
    xml_url = str(locked.xml_url or "").strip()
    if environment not in {"1", "2"}:
        raise ValidationError("Ambiente inválido para a prévia de substituição.")
    if reason_code not in {1, 2, 4}:
        raise ValidationError("Motivo inválido para a prévia de substituição.")
    if rps_number <= 0 or not str(rps_series or "").strip():
        raise ValidationError("Número e série do novo RPS são obrigatórios.")
    if not isinstance(service_payload, dict) or not service_payload:
        raise ValidationError("Serviço do novo RPS e obrigatório.")
    if not isinstance(taker_payload, dict) or not taker_payload:
        raise ValidationError("Tomador do novo RPS e obrigatório.")
    _validate_service(service_payload)
    _validate_taker(taker_payload)
    rps_payload = sanitize_fiscal_payload({"numero": rps_number, "serie": str(rps_series).strip(), "servico": service_payload, "tomador": taker_payload})
    forbidden = sorted(field for field in FORBIDDEN_RPS_FIELDS if field in rps_payload)
    if forbidden:
        raise ValidationError(f"Novo RPS contem campos proibidos: {', '.join(forbidden)}.")
    request_payload = sanitize_fiscal_payload({"ambiente": int(environment), "codigo_verificacao": verification_code, "motivo": reason_code, "rps": rps_payload})
    xml_snapshot = sanitize_fiscal_payload(
        {
            "url": xml_url,
            "uuid": str(locked.uuid),
            "codigo_verificacao": verification_code,
            "numero": locked.number,
            "capturado_em": timezone.now().isoformat(),
            "payload_original": locked.raw_payload,
        }
    )
    preview = NfseSubstitutionPreview(
        workshop=workshop,
        original_nfse=locked,
        original_uuid=locked.uuid,
        original_verification_code=verification_code,
        original_xml_snapshot=xml_snapshot,
        environment=environment,
        reason_code=reason_code,
        rps_payload=rps_payload,
        request_payload=request_payload,
        validation_status=FiscalProductPreviewStatus.VALIDATED,
        validation_errors=[],
        forbidden_fields_detected=forbidden,
        created_by=created_by,
    )
    preview.save()
    return preview


@transaction.atomic
def approve_nfse_substitution_preview(*, preview: NfseSubstitutionPreview, approved_by: Any) -> NfseSubstitutionPreview:
    locked = NfseSubstitutionPreview.objects.select_for_update(of=("self",)).select_related("original_nfse").get(pk=preview.pk, workshop=preview.workshop)
    if not is_nfse_substitution_preview_enabled(workshop=locked.workshop):
        raise ValidationError("A prévia de substituição NFS-e esta desabilitada para esta oficina.")
    if locked.validation_status != FiscalProductPreviewStatus.VALIDATED:
        raise ValidationError("Somente preview validada pode ser aprovada.")
    validate_nfse_substitution_original(original_nfse=locked.original_nfse, workshop=locked.workshop)
    if NfseSubstitutionPreview.objects.filter(original_nfse=locked.original_nfse, is_approved=True).exclude(pk=locked.pk).exists():
        raise ValidationError("Já existe prévia aprovada para esta NFS-e original.")
    locked.validation_status = FiscalProductPreviewStatus.APPROVED
    locked.is_approved = True
    locked.approved_by = approved_by
    locked.approved_at = timezone.now()
    locked.save(update_fields=["validation_status", "is_approved", "approved_by", "approved_at", "atualizado_em"])
    return locked
