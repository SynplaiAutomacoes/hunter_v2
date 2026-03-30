from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.models import TimeStampedModel


class AppointmentStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Agendado"
    COMPLETED = "completed", "Concluido"
    CANCELLED = "cancelled", "Cancelado"


class Appointment(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="appointments")
    customer = models.ForeignKey("customer.Customer", verbose_name="Cliente", on_delete=models.PROTECT, related_name="appointments", null=True, blank=True)
    vehicle = models.ForeignKey("customer.Vehicle", verbose_name="Veiculo", on_delete=models.PROTECT, related_name="appointments", null=True, blank=True)
    guest_customer_name = models.CharField(verbose_name="Nome do cliente", max_length=255, blank=True, default="")
    guest_customer_phone = PhoneNumberField(verbose_name="Telefone do cliente", blank=True, default="")
    title = models.CharField(verbose_name="Titulo", max_length=120)
    starts_at = models.DateTimeField(verbose_name="Data e hora de entrada")
    ends_at = models.DateTimeField(verbose_name="Data e hora de saida")
    block_color = models.CharField(verbose_name="Cor do bloco", max_length=7, default="#0ea5e9")
    alert_customer = models.BooleanField(verbose_name="Alertar cliente", default=False)
    notes = models.TextField(verbose_name="Observacoes", blank=True, default="")
    status = models.CharField(verbose_name="Status", max_length=20, choices=AppointmentStatus.choices, default=AppointmentStatus.SCHEDULED)
    budget = models.ForeignKey("budget.Budget", verbose_name="Orcamento vinculado", on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments")
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de servico vinculada", on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments")

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
        if self.customer_id and self.customer:
            return self.customer.name
        return self.guest_customer_name or "Cliente nao cadastrado"

    @property
    def display_customer_phone(self) -> str:
        if self.customer_id and self.customer:
            return str(self.customer.phone or "")
        return str(self.guest_customer_phone or "")

    @property
    def display_vehicle_label(self) -> str:
        return str(self.vehicle) if self.vehicle_id and self.vehicle else "Sem veiculo vinculado"

    def clean(self) -> None:
        errors: dict[str, list[str]] = {}

        workshop_id = self.__dict__.get("workshop_id")
        customer_id = self.__dict__.get("customer_id")
        vehicle_id = self.__dict__.get("vehicle_id")
        budget_id = self.__dict__.get("budget_id")
        workorder_id = self.__dict__.get("workorder_id")

        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            errors.setdefault("ends_at", []).append("A data de saida deve ser maior que a data de entrada.")

        if not customer_id:
            if not self.guest_customer_name.strip():
                errors.setdefault("guest_customer_name", []).append("Informe o nome do cliente quando ele nao estiver cadastrado.")
            if not str(self.guest_customer_phone or "").strip():
                errors.setdefault("guest_customer_phone", []).append("Informe o telefone do cliente quando ele nao estiver cadastrado.")

        if vehicle_id and not customer_id:
            errors.setdefault("vehicle", []).append("Selecione um cliente cadastrado para vincular um veiculo.")

        if customer_id and vehicle_id and self.vehicle.customer_id != customer_id:
            errors.setdefault("vehicle", []).append("O veiculo deve pertencer ao cliente selecionado.")

        if workshop_id and customer_id and self.customer.workshop_id != workshop_id:
            errors.setdefault("customer", []).append("Cliente invalido para a oficina ativa.")

        if workshop_id and vehicle_id and self.vehicle.workshop_id != workshop_id:
            errors.setdefault("vehicle", []).append("Veiculo invalido para a oficina ativa.")

        if budget_id:
            if workshop_id and self.budget.workshop_id != workshop_id:
                errors.setdefault("budget", []).append("Orcamento invalido para a oficina ativa.")

            if customer_id and self.budget.customer_id and self.budget.customer_id != customer_id:
                errors.setdefault("budget", []).append("O orcamento deve pertencer ao cliente selecionado.")

            if vehicle_id and self.budget.vehicle_id and self.budget.vehicle_id != vehicle_id:
                errors.setdefault("budget", []).append("O orcamento deve pertencer ao veiculo selecionado.")

        if workorder_id:
            if workshop_id and self.workorder.workshop_id != workshop_id:
                errors.setdefault("workorder", []).append("Ordem de servico invalida para a oficina ativa.")

            workorder_budget = getattr(self.workorder, "budget", None)
            if self.budget and workorder_budget and workorder_budget.pk != self.budget.pk:
                errors.setdefault("workorder", []).append("A ordem de servico deve ser do mesmo orcamento vinculado.")

            if customer_id and workorder_budget and workorder_budget.customer_id and workorder_budget.customer_id != customer_id:
                errors.setdefault("workorder", []).append("A ordem de servico deve pertencer ao cliente selecionado.")

            if vehicle_id and workorder_budget and workorder_budget.vehicle_id and workorder_budget.vehicle_id != vehicle_id:
                errors.setdefault("workorder", []).append("A ordem de servico deve pertencer ao veiculo selecionado.")

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
                errors.setdefault("vehicle", []).append("Ja existe agendamento para este veiculo nesse horario.")

        if errors:
            raise ValidationError(errors)
