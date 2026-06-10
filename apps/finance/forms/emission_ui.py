from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from crispy_forms.layout import Div, Field, HTML
from djmoney.money import Money

from apps.finance.services.pricing import build_emission_pricing_snapshot_for_workorder
from apps.workorder.models import WorkOrder


@dataclass(frozen=True)
class Step5PricingPanelData:
    cost_products: Money
    cost_products_shipping: Money
    cost_third_party_services: Money
    mechanic_hour_cost: Money
    labor_total_cost: Money
    duration_display: str
    sale_third_party_services: Money
    sale_products: Money
    sale_labor: Money
    operational_profit: Money
    profitability: Decimal
    profitability_status: str
    profitability_class: str
    profitability_bg: str
    mlr: Decimal
    mlo: Decimal
    discount_display: Money
    discount_percentage_display: str
    total_base_value: Money
    total_budget_value: Money


def format_money(value: Any) -> str:
    amount: Decimal
    if hasattr(value, "amount"):
        amount = value.amount
    else:
        amount = Decimal(str(value or 0))
    amount = amount.quantize(Decimal("0.01"))
    integer_part, decimal_part = f"{amount:.2f}".split(".")
    grouped_integer = f"{int(integer_part):,}".replace(",", ".")
    return f"R$ {grouped_integer},{decimal_part}"


def format_percentage(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}%".replace(".", ",")


def resolve_discount_percentage_display(*, total_base_value: Money, discount_value: Money) -> str:
    base_amount = Decimal(getattr(total_base_value, "amount", Decimal("0.00")) or Decimal("0.00"))
    discount_amount = Decimal(getattr(discount_value, "amount", Decimal("0.00")) or Decimal("0.00"))

    if base_amount <= Decimal("0.00") or discount_amount <= Decimal("0.00"):
        return format_percentage(Decimal("0.00"))

    percentage = ((discount_amount / base_amount) * Decimal("100")).quantize(Decimal("0.01"))
    return format_percentage(min(percentage, Decimal("100.00")))


def clamp_slider_value(value: object, default: int = 0) -> int:
    try:
        slider_source = default if value in (None, "") else str(value)
        return max(-100, min(100, int(slider_source)))
    except (TypeError, ValueError):
        return max(-100, min(100, int(default)))


def resolve_initial_slider(*, initial_value: object, persisted_slider: int | None = None, default_slider: int = 0) -> int:
    base_value = persisted_slider if persisted_slider is not None else default_slider
    return clamp_slider_value(initial_value, default=base_value)


def build_slider_widget_attrs(
    *,
    preview_url: str,
    include_selector: str,
    swap: str,
    target_selector: str | None = None,
    trigger: str = "change",
    method: str = "post",
    sync_selector: str | None = None,
) -> dict[str, str]:
    attrs = {
        "type": "range",
        "min": "-100",
        "max": "100",
        "step": "5",
        "class": "w-full centered-range",
    }
    if preview_url:
        request_attr = "hx-post" if method.lower() == "post" else "hx-get"
        attrs.update(
            {
                request_attr: preview_url,
                "hx-trigger": trigger,
                "hx-swap": swap,
                "hx-include": include_selector,
            }
        )
        if target_selector:
            attrs["hx-target"] = target_selector
        if sync_selector:
            attrs["hx-sync"] = sync_selector
    return attrs


