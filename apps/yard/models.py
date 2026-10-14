from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.infrastructure.models import TimeStampedModel


class YardColumnTarget(models.TextChoices):
    BUDGET = "budget", "Orçamento"
    WORKORDER = "workorder", "Ordem de Serviço"


class YardDateBase(models.TextChoices):
    MONTHLY = "monthly", "Mensal"
    WEEKLY = "weekly", "Semanal"
    DAILY = "daily", "Diário"


STATUS_ALL = "all"


class YardColumn(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="yard_columns")
    target = models.CharField(verbose_name="Modelo", max_length=20, choices=YardColumnTarget.choices)
    status = models.CharField(verbose_name="Status", max_length=32, default=STATUS_ALL)
    title = models.CharField(verbose_name="Título", max_length=80)
    color = models.CharField(verbose_name="Cor", max_length=7, default="#3b82f6")
    date_base = models.CharField(verbose_name="Base de data", max_length=20, choices=YardDateBase.choices, default=YardDateBase.MONTHLY)
    position = models.PositiveIntegerField(verbose_name="Ordem", default=0)
    is_active = models.BooleanField(verbose_name="Ativa", default=True)

    class Meta:
        verbose_name = "Coluna do Pátio"
        verbose_name_plural = "Colunas do Pátio"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=("workshop", "target", "status"), name="unique_yard_column_per_status"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.workshop})"

    @property
    def status_label(self) -> str:
        from apps.budget.models import BudgetStatus
        from apps.workorder.models import WorkOrderStatus

        if self.status == STATUS_ALL:
            return "Todos"
        try:
            if self.target == YardColumnTarget.BUDGET:
                return BudgetStatus(self.status).label
            if self.target == YardColumnTarget.WORKORDER:
                return WorkOrderStatus(self.status).label
        except ValueError:
            pass
        return self.status

    def clean(self) -> None:
        super().clean()
        from apps.budget.models import BudgetStatus
        from apps.workorder.models import WorkOrderStatus

        if self.target == YardColumnTarget.BUDGET:
            valid = {STATUS_ALL, *(value for value, _label in BudgetStatus.choices)}
        elif self.target == YardColumnTarget.WORKORDER:
            valid = {STATUS_ALL, *(value for value, _label in WorkOrderStatus.choices)}
        else:
            raise ValidationError({"target": "Selecione Orçamento ou Ordem de Serviço."})

        if self.status not in valid:
            raise ValidationError({"status": "Status inválido para o modelo selecionado."})

        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(self.color or "").strip()):
            raise ValidationError({"color": "Informe uma cor hexadecimal válida (ex.: #3b82f6)."})
