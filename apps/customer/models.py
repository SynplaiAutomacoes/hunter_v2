from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.infrastructure.models import TimeStampedModel, Address
from apps.core.infrastructure.runtime_environment import is_production_environment
from apps.core.text_normalization import name_case, plate_case, sentence_case

from .vehicle_engine import VehicleEngine, normalize_vehicle_engine_choice
from .vehicle_fuel import VehicleFuel, normalize_vehicle_fuel_choice


def default_customer_accepts_messages() -> bool:
    """Prod liga recebimento por padrão; fora de produção nasce desligado."""
    return is_production_environment()


class Customer(TimeStampedModel, Address):
    SEX_CHOICES = [("M", "Masculino"), ("F", "Feminino"), ("O", "Outro")]

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="customers")

    customer_type = models.CharField(
        max_length=2,
        choices=[
            ("PF", "Pessoa Física"),
            ("PJ", "Pessoa Jurídica"),
        ],
        default="PF",
    )

    # CAMPOS COMUNS
    name = models.CharField(verbose_name="Nome", max_length=255, null=False, blank=False)
    cpf_or_cnpj = models.CharField(verbose_name="CPF/CNPJ", max_length=18, null=False, blank=False)
    phone = PhoneNumberField(verbose_name="Telefone", blank=True)
    email = models.EmailField(verbose_name="E-mail", blank=False, null=False)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)
    accepts_messages = models.BooleanField(
        verbose_name="Receber mensagens",
        default=default_customer_accepts_messages,
    )

    # CAMPOS PESSOA FISICA
    rg = models.CharField(verbose_name="RG", max_length=9, blank=True, null=True)
    birth_date = models.DateField(verbose_name="Data de nascimento", null=True, blank=True)
    sex = models.CharField(verbose_name="Sexo", max_length=1, choices=SEX_CHOICES, blank=True, null=True)

    # CAMPOS PESSOA JURÍDICA
    fantasy_name = models.CharField(verbose_name="Nome fantasia", max_length=255, blank=True, null=True)
    state_registration = models.CharField(verbose_name="Inscrição Estadual", max_length=255, blank=True, null=True)
    municipal_registration = models.CharField(verbose_name="Inscrição Municipal", max_length=255, blank=True, null=True)
    foundation_date = models.DateField(verbose_name="Data de fundação", blank=True, null=True)

    @property
    def full_address(self) -> str:
        return f"{self.logradouro}, {self.numero} - {self.cidade}/{self.estado}"

    @property
    def cpf_or_cnpj_formatted(self) -> str:
        value = "".join(filter(str.isdigit, self.cpf_or_cnpj))

        if len(value) == 11:  # CPF
            return f"{value[:3]}.{value[3:6]}.{value[6:9]}-{value[9:]}"
        elif len(value) == 14:  # CNPJ
            return f"{value[:2]}.{value[2:5]}.{value[5:8]}/{value[8:12]}-{value[12:]}"
        return self.cpf_or_cnpj

    def vehicles_count(self) -> str:
        cached_count = getattr(self, "vehicle_count", None)
        if cached_count is not None:
            return str(cached_count)
        return str(self.vehicles.count())

    if TYPE_CHECKING:
        vehicles: models.Manager["Vehicle"]

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        constraints = [models.UniqueConstraint(fields=("workshop", "cpf_or_cnpj"), name="unique_customer_document_per_workshop")]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        if self.name:
            self.name = name_case(self.name)
        if self.fantasy_name:
            self.fantasy_name = name_case(self.fantasy_name)
        if self.logradouro:
            self.logradouro = sentence_case(self.logradouro)
        if self.complemento:
            self.complemento = sentence_case(self.complemento)
        if self.bairro:
            self.bairro = sentence_case(self.bairro)
        if self.cidade:
            self.cidade = sentence_case(self.cidade)
        super().save(*args, **kwargs)


class OilForecastReason(models.TextChoices):
    BY_DAYS = "VALIDADE_POR_DIAS", "Validade por dias"
    BY_KM = "VALIDADE_POR_QUILOMETRAGEM", "Validade por quilometragem"


class MileageReadingSource(models.TextChoices):
    BUDGET = "budget", "Orçamento"
    WORKORDER_DELIVERY = "workorder_delivery", "Entrega da O.S."
    MANUAL = "manual", "Manual"


