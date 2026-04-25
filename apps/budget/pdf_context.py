from __future__ import annotations

import base64
from decimal import Decimal, ROUND_HALF_UP

from djmoney.money import Money

from apps.budget.pricing import format_duration_display
from apps.budget.review_display import build_budget_review_display
from apps.workshops.services.files import WorkshopFileStorageError, get_workshop_logo_file


_ZERO_DECIMAL = Decimal("0.00")
_TWO_DECIMAL_PLACES = Decimal("0.01")


def _build_pdf_pages(produtos: list[dict], servicos: list[dict], kits: list[dict]) -> list[dict]:
    return [
        {
            "produtos": produtos,
            "servicos": servicos,
            "kits": kits,
            "page_number": 1,
            "total_pages": 1,
        }
    ]


def _calculate_soma_markup(*, total_budget_value: Money, total_costs_products_value: Money, total_costs_services_value: Money) -> Decimal:
    total_cost_amount = total_costs_products_value.amount + total_costs_services_value.amount
    if total_cost_amount <= _ZERO_DECIMAL:
        return _ZERO_DECIMAL

    return (total_budget_value.amount / total_cost_amount).quantize(_TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)


def _format_decimal_multiplier(value: Decimal) -> str:
    quantized_value = value.quantize(_TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    sign = "-" if quantized_value < _ZERO_DECIMAL else ""
    absolute_value = abs(quantized_value)
    integer_part, decimal_part = f"{absolute_value:.2f}".split(".")
    grouped_integer = f"{int(integer_part):,}".replace(",", ".")
    return f"{sign}{grouped_integer},{decimal_part} vezes"


def build_workshop_logo_data_uri(*, workshop) -> str:
    try:
        stored_logo = get_workshop_logo_file(workshop)
    except WorkshopFileStorageError:
        return ""

    if stored_logo is None or not stored_logo.content:
        return ""

    encoded_logo = base64.b64encode(stored_logo.content).decode("ascii")
    return f"data:{stored_logo.content_type};base64,{encoded_logo}"


def build_budget_pdf_context(*, budget, observacao: str | None = None, request=None, zero_warranty_prices: bool = False, presentation: str = "expanded") -> dict:
    snapshot = budget.pricing_snapshot
    resolved_observation = observacao if observacao is not None else budget.pdf_observation
    is_warranty_budget = budget.is_warranty_budget
    is_client_warranty_pdf = is_warranty_budget and zero_warranty_prices
    total_produtos = budget.display_total_products_by_slider
    total_servicos = budget.display_total_services_by_slider
    desconto = budget.display_resolved_discount_value
    total_geral = budget.display_total_budget_value

    if is_client_warranty_pdf:
        total_produtos = Money(0, "BRL")
        total_servicos = Money(0, "BRL")
        desconto = Money(0, "BRL")
        total_geral = Money(0, "BRL")
    soma_markup = _calculate_soma_markup(
        total_budget_value=total_geral,
        total_costs_products_value=snapshot.total_costs_products_value,
        total_costs_services_value=snapshot.total_costs_services_value,
    )

    if presentation == "selected_items":
        review_display = build_budget_review_display(budget=budget)

        produtos = []
        servicos = []
        kits = []

        for line in review_display.direct_products:
            produtos.append({
                "id": line.item.product_id,
                "description": line.item.description,
                "quantity": line.item.quantity,
                "is_customer_supplied": line.item.is_customer_supplied,
                "application": getattr(line.item.product, "application", "") or "-",
                "code": getattr(line.item.product, "code", "") or "-",
                "location": getattr(line.item.product, "location", "") or "-",
                "unit_price": (Money(0, "BRL") if is_warranty_budget else line.unit_price),
                "adjusted_unit_price": (Money(0, "BRL") if is_warranty_budget else line.unit_price),
                "shipping": (Money(0, "BRL") if is_client_warranty_pdf else line.item.shipping),
                "total_price": (Money(0, "BRL") if is_client_warranty_pdf else (line.warranty_total_price if is_warranty_budget else line.total_price)),
                "product_cost_price": line.item.product_cost_price * line.item.quantity,
                "profit_value": (Money(0, "BRL") if is_warranty_budget else line.total_price - (line.item.product_cost_price * line.item.quantity)),
                "show_kit_duplicate_warning": False,
            })

        for line in review_display.direct_services:
            servicos.append({
                "id": line.item.service_id,
                "description": line.item.description,
                "quantity": line.item.quantity,
                "unit_price": (Money(0, "BRL") if is_warranty_budget else line.unit_price),
                "total_price": (Money(0, "BRL") if is_client_warranty_pdf else (line.warranty_total_price if is_warranty_budget else line.total_price)),
                "service_cost_price": line.warranty_total_price,
                "profit_value": (Money(0, "BRL") if is_warranty_budget else line.total_price - line.warranty_total_price),
                "duration_display": line.duration_display,
            })

        for line in review_display.kits:
            kit_item = line.item
            kit_quantity = kit_item.quantity
            product_overrides, service_overrides = kit_item._get_kit_override_maps()

            for kit_product in kit_item._iter_kit_products():
                override = product_overrides.get(kit_product.product_id)
                quantity = override.quantity if override else kit_product.quantity
                if quantity <= 0:
                    continue

                product = kit_product.product
                cost_price = override.product_cost_price if override else product.cost_price
                selling_price = override.product_selling_price if override else product.selling_price
                shipping = override.shipping if override else Money(0, "BRL")
                total_quantity = quantity * kit_quantity

                produtos.append({
                    "id": kit_product.product_id,
                    "description": product.name,
                    "quantity": total_quantity,
                    "is_customer_supplied": False,
                    "application": getattr(product, "application", "") or "-",
                    "code": getattr(product, "code", "") or "-",
                    "location": getattr(product, "location", "") or "-",
                    "unit_price": (Money(0, "BRL") if is_warranty_budget else selling_price),
                    "adjusted_unit_price": (Money(0, "BRL") if is_warranty_budget else selling_price),
                    "shipping": (Money(0, "BRL") if is_client_warranty_pdf else shipping),
                    "total_price": (Money(0, "BRL") if is_client_warranty_pdf else ((cost_price * total_quantity) + shipping if is_warranty_budget else (selling_price * total_quantity) + shipping)),
                    "product_cost_price": cost_price * total_quantity,
                    "profit_value": (Money(0, "BRL") if is_warranty_budget else (selling_price * total_quantity) - (cost_price * total_quantity)),
                    "show_kit_duplicate_warning": False,
                })

            for kit_service in kit_item._iter_kit_services():
                override = service_overrides.get(kit_service.service_id)
                quantity = override.quantity if override else kit_service.quantity
                if quantity <= 0:
                    continue

                service = kit_service.service
                if override:
                    cost_price = override.service_cost_price
                    selling_price = override.service_selling_price
                else:
                    cost_price, selling_price = kit_item.resolve_kit_service_base_prices(kit_service=kit_service)
                duration = override.duration if override and override.duration else kit_service.duration
                total_quantity = quantity * kit_quantity

                servicos.append({
                    "id": kit_service.service_id,
                    "description": service.name,
                    "quantity": total_quantity,
                    "unit_price": (Money(0, "BRL") if is_warranty_budget else selling_price),
                    "total_price": (Money(0, "BRL") if is_client_warranty_pdf else (cost_price * total_quantity if is_warranty_budget else selling_price * total_quantity)),
                    "service_cost_price": cost_price * total_quantity,
                    "profit_value": (Money(0, "BRL") if is_warranty_budget else (selling_price * total_quantity) - (cost_price * total_quantity)),
                    "duration_display": format_duration_display(duration * total_quantity) if duration else "00h 00m",
                })

            kits.append({
                "id": kit_item.kit_id,
                "description": kit_item.description,
                "quantity": kit_quantity,
                "product_count": kit_item.effective_kit_products_count,
                "service_count": kit_item.effective_kit_services_count,
                "products_summary": line.products_summary,
                "services_summary": line.services_summary,
            })
    else:
        produtos = [
            {
                "id": line.entity_id,
                "description": line.description,
                "quantity": line.quantity,
                "is_customer_supplied": line.is_customer_supplied,
                "application": line.application or "-",
                "code": line.code or "-",
                "location": line.location or "-",
                "unit_price": (Money(0, "BRL") if is_warranty_budget else line.unit_price),
                "adjusted_unit_price": (Money(0, "BRL") if is_warranty_budget else line.adjusted_unit_price),
                "shipping": (Money(0, "BRL") if is_client_warranty_pdf else line.shipping),
                "total_price": (Money(0, "BRL") if is_client_warranty_pdf else (line.cost_total + line.shipping if is_warranty_budget else line.total_price)),
                "product_cost_price": line.cost_total,
                "profit_value": (Money(0, "BRL") if is_warranty_budget else line.profit_value),
                "show_kit_duplicate_warning": line.show_kit_duplicate_warning,
            }
            for line in snapshot.product_lines
        ]

        servicos = [
            {
                "id": line.entity_id,
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": (Money(0, "BRL") if is_warranty_budget else line.adjusted_unit_price),
                "total_price": (Money(0, "BRL") if is_client_warranty_pdf else (line.cost_total if is_warranty_budget else line.total_price)),
                "service_cost_price": line.cost_total,
                "profit_value": (Money(0, "BRL") if is_warranty_budget else line.profit_value),
                "duration_display": line.duration_display,
            }
            for line in snapshot.service_lines
        ]

        kits = []

    workshop_logo_data_uri = build_workshop_logo_data_uri(workshop=budget.workshop)

    return {
        "budget": budget,
        "produtos": produtos,
        "servicos": servicos,
        "kits": kits,
        "pages": _build_pdf_pages(produtos, servicos, kits),
        "total_produtos": total_produtos,
        "total_servicos": total_servicos,
        "desconto": desconto,
        "total_geral": total_geral,
        "soma_markup": soma_markup,
        "soma_markup_display": _format_decimal_multiplier(soma_markup),
        "observacao": resolved_observation,
        "total_profit_product_value": (Money(0, "BRL") if is_warranty_budget else sum((line.profit_value for line in snapshot.product_lines), Money(0, "BRL"))),
        "total_profit_service_value": (Money(0, "BRL") if is_warranty_budget else sum((line.profit_value for line in snapshot.service_lines), Money(0, "BRL"))),
        "workshop_logo_data_uri": workshop_logo_data_uri,
        "request": request,
    }
