from __future__ import annotations

from math import ceil

from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem


PRODUCTS_PER_PAGE = 4
SERVICES_PER_PAGE = 2


def _build_pdf_pages(produtos: list[dict], servicos: list[dict]) -> list[dict]:
    total_pages = max(ceil(len(produtos) / PRODUCTS_PER_PAGE) if produtos else 0, ceil(len(servicos) / SERVICES_PER_PAGE) if servicos else 0, 1)

    pages: list[dict] = []
    for index in range(total_pages):
        products_start = index * PRODUCTS_PER_PAGE
        services_start = index * SERVICES_PER_PAGE
        page_products = produtos[products_start : products_start + PRODUCTS_PER_PAGE]
        page_services = servicos[services_start : services_start + SERVICES_PER_PAGE]

        pages.append(
            {
                "produtos": page_products,
                "servicos": page_services,
                "empty_product_rows": range(max(PRODUCTS_PER_PAGE - len(page_products), 0)),
                "empty_service_rows": range(max(SERVICES_PER_PAGE - len(page_services), 0)),
                "page_number": index + 1,
                "total_pages": total_pages,
            }
        )

    return pages


def build_budget_pdf_context(*, budget: Budget, observacao: str, request=None) -> dict:
    itens_all = BudgetItem.objects.filter(budget=budget).select_related("product", "service", "kit").prefetch_related("kit__kit_products__product", "kit__kit_services__service", "kit_overrides").order_by("id")

    produtos: list[dict] = []
    servicos: list[dict] = []

    for item in itens_all:
        if item.product:
            produtos.append(
                {
                    "description": item.description,
                    "quantity": item.quantity,
                    "product_selling_price": item.product_selling_price,
                    "total_price": item.total_price,
                }
            )

        if item.service:
            servicos.append(
                {
                    "description": f"{item.description} x{item.quantity}" if item.quantity > 1 else item.description,
                }
            )

        if not item.kit:
            continue

        product_overrides, service_overrides = item._get_kit_override_maps()

        for kit_product in item.kit.kit_products.select_related("product").all():
            override = product_overrides.get(kit_product.product_id)
            quantity_per_kit = override.quantity if override else kit_product.quantity
            if quantity_per_kit <= 0:
                continue

            final_quantity = quantity_per_kit * item.quantity
            unit_price = override.product_selling_price if override else kit_product.product.selling_price
            shipping = override.shipping if override else Money(0, "BRL")
            line_total = ((unit_price * quantity_per_kit) + shipping) * item.quantity

            produtos.append(
                {
                    "description": f"{kit_product.product.name} (Kit: {item.kit.name})",
                    "quantity": final_quantity,
                    "product_selling_price": unit_price,
                    "total_price": line_total,
                }
            )

        for kit_service in item.kit.kit_services.select_related("service").all():
            override = service_overrides.get(kit_service.service_id)
            quantity_per_kit = override.quantity if override else kit_service.quantity
            if quantity_per_kit <= 0:
                continue

            final_quantity = quantity_per_kit * item.quantity
            label = f"{kit_service.service.name} (Kit: {item.kit.name})"
            servicos.append(
                {
                    "description": f"{label} x{final_quantity}" if final_quantity > 1 else label,
                }
            )

    context = {
        "budget": budget,
        "produtos": produtos,
        "servicos": servicos,
        "pages": _build_pdf_pages(produtos, servicos),
        "total_produtos": budget.total_products_value,
        "total_servicos": budget.total_services_value,
        "desconto": budget.discount_value,
        "total_geral": budget.total_budget_value,
        "observacao": observacao,
    }
    if request is not None:
        context["request"] = request
    return context
