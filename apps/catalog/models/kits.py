from __future__ import annotations

from datetime import timedelta

from django.db import models

from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop


class Kit(TimeStampedModel):
    workshop = models.ForeignKey(
        Workshop,
        on_delete=models.CASCADE,
        related_name="kits",
    )

    name = models.CharField(verbose_name="Kit", max_length=255)
    description = models.TextField(verbose_name="Descrição", blank=True)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    products = models.ManyToManyField(
        Product,
        through="KitProduct",
        related_name="kits",
        blank=True,
    )
    services = models.ManyToManyField(
        Service,
        through="KitService",
        related_name="kits",
        blank=True,
    )

    class Meta:
        verbose_name = "Kit"
        verbose_name_plural = "Kits"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "name"),
                name="unique_kit_name_per_workshop",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class KitProduct(TimeStampedModel):
    kit = models.ForeignKey(Kit, on_delete=models.CASCADE, related_name="kit_products")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="product_kits")
    quantity = models.PositiveIntegerField(verbose_name="Quantidade", default=1)

    class Meta:
        verbose_name = "Item de Kit (Produto)"
        verbose_name_plural = "Itens de Kit (Produtos)"
        constraints = [
            models.UniqueConstraint(
                fields=("kit", "product"),
                name="unique_product_per_kit",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kit} - {self.product}"


class KitService(TimeStampedModel):
    kit = models.ForeignKey(Kit, on_delete=models.CASCADE, related_name="kit_services")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="service_kits")
    quantity = models.PositiveIntegerField(verbose_name="Quantidade", default=1)
    duration = models.DurationField(verbose_name="Duração", default=timedelta)

    class Meta:
        verbose_name = "Item de Kit (Serviço)"
        verbose_name_plural = "Itens de Kit (Serviços)"
        constraints = [
            models.UniqueConstraint(
                fields=("kit", "service"),
                name="unique_service_per_kit",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kit} - {self.service}"
