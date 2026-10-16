from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

from apps.support_chat.models import ChatBlockedUser, ChatDisabledWorkshop, chat_access_cache_key

CACHE_SECONDS = 60


def _is_system_admin(*, username: str) -> bool:
    admin_usernames = getattr(settings, "SYSTEM_ADMIN_USERNAMES", [])
    return username in admin_usernames


def can_use_chat(*, user, workshop) -> bool:
    """Blocklist: acesso se usuário não bloqueado E oficina habilitada.

    Bypass total para SYSTEM_ADMIN_USERNAMES. Resultado com cache curto.
    """
    if _is_system_admin(username=getattr(user, "username", "")):
        return True
    cache_key = chat_access_cache_key(user_id=user.pk, workshop_id=workshop.pk)
    try:
        cached = cache.get(cache_key)
    except Exception:
        cached = None
    if isinstance(cached, bool):
        return cached
    allowed = not ChatBlockedUser.objects.filter(user_id=user.pk).exists()
    if allowed:
        allowed = not ChatDisabledWorkshop.objects.filter(workshop_id=workshop.pk).exists()
    try:
        cache.set(cache_key, allowed, CACHE_SECONDS)
    except Exception:
        pass
    return allowed
