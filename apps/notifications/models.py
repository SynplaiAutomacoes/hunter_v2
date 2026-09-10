from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.infrastructure import TimeStampedModel


class Notification(TimeStampedModel):
    title = models.CharField(max_length=255, verbose_name="Título")
    message = models.TextField(verbose_name="Mensagem")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_notifications",
        verbose_name="Remetente",
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Metadados")

    class Meta:
        verbose_name = "Notificação"
        verbose_name_plural = "Notificações"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        return self.title


class NotificationRecipient(TimeStampedModel):
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="recipients",
        verbose_name="Notificação",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_recipients",
        verbose_name="Usuário",
    )
    workshop = models.ForeignKey(
        "workshops.Workshop",
        on_delete=models.PROTECT,
        related_name="notification_recipients",
        verbose_name="Oficina",
    )
    is_read = models.BooleanField(default=False, verbose_name="Lida?")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="Lida em")

    class Meta:
        verbose_name = "Destinatário de Notificação"
        verbose_name_plural = "Destinatários de Notificação"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(
                fields=["user", "workshop", "is_read", "-criado_em"],
                name="idx_notif_recip_usr_wksp_read",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.notification.title} ({'Lida' if self.is_read else 'Não lida'})"

    def mark_as_read(self) -> None:
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at", "atualizado_em"])
