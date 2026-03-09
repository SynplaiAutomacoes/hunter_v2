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

    # Usaremos dicionários para rastrear a maior quantidade encontrada por item
    dict_produtos = {}
    dict_servicos = {}

    def update_max_items(target_dict, description, quantity, unit_price, total_price):
        # Regra 1: Ignorar se a quantidade for zero
        if quantity <= 0:
            return

        # Regra 2: Manter apenas o de maior quantidade
        existing = target_dict.get(description)
        if not existing or quantity > existing["quantity"]:
            target_dict[description] = {
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": total_price,
            }

    for item in itens_all:
        preco_ajustado = item.adjusted_unit_price

        if item.product:
            valor_total = (preco_ajustado * item.quantity) + item.shipping
            update_max_items(dict_produtos, item.description, item.quantity, preco_ajustado, valor_total)

        elif item.service:
            valor_total = preco_ajustado * item.quantity
            update_max_items(dict_servicos, item.description, item.quantity, preco_ajustado, valor_total)

        elif item.kit:
            p_ovr, s_ovr = item._get_kit_override_maps()

            # Processa Produtos do Kit
            for kp in item.kit.kit_products.all():
                ovr = p_ovr.get(kp.product_id)
                u_p = ovr.product_selling_price if ovr else kp.product.selling_price
                u_c = ovr.product_cost_price if ovr else kp.product.cost_price
                qty = (ovr.quantity if ovr else kp.quantity) * item.quantity
                ship = (ovr.shipping if ovr else Money(0, "BRL")) * item.quantity
                sub_preco = item.calculate_individual_adjustment(u_p, u_c, is_product=True)

                update_max_items(dict_produtos, kp.product.name, qty, sub_preco, (sub_preco * qty) + ship)

            # Processa Serviços do Kit
            for ks in item.kit.kit_services.all():
                ovr = s_ovr.get(ks.service_id)
                u_p = ovr.service_selling_price if ovr else ks.service.selling_price
                u_c = ovr.service_cost_price if ovr else (ks.service.suggested_cost or Money(0, "BRL"))
                qty = (ovr.quantity if ovr else ks.quantity) * item.quantity

                sub_preco = item.calculate_individual_adjustment(u_p, u_c, is_product=False)

                update_max_items(dict_servicos, ks.service.name, qty, sub_preco, sub_preco * qty)

    # Converte os dicionários de volta para listas para o template
    produtos_final = list(dict_produtos.values())
    servicos_final = list(dict_servicos.values())

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
