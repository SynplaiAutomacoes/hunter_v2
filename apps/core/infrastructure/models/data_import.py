from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.infrastructure.models.abstract import TimeStampedModel


class DataImportBatch(TimeStampedModel):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Concluída"
        ROLLED_BACK = "rolled_back", "Desfeita"
        PARTIALLY_ROLLED_BACK = "partially_rolled_back", "Parcialmente desfeita"

    workshop = models.ForeignKey(
        "workshops.Workshop",
        on_delete=models.CASCADE,
        related_name="data_import_batches",
    )
    entity_key = models.CharField(max_length=64, verbose_name="Entidade")
    filename = models.CharField(max_length=255, blank=True, default="")
    options = models.JSONField(default=dict, blank=True)
    mapping = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="data_import_batches",
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.COMPLETED)
    success_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    rolled_back_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Lote de importação"
        verbose_name_plural = "Lotes de importação"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["workshop", "-criado_em"], name="core_impbatch_ws_created_idx"),
            models.Index(fields=["workshop", "entity_key", "-criado_em"], name="core_impbatch_ws_ent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_key} · {self.filename or 'sem arquivo'} · {self.pk}"

    @property
    def can_rollback(self) -> bool:
        return self.status in {self.Status.COMPLETED, self.Status.PARTIALLY_ROLLED_BACK} and self.items.filter(
            success=True,
            object_id__isnull=False,
            rollback_status__in=[
                DataImportBatchItem.RollbackStatus.ACTIVE,
                DataImportBatchItem.RollbackStatus.BLOCKED,
            ],
        ).exists()


class DataImportBatchItem(TimeStampedModel):
    class RollbackStatus(models.TextChoices):
        ACTIVE = "active", "Mantido"
        DELETED = "deleted", "Removido"
        BLOCKED = "blocked", "Em uso"
        MISSING = "missing", "Já não existia"

    batch = models.ForeignKey(DataImportBatch, on_delete=models.CASCADE, related_name="items")
    row_number = models.PositiveIntegerField()
    object_id = models.PositiveIntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    message = models.TextField(blank=True, default="")
    rollback_status = models.CharField(
        max_length=16,
        choices=RollbackStatus.choices,
        default=RollbackStatus.ACTIVE,
    )
    rollback_detail = models.CharField(max_length=255, blank=True, default="")

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Item de importação"
        verbose_name_plural = "Itens de importação"
        ordering = ["row_number", "id"]
        indexes = [
            models.Index(fields=["batch", "object_id"], name="core_impitem_batch_obj_idx"),
            models.Index(fields=["batch", "rollback_status"], name="core_impitem_batch_rb_idx"),
        ]

    def __str__(self) -> str:
        return f"Lote {self.batch_id} linha {self.row_number}"


class DataImportDraft(TimeStampedModel):
    """Rascunho da importação entre upload → mapeamento → confirmação (sobrevive a reload)."""

    token = models.CharField(max_length=64, unique=True, db_index=True)
    workshop = models.ForeignKey(
        "workshops.Workshop",
        on_delete=models.CASCADE,
        related_name="data_import_drafts",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="data_import_drafts",
    )
    entity_key = models.CharField(max_length=64)
    filename = models.CharField(max_length=255, blank=True, default="")
    source_format = models.CharField(max_length=16, blank=True, default="")
    headers = models.JSONField(default=list, blank=True)
    rows = models.JSONField(default=list, blank=True)
    options = models.JSONField(default=dict, blank=True)
    mapping = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField()

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Rascunho de importação"
        verbose_name_plural = "Rascunhos de importação"
        indexes = [
            models.Index(fields=["expires_at"], name="core_impdraft_expires_idx"),
        ]

    def __str__(self) -> str:
        return f"Draft {self.entity_key} · {self.token[:8]}"
