import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from apps.core.infrastructure.models.abstract import TimeStampedModel


class JobStatus(models.TextChoices):
    PENDING = "pending", _("Pendente")
    PROCESSING = "processing", _("Processando")
    COMPLETED = "completed", _("Concluído")
    FAILED = "failed", _("Falhou")
    PENDING_RECONCILIATION = "pending_reconciliation", _("Aguardando Reconciliação")
    CANCELLED = "cancelled", _("Cancelado")


class BackgroundJob(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_type = models.CharField(max_length=100, db_index=True, verbose_name=_("Tipo"))
    workshop = models.ForeignKey(
        "workshops.Workshop",
        on_delete=models.CASCADE,
        related_name="background_jobs",
        verbose_name=_("Oficina"),
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_jobs",
        verbose_name=_("Usuário Solicitante"),
    )
    
    status = models.CharField(
        max_length=30,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
        db_index=True,
        verbose_name=_("Status"),
    )
    attempts = models.PositiveIntegerField(default=0, verbose_name=_("Tentativas"))
    
    payload = models.JSONField(null=True, blank=True, verbose_name=_("Payload"))
    result = models.JSONField(null=True, blank=True, verbose_name=_("Resultado"))
    error = models.TextField(null=True, blank=True, verbose_name=_("Erro"))
    
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Data de Início"))
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Data de Conclusão"))
    
    correlation_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True, 
        db_index=True, 
        verbose_name=_("Correlation ID"),
        help_text=_("Usado para idempotência e rastreamento")
    )

    class Meta:
        verbose_name = _("Job Assíncrono")
        verbose_name_plural = _("Jobs Assíncronos")
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["status", "job_type"]),
            models.Index(fields=["workshop", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.job_type} ({self.get_status_display()}) - {self.id}"