def build_step5_pricing_panel_data(*, workorder: WorkOrder, selected_slider: int) -> Step5PricingPanelData:
    snapshot = build_emission_pricing_snapshot_for_workorder(workorder=workorder, slider_override=selected_slider)
    pricing_data = workorder.calculate_pricing_methods() or {}
    zero_money = Money(0, "BRL")

    total_base_value = workorder.get_total_products_by_slider + workorder.get_total_services_by_slider
    total_budget_value = workorder.total_budget_value
    resolved_discount_value = total_base_value - total_budget_value

    sale_third_party_services = sum((line.adjusted_total for line in snapshot.service_lines if line.third_party), zero_money)
    sale_labor = sum((line.adjusted_total for line in snapshot.service_lines if not line.third_party), zero_money)
    total_cost_value = workorder.total_costs_products_value + workorder.total_products_shipping + workorder.total_third_party_services_cost + workorder.total_labor_cost_value
    operational_profit = total_base_value - total_cost_value

    if total_base_value.amount > 0:
        profitability = ((operational_profit.amount / total_base_value.amount) * Decimal("100")).quantize(Decimal("0.01"))
    else:
        profitability = Decimal("0.00")

    if profitability >= 70:
        profitability_status = "Bom"
        profitability_class = "rentabilidade-bom"
        profitability_bg = "bg-rentabilidade-bom"
    elif profitability < 60:
        profitability_status = "Ruim"
        profitability_class = "rentabilidade-ruim"
        profitability_bg = "bg-rentabilidade-ruim"
    else:
        profitability_status = "Medio"
        profitability_class = "rentabilidade-medio"
        profitability_bg = "bg-rentabilidade-medio"

    discount_display = resolved_discount_value if resolved_discount_value.amount > 0 else zero_money
    discount_percentage_display = resolve_discount_percentage_display(total_base_value=total_base_value, discount_value=resolved_discount_value)
    products_cost_base = workorder.total_costs_products_value + workorder.total_products_shipping
    services_cost_base = workorder.total_third_party_services_cost + workorder.total_labor_cost_value
    mlr = (snapshot.total_products_by_slider.amount / products_cost_base.amount).quantize(Decimal("0.01")) if products_cost_base.amount > 0 else Decimal("0.00")
    mlo = (snapshot.total_services_by_slider.amount / services_cost_base.amount).quantize(Decimal("0.01")) if services_cost_base.amount > 0 else Decimal("0.00")

    return Step5PricingPanelData(
        cost_products=workorder.total_costs_products_value,
        cost_products_shipping=workorder.total_products_shipping,
        cost_third_party_services=workorder.total_third_party_services_cost,
        mechanic_hour_cost=pricing_data.get("custo_hora_mecanico") or zero_money,
        labor_total_cost=workorder.total_labor_cost_value,
        duration_display=workorder.total_duration_display,
        sale_third_party_services=sale_third_party_services,
        sale_products=snapshot.total_products_by_slider,
        sale_labor=sale_labor,
        operational_profit=operational_profit,
        profitability=profitability,
        profitability_status=profitability_status,
        profitability_class=profitability_class,
        profitability_bg=profitability_bg,
        mlr=mlr,
        mlo=mlo,
        discount_display=discount_display,
        discount_percentage_display=discount_percentage_display,
        total_base_value=total_base_value,
        total_budget_value=total_budget_value,
    )


def _build_sale_products_span(*, prefix: str, panel_data: Step5PricingPanelData, oob: bool = False) -> str:
    oob_attr = ' hx-swap-oob="true"' if oob else ""
    return f'''
        <span id="{prefix}-display-venda-pecas"{oob_attr}
              class="col-span-4 p-2 border-l border-base-300 whitespace-nowrap step5-accent-text"
              data-base-val="{panel_data.sale_products.amount}"
              data-cost-val="{panel_data.cost_products.amount}"
              data-frete-val="{panel_data.cost_products_shipping.amount}">
            {panel_data.sale_products}
        </span>
    '''


def _build_sale_labor_span(*, prefix: str, panel_data: Step5PricingPanelData, oob: bool = False) -> str:
    oob_attr = ' hx-swap-oob="true"' if oob else ""
    return f'''
        <span id="{prefix}-display-venda-mo"{oob_attr}
              class="col-span-4 p-2 border-l border-base-300 step5-accent-text"
              data-base-val="{panel_data.sale_labor.amount}"
              data-cost-val="{panel_data.labor_total_cost.amount}">
            {panel_data.sale_labor}
        </span>
    '''


