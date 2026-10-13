from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.support_chat.models import ChatSession


def get_session_timeout() -> timedelta:
    minutes = getattr(settings, "SUPPORT_CHAT_SESSION_TIMEOUT_MINUTES", 5)
    return timedelta(minutes=minutes)


class SessionResolver:
    """Resolve a sessão ativa do par (member, workshop).

    Regra: reusa última sessão se now - last_interaction_at <= timeout,
    senão desativa e cria nova. Uma ativa por (member, workshop).
    """

    @staticmethod
    @transaction.atomic
    def resolve_active(*, member, workshop) -> ChatSession:
        now = timezone.now()
        timeout = get_session_timeout()
        qs = ChatSession.objects.select_for_update().filter(
            member=member,
            workshop=workshop,
        ).order_by("-last_interaction_at")
        latest = qs.first()
        if latest is not None and latest.is_active and (now - latest.last_interaction_at) <= timeout:
            return latest
        # Desativa anteriores e cria nova
        qs.filter(is_active=True).update(is_active=False)
        return ChatSession.objects.create(
            member=member,
            workshop=workshop,
            last_interaction_at=now,
            is_active=True,
        )

    @staticmethod
    @transaction.atomic
    def create_new(*, member, workshop) -> ChatSession:
        ChatSession.objects.filter(member=member, workshop=workshop, is_active=True).update(is_active=False)
        return ChatSession.objects.create(
            member=member,
            workshop=workshop,
            last_interaction_at=timezone.now(),
            is_active=True,
        )
