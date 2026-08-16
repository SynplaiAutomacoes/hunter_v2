from __future__ import annotations

from django.db import models

from apps.core.infrastructure.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop


class MonthlyCost(TimeStampedModel):
    workshop = models.ForeignKey(
        Workshop,
        on_delete=models.CASCADE,
        related_name="monthly_costs",
    )
    name = models.CharField(verbose_name="Nome", max_length=255)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)
    is_editable = models.BooleanField(verbose_name="Editável", default=True)

    class Meta:
        verbose_name = "Custo mensal"
        verbose_name_plural = "Custos mensais"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "name"),
                name="unique_monthly_cost_name_per_workshop",
            ),
        ]

    def __str__(self) -> str:
        return self.name
