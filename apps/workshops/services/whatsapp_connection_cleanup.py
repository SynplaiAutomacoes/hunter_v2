from __future__ import annotations

import logging
from dataclasses import dataclass

from apps.messaging.infrastructure.services.worker_control import MessageWorkerControlError, stop_workshop_dispatch
from apps.workshops.models.workshops import Workshop
from apps.workshops.services.evolution_api import (
    EvolutionAPIServiceFactory,
    WhatsAppConfigurationError,
    WhatsAppServiceError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WhatsAppCleanupResult:
    cancelled_worker: bool
    deleted_instance: bool
    cleared_local: bool
    warnings: tuple[str, ...] = ()


def cleanup_whatsapp_connection(*, workshop: Workshop, cancel_worker: bool = True) -> WhatsAppCleanupResult:
    """Idempotent cleanup when WhatsApp becomes disconnected.

    1. POST cancelled to message worker (if configured)
    2. Delete Evolution instance when name is present
    3. Clear local whatsapp_instance_name
    """
    warnings: list[str] = []
    cancelled_worker = False
    deleted_instance = False
    instance_name = str(workshop.whatsapp_instance_name or "").strip()

    if cancel_worker:
        try:
            cancelled_worker = bool(stop_workshop_dispatch(workshop_id=workshop.pk))
        except MessageWorkerControlError as exc:
            warnings.append(str(exc))
            logger.warning(
                "whatsapp_cleanup_worker_cancel_failed",
                extra={"workshop_id": workshop.pk, "error": str(exc)},
            )

    if instance_name:
        try:
            service = EvolutionAPIServiceFactory.get_service()
            service.delete_instance(instance_name=instance_name)
            deleted_instance = True
        except WhatsAppConfigurationError as exc:
            warnings.append(str(exc))
            logger.warning(
                "whatsapp_cleanup_not_configured",
                extra={"workshop_id": workshop.pk, "error": str(exc)},
            )
        except WhatsAppServiceError as exc:
            warnings.append(str(exc))
            logger.exception(
                "whatsapp_cleanup_delete_failed",
                extra={"workshop_id": workshop.pk, "instance_name": instance_name},
            )

    cleared_local = False
    if workshop.whatsapp_instance_name:
        workshop.whatsapp_instance_name = ""
        workshop.save(update_fields=["whatsapp_instance_name"])
        cleared_local = True

    return WhatsAppCleanupResult(
        cancelled_worker=cancelled_worker,
        deleted_instance=deleted_instance,
        cleared_local=cleared_local,
        warnings=tuple(warnings),
    )
