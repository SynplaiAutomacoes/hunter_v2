from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Self

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from djmoney.models.fields import MoneyField
from moneyed import Money

from apps.core.models import TimeStampedModel
from apps.workshops.models.workshops import Workshop
from apps.workshops.models.monthly_costs import MonthlyCost


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
    mechanic_quantity = models.PositiveIntegerField(verbose_name="Qtd. Mecânicos Produtivos", validators=[MinValueValidator(0)])
    work_hours_per_day = models.DurationField(
        verbose_name="Horas de trabalho/dia",
        validators=[MinValueValidator(timedelta()), MaxValueValidator(timedelta(hours=24))],
        default=8,
        help_text="Máximo 24h",
    )
    work_days_per_month = models.IntegerField(
        verbose_name="Dias úteis/mês",
        validators=[MinValueValidator(0), MaxValueValidator(31)],
        default=22,
        help_text="Máximo 31 dias",
    )
    productivity_average = models.DecimalField(
        verbose_name="Produtividade Média",
        max_digits=5,
        decimal_places=2,
        default=0.60,
        help_text="50% a 80%",
        validators=[MinValueValidator(0.5), MaxValueValidator(0.8)],
    )

    # --- Taxas e Impostos ---
    card_rate = models.DecimalField(verbose_name="Taxa Cartão", max_digits=7, decimal_places=6, default=0, null=True, blank=True)
    tax_rate = models.DecimalField(verbose_name="Impostos", max_digits=7, decimal_places=6, default=0, null=True, blank=True)
    profit_margin = models.DecimalField(verbose_name="Margem de Lucro", max_digits=7, decimal_places=6, default=0, null=True, blank=True)
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
        verbose_name="Coeficiente de Risco",
        max_digits=3,
        decimal_places=2,
        default=1.00,
        validators=[MinValueValidator(1.0), MaxValueValidator(1.5)],
        help_text="1.0 a 1.2 para veículo popular, 1.2 a 1.4 para SUVs e 1.5 para premium, está relacionado ao risco da oficina.",
        null=True,
        blank=True,
    )

    # --- Metas e Indicadores (Inputs manuais) ---
    parts_purchase_cap = MoneyField(verbose_name="Teto Compras Peças", max_digits=14, decimal_places=2, null=True, blank=True)
    freight_cost = MoneyField(
        verbose_name="Frete",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    third_party_service_cap = MoneyField(verbose_name="Teto Serviços Terceiros", max_digits=14, decimal_places=2, null=True, blank=True)

    # --- Calculados (Armazenados para histórico, readonly no form) ---
    total_value = MoneyField(verbose_name="Valor Total", max_digits=14, decimal_places=2, default=0, null=True, blank=True)
    total_monthly_costs = MoneyField(verbose_name="Total Custos Mensais", max_digits=14, decimal_places=2, default=0, null=True, blank=True)
    profit_target = MoneyField(verbose_name="Meta de Lucro", max_digits=14, decimal_places=2, default=0, null=True, blank=True)
    gross_revenue_target = MoneyField(verbose_name="Faturamento Bruto Meta", max_digits=14, decimal_places=2, default=0, null=True, blank=True)
    profitability_multiplier = models.DecimalField(verbose_name="Multiplicador Lucratividade", max_digits=10, decimal_places=4, default=0, null=True, blank=True)

    class Meta:
        verbose_name = "Custo da Oficina"
        verbose_name_plural = "Custos da Oficina"
        ordering = ["-year", "-month"]
        constraints = [models.UniqueConstraint(fields=["workshop", "month", "year"], name="unique_workshop_cost_reference")]

    def __str__(self):
        return f"{self.get_month_display()}/{self.year}"
    
    def calculate_total_value(self) -> Money:
        parts_purchase_cap = self.parts_purchase_cap or Money(0, 'BRL')
        freight_cost = self.freight_cost or Money(0, 'BRL')
        third_party_service_cap = self.third_party_service_cap or Money(0, 'BRL')
        
        total_value = parts_purchase_cap + freight_cost + third_party_service_cap
        
        return total_value
    
    def calculate_total_monthly_costs(self) -> Money:
        card_rate = self.card_rate or Decimal(0)
        tax_rate = self.tax_rate or Decimal(0)
        risk_coefficient = self.risk_coefficient or Decimal(0)
        comission_rate = self.commission_rate or Decimal(0)
        
        fixed_cost = Money(0, 'BRL')
        
        for item in self.items.all():
            fixed_cost += item.amount
            
        total = (fixed_cost / 100 * (card_rate + tax_rate + comission_rate) + fixed_cost) * risk_coefficient
        
        return total
    
    def calculate_profit_target(self, total_monthly_costs: Money) -> Money:
        return total_monthly_costs * Decimal('0.25')
        
    def calculate_gross_revenue_target(self, total_monthly_costs: Money, profit_target: Money, total_value: Money) -> Money:
        return total_monthly_costs + profit_target + total_value
    
    def calculate_profitability_multiplier(self, gross_revenue_target: Money, total_value: Money) -> Decimal:
        if total_value.amount == 0:
            return Decimal('0.00')
        
        multiplier = (gross_revenue_target.amount / total_value.amount).quantize(Decimal('0.01'), ROUND_HALF_UP)
        
        return multiplier
        


class WorkshopCostItem(models.Model):
    """
    Tabela filha que armazena o valor de cada MonthlyCost para aquele mês específico.
    """

    workshop_cost = models.ForeignKey(WorkshopCost, on_delete=models.CASCADE, related_name="items")
    monthly_cost = models.ForeignKey(MonthlyCost, on_delete=models.PROTECT)
    amount = MoneyField(verbose_name="Valor", max_digits=14, decimal_places=2)

    class Meta:
        unique_together = ("workshop_cost", "monthly_cost")
