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


logger = logging.getLogger(__name__)


class WhatsAppConnectView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Workshop
    workshop_permission_codename = "change_workshop"

    def post(self, request, *args, **kwargs):
        workshop = self.workshop
        company = getattr(workshop, "webmania_company", None)
        phone = str(company.telefone or "").strip() if company else ""

        if not phone:
            return JsonResponse({"ok": False, "message": "Telefone da empresa nao configurado. Preencha o campo telefone na aba Empresa."}, status=400)

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
            logger.warning(
                "whatsapp_connect_failed workshop_id=%s error=%s",
                workshop.pk,
                str(exc),
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
            logger.warning(
                "whatsapp_status_failed workshop_id=%s error=%s",
                workshop.pk,
                str(exc),
            )
            return JsonResponse({"ok": False, "connected": False, "message": str(exc)}, status=502)

        connected = bool(status_data.get("connected", False))
        state = str(status_data.get("state", "unknown"))

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
            return JsonResponse({"ok": True, "message": "Nenhuma instancia para desconectar."})

        try:
            service = EvolutionAPIServiceFactory.get_service()
            service.delete_instance(instance_name=instance_name)
        except WhatsAppConfigurationError as exc:
            logger.warning(
                "whatsapp_disconnect_not_configured workshop_id=%s error=%s",
                workshop.pk,
                str(exc),
            )
            return JsonResponse({"ok": False, "message": str(exc)}, status=503)
        except WhatsAppServiceError as exc:
            logger.warning(
                "whatsapp_disconnect_failed workshop_id=%s error=%s",
                workshop.pk,
                str(exc),
            )
            return JsonResponse({"ok": False, "message": str(exc)}, status=502)

        workshop.whatsapp_instance_name = ""
        workshop.save(update_fields=["whatsapp_instance_name"])

        return JsonResponse({"ok": True, "message": "WhatsApp desconectado com sucesso."})
