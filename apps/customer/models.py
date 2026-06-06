from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.infrastructure.models import TimeStampedModel, Address
from apps.core.text_normalization import name_case, plate_case, sentence_case

from .vehicle_engine import VehicleEngine, normalize_vehicle_engine_choice
from .vehicle_fuel import VehicleFuel, normalize_vehicle_fuel_choice


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
    email = models.EmailField(verbose_name="Email", blank=False, null=False)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    # CAMPOS PESSOA FISICA
    rg = models.CharField(verbose_name="RG", max_length=9, blank=True, null=True)
    birth_date = models.DateField(verbose_name="Data de Nascimento", null=True, blank=True)
    sex = models.CharField(verbose_name="Sexo", max_length=1, choices=SEX_CHOICES, blank=True, null=True)

    # CAMPOS PESSOA JURÍDICA
    fantasy_name = models.CharField(verbose_name="Nome Fantasia", max_length=255, blank=True, null=True)
    state_registration = models.CharField(verbose_name="Inscrição Estadual", max_length=255, blank=True, null=True)
    municipal_registration = models.CharField(verbose_name="Inscrição Municipal", max_length=255, blank=True, null=True)
    foundation_date = models.DateField(verbose_name="Data de Fundação", blank=True, null=True)

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


class Vehicle(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="vehicles")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="vehicles")
    plate = models.CharField(verbose_name="Placa", max_length=20)
    brand = models.CharField(verbose_name="Marca", max_length=500)
    model = models.CharField(verbose_name="Modelo", max_length=500)
    year_fabrication = models.CharField(verbose_name="Ano de Fabricação", max_length=4)
    year_model = models.CharField(verbose_name="Ano do Modelo", max_length=4)
    color = models.CharField(verbose_name="Cor", max_length=30)
    fuel = models.CharField(verbose_name="Combustível", max_length=30, choices=VehicleFuel.choices, null=True, blank=True)
    km = models.PositiveIntegerField(verbose_name="Quilometragem", null=True, blank=True)
    engine = models.CharField(verbose_name="Motor", max_length=30, choices=VehicleEngine.choices, null=True, blank=True)
    type = models.CharField(verbose_name="Tipo", max_length=50, null=True, blank=True)
    renavam = models.CharField(verbose_name="Renavam", max_length=500, null=True, blank=True)
    chassi = models.CharField(verbose_name="Chassi", max_length=500, null=True, blank=True)

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
