from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from apps.core.infrastructure.services.webmania.nfe_manifesta import (
    MDE_EVENT_NOT_PERFORMED,
    MDE_EVENTS_REQUIRING_JUSTIFICATION,
    NfeManifestationError,
    build_manifesta_payload,
    manifesta_nfe,
)
from apps.stock.models import (
    SefazManifestation,
    SefazManifestationEvent,
    SefazManifestationStatus,
    SefazZipCache,
)

logger = logging.getLogger(__name__)

JUSTIFICATION_MIN_LENGTH = 15


class SefazManifestationServiceError(Exception):
    pass


def _map_remote_status(remote_status: str) -> str:
    normalized = str(remote_status or "").strip().lower()
    if normalized in {"aprovado", "autorizado", "sucesso", "success", "ok"}:
        return SefazManifestationStatus.APPROVED
    if normalized in {"reprovado", "rejeitado", "denied", "error", "erro", "failed"}:
        return SefazManifestationStatus.REPROVED
    if normalized:
        return SefazManifestationStatus.APPROVED
    return SefazManifestationStatus.FAILED


def submit_sefaz_manifestation(
    *,
    workshop,
    access_key: str,
    event_code: str,
    justificativa: str = "",
    requested_by=None,
) -> SefazManifestation:
    try:
        payload = build_manifesta_payload(
            access_key=access_key,
            event_code=event_code,
            justificativa=justificativa,
        )
    except NfeManifestationError as exc:
        raise SefazManifestationServiceError(str(exc)) from exc

    normalized_key = str(payload["chave"])
    normalized_event = str(payload["evento"])
    justification = str(payload.get("justificativa") or "")

    if normalized_event not in SefazManifestationEvent.values:
        raise SefazManifestationServiceError("Evento de manifestação inválido.")

    if normalized_event in MDE_EVENTS_REQUIRING_JUSTIFICATION and len(justification) < JUSTIFICATION_MIN_LENGTH:
        raise SefazManifestationServiceError(
            "A operação não realizada exige justificativa com pelo menos 15 caracteres."
        )

    sefaz_cache = SefazZipCache.objects.filter(workshop=workshop, key=normalized_key).first()
    manifestation = SefazManifestation.objects.create(
        workshop=workshop,
        access_key=normalized_key,
        sefaz_cache=sefaz_cache,
        event_code=normalized_event,
        status=SefazManifestationStatus.SENT,
        justificativa=justification,
        request_payload=payload,
        requested_by=requested_by if getattr(requested_by, "pk", None) else None,
    )

    try:
        result = manifesta_nfe(
            workshop=workshop,
            access_key=normalized_key,
            event_code=normalized_event,
            justificativa=justification,
        )
    except NfeManifestationError as exc:
        manifestation.status = SefazManifestationStatus.FAILED
        manifestation.error_message = str(exc)
        manifestation.response_payload = {"error": str(exc)}
        manifestation.save(update_fields=["status", "error_message", "response_payload", "atualizado_em"])
        logger.warning(
            "sefaz_manifestation_failed",
            extra={
                "workshop_id": workshop.pk,
                "access_key": normalized_key,
                "event_code": normalized_event,
                "manifestation_id": manifestation.pk,
            },
        )
        raise SefazManifestationServiceError(str(exc)) from exc

    mapped_status = _map_remote_status(result.status)
    manifestation.status = mapped_status
    manifestation.remote_uuid = result.uuid
    manifestation.xml_url = result.xml_url
    manifestation.response_payload = result.raw_payload
    manifestation.error_message = ""
    manifestation.save(
        update_fields=[
            "status",
            "remote_uuid",
            "xml_url",
            "response_payload",
            "error_message",
            "atualizado_em",
        ]
    )

    if sefaz_cache is not None and mapped_status == SefazManifestationStatus.APPROVED:
        sefaz_cache.last_manifestation_event = normalized_event
        sefaz_cache.last_manifestation_status = mapped_status
        sefaz_cache.last_manifested_at = timezone.now()
        sefaz_cache.save(
            update_fields=[
                "last_manifestation_event",
                "last_manifestation_status",
                "last_manifested_at",
                "atualizado_em",
            ]
        )

    return manifestation


def manifestation_event_choices() -> list[tuple[str, str]]:
    return list(SefazManifestationEvent.choices)


def event_requires_justification(event_code: str) -> bool:
    return str(event_code or "").strip() == MDE_EVENT_NOT_PERFORMED


def serialize_manifestation_summary(manifestation: SefazManifestation) -> dict[str, Any]:
    return {
        "id": manifestation.pk,
        "access_key": manifestation.access_key,
        "event_code": manifestation.event_code,
        "event_label": manifestation.event_label,
        "status": manifestation.status,
        "status_label": manifestation.get_status_display(),
        "remote_uuid": manifestation.remote_uuid,
    }
