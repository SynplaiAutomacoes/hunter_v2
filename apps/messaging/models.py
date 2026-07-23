from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from apps.core.infrastructure.models import TimeStampedModel
from apps.customer.models import Customer


class MessageTemplate(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="Data de Criação")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Data de Atualização")
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="message_templates")
    name = models.CharField(verbose_name="Nome", max_length=120)
    message = models.TextField(verbose_name="Mensagem")
    is_active = models.BooleanField(verbose_name="Ativa", default=True)

    class Meta:
        verbose_name = "Mensagem WhatsApp"
        verbose_name_plural = "Mensagens WhatsApp"
        constraints = [models.UniqueConstraint(fields=("workshop", "name"), name="unique_message_template_name_per_workshop")]

    @property
    def created_at_display(self) -> str:
        from django.utils import timezone

        return timezone.localtime(self.criado_em).strftime("%d/%m/%Y %H:%M")

    def __str__(self) -> str:
        return self.name


class CustomerMessageGroup(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="customer_message_groups")
    name = models.CharField(verbose_name="Nome", max_length=120)
    description = models.TextField(verbose_name="Descrição", blank=True)
    message_template = models.ForeignKey(
        MessageTemplate,
        verbose_name="Mensagem cadastrada",
        on_delete=models.SET_NULL,
        related_name="customer_message_groups",
        null=True,
        blank=True,
    )
    message = models.TextField(verbose_name="Mensagem personalizada")
    is_active = models.BooleanField(verbose_name="Ativo", default=True)
    customers = models.ManyToManyField(Customer, through="CustomerMessageGroupMembership", related_name="message_groups", blank=True)
    filter_criteria = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Critérios de segmentação",
        help_text="Configuração JSON com regras para incluir clientes automaticamente no grupo. Deixe vazio para usar apenas seleção manual.",
    )

    class Meta:
        verbose_name = "Grupo de mensagem"
        verbose_name_plural = "Grupos de mensagens"
        constraints = [models.UniqueConstraint(fields=("workshop", "name"), name="unique_customer_message_group_name_per_workshop")]

    @property
    def created_at_display(self) -> str:
        from django.utils import timezone

        return timezone.localtime(self.criado_em).strftime("%d/%m/%Y %H:%M")

    def __str__(self) -> str:
        return self.name


class CustomerMessageGroupMembership(TimeStampedModel):
    group = models.ForeignKey(CustomerMessageGroup, verbose_name="Grupo", on_delete=models.CASCADE, related_name="memberships")
    customer = models.ForeignKey(Customer, verbose_name="Cliente", on_delete=models.CASCADE, related_name="message_group_memberships")

    class Meta:
        verbose_name = "Cliente do grupo de mensagem"
        verbose_name_plural = "Clientes do grupo de mensagem"
        constraints = [models.UniqueConstraint(fields=("group", "customer"), name="unique_customer_message_group_membership")]

    def __str__(self) -> str:
        return f"{self.group} - {self.customer}"


class MessageDispatchBatch(TimeStampedModel):
    class Source(models.TextChoices):
        GROUP_MANUAL = "group_manual", "Disparo manual de grupo"
        APPOINTMENT_ALERT = "appointment_alert", "Alerta de agendamento"
        COMMAND = "command", "Comando"

    class Status(models.TextChoices):
        QUEUED = "queued", "Na fila"
        PROCESSING = "processing", "Processando"
        COMPLETED = "completed", "Concluído"
        FAILED = "failed", "Falhou"
        CANCELLED = "cancelled", "Cancelado"

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="message_dispatch_batches")
    group = models.ForeignKey(
        CustomerMessageGroup,
        verbose_name="Grupo",
        on_delete=models.SET_NULL,
        related_name="dispatch_batches",
        null=True,
        blank=True,
    )
    source = models.CharField(verbose_name="Origem", max_length=32, choices=Source.choices)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Disparado por",
        on_delete=models.SET_NULL,
        related_name="message_dispatch_batches",
        null=True,
        blank=True,
    )
    status = models.CharField(verbose_name="Status", max_length=20, choices=Status.choices, default=Status.QUEUED)
    total_count = models.PositiveIntegerField(verbose_name="Total", default=0)
    queued_count = models.PositiveIntegerField(verbose_name="Na fila", default=0)
    processing_count = models.PositiveIntegerField(verbose_name="Processando", default=0)
    sent_count = models.PositiveIntegerField(verbose_name="Enviadas", default=0)
    failed_count = models.PositiveIntegerField(verbose_name="Falhas", default=0)
    cancelled_count = models.PositiveIntegerField(verbose_name="Canceladas", default=0)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Lote de disparo"
        verbose_name_plural = "Lotes de disparo"
        indexes = [
            models.Index(fields=["workshop", "-criado_em"]),
            models.Index(fields=["group", "-criado_em"]),
        ]

    def __str__(self) -> str:
        return f"Batch #{self.pk} ({self.get_source_display()})"

    @property
    def created_at_display(self) -> str:
        from django.utils import timezone

        return timezone.localtime(self.criado_em).strftime("%d/%m/%Y %H:%M")