def build_step5_pricing_panel_layout(*, prefix: str, panel_data: Step5PricingPanelData, slider_field_name: str, form_selector: str) -> Div:
    return Div(
        HTML(_build_step5_styles_html()),
        HTML(build_step5_slider_script_html(prefix=prefix, form_selector=form_selector, input_name=slider_field_name)),
        Div(
            Div(
                Div(
                    HTML('<h3 class="text-3xl font-bold mb-2 border-b-3 step5-accent-border text-center step5-accent-text">Método Hunter</h3>'),
                    Div(
                        HTML(
                            f"""
                            <div class="grid grid-cols-1 md:grid-cols-2 mt-7 gap-x-8 gap-y-3 text-base text-base-content font-semibold">
                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Peças</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.cost_products}</span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Valor de Venda de Peças</span>
                                    {_build_sale_products_span(prefix=prefix, panel_data=panel_data)}
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Frete de Peças</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.cost_products_shipping}</span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Valor de Venda de Servico de Terceiros</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.sale_third_party_services}</span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Servico de Terceiros</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.cost_third_party_services}</span>
                                </div>

                                <div class="grid grid-cols-12"></div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo da Hora do Mecânico</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.mechanic_hour_cost}</span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Valor de Venda de Mão de Obra</span>
                                    {_build_sale_labor_span(prefix=prefix, panel_data=panel_data)}
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100 font-semibold">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo Total da Mão de Obra</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.labor_total_cost}</span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Duração Total</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.duration_display}</span>
                                </div>

                                <div class="md:col-span-2 h-2"></div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100 font-bold">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Lucro Operacional</span>
                                    <span class="col-span-4 p-2 border-l border-base-300 step5-accent-text">{panel_data.operational_profit}</span>
                                </div>

                                <div class="grid grid-cols-12 border {panel_data.profitability_class} {panel_data.profitability_bg}">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Rentabilidade</span>
                                    <span class="col-span-4 p-2 border-l {panel_data.profitability_class} font-bold">
                                        {panel_data.profitability:.2f}% ({panel_data.profitability_status})
                                    </span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">MLO</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.mlo:.2f}</span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">MLR</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.mlr:.2f}</span>
                                </div>
                            </div>
                            """
                        ),
                        css_class="h-full",
                    ),
                    Div(
                        HTML(
                            f"""<div class="text-center text-base-content mt-6">
                                    <p class="text-2xl font-bold">Valor do Orçamento</p>
                                    <p class="text-3xl font-black step5-accent-text">{panel_data.total_budget_value}</p>
                                </div>"""
                        )
                    ),
                    css_class="bg-base-200 p-6 rounded-2xl border-2 border-base-300 h-full flex flex-col text-base-content",
                ),
                css_class="col-span-12 lg:col-span-6 h-full",
            ),
            Div(
                Div(
                    Div(
                        HTML('<h4 class="font-bold text-lg mb-2">Defina o percentual para cada Nota Fiscal</h4>'),
                        HTML(
                            f"""
                            <div class="flex justify-between mb-1">
                                <span class="text-sm font-bold">Peça: <span id="{prefix}-val-peca">0</span>%</span>
                                <span class="text-sm font-bold">Mão de Obra: <span id="{prefix}-val-mo">0</span>%</span>
                            </div>
                            """
                        ),
                        Field(slider_field_name, label=False, help_text=False, wrapper_class="w-full"),
                        HTML('<p class="text-sm text-gray-500 font-semibold italic">Defina o valor que gostaria de emitir como NF de peça ou NF de serviço.</p>'),
                        css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                    ),
                    Div(
                        HTML('<h4 class="font-bold text-lg mb-2">Desconto</h4>'),
                        HTML(
                            f"""
                            <div class="rounded-lg border border-base-300 bg-base-100 px-4 py-3 space-y-2">
                                <div class="flex justify-between text-sm font-semibold text-base-content/70">
                                    <span>Percentual</span>
                                    <span>{panel_data.discount_percentage_display}</span>
                                </div>
                                <div class="flex justify-between text-lg font-semibold">
                                    <span>Valor</span>
                                    <span>{panel_data.discount_display}</span>
                                </div>
                            </div>
                            """
                        ),
                        css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                    ),
                    Div(
                        HTML('<h4 class="font-bold text-lg mb-2 text-center border-b-1 border-gray-300">Valor Final</h4>'),
                        HTML('<h5 class="font-semibold text-lg mb-2 text-center">Valor do Orçamento com desconto aplicado:</h5>'),
                        HTML(
                            f"""
                            <div class="space-y-3">
                                <div class="flex justify-between text-xl font-semibold">
                                    <span>Subtotal:</span>
                                    <span>{panel_data.total_base_value}</span>
                                </div>
                                <div class="flex justify-between text-xl font-semibold">
                                    <span>Desconto ({panel_data.discount_percentage_display}):</span>
                                    <span>{panel_data.discount_display}</span>
                                </div>
                                <div class="flex justify-between text-xl font-black">
                                    <span>Valor Final:</span>
                                    <span id="{prefix}-valor-final-display">{panel_data.total_budget_value}</span>
                                </div>
                            </div>
                            """
                        ),
                        css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                    ),
                    css_class="sticky top-4",
                ),
                css_class="col-span-12 lg:col-span-6",
            ),
            css_class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch",
        ),
    )


