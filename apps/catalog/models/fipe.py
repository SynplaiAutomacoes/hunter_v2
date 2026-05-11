from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

from apps.core.models import TimeStampedModel


class FipeVehicleType(models.TextChoices):
    CARROS = "carros", "Carros"
    MOTOS = "motos", "Motos"
    CAMINHOES = "caminhoes", "Caminhões"


class FipeVehicleBrand(TimeStampedModel):
    vehicle_type = models.CharField(verbose_name="Tipo de veículo", max_length=20, choices=FipeVehicleType.choices, default=FipeVehicleType.CARROS)
    external_id = models.CharField(verbose_name="ID externo", max_length=50)
    name = models.CharField(verbose_name="Marca", max_length=255)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        verbose_name = "Marca FIPE"
        verbose_name_plural = "Marcas FIPE"
        constraints = [models.UniqueConstraint(fields=("vehicle_type", "external_id"), name="unique_catalog_fipe_brand_per_type")]
        ordering = ("name",)

    if TYPE_CHECKING:
        models: models.Manager["FipeVehicleModel"]

    def __str__(self) -> str:
        return self.name


class FipeVehicleModel(TimeStampedModel):
    brand = models.ForeignKey(FipeVehicleBrand, on_delete=models.CASCADE, related_name="models")
    vehicle_type = models.CharField(verbose_name="Tipo de veículo", max_length=20, choices=FipeVehicleType.choices, default=FipeVehicleType.CARROS)
    external_id = models.CharField(verbose_name="ID externo", max_length=50)
    name = models.CharField(verbose_name="Modelo", max_length=255)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        verbose_name = "Modelo FIPE"
        verbose_name_plural = "Modelos FIPE"
        constraints = [models.UniqueConstraint(fields=("vehicle_type", "brand", "external_id"), name="unique_catalog_fipe_model_per_brand")]
        ordering = ("name",)

    if TYPE_CHECKING:
        fuel_caches: models.Manager["FipeModelFuelCache"]

    def __str__(self) -> str:
        return self.name


class FipeModelFuelCache(TimeStampedModel):
    model = models.ForeignKey(FipeVehicleModel, on_delete=models.CASCADE, related_name="fuel_caches")
    vehicle_type = models.CharField(verbose_name="Tipo de veículo", max_length=20, choices=FipeVehicleType.choices, default=FipeVehicleType.CARROS)
    fuel_values = models.JSONField(verbose_name="Combustíveis", default=list, blank=True)
    source_year_count = models.PositiveIntegerField(verbose_name="Quantidade de anos na origem", default=0)
    last_synced_at = models.DateTimeField(verbose_name="Última sincronização", null=True, blank=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        verbose_name = "Cache de combustível FIPE"
        verbose_name_plural = "Caches de combustível FIPE"
        constraints = [models.UniqueConstraint(fields=("vehicle_type", "model"), name="unique_catalog_fipe_fuel_cache_per_model")]

    def __str__(self) -> str:
        return f"{self.model} ({self.vehicle_type})"


class FipeSyncState(TimeStampedModel):
    scope = models.CharField(verbose_name="Escopo", max_length=100, unique=True)
    access_count = models.PositiveIntegerField(verbose_name="Contador de acessos", default=0)
    last_full_sync_at = models.DateTimeField(verbose_name="Última sincronização completa", null=True, blank=True)
    last_sync_started_at = models.DateTimeField(verbose_name="Último início de sincronização", null=True, blank=True)
    sync_in_progress = models.BooleanField(verbose_name="Sincronização em andamento", default=False)
    last_sync_error = models.TextField(verbose_name="Último erro de sincronização", blank=True, default="")

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        verbose_name = "Estado de sincronização FIPE"
        verbose_name_plural = "Estados de sincronização FIPE"

    def __str__(self) -> str:
        return self.scope
