from django.conf import settings
from django.http import Http404

from apps.collaborators.models import WorkshopMember
from apps.workshops.util.workshops import get_active_workshop_or_404


def support_chat(request):
    visible = False
    if getattr(settings, "SUPPORT_CHAT_ENABLED", False) and getattr(request, "user", None) is not None and request.user.is_authenticated:
        try:
            workshop = get_active_workshop_or_404(request)
            member = WorkshopMember.objects.filter(user=request.user, workshop=workshop, is_active=True).first()
            if member is not None:
                from apps.support_chat.application.access_policy import can_use_chat

                visible = can_use_chat(user=request.user, workshop=workshop)
        except Http404:
            visible = False
    return {
        "SUPPORT_CHAT_ENABLED": getattr(settings, "SUPPORT_CHAT_ENABLED", False),
        "SUPPORT_CHAT_VISIBLE": visible,
    }
