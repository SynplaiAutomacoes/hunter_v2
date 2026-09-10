from __future__ import annotations

import logging
from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin

from apps.notifications.domain.services.notification_service import NotificationService
from apps.workshops.util.workshops import get_active_workshop_or_404

logger = logging.getLogger(__name__)

ALLOWED_LEVELS = {
    messages.SUCCESS,
    messages.WARNING,
    messages.ERROR,
    messages.INFO,
}


class MessagesNotificationMiddleware(MiddlewareMixin):
    """
    Middleware que intercepta mensagens do Django messages framework e as persiste
    como Notificações para os membros ativos da workshop ativa da sessão.
    """

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        if not getattr(settings, "NOTIFICATIONS_AUTO_CAPTURE_MESSAGES", True):
            return response

        if not hasattr(request, "user") or not request.user.is_authenticated:
            return response

        if not hasattr(request, "_messages"):
            return response

        try:
            workshop = get_active_workshop_or_404(request)
        except Http404:
            return response
        except Exception as exc:
            logger.debug("Mensagens middleware: erro ao obter workshop ativa: %s", exc)
            return response

        storage = request._messages
        was_used = getattr(storage, "used", False)

        try:
            msgs = list(storage)
            storage.used = was_used

            for msg in msgs:
                if getattr(msg, "_captured_as_notification", False):
                    continue

                if msg.level in ALLOWED_LEVELS and msg.message:
                    msg_str = str(msg.message).strip()
                    if not msg_str:
                        continue

                    title_prefix = msg.level_tag.capitalize() if getattr(msg, "level_tag", None) else "Aviso"
                    title = f"Mensagem do Sistema: {title_prefix}"

                    NotificationService.create_system_notification(
                        title=title,
                        message=msg_str,
                        workshop=workshop,
                        metadata={"level": msg.level, "level_tag": getattr(msg, "level_tag", "")},
                    )
                    msg._captured_as_notification = True

        except Exception as exc:
            logger.error("Erro ao capturar Django messages para notificações: %s", exc, exc_info=True)

        return response
