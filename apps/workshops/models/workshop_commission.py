from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.infrastructure.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop


class WorkshopCommissionSettings(TimeStampedModel):
    """Configuração vigente de comissão por OS da oficina (OneToOne com a oficina)."""

    workshop = models.OneToOneField(Workshop, on_delete=models.CASCADE, related_name="commission_settings")
    workorder_commission_enabled = models.BooleanField(verbose_name="Comissão por OS habilitada", default=False)
    workorder_commission_percentage = models.DecimalField(
        verbose_name="Percentual da Comissão por OS",
        max_digits=7,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Configuração de Comissão da Oficina"
        verbose_name_plural = "Configurações de Comissão da Oficina"

    def __str__(self) -> str:
        return f"Comissão por OS - {self.workshop.name}"

    @property
    def resolved_workorder_commission_percentage(self):
        return self.workorder_commission_percentage or 0

    def clean(self) -> None:
        super().clean()
        if self.workorder_commission_enabled and self.workorder_commission_percentage is None:
            raise ValidationError({"workorder_commission_percentage": "Informe o percentual para habilitar a comissão por OS."})