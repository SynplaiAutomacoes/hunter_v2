from __future__ import annotations

from django.db import models

from apps.core.infrastructure.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop


class ReviewPlan(TimeStampedModel):
    workshop = models.ForeignKey(
        Workshop,
        on_delete=models.CASCADE,
        related_name="review_plans",
    )
    name = models.CharField(verbose_name="Nome", max_length=255)
    validity_days = models.PositiveIntegerField(verbose_name="Validade do óleo (dias)")
    validity_km = models.PositiveIntegerField(verbose_name="Validade do óleo (km)")
    notification_lead_days = models.PositiveIntegerField(
        verbose_name="Antecedência da notificação (dias)",
        default=7,
    )
    repeat_notification = models.BooleanField(
        verbose_name="Repetir aviso até a troca",
        default=False,
        help_text="Quando ativo, o aviso do plano de revisão é recalculado e reenviado ao cliente até que uma nova troca seja registrada.",
    )
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    class Meta:
        verbose_name = "Plano de revisão"
        verbose_name_plural = "Planos de revisão"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "name"),
                name="unique_review_plan_name_per_workshop",
            ),
        ]

    def __str__(self) -> str:
        return self.name
