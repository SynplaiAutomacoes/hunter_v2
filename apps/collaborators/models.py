from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from djmoney.models.fields import MoneyField
from djmoney.money import Money
from localflavor.br.models import BRCPFField
from phonenumber_field.modelfields import PhoneNumberField

from apps.core.infrastructure.models import TimeStampedModel
from apps.core.text_normalization import name_case, sentence_case


class WorkshopMember(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workshop_members",
    )
    workshop = models.ForeignKey(
        "workshops.Workshop",
        on_delete=models.CASCADE,
        related_name="members",
    )
    role = models.ForeignKey(
        "iam.WorkshopRole",
        on_delete=models.PROTECT,
        related_name="workshop_members",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Membro da Oficina"
        verbose_name_plural = "Membros da Oficina"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "workshop"),
                name="unique_user_workshop_member",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.workshop} ({self.role})"


class WorkshopCollaborator(TimeStampedModel):
    class Sex(models.TextChoices):
        MALE = "M", "Masculino"
        FEMALE = "F", "Feminino"
        OTHER = "O", "Outro"

    class CollaboratorType(models.TextChoices):
        ADMINISTRATIVE = "A", "Administrativo"
        PRODUCTIVE = "P", "Produtivo"

    class PaymentDayType(models.TextChoices):
        FIFTH_BUSINESS_DAY = "FIFTH_BUSINESS_DAY", "5o dia util"
        FIXED_DAY = "FIXED_DAY", "Data de pagamento"

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="collaborators")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="workshop_collaborator", null=True, blank=True)
    name = models.CharField(verbose_name="Nome", max_length=255)
    cpf = BRCPFField(verbose_name="CPF", null=False, blank=False)
    # TODO: Create specific field for RG
    rg = models.CharField(verbose_name="RG", max_length=9, blank=True, null=True)
    birth_date = models.DateField(verbose_name="Data de Nascimento", null=False, blank=False)
    sex = models.CharField(verbose_name="Sexo", max_length=1, choices=Sex.choices, blank=True)
    phone = PhoneNumberField(verbose_name="Telefone", blank=True)
    email = models.EmailField(verbose_name="E-mail", blank=True)
    position = models.CharField(verbose_name="Cargo", max_length=255, blank=True)
    salary = MoneyField(verbose_name="Salário", max_digits=14, decimal_places=2, null=False, blank=True)
    payment_day_type = models.CharField(verbose_name="Tipo de pagamento", max_length=32, choices=PaymentDayType.choices, default=PaymentDayType.FIFTH_BUSINESS_DAY)
    payment_day_of_month = models.PositiveSmallIntegerField(verbose_name="Dia do pagamento", null=True, blank=True)
    transport_allowance_daily = MoneyField(verbose_name="Vale Transporte Diário", max_digits=14, decimal_places=2, default=Decimal("0.00"), blank=True)
    admission_date = models.DateField(verbose_name="Data de Admissão", null=False, blank=False)
    termination_date = models.DateField(verbose_name="Data de Saída", null=True, blank=True)
    collaborator_type = models.CharField(verbose_name="Tipo", max_length=1, choices=CollaboratorType.choices, blank=False, null=False)
    receives_commission = models.BooleanField(verbose_name="Recebe Comissão", default=False)
    commission_percentage = models.DecimalField(verbose_name="Percentual de Comissão", max_digits=7, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(verbose_name="Ativo", default=True)
    system_access = models.BooleanField(verbose_name="Acesso ao Sistema", default=False)

    class Meta:
        verbose_name = "Colaborador da Oficina"
        verbose_name_plural = "Colaboradores da Oficina"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "cpf"),
                name="unique_collaborator_cpf_per_workshop",
            ),
            models.CheckConstraint(
                condition=Q(commission_percentage__isnull=True) | (Q(commission_percentage__gte=0) & Q(commission_percentage__lte=1)),
                name="collaborator_commission_percentage_range",
            ),
            models.CheckConstraint(
                condition=Q(payment_day_type="FIFTH_BUSINESS_DAY", payment_day_of_month__isnull=True) | Q(payment_day_type="FIXED_DAY", payment_day_of_month__gte=1, payment_day_of_month__lte=31),
                name="collaborator_payment_day_configuration_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        if self.name:
            self.name = name_case(self.name)
        if self.position:
            self.position = sentence_case(self.position)
        if self.salary is None:
            self.salary = Money(0, "BRL")
        if self.transport_allowance_daily is None:
            self.transport_allowance_daily = Money(0, "BRL")
        super().save(*args, **kwargs)

    @property
    def salary_amount(self) -> Decimal:
        return Decimal(str(getattr(self.salary, "amount", 0) or 0))

    @property
    def transport_allowance_daily_amount(self) -> Decimal:
        return Decimal(str(getattr(self.transport_allowance_daily, "amount", 0) or 0))

    def get_payment_reference_date(self, *, reference_date: date | None = None) -> date:
        base_date = reference_date or timezone.localdate()
        if base_date.month == 12:
            return date(base_date.year + 1, 1, 1)
        return date(base_date.year, base_date.month + 1, 1)

    def get_due_date_for_payment_month(self, *, payment_month: date) -> date:
        """Compute the due date inside the given payment month (year/month)."""
        target_month = date(payment_month.year, payment_month.month, 1)
        if self.payment_day_type == self.PaymentDayType.FIXED_DAY and self.payment_day_of_month:
            last_day = calendar.monthrange(target_month.year, target_month.month)[1]
            return date(target_month.year, target_month.month, min(self.payment_day_of_month, last_day))

        business_days = 0
        day = 1
        while True:
            current_date = date(target_month.year, target_month.month, day)
            if current_date.weekday() < 5:
                business_days += 1
                if business_days == 5:
                    return current_date
            day += 1

    def get_due_date_for_reference(self, *, reference_date: date | None = None) -> date:
        target_month = self.get_payment_reference_date(reference_date=reference_date)
        return self.get_due_date_for_payment_month(payment_month=target_month)

    def get_legacy_same_month_due_date_for_reference(self, *, reference_date: date | None = None) -> date:
        """Previous rule: due date inside the competence month (not the following month)."""
        base_date = reference_date or timezone.localdate()
        return self.get_due_date_for_payment_month(payment_month=date(base_date.year, base_date.month, 1))


class CollaboratorBenefit(TimeStampedModel):
    collaborator = models.ForeignKey("collaborators.WorkshopCollaborator", on_delete=models.CASCADE, related_name="benefits")
    name = models.CharField(verbose_name="Nome do benefício", max_length=255)
    description = models.TextField(verbose_name="Descrição", blank=True)
    monthly_amount = MoneyField(verbose_name="Valor mensal", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    budget_plan = models.ForeignKey("finance.FinancialGroup", verbose_name="Plano Orçamentário", on_delete=models.PROTECT, null=True, blank=True, related_name="collaborator_benefits")
    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Benefício do Colaborador"
        verbose_name_plural = "Benefícios do Colaborador"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.collaborator.name} - {self.name}"

    def save(self, *args: object, **kwargs: object) -> None:
        if self.name:
            self.name = sentence_case(self.name)
        if self.description:
            self.description = sentence_case(self.description)
        super().save(*args, **kwargs)


class CollaboratorPayroll(TimeStampedModel):
    class Status(models.TextChoices):
        FORECAST = "FORECAST", "Previsto"
        PARTIAL = "PARTIAL", "Parcial"
        PAID = "PAID", "Pago"

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="collaborator_payrolls")
    collaborator = models.ForeignKey("collaborators.WorkshopCollaborator", on_delete=models.CASCADE, related_name="payrolls")
    reference_year = models.PositiveIntegerField(verbose_name="Ano de referência")
    reference_month = models.PositiveSmallIntegerField(verbose_name="Mês de referência")
    due_date = models.DateField(verbose_name="Data prevista para pagamento")
    work_days = models.PositiveSmallIntegerField(verbose_name="Dias úteis", default=0)
    work_days_is_custom = models.BooleanField(verbose_name="Dias úteis personalizados", default=False)
    salary_amount = MoneyField(verbose_name="Salário", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    transport_allowance_amount = MoneyField(verbose_name="Vale Transporte", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    benefits_amount = MoneyField(verbose_name="Benefícios", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    commission_amount = MoneyField(verbose_name="Comissão", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_amount = MoneyField(verbose_name="Valor total", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    financial_movement = models.OneToOneField("finance.FinancialMovement", verbose_name="Movimentação Financeira", on_delete=models.SET_NULL, related_name="collaborator_payroll", null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Folha do Colaborador"
        verbose_name_plural = "Folhas dos Colaboradores"
        ordering = ["-reference_year", "-reference_month", "-id"]
        constraints = [
            models.UniqueConstraint(fields=("collaborator", "reference_year", "reference_month"), name="unique_collaborator_payroll_reference"),
        ]
        indexes = [
            models.Index(fields=["workshop", "reference_year", "reference_month"], name="collab_payroll_ws_ref_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.collaborator.name} - {self.reference_month:02d}/{self.reference_year}"

    @staticmethod
    def _component_order(item) -> int:
        component = getattr(item, "payroll_component", None)
        order = {
            "SALARY": 0,
            "BENEFIT": 1,
            "TRANSPORT": 2,
            "COMMISSION": 3,
        }
        return order.get(str(component or ""), 99)

    def get_financial_movements(self) -> list:
        movements = list(self.financial_movements.all())
        if movements:
            return sorted(movements, key=lambda movement: (self._component_order(movement), movement.pk or 0))
        if self.financial_movement is not None:
            return [self.financial_movement]
        return []

    @property
    def primary_financial_movement(self):
        movements = self.get_financial_movements()
        return movements[0] if movements else None

    @property
    def has_split_financial_movements(self) -> bool:
        return bool(self.financial_movements.exists())

    @property
    def is_reconciled(self) -> bool:
        movements = self.get_financial_movements()
        return bool(movements) and all(movement.is_reconciled for movement in movements)

    @property
    def paid_amount(self) -> Money:
        movements = self.get_financial_movements()
        if not movements:
            return Money(0, "BRL")

        paid_total = sum((Decimal(str(movement.amount.amount or 0)) for movement in movements if movement.is_paid), start=Decimal("0.00"))
        return Money(paid_total, "BRL")

    @property
    def status(self) -> str:
        movements = self.get_financial_movements()
        if not movements:
            return self.Status.FORECAST

        paid_count = sum(1 for movement in movements if movement.is_paid)
        if paid_count == len(movements):
            return self.Status.PAID
        if paid_count > 0:
            return self.Status.PARTIAL
        return self.Status.FORECAST

    @property
    def status_label(self) -> str:
        labels = {
            self.Status.FORECAST: "Não Pago",
            self.Status.PARTIAL: "Parcial",
            self.Status.PAID: "Pago",
        }
        return labels.get(self.status, str(self.Status(self.status).label))


class CollaboratorPayrollItem(TimeStampedModel):
    class ItemType(models.TextChoices):
        SALARY = "SALARY", "Salário"
        TRANSPORT = "TRANSPORT", "Vale Transporte"
        BENEFIT = "BENEFIT", "Benefício"
        COMMISSION = "COMMISSION", "Comissão"

    payroll = models.ForeignKey("collaborators.CollaboratorPayroll", on_delete=models.CASCADE, related_name="items")
    item_type = models.CharField(verbose_name="Tipo", max_length=32, choices=ItemType.choices)
    title = models.CharField(verbose_name="Título", max_length=255)
    description = models.TextField(verbose_name="Descrição", blank=True)
    amount = MoneyField(verbose_name="Valor", max_digits=14, decimal_places=2, default=Decimal("0.00"))

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Item da Folha do Colaborador"
        verbose_name_plural = "Itens da Folha do Colaborador"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.payroll} - {self.title}"


class CollaboratorCommissionEntry(TimeStampedModel):
    class Status(models.TextChoices):
        FORECAST = "FORECAST", "Previsto"
        PAID = "PAID", "Pago"

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="collaborator_commission_entries")
    collaborator = models.ForeignKey("collaborators.WorkshopCollaborator", on_delete=models.CASCADE, related_name="commission_entries")
    workorder = models.ForeignKey("workorder.WorkOrder", on_delete=models.CASCADE, related_name="commission_entries")
    payroll = models.ForeignKey("collaborators.CollaboratorPayroll", on_delete=models.SET_NULL, related_name="commission_entries", null=True, blank=True)
    reference_year = models.PositiveIntegerField(verbose_name="Ano de referência")
    reference_month = models.PositiveSmallIntegerField(verbose_name="Mês de referência")
    percentage = models.DecimalField(verbose_name="Percentual", max_digits=7, decimal_places=6)
    base_amount = MoneyField(verbose_name="Base de cálculo", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    commission_amount = MoneyField(verbose_name="Valor da comissão", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(verbose_name="Status", max_length=16, choices=Status.choices, default=Status.FORECAST)
    paid_at = models.DateField(verbose_name="Pago em", null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Lançamento de Comissão do Colaborador"
        verbose_name_plural = "Lançamentos de Comissão do Colaborador"
        ordering = ["-reference_year", "-reference_month", "-id"]
        constraints = [
            models.UniqueConstraint(fields=("collaborator", "workorder"), name="unique_collaborator_commission_workorder"),
        ]
        indexes = [
            models.Index(fields=["collaborator", "reference_year", "reference_month"], name="collab_comm_ref_idx"),
            models.Index(fields=["workshop", "reference_year", "reference_month"], name="collab_comm_ws_ref_idx"),
        ]

    def __str__(self) -> str:
        return f"Comissão {self.collaborator.name} - OS #{self.workorder.pk}"

    @property
    def percentage_display(self) -> str:
        percentage_value = (Decimal(str(self.percentage or 0)) * Decimal("100")).quantize(Decimal("0.01"))
        return f"{str(percentage_value).replace('.', ',')}%"
