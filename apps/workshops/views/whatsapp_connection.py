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
from apps.workshops.services.whatsapp_instance_status import (
    is_instance_awaiting_qr,
    is_instance_connected,
    is_instance_disconnected,
    normalize_instance_state,
)

logger = logging.getLogger(__name__)


def _png_data_uri(png_bytes: bytes) -> str:
    qrcode_base64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{qrcode_base64}"


def _is_instance_not_found_error(exc: WhatsAppServiceError) -> bool:
    return "nao encontrada" in str(exc).lower()


class WhatsAppConnectView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = Workshop
    workshop_permission_codename = "change_workshop"

    def post(self, request, *args, **kwargs):
        workshop = self.workshop
        phone = str(workshop.whatsapp_phone or "").strip()

        if not phone:
            return JsonResponse(
                {
                    "ok": False,
                    "message": (
                        "Telefone do Assistente Virtual nao configurado. "
                        "Preencha o campo Telefone Assistente Virtual na aba Empresa."
                    ),
                },
                status=400,
            )

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

        workshop.whatsapp_instance_name = resolved_name
        workshop.save(update_fields=["whatsapp_instance_name"])

        return JsonResponse(
            {
                "ok": True,
                "qrcode": _png_data_uri(qrcode_content),
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
            if _is_instance_not_found_error(exc):
                cleanup_result = cleanup_whatsapp_connection(workshop=workshop, cancel_worker=True)
                logger.info(
                    "whatsapp_status_instance_missing_cleanup",
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
                        "state": "close",
                        "instance": instance_name,
                        "cleaned_up": True,
                    }
                )
            logger.exception(
                "whatsapp_status_failed",
                extra={"workshop_id": workshop.pk},
            )
            return JsonResponse({"ok": False, "connected": False, "message": str(exc)}, status=502)

        state = normalize_instance_state(status_data) or str(status_data.get("state", "unknown"))
        connected = is_instance_connected(status_data)

        if connected:
            return JsonResponse(
                {
                    "ok": True,
                    "connected": True,
                    "state": state,
                    "instance": status_data.get("instance", instance_name),
                }
            )

        if is_instance_awaiting_qr(status_data):
            return JsonResponse(
                {
                    "ok": True,
                    "connected": False,
                    "state": state or "connecting",
                    "instance": status_data.get("instance", instance_name),
                }
            )

        if is_instance_disconnected(status_data):
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
                    "state": state or "close",
                    "instance": status_data.get("instance", instance_name),
                    "cleaned_up": True,
                }
            )

        return JsonResponse(
            {
                "ok": True,
                "connected": False,
                "state": state or "unknown",
                "instance": status_data.get("instance", instance_name),
            }
        )


class WhatsAppQrcodeRefreshView(LoginRequiredMixin, WorkshopScopedMixin, View):
    """Refresh QR via GET /instances/{name}/qrcode after checking status."""

    model = Workshop
    workshop_permission_codename = "change_workshop"

    def post(self, request, *args, **kwargs):
        workshop = self.workshop
        instance_name = str(workshop.whatsapp_instance_name or "").strip()

        if not instance_name:
            return JsonResponse(
                {
                    "ok": False,
                    "message": "Nenhuma instancia WhatsApp configurada. Conecte novamente.",
                },
                status=400,
            )

        try:
            service = EvolutionAPIServiceFactory.get_service()
            status_data: dict[str, Any] = service.get_status(instance_name=instance_name)
        except WhatsAppConfigurationError as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=503)
        except WhatsAppServiceError as exc:
            if _is_instance_not_found_error(exc):
                cleanup_whatsapp_connection(workshop=workshop, cancel_worker=True)
                return JsonResponse(
                    {
                        "ok": False,
                        "cleaned_up": True,
                        "message": "Instancia nao encontrada. Conecte novamente para gerar um novo QR Code.",
                    },
                    status=404,
                )
            logger.exception(
                "whatsapp_qrcode_refresh_status_failed",
                extra={"workshop_id": workshop.pk},
            )
            return JsonResponse({"ok": False, "message": str(exc)}, status=502)

        if is_instance_connected(status_data):
            return JsonResponse(
                {
                    "ok": False,
                    "connected": True,
                    "state": normalize_instance_state(status_data) or "open",
                    "message": "Instancia ja conectada. Nao e necessario atualizar o QR Code.",
                },
                status=409,
            )

        if is_instance_disconnected(status_data):
            cleanup_whatsapp_connection(workshop=workshop, cancel_worker=True)
            return JsonResponse(
                {
                    "ok": False,
                    "cleaned_up": True,
                    "state": "close",
                    "message": "Instancia desconectada e removida. Conecte novamente para gerar um novo QR Code.",
                },
                status=409,
            )

        if not is_instance_awaiting_qr(status_data):
            return JsonResponse(
                {
                    "ok": False,
                    "state": normalize_instance_state(status_data) or "unknown",
                    "message": "Nao foi possivel atualizar o QR Code neste estado. Conecte novamente.",
                },
                status=409,
            )

        try:
            qrcode_content = service.get_qrcode(instance_name=instance_name)
        except WhatsAppServiceError as exc:
            if _is_instance_not_found_error(exc):
                cleanup_whatsapp_connection(workshop=workshop, cancel_worker=True)
                return JsonResponse(
                    {
                        "ok": False,
                        "cleaned_up": True,
                        "message": "Instancia nao encontrada. Conecte novamente para gerar um novo QR Code.",
                    },
                    status=404,
                )
            logger.exception(
                "whatsapp_qrcode_refresh_failed",
                extra={"workshop_id": workshop.pk, "instance_name": instance_name},
            )
            return JsonResponse({"ok": False, "message": str(exc)}, status=502)

        return JsonResponse(
            {
                "ok": True,
                "qrcode": _png_data_uri(qrcode_content),
                "instance_name": instance_name,
                "state": "connecting",
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