class MessageDispatchLog(TimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Na fila"
        PROCESSING = "processing", "Processando"
        SENT = "sent", "Enviada"
        FAILED = "failed", "Falhou"
        CANCELLED = "cancelled", "Cancelada"

    # Statuses the external worker may report via HTTP ingest.
    # `queued` is local-only (set when hunter publishes).
    # `cancelled` is local-only (set when hunter cancels in-flight sends).
    WORKER_REPORTABLE_STATUSES: frozenset[str] = frozenset(
        {
            Status.PROCESSING,
            Status.SENT,
            Status.FAILED,
        }
    )

    IN_FLIGHT_STATUSES: frozenset[str] = frozenset(
        {
            Status.QUEUED,
            Status.PROCESSING,
        }
    )

    batch = models.ForeignKey(MessageDispatchBatch, verbose_name="Lote", on_delete=models.CASCADE, related_name="logs")
    client_message_id = models.UUIDField(verbose_name="ID da mensagem", default=uuid.uuid4, unique=True, db_index=True)
    customer = models.ForeignKey(
        Customer,
        verbose_name="Cliente",
        on_delete=models.SET_NULL,
        related_name="message_dispatch_logs",
        null=True,
        blank=True,
    )
    phone = models.CharField(verbose_name="Telefone", max_length=32, blank=True, default="")
    message = models.TextField(verbose_name="Mensagem")
    status = models.CharField(verbose_name="Status", max_length=20, choices=Status.choices, default=Status.QUEUED)
    error = models.TextField(verbose_name="Erro", blank=True, default="")

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Histórico de mensagem"
        verbose_name_plural = "Histórico de mensagens"
        indexes = [
            models.Index(fields=["batch", "status"]),
            models.Index(fields=["client_message_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.client_message_id} ({self.get_status_display()})"


class ScheduledOutboundMessage(TimeStampedModel):
    class Source(models.TextChoices):
        APPOINTMENT_ALERT = "appointment_alert", "Alerta de agendamento"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        PROCESSING = "processing", "Processando"
        SENT = "sent", "Enviada"
        CANCELLED = "cancelled", "Cancelada"
        FAILED = "failed", "Falhou"

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="scheduled_outbound_messages")
    appointment = models.ForeignKey(
        "scheduling.Appointment",
        verbose_name="Agendamento",
        on_delete=models.CASCADE,
        related_name="scheduled_outbound_messages",
        null=True,
        blank=True,
    )
    customer = models.ForeignKey(
        Customer,
        verbose_name="Cliente",
        on_delete=models.SET_NULL,
        related_name="scheduled_outbound_messages",
        null=True,
        blank=True,
    )
    phone = models.CharField(verbose_name="Telefone", max_length=32, blank=True, default="")
    message = models.TextField(verbose_name="Mensagem")
    run_at = models.DateTimeField(verbose_name="Executar em", db_index=True)
    status = models.CharField(verbose_name="Status", max_length=20, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(verbose_name="Origem", max_length=32, choices=Source.choices, default=Source.APPOINTMENT_ALERT)
    client_message_id = models.UUIDField(verbose_name="ID da mensagem", default=uuid.uuid4, unique=True)
    error = models.TextField(verbose_name="Erro", blank=True, default="")
    batch = models.ForeignKey(
        MessageDispatchBatch,
        verbose_name="Lote",
        on_delete=models.SET_NULL,
        related_name="scheduled_messages",
        null=True,
        blank=True,
    )

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Mensagem agendada"
        verbose_name_plural = "Mensagens agendadas"
        indexes = [
            models.Index(fields=["status", "run_at"]),
            models.Index(fields=["workshop", "status", "run_at"]),
            models.Index(fields=["appointment", "status"]),
        ]

    def __str__(self) -> str:
        return f"Outbound #{self.pk} ({self.get_status_display()})"
