from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

__all__ = [
    "DashboardMetrics",
]


@dataclass
class DashboardMetrics:
    workshop_id: int
    selected_month: int
    selected_year: int
    months: list[tuple[int, str]] = field(default_factory=list)
    years: list[int] = field(default_factory=list)
    cars_this_month: int = 0
    cars_this_month_list: list[Any] = field(default_factory=list)
    warranty_courtesy_cars: int = 0
    warranty_courtesy_cars_list: list[Any] = field(default_factory=list)
    average_ticket: Decimal = Decimal("0.00")
    projection: Decimal | None = None
    projection_warning: str = ""
    elapsed_days: int = 0
    remaining_days: int = 0
    configured_working_days: int | None = None
    business_holidays: int = 0
    total_sold_to_date: Decimal = Decimal("0.00")
    accumulated_profitability: float | Decimal = 0
    accumulated_markup: Decimal = Decimal("0.00")
    accumulated_markup_progress: int = 0
    warranty_return_rate: float | Decimal = 0
    approval_rate: float | Decimal = 0
    total_pending_receivable: Decimal = Decimal("0.00")
    total_pending_budgets: Decimal = Decimal("0.00")
    monthly_pending_receivable: Decimal = Decimal("0.00")
    total_general_pending_receivable: Decimal = Decimal("0.00")
    previous_months_pending_receivable: Decimal = Decimal("0.00")
    total_general_pending_budgets: Decimal = Decimal("0.00")
    monthly_pending_budgets: Decimal = Decimal("0.00")
    previous_months_pending_budgets: Decimal = Decimal("0.00")
    total_rejected_budgets: Decimal = Decimal("0.00")
    gross_revenue_target: Decimal | None = None
    daily_revenue_target: Decimal | None = None
    actual_daily_revenue: Decimal | None = None
    projection_vs_target: dict[str, Any] | None = None

    def as_context(self) -> dict[str, Any]:
        return {
            "workshop_id": self.workshop_id,
            "mes_selecionado": self.selected_month,
            "ano_selecionado": self.selected_year,
            "meses": self.months,
            "anos": self.years,
            "qtd_carros_mes": self.cars_this_month,
            "qtd_carros_mes_lista": self.cars_this_month_list,
            "qtd_carros_garantia_cortesia_mes": self.warranty_courtesy_cars,
            "qtd_carros_garantia_cortesia_mes_lista": self.warranty_courtesy_cars_list,
            "ticket_medio": self.average_ticket,
            "projecao": self.projection,
            "projecao_warning": self.projection_warning,
            "dias_transcorridos": self.elapsed_days,
            "dias_faltantes": self.remaining_days,
            "dias_uteis_mes_configurados": self.configured_working_days,
            "feriados_uteis": self.business_holidays,
            "total_vendido_ate_a_data": self.total_sold_to_date,
            "rentabilidade_acumulada_mes": self.accumulated_profitability,
            "markup_acumulado_mes": self.accumulated_markup,
            "markup_acumulado_progresso": self.accumulated_markup_progress,
            "indice_retorno_em_garantia_mes": self.warranty_return_rate,
            "taxa_aprovacao": self.approval_rate,
            "total_os_a_receber_em_execucao": self.total_pending_receivable,
            "total_orcamentos_aguardando_aprovacao": self.total_pending_budgets,
            "total_mensal_os_a_receber_em_execucao": self.monthly_pending_receivable,
            "total_geral_os_a_receber_em_execucao": self.total_general_pending_receivable,
            "total_meses_anteriores_os_a_receber_em_execucao": self.previous_months_pending_receivable,
            "total_geral_orcamentos_aguardando_aprovacao": self.total_general_pending_budgets,
            "total_mensal_orcamentos_aguardando_aprovacao": self.monthly_pending_budgets,
            "total_meses_anteriores_orcamentos_aguardando_aprovacao": self.previous_months_pending_budgets,
            "total_orcamentos_reprovados": self.total_rejected_budgets,
            "meta_faturamento_bruto": self.gross_revenue_target,
            "meta_faturamento_diario": self.daily_revenue_target,
            "faturamento_real_diario": self.actual_daily_revenue,
            "projecao_vs_meta": self.projection_vs_target,
        }
