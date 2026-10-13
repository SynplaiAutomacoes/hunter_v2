from __future__ import annotations

import uuid

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils import timezone

from apps.core.infrastructure import TimeStampedModel


def generate_session_id() -> str:
    return uuid.uuid4().hex


class ChatSession(TimeStampedModel):
    """Trilha de sessão do chat por vínculo (member) + oficina.

    Conteúdo das mensagens NÃO é persistido (modo sem logs).
    Apenas session_id opaco + metadados para regra de 5 min e histórico.
    """

    member = models.ForeignKey(
        "collaborators.WorkshopMember",
        on_delete=models.CASCADE,
        related_name="support_chat_sessions",
        verbose_name="Vínculo",
    )
    workshop = models.ForeignKey(
        "workshops.Workshop",
        on_delete=models.CASCADE,
        related_name="support_chat_sessions",
        verbose_name="Oficina",
    )
    session_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        default=generate_session_id,
        verbose_name="Session ID",
    )
    last_interaction_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        verbose_name="Última interação",
    )
    message_count = models.PositiveIntegerField(default=0, verbose_name="Mensagens")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Ativa?")

    class Meta:
        verbose_name = "Sessão de Chat"
        verbose_name_plural = "Sessões de Chat"
        ordering = ["-last_interaction_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("member", "workshop"),
                condition=models.Q(is_active=True),
                name="unique_active_chat_session_per_member_workshop",
            ),
        ]
        indexes = [
            models.Index(
                fields=("member", "workshop", "-last_interaction_at"),
                name="chat_sess_member_ws_last_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.member_id}@{self.workshop_id} {self.session_id[:8]}"

    def touch(self) -> None:
        self.last_interaction_at = timezone.now()
        self.message_count += 1
        self.save(update_fields=["last_interaction_at", "message_count", "atualizado_em"])


def chat_access_cache_key(*, user_id: int, workshop_id: int) -> str:
    return f"support_chat_access:v{get_access_version()}:{user_id}:{workshop_id}"


ACCESS_VERSION_KEY = "support_chat_access_version"


def get_access_version() -> int:
    try:
        version = cache.get(ACCESS_VERSION_KEY)
    except Exception:
        return 1
    return int(version) if isinstance(version, int) else 1


def bump_access_version() -> None:
    try:
        try:
            cache.incr(ACCESS_VERSION_KEY)
        except ValueError:
            cache.set(ACCESS_VERSION_KEY, get_access_version() + 1, None)
    except Exception:
        pass


class ChatBlockedUser(TimeStampedModel):
    """Blocklist global de usuários sem acesso ao chat (padrão: todos têm acesso)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_chat_block",
        verbose_name="Usuário",
    )
    blocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_chat_blocks_created",
        verbose_name="Bloqueado por",
    )

    class Meta:
        verbose_name = "Usuário Bloqueado do Chat"
        verbose_name_plural = "Usuários Bloqueados do Chat"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        return f"Bloqueado: {self.user}"

    def _clear_access_cache(self) -> None:
        bump_access_version()

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        self._clear_access_cache()

    def delete(self, *args: object, **kwargs: object) -> None:
        super().delete(*args, **kwargs)
        self._clear_access_cache()


class ChatDisabledWorkshop(TimeStampedModel):
    """Oficinas com o chat desabilitado (padrão: todas habilitadas)."""

    workshop = models.OneToOneField(
        "workshops.Workshop",
        on_delete=models.CASCADE,
        related_name="support_chat_disable",
        verbose_name="Oficina",
    )
    disabled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_chat_disables_created",
        verbose_name="Desabilitado por",
    )

    class Meta:
        verbose_name = "Oficina sem Chat"
        verbose_name_plural = "Oficinas sem Chat"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        return f"Chat desabilitado: {self.workshop}"

    def _clear_access_cache(self) -> None:
        bump_access_version()

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        self._clear_access_cache()

    def delete(self, *args: object, **kwargs: object) -> None:
        super().delete(*args, **kwargs)
        self._clear_access_cache()
