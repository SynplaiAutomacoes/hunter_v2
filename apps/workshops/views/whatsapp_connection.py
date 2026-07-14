from __future__ import annotations

import base64
import logging
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.workshops import Workshop
from apps.workshops.services.evolution_api import (
    EvolutionAPIServiceFactory,
    WhatsAppConfigurationError,
    WhatsAppServiceError,
)
from apps.workshops.services.whatsapp_connection_cleanup import cleanup_whatsapp_connection


logger = logging.getLogger(__name__)


class WhatsAppConnectView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Workshop
    workshop_permission_codename = "change_workshop"

    def post(self, request, *args, **kwargs):
        workshop = self.workshop
        phone = str(workshop.whatsapp_phone or "").strip()

        if not phone:
            return JsonResponse({"ok": False, "message": "Telefone do Assistente Virtual nao configurado. Preencha o campo Telefone Assistente Virtual na aba Empresa."}, status=400)

        instance_name = f"workshop_{workshop.pk}"

        try:
            service = EvolutionAPIServiceFactory.get_service()
            qrcode_content, resolved_name = service.create_instance(
                instance_name=instance_name,
                phone=phone,
            )
        except WhatsAppConfigurationError as exc:
            logger.warning(
                "whatsapp_connect_not_configured workshop_id=%s error=%s",
                workshop.pk,
                str(exc),
            )
            return JsonResponse({"ok": False, "message": str(exc)}, status=503)
        except WhatsAppServiceError as exc:
            logger.exception(
                "whatsapp_connect_failed",
                extra={"workshop_id": workshop.pk},
            )
            return JsonResponse({"ok": False, "message": str(exc)}, status=502)

        qrcode_base64 = base64.b64encode(qrcode_content).decode("ascii")
        data_uri = f"data:image/png;base64,{qrcode_base64}"

        workshop.whatsapp_instance_name = resolved_name
        workshop.save(update_fields=["whatsapp_instance_name"])

        return JsonResponse(
            {
                "ok": True,
                "qrcode": data_uri,
                "instance_name": resolved_name,
            }
        )


class WhatsAppStatusView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Workshop
    workshop_permission_codename = "change_workshop"

    def get(self, request, *args, **kwargs):
        workshop = self.workshop
        instance_name = str(workshop.whatsapp_instance_name or "").strip()

        if not instance_name:
            return JsonResponse({"ok": True, "connected": False, "state": "not_configured"})

        try:
            service = EvolutionAPIServiceFactory.get_service()
            status_data: dict[str, Any] = service.get_status(instance_name=instance_name)
        except WhatsAppConfigurationError as exc:
            logger.warning(
                "whatsapp_status_not_configured workshop_id=%s error=%s",
                workshop.pk,
                str(exc),
            )
            return JsonResponse({"ok": False, "connected": False, "message": str(exc)}, status=503)
        except WhatsAppServiceError as exc:
            logger.exception(
                "whatsapp_status_failed",
                extra={"workshop_id": workshop.pk},
            )
            return JsonResponse({"ok": False, "connected": False, "message": str(exc)}, status=502)

        connected = bool(status_data.get("connected", False))
        state = str(status_data.get("state", "unknown"))

        if not connected and instance_name:
            cleanup_result = cleanup_whatsapp_connection(workshop=workshop, cancel_worker=True)
            logger.info(
                "whatsapp_status_triggered_cleanup",
                extra={
                    "workshop_id": workshop.pk,
                    "cancelled_worker": cleanup_result.cancelled_worker,
                    "deleted_instance": cleanup_result.deleted_instance,
                    "warnings": list(cleanup_result.warnings),
                },
            )
            return JsonResponse(
                {
                    "ok": True,
                    "connected": False,
                    "state": state,
                    "instance": status_data.get("instance", instance_name),
                    "cleaned_up": True,
                }
            )

        return JsonResponse(
            {
                "ok": True,
                "connected": connected,
                "state": state,
                "instance": status_data.get("instance", instance_name),
            }
        )


class WhatsAppDisconnectView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Workshop
    workshop_permission_codename = "change_workshop"

    def post(self, request, *args, **kwargs):
        workshop = self.workshop
        instance_name = str(workshop.whatsapp_instance_name or "").strip()

        if not instance_name:
            # Still attempt worker cancel in case a dispatch is running without a local instance name.
            cleanup_whatsapp_connection(workshop=workshop, cancel_worker=True)
            return JsonResponse({"ok": True, "message": "Nenhuma instancia para desconectar."})

        result = cleanup_whatsapp_connection(workshop=workshop, cancel_worker=True)
        if result.warnings and not result.deleted_instance and not result.cleared_local:
            return JsonResponse(
                {
                    "ok": False,
                    "message": result.warnings[0],
                },
                status=502,
            )

        return JsonResponse({"ok": True, "message": "WhatsApp desconectado com sucesso."})