def build_step5_summary_layout(*, prefix: str, panel_data: Step5PricingPanelData, slider_field_name: str, form_selector: str, body_html: str) -> Div:
    return Div(
        HTML(_build_step5_styles_html()),
        HTML(build_step5_slider_script_html(prefix=prefix, form_selector=form_selector, input_name=slider_field_name)),
        Div(
            Div(
                Div(
                    HTML('<h3 class="text-3xl font-bold mb-2 border-b-3 step5-accent-border text-center step5-accent-text">Método Hunter</h3>'),
                    Div(
                        HTML(
                            f"""
                            <div class="grid grid-cols-1 md:grid-cols-2 mt-7 gap-x-8 gap-y-3 text-base text-base-content font-semibold">
                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Peças</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.cost_products}</span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Valor de Venda de Peças</span>
                                    {_build_sale_products_span(prefix=prefix, panel_data=panel_data)}
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Frete de Peças</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.cost_products_shipping}</span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Valor de Venda de Servico de Terceiros</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.sale_third_party_services}</span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo de Servico de Terceiros</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.cost_third_party_services}</span>
                                </div>

                                <div class="grid grid-cols-12"></div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo da Hora do Mecânico</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.mechanic_hour_cost}</span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Valor de Venda de Mão de Obra</span>
                                    {_build_sale_labor_span(prefix=prefix, panel_data=panel_data)}
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100 font-semibold">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Custo Total da Mão de Obra</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.labor_total_cost}</span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Duração Total</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.duration_display}</span>
                                </div>

                                <div class="md:col-span-2 h-2"></div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100 font-bold">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Lucro Operacional</span>
                                    <span class="col-span-4 p-2 border-l border-base-300 step5-accent-text">{panel_data.operational_profit}</span>
                                </div>

                                <div class="grid grid-cols-12 border {panel_data.profitability_class} {panel_data.profitability_bg}">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">Rentabilidade</span>
                                    <span class="col-span-4 p-2 border-l {panel_data.profitability_class} font-bold">
                                        {panel_data.profitability:.2f}% ({panel_data.profitability_status})
                                    </span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">MLO</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.mlo:.2f}</span>
                                </div>

                                <div class="grid grid-cols-12 border border-base-300 bg-base-100">
                                    <span class="col-span-8 p-2 bg-base-200/70 text-base-content/80">MLR</span>
                                    <span class="col-span-4 p-2 border-l border-base-300">{panel_data.mlr:.2f}</span>
                                </div>
                            </div>
                            """
                        ),
                        css_class="h-full",
                    ),
                    Div(
                        HTML(
                            f"""<div class="text-center text-base-content mt-6">
                                    <p class="text-2xl font-bold">Valor do Orçamento</p>
                                    <p class="text-3xl font-black step5-accent-text">{panel_data.total_budget_value}</p>
                                </div>"""
                        )
                    ),
                    css_class="bg-base-200 p-6 rounded-2xl border-2 border-base-300 h-full flex flex-col text-base-content",
                ),
                HTML(body_html),
                css_class="col-span-12 lg:col-span-7 space-y-6",
            ),
            Div(
                Div(
                    Div(
                        HTML('<h4 class="font-bold text-lg mb-2">Defina o percentual para cada Nota Fiscal</h4>'),
                        HTML(
                            f"""
                            <div class="flex justify-between mb-1">
                                <span class="text-sm font-bold">Peça: <span id="{prefix}-val-peca">0</span>%</span>
                                <span class="text-sm font-bold">Mão de Obra: <span id="{prefix}-val-mo">0</span>%</span>
                            </div>
                            """
                        ),
                        Field(slider_field_name, label=False, help_text=False, wrapper_class="w-full"),
                        HTML('<p class="text-sm text-gray-500 font-semibold italic">Defina o valor que gostaria de emitir como NF de peça ou NF de serviço.</p>'),
                        css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                    ),
                    Div(
                        HTML('<h4 class="font-bold text-lg mb-2">Desconto</h4>'),
                        HTML(
                            f"""
                            <div class="rounded-lg border border-base-300 bg-base-100 px-4 py-3 space-y-2">
                                <div class="flex justify-between text-sm font-semibold text-base-content/70">
                                    <span>Percentual</span>
                                    <span>{panel_data.discount_percentage_display}</span>
                                </div>
                                <div class="flex justify-between text-lg font-semibold">
                                    <span>Valor</span>
                                    <span>{panel_data.discount_display}</span>
                                </div>
                            </div>
                            """
                        ),
                        css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                    ),
                    Div(
                        HTML('<h4 class="font-bold text-lg mb-2 text-center border-b-1 border-gray-300">Valor Final</h4>'),
                        HTML('<h5 class="font-semibold text-lg mb-2 text-center">Valor do Orçamento com desconto aplicado:</h5>'),
                        HTML(
                            f"""
                            <div class="space-y-3">
                                <div class="flex justify-between text-xl font-semibold">
                                    <span>Subtotal:</span>
                                    <span>{panel_data.total_base_value}</span>
                                </div>
                                <div class="flex justify-between text-xl font-semibold">
                                    <span>Desconto ({panel_data.discount_percentage_display}):</span>
                                    <span>{panel_data.discount_display}</span>
                                </div>
                                <div class="flex justify-between text-xl font-black">
                                    <span>Valor Final:</span>
                                    <span id="{prefix}-valor-final-display">{panel_data.total_budget_value}</span>
                                </div>
                            </div>
                            """
                        ),
                        css_class="mb-8 p-4 bg-base-200/50 rounded-lg",
                    ),
                    css_class="sticky top-4",
                ),
                css_class="col-span-12 lg:col-span-5 self-start",
            ),
            css_class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start",
        ),
    )


