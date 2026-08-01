from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.infrastructure.models import TimeStampedModel
from apps.customer.vehicle_engine import VehicleEngine, normalize_vehicle_engine_choice
from apps.customer.vehicle_fuel import VehicleFuel, normalize_vehicle_fuel_choice


ALERT_LEAD_TIME_CHOICES: list[tuple[int, str]] = [
    (30, "30 minutos"),
    (60, "1 hora"),
    (120, "2 horas"),
    (180, "3 horas"),
    (300, "5 horas"),
    (1440, "1 dia"),
    (2880, "2 dias"),
    (10080, "1 semana"),
]

DEFAULT_ALERT_LEAD_TIMES: list[int] = [60, 1440, 2880]


def default_alert_lead_times() -> list[int]:
    return list(DEFAULT_ALERT_LEAD_TIMES)


def _digits_only(value: object) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def _normalize_upper_text(value: object) -> str:
    return str(value or "").strip().upper()


def _format_cpf(value: object) -> str:
    digits = _digits_only(value)
    if len(digits) != 11:
        return digits
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


class AppointmentStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Agendado"
    COMPLETED = "completed", "Concluído"
    CANCELLED = "cancelled", "Cancelado"


class Appointment(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="appointments")
    customer = models.ForeignKey("customer.Customer", verbose_name="Cliente", on_delete=models.PROTECT, related_name="appointments", null=True, blank=True)
    vehicle = models.ForeignKey("customer.Vehicle", verbose_name="Veículo", on_delete=models.PROTECT, related_name="appointments", null=True, blank=True)
    guest_customer_name = models.CharField(verbose_name="Nome do cliente", max_length=255, blank=True, default="")
    guest_customer_cpf = models.CharField(verbose_name="CPF do cliente", max_length=14, blank=True, default="")
    guest_customer_phone = PhoneNumberField(verbose_name="Telefone do cliente", blank=True, default="")
    guest_vehicle_plate = models.CharField(verbose_name="Placa do veículo", max_length=20, blank=True, default="")
    guest_vehicle_brand = models.CharField(verbose_name="Marca do veículo", max_length=500, blank=True, default="")
    guest_vehicle_model = models.CharField(verbose_name="Modelo do veículo", max_length=500, blank=True, default="")
    guest_vehicle_year_fabrication = models.CharField(verbose_name="Ano de fabricação", max_length=4, blank=True, default="")
    guest_vehicle_year_model = models.CharField(verbose_name="Ano do modelo", max_length=4, blank=True, default="")
    guest_vehicle_engine = models.CharField(verbose_name="Motorização", max_length=30, choices=VehicleEngine.choices, blank=True, default="")
    guest_vehicle_fuel = models.CharField(verbose_name="Combustível", max_length=30, choices=VehicleFuel.choices, blank=True, default="")
    title = models.CharField(verbose_name="Título", max_length=120)
    starts_at = models.DateTimeField(verbose_name="Data e hora de entrada")
    ends_at = models.DateTimeField(verbose_name="Data e hora de saída")
    block_color = models.CharField(verbose_name="Cor do bloco", max_length=7, default="#0ea5e9")
    alert_customer = models.BooleanField(verbose_name="Alertar cliente", default=True)
    alert_lead_times = ArrayField(
        models.PositiveIntegerField(choices=ALERT_LEAD_TIME_CHOICES),
        verbose_name="Antecedência do alerta",
        blank=True,
        default=default_alert_lead_times,
        help_text="Minutos antes do início do agendamento para enviar o alerta. É possível selecionar mais de uma opção.",
    )
    notes = models.TextField(verbose_name="Observações", blank=True, default="")
    status = models.CharField(verbose_name="Status", max_length=20, choices=AppointmentStatus.choices, default=AppointmentStatus.SCHEDULED)
    budget = models.ForeignKey("budget.Budget", verbose_name="Orçamento vinculado", on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments")
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de serviço vinculada", on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments")

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Agendamento"
        verbose_name_plural = "Agendamentos"
        indexes = [
            models.Index(fields=["workshop", "starts_at"]),
            models.Index(fields=["workshop", "ends_at"]),
            models.Index(fields=["workshop", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} - {self.display_customer_name}"

    @property
    def display_customer_name(self) -> str:
        if getattr(self, "customer_id", None) and self.customer:
            return self.customer.name
        return self.guest_customer_name or "Cliente não cadastrado"

    @property
    def display_customer_phone(self) -> str:
        if getattr(self, "customer_id", None) and self.customer:
            return str(self.customer.phone or "")
        return str(self.guest_customer_phone or "")

    @property
    def display_customer_cpf(self) -> str:
        if getattr(self, "customer_id", None) and self.customer:
            return str(self.customer.cpf_or_cnpj_formatted or "")
        return _format_cpf(self.guest_customer_cpf)

    @property
    def display_vehicle_label(self) -> str:
        if getattr(self, "vehicle_id", None) and self.vehicle:
            return str(self.vehicle)

        vehicle_parts = [self.guest_vehicle_plate]
        brand_model = " ".join(part for part in [self.guest_vehicle_brand, self.guest_vehicle_model] if part)
        if brand_model:
            vehicle_parts.append(brand_model)

        return " - ".join(part for part in vehicle_parts if part) or "Sem veículo vinculado"

    def _normalize_guest_fields(self) -> None:
        self.guest_customer_name = _normalize_upper_text(self.guest_customer_name)
        self.guest_customer_cpf = _digits_only(self.guest_customer_cpf)[:11]
        self.guest_customer_phone = str(self.guest_customer_phone or "").strip()
        self.guest_vehicle_plate = _normalize_upper_text(self.guest_vehicle_plate)
        self.guest_vehicle_brand = _normalize_upper_text(self.guest_vehicle_brand)
        self.guest_vehicle_model = _normalize_upper_text(self.guest_vehicle_model)
        self.guest_vehicle_year_fabrication = str(self.guest_vehicle_year_fabrication or "").strip()
        self.guest_vehicle_year_model = str(self.guest_vehicle_year_model or "").strip()
        raw_guest_vehicle_engine = str(self.guest_vehicle_engine or "").strip()
        normalized_guest_vehicle_engine = normalize_vehicle_engine_choice(raw_guest_vehicle_engine)
        if not raw_guest_vehicle_engine or normalized_guest_vehicle_engine:
            self.guest_vehicle_engine = normalized_guest_vehicle_engine
        else:
            self.guest_vehicle_engine = _normalize_upper_text(self.guest_vehicle_engine)
        self.guest_vehicle_fuel = normalize_vehicle_fuel_choice(self.guest_vehicle_fuel)

    def clean(self) -> None:
        skip_guest_vehicle_engine_required_validation = bool(getattr(self, "_skip_guest_vehicle_engine_required_validation", False))
        raw_guest_vehicle_engine = str(self.guest_vehicle_engine or "").strip()
        normalized_guest_vehicle_engine = normalize_vehicle_engine_choice(raw_guest_vehicle_engine)
        raw_guest_vehicle_fuel = str(self.guest_vehicle_fuel or "").strip()
        normalized_guest_vehicle_fuel = normalize_vehicle_fuel_choice(raw_guest_vehicle_fuel)
        self._normalize_guest_fields()
        guest_validation_done = bool(getattr(self, "_guest_validation_done", False))
        errors: dict[str, list[str]] = {}

        workshop_id = self.__dict__.get("workshop_id")
        customer_id = self.__dict__.get("customer_id")
        vehicle_id = self.__dict__.get("vehicle_id")
        budget_id = self.__dict__.get("budget_id")
        workorder_id = self.__dict__.get("workorder_id")
        customer = self.customer if customer_id else None
        vehicle = self.vehicle if vehicle_id else None
        budget = self.budget if budget_id else None
        workorder = self.workorder if workorder_id else None

        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            errors.setdefault("ends_at", []).append("A data de saída deve ser maior que a data de entrada.")

        if not customer_id and not guest_validation_done:
            if not self.guest_customer_name.strip():
                errors.setdefault("guest_customer_name", []).append("Informe o nome do cliente quando ele não estiver cadastrado.")
            if len(_digits_only(self.guest_customer_cpf)) != 11:
                errors.setdefault("guest_customer_cpf", []).append("Informe o CPF do cliente quando ele não estiver cadastrado.")
            if not str(self.guest_customer_phone or "").strip():
                errors.setdefault("guest_customer_phone", []).append("Informe o telefone do cliente quando ele não estiver cadastrado.")
            if not self.guest_vehicle_plate.strip():
                errors.setdefault("guest_vehicle_plate", []).append("Informe a placa do veículo quando o cliente não estiver cadastrado.")
            if not self.guest_vehicle_brand.strip():
                errors.setdefault("guest_vehicle_brand", []).append("Informe a marca do veículo quando o cliente não estiver cadastrado.")
            if not self.guest_vehicle_model.strip():
                errors.setdefault("guest_vehicle_model", []).append("Informe o modelo do veículo quando o cliente não estiver cadastrado.")
            if not self.guest_vehicle_year_fabrication.strip():
                errors.setdefault("guest_vehicle_year_fabrication", []).append("Informe o ano de fabricação do veículo quando o cliente não estiver cadastrado.")
            if not self.guest_vehicle_year_model.strip():
                errors.setdefault("guest_vehicle_year_model", []).append("Informe o ano do modelo do veículo quando o cliente não estiver cadastrado.")
            if raw_guest_vehicle_engine and not normalized_guest_vehicle_engine:
                errors.setdefault("guest_vehicle_engine", []).append("Selecione uma motorização válida.")
            elif not self.guest_vehicle_engine.strip() and not skip_guest_vehicle_engine_required_validation:
                errors.setdefault("guest_vehicle_engine", []).append("Informe a motorização do veículo quando o cliente não estiver cadastrado.")
            if raw_guest_vehicle_fuel and not normalized_guest_vehicle_fuel:
                errors.setdefault("guest_vehicle_fuel", []).append("Selecione um combustível válido.")
            elif not self.guest_vehicle_fuel.strip():
                errors.setdefault("guest_vehicle_fuel", []).append("Informe o combustível do veículo quando o cliente não estiver cadastrado.")

        if vehicle_id and not customer_id:
            errors.setdefault("vehicle", []).append("Selecione um cliente cadastrado para vincular um veículo.")

        if customer_id and vehicle and vehicle.customer_id != customer_id:
            errors.setdefault("vehicle", []).append("O veículo deve pertencer ao cliente selecionado.")

        if workshop_id and customer and customer.workshop_id != workshop_id:
            errors.setdefault("customer", []).append("Cliente inválido para a oficina ativa.")

        if workshop_id and vehicle and vehicle.workshop_id != workshop_id:
            errors.setdefault("vehicle", []).append("Veículo inválido para a oficina ativa.")

        if budget:
            if workshop_id and budget.workshop_id != workshop_id:
                errors.setdefault("budget", []).append("Orçamento inválido para a oficina ativa.")

            if customer_id and budget.customer_id and budget.customer_id != customer_id:
                errors.setdefault("budget", []).append("O orçamento deve pertencer ao cliente selecionado.")

            if vehicle_id and budget.vehicle_id and budget.vehicle_id != vehicle_id:
                errors.setdefault("budget", []).append("O orçamento deve pertencer ao veículo selecionado.")

        if workorder:
            if workshop_id and workorder.workshop_id != workshop_id:
                errors.setdefault("workorder", []).append("Ordem de serviço inválida para a oficina ativa.")

            workorder_budget = getattr(workorder, "budget", None)
            if budget and workorder_budget and workorder_budget.pk != budget.pk:
                errors.setdefault("workorder", []).append("A ordem de serviço deve ser do mesmo orçamento vinculado.")

            if customer_id and workorder_budget and workorder_budget.customer_id and workorder_budget.customer_id != customer_id:
                errors.setdefault("workorder", []).append("A ordem de serviço deve pertencer ao cliente selecionado.")

            if vehicle_id and workorder_budget and workorder_budget.vehicle_id and workorder_budget.vehicle_id != vehicle_id:
                errors.setdefault("workorder", []).append("A ordem de serviço deve pertencer ao veículo selecionado.")

        if workshop_id and vehicle_id and self.starts_at and self.ends_at and self.status == AppointmentStatus.SCHEDULED:
            overlapping = (
                Appointment.objects.filter(
                    workshop_id=workshop_id,
                    vehicle_id=vehicle_id,
                    status=AppointmentStatus.SCHEDULED,
                    starts_at__lt=self.ends_at,
                    ends_at__gt=self.starts_at,
                )
                .exclude(pk=self.pk)
                .exists()
            )

            if overlapping:
                errors.setdefault("vehicle", []).append("Já existe agendamento para este veículo nesse horário.")

        if errors:
            raise ValidationError(errors)

    def save(self, *args: object, **kwargs: object) -> None:
        self._normalize_guest_fields()
        return super().save(*args, **kwargs)
