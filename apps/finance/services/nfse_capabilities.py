from __future__ import annotations

from dataclasses import dataclass

from apps.finance.models.finance import NfseMunicipalCapability, NfseReceivedDocument, NfseRequest, TaxClassNfse, WebmaniaCompany


class NfseCapabilityError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class NfseCapabilityResolution:
    capability: NfseMunicipalCapability | None
    legacy_compatibility_used: bool


def _resolve_company(*, nfse_request: NfseRequest) -> WebmaniaCompany:
    company = WebmaniaCompany.objects.filter(workshop=nfse_request.workshop).first()
    if company is None:
        raise NfseCapabilityError("Configure a empresa emissora da oficina antes de emitir Nota Fiscal de Serviço.")
    return company


def resolve_nfse_capability(*, nfse_request: NfseRequest) -> NfseCapabilityResolution:
    company = _resolve_company(nfse_request=nfse_request)
    capabilities = NfseMunicipalCapability.objects.filter(
        workshop=nfse_request.workshop,
        company=company,
        is_active=True,
    )

    city_name = str(company.cidade or "").strip()
    state = str(company.uf or "").strip().upper()
    if city_name:
        capabilities = capabilities.filter(city_name__iexact=city_name)
    if state:
        capabilities = capabilities.filter(state__iexact=state)

    matches = list(capabilities.order_by("pk")[:2])
    if len(matches) > 1:
        raise NfseCapabilityError("Existe mais de uma capacidade NFS-e aplicável a empresa emissora. Revise a configuração municipal.")
    if len(matches) == 1:
        return NfseCapabilityResolution(capability=matches[0], legacy_compatibility_used=False)

    if company.nfse_legacy_compatibility_enabled:
        return NfseCapabilityResolution(capability=None, legacy_compatibility_used=True)

    raise NfseCapabilityError("Cadastre a capacidade municipal NFS-e antes de emitir para esta oficina.")


def validate_nfse_emission_capability(*, nfse_request: NfseRequest) -> NfseCapabilityResolution:
    resolution = resolve_nfse_capability(nfse_request=nfse_request)
    capability = resolution.capability
    if capability is None:
        return resolution

    if not capability.emission_enabled:
        raise NfseCapabilityError("A emissão NFS-e esta desabilitada para o município configurado.")

    company = capability.company
    tax_class = TaxClassNfse.objects.filter(workshop=nfse_request.workshop, reference=nfse_request.tax_class).first()
    if capability.requires_municipal_registration and not str(company.im or "").strip():
        raise NfseCapabilityError("A inscricao municipal e obrigatoria para emitir NFS-e neste município.")
    if capability.requires_service_code and (tax_class is None or not str(tax_class.codigo_servico or "").strip()):
        raise NfseCapabilityError("O código de serviço e obrigatório para emitir NFS-e neste município.")
    if capability.requires_cnae and not str(company.cnae or company.cnae_issqn or "").strip():
        raise NfseCapabilityError("O CNAE e obrigatório para emitir NFS-e neste município.")
    if capability.requires_iss_rate and (tax_class is None or tax_class.iss is None):
        raise NfseCapabilityError("A aliquota ISS e obrigatoria para emitir NFS-e neste município.")

    return resolution


def validate_nfse_query_capability(*, nfse_request: NfseRequest) -> NfseCapabilityResolution:
    if not WebmaniaCompany.objects.filter(workshop=nfse_request.workshop).exists():
        return NfseCapabilityResolution(capability=None, legacy_compatibility_used=True)
    resolution = resolve_nfse_capability(nfse_request=nfse_request)
    if resolution.capability is not None and not resolution.capability.query_enabled:
        raise NfseCapabilityError("A consulta NFS-e esta desabilitada para o município configurado.")
    return resolution


def validate_nfse_cancellation_capability(*, nfse_request: NfseRequest) -> NfseCapabilityResolution:
    if not WebmaniaCompany.objects.filter(workshop=nfse_request.workshop).exists():
        return NfseCapabilityResolution(capability=None, legacy_compatibility_used=True)
    resolution = resolve_nfse_capability(nfse_request=nfse_request)
    if resolution.capability is not None and not resolution.capability.cancellation_enabled:
        raise NfseCapabilityError("O cancelamento NFS-e esta desabilitado para o município configurado.")
    return resolution


def validate_nfse_substitution_capability(*, nfse_request: NfseRequest) -> NfseCapabilityResolution:
    resolution = resolve_nfse_capability(nfse_request=nfse_request)
    if resolution.capability is None or not resolution.capability.substitution_enabled:
        raise NfseCapabilityError("A substituição NFS-e esta desabilitada para o município configurado.")
    return resolution


def validate_nfse_manifestation_capability(*, nfse_request: NfseRequest) -> NfseCapabilityResolution:
    resolution = resolve_nfse_capability(nfse_request=nfse_request)
    if resolution.capability is None:
        raise NfseCapabilityError("A manifestação NFS-e exige capacidade municipal cadastrada.")
    if not resolution.capability.national_standard_enabled:
        raise NfseCapabilityError("A manifestação NFS-e e restrita ao Padrão Nacional.")
    if not resolution.capability.manifestation_enabled:
        raise NfseCapabilityError("A manifestação NFS-e esta desabilitada para o município configurado.")
    return resolution


def validate_nfse_received_manifestation_capability(*, document: NfseReceivedDocument) -> NfseCapabilityResolution:
    capabilities = NfseMunicipalCapability.objects.filter(workshop=document.workshop, company=document.company, is_active=True)
    if document.municipality_code:
        capabilities = capabilities.filter(city_code=document.municipality_code)
    matches = list(capabilities.order_by("pk")[:2])
    if len(matches) != 1:
        raise NfseCapabilityError("A manifestação da NFS-e recebida exige capacidade municipal unica e segura.")
    capability = matches[0]
    if not capability.national_standard_enabled:
        raise NfseCapabilityError("A manifestação NFS-e e restrita ao Padrão Nacional.")
    if not capability.manifestation_enabled:
        raise NfseCapabilityError("A manifestação NFS-e esta desabilitada para o município configurado.")
    return NfseCapabilityResolution(capability=capability, legacy_compatibility_used=False)
