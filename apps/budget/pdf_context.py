from __future__ import annotations

from djmoney.money import Money


def _build_pdf_pages(produtos: list[dict], servicos: list[dict]) -> list[dict]:
    return [
        {
            "produtos": produtos,
            "servicos": servicos,
            "page_number": 1,
            "total_pages": 1,
        }
    ]


def build_budget_pdf_context(*, budget, observacao: str, request=None) -> dict:
    from apps.budget.models import BudgetItem
    itens_all = BudgetItem.objects.filter(budget=budget).select_related("product", "service", "kit").prefetch_related("kit__kit_products__product", "kit__kit_services__service", "kit_overrides").order_by("id")

    produtos_final = []
    servicos_final = []

    for item in itens_all:
        preco_ajustado = item.adjusted_unit_price
        valor_total_item = preco_ajustado * item.quantity

        if item.product:
            produtos_final.append({"description": item.description, "quantity": item.quantity, "unit_price": preco_ajustado, "total_price": valor_total_item + item.shipping,})

        elif item.service:
            servicos_final.append({"description": item.description, "quantity": item.quantity, "unit_price": preco_ajustado, "total_price": valor_total_item})

        elif item.kit:
            p_ovr, s_ovr = item._get_kit_override_maps()

            for kp in item.kit.kit_products.all():
                ovr = p_ovr.get(kp.product_id)
                u_p = ovr.product_selling_price if ovr else kp.product.selling_price
                u_c = ovr.product_cost_price if ovr else kp.product.cost_price
                qty = (ovr.quantity if ovr else kp.quantity) * item.quantity
                ship = (ovr.shipping if ovr else Money(0, "BRL")) * item.quantity
                sub_preco = item.calculate_individual_adjustment(u_p, u_c, is_product=True)

                produtos_final.append({"description": kp.product.name, "quantity": qty, "unit_price": sub_preco, "total_price": (sub_preco * qty) + ship})

            for ks in item.kit.kit_services.all():
                ovr = s_ovr.get(ks.service_id)
                u_p = ovr.service_selling_price if ovr else ks.service.selling_price
                u_c = ovr.service_cost_price if ovr else (ks.service.suggested_cost or Money(0, "BRL"))
                qty = (ovr.quantity if ovr else ks.quantity) * item.quantity

                sub_preco = item.calculate_individual_adjustment(u_p, u_c, is_product=False)

                servicos_final.append({"description": ks.service.name, "quantity": qty, "unit_price": sub_preco, "total_price": sub_preco * qty})

    return {
        "budget": budget,
        "produtos": produtos_final,
        "servicos": servicos_final,
        "pages": _build_pdf_pages(produtos_final, servicos_final),
        "total_produtos": budget.get_total_products_by_slider,
        "total_servicos": budget.get_total_services_by_slider,
        "desconto": budget.discount_value,
        "total_geral": budget.total_budget_value,
        "observacao": observacao,
        "request": request,
    }
