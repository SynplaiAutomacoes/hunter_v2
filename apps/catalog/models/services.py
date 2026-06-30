from __future__ import annotations

from django.db import models
from djmoney.models.fields import MoneyField

from apps.core.infrastructure.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop


class Service(TimeStampedModel):
    workshop = models.ForeignKey(
        Workshop,
        on_delete=models.CASCADE,
        related_name="services",
    )
    name = models.CharField(verbose_name="Serviço", max_length=255)
    description = models.TextField(verbose_name="Descrição", blank=True)

    duration = models.DurationField(verbose_name="Duração")

    suggested_cost = MoneyField(verbose_name="Custo do tempo do serviço", max_digits=14, decimal_places=2, null=True, blank=True)

    shipping = MoneyField(verbose_name="Frete", max_digits=14, decimal_places=2, null=True, blank=True)

    selling_price = MoneyField(verbose_name="Valor de Venda", max_digits=14, decimal_places=2)
    last_used_price = MoneyField(verbose_name="Ultimo Valor Utilizado", max_digits=14, decimal_places=2, null=True, blank=True)

    is_third_party = models.BooleanField(verbose_name="Serviço de Terceiro", default=False)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    @property
    def duration_display(self):
        if not self.duration:
            return "00:00"

        total_seconds = int(self.duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        return f"{hours:02d}h {minutes:02d}m"

    @property
    def is_used(self) -> bool:
        # Verifica se já foi usado em orçamentos ou ordens de serviço
        if self.budgetitem_set.exists():
            return True
        if self.workorderitem_set.exists():
            return True
        if self.budgetkititemoverride_set.exists():
            return True
        if self.workorderkititemoverride_set.exists():
            return True
        if self.service_kits.exists():
            return True
        return False

    class Meta:
        verbose_name = "Serviço"
        verbose_name_plural = "Serviços"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "name"),
                name="unique_service_name_per_workshop",
            ),
        ]

    def __str__(self) -> str:
        return self.name
