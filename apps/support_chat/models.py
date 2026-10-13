from __future__ import annotations

import uuid

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
