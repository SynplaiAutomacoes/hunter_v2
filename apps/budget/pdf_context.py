from __future__ import annotations

import math
from decimal import Decimal

from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem


def _build_pdf_pages(produtos: list[dict], servicos: list[dict]) -> list[dict]:
    return [
        {
            "produtos": produtos,
            "servicos": servicos,
            "page_number": 1,
            "total_pages": 1,
        }
    ]


def build_budget_pdf_context(*, budget: Budget, observacao: str, request=None) -> dict:
    itens_all = BudgetItem.objects.filter(budget=budget).select_related("product", "service", "kit").prefetch_related("kit__kit_products__product", "kit__kit_services__service", "kit_overrides").order_by("id")

    # Valores Base
    custo_pecas = budget.total_costs_products_value
    frete_pecas = budget.total_products_shipping
    venda_pecas_base = budget.total_products_value - frete_pecas

    custo_serv_terceiros = budget.total_third_party_services_cost
    venda_serv_terceiros = budget.total_third_party_services_selling

    # Para MO, o formulário usa a duração e custo hora, mas no PDF
    # validamos pelo total_services_value (venda) e total_costs_services_value (custo)
    venda_mo_base = budget.total_services_value - venda_serv_terceiros
    custo_mo_base = budget.total_costs_services_value - custo_serv_terceiros

    # Cálculo do Lucro Total Redistribuível (A "Fatia" que o slider move)
    # Lucro Peças + Lucro MO
    lucro_total = (venda_pecas_base.amount - custo_pecas.amount) + (venda_mo_base.amount - custo_mo_base.amount)
    lucro_total = max(lucro_total, Decimal("0"))

    slider = budget.slider  # -100 a 100

    if slider < 0:
        # Slider p/ Esquerda: Peças aumentam.
        # Lucro Peça = total * % slider | Lucro MO = restante
        lucro_peca_novo = lucro_total * (Decimal(abs(slider)) / Decimal(100))
        lucro_mo_novo = lucro_total - lucro_peca_novo
    elif slider > 0:
        # Slider p/ Direita: MO aumenta.
        lucro_mo_novo = lucro_total * (Decimal(slider) / Decimal(100))
        lucro_peca_novo = lucro_total - lucro_mo_novo
    else:
        # Neutro
        lucro_peca_novo = venda_pecas_base.amount - custo_pecas.amount
        lucro_mo_novo = venda_mo_base.amount - custo_mo_base.amount

    # Novos Totais Alvo (Soma-se o custo fixo + lucro redistribuído + frete/terceiros)
    target_total_pecas = Money(custo_pecas.amount + lucro_peca_novo + frete_pecas.amount, "BRL")
    target_total_serv = Money(custo_mo_base.amount + lucro_mo_novo + venda_serv_terceiros.amount, "BRL")

    # Processamento de Itens para Regra de Três
    produtos_raw, servicos_raw = [], []
    for item in itens_all:
        if item.product:
            produtos_raw.append(
                {
                    "description": item.description,
                    "application": item.product.application,
                    "quantity": item.quantity,
                    "base_total": (item.product_selling_price * item.quantity) + item.shipping,
                }
            )
        if item.service:
            servicos_raw.append({"description": item.description, "quantity": item.quantity, "base_total": item.service_selling_price * item.quantity})
        if item.kit:
            product_overrides, service_overrides = item._get_kit_override_maps()
            for kp in item.kit.kit_products.all():
                ovr = product_overrides.get(kp.product_id)
                u_p = ovr.product_selling_price if ovr else kp.product.selling_price
                qty = (ovr.quantity if ovr else kp.quantity) * item.quantity
                ship = (ovr.shipping if ovr else Money(0, "BRL")) * item.quantity
                produtos_raw.append(
                    {
                        "description": kp.product.name,
                        "application": kp.product.application,
                        "quantity": qty,
                        "base_total": (u_p * qty) + ship,
                    }
                )
            for ks in item.kit.kit_services.all():
                ovr = service_overrides.get(ks.service_id)
                u_p = ovr.service_selling_price if ovr else ks.service.selling_price
                qty = (ovr.quantity if ovr else ks.quantity) * item.quantity
                servicos_raw.append({"description": ks.service.name, "quantity": qty, "base_total": u_p * qty})

    # Distribuição Proporcional nos itens
    def ajustar_proporcional(items, target, original):
        if original.amount <= 0:
            return items
        factor = target.amount / original.amount
        for it in items:
            # Arredondamento para cima (Ceil) na casa dos centavos
            novo_total = Decimal(math.ceil(it["base_total"].amount * factor * 100)) / Decimal(100)
            it["total_price"] = Money(novo_total, "BRL")
            it["product_selling_price"] = Money(Decimal(math.ceil((novo_total / it["quantity"]) * 100)) / Decimal(100), "BRL")
        return items

    produtos_final = ajustar_proporcional(produtos_raw, target_total_pecas, budget.total_products_value)
    servicos_final = ajustar_proporcional(servicos_raw, target_total_serv, budget.total_services_value)

    # Formatar descrições de serviço
    for s in servicos_final:
        if s["quantity"] > 1:
            s["description"] = f"{s['description']} x{s['quantity']}"

    return {
        "budget": budget,
        "produtos": produtos_final,
        "servicos": servicos_final,
        "pages": _build_pdf_pages(produtos_final, servicos_final),
        "total_produtos": target_total_pecas,
        "total_servicos": target_total_serv,
        "desconto": budget.discount_value,
        "total_geral": budget.total_budget_value,
        "observacao": observacao,
        "request": request,
    }
