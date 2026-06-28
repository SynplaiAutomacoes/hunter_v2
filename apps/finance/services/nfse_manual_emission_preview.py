from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.finance.models.finance import FiscalProductPreviewStatus, NfseItem, NfseManualEmissionPreview, NfseMunicipalCapability, NfseRequest, WebmaniaCompany
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload


FORBIDDEN_RPS_FIELDS = {"uuid", "codigo_verificacao", "cancelamento", "substituicao", "manifestacao", "url_notificacao", "data_agendamento", "previa_danfe"}


def is_nfse_manual_emission_preview_enabled(*, workshop: Any) -> bool:
    return WebmaniaCompany.objects.filter(workshop=workshop, nfse_manual_emission_preview_enabled=True).exists()


def _normalize_decimal(value: Any, *, field_name: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValidationError(f"{field_name} invalido.") from exc
    return amount


def _validate_taker(taker: dict[str, Any]) -> None:
    document = str(taker.get("cpf") or taker.get("cnpj") or "").strip()
    name = str(taker.get("nome_completo") or taker.get("razao_social") or "").strip()
    if not document or not name:
        raise ValidationError("Tomador exige documento e nome/razao social.")


def _validate_service(service: dict[str, Any], *, capability: NfseMunicipalCapability) -> None:
    if not str(service.get("discriminacao") or "").strip():
        raise ValidationError("Servico exige discriminacao.")
    value = _normalize_decimal(service.get("valor_servicos"), field_name="Valor de servicos")
    if value <= 0:
        raise ValidationError("Valor de servicos deve ser positivo.")
    if capability.requires_service_code and not str(service.get("codigo_servico") or service.get("classe_imposto") or "").strip():
        raise ValidationError("A capacidade municipal exige codigo de servico ou classe fiscal.")
    if capability.requires_cnae and not str(service.get("cnae") or "").strip():
        raise ValidationError("A capacidade municipal exige CNAE.")
    if not str(service.get("classe_imposto") or "").strip() and not isinstance(service.get("impostos"), dict):
        raise ValidationError("Servico exige classe de imposto ou tributacao explicita.")


def _validate_values(values: dict[str, Any], *, service: dict[str, Any]) -> None:
    total = _normalize_decimal(values.get("valor_servicos", service.get("valor_servicos")), field_name="Valor de servicos")
    if total <= 0:
        raise ValidationError("Valor de servicos deve ser positivo.")
    service_total = _normalize_decimal(service.get("valor_servicos"), field_name="Valor de servicos")
    if total != service_total:
        raise ValidationError("Snapshot de valores diverge do valor de servicos.")


def _validate_taxation(taxation: dict[str, Any], *, capability: NfseMunicipalCapability) -> None:
    if not taxation:
        raise ValidationError("Tributacao e obrigatoria.")
    if capability.requires_iss_rate:
        iss_rate = taxation.get("aliquota_iss") or taxation.get("aliquota")
        if iss_rate in (None, ""):
            raise ValidationError("A capacidade municipal exige aliquota ISS.")
        if _normalize_decimal(iss_rate, field_name="Aliquota ISS") < 0:
            raise ValidationError("Aliquota ISS invalida.")


def _validate_retention(retention: dict[str, Any]) -> None:
    for key, value in retention.items():
        if value in (None, ""):
            continue
        if _normalize_decimal(value, field_name=f"Retencao {key}") < 0:
            raise ValidationError("Retencoes nao podem ser negativas.")


def _validate_ibs_cbs(ibs_cbs: dict[str, Any], *, taxation: dict[str, Any]) -> None:
    if taxation.get("ibs_cbs_required") and not ibs_cbs:
        raise ValidationError("IBS/CBS e obrigatorio para esta preview.")


def _existing_rps_queryset(*, workshop: Any, company: WebmaniaCompany, environment: str, rps_number: int, rps_series: str):
    reserved_requests = NfseRequest.objects.filter(workshop=workshop, reserved_rps_number=rps_number, reserved_rps_series=rps_series)
    emitted_items = NfseItem.objects.filter(workshop=workshop, rps_number=str(rps_number), rps_series=rps_series)
    approved_previews = NfseManualEmissionPreview.objects.filter(company=company, environment=environment, rps_number=rps_number, rps_series=rps_series, is_approved=True)
    return reserved_requests, emitted_items, approved_previews


def _assert_rps_available(*, workshop: Any, company: WebmaniaCompany, environment: str, rps_number: int, rps_series: str) -> None:
    reserved_requests, emitted_items, approved_previews = _existing_rps_queryset(workshop=workshop, company=company, environment=environment, rps_number=rps_number, rps_series=rps_series)
    if reserved_requests.exists() or emitted_items.exists() or approved_previews.exists():
        raise ValidationError("Ja existe RPS local conhecido para esta empresa/oficina/ambiente.")


def _assert_company_configured(company: WebmaniaCompany) -> None:
    if not company.pk:
        raise ValidationError("Empresa emissora obrigatoria.")
    if not str(company.webmania_company_id or company.bearer_access_token or company.consumer_key or "").strip():
        raise ValidationError("Empresa emissora Webmania nao esta configurada.")


def _assert_capability_enabled(capability: NfseMunicipalCapability) -> None:
    if not capability.is_active or not capability.emission_enabled or not capability.manual_emission_enabled:
        raise ValidationError("A capacidade municipal nao permite preview de emissao manual NFS-e.")


@transaction.atomic
def create_nfse_manual_emission_preview(
    *,
    workshop: Any,
    company: WebmaniaCompany,
    municipal_capability: NfseMunicipalCapability,
    environment: str,
    rps_number: int,
    rps_series: str,
    service_payload: dict[str, Any],
    taker_payload: dict[str, Any],
    values_payload: dict[str, Any],
    taxation_payload: dict[str, Any],
    retention_payload: dict[str, Any] | None = None,
    ibs_cbs_payload: dict[str, Any] | None = None,
    created_by: Any | None = None,
) -> NfseManualEmissionPreview:
    if not is_nfse_manual_emission_preview_enabled(workshop=workshop):
        raise ValidationError("A preview de emissao manual NFS-e esta desabilitada para esta oficina.")
    try:
        locked_company = WebmaniaCompany.objects.select_for_update().get(pk=company.pk, workshop=workshop)
        locked_capability = NfseMunicipalCapability.objects.select_for_update().get(pk=municipal_capability.pk, workshop=workshop, company=locked_company)
    except (WebmaniaCompany.DoesNotExist, NfseMunicipalCapability.DoesNotExist) as exc:
        raise ValidationError("Empresa emissora ou capacidade municipal nao pertence a oficina ativa.") from exc
    _assert_company_configured(locked_company)
    _assert_capability_enabled(locked_capability)
    if environment not in {"1", "2"}:
        raise ValidationError("Ambiente invalido para preview NFS-e.")
    if rps_number <= 0 or not str(rps_series or "").strip():
        raise ValidationError("Numero e serie do RPS sao obrigatorios.")
    if not isinstance(service_payload, dict) or not service_payload:
        raise ValidationError("Servico e obrigatorio.")
    if not isinstance(taker_payload, dict) or not taker_payload:
        raise ValidationError("Tomador e obrigatorio.")
    if not isinstance(values_payload, dict) or not values_payload:
        raise ValidationError("Valores sao obrigatorios.")
    if not isinstance(taxation_payload, dict) or not taxation_payload:
        raise ValidationError("Tributacao e obrigatoria.")
    retention_payload = retention_payload or {}
    ibs_cbs_payload = ibs_cbs_payload or {}
    _validate_taker(taker_payload)
    _validate_service(service_payload, capability=locked_capability)
    _validate_values(values_payload, service=service_payload)
    _validate_taxation(taxation_payload, capability=locked_capability)
    _validate_retention(retention_payload)
    _validate_ibs_cbs(ibs_cbs_payload, taxation=taxation_payload)
    _assert_rps_available(workshop=workshop, company=locked_company, environment=environment, rps_number=rps_number, rps_series=str(rps_series).strip())
    rps_payload = sanitize_fiscal_payload({"numero": rps_number, "serie": str(rps_series).strip(), "servico": service_payload, "tomador": taker_payload})
    forbidden = sorted(field for field in FORBIDDEN_RPS_FIELDS if field in rps_payload or field in service_payload or field in taker_payload)
    if forbidden:
        raise ValidationError(f"RPS contem campos proibidos: {', '.join(forbidden)}.")
    request_payload = sanitize_fiscal_payload({"ambiente": int(environment), "rps": [rps_payload]})
    preview = NfseManualEmissionPreview(
        workshop=workshop,
        company=locked_company,
        municipal_capability=locked_capability,
        environment=environment,
        rps_number=rps_number,
        rps_series=str(rps_series).strip(),
        rps_payload=rps_payload,
        request_payload=request_payload,
        taker_snapshot=sanitize_fiscal_payload(taker_payload),
        service_snapshot=sanitize_fiscal_payload(service_payload),
        values_snapshot=sanitize_fiscal_payload(values_payload),
        taxation_snapshot=sanitize_fiscal_payload(taxation_payload),
        retention_snapshot=sanitize_fiscal_payload(retention_payload),
        ibs_cbs_snapshot=sanitize_fiscal_payload(ibs_cbs_payload),
        validation_status=FiscalProductPreviewStatus.VALIDATED,
        validation_errors=[],
        forbidden_fields_detected=forbidden,
        created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
    )
    preview.save()
    return preview


@transaction.atomic
def approve_nfse_manual_emission_preview(*, preview: NfseManualEmissionPreview, approved_by: Any) -> NfseManualEmissionPreview:
    locked = NfseManualEmissionPreview.objects.select_for_update().select_related("company", "municipal_capability").get(pk=preview.pk, workshop=preview.workshop)
    if not is_nfse_manual_emission_preview_enabled(workshop=locked.workshop):
        raise ValidationError("A preview de emissao manual NFS-e esta desabilitada para esta oficina.")
    _assert_capability_enabled(locked.municipal_capability)
    if locked.validation_status != FiscalProductPreviewStatus.VALIDATED:
        raise ValidationError("Somente preview validada pode ser aprovada.")
    _assert_rps_available(workshop=locked.workshop, company=locked.company, environment=locked.environment, rps_number=locked.rps_number, rps_series=locked.rps_series)
    locked.validation_status = FiscalProductPreviewStatus.APPROVED
    locked.is_approved = True
    locked.approved_by = approved_by if getattr(approved_by, "is_authenticated", False) else None
    locked.approved_at = timezone.now()
    locked.save(update_fields=["validation_status", "is_approved", "approved_by", "approved_at", "atualizado_em"])
    return locked