class Vehicle(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="vehicles")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="vehicles")
    plate = models.CharField(verbose_name="Placa", max_length=20)
    brand = models.CharField(verbose_name="Marca", max_length=500)
    model = models.CharField(verbose_name="Modelo", max_length=500)
    year_fabrication = models.CharField(verbose_name="Ano de fabricação", max_length=4)
    year_model = models.CharField(verbose_name="Ano do modelo", max_length=4)
    color = models.CharField(verbose_name="Cor", max_length=30)
    fuel = models.CharField(verbose_name="Combustível", max_length=30, choices=VehicleFuel.choices, null=True, blank=True)
    km = models.PositiveIntegerField(verbose_name="Quilometragem", null=True, blank=True)
    engine = models.CharField(verbose_name="Motor", max_length=30, choices=VehicleEngine.choices, null=True, blank=True)
    type = models.CharField(verbose_name="Tipo", max_length=50, null=True, blank=True)
    renavam = models.CharField(verbose_name="Renavam", max_length=500, null=True, blank=True)
    chassi = models.CharField(verbose_name="Chassi", max_length=500, null=True, blank=True)
    last_oil_change_date = models.DateField(verbose_name="Data da última troca de óleo", null=True, blank=True)
    last_oil_change_km = models.PositiveIntegerField(verbose_name="KM da última troca de óleo", null=True, blank=True)
    review_plan = models.ForeignKey(
        "workshops.ReviewPlan",
        verbose_name="Plano de revisão",
        on_delete=models.SET_NULL,
        related_name="vehicles",
        null=True,
        blank=True,
    )
    next_oil_change_date = models.DateField(verbose_name="Data prevista da próxima troca de óleo", null=True, blank=True)
    oil_forecast_reason = models.CharField(
        verbose_name="Motivo da previsão de troca de óleo",
        max_length=40,
        choices=OilForecastReason.choices,
        null=True,
        blank=True,
    )

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        verbose_name = "Veículo"
        verbose_name_plural = "Veículos"
        constraints = [models.UniqueConstraint(fields=("workshop", "plate"), name="unique_vehicle_plate_per_workshop")]

    def save(self, *args: object, **kwargs: object) -> None:
        if self.plate:
            self.plate = plate_case(self.plate)
        if self.brand:
            self.brand = sentence_case(self.brand)
        if self.model:
            self.model = sentence_case(self.model)
        if self.color:
            self.color = sentence_case(self.color)
        if self.type:
            self.type = sentence_case(self.type)
        if self.engine is not None:
            raw_engine = str(self.engine).strip()
            normalized_engine = normalize_vehicle_engine_choice(raw_engine)
            if not raw_engine or normalized_engine:
                self.engine = normalized_engine
        if self.fuel is not None:
            self.fuel = normalize_vehicle_fuel_choice(self.fuel) or ""
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.plate} - {self.model}"


class VehicleOilChange(TimeStampedModel):
    vehicle = models.ForeignKey(Vehicle, verbose_name="Veículo", on_delete=models.CASCADE, related_name="oil_changes")
    changed_at = models.DateField(verbose_name="Data da troca")
    odometer_km = models.PositiveIntegerField(verbose_name="Quilometragem da troca")
    review_plan = models.ForeignKey(
        "workshops.ReviewPlan",
        verbose_name="Plano de revisão",
        on_delete=models.SET_NULL,
        related_name="oil_changes",
        null=True,
        blank=True,
    )
    validity_days = models.PositiveIntegerField(verbose_name="Validade do óleo (dias)")
    validity_km = models.PositiveIntegerField(verbose_name="Validade do óleo (km)")
    budget = models.ForeignKey(
        "budget.Budget",
        verbose_name="Orçamento",
        on_delete=models.SET_NULL,
        related_name="oil_changes",
        null=True,
        blank=True,
    )
    workorder = models.ForeignKey(
        "workorder.WorkOrder",
        verbose_name="Ordem de serviço",
        on_delete=models.SET_NULL,
        related_name="oil_changes",
        null=True,
        blank=True,
    )

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        verbose_name = "Troca de óleo"
        verbose_name_plural = "Trocas de óleo"
        indexes = [
            models.Index(fields=["vehicle", "-changed_at"]),
            models.Index(fields=["workorder"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("workorder",),
                condition=models.Q(workorder__isnull=False),
                name="unique_oil_change_per_workorder",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.vehicle} @ {self.changed_at}"


class VehicleMileageReading(TimeStampedModel):
    vehicle = models.ForeignKey(Vehicle, verbose_name="Veículo", on_delete=models.CASCADE, related_name="mileage_readings")
    read_at = models.DateField(verbose_name="Data da leitura")
    odometer_km = models.PositiveIntegerField(verbose_name="Quilometragem")
    source = models.CharField(verbose_name="Origem da leitura", max_length=32, choices=MileageReadingSource.choices)
    budget = models.ForeignKey(
        "budget.Budget",
        verbose_name="Orçamento",
        on_delete=models.SET_NULL,
        related_name="mileage_readings",
        null=True,
        blank=True,
    )
    workorder = models.ForeignKey(
        "workorder.WorkOrder",
        verbose_name="Ordem de serviço",
        on_delete=models.SET_NULL,
        related_name="mileage_readings",
        null=True,
        blank=True,
    )

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        verbose_name = "Leitura de quilometragem"
        verbose_name_plural = "Leituras de quilometragem"
        indexes = [
            models.Index(fields=["vehicle", "read_at", "odometer_km"]),
        ]

    def __str__(self) -> str:
        return f"{self.vehicle} {self.odometer_km} km @ {self.read_at}"
