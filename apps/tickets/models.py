from __future__ import annotations

from django.conf import settings
from django.db import models


class TicketStatus(models.TextChoices):
    ABERTO = "aberto", "Aberto"
    EM_ANDAMENTO = "em_andamento", "Em andamento"
    VALIDACAO_INTERNA = "validacao_interna", "Validação interna"
    AGUARDANDO_VALIDACAO = "aguardando_validacao", "Aguardando validação"
    REPROVADO = "reprovado", "Reprovado"
    FECHADO = "fechado", "Fechado"
    CANCELADO = "cancelado", "Cancelado"


NON_FINAL_STATUSES: tuple[str, ...] = (
    TicketStatus.ABERTO,
    TicketStatus.EM_ANDAMENTO,
    TicketStatus.VALIDACAO_INTERNA,
    TicketStatus.AGUARDANDO_VALIDACAO,
    TicketStatus.REPROVADO,
)

FINAL_STATUSES: tuple[str, ...] = (
    TicketStatus.FECHADO,
    TicketStatus.CANCELADO,
)


class TicketAttachmentSource(models.TextChoices):
    UPLOAD = "upload", "Upload"
    SCREEN_RECORDING = "screen_recording", "Gravação de tela"
    REJECTION = "rejection", "Recusa"


class Ticket(models.Model):
    workshop = models.ForeignKey(
        "workshops.Workshop",
        on_delete=models.CASCADE,
        related_name="tickets",
        verbose_name="Oficina",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tickets_created",
        verbose_name="Criado por",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="tickets_assigned",
        verbose_name="Responsável",
        null=True,
        blank=True,
    )
    title = models.CharField(verbose_name="Título", max_length=255)
    problem = models.TextField(verbose_name="Qual o problema")
    reproduction_steps = models.TextField(verbose_name="Como repetir este problema")
    status = models.CharField(
        verbose_name="Status",
        max_length=32,
        choices=TicketStatus.choices,
        default=TicketStatus.ABERTO,
        db_index=True,
    )
    cancellation_reason = models.TextField(verbose_name="Motivo do cancelamento", blank=True)
    rejection_reason = models.TextField(verbose_name="Motivo da recusa", blank=True)
    created_at = models.DateTimeField(verbose_name="Criado em", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="Atualizado em", auto_now=True)
    captured_at = models.DateTimeField(verbose_name="Capturado em", null=True, blank=True)

    class Meta:
        verbose_name = "Chamado"
        verbose_name_plural = "Chamados"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"#{self.pk} {self.title}"

    @property
    def is_final(self) -> bool:
        return self.status in FINAL_STATUSES

    @property
    def status_badge_class(self) -> str:
        from apps.tickets.constants import STATUS_BADGE_CLASSES

        return STATUS_BADGE_CLASSES.get(self.status, "badge-ghost")


class TicketAttachment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="attachments", verbose_name="Chamado")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ticket_attachments",
        verbose_name="Enviado por",
    )
    file_key = models.CharField(verbose_name="Chave no storage", max_length=512)
    content_type = models.CharField(verbose_name="Content-Type", max_length=255, blank=True)
    original_name = models.CharField(verbose_name="Nome original", max_length=255)
    size_bytes = models.PositiveBigIntegerField(verbose_name="Tamanho (bytes)", default=0)
    source = models.CharField(
        verbose_name="Origem",
        max_length=32,
        choices=TicketAttachmentSource.choices,
        default=TicketAttachmentSource.UPLOAD,
    )
    created_at = models.DateTimeField(verbose_name="Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Anexo do chamado"
        verbose_name_plural = "Anexos do chamado"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return self.original_name


class TicketMessage(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages", verbose_name="Chamado")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ticket_messages",
        verbose_name="Autor",
    )
    body = models.TextField(verbose_name="Mensagem")
    created_at = models.DateTimeField(verbose_name="Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Mensagem do chamado"
        verbose_name_plural = "Mensagens do chamado"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"Mensagem #{self.pk} do chamado #{self.ticket_id}"


class TicketStatusHistory(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="status_history", verbose_name="Chamado")
    from_status = models.CharField(verbose_name="Status anterior", max_length=32, blank=True)
    to_status = models.CharField(verbose_name="Novo status", max_length=32)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="ticket_status_changes",
        verbose_name="Autor",
        null=True,
        blank=True,
    )
    note = models.TextField(verbose_name="Observação", blank=True)
    created_at = models.DateTimeField(verbose_name="Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Histórico de status do chamado"
        verbose_name_plural = "Históricos de status do chamado"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.from_status} → {self.to_status}"
