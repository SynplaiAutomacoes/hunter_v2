from __future__ import annotations

from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from apps.catalog.kit_applications import KitApplicationsTableValue, build_kit_application_label, build_kit_applications_summary, build_kit_application_preview_lines, build_kit_applications_table_value, build_powertrain_display
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop


class Kit(TimeStampedModel):
    class ServicePricingMode(models.TextChoices):
        BY_DURATION = "by_duration", "Valor de venda por duração"
        INSERTED_VALUE = "inserted_value", "Valor de venda inserido"

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

    total_price = MoneyField(verbose_name="Preço Total", max_digits=14, decimal_places=2, default=0.00)
    total_duration = models.DurationField(verbose_name="Duração Total", null=True, blank=True)
    service_pricing_mode = models.CharField(
        verbose_name="Modo de precificação de serviços",
        max_length=20,
        choices=ServicePricingMode.choices,
        default=ServicePricingMode.BY_DURATION,
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

    def ordered_applications(self) -> list[KitApplication]:
        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("applications")
        applications = list(prefetched) if prefetched is not None else list(self.applications.all())
        return sorted(applications, key=lambda application: application.pk or 0)

    @property
    def applications_summary(self) -> str:
        return build_kit_applications_summary(self.ordered_applications())

    def application_preview_lines(self, *, limit: int = 3) -> list[str]:
        return build_kit_application_preview_lines(self.ordered_applications(), limit=limit)

    def applications_table_value(self, *, preview_limit: int = 2) -> KitApplicationsTableValue:
        return build_kit_applications_table_value(self.ordered_applications(), preview_limit=preview_limit)

    @property
    def is_used(self) -> bool:
        # Verifica se já foi usado em orçamentos ou ordens de serviço
        if self.budgetitem_set.exists():
            return True
        if self.workorderitem_set.exists():
            return True
        return False


class KitApplication(TimeStampedModel):
    kit = models.ForeignKey(Kit, on_delete=models.CASCADE, related_name="applications")
    brand = models.CharField(verbose_name="Marca", max_length=100)
    model = models.CharField(verbose_name="Modelo", max_length=120)
    engine = models.CharField(verbose_name="Motor", max_length=60)
    fuel = models.CharField(verbose_name="Combustível", max_length=30)
    year_start = models.PositiveSmallIntegerField(verbose_name="Ano inicial", validators=[MinValueValidator(1900), MaxValueValidator(2100)])
    year_end = models.PositiveSmallIntegerField(verbose_name="Ano final", validators=[MinValueValidator(1900), MaxValueValidator(2100)])

    class Meta:
        verbose_name = "Aplicação do Kit"
        verbose_name_plural = "Aplicações do Kit"
        constraints = [
            models.UniqueConstraint(
                fields=("kit", "brand", "model", "engine", "fuel", "year_start", "year_end"),
                name="unique_kit_application_per_kit",
            ),
            models.CheckConstraint(
                condition=Q(year_end__gte=F("year_start")),
                name="kit_application_valid_year_range",
            ),
        ]

    def __str__(self) -> str:
        return build_kit_application_label(self)

    @property
    def powertrain_display(self) -> str:
        return build_powertrain_display(self.engine, self.fuel)


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
    cost_price = MoneyField(verbose_name="Custo", max_digits=14, decimal_places=2, null=True, blank=True, default_currency="BRL")
    duration_selling_price = MoneyField(verbose_name="Valor de Venda por Duração", max_digits=14, decimal_places=2, null=True, blank=True, default_currency="BRL")
    selling_price = MoneyField(verbose_name="Valor de Venda", max_digits=14, decimal_places=2, null=True, blank=True, default_currency="BRL")

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

    @property
    def resolved_selling_price(self) -> Money:
        return self.selling_price if self.selling_price is not None else self.service.selling_price

    @property
    def resolved_cost_price(self) -> Money:
        return self.cost_price if self.cost_price is not None else self.service.suggested_cost

    @property
    def resolved_duration_selling_price(self) -> Money:
        return self.duration_selling_price if self.duration_selling_price is not None else self.service.selling_price
