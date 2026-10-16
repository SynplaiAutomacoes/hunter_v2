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
    color = models.CharField(verbose_name="Cor", max_length=7, default="#1e40af")
    date_base = models.CharField(verbose_name="Período", max_length=20, choices=YardDateBase.choices, default=YardDateBase.MONTHLY)
    position = models.PositiveIntegerField(verbose_name="Ordem", default=0)

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


def valid_statuses_for_target(target: str) -> set[str]:
    from apps.budget.models import BudgetStatus
    from apps.workorder.models import WorkOrderStatus

    if target == YardColumnTarget.BUDGET:
        return {STATUS_ALL, *(value for value, _label in BudgetStatus.choices)}
    if target == YardColumnTarget.WORKORDER:
        return {STATUS_ALL, *(value for value, _label in WorkOrderStatus.choices)}
    return set()


class YardHiddenStatus(TimeStampedModel):
    """Status que nunca aparece no painel da oficina."""

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="yard_hidden_statuses")
    target = models.CharField(verbose_name="Modelo", max_length=20, choices=YardColumnTarget.choices)
    status = models.CharField(verbose_name="Status", max_length=32)

    class Meta:
        verbose_name = "Status Oculto do Pátio"
        verbose_name_plural = "Status Ocultos do Pátio"
        ordering = ["target", "status"]
        constraints = [
            models.UniqueConstraint(fields=("workshop", "target", "status"), name="unique_yard_hidden_status"),
        ]

    def __str__(self) -> str:
        return f"{self.target}/{self.status} ({self.workshop})"

    @property
    def status_label(self) -> str:
        from apps.budget.models import BudgetStatus
        from apps.workorder.models import WorkOrderStatus

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
        if self.status not in valid_statuses_for_target(self.target) or self.status == STATUS_ALL:
            raise ValidationError({"status": "Selecione um status válido do modelo (exceto Todos)."})


class YardStatusGroup(TimeStampedModel):
    """Agrupa status sob um título de exibição (apenas visual)."""

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="yard_status_groups")
    target = models.CharField(verbose_name="Modelo", max_length=20, choices=YardColumnTarget.choices)
    title = models.CharField(verbose_name="Título de exibição", max_length=80)
    statuses = models.JSONField(verbose_name="Status agrupados", default=list, blank=True)

    class Meta:
        verbose_name = "Agrupamento de Status do Pátio"
        verbose_name_plural = "Agrupamentos de Status do Pátio"
        ordering = ["target", "title"]
        constraints = [
            models.UniqueConstraint(fields=("workshop", "target", "title"), name="unique_yard_status_group_title"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.workshop})"

    def clean(self) -> None:
        super().clean()
        members = [str(status) for status in (self.statuses or []) if str(status)]
        if not members:
            raise ValidationError({"statuses": "Selecione ao menos um status."})
        valid = valid_statuses_for_target(self.target) - {STATUS_ALL}
        invalid = [status for status in members if status not in valid]
        if invalid:
            raise ValidationError({"statuses": f"Status inválidos para o modelo: {', '.join(invalid)}."})
        self.statuses = sorted(set(members))


class YardPreference(TimeStampedModel):
    """Preferências de exibição do painel por oficina."""

    workshop = models.OneToOneField("workshops.Workshop", on_delete=models.CASCADE, related_name="yard_preference")
    hide_similar = models.BooleanField(verbose_name="Não exibir similares", default=False)

    class Meta:
        verbose_name = "Preferência do Pátio"
        verbose_name_plural = "Preferências do Pátio"

    def __str__(self) -> str:
        return f"Preferências do pátio ({self.workshop})"