def build_step5_preview_oob_html(*, prefix: str, panel_data: Step5PricingPanelData, warning_html: str, preview_html: str) -> str:
    return f"""
        {_build_sale_products_span(prefix=prefix, panel_data=panel_data, oob=True)}
        {_build_sale_labor_span(prefix=prefix, panel_data=panel_data, oob=True)}
        <div id="{prefix}-warning-block" hx-swap-oob="true">{warning_html}</div>
        <div id="{prefix}-preview-block" hx-swap-oob="true">{preview_html}</div>
    """


def build_step5_slider_script_html(*, prefix: str, form_selector: str, input_name: str) -> str:
    init_name = f"init_{prefix.replace('-', '_')}_step5_slider"
    return f"""
        <script>
            (function () {{
                window.{init_name} = function {init_name}() {{
                    const slider = document.querySelector('{form_selector} input[name="{input_name}"]');
                    const labelPecaPct = document.getElementById('{prefix}-val-peca');
                    const labelMOPct = document.getElementById('{prefix}-val-mo');

                    if (!slider || !labelPecaPct || !labelMOPct) return;

                    function updateFill(val) {{
                        const min = -100;
                        const max = 100;
                        const center = 50;
                        const percent = ((val - min) / (max - min)) * 100;

                        if (val === 0) {{
                            slider.style.setProperty('--left', `${{center}}%`);
                            slider.style.setProperty('--right', `${{center}}%`);
                        }} else if (val < 0) {{
                            slider.style.setProperty('--left', `${{percent}}%`);
                            slider.style.setProperty('--right', `${{center}}%`);
                        }} else {{
                            slider.style.setProperty('--left', `${{center}}%`);
                            slider.style.setProperty('--right', `${{percent}}%`);
                        }}
                    }}

                    function update(val) {{
                        const numericValue = parseInt(val || 0, 10) || 0;
                        labelPecaPct.textContent = numericValue < 0 ? Math.abs(numericValue) : 0;
                        labelMOPct.textContent = numericValue > 0 ? numericValue : 0;
                        updateFill(numericValue);
                    }}

                    if (slider.dataset.step5Bound !== 'true') {{
                        slider.addEventListener('input', function (event) {{
                            update(event.target.value);
                        }});
                        slider.dataset.step5Bound = 'true';
                    }}

                    update(slider.value || 0);
                }};

                document.addEventListener('DOMContentLoaded', window.{init_name});
                document.body.addEventListener('htmx:afterSettle', window.{init_name});
            }})();
        </script>
    """


