from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from apps.finance.models.finance import NfeRequest, NfseRequest, WebmaniaCompany


class EmissionNumberReservationError(Exception):
    pass


@dataclass(frozen=True)
class ReservedNfeNumber:
    number: int
    series: int | None


@dataclass(frozen=True)
class ReservedNfseRpsNumber:
    number: int
    series: str


def _is_homolog_environment() -> bool:
    raw_value = str(getattr(settings, "WEBMANIA_AMBIENT", "2") or "2").strip()
    return raw_value == "2"


def _lock_company_for_workshop(*, workshop_id: int) -> WebmaniaCompany:
    company = WebmaniaCompany.objects.select_for_update().filter(workshop_id=workshop_id).first()
    if company is None:
        raise EmissionNumberReservationError("Configure a empresa fiscal da oficina antes de emitir notas.")
    return company


def reserve_nfe_request_number(*, nfe_request: NfeRequest) -> ReservedNfeNumber:
    with transaction.atomic():
        locked_request = NfeRequest.objects.select_related("workshop").select_for_update().get(pk=nfe_request.pk)
        if locked_request.reserved_number is not None:
            reserved = ReservedNfeNumber(number=int(locked_request.reserved_number), series=locked_request.reserved_series)
            nfe_request.reserved_number = reserved.number
            nfe_request.reserved_series = reserved.series
            return reserved

        company = _lock_company_for_workshop(workshop_id=locked_request.workshop_id)
        counter_field = "nfe_numero_dev" if _is_homolog_environment() else "nfe_numero"
        next_number = getattr(company, counter_field)
        if next_number is None:
            raise EmissionNumberReservationError("Configure o próximo número da Nota Fiscal de Produto da oficina antes de emitir a Nota Fiscal de Produto.")
        if company.nfe_serie is None:
            raise EmissionNumberReservationError("Configure a série da Nota Fiscal de Produto da oficina antes de emitir a Nota Fiscal de Produto.")

        locked_request.reserved_number = int(next_number)
        locked_request.reserved_series = company.nfe_serie
        locked_request.save(update_fields=["reserved_number", "reserved_series"])

        setattr(company, counter_field, int(next_number) + 1)
        company.save(update_fields=[counter_field])

        reserved = ReservedNfeNumber(number=int(locked_request.reserved_number), series=locked_request.reserved_series)
        nfe_request.reserved_number = reserved.number
        nfe_request.reserved_series = reserved.series
        return reserved


def reserve_nfse_request_rps_number(*, nfse_request: NfseRequest) -> ReservedNfseRpsNumber:
    with transaction.atomic():
        locked_request = NfseRequest.objects.select_related("workshop").select_for_update().get(pk=nfse_request.pk)
        if locked_request.reserved_rps_number is not None:
            reserved = ReservedNfseRpsNumber(number=int(locked_request.reserved_rps_number), series=str(locked_request.reserved_rps_series or ""))
            nfse_request.reserved_rps_number = reserved.number
            nfse_request.reserved_rps_series = reserved.series
            return reserved

        company = _lock_company_for_workshop(workshop_id=locked_request.workshop_id)
        counter_field = "nfse_rps_numero_dev" if _is_homolog_environment() else "nfse_rps_numero"
        next_number = getattr(company, counter_field)
        if next_number is None:
            raise EmissionNumberReservationError("Configure o próximo RPS da Nota Fiscal de Serviço da oficina antes de emitir a Nota Fiscal de Serviço.")

        locked_request.reserved_rps_number = int(next_number)
        locked_request.reserved_rps_series = str(company.nfse_rps_serie or "")
        locked_request.save(update_fields=["reserved_rps_number", "reserved_rps_series"])

        setattr(company, counter_field, int(next_number) + 1)
        company.save(update_fields=[counter_field])

        reserved = ReservedNfseRpsNumber(number=int(locked_request.reserved_rps_number), series=str(locked_request.reserved_rps_series or ""))
        nfse_request.reserved_rps_number = reserved.number
        nfse_request.reserved_rps_series = reserved.series
        return reserved
