from __future__ import annotations

from django.db import models

from apps.core.infrastructure.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop


class OilType(TimeStampedModel):
    workshop = models.ForeignKey(
        Workshop,
        on_delete=models.CASCADE,
        related_name="oil_types",
    )
    name = models.CharField(verbose_name="Nome", max_length=255)
    validity_days = models.PositiveIntegerField(verbose_name="Validade do óleo (dias)")
    validity_km = models.PositiveIntegerField(verbose_name="Validade do óleo (km)")
    notification_lead_days = models.PositiveIntegerField(
        verbose_name="Antecedência da notificação (dias)",
        default=7,
    )
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    class Meta:
        verbose_name = "Tipo de óleo"
        verbose_name_plural = "Tipos de óleo"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "name"),
                name="unique_oil_type_name_per_workshop",
            ),
        ]

    def __str__(self) -> str:
        return self.name
