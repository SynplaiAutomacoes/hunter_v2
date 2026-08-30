# ruff: noqa: F403,F405
from apps.budget.discount import split_budget_discount
from apps.budget.forms.steps.common import *
from apps.budget.models import BudgetItem
from dataclasses import dataclass
from datetime import timedelta
from django.db.models import F, Sum


@dataclass
class Step5PricingContext:
    custo_pecas: Money
    custo_pecas_sem_frete: Money
    custo_pecas_efetivo: Money
    custo_frete_pecas: Money
    custo_frete_servicos: Money
    custo_servico_terceiros: Money
    custo_hora_mecanico: Money
    custo_total_mao_obra: Money
    custo_efetivo_mao_obra: Money
    duracao_total: str
    venda_servico_terceiros: Money
    venda_pecas: Money
    venda_mao_obra: Money
    venda_mao_obra_base: Money
    metodo_precificacao: str
    lucro_operacional: Money
    rentabilidade: Decimal
    rentabilidade_class: str
    rentabilidade_bg: str
    status_texto: str
    mlr: float
    mlo: float
    discount_amount: Decimal
    discount_display: Money
    discount_products: Money
    discount_labor: Money
    discount_third_party: Money
    step5_calculation_done: bool
    step5_loading_hidden_class: str
    step5_method_hidden_class: str
    step5_should_block_next_button: str
    step5_calculated_input_value: str


def build_step5_context(budget) -> Step5PricingContext:
    dados = {}
    if budget.pk:
        dados = budget.calculate_pricing_methods()

    zerado = Money(0, "BRL")

    custo_pecas_sem_frete = budget.total_costs_products_value + budget.total_benefit_products_cost
    custo_frete_pecas = budget.total_cost_products_shipping
    custo_pecas = custo_pecas_sem_frete
    custo_pecas_efetivo = custo_pecas_sem_frete + custo_frete_pecas
    custo_frete_servicos = budget.total_cost_services_shipping
    custo_servico_terceiros = budget.total_third_party_services_cost

    benefit_tp_agg = (
        BudgetItem.objects.filter(
            budget=budget,
            item_benefit_type__in=("warranty", "courtesy"),
            service__is_third_party=True,
        ).aggregate(
            total=Sum(F("service_cost_price") * F("quantity"))
        )["total"]
    )
    if benefit_tp_agg:
        custo_servico_terceiros += Money(benefit_tp_agg, "BRL")

    custo_hora_mecanico = dados.get("custo_hora_mecanico") or zerado
    custo_frete_mao_obra = sum(
        (line.shipping for line in budget.pricing_snapshot.service_lines if not line.third_party),
        zerado,
    )
    benefit_labor_shipping = (
        BudgetItem.objects.filter(
            budget=budget,
            item_benefit_type__in=("warranty", "courtesy"),
            service__is_third_party=False,
        ).aggregate(total=Sum(F("service_shipping") * F("quantity")))["total"]
        or Decimal("0")
    )
    custo_frete_mao_obra += Money(benefit_labor_shipping, "BRL")

    snapshot_total_td = budget.total_duration or timedelta()

    benefit_items_qs = BudgetItem.objects.filter(
        budget=budget,
        item_benefit_type__in=("warranty", "courtesy"),
    )
    benefit_duration = timedelta()
    for item in benefit_items_qs:
        if item.duration:
            benefit_duration += item.duration * item.quantity

    total_td = snapshot_total_td + benefit_duration

    if not total_td:
        duracao_total = "00h 00m"
    else:
        ts = int(total_td.total_seconds())
        duracao_total = f"{ts // 3600:02d}h {(ts % 3600) // 60:02d}m"

    duracao_em_horas = Decimal(total_td.total_seconds()) / Decimal(3600)
    custo_total_mao_obra = custo_hora_mecanico * duracao_em_horas
    custo_efetivo_mao_obra = custo_total_mao_obra + custo_frete_mao_obra

    venda_servico_terceiros = budget.display_total_third_party_by_slider
    venda_pecas = budget.display_total_products_by_slider
    venda_mao_obra = budget.display_total_services_by_slider - venda_servico_terceiros
    venda_mao_obra_base = budget.pricing_snapshot.total_labor_selling_value + custo_frete_mao_obra

    metodo_precificacao = dados.get("method_name") or ""
    lucro_operacional = dados.get("lucro_operacional") or zerado
    rentabilidade = dados.get("rentabilidade") or Decimal("0")
    mlr = budget.get_mlr
    mlo = budget.get_mlo

    if rentabilidade >= 70:
        status_texto = "Bom"
        rentabilidade_class = "rentabilidade-bom"
        rentabilidade_bg = "bg-rentabilidade-bom"
    elif rentabilidade < 60:
        status_texto = "Ruim"
        rentabilidade_class = "rentabilidade-ruim"
        rentabilidade_bg = "bg-rentabilidade-ruim"
    else:
        status_texto = "Médio"
        rentabilidade_class = "rentabilidade-medio"
        rentabilidade_bg = "bg-rentabilidade-medio"

    discount_amount = budget.display_resolved_discount_value.amount if budget.display_resolved_discount_value else Decimal("0")
    discount_display = budget.display_resolved_discount_value if discount_amount != Decimal("0") else Money(0, "BRL")
    discount_split = split_budget_discount(budget=budget)
    step5_calculation_done = bool(budget.pk and (budget.step5_calculation_viewed or budget.current_step > 5))
    step5_loading_hidden_class = "hidden" if step5_calculation_done else ""
    step5_method_hidden_class = "" if step5_calculation_done else "hidden"
    step5_should_block_next_button = "true" if not step5_calculation_done else "false"
    step5_calculated_input_value = "1" if step5_calculation_done else "0"

    return Step5PricingContext(
        custo_pecas=custo_pecas,
        custo_pecas_sem_frete=custo_pecas_sem_frete,
        custo_pecas_efetivo=custo_pecas_efetivo,
        custo_frete_pecas=custo_frete_pecas,
        custo_frete_servicos=custo_frete_servicos,
        custo_servico_terceiros=custo_servico_terceiros,
        custo_hora_mecanico=custo_hora_mecanico,
        custo_total_mao_obra=custo_total_mao_obra,
        custo_efetivo_mao_obra=custo_efetivo_mao_obra,
        duracao_total=duracao_total,
        venda_servico_terceiros=venda_servico_terceiros,
        venda_pecas=venda_pecas,
        venda_mao_obra=venda_mao_obra,
        venda_mao_obra_base=venda_mao_obra_base,
        metodo_precificacao=metodo_precificacao,
        lucro_operacional=lucro_operacional,
        rentabilidade=rentabilidade,
        rentabilidade_class=rentabilidade_class,
        rentabilidade_bg=rentabilidade_bg,
        status_texto=status_texto,
        mlr=mlr,
        mlo=mlo,
        discount_amount=discount_amount,
        discount_display=discount_display,
        discount_products=discount_split.products,
        discount_labor=discount_split.labor,
        discount_third_party=discount_split.third_party,
        step5_calculation_done=step5_calculation_done,
        step5_loading_hidden_class=step5_loading_hidden_class,
        step5_method_hidden_class=step5_method_hidden_class,
        step5_should_block_next_button=step5_should_block_next_button,
        step5_calculated_input_value=step5_calculated_input_value,
    )