def _build_step5_styles_html() -> str:
    return """
        <style>
            :root[data-theme="light"] {
              --step5-accent: #0f766e;
              --step5-warning-soft: rgba(245, 158, 11, 0.16);
            }

            :root[data-theme="dark"] {
              --step5-accent: #5eead4;
              --step5-warning-soft: rgba(245, 158, 11, 0.22);
            }

            input[type="range"].centered-range {
              -webkit-appearance: none;
              -moz-appearance: none;
              width: 100%;
              height: 8px;
              background: transparent;
            }

            input[type="range"].centered-range::-webkit-slider-runnable-track {
              height: 8px;
              border-radius: 999px;
              background: linear-gradient(
                to right,
                #e5e7eb var(--left),
                #2563eb var(--left),
                #2563eb var(--right),
                #e5e7eb var(--right)
              );
            }

            input[type="range"].centered-range::-webkit-slider-thumb {
              -webkit-appearance: none;
              width: 24px;
              height: 24px;
              background: #007bff;
              border-radius: 50%;
              margin-top: -8px;
              cursor: pointer;
            }

            input[type="range"].centered-range::-moz-range-track {
              height: 8px;
              border-radius: 999px;
              background: linear-gradient(
                to right,
                #e5e7eb var(--left),
                #2563eb var(--left),
                #2563eb var(--right),
                #e5e7eb var(--right)
              );
            }

            input[type="range"].centered-range::-moz-range-thumb {
              width: 24px;
              height: 24px;
              background: #007bff;
              border-radius: 50%;
              border: none;
            }

            .step5-accent-text {
                color: var(--step5-accent);
            }

            .step5-accent-border {
                border-color: var(--step5-accent);
            }

            .step5-warning-surface {
                background-color: var(--step5-warning-soft);
            }

            .rentabilidade-bom { color: #22c55e !important; border-color: #22c55e !important; }
            .rentabilidade-medio { color: #f59e0b !important; border-color: #f59e0b !important; }
            .rentabilidade-ruim { color: #ef4444 !important; border-color: #ef4444 !important; }

            .bg-rentabilidade-bom { background-color: rgba(34, 197, 94, 0.1); }
            .bg-rentabilidade-medio { background-color: rgba(245, 158, 11, 0.1); }
            .bg-rentabilidade-ruim { background-color: rgba(239, 68, 68, 0.1); }
        </style>
    """
