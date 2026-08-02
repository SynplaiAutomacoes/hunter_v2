from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from apps.core.infrastructure.models import TimeStampedModel
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshops import Workshop


class WorkshopCost(TimeStampedModel):
    class Month(models.IntegerChoices):
        JANUARY = 1, _("Janeiro")
        FEBRUARY = 2, _("Fevereiro")
        MARCH = 3, _("Março")
        APRIL = 4, _("Abril")
        MAY = 5, _("Maio")
        JUNE = 6, _("Junho")
        JULY = 7, _("Julho")
        AUGUST = 8, _("Agosto")
        SEPTEMBER = 9, _("Setembro")
        OCTOBER = 10, _("Outubro")
        NOVEMBER = 11, _("Novembro")
        DECEMBER = 12, _("Dezembro")

    workshop = models.ForeignKey(
        Workshop,
        on_delete=models.CASCADE,
        related_name="workshop_costs",
    )

    # --- Mês de Referência ---
    month = models.PositiveIntegerField(verbose_name="Mês", choices=Month.choices)
    year = models.PositiveIntegerField(verbose_name="Ano")

    # --- Mecânicos Produtivos ---
    mechanic_quantity = models.PositiveIntegerField(verbose_name="Qtd. mecânicos produtivos", validators=[MinValueValidator(0)])
    work_hours_per_day = models.DurationField(
        verbose_name="Horas de trabalho/dia",
        validators=[MinValueValidator(timedelta()), MaxValueValidator(timedelta(hours=24))],
        default=timedelta(hours=8),
        help_text="Máximo 24h",
    )
    work_days_per_month = models.IntegerField(
        verbose_name="Dias úteis/mês",
        validators=[MinValueValidator(0), MaxValueValidator(31)],
        default=22,
        help_text="Máximo 31 dias",
    )
    productivity_average = models.DecimalField(
        verbose_name="Produtividade média",
        max_digits=5,
        decimal_places=4,
        default=0.60,
        help_text="50% a 80%",
        validators=[MinValueValidator(0.5), MaxValueValidator(0.8)],
    )

    # --- Taxas e Impostos ---
    card_rate = models.DecimalField(verbose_name="Taxa cartão", max_digits=7, decimal_places=6, default=0, null=True, blank=True)
    tax_rate = models.DecimalField(verbose_name="Impostos", max_digits=7, decimal_places=6, default=0, null=True, blank=True)
    profit_margin = models.DecimalField(verbose_name="Margem de lucro", max_digits=7, decimal_places=6, default=0, null=True, blank=True)
    commission_rate = models.DecimalField(
        verbose_name="Comissão",
        max_digits=7,
        decimal_places=6,
        default=0,
        help_text="Máximo 10%",
        validators=[MinValueValidator(0), MaxValueValidator(0.1)],
        null=True,
        blank=True,
    )
    risk_coefficient = models.DecimalField(
        verbose_name="Coeficiente de risco",
        max_digits=3,
        decimal_places=2,
        default=1.00,
        validators=[MinValueValidator(1.0), MaxValueValidator(1.5)],
        help_text="1,00 a 1,20 para veículo popular, 1,20 a 1,40 para SUVs e 1,50 para premium, está relacionado ao risco da oficina.",
        null=True,
        blank=True,
    )

    # --- Metas e Indicadores (Inputs manuais) ---
    parts_purchase_cap = MoneyField(verbose_name="Teto compras peças", max_digits=14, decimal_places=2, null=True, blank=True)
    freight_cost = MoneyField(
        verbose_name="Frete",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    third_party_service_cap = MoneyField(verbose_name="Teto serviços terceiros", max_digits=14, decimal_places=2, null=True, blank=True)

    # --- Calculados (Armazenados para histórico, readonly no form) ---
    total_value = MoneyField(verbose_name="Valor total", max_digits=14, decimal_places=2, default=0, null=True, blank=True)
    total_monthly_costs = MoneyField(verbose_name="Total custos mensais", max_digits=14, decimal_places=2, default=0, null=True, blank=True)
    profit_target = MoneyField(verbose_name="Meta de lucro", max_digits=14, decimal_places=2, default=0, null=True, blank=True)
    gross_revenue_target = MoneyField(verbose_name="Faturamento bruto meta", max_digits=14, decimal_places=2, default=0, null=True, blank=True)
    profitability_multiplier = models.DecimalField(verbose_name="Multiplicador lucratividade", max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    working_hours_per_month = models.DecimalField(verbose_name="Horas úteis/mês", max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    minimum_hourly_cost = MoneyField(verbose_name="Custo hora mínimo", max_digits=14, decimal_places=2, default=0, null=True, blank=True)
    hourly_cost_value = MoneyField(verbose_name="Valor sua hora", max_digits=14, decimal_places=2, default=0, null=True, blank=True)

    class Meta:
        verbose_name = "Custo da oficina"
        verbose_name_plural = "Custos da oficina"
        ordering = ["-year", "-month"]
        constraints = [models.UniqueConstraint(fields=["workshop", "month", "year"], name="unique_workshop_cost_reference")]

    def __str__(self):
        return f"{self.get_month_display()}/{self.year}"

    def get_work_day_dates(self) -> set[date]:
        override_work_day_dates = getattr(self, "work_day_dates_override", None)
        if override_work_day_dates is not None:
            return set(override_work_day_dates)
        if self.pk:
            return set(self.work_days.values_list("date", flat=True))
        return set()

    def get_work_day_count(self) -> int:
        return len(self.get_work_day_dates())

    def calculate_working_hours_per_month(self) -> Decimal:
        if not self.work_hours_per_day:
            return Decimal("0.00")

        work_hours_per_day = Decimal(self.work_hours_per_day.total_seconds()) / Decimal("3600")
        productivity_per_day = Decimal(self.mechanic_quantity or 0) * work_hours_per_day * (self.productivity_average or Decimal("0"))

        working_hours_per_month = productivity_per_day * Decimal(self.work_days_per_month or 0)
        return working_hours_per_month.quantize(Decimal("0.01"), ROUND_HALF_UP)

    def calculate_minimum_hourly_cost(self) -> Money:
        working_hours = self.working_hours_per_month or Decimal("0")
        if working_hours == 0:
            return Money(0, "BRL")

        total_monthly_costs = self.total_monthly_costs or Money(0, "BRL")
        amount = total_monthly_costs.amount / working_hours
        return self._quantize_money(Money(amount, "BRL"))

    def calculate_hourly_cost_value(self) -> Money:
        working_hours = self.working_hours_per_month or Decimal("0")
        if working_hours == 0:
            return Money(0, "BRL")

        total_monthly_costs = self.total_monthly_costs or Money(0, "BRL")
        profit_margin = (self.profit_margin or Decimal(0)) * 100
        amount = ((total_monthly_costs.amount / 100 * profit_margin) + total_monthly_costs.amount) / working_hours
        return self._quantize_money(Money(amount, "BRL"))

    def calculate_monthly_costs(self) -> None:
        self.working_hours_per_month = self.calculate_working_hours_per_month()
        self.minimum_hourly_cost = self.calculate_minimum_hourly_cost()
        self.hourly_cost_value = self.calculate_hourly_cost_value()

    def _quantize_money(self, value: Money) -> Money:
        amount = value.amount.quantize(Decimal("0.01"), ROUND_HALF_UP)
        return Money(amount, value.currency)

    def calculate_total_value(self) -> Money:
        parts_purchase_cap = self.parts_purchase_cap or Money(0, "BRL")
        freight_cost = self.freight_cost or Money(0, "BRL")
        third_party_service_cap = self.third_party_service_cap or Money(0, "BRL")

        total_value = parts_purchase_cap + freight_cost + third_party_service_cap

        return self._quantize_money(total_value)

    def calculate_total_monthly_costs(self, items=None) -> Money:
        card_rate = (self.card_rate or Decimal(0)) * 100
        tax_rate = (self.tax_rate or Decimal(0)) * 100
        risk_coefficient = self.risk_coefficient if self.risk_coefficient is not None else Decimal(1)
        commission_rate = (self.commission_rate or Decimal(0)) * 100

        fixed_cost = Money(0, "BRL")

        iterable_items = items if items is not None else self.items.all()

        for item in iterable_items:
            fixed_cost += item.amount

        total = ((fixed_cost / 100) * (card_rate + tax_rate + commission_rate) + fixed_cost) * risk_coefficient

        return self._quantize_money(total)

    def calculate_profit_target(self, total_monthly_costs: Money) -> Money:
        return self._quantize_money(total_monthly_costs * Decimal("0.25"))

    def calculate_gross_revenue_target(self, total_monthly_costs: Money, profit_target: Money, total_value: Money) -> Money:
        return self._quantize_money(total_monthly_costs + profit_target + total_value)

    def calculate_profitability_multiplier(self, gross_revenue_target: Money, total_value: Money) -> Decimal:
        if total_value.amount == 0:
            return Decimal("0.00")

        multiplier = (gross_revenue_target.amount / total_value.amount).quantize(Decimal("0.01"), ROUND_HALF_UP)

        return multiplier.normalize()

    def calculate_all(self):
        total_value = self.calculate_total_value()
        total_monthly_costs = self.calculate_total_monthly_costs()
        profit_target = self.calculate_profit_target(total_monthly_costs)
        gross_revenue_target = self.calculate_gross_revenue_target(total_monthly_costs, profit_target, total_value)
        profitability_multiplier = self.calculate_profitability_multiplier(gross_revenue_target, total_value)

        self.total_value = total_value
        self.total_monthly_costs = total_monthly_costs
        self.profit_target = profit_target
        self.gross_revenue_target = gross_revenue_target
        self.profitability_multiplier = profitability_multiplier

        self.calculate_monthly_costs()


class WorkshopCostItem(models.Model):
    """
    Tabela filha que armazena o valor de cada MonthlyCost para aquele mês específico.
    """

    workshop_cost = models.ForeignKey(WorkshopCost, on_delete=models.CASCADE, related_name="items")
    monthly_cost = models.ForeignKey(MonthlyCost, on_delete=models.PROTECT)
    amount = MoneyField(verbose_name="Valor", max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = "Custo dos itens da oficina"
        verbose_name_plural = "Custos dos itens da oficina"
        unique_together = ("workshop_cost", "monthly_cost")


class WorkshopCostWorkDay(models.Model):
    workshop_cost = models.ForeignKey(WorkshopCost, on_delete=models.CASCADE, related_name="work_days")
    date = models.DateField(verbose_name="Data do dia trabalhado")
    description = models.CharField(verbose_name="Descrição", max_length=120, blank=True)

    class Meta:
        verbose_name = "Dia trabalhado do custo da oficina"
        verbose_name_plural = "Dias trabalhados do custo da oficina"
        ordering = ["date", "pk"]
        constraints = [models.UniqueConstraint(fields=["workshop_cost", "date"], name="unique_workshop_cost_work_day_date")]

    def __str__(self) -> str:
        return self.description or self.date.strftime("%d/%m/%Y")

    def clean(self) -> None:
        super().clean()

        if self.date.month != self.workshop_cost.month or self.date.year != self.workshop_cost.year:
            raise ValidationError({"date": "O dia trabalhado deve pertencer ao mesmo mês e ano do custo mensal."})
